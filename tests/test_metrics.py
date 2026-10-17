import math

import pytest

from policybank import data as D
from policybank.data import Episode
from policybank.metrics import bootstrap_q, challenge_q, rollouts_for_effect, success_rate, task_means, within_task_sd


def ep(t, i, q, success=None):
    return Episode(task_id=t, task=f"t{t}", instance=i, policy="p", q=q,
                   success=(q == 1.0) if success is None else success)


def test_missing_instances_count_as_zero():
    eps = [ep(0, 301, 1.0), ep(0, 302, 0.5)]
    assert task_means(eps) == {0: pytest.approx(0.15)}
    assert challenge_q(eps) == pytest.approx(0.0015)


def test_duplicate_cells_are_rejected():
    with pytest.raises(ValueError, match="duplicate cell"):
        task_means([ep(0, 301, 0.0), ep(0, 301, 1.0)])


def test_released_dataset_reproduces_headline_numbers():
    eps = D.load_official()
    assert len(eps) == 1000
    assert challenge_q(eps) == pytest.approx(0.15605353674103672, abs=1e-12)
    assert sum(e.success for e in eps) == 37
    assert success_rate(eps) == pytest.approx(0.037)
    means = task_means(eps)
    assert sum(v > 0 for v in means.values()) == 71
    assert all(e.q == 1.0 for e in eps if e.success)


def test_every_failure_ran_to_the_step_cap():
    eps = D.load_official()
    assert all(e.timed_out for e in eps if not e.success)


def test_bootstrap_brackets_point_estimate_and_is_deterministic():
    eps = D.load_official()
    q, lo, hi = bootstrap_q(eps, n_boot=500, seed=1)
    assert lo < q < hi
    assert bootstrap_q(eps, n_boot=500, seed=1) == (q, lo, hi)
    assert 0.13 < lo and hi < 0.18


def test_within_task_sd_and_power():
    eps = [ep(0, 301, 0.0), ep(0, 302, 1.0), ep(1, 301, 0.5), ep(1, 302, 0.5)]
    assert within_task_sd(eps) == pytest.approx(math.sqrt(0.5 / 2))
    n = rollouts_for_effect(0.05, 0.2)
    assert 245 <= n <= 255
    assert rollouts_for_effect(0.05, 0.2, paired_rho=0.5) < n
