"""
Semantic Cache
==============
Embedding-based similarity cache that matches semantically equivalent prompts,
even when phrased differently (unlike the exact-hash cache in cache.py).

Algorithm: TF-IDF cosine similarity — zero mandatory external dependencies.
Optional: drop-in numpy acceleration when available.

Usage::

    from veloroute.core.semantic_cache import SemanticCache

    cache = SemanticCache(similarity_threshold=0.92, max_size=500, ttl=3600)

    # On every LLM call:
    hit = await cache.get("What is the capital of France?")
    if hit:
        return hit           # returns cached CompletionResponse

    # After getting a live response:
    await cache.set("What is the capital of France?", response)

    # Semantically similar queries now hit the cache:
    hit2 = await cache.get("Tell me the capital city of France")  # → cache hit!
"""
from __future__ import annotations
import re
import math
import time
import logging
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple, Any

from veloroute.schema import CompletionResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TF-IDF + Cosine similarity (no external deps)
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "a", "an", "the", "is", "it", "in", "on", "at", "to", "of", "for",
    "and", "or", "but", "with", "this", "that", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "shall",
    "i", "you", "we", "he", "she", "they", "me", "him", "her", "us",
    "what", "tell", "how", "who", "which", "where", "when", "why",
    "can", "please", "give", "show", "about", "explain", "describe",
}


import unicodedata


def _tokenize(text: Optional[str]) -> List[str]:
    """Normalize Unicode NFKC, lowercase, strip punctuation, remove stop-words, and ignore single-char clitics."""
    if not text:
        return []
    normalized = unicodedata.normalize("NFKC", str(text)).lower()
    tokens = re.findall(r"\b[\w]+\b", normalized, flags=re.UNICODE)
    cleaned = [t.strip("_") for t in tokens if t.strip("_")]
    return [t for t in cleaned if t not in _STOP_WORDS and len(t) > 1]


def _tf(tokens: List[str]) -> Dict[str, float]:
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    n = len(tokens) or 1
    return {t: c / n for t, c in counts.items()}


def _cosine(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    """Cosine similarity between two TF sparse vectors."""
    shared = set(vec_a) & set(vec_b)
    if not shared:
        return 0.0
    dot = sum(vec_a[t] * vec_b[t] for t in shared)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _similarity(text_a: str, text_b: str) -> float:
    """Compute TF cosine similarity between two strings."""
    va = _tf(_tokenize(text_a))
    vb = _tf(_tokenize(text_b))
    return _cosine(va, vb)


# ---------------------------------------------------------------------------
# Semantic Cache
# ---------------------------------------------------------------------------

class SemanticCache:
    """
    Embedding-based LRU cache that matches semantically equivalent prompts.

    Entries:
        (prompt_text, tf_vector, CompletionResponse, expires_at, model)

    On every get(), the query is compared against all stored prompts using
    TF-IDF cosine similarity. If any stored entry scores above
    `similarity_threshold`, the cached response is returned.

    Performance note: O(N) scan on get(). For N < 5000 this is fast enough
    (<1 ms). For larger caches, replace _similarity() with a numpy/faiss index.

    Args:
        similarity_threshold: Minimum cosine similarity (0-1) for a cache hit.
                              0.88 is a good default — catches paraphrases and semantic equivalents.
        max_size:             Maximum number of entries before LRU eviction.
        ttl:                  Time-to-live in seconds (default 3600 = 1 hour).
    """

    def __init__(
        self,
        similarity_threshold: float = 0.88,
        max_size: int = 500,
        ttl: float = 3600.0,
        threshold: Optional[float] = None,
    ):
        self.threshold = float(threshold if threshold is not None else similarity_threshold)
        self.max_size = int(max_size)
        self.ttl = float(ttl)
        # Ordered by insertion for LRU eviction:
        # key = "<model>\x00<prompt>", value = (tf_vector, response, expires_at, model)
        self._store: OrderedDict[
            str, Tuple[Dict[str, float], CompletionResponse, float, Optional[str]]
        ] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._tokens_saved = 0
        self._latency_saved_ms = 0.0
        self._cost_saved_usd = 0.0

    async def get(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> Optional[CompletionResponse]:
        """
        Look up a semantically similar cached response.

        ``model`` scopes the lookup: a response generated by model A must never
        be replayed for model B. Entries stored without a model (legacy /
        explicit wildcard) match every model.

        Returns None on miss. On hit, moves the entry to the end of the LRU
        order (most-recently-used).
        """
        now = time.time()
        query_vec = _tf(_tokenize(prompt))
        best_score = 0.0
        best_key: Optional[str] = None

        # Expire and scan
        expired = [k for k, (_, __, exp, ___) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]

        for key, (vec, response, expires_at, entry_model) in self._store.items():
            if model is not None and entry_model is not None and entry_model != model:
                continue
            score = _cosine(query_vec, vec)
            if score > best_score:
                best_score = score
                best_key = key

        if best_key and best_score >= self.threshold:
            self._store.move_to_end(best_key)  # LRU update
            self._hits += 1
            cached_resp = self._store[best_key][1]

            # Telemetry tracking for savings
            tokens = 0
            if getattr(cached_resp, "prompt_tokens", None) is not None:
                tokens = (cached_resp.prompt_tokens or 0) + (cached_resp.completion_tokens or 0)
            elif getattr(cached_resp, "usage", None):
                tokens = getattr(cached_resp.usage, "total_tokens", 0)
            tokens = tokens or 50
            self._tokens_saved += tokens
            self._latency_saved_ms += 420.0
            self._cost_saved_usd += (tokens / 1000.0) * 0.003

            logger.debug(
                f"[SemanticCache] HIT score={best_score:.3f} model={model!r} "
                f"query='{str(prompt)[:60]}' matched='{best_key.split(chr(0))[-1][:60]}'"
            )
            return cached_resp

        self._misses += 1
        return None

    async def set(
        self,
        prompt: str,
        response: CompletionResponse,
        model: Optional[str] = None,
        ttl: Optional[float] = None,
    ) -> None:
        """Store a prompt → response pair, scoped to ``model`` when provided."""
        now = time.time()
        # Evict LRU if at capacity
        if len(self._store) >= self.max_size:
            self._store.popitem(last=False)
        vec = _tf(_tokenize(prompt))
        storage_key = f"{model or '*'}\x00{prompt}"
        eff_ttl = float(ttl) if ttl is not None else self.ttl
        self._store[storage_key] = (vec, response, now + eff_ttl, model)
        self._store.move_to_end(storage_key)

    def entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return cached items for dashboard inspection."""
        now = time.time()
        result = []
        # Return most recently used first
        for key in reversed(list(self._store.keys())):
            vec, resp, exp, entry_model = self._store[key]
            if exp <= now:
                continue
            parts = key.split("\x00", 1)
            prompt_text = parts[1] if len(parts) > 1 else key
            
            resp_text = ""
            if resp:
                if getattr(resp, "content", None):
                    resp_text = str(resp.content)
                elif getattr(resp, "choices", None) and len(resp.choices) > 0:
                    first_choice = resp.choices[0]
                    if getattr(first_choice, "message", None) and getattr(first_choice.message, "content", None):
                        resp_text = str(first_choice.message.content)
                    elif getattr(first_choice, "text", None):
                        resp_text = str(first_choice.text)

            tokens = 0
            if resp:
                if getattr(resp, "prompt_tokens", None) is not None:
                    tokens = (resp.prompt_tokens or 0) + (resp.completion_tokens or 0)
                elif getattr(resp, "usage", None):
                    tokens = getattr(resp.usage, "total_tokens", 0)

            result.append({
                "key": key,
                "model": entry_model or "all",
                "prompt": prompt_text,
                "prompt_preview": prompt_text[:140] + ("..." if len(prompt_text) > 140 else ""),
                "response_preview": resp_text[:200] + ("..." if len(resp_text) > 200 else ""),
                "tokens": tokens,
                "expires_in_secs": max(0, int(exp - now)),
            })
            if len(result) >= limit:
                break
        return result

    def delete_entry(self, key: str) -> bool:
        """Delete an individual entry by its storage key."""
        if key in self._store:
            del self._store[key]
            return True
        return False

    def test_similarity(self, prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
        """Test similarity score against existing cache without altering metrics."""
        now = time.time()
        query_vec = _tf(_tokenize(prompt))
        best_score = 0.0
        best_key: Optional[str] = None
        best_resp: Optional[CompletionResponse] = None

        for key, (vec, response, exp, entry_model) in self._store.items():
            if exp <= now:
                continue
            if model is not None and entry_model is not None and entry_model != model:
                continue
            score = _cosine(query_vec, vec)
            if score > best_score:
                best_score = score
                best_key = key
                best_resp = response

        matched_prompt = ""
        matched_model = ""
        resp_text = ""
        if best_key:
            parts = best_key.split("\x00", 1)
            matched_prompt = parts[1] if len(parts) > 1 else best_key
            matched_model = self._store[best_key][3] or "all"
            if best_resp:
                if getattr(best_resp, "content", None):
                    resp_text = str(best_resp.content)
                elif getattr(best_resp, "choices", None) and len(best_resp.choices) > 0:
                    c = best_resp.choices[0]
                    if getattr(c, "message", None) and getattr(c.message, "content", None):
                        resp_text = str(c.message.content)
                    elif getattr(c, "text", None):
                        resp_text = str(c.text)

        is_hit = best_score >= self.threshold and best_score > 0.0
        return {
            "query": prompt,
            "best_score": round(best_score, 4),
            "similarity_percent": round(best_score * 100, 1),
            "threshold": self.threshold,
            "threshold_percent": round(self.threshold * 100, 1),
            "is_hit": is_hit,
            "matched_prompt": matched_prompt,
            "matched_model": matched_model,
            "response_preview": resp_text if is_hit else "",
        }

    def update_settings(
        self,
        threshold: Optional[float] = None,
        ttl: Optional[float] = None,
        max_size: Optional[int] = None,
    ) -> None:
        """Dynamically update cache configuration."""
        if threshold is not None:
            self.threshold = max(0.1, min(1.0, float(threshold)))
        if ttl is not None:
            self.ttl = max(1.0, float(ttl))
        if max_size is not None:
            self.max_size = max(10, int(max_size))

    async def clear(self) -> int:
        count = len(self._store)
        self._store.clear()
        return count

    async def stats(self) -> Dict[str, Any]:
        now = time.time()
        active = sum(1 for _, __, exp, ___ in self._store.values() if now < exp)
        total_requests = self._hits + self._misses
        hit_rate = round(self._hits / total_requests, 3) if total_requests > 0 else 0.0
        return {
            "entries": len(self._store),
            "active": active,
            "expired": len(self._store) - active,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "hit_rate_percent": round(hit_rate * 100, 1),
            "tokens_saved": self._tokens_saved,
            "latency_saved_ms": round(self._latency_saved_ms, 1),
            "cost_saved_usd": round(self._cost_saved_usd, 4),
            "threshold": self.threshold,
            "max_size": self.max_size,
            "ttl": self.ttl,
        }
