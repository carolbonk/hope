"""Near-duplicate detection over normalized text with MinHash LSH (blueprint 2.2 A1).
Exact dedup on `(source_system, source_id)` is the UNIQUE key in `opportunities`."""

from __future__ import annotations

import re

from datasketch import MinHash, MinHashLSH

WORD = re.compile(r"[a-z0-9]+")
SCHEME = "affine32"  # uint32 hash values, stored as bigint in opportunity_minhash


def shingles(text: str, size: int = 5) -> set[str]:
    words = WORD.findall(text.lower())
    if len(words) <= size:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


class NearDuplicateIndex:
    def __init__(self, threshold: float = 0.85, num_perm: int = 128) -> None:
        self.threshold = threshold
        self.num_perm = num_perm
        self._lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self._sigs: dict[str, MinHash] = {}

    def signature(self, text: str) -> MinHash:
        sig = MinHash(num_perm=self.num_perm, scheme=SCHEME)
        for shingle in shingles(text):
            sig.update(shingle.encode())
        return sig

    def add(self, key: str, text: str) -> list[int]:
        return self.add_signature(key, self.signature(text))

    def add_signature(self, key: str, sig: MinHash | list[int]) -> list[int]:
        if not isinstance(sig, MinHash):
            sig = MinHash(num_perm=self.num_perm, hashvalues=sig, scheme=SCHEME)
        if key in self._sigs:
            self._lsh.remove(key)
        self._lsh.insert(key, sig)
        self._sigs[key] = sig
        return [int(v) for v in sig.hashvalues]

    def similar(self, text: str, exclude: str | None = None) -> list[tuple[str, float]]:
        sig = self.signature(text)
        matches = [
            (key, float(sig.jaccard(self._sigs[key])))
            for key in self._lsh.query(sig)
            if key != exclude
        ]
        return sorted(
            [m for m in matches if m[1] >= self.threshold], key=lambda m: m[1], reverse=True
        )
