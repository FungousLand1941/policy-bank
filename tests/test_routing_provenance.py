import json
from datetime import datetime, timedelta

import pytest

from policybank import data as D
from policybank.provenance import (Attempt, AuditError, check_coverage, parse_metrics,
                                   resolve_duplicates)
from policybank.routing import Route, RouteError


def test_frozen_route_is_complete_and_stable():
    doc = D.load_route()
    route = Route.from_json(doc)
    route.validate(D.load_policies())
    assert route.sha256 == Route.from_json({str(k): v for k, v in route.assignments.items()}).sha256
    images = route.images()
    assert sum(map(len, images.values())) == 100
    assert len(images) == 10
    assert images["comet@ymetz9999"][0] == 50


def test_every_reported_episode_came_from_its_routed_policy():
    route = Route.from_json(D.load_route())
    for e in D.load_official():
        assert route.policy(e.task_id) == e.policy


def test_route_validation_errors():
    r = Route({0: "a"})
    with pytest.raises(RouteError, match="unrouted"):
        r.validate({"a"}, n_tasks=2)
    with pytest.raises(RouteError, match="outside the bank"):
        Route({0: "zzz"}).validate({"a"}, n_tasks=1)
    assert Route({0: "a", 1: "b"}).diff(Route({0: "a", 1: "c"})) == {1: ("b", "c")}


GOOD = {"task": "turning_on_radio", "instance_id": 302, "rollout_id": 0, "steps": 2634, "success": True,
        "q_score": {"final": 1.0}, "time": {"normalized_time": 0.8161}}


def test_parse_metrics_accepts_valid_files():
    doc = parse_metrics("turning_on_radio_302_0.json", json.dumps(GOOD))
    assert doc["q_score"]["final"] == 1.0


@pytest.mark.parametrize("name,text,match", [
    ("turning_on_radio_303_0.json", json.dumps(GOOD), "does not match"),
    ("radio.json", json.dumps(GOOD), "file name"),
    ("turning_on_radio_302_0.json", json.dumps({**GOOD, "q_score": {"final": 1.5}}), "finite number"),
    ("turning_on_radio_302_0.json", json.dumps({**GOOD, "q_score": {"final": 0.5}}), "partial q"),
    ("turning_on_radio_302_0.json", '{"task": "a", "task": "b"}', "duplicate JSON keys"),
    ("turning_on_radio_302_0.json", json.dumps(GOOD).replace("2634", "NaN"), "nonfinite"),
])
def test_parse_metrics_rejects_bad_files(name, text, match):
    with pytest.raises(AuditError, match=match):
        parse_metrics(name, text)


def test_coverage_check():
    names = [f"t{i}" for i in range(100)]
    cells = [(t, i) for t in names for i in range(301, 311)]
    check_coverage(cells, names)
    with pytest.raises(AuditError, match="missing"):
        check_coverage(cells[:-1], names)
    with pytest.raises(AuditError, match="duplicate"):
        check_coverage(cells + cells[:1], names)


T0 = datetime(2026, 10, 11, 14, 0)


@pytest.mark.parametrize("first_q,later_q", [(0.5, 0.0), (0.0, 0.5), (0.0, 0.0)])
def test_duplicate_resolution_ignores_scores(first_q, later_q):
    cell = ("spraying_for_bugs", 307)
    first = Attempt(cell, T0, T0 + timedelta(minutes=25), first_q, "first")
    later = Attempt(cell, T0 + timedelta(minutes=27), T0 + timedelta(minutes=60), later_q, "later")
    kept, decisions = resolve_duplicates([later, first])
    assert [a.ref for a in kept] == ["first"]
    assert decisions[0]["excluded"] == ["later"]


def test_overlapping_duplicates_are_ambiguous():
    cell = ("x", 301)
    a = Attempt(cell, T0, T0 + timedelta(minutes=30), 0.0, "a")
    b = Attempt(cell, T0 + timedelta(minutes=10), T0 + timedelta(minutes=40), 1.0, "b")
    with pytest.raises(AuditError, match="overlap"):
        resolve_duplicates([a, b])


def test_released_duplicate_ledger():
    dups = D.load_json("duplicates.json")
    assert {(d["task"], d["instance"]) for d in dups} == {("spraying_for_bugs", 307), ("cook_brussels_sprouts", 303)}
