"""
Prompt Hub & Playground Router
==============================
Provides endpoints to manage versioned prompt templates and execute them
live in an interactive playground.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import time

from .deps import auth, llm_client

router = APIRouter()


class PromptCreateRequest(BaseModel):
    name: str = Field(..., description="Unique prompt template identifier (e.g. code_reviewer)")
    template: str = Field(..., description="Prompt template with {{variable}} placeholders")
    system_prompt: Optional[str] = Field("", description="Optional system instructions with {{variable}} placeholders")
    version: Optional[str] = Field("v1", description="Version string (e.g. v1, v2)")
    description: Optional[str] = Field("", description="Human-readable description")
    model: Optional[str] = Field(None, description="Preferred default model")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, gt=0)


class PromptRenderRequest(BaseModel):
    version: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)


class PromptRunRequest(BaseModel):
    version: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@router.get("/api/v1/prompts")
async def list_prompts(_: str = Depends(auth)):
    prompts = llm_client.prompts.list_prompts_overview()
    return {
        "status": "ok",
        "total": len(prompts),
        "prompts": prompts,
    }


@router.post("/api/v1/prompts", status_code=201)
async def create_prompt(req: PromptCreateRequest, _: str = Depends(auth)):
    pv = llm_client.prompts.set(
        name=req.name,
        template=req.template,
        system_prompt=req.system_prompt or "",
        version=req.version or "v1",
        description=req.description or "",
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )
    return {
        "status": "ok",
        "message": f"Prompt '{pv.name}' version '{pv.version}' saved successfully",
        "prompt": pv.to_dict(),
    }


@router.get("/api/v1/prompts/{name}")
async def get_prompt_versions(name: str, _: str = Depends(auth)):
    versions = llm_client.prompts.list(name=name)
    if not versions:
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")
    return {
        "status": "ok",
        "name": name,
        "versions": versions,
    }


@router.delete("/api/v1/prompts/{name}")
async def delete_prompt(
    name: str,
    version: Optional[str] = Query(None, description="Optional specific version to delete"),
    _: str = Depends(auth),
):
    deleted = llm_client.prompts.delete(name=name, version=version)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")
    return {
        "status": "ok",
        "deleted_count": deleted,
        "message": f"Deleted {deleted} version(s) of '{name}'",
    }


@router.post("/api/v1/prompts/{name}/render")
async def render_prompt(name: str, req: PromptRenderRequest, _: str = Depends(auth)):
    try:
        pv = llm_client.prompts.get(name, version=req.version)
        messages = pv.render_messages(**req.variables)
        return {
            "status": "ok",
            "name": name,
            "version": pv.version,
            "messages": messages,
            "variables_used": list(req.variables.keys()),
        }
    except KeyError as err:
        raise HTTPException(status_code=400, detail=str(err))


class PromptAnalyzeRequest(BaseModel):
    name: Optional[str] = None
    template: str = ""
    system_prompt: Optional[str] = ""


@router.post("/api/v1/prompts/analyze")
async def analyze_prompt_endpoint(req: PromptAnalyzeRequest, _: str = Depends(auth)):
    tpl = req.template
    sys_p = req.system_prompt or ""
    if not tpl and req.name:
        try:
            pv = llm_client.prompts.get(req.name)
            tpl = pv.template
            sys_p = sys_p or pv.system_prompt or ""
        except KeyError:
            pass
    report = llm_client.prompts.analyze_prompt(
        template=tpl,
        system_prompt=sys_p,
    )
    return {"status": "ok", "analysis": report, **report}


@router.get("/api/v1/prompts/{name}/export")
async def export_prompt_ide_rules(
    name: str,
    format: str = Query("cursorrules", description="cursorrules | claude | agents"),
    _: str = Depends(auth),
):
    try:
        exported = llm_client.prompts.export_ide_rules(name=name, format_type=format)
        return {"status": "ok", **exported}
    except KeyError as err:
        raise HTTPException(status_code=404, detail=str(err))


@router.post("/api/v1/prompts/{name}/run")
async def run_prompt(name: str, req: PromptRunRequest, _: str = Depends(auth)):
    try:
        pv = llm_client.prompts.get(name, version=req.version)
        messages = pv.render_messages(**req.variables)
    except KeyError as err:
        raise HTTPException(status_code=400, detail=str(err))

    target_model = req.model or pv.model or "mock/mock-fast"
    start_time = time.time()
    try:
        response = await llm_client.complete(
            model=target_model,
            messages=messages,
            temperature=req.temperature if req.temperature is not None else pv.temperature,
            max_tokens=req.max_tokens if req.max_tokens is not None else pv.max_tokens,
        )
        latency_ms = round((time.time() - start_time) * 1000, 1)
        tokens = (response.prompt_tokens or 0) + (response.completion_tokens or 0)
        return {
            "status": "ok",
            "name": name,
            "version": pv.version,
            "model_used": response.model,
            "provider": response.provider,
            "content": response.content,
            "tokens": tokens,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "latency_ms": latency_ms,
            "cached": getattr(response, "cached", False),
        }
    except Exception as err:
        raise HTTPException(status_code=502, detail=f"LLM execution error: {err}")
