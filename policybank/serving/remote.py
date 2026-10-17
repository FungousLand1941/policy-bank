"""Adapter for a real checkpoint served by an OpenPI-compatible websocket policy server.

OpenPI's ``serve_policy.py`` (and the Comet and 2025-winner forks) speak a simple protocol:
on connect the server sends a metadata map; each request is one msgpack-numpy observation
map for a single environment, and the reply is a map whose ``"actions"`` entry holds the
native action plan with shape ``(horizon, action_dim)``.  A string reply is an error.

:class:`OpenPIRemotePolicy` turns such a server into a :class:`~policybank.serving.executor.Policy`,
so the fail-stop :class:`~policybank.serving.server.PolicyServer` can sit in front of any real
checkpoint without touching its native preprocessing.  Batched queries are split per environment
because upstream servers are unbatched.
"""
from __future__ import annotations

import numpy as np

from .codec import pack, unpack


class UpstreamError(RuntimeError):
    pass


class OpenPIRemotePolicy:
    def __init__(self, uri: str, *, name: str = "remote", horizon: int = 32, action_dim: int = 23,
                 timeout_s: float = 540.0, drop_keys: tuple[str, ...] = ("action_chunk_size",)):
        from websockets.sync.client import connect

        self.name, self.horizon, self.action_dim = name, horizon, action_dim
        self.timeout_s, self.drop_keys = timeout_s, drop_keys
        self._conn = connect(uri, compression=None, max_size=None, open_timeout=timeout_s)
        self.ws = self._conn.__enter__()
        self.metadata = unpack(self.ws.recv(timeout=timeout_s))

    def _split(self, obs: dict, n: int, i: int) -> dict:
        out = {}
        for k, v in obs.items():
            if k in self.drop_keys:
                continue
            a = np.asarray(v) if isinstance(v, np.ndarray) else v
            if isinstance(a, np.ndarray) and n > 1 and a.ndim >= 1 and a.shape[0] == n:
                a = a[i]
            elif isinstance(a, np.ndarray) and a.ndim >= 1 and a.shape[0] == 1 and k == "task_id":
                a = a[0]
            out[k] = a
        return out

    def plan(self, obs: dict, n: int) -> np.ndarray:
        plans = []
        for i in range(n):
            self.ws.send(pack(self._split(obs, n, i)))
            reply = self.ws.recv(timeout=self.timeout_s)
            if isinstance(reply, str):
                raise UpstreamError(f"upstream policy error: {reply[:500]}")
            out = unpack(reply)
            if not isinstance(out, dict) or "actions" not in out:
                raise UpstreamError("upstream reply has no 'actions'")
            a = np.asarray(out["actions"], dtype=np.float32)
            if a.ndim != 2 or a.shape[0] < self.horizon or a.shape[1] != self.action_dim:
                raise UpstreamError(f"upstream plan {a.shape}, expected at least ({self.horizon}, {self.action_dim})")
            plans.append(a[: self.horizon])
        return np.stack(plans)

    def reset(self) -> None:
        """Upstream servers keep no per-episode state between requests; nothing to forward."""

    def close(self) -> None:
        self._conn.__exit__(None, None, None)
