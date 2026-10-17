"""Audit evaluator output before scoring it.

Two rules from our run are encoded here:

* **Coverage and integrity.**  Exactly one metrics file per (task, reported instance), whose
  file name agrees with its body, with finite scores in range and no duplicate JSON keys.
* **Score-blind duplicate resolution.**  When infrastructure retries produce two completed
  rollouts of the same cell, keep the attempt that finished first and ignore its score.  The
  later attempt must not have started before the kept one ended; otherwise the order is not
  established and the cell is reported as ambiguous.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from . import N_TASKS, REPORT_INSTANCES

NAME = re.compile(r"^(?P<task>[A-Za-z0-9_]+)_(?P<instance>\d+)_(?P<rollout>\d+)\.json$")
REQUIRED = ("task", "instance_id", "rollout_id", "steps", "success", "q_score", "time")


class AuditError(ValueError):
    pass


def _no_duplicate_keys(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise AuditError(f"duplicate JSON keys: {sorted(k for k in set(keys) if keys.count(k) > 1)}")
    return dict(pairs)


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def parse_metrics(filename: str, text: str) -> dict:
    """Parse and validate one evaluator metrics file."""
    m = NAME.match(filename)
    if not m:
        raise AuditError(f"{filename}: unexpected file name")
    doc = json.loads(text, object_pairs_hook=_no_duplicate_keys,
                     parse_constant=lambda c: (_ for _ in ()).throw(AuditError(f"nonfinite {c}")))
    for k in REQUIRED:
        if k not in doc:
            raise AuditError(f"{filename}: missing {k}")
    if doc["task"] != m["task"] or int(doc["instance_id"]) != int(m["instance"]) \
            or int(doc["rollout_id"]) != int(m["rollout"]):
        raise AuditError(f"{filename}: name does not match body")
    q = doc["q_score"].get("final") if isinstance(doc["q_score"], dict) else None
    if not _finite(q) or not 0.0 <= q <= 1.0:
        raise AuditError(f"{filename}: q_score.final must be a finite number in [0, 1]")
    if not isinstance(doc["success"], bool):
        raise AuditError(f"{filename}: success must be boolean")
    if doc["success"] and q != 1.0:
        raise AuditError(f"{filename}: success with partial q")
    nt = doc["time"].get("normalized_time")
    if not _finite(nt) or nt < 0:
        raise AuditError(f"{filename}: invalid normalized_time")
    return doc


def check_coverage(cells: Iterable[tuple[str, int]], task_names: Sequence[str],
                   instances: Sequence[int] = REPORT_INSTANCES) -> None:
    """Every task x reported instance exactly once, nothing else."""
    seen: dict[tuple[str, int], int] = {}
    for c in cells:
        seen[c] = seen.get(c, 0) + 1
    dup = sorted(c for c, n in seen.items() if n > 1)
    if dup:
        raise AuditError(f"duplicate cells: {dup[:5]}")
    want = {(t, i) for t in task_names for i in instances}
    missing, extra = sorted(want - set(seen)), sorted(set(seen) - want)
    if len(task_names) != N_TASKS:
        raise AuditError(f"expected {N_TASKS} tasks, got {len(task_names)}")
    if missing or extra:
        raise AuditError(f"missing={missing[:5]} extra={extra[:5]}")


@dataclass(frozen=True)
class Attempt:
    cell: tuple[str, int]
    started: datetime
    finished: datetime
    q: float
    ref: str = ""


def resolve_duplicates(attempts: Iterable[Attempt]) -> tuple[list[Attempt], list[dict]]:
    """Keep the first completed attempt per cell, independent of ``q``.

    Returns the kept attempts and one decision record per resolved duplicate.
    """
    groups: dict[tuple[str, int], list[Attempt]] = {}
    for a in attempts:
        groups.setdefault(a.cell, []).append(a)
    kept, decisions = [], []
    for cell, group in sorted(groups.items()):
        group.sort(key=lambda a: a.finished)
        first = group[0]
        for later in group[1:]:
            if later.started < first.finished:
                raise AuditError(f"{cell}: attempts overlap in time; chronology not established")
        kept.append(first)
        if len(group) > 1:
            decisions.append({
                "cell": cell, "kept": first.ref, "kept_q": first.q,
                "excluded": [a.ref for a in group[1:]], "excluded_q": [a.q for a in group[1:]],
                "rule": "first completed attempt, score-blind",
            })
    return kept, decisions
