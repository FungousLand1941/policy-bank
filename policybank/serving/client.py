"""Minimal synchronous client for smoke tests against a running :class:`PolicyServer`."""
from __future__ import annotations

import numpy as np

from .codec import pack, unpack
from .contract import CHUNK_KEY


class PolicyClient:
    def __init__(self, uri: str, chunk: int = 4, timeout: float = 30.0):
        from websockets.sync.client import connect

        self._conn = connect(uri, max_size=128 * 1024 * 1024, compression=None, open_timeout=timeout)
        self.ws = self._conn.__enter__()
        self.metadata = unpack(self.ws.recv(timeout=timeout))
        self.chunk, self.timeout = chunk, timeout

    def infer(self, proprio: np.ndarray, task_id: int, **extra) -> dict:
        n = 1 if proprio.ndim == 1 else proprio.shape[0]
        obs = {"robot_r1::proprio": proprio.astype(np.float32),
               "task_id": np.full((n,), task_id, dtype=np.int64),
               CHUNK_KEY: np.asarray(self.chunk, dtype=np.int64), **extra}
        self.ws.send(pack(obs))
        return unpack(self.ws.recv(timeout=self.timeout))

    def reset(self) -> None:
        self.ws.send(pack({"reset": True}))

    def close(self) -> None:
        self._conn.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
