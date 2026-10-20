from __future__ import annotations

import hashlib
import math
import re
import struct
from typing import Protocol, runtime_checkable


_WORD_REGEX = re.compile(r"[A-Za-z0-9_./{}-]+")


@runtime_checkable
class Embedder(Protocol):
    dimension: int

    def embed(self, text: str) -> list[float]:
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...


def pack_vector(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def unpack_vector(data: bytes) -> list[float]:
    count = len(data) // 4
    return list(struct.unpack(f"{count}f", data))


def cosine_similarity(vec_a_bytes: bytes, vec_b_bytes: bytes) -> float:
    """Compute dot product of two L2-normalized float32 vectors packed in bytes."""
    dim = len(vec_a_bytes) // 4
    floats_a = struct.unpack(f"{dim}f", vec_a_bytes)
    floats_b = struct.unpack(f"{dim}f", vec_b_bytes)
    return sum(a * b for a, b in zip(floats_a, floats_b))


class HashingEmbedder:
    """Lightweight, zero-dependency embedder using hashed n-grams and L2 normalization."""

    def __init__(self, dimension: int = 128):
        self.dimension = dimension

    def _hash_token(self, token: str) -> tuple[int, int]:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % self.dimension
        sign = 1 if (digest[4] % 2 == 0) else -1
        return idx, sign

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        tokens = _WORD_REGEX.findall(text.lower())
        if not tokens:
            return vec

        for token in tokens:
            idx, sign = self._hash_token(token)
            vec[idx] += float(sign)
            if len(token) >= 3:
                for i in range(len(token) - 2):
                    sub_idx, sub_sign = self._hash_token(token[i : i + 3])
                    vec[sub_idx] += float(sub_sign)

        norm = math.sqrt(sum(val * val for val in vec))
        if norm > 0.0:
            vec = [val / norm for val in vec]
        return vec

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
