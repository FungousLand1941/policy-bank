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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

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
    """Parse and validate one evaluator metrics file; every problem raises :class:`AuditError`."""
    m = NAME.match(filename)
    if not m:
        raise AuditError(f"{filename}: unexpected file name")
    try:
        doc = json.loads(text, object_pairs_hook=_no_duplicate_keys,
                         parse_constant=lambda c: (_ for _ in ()).throw(AuditError(f"nonfinite {c}")))
    except json.JSONDecodeError as e:
        raise AuditError(f"{filename}: malformed JSON ({e})") from None
    if not isinstance(doc, dict):
        raise AuditError(f"{filename}: top level must be an object")
    for k in REQUIRED:
        if k not in doc:
            raise AuditError(f"{filename}: missing {k}")
    for k in ("instance_id", "rollout_id", "steps"):
        if type(doc[k]) is not int or doc[k] < 0:
            raise AuditError(f"{filename}: {k} must be a non-negative integer")
    if (doc["task"] != m["task"] or doc["instance_id"] != int(m["instance"])
            or doc["rollout_id"] != int(m["rollout"])):
        raise AuditError(f"{filename}: name does not match body")
    if not isinstance(doc["q_score"], dict) or not isinstance(doc["time"], dict):
        raise AuditError(f"{filename}: q_score and time must be objects")
    q = doc["q_score"].get("final")
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
    if len(set(task_names)) != N_TASKS or len(task_names) != N_TASKS:
        raise AuditError(f"expected {N_TASKS} distinct tasks, got {len(set(task_names))} of {len(task_names)}")
    seen: dict[tuple[str, int], int] = {}
    for c in cells:
        seen[c] = seen.get(c, 0) + 1
    dup = sorted(c for c, n in seen.items() if n > 1)
    if dup:
        raise AuditError(f"duplicate cells: {dup[:5]}")
    want = {(t, i) for t in task_names for i in instances}
    missing, extra = sorted(want - set(seen)), sorted(set(seen) - want)
    if missing or extra:
        raise AuditError(f"missing={missing[:5]} extra={extra[:5]}")


def verify_directory(directory, task_names: Sequence[str], expected_sha256: dict[tuple[str, int], str] | None = None,
                     instances: Sequence[int] = REPORT_INSTANCES) -> dict:
    """Audit a folder of evaluator metrics files (searched recursively for ``*_<inst>_<rollout>.json``).

    Checks every file with :func:`parse_metrics`, then coverage, then (optionally) each file's
    SHA-256 against the released ledger.  Returns a small report; raises :class:`AuditError` on
    the first hard failure.
    """
    import hashlib
    from pathlib import Path

    cells, mismatched, total = [], [], 0.0
    for path in sorted(Path(directory).rglob("*.json")):
        if not NAME.match(path.name):
            continue
        raw = path.read_bytes()
        doc = parse_metrics(path.name, raw.decode("utf-8"))
        cell = (doc["task"], doc["instance_id"])
        cells.append(cell)
        total += doc["q_score"]["final"]
        if expected_sha256 is not None and expected_sha256.get(cell) != hashlib.sha256(raw).hexdigest():
            mismatched.append(cell)
    check_coverage(cells, task_names, instances)
    return {"files": len(cells), "Q": total / (len(task_names) * len(instances)), "sha256_mismatches": mismatched}


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
