"""Regression tests for the issues found in the independent code review."""
import json

import msgpack
import pytest

from policybank import data as D
from policybank.data import Episode
from policybank.metrics import bootstrap_q, challenge_q, rollouts_for_effect, rollouts_for_selection, task_means
from policybank.provenance import AuditError, check_coverage, parse_metrics, verify_directory
from policybank.routing import Route, RouteError
from policybank.selection import Gaussian, select_by_level
from policybank.serving.codec import unpack


def ep(t, i, q, p="p"):
    return Episode(task_id=t, task=f"t{t}", instance=i, policy=p, q=q, success=q == 1.0)


# ------------------------------------------------------------------ metrics

def test_bootstrap_counts_missing_cells_as_zero():
    eps = [e for e in D.load_official() if not (e.task_id == 0 and e.instance == 302)]   # drop a q=1 cell
    q, lo, hi = bootstrap_q(eps, n_boot=200, seed=0)
    assert q == pytest.approx(challenge_q(eps))
    assert q == pytest.approx(0.15605353674103672 - 0.001)
    q1, _, _ = bootstrap_q([ep(0, 301, 1.0)], n_boot=50)
    assert q1 == pytest.approx(0.001)


@pytest.mark.parametrize("bad,match", [
    (ep(150, 301, 0.5), "task id"),
    (ep(0, 399, 0.5), "reporting instance"),
    (ep(0, 301, 1.5), "outside"),
])
def test_task_means_rejects_cells_outside_the_contract(bad, match):
    with pytest.raises(ValueError, match=match):
        task_means([bad])


def test_power_helpers_accept_any_level():
    assert rollouts_for_effect(0.05, 0.2, alpha=0.01, power=0.95) > rollouts_for_effect(0.05, 0.2)
    assert rollouts_for_selection(0.05, 0.2) == 23
    assert rollouts_for_selection(0.05, 0.2, paired_rho=0.5) < 23


def test_gaussian_rejects_degenerate_parameters():
    with pytest.raises(ValueError):
        Gaussian(0.1, 0.0)
    with pytest.raises(ValueError):
        Gaussian(float("nan"), 0.1)


# ------------------------------------------------------------------ routing and provenance

def test_route_hash_is_recorded_and_stable():
    doc = D.load_route()
    assert Route.from_json(doc).sha256 == doc["route_sha256"]
    assert doc["route_sha256"] == "adb6f400a503a3bbdca961260514f64a4c854b341f3021ae397f4fad8467d7e1"


def test_route_rejects_a_task_routed_twice():
    with pytest.raises(RouteError, match="twice"):
        Route.from_json({"tasks": [{"task_id": 7, "policy": "a"}, {"task_id": 7, "policy": "b"}]})


def test_coverage_needs_distinct_task_names():
    names = [f"t{i}" for i in range(99)] + ["t0"]
    with pytest.raises(AuditError, match="distinct"):
        check_coverage([(t, i) for t in names for i in range(301, 311)], names)


GOOD = {"task": "x", "instance_id": 302, "rollout_id": 0, "steps": 10, "success": False,
        "q_score": {"final": 0.5}, "time": {"normalized_time": 0.66}}


@pytest.mark.parametrize("patch,match", [
    ({"time": 3}, "objects"),
    ({"instance_id": 302.0}, "integer"),
    ({"instance_id": True}, "integer"),
    ({"steps": -1}, "integer"),
])
def test_parse_metrics_structural_errors_are_audit_errors(patch, match):
    with pytest.raises(AuditError, match=match):
        parse_metrics("x_302_0.json", json.dumps({**GOOD, **patch}))


def test_parse_metrics_malformed_json():
    with pytest.raises(AuditError, match="malformed"):
        parse_metrics("x_302_0.json", "{")


def test_verify_directory_end_to_end(tmp_path):
    names = [t["name"] for t in D.load_tasks()]
    for e in D.load_official():
        doc = {"task": e.task, "instance_id": e.instance, "rollout_id": 0, "steps": e.steps,
               "success": e.success, "q_score": {"final": e.q}, "time": {"normalized_time": e.normalized_time}}
        d = tmp_path / e.task
        d.mkdir(exist_ok=True)
        (d / f"{e.task}_{e.instance}_0.json").write_text(json.dumps(doc))
    rep = verify_directory(tmp_path, names)
    assert rep["files"] == 1000 and rep["Q"] == pytest.approx(0.15605353674103672)
    (tmp_path / names[0] / f"{names[0]}_301_0.json").unlink()
    with pytest.raises(AuditError, match="missing"):
        verify_directory(tmp_path, names)


def test_missing_dataset_gives_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="POLICYBANK_DATA"):
        D.load_tasks(tmp_path)


# ------------------------------------------------------------------ codec

def test_scalar_marker_cannot_smuggle_an_array():
    frame = msgpack.packb({"robot::proprio": {b"__npgeneric__": True, b"data": [0.0] * 61, b"dtype": "<f4"}},
                          use_bin_type=True)
    with pytest.raises(ValueError, match="scalar"):
        unpack(frame)


# ------------------------------------------------------------------ selection: family rule

def _family_ledger():
    rows = []
    for t in range(1, 7):
        rows += [ep(t, 311, 0.05, "R"), ep(t, 312, 0.05, "R")]
    # Three specialists of one family, each strong on different tasks.
    rows += [ep(1, 311, 0.9, "A"), ep(1, 312, 0.9, "A"), ep(3, 311, 0.8, "A"), ep(3, 312, 0.8, "A")]
    rows += [ep(2, 311, 0.7, "B"), ep(2, 312, 0.7, "B")]
    rows += [ep(4, 311, 0.6, "C"), ep(4, 312, 0.6, "C")]
    return rows


def test_one_checkpoint_per_family_is_enforced():
    rows = _family_ledger()
    ds = select_by_level(list(range(1, 7)), rows, "R", ["R"], ["A", "B", "C"], {"A": "F", "B": "F", "C": "F"})
    chosen = {d.choice for d in ds} - {"R"}
    assert len(chosen) <= 1


def test_reference_in_a_family_is_never_dropped():
    rows = _family_ledger()
    ds = select_by_level(list(range(1, 7)), rows, "R", ["R"], ["A", "B"], {"A": "F", "B": "F", "R": "F"})
    assert all(d.fallback == "R" for d in ds)
    assert len({d.choice for d in ds} - {"R"}) <= 1
