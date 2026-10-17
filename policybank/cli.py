"""Command line interface: ``python -m policybank <command>``."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from . import data as D


def cmd_score(a):
    from .metrics import bootstrap_q, success_rate
    eps = D.load_official(a.data)
    q, lo, hi = bootstrap_q(eps, n_boot=a.boot, seed=0)
    print(f"Q = {q:.6f}  (95% CI {lo:.4f}-{hi:.4f}, task-stratified bootstrap, {a.boot} resamples)")
    print(f"episodes = {len(eps)}  successes = {sum(e.success for e in eps)}  "
          f"success rate = {success_rate(eps):.3f}")


def cmd_route(a):
    from .routing import Route
    doc = D.load_route(a.data)
    route = Route.from_json(doc)
    route.validate(D.load_policies(a.data))
    print(f"route sha256 {route.sha256}  (stage 2 frozen {doc['stage2_frozen_utc']})")
    names = {t["id"]: t["name"] for t in D.load_tasks(a.data)}
    if a.images:
        for p, ts in route.images().items():
            print(f"{p:22s} {len(ts):3d} tasks  {ts}")
        return
    for t in doc["tasks"]:
        fb = f"  fallback {t['fallback']} {t['fallback_expected_q']:.3f}" if t["fallback"] else ""
        print(f"{t['task_id']:3d} {names[t['task_id']][:38]:38s} -> {t['policy']:20s} "
              f"stage {t['stage']}  E[q]={t['expected_q']:.3f}{fb}")


def cmd_select(a):
    from .analysis import reproduce_stage2
    r = reproduce_stage2(freeze_utc=a.freeze)
    print(f"stage-2 tasks 50-99: reimplementation agrees with the frozen route on "
          f"{r['agree']}/{r['tasks']} tasks using {r['dev_rollouts_used']} dev rollouts")
    for d in r["disagreements"]:
        print(f"  task {d['task_id']}: ours {d['ours']} ({d['posterior_ours']:.3f}) vs frozen "
              f"{d['frozen']} ({d['posterior_frozen']:.3f})")


def cmd_analyze(a):
    from .analysis import summarize
    s = summarize()
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=1, default=float)
        print(f"wrote {a.out}")
    else:
        s.pop("tasks")
        print(json.dumps(s, indent=1, default=float))


def cmd_serve(a):
    from .serving.contract import ContractSpec
    from .serving.executor import ScriptedPolicy
    from .serving.server import PolicyServer
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    policy = ScriptedPolicy(name=a.policy, horizon=a.replay)
    server = PolicyServer(policy, ContractSpec(chunk=a.chunk), query_timeout_s=a.query_timeout)
    sys.exit(asyncio.run(server.serve(a.host, a.port)))


def main(argv=None):
    p = argparse.ArgumentParser(prog="policybank", description=__doc__)
    p.add_argument("--data", type=lambda s: __import__("pathlib").Path(s), default=None,
                   help="dataset directory (default: the repository's data/)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score", help="challenge Q of the reported episodes with a bootstrap CI")
    s.add_argument("--boot", type=int, default=10_000)
    s.set_defaults(fn=cmd_score)
    s = sub.add_parser("route", help="show and validate the frozen route")
    s.add_argument("--images", action="store_true", help="group tasks by serving image")
    s.set_defaults(fn=cmd_route)
    s = sub.add_parser("select", help="re-run the stage-2 selection and compare with the frozen route")
    s.add_argument("--freeze", default="2026-10-13T12:54:00Z")
    s.set_defaults(fn=cmd_select)
    s = sub.add_parser("analyze", help="every number in the paper, as JSON")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_analyze)
    s = sub.add_parser("serve", help="run the fail-stop server with a scripted stand-in policy")
    s.add_argument("--policy", default="scripted")
    s.add_argument("--replay", type=int, default=32)
    s.add_argument("--chunk", type=int, default=4)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--query-timeout", type=float, default=550.0)
    s.set_defaults(fn=cmd_serve)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
