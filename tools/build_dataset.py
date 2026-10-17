#!/usr/bin/env python3
"""Build the public, sanitised dataset in ``data/`` from the team's raw evaluation exports.

The raw inputs are internal pipeline files (cluster paths, job identifiers, run
directories).  This script keeps only the fields needed to reproduce the
numbers in the paper and drops everything that identifies infrastructure.

Usage::

    python tools/build_dataset.py --raw /path/to/raw --out data

Expected raw layout (names as exported by the evaluation pipeline)::

    tasks_all.tsv                 id, name, demo seconds, scene, instruction
    ROUTE.tsv / ROUTE2.tsv        stage-1 and stage-2 route tables with expected Q
    routes.frozen.json            frozen task -> policy mapping used by the run
    official7_episodes.tsv        episode index with the policy that produced it
    canonical/*.json              1,000 unchanged evaluator metric files
    dev_all_live.tsv              every development rollout (instances 311-320)
    duplicate-resolution.json     chronology decisions for the two duplicate cells
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from policybank.routing import Route  # noqa: E402

# Replay length actually executed per policy family (actions replayed per model query).
FAMILY_REPLAY = {"comet": 32, "winner": 20, "winner100": 20}

# The seven reported episodes produced by the second recovery pass, which replays 0 actions
# (one model query per control step).  Taken from the run's ``.chunk`` markers.
ZERO_REPLAY = {
    ("cleaning_up_plates_and_food", 307), ("sorting_vegetables", 305), ("canning_food", 306),
    ("freeze_fruit", 308), ("putting_away_toys", 306), ("carrying_out_garden_furniture", 301),
    ("tidying_bathroom", 309),
}

POLICIES = {
    "pt50": {
        "family": "comet", "display": "Comet π0.5 pt50", "kind": "public",
        "source": "sunshk/openpi_comet", "revision": "61739ffbced89dd5ba1b87c30d93d6084b79b0af",
        "subfolder": "pi05-b1kpt50-cs32", "replay": 32,
        "lineage": "π0.5 (OpenPI) post-trained by Team Comet on BEHAVIOR-1K demonstrations (2025 challenge, 2nd place).",
        "license_status": "Code Apache-2.0; separate weight grant not found (scope unresolved).",
    },
    "pt12": {
        "family": "comet", "display": "Comet π0.5 pt12", "kind": "public",
        "source": "sunshk/openpi_comet", "revision": "61739ffbced89dd5ba1b87c30d93d6084b79b0af",
        "subfolder": "pi05-b1kpt12-cs32", "replay": 32,
        "lineage": "Sibling Comet π0.5 checkpoint released with pt50.",
        "license_status": "Code Apache-2.0; separate weight grant not found (scope unresolved).",
    },
    "s150997": {
        "family": "comet", "display": "pt50 + 2026 demos (ours)", "kind": "ours",
        "source": "KANR continued training", "revision": "step 150997", "subfolder": "", "replay": 32,
        "lineage": "Our continued training of Comet pt50 on the 2026 demonstrations of all 100 tasks.",
        "license_status": "Derivative of pt50; inherits the pt50 terms.",
    },
    "comet@ymetz9999": {
        "family": "comet", "display": "ymetz pt50 step 9999", "kind": "public",
        "source": "ymetz/pi05-b1k-pt50-steps-public", "revision": "20e80d254069f318196db7fb91865bdb647f549b",
        "subfolder": "steps-cont-9999", "replay": 32,
        "lineage": "Public continuation of pt50 on the 2026 demos with task/skill/step prompts.",
        "license_status": "Declared to follow the base checkpoint and OpenPI terms.",
    },
    "winner1": {
        "family": "winner", "display": "2025 winner ckpt 1", "kind": "public",
        "source": "IliaLarchenko/behavior_submission", "revision": "89545bc1b7aa7f2e687bc0032d091f132d715d4e",
        "subfolder": "checkpoint_1", "replay": 20,
        "lineage": "2025 BEHAVIOR Challenge winning solution (Larchenko, Zarin, Karnatak), native wrapper with correction rules.",
        "license_status": "Apache-2.0 declared by the publisher at this revision.",
    },
    "winner2": {
        "family": "winner", "display": "2025 winner ckpt 2", "kind": "public",
        "source": "IliaLarchenko/behavior_submission", "revision": "89545bc1b7aa7f2e687bc0032d091f132d715d4e",
        "subfolder": "checkpoint_2", "replay": 20,
        "lineage": "2025 BEHAVIOR Challenge winning solution, checkpoint 2.",
        "license_status": "Apache-2.0 declared by the publisher at this revision.",
    },
    "winner3": {
        "family": "winner", "display": "2025 winner ckpt 3", "kind": "public",
        "source": "IliaLarchenko/behavior_submission", "revision": "89545bc1b7aa7f2e687bc0032d091f132d715d4e",
        "subfolder": "checkpoint_3", "replay": 20,
        "lineage": "2025 BEHAVIOR Challenge winning solution, checkpoint 3.",
        "license_status": "Apache-2.0 declared by the publisher at this revision.",
    },
    "winner4": {
        "family": "winner", "display": "2025 winner ckpt 4", "kind": "public",
        "source": "IliaLarchenko/behavior_submission", "revision": "89545bc1b7aa7f2e687bc0032d091f132d715d4e",
        "subfolder": "checkpoint_4", "replay": 20,
        "lineage": "2025 BEHAVIOR Challenge winning solution, checkpoint 4.",
        "license_status": "Apache-2.0 declared by the publisher at this revision.",
    },
    "w100@j_jl_4task100": {
        "family": "winner100", "display": "JackLiu 4-task specialist", "kind": "public",
        "source": "JackLiu0406/b1k-checkpoints", "revision": "ec1844b09fa2b259f131e9078896742404d5cbfd",
        "subfolder": "pi_behavior_100t_meta_ft_4task", "replay": 20,
        "lineage": "Winner-format model fine-tuned for four 2026 tasks (54, 56, 77, 98).",
        "license_status": "Apache-2.0 declared by the publisher at this revision.",
    },
    "w100@b_amy_t90": {
        "family": "winner100", "display": "amyjia 5-task specialist", "kind": "public",
        "source": "amyjia1212/b1k-2026-t90-91-93-96-97", "revision": "7519e44670b9c589ed8fe3ce65a5a17583ae9cff",
        "subfolder": "step_099999", "replay": 20,
        "lineage": "Winner-format specialist published for tasks 90, 91, 93, 96 and 97.",
        "license_status": "Public and ungated; no licence stated by the publisher.",
    },
}

# ROUTE2.tsv header: written 2026-10-13 07:54 CDT from development evidence only.
STAGE2_FROZEN_UTC = "2026-10-13T12:54:00Z"

# Older dev-run labels that do not carry a routed-policy name.
DEV_LABEL_ALIASES = {"base": "pt50-sweep", "ft": "ft-sweep"}


def iso(epoch: str) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_tsv(path: Path, comment: str = "#"):
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith(comment):
                continue
            yield line.split("\t")


def parse_tasks(raw: Path):
    tasks = []
    for row in read_tsv(raw / "tasks_all.tsv"):
        tid, name, demo_s, scene, instruction = row[:5]
        tasks.append({"id": int(tid), "name": name, "demo_seconds": int(demo_s), "scene": scene,
                      "instruction": instruction})
    prompts = raw / "task_mapping_100.json"   # BEHAVIOR task prompts, used where the table has none
    if prompts.exists():
        by_name = json.loads(prompts.read_text(encoding="utf-8"))
        for t in tasks:
            if not t["instruction"] and t["name"] in by_name:
                t["instruction"] = by_name[t["name"]]["task"]
    tasks.sort(key=lambda t: t["id"])
    assert len(tasks) == 100 and [t["id"] for t in tasks] == list(range(100))
    return tasks


EXPECT = re.compile(r"#\s*([0-9.]+)")
FALLBACK = re.compile(r"fallback\s+(\S+)\s+([0-9.]+)")


def parse_routes(raw: Path, tasks):
    frozen = json.loads((raw / "routes.frozen.json").read_text())
    stage1, stage2 = {}, {}
    for row in read_tsv(raw / "ROUTE.tsv"):
        tid, name, demo_s, policy, part = row[:5]
        rest = "\t".join(row[5:])
        m = EXPECT.search(rest)
        stage1[int(tid)] = {"policy": policy, "part": part, "expected_q": float(m.group(1)) if m else None,
                            "fallback": row[5] if policy == "defer" else None}
    for row in read_tsv(raw / "ROUTE2.tsv"):
        tid, name, demo_s, policy, part = row[:5]
        rest = "\t".join(row[5:])
        m, fb = EXPECT.search(rest), FALLBACK.search(rest)
        stage2[int(tid)] = {"policy": policy, "part": part, "expected_q": float(m.group(1)),
                            "fallback": fb.group(1) if fb else None,
                            "fallback_expected_q": float(fb.group(2)) if fb else None}
    route = []
    for t in tasks:
        tid = t["id"]
        final = frozen["tasks"][str(tid)]["policy"]
        s1 = stage1[tid]
        if s1["policy"] == "defer":
            s2 = stage2[tid]
            assert s2["policy"] == final, (tid, s2["policy"], final)
            entry = {"stage": 2, "selection": "development posterior (stage 2)", "part": s2["part"],
                     "expected_q": s2["expected_q"], "fallback": s2["fallback"],
                     "fallback_expected_q": s2["fallback_expected_q"]}
        else:
            assert s1["policy"] == final, (tid, s1["policy"], final)
            entry = {"stage": 1, "selection": "prior + development posterior (stage 1)", "part": s1["part"],
                     "expected_q": s1["expected_q"], "fallback": None, "fallback_expected_q": None}
        route.append({"task_id": tid, "task": t["name"], "policy": final,
                      "family": POLICIES[final]["family"], **entry})
    return route, frozen["source"]


def parse_official(raw: Path, tasks, route):
    by_name = {t["name"]: t["id"] for t in tasks}
    policy_of = {r["task_id"]: r["policy"] for r in route}
    index = {}
    for row in read_tsv(raw / "official7_episodes.tsv"):
        if row[0] == "task":
            continue
        index[(row[0], int(row[1]))] = (row[9], iso(row[11]))
    rows = []
    for path in sorted((raw / "canonical").glob("*.json")):
        d = json.loads(path.read_text())
        task, inst = d["task"], int(d["instance_id"])
        tid = by_name[task]
        policy = policy_of[tid]
        indexed_policy, finished = index[(task, inst)]
        assert indexed_policy == policy, (task, inst, indexed_policy, policy)
        replay = 0 if (task, inst) in ZERO_REPLAY else FAMILY_REPLAY[POLICIES[policy]["family"]]
        rows.append({
            "task_id": tid, "task": task, "instance": inst, "policy": policy,
            "q": d["q_score"]["final"], "success": int(bool(d["success"])), "steps": d["steps"],
            "sim_seconds": round(d["time"]["simulator_time"], 3),
            "normalized_time": round(d["time"]["normalized_time"], 6),
            "nd_base": round(d["normalized_agent_distance"]["base"], 6),
            "nd_left": round(d["normalized_agent_distance"]["left"], 6),
            "nd_right": round(d["normalized_agent_distance"]["right"], 6),
            "replay": replay, "finished_utc": finished,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    rows.sort(key=lambda r: (r["task_id"], r["instance"]))
    assert len(rows) == 1000
    return rows


def parse_dev(raw: Path, tasks):
    by_name = {t["name"]: t["id"] for t in tasks}
    out = []
    for row in read_tsv(raw / "dev_all_live.tsv"):
        if row[0] == "run":
            continue
        run, task, inst, q, success, steps, norm_time, label, _rundir, mtime = row[:10]
        if task not in by_name:
            continue
        head, _, desc = label.partition("|")
        policy = head.strip() or "unlabelled"
        policy = DEV_LABEL_ALIASES.get(policy, policy)
        desc = desc.lower()
        variant = any(k in desc for k in ("time compression", "gripper correction", "action_search",
                                          "sticky", "zscore"))
        nondefault_config = "robot config" in desc
        inst = int(inst)
        out.append({
            "run": run, "task_id": by_name[task], "task": task, "instance": inst,
            "policy": policy, "q": float(q), "success": int(success), "steps": int(steps),
            "normalized_time": float(norm_time),
            "variant": int(variant), "nondefault_config": int(nondefault_config),
            "dev_split": int(311 <= inst <= 320), "finished_utc": iso(mtime),
        })
    out.sort(key=lambda r: (r["task_id"], r["run"], r["instance"]))
    return out


def write_csv(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("data"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    tasks = parse_tasks(a.raw)
    route, source = parse_routes(a.raw, tasks)
    official = parse_official(a.raw, tasks, route)
    dev = parse_dev(a.raw, tasks)
    dup = json.loads((a.raw / "duplicate-resolution.json").read_text())

    (a.out / "tasks.json").write_text(json.dumps(tasks, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (a.out / "policies.json").write_text(json.dumps(POLICIES, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (a.out / "route.json").write_text(json.dumps({
        "schema": "policy-bank-route/1",
        "stage2_frozen_utc": STAGE2_FROZEN_UTC,
        "manifest_built_utc": source["built_utc"],
        "route_sha256": Route.from_json({"tasks": route}).sha256,
        "stage1_table_sha256": source["route_sha256"],
        "stage2_table_sha256": source["route2_sha256"],
        "tasks": route,
    }, indent=1) + "\n", encoding="utf-8", newline="\n")
    write_csv(a.out / "official_episodes.csv", official)
    write_csv(a.out / "dev_rollouts.csv", dev)
    (a.out / "duplicates.json").write_text(json.dumps([{
        "task": d["task"], "instance": d["instance"], "rule": d["rule"],
        "kept_q": d["kept"]["q"], "kept_sha256": d["kept"]["sha256"],
        "excluded_q": d["excluded"]["q"], "excluded_sha256": d["excluded"]["sha256"],
    } for d in dup["decisions"]], indent=1) + "\n", encoding="utf-8", newline="\n")

    q = sum(r["q"] for r in official) / len(official)
    print(f"tasks={len(tasks)} official={len(official)} dev={len(dev)} Q={q:.17g}")


if __name__ == "__main__":
    main()
