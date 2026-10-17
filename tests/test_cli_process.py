"""End-to-end tests of ``python -m policybank`` in real subprocesses.

Each test runs the CLI with ``sys.executable`` from the repository root, with bounded timeouts,
and always kills a still-running child in ``finally``.  Server tests bind an ephemeral port.
"""
import contextlib
import csv
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
Q_RELEASED = "0.156054"


def _env():
    env = {k: v for k, v in os.environ.items() if k != "POLICYBANK_DATA"}   # use the repo's data/
    env["PYTHONUNBUFFERED"] = "1"
    return env


def run_cli(*args, timeout=60):
    return subprocess.run([sys.executable, "-m", "policybank", *args], cwd=ROOT, env=_env(),
                          capture_output=True, text=True, timeout=timeout)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def health(port, timeout=1.0):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return None


@contextlib.contextmanager
def cli_server(tmp_path, *, startup_s=30.0):
    """Start ``policybank serve`` on a free port; yield (proc, port, log_path); always kill it."""
    log_path = tmp_path / "serve.log"
    proc = log = None
    try:
        for _attempt in range(3):                       # a freed ephemeral port can be grabbed in between
            port = free_port()
            log = open(log_path, "wb")                  # closed below or in finally
            proc = subprocess.Popen(
                [sys.executable, "-m", "policybank", "serve", "--host", "127.0.0.1", "--port", str(port),
                 "--replay", "32", "--chunk", "4"],
                cwd=ROOT, env=_env(), stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + startup_s
            while time.monotonic() < deadline and proc.poll() is None:
                if health(port) == 200:
                    break
                time.sleep(0.05)
            if proc.poll() is None and health(port) == 200:
                break
            proc.kill()
            proc.wait(10)
            log.close()
        else:
            pytest.fail(f"server never became healthy:\n{log_path.read_text(errors='replace')}")
        yield proc, port, log_path
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(10)
        if log is not None:
            log.close()


# ------------------------------------------------------------------ score / route

def test_score_prints_the_released_q():
    r = run_cli("score", "--boot", "200")
    assert r.returncode == 0, r.stderr
    assert f"Q = {Q_RELEASED}" in r.stdout
    assert "95% CI" in r.stdout and "200 resamples" in r.stdout
    assert "episodes = 1000  successes = 37" in r.stdout


def test_route_with_an_empty_data_dir_fails_with_a_clear_message(tmp_path):
    r = run_cli("--data", str(tmp_path), "route")
    assert r.returncode != 0
    assert r.stdout == ""
    last = [line for line in r.stderr.splitlines() if line.strip()][-1]
    assert last.startswith("FileNotFoundError") and "route.json" in last, r.stderr
    assert "POLICYBANK_DATA" in last and "--data" in last, r.stderr


# ------------------------------------------------------------------ serve

def test_serve_answers_a_batch_then_fails_stop_on_a_task_change(tmp_path):
    websockets = pytest.importorskip("websockets")
    from policybank.serving.client import PolicyClient

    with cli_server(tmp_path) as (proc, port, log_path):
        c = PolicyClient(f"ws://127.0.0.1:{port}", chunk=4, timeout=15)
        try:
            assert c.metadata["action_chunk_size"] == 4 and c.metadata["replay"] == 32
            assert c.metadata["failure_mode"] == "terminal"
            out = c.infer(np.zeros((3, 61), np.float32), task_id=7)
            assert out["action"].shape == (3, 23) and out["action_chunk"].shape == (3, 4, 23)
            # ScriptedPolicy's first plan is arange(32) / 32: the first chunk is its first four steps.
            np.testing.assert_array_equal(out["action_chunk"][:, :, 0], np.tile(np.arange(4) / 32, (3, 1)))
            np.testing.assert_array_equal(out["action"], out["action_chunk"][:, 0])
            assert health(port) == 200
            with pytest.raises(websockets.ConnectionClosedError) as e:
                c.infer(np.zeros((3, 61), np.float32), task_id=8)          # one task per container
            assert e.value.rcvd is not None and e.value.rcvd.code == 1011
        finally:
            with contextlib.suppress(Exception):
                c.close()
        t0 = time.monotonic()
        code = proc.wait(timeout=10)                                       # os._exit path, no hang
        assert time.monotonic() - t0 < 5
        assert code != 0
        log = log_path.read_text(errors="replace")
        assert "terminal failure" in log and "one task per container" in log, log


def test_serve_shuts_down_cleanly_on_terminate(tmp_path):
    pytest.importorskip("websockets")
    from policybank.serving.client import PolicyClient

    with cli_server(tmp_path) as (proc, port, log_path):
        with PolicyClient(f"ws://127.0.0.1:{port}", chunk=4, timeout=15) as c:
            assert c.infer(np.zeros(61, np.float32), task_id=3)["action"].shape == (23,)
        time.sleep(0.2)
        assert health(port) == 200                     # a clean disconnect is not a policy failure
        assert proc.poll() is None
        proc.terminate()
        code = proc.wait(timeout=10)
        log = log_path.read_text(errors="replace")
    assert "terminal failure" not in log, log
    if sys.platform == "win32":
        pytest.skip("Popen.terminate() is TerminateProcess on Windows (forced exit code), not SIGTERM; "
                    "the clean exit code 0 is asserted on POSIX only")
    assert code == 0, log


# ------------------------------------------------------------------ verify

def _write_metrics_folder(root: Path) -> list[Path]:
    """One evaluator metrics file per row of the released ledger (1,000 files)."""
    paths = []
    with (ROOT / "data" / "official_episodes.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            doc = {"task": r["task"], "instance_id": int(r["instance"]), "rollout_id": 0,
                   "steps": int(r["steps"]), "success": r["success"] == "1", "q_score": {"final": float(r["q"])},
                   "time": {"normalized_time": float(r["normalized_time"])}}
            d = root / r["task"]
            d.mkdir(exist_ok=True)
            p = d / f"{r['task']}_{r['instance']}_0.json"
            p.write_text(json.dumps(doc), encoding="utf-8")
            paths.append(p)
    return paths


@pytest.fixture(scope="module", autouse=True)
def metrics_folder(tmp_path_factory):
    """Build the synthetic folder in a background thread as soon as this module starts.

    The first open of each freshly written file is slow under real-time antivirus scanning (about
    4 s for 1,000 files on Windows); writing and reading the folder once here overlaps that cost
    with the subprocess-bound tests above instead of adding it to the verify test.
    """
    root = tmp_path_factory.mktemp("metrics")
    box = {}

    def prepare():
        try:
            paths = _write_metrics_folder(root)
            for p in paths:
                p.read_bytes()
            box["paths"] = paths
        except BaseException as e:  # noqa: BLE001 - re-raised in the test thread
            box["error"] = e

    worker = threading.Thread(target=prepare, daemon=True)
    worker.start()

    def get():
        worker.join(120)
        assert not worker.is_alive(), "writing the synthetic metrics folder timed out"
        if "error" in box:
            raise box["error"]
        return root, box["paths"]

    yield get
    worker.join(120)


def test_verify_reports_complete_coverage_and_q(metrics_folder):
    root, paths = metrics_folder()
    assert len(paths) == 1000
    r = run_cli("verify", str(root))
    assert r.returncode == 0, r.stderr
    assert "1000 metrics files, coverage complete" in r.stdout and f"Q = {Q_RELEASED}" in r.stdout

    paths[0].unlink()
    r = run_cli("verify", str(root))
    assert r.returncode != 0
    assert "coverage complete" not in r.stdout
    assert "AuditError" in r.stderr and "missing" in r.stderr, r.stderr
