"""Seeded randomized property tests (no hypothesis dependency).

Every test draws many random cases from ``random.Random(seed)`` so failures are reproducible:
the assertion message names the case index, and re-running the test replays the same cases.
"""
import itertools
import json
import math
import random
import threading
from collections import Counter

import msgpack
import numpy as np
import pytest

from policybank.data import Episode
from policybank.metrics import bootstrap_q, challenge_q, task_means
from policybank.routing import Route, RouteError
from policybank.selection import Gaussian, Rules, combine, decide, per_task_scores, select_by_level, update
from policybank.serving import codec
from policybank.serving.codec import pack, unpack
from policybank.serving.executor import ChunkExecutor
from policybank.simulate import RULES, Setup, draw_ledger, fit_beta_concentration, run_study

REPORT = list(range(301, 311))
DEV = list(range(311, 321))


def ep(t, i, q, p="p"):
    return Episode(task_id=t, task=f"t{t}", instance=i, policy=p, q=q, success=q >= 1.0)


def rand_q(rng):
    """Partial credit with the atoms the real data has (many zeros, some full successes)."""
    r = rng.random()
    return 0.0 if r < 0.35 else 1.0 if r < 0.45 else rng.random()


def rand_official(rng, n_tasks=100, min_tasks=1):
    """A random reporting ledger: a subset of tasks, a subset of instances each, no duplicates."""
    eps = []
    for t in rng.sample(range(n_tasks), rng.randrange(min_tasks, n_tasks + 1)):
        for i in rng.sample(REPORT, rng.randrange(1, len(REPORT) + 1)):
            eps.append(ep(t, i, rand_q(rng)))
    rng.shuffle(eps)
    return eps


def within(seconds, fn):
    """Run ``fn`` in a daemon thread and fail (instead of hanging the suite) if it overruns."""
    box = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 - re-raised in the test thread
            box["error"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(seconds)
    assert not th.is_alive(), f"did not finish within {seconds} s (non-terminating loop?)"
    if "error" in box:
        raise box["error"]
    return box.get("value")


# =================================================================== metrics

def test_challenge_q_is_mean_of_zero_padded_task_means():
    rng = random.Random(101)
    for case in range(150):
        n_tasks = rng.choice([1, 3, 17, 100])
        eps = rand_official(rng, n_tasks)
        per_task = {}
        for e in eps:
            per_task.setdefault(e.task_id, []).append(e.q)
        expected_means = {t: math.fsum(qs) / len(REPORT) for t, qs in per_task.items()}
        expected_q = math.fsum(expected_means.get(t, 0.0) for t in range(n_tasks)) / n_tasks
        means = task_means(eps, n_tasks=n_tasks)
        assert set(means) == set(per_task), case
        for t, m in means.items():
            assert m == pytest.approx(expected_means[t], abs=1e-12), (case, t)
        q = challenge_q(eps, n_tasks=n_tasks)
        assert q == pytest.approx(expected_q, abs=1e-12), case
        assert 0.0 <= q <= 1.0


def test_adding_a_missing_cell_raises_q_by_exactly_its_share():
    rng = random.Random(102)
    for case in range(100):
        eps = rand_official(rng)
        cells = {(e.task_id, e.instance) for e in eps}
        free = [(t, i) for t in range(100) for i in REPORT if (t, i) not in cells]
        if not free:
            continue
        t, i = rng.choice(free)
        q_new = rng.random()
        assert challenge_q(eps + [ep(t, i, q_new)]) == pytest.approx(
            challenge_q(eps) + q_new / (100 * len(REPORT)), abs=1e-12), case


def test_bootstrap_point_equals_challenge_q_and_ci_brackets_it():
    rng = random.Random(103)
    for case in range(30):
        n_tasks = rng.choice([5, 12, 30]) if case % 10 else 100
        eps = rand_official(rng, n_tasks, min_tasks=min(5, n_tasks))
        n_boot, seed = 200, rng.randrange(1000)
        q, lo, hi = bootstrap_q(eps, n_boot=n_boot, seed=seed, n_tasks=n_tasks)
        assert q == challenge_q(eps, n_tasks=n_tasks), case
        assert lo <= q <= hi, (case, lo, q, hi)
        padded = {}
        for e in eps:
            padded.setdefault(e.task_id, []).append(e.q)
        if any(len(set(qs + [0.0] * (len(REPORT) - len(qs)))) > 1 for qs in padded.values()):
            assert lo < hi, (case, lo, hi)


def test_bootstrap_of_constant_full_coverage_is_degenerate():
    rng = random.Random(104)
    for case in range(20):
        n_tasks = rng.randrange(1, 12)
        consts = [rng.choice([0.0, 0.25, 0.5, 1.0, rng.random()]) for _ in range(n_tasks)]
        eps = [ep(t, i, consts[t]) for t in range(n_tasks) for i in REPORT]
        q, lo, hi = bootstrap_q(eps, n_boot=100, seed=case, n_tasks=n_tasks)
        assert lo == pytest.approx(q, abs=1e-12) and hi == pytest.approx(q, abs=1e-12), case


def test_challenge_q_and_bootstrap_point_ignore_episode_order():
    # Q is a sum over cells, so it is order invariant up to floating-point summation order.
    rng = random.Random(105)
    for case in range(100):
        eps = rand_official(rng)
        perm = eps[:]
        rng.shuffle(perm)
        assert challenge_q(perm) == pytest.approx(challenge_q(eps), abs=1e-12), case
        a, b = task_means(eps), task_means(perm)
        assert a.keys() == b.keys() and all(a[t] == pytest.approx(b[t], abs=1e-12) for t in a), case
        if case < 5:
            assert bootstrap_q(perm, n_boot=50, seed=1)[0] == pytest.approx(
                bootstrap_q(eps, n_boot=50, seed=1)[0], abs=1e-12), case


def test_bootstrap_ci_ignores_episode_order():
    rng = random.Random(106)
    for case in range(10):
        eps = rand_official(rng, min_tasks=5)
        perm = eps[:]
        rng.shuffle(perm)
        _, lo1, hi1 = bootstrap_q(eps, n_boot=200, seed=7)
        _, lo2, hi2 = bootstrap_q(perm, n_boot=200, seed=7)
        assert (lo1, hi1) == pytest.approx((lo2, hi2), abs=1e-12), case


def test_relabelling_instances_changes_nothing():
    # Shuffling which reporting instance id each score sits on (independently per task) must not
    # change any metric: instances are exchangeable within a task.
    rng = random.Random(107)
    for case in range(60):
        eps = rand_official(rng)
        perms = {t: dict(zip(REPORT, rng.sample(REPORT, len(REPORT)), strict=True)) for t in range(100)}
        relabelled = [Episode(task_id=e.task_id, task=e.task, instance=perms[e.task_id][e.instance],
                              policy=e.policy, q=e.q, success=e.success) for e in eps]
        assert challenge_q(relabelled) == challenge_q(eps), case
        assert task_means(relabelled) == task_means(eps), case
        if case < 5:
            assert bootstrap_q(relabelled, n_boot=50, seed=case) == bootstrap_q(eps, n_boot=50, seed=case), case


# =================================================================== selection.update / combine

def rand_gaussian(rng, lo=0.01, hi=1.0):
    return Gaussian(rng.uniform(-0.5, 1.5), rng.uniform(lo, hi))


def test_update_posterior_lies_between_prior_and_data_and_shrinks():
    rng = random.Random(201)
    for case in range(500):
        prior = rand_gaussian(rng)
        scores = [rng.random() for _ in range(rng.randrange(1, 12))]
        noise = rng.uniform(0.001, 1.0)
        post = update(prior, scores, noise)
        dm = sum(scores) / len(scores)
        lo, hi = min(prior.mean, dm), max(prior.mean, dm)
        assert lo - 1e-12 <= post.mean <= hi + 1e-12, case
        assert post.sd < prior.sd, case
        assert update(prior, [], noise) == prior


def test_update_more_data_with_the_same_mean_moves_closer_to_it():
    rng = random.Random(202)
    for case in range(300):
        prior = rand_gaussian(rng)
        scores = [rng.random() for _ in range(rng.randrange(1, 6))]
        noise = rng.uniform(0.001, 1.0)
        dm = sum(scores) / len(scores)
        dist = [abs(update(prior, scores * k, noise).mean - dm) for k in range(1, 6)]
        sds = [update(prior, scores * k, noise).sd for k in range(1, 6)]
        for a, b in itertools.pairwise(dist):
            assert b <= a + 1e-12, (case, dist)
        for a, b in itertools.pairwise(sds):
            assert b < a, (case, sds)
        if abs(prior.mean - dm) > 1e-3:
            assert dist[-1] < dist[0], case


def test_combine_is_order_invariant_and_tightens():
    rng = random.Random(203)
    for case in range(300):
        parts = [rand_gaussian(rng, 0.02, 0.5) for _ in range(rng.randrange(1, 7))]
        ref = combine(*parts)
        for _ in range(3):
            perm = parts[:]
            rng.shuffle(perm)
            c = combine(*perm)
            assert c.mean == pytest.approx(ref.mean, rel=1e-12, abs=1e-12), case
            assert c.sd == pytest.approx(ref.sd, rel=1e-12), case
        assert ref.sd <= min(p.sd for p in parts) + 1e-15
        assert min(p.mean for p in parts) - 1e-12 <= ref.mean <= max(p.mean for p in parts) + 1e-12


# =================================================================== decide()

def rand_decide_case(rng, task=7):
    challengers = [f"c{i}" for i in range(rng.randrange(1, 6))]
    policies = ["fb"] + challengers
    priors = {p: Gaussian(rng.uniform(0, 1), rng.uniform(0.02, 0.3)) for p in policies}
    dev = []
    for p in policies:
        for i in rng.sample(DEV, rng.randrange(0, 5)):
            for _ in range(rng.choice([1, 1, 2])):
                dev.append(ep(task, i, rand_q(rng), p))
    for _ in range(rng.randrange(0, 6)):                       # rows on other tasks must be ignored
        dev.append(ep(rng.choice([1, 2, 3]), rng.choice(DEV), rand_q(rng), rng.choice(policies)))
    rng.shuffle(dev)
    noise = {p: rng.uniform(0.01, 0.2) for p in policies if rng.random() < 0.8}
    # min_shared is drawn from 1..3 here; min_shared=0 is covered by its own test below.
    rules = Rules(min_own_rollouts=rng.randrange(0, 4), dev_guard=rng.random() < 0.6,
                  min_shared=rng.randrange(1, 4), switch_margin=rng.choice([0.0, 0.01, rng.uniform(0, 0.3)]),
                  veto_ref_above=rng.choice([None, 0.1, 0.5]))
    return priors, dev, noise, rules, rng.random() < 0.5


def test_decide_chooses_fallback_or_an_eligible_challenger_with_enough_gain():
    rng = random.Random(301)
    switched = kept = 0
    for case in range(600):
        priors, dev, noise, rules, guarded = rand_decide_case(rng)
        d = decide(7, "fb", priors, dev, noise, rules, guarded=guarded)
        by = {c.policy: c for c in d.candidates}
        assert set(by) == set(priors) and d.fallback == "fb", case
        assert by["fb"].eligible, case                               # the fallback is never flagged
        gains = {p: c.posterior.mean - by["fb"].posterior.mean for p, c in by.items() if p != "fb"}
        if d.switched:
            switched += 1
            assert by[d.choice].eligible, case
            assert gains[d.choice] >= rules.switch_margin, case
            best = max(c.posterior.mean for p, c in by.items() if p != "fb" and c.eligible)
            assert by[d.choice].posterior.mean == best, case
        else:
            kept += 1
            assert d.choice == "fb"
        if all(g < rules.switch_margin for g in gains.values()):
            assert d.choice == "fb", case
        if guarded:
            for p, c in by.items():
                if p != "fb" and c.n < rules.min_own_rollouts:
                    assert not c.eligible, case
    assert switched > 50 and kept > 50                               # both branches exercised


def test_decide_is_invariant_to_the_order_of_the_priors():
    rng = random.Random(302)
    for case in range(300):
        priors, dev, noise, rules, guarded = rand_decide_case(rng)
        ref = decide(7, "fb", priors, dev, noise, rules, guarded=guarded)
        items = list(priors.items())
        for _ in range(3):
            rng.shuffle(items)
            d = decide(7, "fb", dict(items), dev, noise, rules, guarded=guarded)
            assert (d.choice, d.reason) == (ref.choice, ref.reason), case
            assert {c.policy: (c.posterior, c.flags) for c in d.candidates} == \
                   {c.policy: (c.posterior, c.flags) for c in ref.candidates}, case


def test_decide_with_min_shared_zero_does_not_crash():
    rng = random.Random(304)
    for case in range(50):
        priors, dev, noise, rules, _ = rand_decide_case(rng)
        rules = Rules(min_own_rollouts=0, dev_guard=True, min_shared=0, switch_margin=rules.switch_margin,
                      veto_ref_above=rules.veto_ref_above)
        d = decide(7, "fb", priors, dev, noise, rules, guarded=True)
        assert d.choice in priors, case


def test_decide_breaks_exact_ties_independently_of_prior_order():
    rng = random.Random(303)
    for case in range(20):
        tied = Gaussian(rng.uniform(0.3, 0.9), rng.uniform(0.02, 0.2))
        priors = {"fb": Gaussian(0.0, 0.1), "x": tied, "y": tied}
        a = decide(1, "fb", priors, [], {}, guarded=False)
        b = decide(1, "fb", dict(reversed(list(priors.items()))), [], {}, guarded=False)
        assert a.choice == b.choice, case


# =================================================================== select_by_level()

def rand_level_ledger(rng):
    tasks = sorted(rng.sample(range(50, 100), rng.randrange(2, 10)))
    gens = ["R"] + [f"g{i}" for i in range(rng.randrange(0, 4))]
    specs = [f"s{i}" for i in range(rng.randrange(0, 6))]
    strength = {p: (0.1 if p == "R" else rng.random()) for p in gens + specs}
    rows = []
    for p in gens + specs:
        if p == "R" or (p in gens and rng.random() < 0.7):
            cover = tasks
        else:
            cover = rng.sample(tasks, rng.randrange(0, len(tasks) + 1))
        for t in cover:
            for i in rng.sample(DEV, rng.randrange(1 if p == "R" else 0, 4)):
                for _ in range(rng.choice([1, 1, 2])):
                    q = 0.0 if rng.random() < 0.3 else min(1.0, max(0.0, rng.gauss(strength[p], 0.2)))
                    rows.append(ep(t, i, q, p))
    for _ in range(rng.randrange(0, 10)):                         # rows on tasks not being routed
        rows.append(ep(rng.randrange(0, 50), rng.choice(DEV), rand_q(rng), rng.choice(gens + specs)))
    fams = [f"F{i}" for i in range(rng.randrange(1, 4))]
    family = {p: rng.choice(fams) for p in gens + specs if rng.random() < 0.85}
    rng.shuffle(rows)
    return tasks, rows, gens, specs, family


def test_select_by_level_route_invariants():
    rng = random.Random(401)

    def run():
        crowded_cases = 0
        for case in range(250):
            tasks, rows, gens, specs, family = rand_level_ledger(rng)
            min_roll = rng.choice([1, 2, 3])
            unconsolidated = select_by_level(tasks, rows, "R", gens, specs, {}, min_policy_rollouts=min_roll)
            before = Counter(family[d] for d in {x.choice for x in unconsolidated} if d in family and d != "R")
            crowded_cases += any(n > 1 for n in before.values())

            ds = select_by_level(tasks, rows, "R", gens, specs, family, min_policy_rollouts=min_roll)
            scores = per_task_scores(rows)
            assert [d.task_id for d in ds] == tasks, case
            route = {d.choice for d in ds}
            # (a) at most one non-reference member of each family in the whole route
            fam_count = Counter(family[p] for p in route if p in family and p != "R")
            assert all(n <= 1 for n in fam_count.values()), (case, fam_count)
            for d in ds:
                # (b) the reference is the fallback everywhere, so it can never have been removed
                assert d.fallback == "R" and any(c.policy == "R" for c in d.candidates), case
                by = {c.policy: c for c in d.candidates}
                assert d.choice in by and (d.choice == "R" or by[d.choice].eligible), case
                # (c) a chosen specialist has its own rollouts on that task (and enough overall)
                if d.choice in specs:
                    assert scores[d.choice].get(d.task_id), (case, d.task_id, d.choice)
                    assert sum(map(len, scores[d.choice].values())) >= min_roll, case
                # specialists never even compete on tasks where they have no rollouts
                for p in by:
                    if p in specs:
                        assert scores[p].get(d.task_id), (case, p)
        return crowded_cases

    crowded = within(60, run)                                     # (d) the consolidation loop terminates
    assert crowded >= 20, f"generator only exercised family consolidation {crowded} times"


def test_select_by_level_with_reference_inside_a_family_keeps_reference():
    rng = random.Random(402)

    def run():
        for case in range(80):
            tasks, rows, gens, specs, family = rand_level_ledger(rng)
            family["R"] = rng.choice(sorted(set(family.values()) or {"F0"}))
            ds = select_by_level(tasks, rows, "R", gens, specs, family)
            assert [d.task_id for d in ds] == tasks, case
            for d in ds:
                assert d.fallback == "R" and any(c.policy == "R" for c in d.candidates), case
            # the reference may share a family with one other kept member; nothing else doubles up
            others = {d.choice for d in ds} - {"R"}
            fam_count = Counter(family[p] for p in others if p in family)
            assert all(n <= 1 for n in fam_count.values()), (case, fam_count)

    within(60, run)


# =================================================================== routing.Route

def rand_assignments(rng, n_tasks):
    bank = [f"p{i}" for i in range(rng.randrange(1, 8))]
    return {t: rng.choice(bank) for t in range(n_tasks)}, bank


def test_route_hash_is_invariant_to_insertion_order_and_encoding():
    rng = random.Random(501)
    for case in range(150):
        assign, _ = rand_assignments(rng, rng.randrange(1, 120))
        base = Route(dict(assign))
        items = list(assign.items())
        rng.shuffle(items)
        assert Route(dict(items)).sha256 == base.sha256, case
        as_list = [{"task_id": t, "policy": p} for t, p in items]
        assert Route.from_json({"tasks": as_list}).sha256 == base.sha256, case
        assert Route.from_json({str(t): p for t, p in items}).sha256 == base.sha256, case
        doc = json.loads(base.canonical())
        assert {int(k): v for k, v in doc.items()} == assign
        # any single reassignment changes the hash
        t = rng.choice(list(assign))
        assert Route({**assign, t: assign[t] + "-other"}).sha256 != base.sha256, case


def test_route_validate_rejects_missing_extra_and_unknown():
    rng = random.Random(502)
    for case in range(200):
        n = rng.randrange(1, 120)
        assign, bank = rand_assignments(rng, n)
        Route(assign).validate(bank, n_tasks=n)
        missing = sorted(rng.sample(range(n), rng.randrange(1, n + 1)))
        partial = {t: p for t, p in assign.items() if t not in missing}
        with pytest.raises(RouteError, match="unrouted") as e:
            Route(partial).validate(bank, n_tasks=n)
        assert str(missing) in str(e.value), case
        extra = sorted(rng.sample([*range(n, n + 50), -1, -7], rng.randrange(1, 5)))
        with pytest.raises(RouteError, match="unknown task ids") as e:
            Route({**assign, **{t: bank[0] for t in extra}}).validate(bank, n_tasks=n)
        assert str(extra) in str(e.value), case
        t = rng.randrange(n)
        with pytest.raises(RouteError, match="outside the bank"):
            Route({**assign, t: "not-in-bank"}).validate(bank, n_tasks=n)


def test_route_diff_is_antisymmetric_and_exact():
    rng = random.Random(503)
    for case in range(200):
        bank = [f"p{i}" for i in range(rng.randrange(1, 5))]
        a = Route({t: rng.choice(bank) for t in rng.sample(range(40), rng.randrange(0, 40))})
        b = Route({t: rng.choice(bank) for t in rng.sample(range(40), rng.randrange(0, 40))})
        ab, ba = a.diff(b), b.diff(a)
        assert ab.keys() == ba.keys(), case
        assert all(ab[t] == (ba[t][1], ba[t][0]) for t in ab), case
        assert a.diff(a) == {} and list(ab) == sorted(ab)
        keys = set(a.assignments) | set(b.assignments)
        assert set(ab) == {t for t in keys if a.assignments.get(t) != b.assignments.get(t)}, case
        for t, (x, y) in ab.items():
            assert a.assignments.get(t) == x and b.assignments.get(t) == y
        imgs = a.images()
        assert sorted(t for ts in imgs.values() for t in ts) == sorted(a.assignments), case
        assert [len(ts) for ts in imgs.values()] == sorted((len(ts) for ts in imgs.values()), reverse=True)


# =================================================================== serving codec

DTYPES = ["|b1", "|i1", "<i2", ">i2", "<i4", ">i4", "<i8", ">i8", "|u1", "<u2", ">u2", "<u4", ">u4",
          "<u8", ">u8", "<f2", ">f2", "<f4", ">f4", "<f8", ">f8"]


def rand_array(rng, min_ndim=1):
    dt = np.dtype(rng.choice(DTYPES))
    ndim = rng.randrange(min_ndim, 9)
    shape = tuple(rng.randrange(0, 4 if ndim <= 3 else 2 + (rng.random() < 0.3)) for _ in range(ndim))
    n = math.prod(shape)
    if dt.kind == "b":
        raw = bytes(rng.randrange(2) for _ in range(n))
    else:
        raw = rng.randbytes(n * dt.itemsize)
    a = np.frombuffer(raw, dtype=dt).reshape(shape).copy()
    if a.ndim >= 2 and rng.random() < 0.3:
        a = a.T                                                     # non-contiguous input
    elif a.ndim >= 1 and a.shape[0] > 1 and rng.random() < 0.3:
        a = a[::2]
    return a


def same_array(x, y):
    return (isinstance(y, np.ndarray) and x.dtype == y.dtype and x.shape == y.shape
            and np.ascontiguousarray(x).tobytes() == y.tobytes())


def test_codec_roundtrips_random_arrays_exactly():
    rng = random.Random(601)
    for case in range(1500):
        arrays = [rand_array(rng) for _ in range(rng.randrange(1, 4))]
        doc = {"a": arrays[0], "nested": {"list": arrays[1:], "s": "x", "i": rng.randrange(-5, 5)}}
        out = unpack(pack(doc))
        assert same_array(arrays[0], out["a"]), (case, arrays[0].dtype, arrays[0].shape)
        assert len(out["nested"]["list"]) == len(arrays) - 1
        for x, y in zip(arrays[1:], out["nested"]["list"], strict=True):
            assert same_array(x, y), (case, x.dtype, x.shape)
        assert out["nested"]["s"] == "x"


def test_codec_roundtrips_zero_dimensional_arrays():
    rng = random.Random(607)
    for case in range(50):
        a = rand_array(rng, min_ndim=0)
        a = a.reshape(-1)[:1].reshape(()) if a.size else np.zeros((), a.dtype)
        assert a.ndim == 0
        assert same_array(a, unpack(pack({"a": a}))["a"]), (case, a.dtype)


def test_codec_roundtrips_random_scalars():
    rng = random.Random(602)
    for case in range(1500):
        a = rand_array(rng).reshape(-1)
        if a.size == 0:
            continue
        s = a[rng.randrange(a.size)]                                # a numpy scalar (native byte order)
        out = unpack(pack({"s": s}))["s"]
        # np.float64 subclasses float, so msgpack sends it natively and it returns as a Python float
        # (the OpenPI codec behaves the same); every other scalar keeps its numpy type.
        assert np.asarray(out).dtype == s.dtype, (case, s.dtype, type(out))
        if s.dtype != np.float64:
            assert type(out) is type(s), (case, type(s), type(out))
        if s.dtype.kind == "f" and np.isnan(s):
            assert np.isnan(out)
        else:
            assert out == s and np.asarray(out).tobytes() == s.tobytes(), (case, s, out)


def test_codec_random_bytes_decode_or_fail_with_value_or_type_error():
    rng = random.Random(603)
    outcomes = Counter()
    for case in range(6000):
        head = rng.choice([b"", bytes([0x80 | rng.randrange(16)]), bytes([0x90 | rng.randrange(16)]),
                           b"\xde", b"\xc4", b"\xd9"])
        frame = head + rng.randbytes(rng.randrange(0, 64))
        try:
            unpack(frame)
            outcomes["ok"] += 1
        except Exception as e:  # noqa: BLE001 - the type is the assertion
            assert isinstance(e, (ValueError, TypeError)), (case, frame, type(e).__name__, e)
            outcomes[type(e).__name__] += 1
    assert outcomes["ok"] > 0 and sum(outcomes.values()) - outcomes["ok"] > 1000


def _mutate(rng, frame: bytes) -> bytes:
    b = bytearray(frame)
    for _ in range(rng.randrange(1, 4)):
        op = rng.randrange(3)
        if op == 0 and b:
            b[rng.randrange(len(b))] = rng.randrange(256)
        elif op == 1 and b:
            del b[rng.randrange(len(b)):]
        else:
            b.insert(rng.randrange(len(b) + 1), rng.randrange(256))
    return bytes(b)


def test_codec_corrupted_frames_decode_or_fail_with_value_or_type_error():
    rng = random.Random(604)
    for case in range(3000):
        doc = {"a": rand_array(rng), "s": np.int64(rng.randrange(-5, 5)), "f": np.float32(rng.random()), "t": "x"}
        frame = _mutate(rng, pack(doc))
        try:
            unpack(frame)
        except Exception as e:  # noqa: BLE001 - the type is the assertion
            assert isinstance(e, (ValueError, TypeError)), (case, frame, type(e).__name__, e)


@pytest.mark.parametrize("data,dtype", [(300, "|i1"), (-1, "|u1"), (2 ** 63, "<i8"), (float("inf"), "<i8")])
def test_codec_out_of_range_scalar_payload_is_a_value_error(data, dtype):
    frame = msgpack.packb({"x": {b"__npgeneric__": True, b"data": data, b"dtype": dtype}}, use_bin_type=True)
    with pytest.raises((ValueError, TypeError)):
        unpack(frame)


def test_codec_rejects_oversized_and_inconsistent_declared_shapes():
    rng = random.Random(605)
    for _ in range(400):
        dt = np.dtype(rng.choice(DTYPES))
        ndim = rng.randrange(1, 9)
        while True:
            shape = [rng.choice([1, 2, 3, 1000, 2 ** 16, 2 ** 31, 2 ** 40]) for _ in range(ndim)]
            if math.prod(shape) * dt.itemsize > codec.MAX_BYTES:
                break
            ndim = min(8, ndim + 1)
        frame = msgpack.packb({"x": {b"__ndarray__": True, b"data": b"\x00" * rng.randrange(0, 64),
                                     b"dtype": dt.str, b"shape": shape}}, use_bin_type=True)
        with pytest.raises(ValueError, match="too large"):
            unpack(frame)
        # a byte length that disagrees with a small declared shape is rejected too
        small = [rng.randrange(1, 4) for _ in range(rng.randrange(1, 4))]
        size = math.prod(small) * dt.itemsize
        wrong = rng.choice([size - 1, size + 1, size + dt.itemsize, 0])
        frame = msgpack.packb({"x": {b"__ndarray__": True, b"data": b"\x00" * wrong, b"dtype": dt.str,
                                     b"shape": small}}, use_bin_type=True)
        with pytest.raises(ValueError, match="length"):
            unpack(frame)
    for bad_shape in ([1] * 9, [-1], [True], [1.0], "12", {"a": 1}):
        frame = msgpack.packb({"x": {b"__ndarray__": True, b"data": b"", b"dtype": "<f4",
                                     b"shape": bad_shape}}, use_bin_type=True)
        with pytest.raises(ValueError, match="shape"):
            unpack(frame)


def test_codec_rejects_frames_and_arrays_over_the_byte_cap(monkeypatch):
    monkeypatch.setattr(codec, "MAX_BYTES", 4096)
    rng = random.Random(606)
    for _ in range(50):
        n = rng.randrange(4097, 9000)
        with pytest.raises(ValueError, match="oversized"):
            unpack(b"\x00" * n)
        k = rng.randrange(1025, 2000)                               # k float32 values = 4k > 4096 bytes
        frame = msgpack.packb({"x": {b"__ndarray__": True, b"data": b"", b"dtype": "<f4", b"shape": [k]}},
                              use_bin_type=True)
        with pytest.raises(ValueError, match="too large"):
            unpack(frame)


# =================================================================== ChunkExecutor

class ObsPolicy:
    """Plans depend on each environment's observation and on the plan count since reset."""

    def __init__(self, horizon, action_dim, extra=0):
        self.name, self.horizon, self.action_dim, self.extra = "obs", horizon, action_dim, extra
        self.calls = 0
        self.seen = []

    def plan(self, obs, n):
        x = np.asarray(obs["x"], dtype=np.float64).reshape(n)
        self.seen.append(x.copy())
        t = np.arange(self.horizon + self.extra, dtype=np.float64)
        a = np.arange(self.action_dim, dtype=np.float64)
        out = x[:, None, None] * 1000 + self.calls * 100 + t[None, :, None] + a[None, None, :] / 64
        self.calls += 1
        return out.astype(np.float32)

    def reset(self):
        self.calls = 0


def divisors(h):
    return [k for k in range(1, h + 1) if h % k == 0]


def _native_stream(horizon, action_dim, extra, observations, per_plan):
    pol = ObsPolicy(horizon, action_dim, extra)
    plans = [pol.plan({"x": observations[j * per_plan]}, len(observations[0]))[:, :horizon]
             for j in range(len(observations) // per_plan)]
    return np.concatenate(plans, axis=1)


def test_chunk_stream_equals_native_plans_per_environment():
    rng = random.Random(701)
    for case in range(300):
        horizon = rng.randrange(1, 65)
        k = rng.choice(divisors(horizon) + [0])                      # 0 disables chunking (K = 1)
        k_eff = max(k, 1)
        n = rng.randrange(1, 11)
        action_dim = rng.randrange(1, 5)
        extra = rng.choice([0, 0, rng.randrange(1, 8)])               # longer native plans get truncated
        n_plans = rng.randrange(1, 5)
        per_plan = horizon // k_eff
        observations = [np.array([rng.randrange(50) for _ in range(n)]) for _ in range(n_plans * per_plan)]
        pol = ObsPolicy(horizon, action_dim, extra)
        ex = ChunkExecutor(pol, k)
        got = []
        for i, o in enumerate(observations):
            out = ex.step({"x": o}, n)
            assert out.shape == (n, k_eff, action_dim), (case, i, out.shape)
            got.append(out)
        stream = np.concatenate(got, axis=1)
        expected = _native_stream(horizon, action_dim, extra, observations, per_plan)
        assert np.array_equal(stream, expected), case
        assert ex.plans == n_plans and len(pol.seen) == n_plans, case
        for j, x in enumerate(pol.seen):                             # re-planned exactly at plan boundaries
            assert np.array_equal(x, observations[j * per_plan]), (case, j)


def test_chunk_executor_reset_restarts_the_stream():
    rng = random.Random(702)
    for case in range(200):
        horizon = rng.randrange(1, 49)
        k = rng.choice(divisors(horizon))
        action_dim = rng.randrange(1, 4)
        ex = ChunkExecutor(ObsPolicy(horizon, action_dim), k)
        n0 = rng.randrange(1, 11)
        for _ in range(rng.randrange(0, 3 * horizon // k + 2)):
            ex.step({"x": np.array([rng.randrange(50) for _ in range(n0)])}, n0)
        ex.reset()
        n = rng.randrange(1, 11)                                     # the batch size may change after a reset
        per_plan = horizon // k
        observations = [np.array([rng.randrange(50) for _ in range(n)]) for _ in range(2 * per_plan)]
        after = np.concatenate([ex.step({"x": o}, n) for o in observations], axis=1)
        fresh = ChunkExecutor(ObsPolicy(horizon, action_dim), k)
        again = np.concatenate([fresh.step({"x": o}, n) for o in observations], axis=1)
        assert np.array_equal(after, again), case
        assert np.array_equal(after, _native_stream(horizon, action_dim, 0, observations, per_plan)), case


def test_chunk_executor_rejects_chunks_that_do_not_divide_the_replay():
    rng = random.Random(703)
    for _ in range(200):
        horizon = rng.randrange(2, 65)
        bad = [k for k in range(2, horizon + 8) if horizon % k]
        if not bad:
            continue
        with pytest.raises(ValueError, match="divide"):
            ChunkExecutor(ObsPolicy(horizon, 2), rng.choice(bad))


# =================================================================== simulate

def rand_setup(rng):
    tasks, rows, gens, specs, family = rand_level_ledger(rng)
    return rows, Setup.from_ledger(rows, tasks, "R", gens, specs, family)


def test_draw_ledger_keeps_template_cells_and_counts():
    rng = random.Random(801)
    for case in range(80):
        _, setup = rand_setup(rng)
        world = {(t, p): rng.random() for t, ps in setup.candidates.items() for p in ps}
        kappa = rng.uniform(0.2, 20)
        rep = rng.randrange(1, 4)
        seed = rng.randrange(10 ** 6)
        led = draw_ledger(setup, world, kappa, random.Random(seed), replicate=rep)
        assert led == draw_ledger(setup, world, kappa, random.Random(seed), replicate=rep), case
        m = len(setup.template)
        assert len(led) == rep * m, case
        for k in range(rep):
            for src, e in zip(setup.template, led[k * m:(k + 1) * m], strict=True):
                assert (e.task_id, e.task, e.policy, e.instance) == \
                       (src.task_id, src.task, src.policy, src.instance + 100 * k), case
        assert Counter((e.task_id, e.policy) for e in led) == \
               Counter({c: rep * n for c, n in Counter((e.task_id, e.policy) for e in setup.template).items()})
        assert all(0.0 <= e.q <= 1.0 and e.success == (e.q >= 0.999) for e in led), case
        cands = {(t, p) for t, ps in setup.candidates.items() for p in ps}
        assert {(e.task_id, e.policy) for e in setup.template} <= cands, case


def test_fit_beta_concentration_recovers_kappa():
    rng = random.Random(802)
    for case in range(12):
        kappa = rng.uniform(1.0, 20.0)
        eps = []
        for t in range(300):
            m = rng.uniform(0.1, 0.9)
            for i in REPORT:
                eps.append(ep(t, i, rng.betavariate(m * kappa, (1 - m) * kappa)))
        # Method of moments with the sample mean is biased low by about 1/n (n = 10 instances).
        assert fit_beta_concentration(eps) == pytest.approx(kappa, rel=0.2), (case, kappa)
    with pytest.raises(ValueError, match="variation"):
        fit_beta_concentration([ep(t, i, 0.5) for t in range(3) for i in REPORT])


def _canon(x):
    """NaN-safe structural comparison key for run_study output."""
    if isinstance(x, dict):
        return {k: _canon(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_canon(v) for v in x]
    if isinstance(x, float) and math.isnan(x):
        return "nan"
    return x


def test_run_study_is_deterministic_for_a_fixed_seed():
    rng = random.Random(803)
    for case in range(4):
        rows, setup = rand_setup(rng)
        kappa, seed, rep = rng.uniform(0.5, 5), rng.randrange(1000), rng.randrange(1, 3)
        a = run_study(setup, rows, kappa, sims=6, seed=seed, replicate=rep)
        b = run_study(setup, rows, kappa, sims=6, seed=seed, replicate=rep)
        assert _canon(a) == _canon(b), case
        assert set(a) == set(RULES)
        assert a["oracle"]["regret"] == 0
        for name, v in a.items():
            assert v["true"] <= a["oracle"]["true"] + 1e-12, (case, name)
            assert v["reported"] == sorted(v["reported"])
        other = run_study(setup, rows, kappa, sims=6, seed=seed + 1, replicate=rep)
        assert _canon(other) != _canon(a), case                     # the seed actually matters
