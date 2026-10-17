import math

import pytest

from policybank.analysis import reproduce_stage2
from policybank.data import Episode
from policybank.selection import (
    Gaussian,
    Rules,
    combine,
    decide,
    estimate_transfer_factor,
    flat_level_prior,
    noise_variance,
    one_per_family,
    paired_level,
    policy_level,
    transfer_prior,
    update,
)


def ep(task, inst, policy, q):
    return Episode(task_id=task, task=f"t{task}", instance=inst, policy=policy, q=q, success=q == 1.0)


def test_conjugate_update_matches_closed_form():
    prior = Gaussian(0.184, 0.111)
    post = update(prior, [0.0], noise_var=0.0822)
    p0, pd = 1 / 0.111 ** 2, 1 / 0.0822
    assert post.mean == pytest.approx(p0 * 0.184 / (p0 + pd))
    assert post.sd == pytest.approx(math.sqrt(1 / (p0 + pd)))
    # With no data the prior is returned unchanged.
    assert update(prior, [], 0.1) == prior


def test_frozen_route_report_example_is_reproduced():
    # Route report: comet@ymetz9999 prior 0.184+-0.111, one rollout at 0 -> posterior 0.160.
    post = update(Gaussian(0.184, 0.111), [0.0], noise_var=0.0822)
    assert round(post.mean, 3) == 0.160


def test_combine_is_precision_weighted():
    c = combine(Gaussian(0.0, 1.0), Gaussian(1.0, 1.0))
    assert c.mean == pytest.approx(0.5) and c.sd == pytest.approx(math.sqrt(0.5))


def test_transfer_prior_and_factor():
    p = transfer_prior(0.5, Gaussian(0.81, 0.10))
    assert p.mean == pytest.approx(0.405)
    assert p.sd == pytest.approx(math.sqrt(0.05 ** 2 + 0.088 ** 2))
    own = {0: [0.3, 0.1], 1: [0.4], 2: [0.6]}
    ref = {0: 0.4, 1: 0.8, 2: 1.0}
    f = estimate_transfer_factor(own, ref)
    assert f.mean == pytest.approx((0.2 + 0.4 + 0.6) / 2.2)
    f2 = estimate_transfer_factor(own, ref, leave_out=2)
    assert f2.mean == pytest.approx(0.6 / 1.2)


def test_levels_leave_the_decided_task_out():
    ref = {1: [0.1], 2: [0.0], 3: [0.2]}
    cand = {1: [0.3], 2: [0.2], 3: [0.9]}
    lv = policy_level(ref, leave_out=3)
    assert lv.mean == pytest.approx(0.05)
    pl = paired_level(cand, ref, leave_out=3)
    assert pl.mean == pytest.approx(0.05 + 0.2)
    prior = flat_level_prior(pl)
    assert prior.sd > 0.1  # widened by the between-task spread


def test_noise_variance_shrinks_toward_default():
    assert noise_variance({}) == pytest.approx(0.08)
    v = noise_variance({0: [0.0, 1.0], 1: [0.0, 1.0]}, default=0.08, prior_dof=4)
    assert 0.08 < v < 0.5


DEV = [
    # task 7: incumbent "a" vs challenger "b" on shared instances 311/312
    ep(7, 311, "a", 0.2), ep(7, 312, "a", 0.1),
    ep(7, 311, "b", 0.6), ep(7, 312, "b", 0.5),
    # challenger "c" has one rollout only
    ep(7, 313, "c", 1.0),
]
PRIORS = {"a": Gaussian(0.2, 0.1), "b": Gaussian(0.2, 0.1), "c": Gaussian(0.3, 0.1)}
NOISE = {"a": 0.05, "b": 0.05, "c": 0.05}


def test_guarded_switch_requires_rollouts_guard_and_margin():
    d = decide(7, "a", PRIORS, DEV, NOISE, Rules(), guarded=True)
    assert d.choice == "b" and d.switched
    c = next(x for x in d.candidates if x.policy == "c")
    assert any("own dev rollout" in f for f in c.flags)


def test_dev_guard_blocks_a_challenger_that_loses_on_shared_instances():
    dev = [ep(7, 311, "a", 0.5), ep(7, 312, "a", 0.5), ep(7, 311, "b", 0.4), ep(7, 312, "b", 0.4),
           ep(7, 313, "b", 1.0), ep(7, 314, "b", 1.0)]
    d = decide(7, "a", {"a": Gaussian(0.3, 0.1), "b": Gaussian(0.3, 0.1)}, dev, {"a": 0.05, "b": 0.05})
    assert d.choice == "a"
    assert "dev guard" in d.reason


def test_margin_keeps_near_ties_with_the_fallback():
    dev = [ep(7, 311, "a", 0.3), ep(7, 312, "a", 0.3), ep(7, 311, "b", 0.31), ep(7, 312, "b", 0.31)]
    d = decide(7, "a", {"a": Gaussian(0.3, 0.1), "b": Gaussian(0.3, 0.1)}, dev, {"a": 0.05, "b": 0.05},
               Rules(switch_margin=0.05))
    assert d.choice == "a"


def test_veto_when_challenger_scores_zero_where_fallback_scores():
    dev = [ep(7, 311, "a", 0.5), ep(7, 311, "b", 0.0)]
    d = decide(7, "a", {"a": Gaussian(0.05, 0.1), "b": Gaussian(0.4, 0.1)}, dev, {"a": 0.05, "b": 0.05},
               guarded=False)
    b = next(x for x in d.candidates if x.policy == "b")
    assert any("veto" in f for f in b.flags) and d.choice == "a"


def test_one_per_family_keeps_the_member_with_larger_gain():
    d1 = decide(1, "a", {"a": Gaussian(0.1, 0.1), "x1": Gaussian(0.3, 0.1), "x2": Gaussian(0.2, 0.1)},
                [], {}, guarded=False)
    d2 = decide(2, "a", {"a": Gaussian(0.1, 0.1), "x1": Gaussian(0.15, 0.1), "x2": Gaussian(0.2, 0.1)},
                [], {}, guarded=False)
    assert (d1.choice, d2.choice) == ("x1", "x2")
    keep = one_per_family([d1, d2], {"x1": "x", "x2": "x"})
    assert keep["x1"] == keep["x2"] == "x1"   # x1 gains 0.2 + 0.05 > x2's 0.1 + 0.1


def test_reimplementation_reproduces_stage2_route():
    r = reproduce_stage2()
    assert r["tasks"] == 50
    assert r["agree"] >= 48
    for d in r["disagreements"]:
        assert d["ours"] == "s150997"   # the remaining differences fall back to the reference policy
