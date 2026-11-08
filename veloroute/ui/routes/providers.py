import os
import logging
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from .deps import auth, llm_client
from .models import AddProviderRequest, UpdateProviderRequest, AddKeyRequest, SyncModelsRequest
from veloroute.cli import _set_env_key, _remove_env_key, _safe_load_env

logger = logging.getLogger("veloroute.ui.providers")

router = APIRouter()

@router.get("/api/v1/providers")
async def list_providers(_: str = Depends(auth)):
    result = []
    for name in llm_client.get_providers():
        counts = llm_client.key_manager.key_count(name)
        custom_m = llm_client.get_custom_models(name)
        result.append({
            "name": name,
            "base_url": llm_client._providers[name].base_url,
            "keys": counts,
            "custom_models": custom_m,
            "is_custom": custom_m is not None,
        })
    return result

@router.post("/api/v1/providers")
async def add_provider(req: AddProviderRequest, _: str = Depends(auth)):
    llm_client.add_provider(req.name, req.api_keys, req.base_url, models=req.models)
    
    # Auto-save to .env so changes persist across PC / server restarts!
    try:
        env_path = Path(".env")
        p_name = req.name.upper()
        if req.base_url:
            _set_env_key(env_path, f"{p_name}_BASE_URL", req.base_url)
            os.environ[f"{p_name}_BASE_URL"] = req.base_url
            
        existing_keys_raw = os.environ.get(f"{p_name}_API_KEYS", "")
        existing_keys = [k.strip() for k in existing_keys_raw.split(",") if k.strip()]
        for k in req.api_keys:
            if k not in existing_keys:
                existing_keys.append(k)
        keys_str = ",".join(existing_keys)
        _set_env_key(env_path, f"{p_name}_API_KEYS", keys_str)
        os.environ[f"{p_name}_API_KEYS"] = keys_str

        if req.models:
            models_clean = [m.strip() for m in req.models if m.strip()]
            if models_clean:
                _set_env_key(env_path, f"{p_name}_MODELS", ",".join(models_clean))
                os.environ[f"{p_name}_MODELS"] = ",".join(models_clean)
    except Exception as e:
        logger.warning(f"Could not auto-persist provider to .env: {e}")

    return {"status": "ok", "provider": req.name.lower(), "keys_added": len(req.api_keys)}

@router.put("/api/v1/providers/{name}")
async def update_provider(name: str, req: UpdateProviderRequest, _: str = Depends(auth)):
    p_lower = name.lower()
    p_upper = name.upper()
    env_path = Path(".env")
    
    valid_keys = [k.strip() for k in req.api_keys if k.strip()] if req.api_keys is not None else None
    
    # 1. Update in VeloRoute client
    llm_client.update_provider(
        name=p_lower,
        api_keys=valid_keys if valid_keys and len(valid_keys) > 0 else None,
        base_url=req.base_url,
        models=req.models,
    )
    
    # 2. Persist Base URL if provided
    if req.base_url:
        clean_url = req.base_url.strip().rstrip("/")
        _set_env_key(env_path, f"{p_upper}_BASE_URL", clean_url)
        os.environ[f"{p_upper}_BASE_URL"] = clean_url
        
    # 3. Persist API Keys if provided
    if valid_keys is not None and len(valid_keys) > 0:
        keys_str = ",".join(valid_keys)
        _set_env_key(env_path, f"{p_upper}_API_KEYS", keys_str)
        os.environ[f"{p_upper}_API_KEYS"] = keys_str
        _remove_env_key(env_path, f"{p_upper}_API_KEY")
        os.environ.pop(f"{p_upper}_API_KEY", None)

    # 4. Persist Custom Models if provided
    if req.models is not None:
        valid_models = [m.strip() for m in req.models if m.strip()]
        if valid_models:
            _set_env_key(env_path, f"{p_upper}_MODELS", ",".join(valid_models))
            os.environ[f"{p_upper}_MODELS"] = ",".join(valid_models)
        else:
            _remove_env_key(env_path, f"{p_upper}_MODELS")
            os.environ.pop(f"{p_upper}_MODELS", None)

    _safe_load_env(override=True)
    return {"status": "ok", "provider": p_lower, "message": f"Provider {name} updated"}

@router.delete("/api/v1/providers/{name}")
async def delete_provider(name: str, _: str = Depends(auth)):
    p_lower = name.lower()
    p_upper = name.upper()
    
    # 1. Remove from client
    llm_client.remove_provider(p_lower)
        
    # 2. Remove from os.environ
    os.environ.pop(f"{p_upper}_API_KEYS", None)
    os.environ.pop(f"{p_upper}_API_KEY", None)
    os.environ.pop(f"{p_upper}_BASE_URL", None)
    os.environ.pop(f"{p_upper}_MODELS", None)
    
    # 3. Remove from .env file
    try:
        env_path = Path(".env")
        _remove_env_key(env_path, f"{p_upper}_API_KEYS")
        _remove_env_key(env_path, f"{p_upper}_API_KEY")
        _remove_env_key(env_path, f"{p_upper}_BASE_URL")
        _remove_env_key(env_path, f"{p_upper}_MODELS")
    except Exception as e:
        logger.warning(f"Could not remove from .env: {e}")
        
    _safe_load_env(override=True)
    return {"status": "ok", "provider": p_lower, "message": f"Provider {name} deleted"}

@router.delete("/api/v1/providers/{name}/keys")
async def delete_key(name: str, key: str = Query(...), _: str = Depends(auth)):
    p_lower = name.lower()
    p_upper = name.upper()
    removed = llm_client.remove_key(p_lower, key)
    
    if removed:
        env_path = Path(".env")
        existing_records = llm_client.key_manager._keys.get(p_lower, [])
        remaining_keys = [r.key for r in existing_records]
        if remaining_keys:
            keys_str = ",".join(remaining_keys)
            _set_env_key(env_path, f"{p_upper}_API_KEYS", keys_str)
            os.environ[f"{p_upper}_API_KEYS"] = keys_str
            _remove_env_key(env_path, f"{p_upper}_API_KEY")
            os.environ.pop(f"{p_upper}_API_KEY", None)
        else:
            _remove_env_key(env_path, f"{p_upper}_API_KEYS")
            _remove_env_key(env_path, f"{p_upper}_API_KEY")
            os.environ.pop(f"{p_upper}_API_KEYS", None)
            os.environ.pop(f"{p_upper}_API_KEY", None)
            
    _safe_load_env(override=True)
    return {"status": "ok", "provider": p_lower, "removed": removed}

@router.get("/api/v1/providers/{name}/models")
async def get_provider_models(name: str, _: str = Depends(auth)):
    p_lower = name.lower()
    models = []
    try:
        models = await llm_client.get_models(p_lower)
    except Exception:
        pass
    custom_m = llm_client.get_custom_models(p_lower)
    return {
        "provider": name,
        "models": models,
        "count": len(models),
        "custom_models": custom_m,
        "is_custom": custom_m is not None,
    }

@router.get("/api/v1/providers/{name}/custom_models")
async def get_provider_custom_models(name: str, _: str = Depends(auth)):
    p_lower = name.lower()
    models = llm_client.get_custom_models(p_lower)
    return {
        "provider": p_lower,
        "custom_models": models,
        "is_configured": models is not None,
    }

@router.put("/api/v1/providers/{name}/custom_models")
async def set_provider_custom_models(name: str, req: dict, _: str = Depends(auth)):
    p_lower = name.lower()
    p_upper = name.upper()
    models_raw = req.get("models")
    models = [m.strip() for m in models_raw if m.strip()] if isinstance(models_raw, list) else []
    
    llm_client.set_custom_models(p_lower, models if models else None)
    env_path = Path(".env")
    if models:
        _set_env_key(env_path, f"{p_upper}_MODELS", ",".join(models))
        os.environ[f"{p_upper}_MODELS"] = ",".join(models)
    else:
        _remove_env_key(env_path, f"{p_upper}_MODELS")
        os.environ.pop(f"{p_upper}_MODELS", None)
    _safe_load_env(override=True)
    return {"status": "ok", "provider": p_lower, "custom_models": models}

@router.delete("/api/v1/providers/{name}/custom_models")
async def delete_provider_custom_models(name: str, _: str = Depends(auth)):
    p_lower = name.lower()
    p_upper = name.upper()
    llm_client.remove_custom_models(p_lower)
    env_path = Path(".env")
    _remove_env_key(env_path, f"{p_upper}_MODELS")
    os.environ.pop(f"{p_upper}_MODELS", None)
    _safe_load_env(override=True)
    return {"status": "ok", "provider": p_lower, "message": "Custom models cleared, dynamic discovery restored"}

@router.post("/api/v1/providers/sync_models")
async def sync_models_endpoint(req: SyncModelsRequest, _: str = Depends(auth)):
    prov_name = req.provider or ""
    try:
        discovered = await llm_client.discover_models(
            provider=prov_name,
            base_url=req.base_url,
            api_key=req.api_key,
        )
    except Exception as e:
        logger.warning(f"discover_models failed for provider '{prov_name}': {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    flt = (req.filter or "all").lower()
    if flt == "free":
        filtered = [item["id"] for item in discovered if item.get("is_free")]
    elif flt == "paid":
        filtered = [item["id"] for item in discovered if not item.get("is_free")]
    else:
        filtered = [item["id"] for item in discovered]
        
    p_lower = prov_name.lower()
    if req.save and p_lower in llm_client.get_providers():
        llm_client.set_custom_models(p_lower, filtered)
        try:
            env_path = Path(".env")
            p_upper = prov_name.upper()
            if filtered:
                _set_env_key(env_path, f"{p_upper}_MODELS", ",".join(filtered))
                os.environ[f"{p_upper}_MODELS"] = ",".join(filtered)
            else:
                _remove_env_key(env_path, f"{p_upper}_MODELS")
                os.environ.pop(f"{p_upper}_MODELS", None)
            _safe_load_env(override=True)
        except Exception as e:
            logger.warning(f"Could not persist custom models to .env: {e}")
            
    return {
        "status": "ok",
        "provider": prov_name,
        "filter": flt,
        "total_discovered": len(discovered),
        "count": len(filtered),
        "models": filtered,
        "saved": bool(req.save and p_lower in llm_client.get_providers()),
    }

@router.post("/api/v1/providers/{name}/sync")
async def sync_provider_endpoint(
    name: str,
    filter: str = Query("all"),
    save: bool = Query(False),
    _: str = Depends(auth),
):
    req = SyncModelsRequest(provider=name, filter=filter, save=save)
    return await sync_models_endpoint(req, _)

@router.get("/api/v1/active_models")
async def get_active_models(_: str = Depends(auth)):
    out = {}
    for p in llm_client.get_providers():
        p_lower = p.lower()
        models = []
        try:
            models = await llm_client.get_models(p_lower)
        except Exception:
            pass
        out[p] = models
    return out

@router.get("/api/v1/active_models_details")
async def get_active_models_details(_: str = Depends(auth)):
    out = []
    for p in llm_client.get_providers():
        p_lower = p.lower()
        models = []
        try:
            models = await llm_client.get_models(p_lower)
        except Exception:
            pass
        for m in models:
            full_name = f"{p_lower}/{m}"
            pricing = llm_client._get_pricing(m) or llm_client._get_pricing(full_name)
            input_price = pricing.get("input") if pricing else None
            output_price = pricing.get("output") if pricing else None
            context_window = llm_client.context_windows.get(m) or llm_client.context_windows.get(full_name)
            
            features = []
            m_lower = m.lower()
            if any(x in m_lower for x in ("vision", "gpt-4o", "claude-3-5", "gemini-1.5")):
                features.append("Vision")
            if any(x in m_lower for x in ("tool", "gpt-", "claude-", "llama-3", "gemini")):
                features.append("Tool Use")
            if any(x in m_lower for x in ("instruct", "chat", "gpt", "claude", "llama", "gemini")):
                features.append("Chat")
            if "embedding" in m_lower:
                features.append("Embeddings")
            features.append("Streaming")
            
            out.append({
                "provider": p_lower,
                "model": m,
                "full_name": full_name,
                "context_window": context_window or 4096,
                "input_price": input_price,
                "output_price": output_price,
                "features": features
            })
    return out

@router.get("/api/v1/providers/{name}/keys")
async def get_provider_keys(name: str, _: str = Depends(auth)):
    return {"provider": name, "stats": llm_client.key_manager.get_stats(name)}

@router.post("/api/v1/providers/{name}/keys")
async def add_keys(name: str, req: AddKeyRequest, _: str = Depends(auth)):
    for k in req.keys:
        llm_client.key_manager.add_key(name, k)
        
    # Auto-save additional keys to .env
    try:
        env_path = Path(".env")
        p_name = name.upper()
        existing_keys_raw = os.environ.get(f"{p_name}_API_KEYS", "")
        existing_keys = [k.strip() for k in existing_keys_raw.split(",") if k.strip()]
        for k in req.keys:
            if k not in existing_keys:
                existing_keys.append(k)
        keys_str = ",".join(existing_keys)
        _set_env_key(env_path, f"{p_name}_API_KEYS", keys_str)
        os.environ[f"{p_name}_API_KEYS"] = keys_str
    except Exception as e:
        logger.warning(f"Could not auto-persist keys to .env: {e}")

    return {"status": "ok", "provider": name, "keys_added": len(req.keys)}

@router.get("/api/v1/registry")
async def get_registry(_: str = Depends(auth)):
    from veloroute.providers.registry import PROVIDER_REGISTRY
    return PROVIDER_REGISTRY

@router.post("/api/v1/providers/{name}/ping")
async def ping_provider(
    name: str,
    model: Optional[str] = Query(None),
    timeout: float = Query(10.0),
    _: str = Depends(auth),
):
    """
    Probe provider with a live test request to verify reachability, key validity,
    and measure roundtrip latency.
    """
    res = await llm_client.ping_provider(name, model=model, timeout=timeout)
    return res

@router.post("/api/v1/providers/ping_all")
async def ping_all_providers(
    timeout: float = Query(10.0),
    _: str = Depends(auth),
):
    """
    Concurrently probe all configured providers.
    """
    res = await llm_client.ping_all_providers(timeout=timeout)
    return res

