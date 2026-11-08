"""
Semantic Cache Admin & Telemetry Router
=======================================
Provides endpoints to inspect, test, configure, and purge the Semantic Cache.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from .deps import auth, llm_client
from veloroute.core.semantic_cache import SemanticCache

router = APIRouter()


def _get_cache() -> SemanticCache:
    if getattr(llm_client, "_semantic_cache", None) is None:
        llm_client._semantic_cache = SemanticCache()
    return llm_client._semantic_cache


class CacheTestRequest(BaseModel):
    prompt: str = Field(..., description="Prompt or query text to test against semantic cache")
    model: Optional[str] = Field(None, description="Optional target model identifier")


class CacheConfigRequest(BaseModel):
    threshold: Optional[float] = Field(None, ge=0.1, le=1.0, description="Similarity threshold (0.1 - 1.0)")
    ttl: Optional[float] = Field(None, ge=1.0, description="Time to live in seconds")
    max_size: Optional[int] = Field(None, ge=10, description="Maximum number of stored cache entries")


class CacheDeleteRequest(BaseModel):
    key: str = Field(..., description="Storage key to delete")


@router.get("/api/v1/cache/stats")
async def get_cache_stats(_: str = Depends(auth)):
    cache = _get_cache()
    stats = await cache.stats()
    return {
        "status": "ok",
        "cache_type": "TF-IDF Semantic Vector Cache",
        "stats": stats,
    }


@router.get("/api/v1/cache/entries")
async def get_cache_entries(
    limit: int = Query(50, ge=1, le=200),
    _: str = Depends(auth),
):
    cache = _get_cache()
    entries = cache.entries(limit=limit)
    return {
        "status": "ok",
        "count": len(entries),
        "entries": entries,
    }


@router.post("/api/v1/cache/test")
async def test_cache_similarity(
    req: CacheTestRequest,
    _: str = Depends(auth),
):
    cache = _get_cache()
    result = cache.test_similarity(req.prompt, model=req.model)
    return {
        "status": "ok",
        "result": result,
    }


@router.post("/api/v1/cache/config")
async def update_cache_config(
    req: CacheConfigRequest,
    _: str = Depends(auth),
):
    cache = _get_cache()
    cache.update_settings(threshold=req.threshold, ttl=req.ttl, max_size=req.max_size)
    return {
        "status": "ok",
        "message": "Cache configuration updated successfully",
        "current_threshold": cache.threshold,
        "current_ttl": cache.ttl,
        "current_max_size": cache.max_size,
    }


@router.delete("/api/v1/cache/entry")
async def delete_cache_entry(
    req: CacheDeleteRequest,
    _: str = Depends(auth),
):
    cache = _get_cache()
    deleted = cache.delete_entry(req.key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cache entry not found")
    return {
        "status": "ok",
        "message": "Cache entry deleted successfully",
    }


@router.post("/api/v1/cache/clear")
async def clear_cache(_: str = Depends(auth)):
    cache = _get_cache()
    count = await cache.clear()
    return {
        "status": "ok",
        "cleared_count": count,
        "message": f"Purged {count} cached entries from semantic cache",
    }
