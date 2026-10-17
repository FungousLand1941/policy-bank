"""The session contract between the challenge evaluator and one policy container.

Every inbound frame and every outbound action passes through :class:`SessionContract`.  A
violation raises :class:`ContractError`, which the server treats as terminal: it closes the
connection and stops instead of inventing an action.  A failed rollout stays failed; a
fabricated action could look like a success while hiding the fault.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .codec import MAX_BYTES, unpack

CHUNK_KEY = "action_chunk_size"


class ContractError(ValueError):
    pass


@dataclass
class ContractSpec:
    proprio_dim: int = 61
    action_dim: int = 23
    max_batch: int = 10
    chunk: int = 4                       # global transport chunk K; 0/1 disables chunking
    tasks: frozenset[int] = field(default_factory=lambda: frozenset(range(100)))
    max_resets_between_queries: int = 1000


@dataclass
class Query:
    obs: dict
    n: int
    batched: bool
    task_id: int


class SessionContract:
    """Validates one evaluator connection.  The task binding outlives the connection."""

    def __init__(self, spec: ContractSpec, binding: dict | None = None):
        self.spec = spec
        self.binding = binding if binding is not None else {"task_id": None}
        self.batch: tuple[int, bool] | None = None
        self.pending_resets = 0

    def request(self, payload: bytes) -> Query | None:
        """Parse a frame.  Returns ``None`` for a reset (which has no reply)."""
        if not isinstance(payload, (bytes, bytearray)) or len(payload) > MAX_BYTES:
            raise ContractError("expected a bounded binary msgpack frame")
        try:
            obs = unpack(payload)
        except Exception as e:  # malformed msgpack, bad array header, ...
            raise ContractError(f"undecodable frame: {e}") from None
        if not isinstance(obs, dict):
            raise ContractError("expected an observation map")
        if "reset" in obs:
            if set(obs) != {"reset"} or obs["reset"] is not True:
                raise ContractError("reset must be exactly {reset: True}")
            self.batch = None
            self.pending_resets += 1
            if self.pending_resets > self.spec.max_resets_between_queries:
                raise ContractError("excessive resets without observations")
            return None

        props = [np.asarray(v) for k, v in obs.items() if isinstance(k, str) and k.endswith("proprio")]
        if len(props) != 1:
            raise ContractError("exactly one *proprio observation is required")
        p, d = props[0], self.spec.proprio_dim
        if p.shape == (d,):
            n, batched = 1, False
        elif p.ndim == 2 and p.shape[1] == d and 1 <= p.shape[0] <= self.spec.max_batch:
            n, batched = p.shape[0], True
        else:
            raise ContractError(f"proprio must be ({d},) or (N,{d}) with 1<=N<={self.spec.max_batch}")
        if p.dtype.kind not in "fiu" or not np.isfinite(p).all():
            raise ContractError("nonfinite or nonnumeric proprio")
        if self.batch is not None and self.batch != (n, batched):
            raise ContractError("batch shape changed without a reset")
        self.batch = (n, batched)

        ids = np.asarray(obs.get("task_id", []))
        if ids.dtype.kind not in "iu" or ids.size not in (1, n):
            raise ContractError("task_id must hold one integer or one per environment")
        values = {int(v) for v in ids.reshape(-1)}
        if len(values) != 1 or not values <= self.spec.tasks:
            raise ContractError("mixed or unsupported task ids")
        tid = values.pop()
        if self.binding["task_id"] is None:
            self.binding["task_id"] = tid
        elif self.binding["task_id"] != tid:
            raise ContractError("one task per container; a task change needs a new container")

        k = np.asarray(obs.get(CHUNK_KEY, 0))
        if k.size != 1 or k.dtype.kind not in "iu":
            raise ContractError("chunk size must be one integer")
        k = int(k.reshape(-1)[0])
        if (self.spec.chunk > 1 and k != self.spec.chunk) or (self.spec.chunk <= 1 and k not in (0, 1)):
            raise ContractError(f"expected the frozen global chunk {self.spec.chunk}, got {k}")
        return Query(obs, n, batched, tid)

    def reply(self, action: np.ndarray, chunk: np.ndarray | None, q: Query) -> dict:
        """Validate an outbound action (and chunk) and build the reply map."""
        a_dim = self.spec.action_dim
        a = np.asarray(action)
        want = (q.n, a_dim) if q.batched else (a_dim,)
        if a.shape != want or a.dtype.kind != "f" or not np.isfinite(a).all():
            raise ContractError(f"invalid action: shape {a.shape}, expected {want}, all finite")
        out = {"action": a}
        if self.spec.chunk > 1:
            c = np.asarray(chunk) if chunk is not None else None
            want_c = (q.n, self.spec.chunk, a_dim) if q.batched else (self.spec.chunk, a_dim)
            if c is None or c.shape != want_c or c.dtype != a.dtype or not np.isfinite(c).all():
                raise ContractError("missing or invalid action chunk")
            if c[..., 0, :].tobytes() != a.tobytes():
                raise ContractError("action differs from chunk row zero")
            out["action_chunk"] = c
        elif chunk is not None:
            raise ContractError("chunk returned while chunking is disabled")
        self.pending_resets = 0
        return out
