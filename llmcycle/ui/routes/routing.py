from fastapi import APIRouter, Depends, Query, HTTPException
from llmcycle.core.router import RoutingStrategy
from .deps import auth, llm_client
from .models import SetFallbackRequest, AliasRequest

router = APIRouter()

@router.get("/api/v1/router")
async def get_router(_: str = Depends(auth)):
    return {
        "strategy": llm_client.router.strategy.value,
        "fallbacks": llm_client.router.fallbacks,
        "aliases": llm_client.list_aliases(),
        "latencies": llm_client.router.latency.all(),
        "available_strategies": [s.value for s in RoutingStrategy],
    }

@router.post("/api/v1/router/fallbacks")
async def set_fallbacks(req: SetFallbackRequest, _: str = Depends(auth)):
    llm_client.router.fallbacks = req.fallbacks
    try:
        await llm_client.router.save()
    except Exception:
        pass
    return {"status": "ok", "fallbacks": req.fallbacks}

@router.get("/api/v1/router/aliases")
async def get_aliases(_: str = Depends(auth)):
    return {"aliases": llm_client.list_aliases()}

@router.post("/api/v1/router/aliases")
async def set_alias(req: AliasRequest, _: str = Depends(auth)):
    if not req.name or not req.target:
        raise HTTPException(400, "Missing 'name' or 'target' for alias")
    llm_client.alias(req.name, req.target)
    try:
        await llm_client.router.save()
    except Exception:
        pass
    return {"status": "ok", "alias": req.name, "target": req.target}

@router.delete("/api/v1/router/aliases/{name}")
async def delete_alias(name: str, _: str = Depends(auth)):
    removed = llm_client.remove_alias(name)
    if not removed:
        raise HTTPException(404, f"Alias '{name}' not found")
    try:
        await llm_client.router.save()
    except Exception:
        pass
    return {"status": "ok", "message": f"Alias '{name}' removed"}

from typing import Optional
from pydantic import BaseModel

class SetStrategyRequest(BaseModel):
    strategy: Optional[str] = None

@router.api_route("/api/v1/router/strategy", methods=["PUT", "POST"])
async def set_strategy(strategy: Optional[str] = Query(None), req: Optional[SetStrategyRequest] = None, _: str = Depends(auth)):
    chosen_strategy = strategy or (req.strategy if req else None)
    if not chosen_strategy:
        raise HTTPException(400, "Missing 'strategy' parameter in query or body")
    try:
        llm_client.router.strategy = RoutingStrategy(chosen_strategy)
        try:
            await llm_client.router.save()
        except Exception:
            pass
        return {"status": "ok", "strategy": chosen_strategy}
    except ValueError:
        raise HTTPException(400, f"Unknown strategy '{chosen_strategy}'. Use: priority, round_robin, lowest_latency, active_first, cost_optimized, least_busy, weighted")

