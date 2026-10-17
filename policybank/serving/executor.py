"""Receding-horizon execution of action plans in fixed transport chunks.

Policies in the bank plan different horizons natively (32 actions for the Comet family, 20
for the winner family).  The evaluator asks for a single global chunk size ``K`` per query.
:class:`ChunkExecutor` keeps one queue of planned actions per environment, serves ``K`` of them
per query, and asks the policy for a new plan only when a queue cannot fill a chunk.  With
``K`` dividing the replay length, the executed action stream is identical to the native one.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np


class Policy(Protocol):
    """A batch policy: ``plan`` returns ``(n, horizon, action_dim)`` actions for ``n`` envs."""

    name: str
    horizon: int        # actions replayed per plan (the policy's native receding horizon)
    action_dim: int

    def plan(self, obs: dict, n: int) -> np.ndarray: ...

    def reset(self) -> None: ...


class ChunkExecutor:
    def __init__(self, policy: Policy, chunk: int):
        if chunk > 1 and policy.horizon % chunk:
            raise ValueError(f"chunk {chunk} must divide the policy's replay length {policy.horizon}")
        self.policy, self.chunk = policy, max(chunk, 1)
        self.queue: np.ndarray | None = None   # (n, remaining, action_dim)
        self.plans = 0

    def reset(self) -> None:
        self.queue = None
        self.policy.reset()

    def step(self, obs: dict, n: int) -> np.ndarray:
        """Return the next ``(n, K, action_dim)`` actions, re-planning when the queue runs dry."""
        if self.queue is None or self.queue.shape[1] < self.chunk:
            plan = np.asarray(self.policy.plan(obs, n))
            want = (n, self.policy.horizon, self.policy.action_dim)
            if plan.shape[:1] != (n,) or plan.ndim != 3 or plan.shape[2] != want[2] or plan.shape[1] < want[1]:
                raise ValueError(f"policy returned {plan.shape}, expected at least {want}")
            if not np.isfinite(plan).all():
                raise ValueError("policy returned nonfinite actions")
            self.queue = plan[:, : self.policy.horizon]
            self.plans += 1
        out, self.queue = self.queue[:, : self.chunk], self.queue[:, self.chunk:]
        return out


class ScriptedPolicy:
    """Deterministic stand-in used by tests and smoke runs: action[t] = plan_index + t / horizon."""

    def __init__(self, name: str = "scripted", horizon: int = 32, action_dim: int = 23):
        self.name, self.horizon, self.action_dim = name, horizon, action_dim
        self.calls = 0

    def plan(self, obs: dict, n: int) -> np.ndarray:
        base = np.arange(self.horizon, dtype=np.float32) / self.horizon + self.calls
        self.calls += 1
        return np.broadcast_to(base[None, :, None], (n, self.horizon, self.action_dim)).astype(np.float32)

    def reset(self) -> None:
        self.calls = 0
