"""API endpoints for Gateway Transformation & Custom Middleware Rules."""
from __future__ import annotations

import secrets
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .deps import auth, llm_client
from veloroute.core.transform import TransformRule

router = APIRouter()


class RuleCreateRequest(BaseModel):
    name: str
    rule_type: str  # "model_rewrite", "inject_header", "strip_header", "response_redact"
    match_pattern: str
    replacement: Optional[str] = ""
    enabled: bool = True
    description: Optional[str] = ""


class RuleUpdateRequest(BaseModel):
    name: Optional[str] = None
    rule_type: Optional[str] = None
    match_pattern: Optional[str] = None
    replacement: Optional[str] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None


class TestTransformRequest(BaseModel):
    test_type: str  # "model", "redact", "header_inject", "header_strip"
    input_value: str
    header_key: Optional[str] = None


@router.get("/api/v1/transforms")
async def list_transforms(_: str = Depends(auth)):
    if not hasattr(llm_client, "transforms"):
        return {"rules": [], "total": 0}
    rules = llm_client.transforms.list_rules()
    return {
        "rules": rules,
        "total": len(rules),
    }


@router.post("/api/v1/transforms")
async def create_transform(req: RuleCreateRequest, _: str = Depends(auth)):
    if not hasattr(llm_client, "transforms"):
        raise HTTPException(500, "Transform engine not initialized")

    rule_id = f"tr-{secrets.token_hex(4)}"
    rule = TransformRule(
        id=rule_id,
        name=req.name.strip(),
        rule_type=req.rule_type.strip(),
        match_pattern=req.match_pattern.strip(),
        replacement=req.replacement.strip() if req.replacement else "",
        enabled=req.enabled,
        description=req.description.strip() if req.description else "",
    )
    llm_client.transforms._rules[rule.id] = rule
    await llm_client.transforms.save_async()
    return {"status": "created", "rule": rule.to_dict()}


@router.put("/api/v1/transforms/{rule_id}")
async def update_transform(rule_id: str, req: RuleUpdateRequest, _: str = Depends(auth)):
    if not hasattr(llm_client, "transforms"):
        raise HTTPException(500, "Transform engine not initialized")

    rule = llm_client.transforms.get_rule(rule_id)
    if not rule:
        raise HTTPException(404, f"Transform rule {rule_id} not found")

    if req.name is not None:
        rule.name = req.name.strip()
    if req.rule_type is not None:
        rule.rule_type = req.rule_type.strip()
    if req.match_pattern is not None:
        rule.match_pattern = req.match_pattern.strip()
    if req.replacement is not None:
        rule.replacement = req.replacement.strip()
    if req.enabled is not None:
        rule.enabled = req.enabled
    if req.description is not None:
        rule.description = req.description.strip()

    await llm_client.transforms.save_async()
    return {"status": "updated", "rule": rule.to_dict()}


@router.delete("/api/v1/transforms/{rule_id}")
async def delete_transform(rule_id: str, _: str = Depends(auth)):
    if not hasattr(llm_client, "transforms"):
        raise HTTPException(500, "Transform engine not initialized")

    if rule_id in llm_client.transforms._rules:
        del llm_client.transforms._rules[rule_id]
        await llm_client.transforms.save_async()
        return {"status": "deleted", "rule_id": rule_id}
    for k, r in list(llm_client.transforms._rules.items()):
        if r.name == rule_id:
            del llm_client.transforms._rules[k]
            await llm_client.transforms.save_async()
            return {"status": "deleted", "rule_id": rule_id}

    raise HTTPException(404, f"Transform rule {rule_id} not found")


@router.post("/api/v1/transforms/test")
async def test_transform_endpoint(req: TestTransformRequest, _: str = Depends(auth)):
    if not hasattr(llm_client, "transforms"):
        raise HTTPException(500, "Transform engine not initialized")

    result = llm_client.transforms.test_transform(
        test_type=req.test_type,
        input_value=req.input_value,
        header_key=req.header_key,
    )
    return result
