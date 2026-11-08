"""Admin endpoints for virtual gateway keys."""
from fastapi import APIRouter, Depends, HTTPException

from .deps import auth, llm_client
from .models import VirtualKeyCreateRequest, VirtualKeyUpdateRequest

router = APIRouter()


@router.get("/api/v1/gateway/keys")
async def list_gateway_keys(_: str = Depends(auth)):
    manager = llm_client.virtual_keys
    keys = manager.list_keys()
    for key in keys:
        usage = manager.get_usage(key["id"])
        if usage:
            key["window_requests"] = usage["window_requests"]
            key["window_tokens"] = usage["window_tokens"]
    return {"stats": manager.stats(), "keys": keys}


@router.post("/api/v1/gateway/keys", status_code=201)
async def create_gateway_key(req: VirtualKeyCreateRequest, _: str = Depends(auth)):
    try:
        record, plaintext = await llm_client.virtual_keys.create_key(
            req.name,
            budget_usd=req.budget_usd,
            budget_alert_threshold=req.budget_alert_threshold,
            budget_alert_webhook=req.budget_alert_webhook,
            auto_pause_on_budget=req.auto_pause_on_budget if req.auto_pause_on_budget is not None else True,
            rpm_limit=req.rpm_limit,
            tpm_limit=req.tpm_limit,
            allowed_models=req.allowed_models,
            expires_at=req.expires_at,
            expires_in=req.expires_in,
            metadata=req.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"key": plaintext, "virtual_key": record.to_public_dict()}


@router.get("/api/v1/gateway/keys/{key_id}")
async def get_gateway_key(key_id: str, _: str = Depends(auth)):
    usage = llm_client.virtual_keys.get_usage(key_id)
    if usage is None:
        raise HTTPException(status_code=404, detail="Virtual key not found")
    return {"virtual_key": usage}


@router.patch("/api/v1/gateway/keys/{key_id}")
async def update_gateway_key(
    key_id: str,
    req: VirtualKeyUpdateRequest,
    _: str = Depends(auth),
):
    try:
        record = await llm_client.virtual_keys.update_key(
            key_id, **req.model_dump(exclude_unset=True)
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Virtual key not found")
    return {"virtual_key": record.to_public_dict()}


@router.post("/api/v1/gateway/keys/{key_id}/revoke")
async def revoke_gateway_key(key_id: str, _: str = Depends(auth)):
    if not await llm_client.virtual_keys.revoke_key(key_id):
        raise HTTPException(status_code=404, detail="Virtual key not found")
    return {"status": "ok", "key_id": key_id}


@router.post("/api/v1/gateway/keys/{key_id}/rotate")
async def rotate_gateway_key(key_id: str, _: str = Depends(auth)):
    plaintext = await llm_client.virtual_keys.rotate_key(key_id)
    if plaintext is None:
        raise HTTPException(status_code=404, detail="Virtual key not found")
    return {"key": plaintext, "virtual_key": llm_client.virtual_keys.get_key(key_id).to_public_dict()}


@router.delete("/api/v1/gateway/keys/{key_id}")
async def delete_gateway_key(key_id: str, _: str = Depends(auth)):
    if not await llm_client.virtual_keys.delete_key(key_id):
        raise HTTPException(status_code=404, detail="Virtual key not found")
    return {"status": "ok", "key_id": key_id}
