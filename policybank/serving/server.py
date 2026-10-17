"""Fail-stop websocket policy server: one routed policy, one task, one evaluator session.

Design rules (each one answers a failure we either hit or had to rule out):

* **One task per container.**  The first query binds the task id; a different task id is a
  contract violation.  Images are built per policy and started per task.
* **One session at a time.**  Native policies can share RNG and action queues across
  connections, so a second concurrent connection is refused with close code 1013.  Every new
  session starts from a reset policy, so nothing leaks from a previous connection.
* **Terminal policy failures.**  Malformed frames, wrong shapes, nonfinite actions, model
  exceptions and timeouts close the connection with 1011 and stop the server with a nonzero
  status.  There is no retry, no substitute action, no fallback checkpoint and no automatic
  restart.  An evaluator that simply disconnects is not a policy failure: the session ends and
  the next connection starts fresh (the evaluator may reconnect).
* **Bounded latency.**  Each query is bounded end to end (decode, inference, validation,
  encode and send) below the evaluator's per-query limit.  Inference runs on a dedicated
  worker thread; a hung model cannot be interrupted from Python, so the command-line entry
  point exits the process with ``os._exit`` after a failure instead of joining that thread.
* **Exact resets.**  A reset clears the action queues before the next action is produced.
"""
from __future__ import annotations

import asyncio
import contextlib
import http
import logging
import signal
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .codec import pack
from .contract import ContractError, ContractSpec, SessionContract
from .executor import ChunkExecutor, Policy

LOG = logging.getLogger("policybank.serving")


class QueryTimeout(TimeoutError):
    pass


class PolicyServer:
    def __init__(self, policy: Policy, spec: ContractSpec | None = None, *, query_timeout_s: float = 550.0,
                 task_id: int | None = None):
        self.policy = policy
        self.spec = spec or ContractSpec(action_dim=policy.action_dim)
        self.query_timeout_s = query_timeout_s
        self.binding = {"task_id": task_id}
        self.executor = ChunkExecutor(policy, self.spec.chunk)
        self.active = None
        self.failed = threading.Event()          # thread-safe; readable before, during and after serve()
        self.failure: str | None = None
        self.queries = 0
        self.sessions = 0
        self.port: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None
        self._stop: asyncio.Event | None = None
        self._pool: ThreadPoolExecutor | None = None

    def metadata(self) -> dict:
        return {"protocol": "b1k-2026", "policy": self.policy.name, "action_dim": self.spec.action_dim,
                "max_batch": self.spec.max_batch, "action_chunk_size": self.spec.chunk,
                "replay": self.policy.horizon, "failure_mode": "terminal"}

    # ------------------------------------------------------------------ state

    def fail(self, reason: str) -> None:
        if self.failed.is_set():
            return
        self.failure = reason
        LOG.error("terminal failure: %s", reason)
        self.failed.set()
        loop, wake = self._loop, self._wake
        if loop is not None and wake is not None:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(wake.set)

    def shutdown(self) -> None:
        """Stop serving cleanly (thread-safe); a no-op before :meth:`serve` starts."""
        loop, stop = self._loop, self._stop
        if loop is not None and stop is not None:
            with contextlib.suppress(RuntimeError):          # the loop already finished
                loop.call_soon_threadsafe(stop.set)

    def health(self, connection, request):
        if request.path in ("/healthz", "/readyz"):
            ok = not self.failed.is_set()
            return connection.respond(http.HTTPStatus.OK if ok else http.HTTPStatus.SERVICE_UNAVAILABLE,
                                      "OK\n" if ok else "FAILED\n")
        return None

    # ------------------------------------------------------------------ queries

    def _act(self, contract: SessionContract, payload: bytes):
        q = contract.request(payload)
        if q is None:
            self.executor.reset()
            return None
        chunk = self.executor.step(q.obs, q.n)                     # (n, K, A)
        action = chunk[:, 0] if q.batched else chunk[0, 0]
        chunk_out = None
        if self.spec.chunk > 1:
            chunk_out = np.ascontiguousarray(chunk if q.batched else chunk[0])
        return contract.reply(np.ascontiguousarray(action), chunk_out, q)

    async def _run(self, fn, *args):
        return await asyncio.get_running_loop().run_in_executor(self._pool, fn, *args)

    async def _query(self, ws, contract: SessionContract, payload: bytes, start: float) -> None:
        out = await self._run(self._act, contract, payload)
        if out is None:
            return                                                 # reset: the protocol sends no reply
        out["server_timing"] = {"total_ms": (time.monotonic() - start) * 1000}
        await ws.send(await self._run(pack, out))
        self.queries += 1

    async def handler(self, ws):
        import websockets

        if self.active is not None or self.failed.is_set():
            await ws.close(code=1013, reason="one rollout batch per container")
            return
        self.active = ws
        self.sessions += 1
        conn = uuid.uuid4().hex[:8]
        contract = SessionContract(self.spec, self.binding)
        try:
            await self._run(self.executor.reset)                   # nothing carries over between sessions
            await asyncio.wait_for(ws.send(pack(self.metadata())), self.query_timeout_s)
            async for payload in ws:
                try:
                    await asyncio.wait_for(self._query(ws, contract, payload, time.monotonic()),
                                           self.query_timeout_s)
                except asyncio.TimeoutError:
                    raise QueryTimeout(f"query exceeded {self.query_timeout_s:g} s") from None
        except websockets.ConnectionClosed as e:
            # The evaluator went away (cleanly or not).  Not a policy fault: end the session.
            LOG.warning("session %s closed by peer (%s)", conn, e)
        except Exception as e:  # noqa: BLE001 - every policy-side failure is terminal by design
            kind = "contract" if isinstance(e, ContractError) else type(e).__name__
            self.fail(f"{kind} [{conn}]: {e}")
            with contextlib.suppress(Exception):
                await asyncio.wait_for(ws.close(code=1011, reason="terminal policy failure"), 1)
        finally:
            self.active = None

    # ------------------------------------------------------------------ lifecycle

    async def serve(self, host: str = "0.0.0.0", port: int = 8000, ready: asyncio.Event | None = None) -> int:
        from websockets.asyncio.server import serve

        self._loop = asyncio.get_running_loop()
        self._wake, self._stop = asyncio.Event(), asyncio.Event()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="policy")
        if self.failed.is_set():
            self._wake.set()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                self._loop.add_signal_handler(sig, self._stop.set)
        try:
            async with serve(self.handler, host, port, compression=None, max_size=128 * 1024 * 1024,
                             max_queue=1, ping_interval=None, close_timeout=1,
                             process_request=self.health) as server:
                self.port = server.sockets[0].getsockname()[1] if server.sockets else port
                LOG.info("SERVER_READY policy=%s chunk=%s replay=%s port=%s", self.policy.name,
                         self.spec.chunk, self.policy.horizon, self.port)
                if ready is not None:
                    ready.set()
                waits = [asyncio.create_task(self._wake.wait()), asyncio.create_task(self._stop.wait())]
                done, pending = await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
                for w in pending:
                    w.cancel()
                for w in done:
                    if w.exception() is not None:
                        self.fail(f"serve loop: {w.exception()!r}")
        finally:
            # Never join a possibly hung inference thread here.
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._loop = None
        return 1 if self.failed.is_set() else 0
