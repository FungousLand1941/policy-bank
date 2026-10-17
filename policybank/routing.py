"""Frozen task-to-policy routes.

A route maps every task id to exactly one policy in the bank.  It is frozen before reported
evaluation starts and identified by the SHA-256 of a canonical JSON encoding, so the policy
that produced any reported episode can be checked after the fact.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from . import N_TASKS


class RouteError(ValueError):
    pass


@dataclass(frozen=True)
class Route:
    assignments: Mapping[int, str]

    @classmethod
    def from_json(cls, doc: Mapping) -> Route:
        """Accept either ``{"tasks": [{"task_id", "policy"}, ...]}`` or ``{task_id: policy}``."""
        items = ([(t["task_id"], t["policy"]) for t in doc["tasks"]] if "tasks" in doc
                 else list(doc.items()))
        pairs: dict[int, str] = {}
        for k, v in items:
            if int(k) in pairs:
                raise RouteError(f"task {int(k)} is routed twice")
            pairs[int(k)] = str(v)
        return cls(dict(sorted(pairs.items())))

    def canonical(self) -> bytes:
        return json.dumps({str(k): v for k, v in sorted(self.assignments.items())},
                          sort_keys=True, separators=(",", ":")).encode()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical()).hexdigest()

    def policy(self, task_id: int) -> str:
        try:
            return self.assignments[task_id]
        except KeyError:
            raise RouteError(f"task {task_id} is not routed") from None

    def validate(self, bank: Iterable[str], n_tasks: int = N_TASKS) -> None:
        bank = set(bank)
        missing = sorted(set(range(n_tasks)) - set(self.assignments))
        if missing:
            raise RouteError(f"unrouted tasks: {missing}")
        extra = sorted(set(self.assignments) - set(range(n_tasks)))
        if extra:
            raise RouteError(f"unknown task ids: {extra}")
        unknown = sorted({p for p in self.assignments.values() if p not in bank})
        if unknown:
            raise RouteError(f"policies outside the bank: {unknown}")

    def images(self) -> dict[str, list[int]]:
        """Group tasks by policy: one serving image per policy, each bound to its tasks."""
        out: dict[str, list[int]] = defaultdict(list)
        for t, p in self.assignments.items():
            out[p].append(t)
        return {p: sorted(ts) for p, ts in sorted(out.items(), key=lambda kv: -len(kv[1]))}

    def diff(self, other: Route) -> dict[int, tuple[str | None, str | None]]:
        keys = set(self.assignments) | set(other.assignments)
        return {t: (self.assignments.get(t), other.assignments.get(t)) for t in sorted(keys)
                if self.assignments.get(t) != other.assignments.get(t)}
