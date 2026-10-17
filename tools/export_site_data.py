#!/usr/bin/env python3
"""Write ``site/data/results.json`` (everything the website renders) and ``results/summary.json``."""
from __future__ import annotations

import csv
import json
import random
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from policybank import data as D  # noqa: E402
from policybank.analysis import FREEZE_UTC, STAGE1_START_UTC, summarize  # noqa: E402


def r(x, n=4):
    return None if x is None else round(float(x), n)


def main():
    s = summarize()
    policies = D.load_policies()
    dev = D.load_dev(selection_only=True)
    stage = {t["task_id"]: t["stage"] for t in D.load_route()["tasks"]}
    finished = {}
    with D._path("dev_rollouts.csv", None).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            finished[(row["run"], int(row["task_id"]), int(row["instance"]), row["policy"])] = row["finished_utc"]
    # Evidence as it stood when each task's route froze (stage 1: before its reported runs began).
    cell = defaultdict(lambda: defaultdict(list))
    later = defaultdict(int)
    for e in dev:
        cutoff = FREEZE_UTC if stage[e.task_id] == 2 else STAGE1_START_UTC
        if finished[(e.run, e.task_id, e.instance, e.policy)] <= cutoff:
            cell[e.task_id][e.policy].append(e.q)
        else:
            later[e.task_id] += 1

    own_n = s["calibration_breakdown"]["own_dev_n"]
    rng = random.Random(0)

    def task_ci(qs, n_boot=2000):
        """Percentile bootstrap of one task's mean over its ten instances."""
        k = len(qs)
        means = sorted(sum(qs[rng.randrange(k)] for _ in range(k)) / k for _ in range(n_boot))
        return [r(means[int(0.025 * n_boot)]), r(means[int(0.975 * n_boot) - 1])]

    tasks = []
    for t in s["tasks"]:
        tasks.append({
            "id": t["id"], "name": t["name"], "scene": t["scene"], "demo_s": t["demo_seconds"],
            "instruction": t["instruction"], "policy": t["policy"], "family": t["family"],
            "stage": t["stage"], "expected": r(t["expected_q"], 3), "fallback": t["fallback"],
            "fallback_expected": r(t["fallback_expected_q"], 3), "q": r(t["q"]),
            "qs": t["q_by_instance"], "q_ci95": task_ci(t["q_by_instance"]), "successes": t["successes"],
            "own_dev_n": own_n[t["id"]] if t["id"] in own_n else own_n[str(t["id"])],
            "dev": {p: {"n": len(v), "mean": r(sum(v) / len(v), 3)} for p, v in sorted(cell[t["id"]].items())},
            "dev_after_freeze": later[t["id"]],
        })

    out = {
        "generated_from": "data/ via tools/export_site_data.py",
        "headline": {
            "Q": r(s["Q"], 5), "Q_ci95": [r(x, 6) for x in s["Q_ci95"]], "episodes": s["episodes"],
            "successes": s["successes"], "nonzero_tasks": s["nonzero_tasks"], "zero_tasks": s["zero_tasks"],
            "tasks_with_success": s["tasks_with_success"], "episodes_nonzero": s["episodes_nonzero"],
            "within_task_sd": r(s["within_task_sd"], 3), "dev_rollouts": s["dev"]["rollouts"],
            "dev_eligible": s["dev"]["selection_eligible"], "policies_tested": s["dev"]["policies_tested"],
            "policies_routed": len(s["policies"]),
        },
        "stages": {str(k): {kk: r(vv, 4) for kk, vv in v.items()} for k, v in s["stages"].items()},
        "calibration": {k: r(v, 4) for k, v in s["calibration"].items()},
        "scenes": {k: {"tasks": v["tasks"], "q": r(v["q_mean"])} for k, v in s["scenes"].items()},
        "histogram": s["q_histogram_deciles"],
        "dev_instances": s["dev"]["instance_counts"],
        "share_313": r(s["dev"]["share_instance_313"], 3),
        "power": s["power"],
        "replay_counts": {str(k): v for k, v in s["replay_counts"].items()},
        "reproduction": {k: v for k, v in s["stage2_reproduction"].items() if k != "choices"},
        "reproduction_baselines": s["reproduction_baselines"],
        "breakdown": s["calibration_breakdown"],
        "simulation": {
            "kappa": r(s["simulation"]["kappa"], 3), "sims": s["simulation"]["sims"],
            "rules": {k: {kk: r(vv) for kk, vv in v.items()} for k, v in s["simulation"]["rules"].items()},
            "curve": {str(m): {k: {kk: r(vv) for kk, vv in v.items()} for k, v in c.items()}
                      for m, c in s["simulation"]["curve"].items()},
            "observed": {k: r(v) if isinstance(v, float) else v for k, v in s["simulation"]["observed"].items()},
            "zero_c": r(s["simulation"]["zero_c"], 2), "zero_share_official": r(s["simulation"]["zero_share_official"], 3),
            "zero_share_dev": r(s["simulation"]["zero_share_dev"], 3),
            "template_rollouts": s["simulation"]["template_rollouts"],
        },
        "policies": [{**p, "q_mean": r(p["q_mean"]), "task_points": r(p["task_points"], 3),
                      "expected_mean": r(p["expected_mean"], 3), **{
                          k: policies[p["policy"]][k] for k in ("source", "revision", "subfolder", "replay",
                                                                 "lineage", "license_status")}}
                     for p in s["policies"]],
        "tasks": tasks,
    }
    site = ROOT / "site" / "data"
    site.mkdir(parents=True, exist_ok=True)
    for name in ("official_episodes.csv", "dev_rollouts.csv", "route.json", "tasks.json", "policies.json"):
        shutil.copyfile(ROOT / "data" / name, site / name)       # downloadable from the page
    route = D.load_route()
    out["hashes"] = {"stage1_table_sha256": route["stage1_table_sha256"],
                     "stage2_table_sha256": route["stage2_table_sha256"],
                     "route_canonical_sha256": __import__("policybank.routing", fromlist=["Route"]).Route
                     .from_json(route).sha256, "stage2_frozen_utc": route["stage2_frozen_utc"]}
    (site / "results.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8", newline="\n")
    res = ROOT / "results"
    res.mkdir(exist_ok=True)
    s_out = dict(s)
    (res / "summary.json").write_text(json.dumps(s_out, indent=1, default=float, ensure_ascii=False) + "\n",
                                      encoding="utf-8", newline="\n")
    print(f"site/data/results.json  {len(tasks)} tasks, {len(out['policies'])} policies")


if __name__ == "__main__":
    main()
