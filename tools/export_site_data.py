#!/usr/bin/env python3
"""Write ``site/data/results.json`` (everything the website renders) and ``results/summary.json``."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from policybank import data as D  # noqa: E402
from policybank.analysis import summarize  # noqa: E402


def r(x, n=4):
    return None if x is None else round(float(x), n)


def main():
    s = summarize()
    policies = D.load_policies()
    dev = D.load_dev(selection_only=True)
    cell = defaultdict(lambda: defaultdict(list))
    for e in dev:
        cell[e.task_id][e.policy].append(e.q)

    tasks = []
    for t in s["tasks"]:
        tasks.append({
            "id": t["id"], "name": t["name"], "scene": t["scene"], "demo_s": t["demo_seconds"],
            "instruction": t["instruction"], "policy": t["policy"], "family": t["family"],
            "stage": t["stage"], "expected": r(t["expected_q"], 3), "fallback": t["fallback"],
            "fallback_expected": r(t["fallback_expected_q"], 3), "q": r(t["q"]),
            "qs": t["q_by_instance"], "successes": t["successes"],
            "dev": {p: {"n": len(v), "mean": r(sum(v) / len(v), 3)} for p, v in sorted(cell[t["id"]].items())},
        })

    out = {
        "generated_from": "data/ via tools/export_site_data.py",
        "headline": {
            "Q": r(s["Q"], 5), "Q_ci95": [r(x, 4) for x in s["Q_ci95"]], "episodes": s["episodes"],
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
        "policies": [{**p, "q_mean": r(p["q_mean"]), "task_points": r(p["task_points"], 3),
                      "expected_mean": r(p["expected_mean"], 3), **{
                          k: policies[p["policy"]][k] for k in ("source", "revision", "subfolder", "replay",
                                                                 "lineage", "license_status")}}
                     for p in s["policies"]],
        "tasks": tasks,
    }
    site = ROOT / "site" / "data"
    site.mkdir(parents=True, exist_ok=True)
    (site / "results.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    res = ROOT / "results"
    res.mkdir(exist_ok=True)
    s_out = dict(s)
    (res / "summary.json").write_text(json.dumps(s_out, indent=1, default=float, ensure_ascii=False) + "\n",
                                      encoding="utf-8")
    print(f"site/data/results.json  {len(tasks)} tasks, {len(out['policies'])} policies")


if __name__ == "__main__":
    main()
