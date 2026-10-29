"""
LLMCycle Model Info Cache
==========================
Two-level cache for provider model metadata (context window, pricing, etc.):

  Level 1 — In-memory LRU   (OrderedDict, max 512 entries, zero I/O)
  Level 2 — Disk / SSD      (JSON file inside the project's llmcycle/storage/ dir)

The provider API is called at most ONCE per model per machine.
On subsequent startups the disk cache is loaded — no network needed.

Default cache path (relative to current working directory):
  <cwd>/llmcycle/storage/model_info.json

Override options (highest priority first):
  1. Constructor:  ModelInfoCache(cache_dir=Path("/custom/path"))
  2. Env var:      LLMCYCLE_CACHE_DIR=/custom/path
  3. Default:      <cwd>/llmcycle/storage/

Usage (internal):

    cache = get_model_info_cache()
    info  = cache.get("openai/gpt-4o")     # None on miss
    cache.set("openai/gpt-4o", {...})       # write to LRU + disk
    cache.invalidate("openai/gpt-4o")       # force re-fetch from API
    cache.clear()                           # wipe everything
    print(cache.stats())
"""
from __future__ import annotations

import json
import logging
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

_LRU_MAX_SIZE    = 512
_CACHE_SUBFOLDER = "model_info"       # llmcycle/storage/model_info/
_CACHE_FILE      = "model_info.json"  # all model metadata in one file


# ─── Resolve cache directory ─────────────────────────────────────────────────

def _default_cache_dir() -> Path:
    """
    Priority:
      1. LLMCYCLE_CACHE_DIR env var
      2. <cwd>/llmcycle/storage/model_info/
    """
    env = os.environ.get("LLMCYCLE_CACHE_DIR", "").strip()
    if env:
        return Path(env)
    return Path.cwd() / "llmcycle" / "storage" / _CACHE_SUBFOLDER


# ─── LRU + Disk cache ────────────────────────────────────────────────────────

class ModelInfoCache:
    """
    Thread-safe two-level model-info cache.

    L1  In-memory LRU  —  OrderedDict bounded to max_size entries.
                          Evicts least-recently-used when full.
    L2  Disk cache     —  JSON file inside llmcycle/storage/model_info/
                          Persists across process restarts.

    Keys are  "<provider>/<model_id>"  strings, e.g. "openai/gpt-4o".
    Values are the raw + normalised dict returned by the provider API.

    Args:
        cache_dir:   Override the directory where the JSON file is written.
                     Defaults to <cwd>/llmcycle/storage/model_info/
                     Can also be set via LLMCYCLE_CACHE_DIR env var.
        max_size:    Max entries kept in the in-memory LRU (default: 512).
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        max_size: int = _LRU_MAX_SIZE,
    ):
        self._max         = max_size
        self._lru:        OrderedDict[str, dict] = OrderedDict()
        self._lock        = threading.Lock()
        self._disk_loaded = False

        # Resolve cache directory — constructor arg > env var > default
        resolved = cache_dir or _default_cache_dir()
        self._disk_dir  = Path(resolved)
        self._disk_file = self._disk_dir / _CACHE_FILE

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def cache_dir(self) -> Path:
        """The directory where the JSON disk cache is stored."""
        return self._disk_dir

    @property
    def cache_file(self) -> Path:
        """Full path to the JSON cache file."""
        return self._disk_file

    # ── Disk I/O ──────────────────────────────────────────────────────────────

    def _load_disk(self) -> None:
        """Load disk cache into LRU on first call (lazy, thread-safe)."""
        if self._disk_loaded:
            return
        self._disk_loaded = True
        if not self._disk_file.exists():
            logger.debug(f"ModelInfoCache: no existing cache at {self._disk_file}")
            return
        try:
            data: dict = json.loads(self._disk_file.read_text(encoding="utf-8"))
            for key, val in data.items():
                if len(self._lru) >= self._max:
                    self._lru.popitem(last=False)   # evict oldest
                self._lru[key] = val
            logger.debug(
                f"ModelInfoCache: loaded {len(data)} entries from {self._disk_file}"
            )
        except Exception as e:
            logger.warning(f"ModelInfoCache: failed to load disk cache: {e}")

    def _flush_disk(self) -> None:
        """Write current LRU to disk (best-effort, non-fatal on failure)."""
        try:
            self._disk_dir.mkdir(parents=True, exist_ok=True)
            self._disk_file.write_text(
                json.dumps(dict(self._lru), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"ModelInfoCache: disk write failed: {e}")

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[dict]:
        """
        Return cached model info or None on a miss.

        Loads the disk cache automatically on first access.
        Promotes the entry to most-recently-used on every hit.
        """
        with self._lock:
            self._load_disk()
            if key in self._lru:
                self._lru.move_to_end(key)
                return self._lru[key]
        return None

    def set(self, key: str, value: dict) -> None:
        """
        Store model info in L1 (LRU) and L2 (disk).

        If the LRU is at capacity the least-recently-used entry is evicted
        from memory (not from disk — disk retains all entries ever seen).
        """
        with self._lock:
            self._load_disk()
            if key in self._lru:
                self._lru.move_to_end(key)
            else:
                if len(self._lru) >= self._max:
                    self._lru.popitem(last=False)
            self._lru[key] = value
            self._flush_disk()

    def invalidate(self, key: str) -> None:
        """Remove a single entry so it will be re-fetched from the provider API."""
        with self._lock:
            self._lru.pop(key, None)
            if self._disk_file.exists():
                try:
                    data = json.loads(self._disk_file.read_text(encoding="utf-8"))
                    if key in data:
                        del data[key]
                        self._disk_file.write_text(
                            json.dumps(data, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                except Exception:
                    pass

    def clear(self) -> None:
        """Wipe the in-memory LRU and delete the disk cache file."""
        with self._lock:
            self._lru.clear()
            if self._disk_file.exists():
                try:
                    self._disk_file.unlink()
                    logger.debug(f"ModelInfoCache: deleted {self._disk_file}")
                except Exception as e:
                    logger.warning(f"ModelInfoCache: could not delete cache file: {e}")

    def keys(self) -> list[str]:
        """Return all cached model keys currently in the LRU."""
        with self._lock:
            return list(self._lru.keys())

    def stats(self) -> dict:
        """Diagnostic info about the cache state."""
        with self._lock:
            self._load_disk()
            return {
                "lru_entries":  len(self._lru),
                "lru_max":      self._max,
                "cache_dir":    str(self._disk_dir),
                "cache_file":   str(self._disk_file),
                "disk_exists":  self._disk_file.exists(),
                "disk_size_kb": (
                    round(self._disk_file.stat().st_size / 1024, 1)
                    if self._disk_file.exists() else 0
                ),
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._lru)

    def __repr__(self) -> str:
        return (
            f"ModelInfoCache("
            f"entries={len(self._lru)}/{self._max}, "
            f"file={self._disk_file})"
        )


# ─── Process-wide singleton ───────────────────────────────────────────────────

_singleton:      Optional[ModelInfoCache] = None
_singleton_lock  = threading.Lock()


def get_model_info_cache(
    cache_dir: Optional[Path] = None,
    max_size:  int = _LRU_MAX_SIZE,
) -> ModelInfoCache:
    """
    Return the process-wide ModelInfoCache singleton.

    All provider instances share the same cache — a model fetched by any
    provider is never fetched again for the lifetime of the process.

    Args:
        cache_dir:  Override the disk cache location.
                    Only respected on the FIRST call (singleton creation).
                    Subsequent calls return the existing instance unchanged.
        max_size:   Max LRU size (only respected on first call).
    """
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:          # double-checked locking
                _singleton = ModelInfoCache(cache_dir=cache_dir, max_size=max_size)
                logger.debug(f"ModelInfoCache singleton created: {_singleton}")
    return _singleton
