"""Analyses reported in the paper.  Every number is recomputed from ``data/``."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import mean

from . import data as D
from .metrics import bootstrap_q, challenge_q, rollouts_for_effect, task_means, within_task_sd
from .selection import Rules, select_by_level

FREEZE_UTC = "2026-10-13T12:54:00Z"   # stage-2 route frozen 07:54 CDT on Oct 13


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2
        i = j + 1
    return r


def pearson(x, y):
    mx, my = mean(x), mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sxy / (sx * sy) if sx and sy else float("nan")


def spearman(x, y):
    return pearson(_rank(x), _rank(y))


def task_table(official=None, route=None, tasks=None, dev=None):
    official = official or D.load_official()
    route = route or D.load_route()
    tasks = tasks or D.load_tasks()
    dev = dev if dev is not None else D.load_dev(selection_only=True)
    means = task_means(official)
    by_task = defaultdict(list)
    for e in official:
        by_task[e.task_id].append(e)
    dev_by = defaultdict(lambda: defaultdict(list))
    for e in dev:
        dev_by[e.task_id][e.policy].append(e.q)
    rows = []
    for t, r in zip(tasks, route["tasks"], strict=True):
        eps = sorted(by_task[t["id"]], key=lambda e: e.instance)
        chosen = dev_by[t["id"]].get(r["policy"], [])
        rows.append({
            "id": t["id"], "name": t["name"], "scene": t["scene"], "demo_seconds": t["demo_seconds"],
            "instruction": t["instruction"], "policy": r["policy"], "family": r["family"],
            "stage": r["stage"], "expected_q": r["expected_q"], "fallback": r["fallback"],
            "fallback_expected_q": r["fallback_expected_q"],
            "q": means.get(t["id"], 0.0), "q_by_instance": [round(e.q, 4) for e in eps],
            "successes": sum(e.success for e in eps),
            "timeouts": sum(e.timed_out for e in eps),
            "dev_rollouts": sum(len(v) for v in dev_by[t["id"]].values()),
            "dev_policies": len(dev_by[t["id"]]),
            "dev_chosen_n": len(chosen), "dev_chosen_mean": mean(chosen) if chosen else None,
        })
    return rows


def policy_table(rows, policies=None):
    policies = policies or D.load_policies()
    out = []
    for p, meta in policies.items():
        mine = [r for r in rows if r["policy"] == p]
        if not mine:
            continue
        out.append({
            "policy": p, "display": meta["display"], "family": meta["family"], "kind": meta["kind"],
            "tasks": len(mine), "task_ids": [r["id"] for r in mine],
            "q_mean": mean(r["q"] for r in mine),
            "task_points": sum(r["q"] for r in mine),
            "successes": sum(r["successes"] for r in mine),
            "nonzero_tasks": sum(r["q"] > 0 for r in mine),
            "expected_mean": mean(r["expected_q"] for r in mine),
        })
    out.sort(key=lambda d: -d["task_points"])
    return out


def reproduce_stage2(dev=None, route=None, freeze_utc: str = FREEZE_UTC):
    """Re-run the level-based selection for the deferred tasks 50-99 with dev data before the freeze."""
    import csv
    route = route or D.load_route()
    finished = {}
    with D._path("dev_rollouts.csv", None).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            finished[(r["run"], int(r["task_id"]), int(r["instance"]), r["policy"])] = r["finished_utc"]
    dev = dev if dev is not None else D.load_dev(selection_only=True)
    dev = [e for e in dev if finished[(e.run, e.task_id, e.instance, e.policy)] <= freeze_utc
           and e.task_id >= 50]
    frozen = {t["task_id"]: t for t in route["tasks"]}
    tasks = [t for t in range(50, 100) if frozen[t]["stage"] == 2]
    pols = {e.policy for e in dev}
    generalists = ["s150997", "comet@ymetz6000", "comet@ymetz9999"]
    specialists = sorted(p for p in pols if p.startswith("w100@"))
    family = {p: "ymetz" for p in generalists if "ymetz" in p}
    decisions = select_by_level(tasks, dev, "s150997", generalists, specialists, family, Rules())
    agree = [d for d in decisions if d.choice == frozen[d.task_id]["policy"]]
    disagree = []
    for d in decisions:
        if d.choice != frozen[d.task_id]["policy"]:
            post = {c.policy: c.posterior.mean for c in d.candidates}
            disagree.append({"task_id": d.task_id, "ours": d.choice, "frozen": frozen[d.task_id]["policy"],
                             "posterior_ours": post.get(d.choice),
                             "posterior_frozen": post.get(frozen[d.task_id]["policy"])})
    return {"tasks": len(decisions), "agree": len(agree), "dev_rollouts_used": len(dev),
            "disagreements": disagree,
            "choices": Counter(d.choice for d in decisions)}


def summarize(simulate: bool = True):
    official = D.load_official()
    route = D.load_route()
    dev_all = D.load_dev()
    dev_sel = D.load_dev(selection_only=True)
    rows = task_table(official, route, dev=dev_sel)
    q, lo, hi = bootstrap_q(official, n_boot=10_000, seed=0)
    sd = within_task_sd(official)
    failures = [e for e in official if not e.success]
    exp = [r["expected_q"] for r in rows]
    real = [r["q"] for r in rows]
    stage = {}
    for s in (1, 2):
        rs = [r for r in rows if r["stage"] == s]
        stage[s] = {"tasks": len(rs), "q_mean": mean(r["q"] for r in rs),
                    "expected_mean": mean(r["expected_q"] for r in rs),
                    "task_points": sum(r["q"] for r in rs)}
    gain = [r["expected_q"] - r["fallback_expected_q"] for r in rows if r["fallback_expected_q"] is not None]
    scenes = defaultdict(list)
    for r in rows:
        scenes[r["scene"]].append(r["q"])
    demo = [r["demo_seconds"] for r in rows]
    inst = Counter(e.instance for e in dev_all if 311 <= e.instance <= 320)
    hist = Counter(min(int(e.q * 10), 9) for e in official)
    return {
        "Q": challenge_q(official), "Q_ci95": [lo, hi], "episodes": len(official),
        "successes": sum(e.success for e in official), "success_rate": mean(e.success for e in official),
        "nonzero_tasks": sum(r["q"] > 0 for r in rows), "zero_tasks": sum(r["q"] == 0 for r in rows),
        "tasks_with_success": sum(r["successes"] > 0 for r in rows),
        "episodes_nonzero": sum(e.q > 0 for e in official),
        "within_task_sd": sd,
        "timeouts": sum(e.timed_out for e in official),
        "timeout_share_of_failures": sum(e.timed_out for e in failures) / len(failures),
        "replay_counts": Counter(r for r in _replays()),
        "stages": stage,
        "calibration": {"pearson": pearson(exp, real), "spearman": spearman(exp, real),
                        "mean_expected": mean(exp), "mean_realized": mean(real),
                        "stage2_predicted_gain_task_points": sum(gain)},
        "scenes": {k: {"tasks": len(v), "q_mean": mean(v)} for k, v in sorted(scenes.items())},
        "demo_length_spearman": spearman(demo, real),
        "q_histogram_deciles": [hist.get(i, 0) for i in range(10)],
        "dev": {"rollouts": len(dev_all), "selection_eligible": len(dev_sel),
                "instance_counts": dict(sorted(inst.items())),
                "share_instance_313": inst.get(313, 0) / max(1, sum(inst.values())),
                "policies_tested": len({e.policy for e in dev_all})},
        "power": {f"{d:.2f}": rollouts_for_effect(d, sd) for d in (0.02, 0.05, 0.10, 0.20)},
        "policies": policy_table(rows),
        "stage2_reproduction": reproduce_stage2(dev_sel, route),
        "simulation": simulation_study() if simulate else None,
        "calibration_breakdown": calibration_breakdown(),
        "reproduction_baselines": reproduction_baselines(),
        "tasks": rows,
    }


def _replays():
    import csv
    with D._path("official_episodes.csv", None).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            yield int(r["replay"])


def _stage2_setup(freeze_utc: str = FREEZE_UTC):
    """Development rows before the stage-2 freeze on tasks 50-99, and the simulation setup."""
    import csv

    from .simulate import Setup
    finished = {}
    with D._path("dev_rollouts.csv", None).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            finished[(r["run"], int(r["task_id"]), int(r["instance"]), r["policy"])] = r["finished_utc"]
    dev = [e for e in D.load_dev(selection_only=True)
           if e.task_id >= 50 and finished[(e.run, e.task_id, e.instance, e.policy)] <= freeze_utc]
    gens = ["s150997", "comet@ymetz6000", "comet@ymetz9999"]
    specs = sorted({e.policy for e in dev if e.policy.startswith("w100@")})
    family = {"comet@ymetz6000": "ymetz", "comet@ymetz9999": "ymetz"}
    return dev, Setup.from_ledger(dev, list(range(50, 100)), "s150997", gens, specs, family)


def simulation_study(sims: int = 300, curve_sims: int = 120, seed: int = 0):
    """Posterior-predictive study of the selection rules on tasks 50-99 (see policybank.simulate)."""
    from .simulate import fit_zero_inflated, run_study
    dev, setup = _stage2_setup()
    official = D.load_official()
    model = fit_zero_inflated(official)
    main = run_study(setup, dev, model, sims=sims, seed=seed)
    keep = ("strict rules (ours)", "best dev mean", "oracle")
    curve = {1: {k: {"true": main[k]["true"], "true_p05": main[k]["true_p05"], "true_p95": main[k]["true_p95"]}
                 for k in keep}}                      # the x1 point is the main run itself
    for m in (2, 4, 8):
        r = run_study(setup, dev, model, sims=curve_sims, seed=seed + m, replicate=m)
        curve[m] = {k: {"true": v["true"], "true_p05": v["true_p05"], "true_p95": v["true_p95"]}
                    for k, v in r.items() if k in keep}
    zeros_dev = sum(e.q == 0 for e in dev) / len(dev)
    # Observed counterparts on the same tasks.
    route = {t["task_id"]: t for t in D.load_route()["tasks"]}
    off = defaultdict(list)
    for e in official:
        off[e.task_id].append(e.q)
    cell = defaultdict(list)
    for e in dev:
        cell[(e.task_id, e.policy)].append(e.q)
    seen = [(mean(cell[(t, route[t]["policy"])]), mean(off[t])) for t in setup.tasks
            if cell.get((t, route[t]["policy"]))]
    observed = {
        "tasks": len(setup.tasks),
        "claimed": mean(route[t]["expected_q"] for t in setup.tasks),
        "realized": mean(mean(off[t]) for t in setup.tasks),
        "raw_dev_mean_routed": mean(a for a, _ in seen), "realized_on_those": mean(b for _, b in seen),
        "tasks_with_dev": len(seen),
    }
    observed["optimism"] = observed["claimed"] - observed["realized"]
    # Where does the observed reporting score fall among simulated reporting runs of our rule?
    rep = main["strict rules (ours)"]["reported"]
    observed["reported_percentile"] = sum(x <= observed["realized"] for x in rep) / len(rep)
    observed["reported_p05"], observed["reported_p95"] = rep[int(0.05 * len(rep))], rep[int(0.95 * len(rep)) - 1]
    for v in main.values():
        v.pop("reported")
    observed["raw_dev_gap"] = observed["raw_dev_mean_routed"] - observed["realized_on_those"]
    return {"kappa": model.kappa, "zero_c": model.c, "sims": sims, "rules": main, "curve": curve,
            "observed": observed, "template_rollouts": len(setup.template),
            "zero_share_official": sum(e.q == 0 for e in official) / len(official), "zero_share_dev": zeros_dev}


STAGE1_START_UTC = "2026-10-11T03:00:00Z"   # stage-1 reported runs began (first finish 03:04 UTC)


def calibration_breakdown():
    """Where the optimism gap sits: by evidence depth, by stage and task range, plus baselines."""
    import csv

    from .metrics import rollouts_for_selection, within_task_sd
    route = {t["task_id"]: t for t in D.load_route()["tasks"]}
    official = D.load_official()
    off = defaultdict(list)
    for e in official:
        off[e.task_id].append(e.q)
    real = {t: mean(v) for t, v in off.items()}
    finished = {}
    with D._path("dev_rollouts.csv", None).open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            finished[(r["run"], int(r["task_id"]), int(r["instance"]), r["policy"])] = r["finished_utc"]
    dev = D.load_dev(selection_only=True)

    def cutoff(t):
        return FREEZE_UTC if route[t]["stage"] == 2 else STAGE1_START_UTC

    own = defaultdict(list)
    for e in dev:
        done = finished[(e.run, e.task_id, e.instance, e.policy)]
        if e.policy == route[e.task_id]["policy"] and done <= cutoff(e.task_id):
            own[e.task_id].append(e.q)

    def group(ts):
        return {"tasks": len(ts), "expected": mean(route[t]["expected_q"] for t in ts) if ts else None,
                "realized": mean(real[t] for t in ts) if ts else None,
                "gap_points": sum(route[t]["expected_q"] - real[t] for t in ts)}

    by_depth = {"0": group([t for t in route if len(own[t]) == 0]),
                "1": group([t for t in route if len(own[t]) == 1]),
                "2+": group([t for t in route if len(own[t]) >= 2])}
    by_stage = {"stage 1 (tasks 0-49)": group([t for t in route if route[t]["stage"] == 1]),
                "stage 2, tasks 0-49": group([t for t in route if route[t]["stage"] == 2 and t < 50]),
                "stage 2, tasks 50-99": group([t for t in route if route[t]["stage"] == 2 and t >= 50])}
    fb = [t for t in route if route[t]["fallback_expected_q"] is not None]
    predicted_gain = sum(route[t]["expected_q"] - route[t]["fallback_expected_q"] for t in fb) / 100
    sd = within_task_sd(official)
    sd_nz = within_task_sd([e for e in official if real[e.task_id] > 0])
    elig_labels = len({e.policy for e in dev})
    inst = defaultdict(int)
    for e in dev:
        inst[e.instance] += 1
    # Development-only single-policy reference points (sweeps lean on instance 313).
    single = {}
    for p in ("s150997", "pt12", "comet@ymetz9999", "comet@ymetz6000", "pt50"):
        per = defaultdict(list)
        for e in dev:
            if e.policy == p:
                per[e.task_id].append(e.q)
        if per:
            single[p] = {"tasks": len(per), "mean": mean(mean(v) for v in per.values())}
    return {
        "by_depth": by_depth, "by_stage": by_stage,
        "predicted_gain_Q": predicted_gain, "fallback_tasks": len(fb),
        "within_sd": sd, "within_sd_nonzero_tasks": sd_nz,
        "selection_n": {f"{d:.2f}": rollouts_for_selection(d, sd) for d in (0.05, 0.10, 0.20)},
        "eligible_labels": elig_labels,
        "share_313_eligible": inst[313] / sum(inst.values()),
        "dev_single_policy": single,
        "routed_with_zero_own_stage1": sum(1 for t in route if route[t]["stage"] == 1 and len(own[t]) == 0),
        "own_dev_n": {t: len(own[t]) for t in sorted(route)},
        "eligible_at_freeze": sum(1 for e in dev if finished[(e.run, e.task_id, e.instance, e.policy)] <= FREEZE_UTC),
    }


def reproduction_baselines():
    """How much agreement with the frozen stage-2 route would trivial rules achieve?"""
    dev, setup = _stage2_setup()
    route = {t["task_id"]: t for t in D.load_route()["tasks"]}
    cell = defaultdict(list)
    for e in dev:
        cell[(e.task_id, e.policy)].append(e.q)
    raw = 0
    for t in setup.tasks:
        seen = [(sum(v) / len(v), p) for p in setup.candidates[t] if (v := cell.get((t, p)))]
        pick = max(seen)[1] if seen else setup.reference
        raw += pick == route[t]["policy"]
    ymetz = sum(route[t]["policy"] == "comet@ymetz9999" for t in setup.tasks)
    rep = reproduce_stage2()
    nondefault = [t for t in setup.tasks if route[t]["policy"] != "comet@ymetz9999"]
    dis = {d["task_id"] for d in rep["disagreements"]}
    return {"raw_dev_mean_agree": raw, "ymetz_everywhere_agree": ymetz,
            "nondefault_tasks": len(nondefault), "nondefault_agree": sum(t not in dis for t in nondefault)}
