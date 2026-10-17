"""Fail-stop websocket policy server: one routed policy, one task, one evaluator session.

Design rules (each one answers a failure we either hit or had to rule out):

* **One task per container.**  The first query binds the task id; a different task id is a
  contract violation.  Images are built per policy and started per task.
* **One session at a time.**  Native policies can share RNG and action queues across
  connections, so a second concurrent connection is refused with close code 1013.
* **Terminal failures.**  Malformed frames, wrong shapes, nonfinite actions, model exceptions
  and timeouts close the connection with 1011 and stop the process with a nonzero status.
  There is no retry, no substitute action, no fallback checkpoint and no automatic restart.
* **Bounded latency.**  Each query is bounded end to end (decode, inference, validation,
  encode and send) below the evaluator's per-query limit.
* **Exact resets.**  A reset clears the action queues before the next action is produced.
"""
from __future__ import annotations

import asyncio
import contextlib
import http
import logging
import signal
import time
import uuid

import numpy as np

from .codec import pack
from .contract import ContractError, ContractSpec, SessionContract
from .executor import ChunkExecutor, Policy

LOG = logging.getLogger("policybank.serving")


class PolicyServer:
    def __init__(self, policy: Policy, spec: ContractSpec | None = None, *, query_timeout_s: float = 550.0,
                 task_id: int | None = None):
        self.policy = policy
        self.spec = spec or ContractSpec(action_dim=policy.action_dim)
        self.query_timeout_s = query_timeout_s
        self.binding = {"task_id": task_id}
        self.executor = ChunkExecutor(policy, self.spec.chunk)
        self.active = None
        self.failed = asyncio.Event()
        self.failure: str | None = None
        self.queries = 0

    def metadata(self) -> dict:
        return {"protocol": "b1k-2026", "policy": self.policy.name, "action_dim": self.spec.action_dim,
                "max_batch": self.spec.max_batch, "action_chunk_size": self.spec.chunk,
                "replay": self.policy.horizon, "failure_mode": "terminal"}

    def fail(self, reason: str) -> None:
        if not self.failed.is_set():
            self.failure = reason
            LOG.error("terminal failure: %s", reason)
            self.failed.set()

    def health(self, connection, request):
        if request.path in ("/healthz", "/readyz"):
            ok = not self.failed.is_set()
            return connection.respond(http.HTTPStatus.OK if ok else http.HTTPStatus.SERVICE_UNAVAILABLE,
                                      "OK\n" if ok else "FAILED\n")
        return None

    def _act(self, contract: SessionContract, payload: bytes):
        q = contract.request(payload)
        if q is None:
            self.executor.reset()
            return None
        chunk = self.executor.step(q.obs, q.n)                     # (n, K, A)
        k = self.spec.chunk
        if k > 1:
            action = chunk[:, 0]
            chunk_out = chunk if q.batched else chunk[0]
        else:
            action, chunk_out = chunk[:, 0], None
        action = action if q.batched else action[0]
        return contract.reply(np.ascontiguousarray(action), None if chunk_out is None
                              else np.ascontiguousarray(chunk_out), q)

    async def handler(self, ws):
        if self.active is not None or self.failed.is_set():
            await ws.close(code=1013, reason="one rollout batch per container")
            return
        self.active = ws
        conn = uuid.uuid4().hex[:8]
        contract = SessionContract(self.spec, self.binding)
        try:
            await asyncio.wait_for(ws.send(pack(self.metadata())), self.query_timeout_s)
            async for payload in ws:
                start = time.monotonic()

                async def one():
                    out = await asyncio.to_thread(self._act, contract, payload)
                    if out is None:
                        return
                    out["server_timing"] = {"total_ms": (time.monotonic() - start) * 1000}
                    await ws.send(await asyncio.to_thread(pack, out))
                    self.queries += 1

                await asyncio.wait_for(one(), self.query_timeout_s)
        except Exception as e:  # noqa: BLE001 - every failure is terminal by design
            import websockets
            if not isinstance(e, websockets.ConnectionClosedOK):
                kind = "contract" if isinstance(e, ContractError) else type(e).__name__
                self.fail(f"{kind} [{conn}]: {e}")
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(ws.close(code=1011, reason="terminal policy failure"), 1)
        finally:
            self.active = None

    def shutdown(self) -> None:
        """Stop serving cleanly (thread-safe); a no-op before :meth:`serve` starts."""
        if getattr(self, "_shutdown", None):
            self._shutdown()

    async def serve(self, host: str = "0.0.0.0", port: int = 8000, ready: asyncio.Event | None = None) -> int:
        from websockets.asyncio.server import serve

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        self._shutdown = lambda: loop.call_soon_threadsafe(stop.set)
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                loop.add_signal_handler(sig, stop.set)
        async with serve(self.handler, host, port, compression=None, max_size=128 * 1024 * 1024,
                         max_queue=1, ping_interval=None, close_timeout=1,
                         process_request=self.health) as server:
            self.port = server.sockets[0].getsockname()[1] if server.sockets else port
            LOG.info("SERVER_READY policy=%s chunk=%s replay=%s port=%s", self.policy.name,
                     self.spec.chunk, self.policy.horizon, self.port)
            if ready is not None:
                ready.set()
            waits = [asyncio.create_task(self.failed.wait()), asyncio.create_task(stop.wait())]
            await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
            for w in waits:
                w.cancel()
        return 1 if self.failed.is_set() else 0
