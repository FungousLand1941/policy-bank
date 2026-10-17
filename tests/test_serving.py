import asyncio
import threading

import msgpack
import numpy as np
import pytest

from policybank.serving import (CHUNK_KEY, ChunkExecutor, ContractError, ContractSpec, ScriptedPolicy,
                                SessionContract, pack, unpack)
from policybank.serving.server import PolicyServer


def obs(n=1, task=3, k=4, d=61):
    p = np.zeros((n, d) if n > 1 else (d,), dtype=np.float32)
    return {"robot_r1::proprio": p, "task_id": np.full((n,), task, dtype=np.int64),
            CHUNK_KEY: np.asarray(k, dtype=np.int64)}


# ------------------------------------------------------------------ codec

def test_codec_roundtrip_preserves_dtype_and_shape():
    x = {"a": np.arange(6, dtype=np.float32).reshape(2, 3), "b": np.int64(4), "c": "text"}
    y = unpack(pack(x))
    assert y["a"].dtype == np.float32 and y["a"].shape == (2, 3)
    np.testing.assert_array_equal(x["a"], y["a"])
    assert y["b"] == 4 and y["c"] == "text"


def test_codec_rejects_object_dtype_and_bad_lengths():
    with pytest.raises(TypeError):
        pack({"a": np.array([object()], dtype=object)})
    bad = msgpack.packb({"x": {b"__ndarray__": True, b"data": b"\x00" * 3, b"dtype": "<f4", b"shape": [1]}},
                        use_bin_type=True)
    with pytest.raises(ValueError, match="length"):
        unpack(bad)
    bad = msgpack.packb({"x": {b"__ndarray__": True, b"data": b"", b"dtype": "|O", b"shape": [0]}},
                        use_bin_type=True)
    with pytest.raises(ValueError):
        unpack(bad)


def test_codec_accepts_text_keys_from_other_clients():
    frame = msgpack.packb({"x": {"__ndarray__": True, "data": np.float32(1).tobytes(), "dtype": "<f4",
                                 "shape": [1]}}, use_bin_type=True)
    assert unpack(frame)["x"][0] == 1.0


# ------------------------------------------------------------------ contract

def test_contract_binds_one_task_and_one_batch_shape():
    c = SessionContract(ContractSpec())
    q = c.request(pack(obs(n=10)))
    assert (q.n, q.batched, q.task_id) == (10, True, 3)
    with pytest.raises(ContractError, match="batch shape changed"):
        c.request(pack(obs(n=2)))
    assert c.request(pack({"reset": True})) is None
    c.request(pack(obs(n=2)))                          # new shape allowed after reset
    with pytest.raises(ContractError, match="one task per container"):
        c.request(pack(obs(n=2, task=4)))


@pytest.mark.parametrize("frame,match", [
    (b"\xc1", "undecodable"),
    (pack({"reset": True, "x": 1}), "reset must be"),
    (pack({"task_id": np.array([1])}), "proprio"),
    (pack({**obs(), "robot_r1::proprio": np.full(61, np.nan, np.float32)}), "nonfinite"),
    (pack({**obs(), "robot_r1::proprio": np.zeros((11, 61), np.float32)}), "proprio must be"),
    (pack(obs(k=8)), "global chunk"),
    (pack({**obs(n=2), "task_id": np.array([1, 2])}), "mixed"),
])
def test_contract_rejects_bad_frames(frame, match):
    with pytest.raises(ContractError, match=match):
        SessionContract(ContractSpec()).request(frame)


def test_contract_validates_actions():
    c = SessionContract(ContractSpec())
    q = c.request(pack(obs()))
    chunk = np.zeros((4, 23), np.float32)
    out = c.reply(chunk[0], chunk, q)
    assert out["action"].shape == (23,)
    with pytest.raises(ContractError, match="invalid action"):
        c.reply(np.full(23, np.inf, np.float32), chunk, q)
    with pytest.raises(ContractError, match="row zero"):
        c.reply(np.ones(23, np.float32), chunk, q)


# ------------------------------------------------------------------ executor

@pytest.mark.parametrize("replay", [32, 20])
def test_chunked_stream_equals_native_receding_horizon(replay):
    native = ScriptedPolicy(horizon=replay, action_dim=2)
    expected = np.concatenate([native.plan({}, 1)[0] for _ in range(3)])   # three native plans
    ex = ChunkExecutor(ScriptedPolicy(horizon=replay, action_dim=2), chunk=4)
    got = np.concatenate([ex.step({}, 1)[0] for _ in range(3 * replay // 4)])
    np.testing.assert_array_equal(got, expected)
    assert ex.plans == 3


def test_executor_reset_replans_and_rejects_bad_chunk():
    ex = ChunkExecutor(ScriptedPolicy(horizon=32, action_dim=2), chunk=4)
    ex.step({}, 1)
    ex.reset()
    assert ex.step({}, 1)[0, 0, 0] == 0.0   # plan counter restarted
    with pytest.raises(ValueError, match="divide"):
        ChunkExecutor(ScriptedPolicy(horizon=20), chunk=8)


# ------------------------------------------------------------------ server (integration)

class Running:
    def __init__(self, policy=None, **kw):
        self.server = PolicyServer(policy or ScriptedPolicy(horizon=32), ContractSpec(chunk=4), **kw)
        self.ready = threading.Event()
        self.code = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        async def main():
            ev = asyncio.Event()
            task = asyncio.create_task(self.server.serve("127.0.0.1", 0, ready=ev))
            await ev.wait()
            self.ready.set()
            self.code = await task
        asyncio.run(main())

    def __enter__(self):
        self.thread.start()
        assert self.ready.wait(10)
        return f"ws://127.0.0.1:{self.server.port}"

    def __exit__(self, *exc):
        self.server.shutdown()
        self.thread.join(10)
        assert not self.thread.is_alive()


def test_server_serves_batches_and_resets():
    from policybank.serving.client import PolicyClient
    r = Running()
    with r as uri, PolicyClient(uri) as c:
        assert c.metadata["action_chunk_size"] == 4 and c.metadata["failure_mode"] == "terminal"
        out = c.infer(np.zeros((10, 61), np.float32), task_id=5)
        assert out["action"].shape == (10, 23) and out["action_chunk"].shape == (10, 4, 23)
        c.reset()
        out = c.infer(np.zeros(61, np.float32), task_id=5)
        assert out["action"].shape == (23,) and out["action"][0] == 0.0
    assert r.code == 0 and not r.server.failed.is_set()


def test_server_fails_stop_on_contract_violation():
    import websockets
    from policybank.serving.client import PolicyClient
    with Running() as uri:
        c = PolicyClient(uri)
        c.infer(np.zeros(61, np.float32), task_id=5)
        with pytest.raises(websockets.ConnectionClosedError) as e:
            c.infer(np.zeros(61, np.float32), task_id=6)       # task change is terminal
        assert e.value.rcvd.code == 1011


def test_server_refuses_a_second_session():
    import websockets
    from policybank.serving.client import PolicyClient
    with Running() as uri:
        first = PolicyClient(uri)
        with pytest.raises(websockets.ConnectionClosed):
            second = PolicyClient(uri)
            second.infer(np.zeros(61, np.float32), task_id=1)
        first.close()


class Exploding(ScriptedPolicy):
    def plan(self, obs, n):
        return np.full((n, self.horizon, self.action_dim), np.nan, np.float32)


def test_server_never_substitutes_actions_for_nonfinite_output():
    import websockets
    from policybank.serving.client import PolicyClient
    r = Running(Exploding(horizon=32))
    with r as uri:
        c = PolicyClient(uri)
        with pytest.raises(websockets.ConnectionClosedError):
            c.infer(np.zeros(61, np.float32), task_id=1)
    assert r.server.failed.is_set() and "nonfinite" in r.server.failure
