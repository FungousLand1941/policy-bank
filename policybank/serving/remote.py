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
                 timeout_s: float = 540.0, drop_keys: tuple[str, ...] = ("action_chunk_size",),
                 forward_reset: bool = False):
        from websockets.sync.client import connect

        self.name, self.horizon, self.action_dim = name, horizon, action_dim
        self.timeout_s, self.drop_keys, self.forward_reset = timeout_s, drop_keys, forward_reset
        self._conn = connect(uri, compression=None, max_size=None, open_timeout=timeout_s)
        self.ws = self._conn.__enter__()
        self.metadata = unpack(self.ws.recv(timeout=timeout_s))

    @staticmethod
    def _batched(obs: dict) -> bool:
        props = [np.asarray(v) for k, v in obs.items() if isinstance(k, str) and k.endswith("proprio")]
        return bool(props) and props[0].ndim == 2

    def _split(self, obs: dict, n: int, i: int, batched: bool) -> dict:
        """One environment's observation, without the batch dimension (upstream is unbatched)."""
        out = {}
        for k, v in obs.items():
            if k in self.drop_keys:
                continue
            a = v
            if isinstance(a, np.ndarray) and a.ndim >= 1 and a.shape[0] == n and (batched or k == "task_id"):
                a = a[i]
            out[k] = a
        return out

    def _exchange(self, frame: bytes, expect_reply: bool = True):
        from websockets import ConnectionClosed
        try:
            self.ws.send(frame)
            return self.ws.recv(timeout=self.timeout_s) if expect_reply else None
        except ConnectionClosed as e:
            raise UpstreamError(f"upstream policy server closed the connection ({e})") from None
        except TimeoutError:
            raise UpstreamError(f"upstream policy server did not answer within {self.timeout_s:g} s") from None
        except OSError as e:
            raise UpstreamError(f"upstream connection failed: {e}") from None

    def plan(self, obs: dict, n: int) -> np.ndarray:
        batched = self._batched(obs)
        plans = []
        for i in range(n):
            reply = self._exchange(pack(self._split(obs, n, i, batched)))
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
        """Reset per-episode state.

        Plain OpenPI servers are stateless between requests, so by default nothing is sent and only
        the wrapper's own action queues (held by the executor) are cleared.  Native BEHAVIOR servers
        that keep per-episode state (stage trackers, action queues) understand the challenge's
        ``{"reset": True}`` frame, which carries no reply; enable ``forward_reset`` for those, or
        restart the upstream server for every session.
        """
        if self.forward_reset:
            self._exchange(pack({"reset": True}), expect_reply=False)

    def close(self) -> None:
        self._conn.__exit__(None, None, None)
