#!/usr/bin/env python3
"""End-to-end smoke test for a running ``policybank serve`` endpoint (from source or the container).

The server under test must be a fresh one serving the scripted policy (no ``--upstream``), because
the checks compare actions with the deterministic ScriptedPolicy stream, and because the last check
sends a contract violation that stops the server for good.  Start a new server for every run.

    python -m policybank serve --host 127.0.0.1 --port 8000 --replay 32 --chunk 4 &
    python docker/smoke_test.py --uri ws://127.0.0.1:8000 --http http://127.0.0.1:8000

Exit status 0 when every check passes, 1 (with the failing check named) otherwise.
"""
from __future__ import annotations

import argparse
import http.client
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import websockets

try:
    from policybank.serving.client import PolicyClient
except ImportError:  # a plain checkout without `pip install .`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from policybank.serving.client import PolicyClient

PROPRIO_DIM = 61
ACTION_DIM = 23
MAX_BATCH = 10
TASK = 5            # the first query binds the container to this task
OTHER_TASK = 6      # sending it later is a contract violation


class SmokeFailure(AssertionError):
    pass


def check(cond, msg: str) -> None:
    if not cond:
        raise SmokeFailure(msg)


def health(url: str, timeout: float = 3.0) -> str:
    """GET ``url``: the HTTP status as a string, or "refused" / "reset" / "timeout" / "error: ..."."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return str(r.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ConnectionRefusedError):
            return "refused"
        if isinstance(e.reason, ConnectionError):
            return "reset"
        if isinstance(e.reason, TimeoutError):
            return "timeout"
        return f"error: {e.reason}"
    except (ConnectionError, http.client.RemoteDisconnected):
        return "reset"                      # e.g. docker-proxy accepting with no backend behind it
    except TimeoutError:
        return "timeout"
    except (OSError, http.client.HTTPException) as e:
        return f"error: {type(e).__name__}: {e}"


def close_code(e: websockets.exceptions.ConnectionClosed) -> int | None:
    return e.rcvd.code if e.rcvd is not None else None


class Smoke:
    def __init__(self, a: argparse.Namespace):
        self.a = a
        self.uri = a.uri
        self.healthz = (a.http or a.uri.replace("ws://", "http://", 1).replace("wss://", "https://", 1))
        self.healthz = self.healthz.rstrip("/") + "/healthz"
        self.k, self.replay = a.chunk, a.replay
        self.first: PolicyClient | None = None
        self.second: PolicyClient | None = None

    # ------------------------------------------------------------------ helpers

    def client(self) -> PolicyClient:
        return PolicyClient(self.uri, chunk=self.k, timeout=self.a.recv_timeout)

    def expected(self, q: int) -> np.ndarray:
        """ScriptedPolicy chunk for query ``q`` since the last reset: value = plan + step / replay."""
        s = np.arange(q * self.k, (q + 1) * self.k)
        return (s // self.replay + (s % self.replay) / self.replay).astype(np.float32)

    def query(self, c: PolicyClient, n: int | None, q: int) -> dict:
        """Send one zero observation (``n`` envs, or unbatched when None) and validate the reply."""
        proprio = np.zeros((n, PROPRIO_DIM) if n else (PROPRIO_DIM,), np.float32)
        out = c.infer(proprio, task_id=TASK)
        check(isinstance(out, dict) and set(out) == {"action", "action_chunk", "server_timing"},
              f"reply keys {sorted(out) if isinstance(out, dict) else type(out).__name__}, "
              "expected action, action_chunk, server_timing")
        a, ch = np.asarray(out["action"]), np.asarray(out["action_chunk"])
        want_a = (n, ACTION_DIM) if n else (ACTION_DIM,)
        want_c = (n, self.k, ACTION_DIM) if n else (self.k, ACTION_DIM)
        check(a.shape == want_a, f"action shape {a.shape}, expected {want_a}")
        check(ch.shape == want_c, f"action_chunk shape {ch.shape}, expected {want_c}")
        check(a.dtype.kind == "f" and np.isfinite(a).all() and np.isfinite(ch).all(),
              f"nonfinite or nonfloat actions ({a.dtype})")
        check(np.array_equal(ch[..., 0, :], a), "action differs from action_chunk row zero")
        t = out["server_timing"]
        check(isinstance(t, dict) and isinstance(t.get("total_ms"), (int, float)) and t["total_ms"] >= 0,
              f"bad server_timing {t!r}")
        want = self.expected(q)
        got = ch.reshape(-1, self.k, ACTION_DIM)                 # (envs, K, A)
        if not np.allclose(got, want[None, :, None], rtol=0, atol=1e-6):
            raise SmokeFailure(f"query {q} since reset: chunk[0, :, 0] = {got[0, :, 0].tolist()}, "
                               f"expected scripted {want.tolist()}")
        return out

    # ------------------------------------------------------------------ checks

    def wait_healthy(self) -> str:
        deadline, last = time.monotonic() + self.a.startup_timeout, "no attempt"
        while time.monotonic() < deadline:
            last = health(self.healthz)
            if last == "200":
                return f"GET {self.healthz} -> 200"
            time.sleep(0.5)
        raise SmokeFailure(f"{self.healthz} not 200 within {self.a.startup_timeout:g} s (last: {last})")

    def metadata(self) -> str:
        self.first = self.client()
        m = self.first.metadata
        want = {"protocol": "b1k-2026", "action_dim": ACTION_DIM, "max_batch": MAX_BATCH,
                "action_chunk_size": self.k, "replay": self.replay, "failure_mode": "terminal"}
        if self.a.policy is not None:
            want["policy"] = self.a.policy
        check(isinstance(m, dict), f"metadata is {type(m).__name__}, expected a map")
        bad = {k: (m.get(k), v) for k, v in want.items() if m.get(k) != v}
        check(not bad, f"metadata mismatch (got, expected): {bad}")
        return f"policy={m.get('policy')!r} chunk={m['action_chunk_size']} replay={m['replay']}"

    def batch10(self) -> str:
        self.query(self.first, MAX_BATCH, 0)
        return f"action ({MAX_BATCH}, {ACTION_DIM}), action_chunk ({MAX_BATCH}, {self.k}, {ACTION_DIM})"

    def plan_boundary(self) -> str:
        per_plan = self.replay // self.k
        for q in range(1, per_plan + 1):                         # query per_plan + 1 forces a re-plan
            out = self.query(self.first, MAX_BATCH, q)
        first = float(np.asarray(out["action"])[0, 0])
        check(first == 1.0, f"query {per_plan + 1} should open plan 1 (action 1.0), got {first}")
        return f"{per_plan} more queries; query {per_plan + 1} starts native plan 1 (action {first:g})"

    def reset(self) -> str:
        self.first.reset()
        try:
            extra = self.first.ws.recv(timeout=self.a.reset_wait)
        except TimeoutError:
            pass
        else:
            raise SmokeFailure(f"server replied to a reset ({len(extra)} bytes); the protocol sends nothing")
        out = self.query(self.first, None, 0)                    # a new batch shape is allowed after reset
        return f"no reply within {self.a.reset_wait:g} s; unbatched query restarts at {out['action'][0]:g}"

    def second_refused(self) -> str:
        try:
            self.second = self.client()
        except websockets.exceptions.ConnectionClosed as e:
            code = close_code(e)
            check(code == 1013, f"second connection closed with {code}, expected 1013")
            reason = e.rcvd.reason if e.rcvd is not None else ""
        else:
            raise SmokeFailure("a second concurrent connection was accepted (metadata received)")
        out = self.query(self.first, None, 1)                    # the first session is unaffected
        return f"1013 {reason!r}; first session still answers (action {out['action'][0]:g})"

    def clean_close(self) -> str:
        self.first.close()
        code = self.first.ws.close_code
        check(code == 1000, f"clean close ended with code {code}, expected 1000")
        status = health(self.healthz)
        check(status == "200", f"/healthz is {status} after a clean disconnect; expected 200")
        return "close code 1000, /healthz still 200"

    def reconnect(self) -> str:
        deadline = time.monotonic() + 3.0
        while True:
            try:
                self.first = self.client()
                break
            except websockets.exceptions.ConnectionClosed as e:
                # The previous session's teardown can trail the client's close by a moment.
                if close_code(e) != 1013 or time.monotonic() > deadline:
                    raise SmokeFailure(f"reconnect refused with close code {close_code(e)}") from None
                time.sleep(0.1)
        check(self.first.metadata.get("protocol") == "b1k-2026", "reconnect: bad metadata")
        self.query(self.first, 3, 0)                             # fresh session: plan restarts at 0
        return "new session, metadata ok, batch-3 query starts a fresh plan"

    def invalid_frame(self) -> str:
        proprio = np.zeros((3, PROPRIO_DIM), np.float32)
        try:
            out = self.first.infer(proprio, task_id=OTHER_TASK)
        except websockets.exceptions.ConnectionClosed as e:
            code = close_code(e)
            check(code == 1011, f"task change closed the connection with {code}, expected 1011")
            return f"task {TASK} -> {OTHER_TASK} closed with 1011 {e.rcvd.reason!r}"
        raise SmokeFailure(f"server answered a task change with {sorted(out) if isinstance(out, dict) else out!r}")

    def health_red(self) -> str:
        deadline, status = time.monotonic() + self.a.stop_timeout, "no attempt"
        while time.monotonic() < deadline:
            status = health(self.healthz)
            if status in ("503", "refused", "reset"):
                return f"GET /healthz -> {status}"
            time.sleep(0.2)
        raise SmokeFailure(f"/healthz still {status} {self.a.stop_timeout:g} s after the terminal failure")

    def run(self) -> int:
        steps = [
            ("health endpoint reports 200", self.wait_healthy),
            ("metadata map on connect", self.metadata),
            ("batch-10 query shapes", self.batch10),
            ("queries across a native plan boundary", self.plan_boundary),
            ("reset gets no reply, next query starts a fresh plan", self.reset),
            ("second concurrent connection refused with 1013", self.second_refused),
            ("clean close", self.clean_close),
            ("reconnect after a clean close", self.reconnect),
            ("invalid frame (task change) closes with 1011", self.invalid_frame),
            ("health no longer 200 after the terminal failure", self.health_red),
        ]
        t0 = time.monotonic()
        print(f"smoke test: {self.uri} (health {self.healthz})", flush=True)
        for i, (name, fn) in enumerate(steps, 1):
            try:
                detail = fn()
            except SmokeFailure as e:
                print(f"[FAIL] {i:2d}. {name}: {e}", flush=True)
                return 1
            except Exception as e:  # noqa: BLE001 - any surprise is a failed check, reported with its step
                print(f"[FAIL] {i:2d}. {name}: unexpected {type(e).__name__}: {e}", flush=True)
                return 1
            print(f"[ ok ] {i:2d}. {name}: {detail}", flush=True)
        print(f"PASS: {len(steps)} checks in {time.monotonic() - t0:.1f} s", flush=True)
        return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--uri", default="ws://127.0.0.1:8000", help="websocket endpoint of the server")
    p.add_argument("--http", help="HTTP base URL for /healthz (default: derived from --uri)")
    p.add_argument("--chunk", type=int, default=4, help="the server's --chunk (must be > 1)")
    p.add_argument("--replay", type=int, default=32, help="the server's --replay")
    p.add_argument("--policy", default="scripted", help="expected policy name in the metadata ('' skips)")
    p.add_argument("--startup-timeout", type=float, default=60.0, help="seconds to wait for /healthz 200")
    p.add_argument("--stop-timeout", type=float, default=10.0, help="seconds for /healthz to leave 200 at the end")
    p.add_argument("--recv-timeout", type=float, default=30.0, help="seconds per websocket open/receive")
    p.add_argument("--reset-wait", type=float, default=0.5, help="seconds to listen for a (forbidden) reset reply")
    a = p.parse_args(argv)
    if a.chunk < 2 or a.replay % a.chunk:
        p.error("--chunk must be > 1 and divide --replay")
    a.policy = a.policy or None
    return Smoke(a).run()


if __name__ == "__main__":
    sys.exit(main())
