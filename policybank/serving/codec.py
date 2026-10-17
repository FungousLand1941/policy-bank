"""Bounded msgpack + numpy codec, wire-compatible with the OpenPI / BEHAVIOR policy client.

Arrays travel as ``{"__ndarray__": True, "data": bytes, "dtype": str, "shape": list}``.
Decoding refuses object dtypes, oversized frames, inconsistent byte lengths and extension
types, so a malformed frame becomes a clean error instead of an allocation or code path the
server did not intend.
"""
from __future__ import annotations

import math

import msgpack
import numpy as np

MAX_BYTES = 128 * 1024 * 1024
_KINDS = "biuf"


def _encode(obj):
    if isinstance(obj, np.ndarray):
        if obj.dtype.kind not in _KINDS:
            raise TypeError(f"unsupported array dtype {obj.dtype}")
        a = np.ascontiguousarray(obj)
        return {b"__ndarray__": True, b"data": a.tobytes(), b"dtype": a.dtype.str, b"shape": list(a.shape)}
    if isinstance(obj, np.generic):
        if obj.dtype.kind not in _KINDS:
            raise TypeError(f"unsupported scalar dtype {obj.dtype}")
        return {b"__npgeneric__": True, b"data": obj.item(), b"dtype": obj.dtype.str}
    raise TypeError(f"cannot encode {type(obj).__name__}")


def _dtype(spec) -> np.dtype:
    if isinstance(spec, bytes):
        spec = spec.decode("ascii")
    if not isinstance(spec, str) or len(spec) > 8:
        raise ValueError("invalid dtype")
    return np.dtype(spec)


def _decode(obj):
    # OpenPI writes byte-string keys; accept text keys from other clients too.
    if "__ndarray__" in obj or "__npgeneric__" in obj:
        obj = {k.encode() if isinstance(k, str) else k: v for k, v in obj.items()}
    if b"__ndarray__" in obj:
        if obj[b"__ndarray__"] is not True:
            raise ValueError("invalid ndarray marker")
        dtype = _dtype(obj[b"dtype"])
        if dtype.kind not in _KINDS or dtype.itemsize > 8:
            raise ValueError("unsupported array dtype")
        shape = obj[b"shape"]
        if not isinstance(shape, (list, tuple)) or len(shape) > 8 or \
                any(type(x) is not int or x < 0 for x in shape):
            raise ValueError("invalid array shape")
        size = math.prod(shape) * dtype.itemsize
        data = obj[b"data"]
        if size > MAX_BYTES or not isinstance(data, bytes) or len(data) != size:
            raise ValueError("array byte length mismatch or too large")
        return np.frombuffer(data, dtype=dtype).reshape(shape)
    if b"__npgeneric__" in obj:
        dtype = _dtype(obj[b"dtype"])
        if dtype.kind not in _KINDS or dtype.itemsize > 8:
            raise ValueError("unsupported scalar dtype")
        return dtype.type(obj[b"data"])
    return obj


def pack(obj) -> bytes:
    return msgpack.packb(obj, default=_encode, use_bin_type=True)


def unpack(data: bytes):
    if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_BYTES:
        raise ValueError("oversized or non-binary frame")
    return msgpack.unpackb(bytes(data), object_hook=_decode, strict_map_key=False, raw=False,
                           max_array_len=1_000_000, max_map_len=100_000, max_str_len=MAX_BYTES,
                           max_bin_len=MAX_BYTES, max_ext_len=0)
