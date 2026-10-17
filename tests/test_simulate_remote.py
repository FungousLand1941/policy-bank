import asyncio
import random
import threading

import numpy as np
import pytest

from policybank.data import Episode
from policybank.serving.codec import pack, unpack
from policybank.simulate import RULES, Setup, draw_ledger, fit_beta_concentration, run_study


def ep(t, i, p, q):
    return Episode(task_id=t, task=f"t{t}", instance=i, policy=p, q=q, success=q >= 0.999)


def test_beta_concentration_recovers_simulated_kappa():
    rng = random.Random(0)
    eps = []
    for t in range(200):
        m = rng.uniform(0.05, 0.6)
        for i in range(10):
            eps.append(ep(t, 301 + i, "p", rng.betavariate(m * 2.0, (1 - m) * 2.0)))
    assert fit_beta_concentration(eps) == pytest.approx(2.0, rel=0.2)


def _toy():
    # Reference "r" is weak everywhere; "g" is a better generalist; "s" a specialist on task 3.
    rows = []
    for t in range(1, 9):
        for i in (311, 312):
            rows.append(ep(t, i, "r", 0.05))
            rows.append(ep(t, i, "g", 0.30))
    rows += [ep(3, 311, "s", 0.9), ep(3, 312, "s", 0.8)]
    return rows, Setup.from_ledger(rows, list(range(1, 9)), "r", ["r", "g"], ["s"])


def test_setup_scopes_specialists_to_their_tasks():
    _, setup = _toy()
    assert setup.candidates[3] == ["r", "g", "s"]
    assert setup.candidates[1] == ["r", "g"]


def test_study_orders_rules_sensibly_and_is_deterministic():
    rows, setup = _toy()
    a = run_study(setup, rows, kappa=1.5, sims=30, seed=3)
    b = run_study(setup, rows, kappa=1.5, sims=30, seed=3)
    assert a["strict rules (ours)"]["true"] == b["strict rules (ours)"]["true"]
    assert a["oracle"]["true"] >= a["strict rules (ours)"]["true"] >= a["reference only"]["true"]
    assert a["oracle"]["regret"] == 0
    # Naive selection by raw development mean overclaims; the posterior does not (much).
    assert a["best dev mean"]["optimism"] > a["best posterior"]["optimism"]
    assert set(a) == set(RULES)


def test_replicated_ledger_keeps_cells_and_offsets_instances():
    rows, setup = _toy()
    world = {k: 0.5 for k in ((t, p) for t, ps in setup.candidates.items() for p in ps)}
    led = draw_ledger(setup, world, 1.5, random.Random(0), replicate=3)
    assert len(led) == 3 * len(setup.template)
    assert {e.instance for e in led} >= {311, 411, 511}


# ------------------------------------------------------------------ OpenPI remote adapter

class FakeUpstream:
    """An OpenPI-style server: metadata on connect, one obs -> {"actions": (H, A)} per request."""

    def __init__(self, horizon=50, dim=23, fail_after=None):
        self.horizon, self.dim, self.fail_after, self.calls = horizon, dim, fail_after, 0
        self.resets = 0
        self.seen = []
        self.ready = threading.Event()
        self.thread = threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True)

    async def _main(self):
        from websockets.asyncio.server import serve

        async def handler(ws):
            await ws.send(pack({"server": "fake-openpi"}))
            async for msg in ws:
                obs = unpack(msg)
                self.seen.append(obs)
                if obs.get("reset") is True:
                    self.resets += 1
                    continue
                self.calls += 1
                if self.fail_after is not None and self.calls > self.fail_after:
                    await ws.send("Traceback: boom")
                    continue
                base = float(np.asarray(obs["robot_r1::proprio"]).reshape(-1)[0])
                acts = base + np.arange(self.horizon, dtype=np.float32)[:, None] / 100
                await ws.send(pack({"actions": np.repeat(acts, self.dim, axis=1)}))

        self.stop = asyncio.Event()
        async with serve(handler, "127.0.0.1", 0, compression=None, max_size=None) as srv:
            self.port = srv.sockets[0].getsockname()[1]
            self.ready.set()
            await self.stop.wait()

    def __enter__(self):
        self.thread.start()
        assert self.ready.wait(10)
        return f"ws://127.0.0.1:{self.port}"

    def __exit__(self, *exc):
        self.thread.join(0.1)


def test_remote_policy_splits_batches_and_truncates_to_replay():
    from policybank.serving.remote import OpenPIRemotePolicy
    with FakeUpstream(horizon=50) as uri:
        pol = OpenPIRemotePolicy(uri, horizon=32)
        assert pol.metadata == {"server": "fake-openpi"}
        prop = np.stack([np.full(61, 1.0, np.float32), np.full(61, 2.0, np.float32)])
        plan = pol.plan({"robot_r1::proprio": prop, "task_id": np.array([4, 4]), "action_chunk_size": 4}, 2)
        assert plan.shape == (2, 32, 23)
        assert plan[0, 0, 0] == pytest.approx(1.0) and plan[1, 0, 0] == pytest.approx(2.0)
        pol.close()


def test_remote_upstream_error_is_terminal_through_the_server():
    import websockets

    from policybank.serving.client import PolicyClient
    from policybank.serving.remote import OpenPIRemotePolicy
    from tests.test_serving import Running

    with FakeUpstream(horizon=32, fail_after=1) as up:
        r = Running(OpenPIRemotePolicy(up, horizon=32))
        with r as uri:
            c = PolicyClient(uri)
            first = c.infer(np.full(61, 3.0, np.float32), task_id=2)
            np.testing.assert_allclose(first["action_chunk"][:, 0], 3.0 + np.arange(4) / 100, rtol=1e-6)
            for _ in range(7):                                  # rest of the first native plan
                c.infer(np.full(61, 3.0, np.float32), task_id=2)
            with pytest.raises(websockets.ConnectionClosedError):
                c.infer(np.full(61, 3.0, np.float32), task_id=2)  # forces a re-plan -> upstream error
        assert r.server.failed.is_set() and "upstream policy error" in r.server.failure


def test_reset_is_forwarded_only_when_enabled():
    import time

    from policybank.serving.remote import OpenPIRemotePolicy
    obs = {"robot_r1::proprio": np.zeros(61, np.float32), "task_id": np.array([3])}
    up = FakeUpstream(horizon=32)
    with up as uri:
        quiet = OpenPIRemotePolicy(uri, horizon=32)
        quiet.reset()
        time.sleep(0.2)
        assert up.resets == 0                  # default: nothing is sent upstream
        loud = OpenPIRemotePolicy(uri, horizon=32, forward_reset=True)
        loud.reset()
        plan = loud.plan(obs, 1)               # the reset frame got no reply; the next plan still works
        assert plan.shape == (1, 32, 23)
        assert up.resets == 1
        quiet.close()
        loud.close()
