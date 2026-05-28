"""Semantic fingerprinting with MinHash and LSH."""

import hashlib
import re
from dataclasses import dataclass

from datasketch import MinHash, MinHashLSH

from app.utils.helpers import content_hash, fingerprint


@dataclass
class FingerprintResult:
    fingerprint: str
    content_hash: str
    minhash_signature: list[int]
    similarity_key: str


class FingerprintService:
    NUM_PERM = 128
    _lsh: MinHashLSH | None = None
    _store: dict[str, FingerprintResult] = {}

    def __init__(self, threshold: float = 0.85) -> None:
        self.threshold = threshold
        if FingerprintService._lsh is None:
            FingerprintService._lsh = MinHashLSH(threshold=threshold, num_perm=self.NUM_PERM)

    def _tokenize(self, text: str) -> set[str]:
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        words = set(normalized.split())
        shingles: set[str] = set()
        for i in range(len(normalized) - 4):
            shingles.add(normalized[i:i + 5])
        return words | shingles

    def _create_minhash(self, text: str) -> MinHash:
        mh = MinHash(num_perm=self.NUM_PERM)
        for token in self._tokenize(text):
            mh.update(token.encode("utf-8"))
        return mh

    def _index_fingerprint(self, fp: str, mh: MinHash) -> None:
        if self._lsh is None:
            return
        try:
            self._lsh.insert(fp, mh)
        except ValueError:
            # datasketch raises when the same key is inserted twice (e.g. repeat requests)
            pass

    def fingerprint(self, text: str) -> FingerprintResult:
        fp = fingerprint(text)
        existing = self._store.get(fp)
        if existing is not None:
            return existing

        ch = content_hash(text)
        mh = self._create_minhash(text)
        sig = mh.hashvalues.tolist()

        result = FingerprintResult(
            fingerprint=fp,
            content_hash=ch,
            minhash_signature=sig,
            similarity_key=fp,
        )
        self._store[fp] = result
        self._index_fingerprint(fp, mh)
        return result

    def find_similar(self, text: str) -> list[tuple[str, float]]:
        mh = self._create_minhash(text)
        if self._lsh is None:
            return []

        candidates = self._lsh.query(mh)
        results: list[tuple[str, float]] = []

        for key in candidates:
            stored = self._store.get(key)
            if stored:
                stored_mh = MinHash(num_perm=self.NUM_PERM)
                stored_mh.hashvalues = stored.minhash_signature  # type: ignore[assignment]
                similarity = mh.jaccard(stored_mh)
                results.append((key, similarity))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def fingerprint_messages(self, messages: list[dict]) -> str:
        combined = "|".join(
            f"{m.get('role')}:{str(m.get('content', ''))[:500]}"
            for m in messages
        )
        return self.fingerprint(combined).fingerprint

    def is_near_duplicate(self, text_a: str, text_b: str, threshold: float | None = None) -> bool:
        th = threshold or self.threshold
        mh_a = self._create_minhash(text_a)
        mh_b = self._create_minhash(text_b)
        return mh_a.jaccard(mh_b) >= th
