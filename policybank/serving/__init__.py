"""Serving layer: wire codec, session contract, chunked execution and the fail-stop server.

Real checkpoints plug in through the :class:`~policybank.serving.executor.Policy` protocol
(``plan(obs, n) -> (n, horizon, action_dim)`` and ``reset()``); the package ships only a
deterministic :class:`~policybank.serving.executor.ScriptedPolicy` for tests.
"""
from .codec import pack, unpack
from .contract import CHUNK_KEY, ContractError, ContractSpec, SessionContract
from .executor import ChunkExecutor, Policy, ScriptedPolicy

__all__ = ["pack", "unpack", "CHUNK_KEY", "ContractError", "ContractSpec", "SessionContract",
           "ChunkExecutor", "Policy", "ScriptedPolicy"]
