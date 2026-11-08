"""
Model Context Protocol (MCP) Gateway Routes
=============================================
Exposes:
  - POST /mcp                 Standard JSON-RPC 2.0 endpoint for MCP clients (Cursor, Claude Code, OpenCode)
  - GET  /mcp/v1/tools        List registered tools (supports ?format=openai or ?format=mcp)
  - POST /mcp/v1/call         Direct REST invocation of an MCP tool
  - POST /mcp/v1/tools/register Register a tool dynamically
  - GET  /mcp/v1/health       MCP subsystem health & metrics
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .deps import auth, llm_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["mcp"])


@router.post("/mcp")
async def mcp_jsonrpc_endpoint(req: Union[Dict[str, Any], List[Dict[str, Any]]], request: Request):
    """
    Standard JSON-RPC 2.0 Model Context Protocol endpoint.
    Handles 'initialize', 'notifications/initialized', 'tools/list', 'tools/call', 'ping', and batch arrays.
    """
    if not hasattr(llm_client, "mcp") or not llm_client.mcp:
        raise HTTPException(503, "MCP subsystem not initialized on gateway.")

    response = await llm_client.mcp.handle_jsonrpc(req)
    if response is None:
        return Response(status_code=204)
    return JSONResponse(content=response)


@router.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request):
    """
    MCP HTTP+SSE transport discovery stream for SSE-based MCP clients (Cursor, Claude Desktop, Inspector).
    Emits the JSON-RPC POST endpoint event per MCP HTTP+SSE specification.
    """
    if not hasattr(llm_client, "mcp") or not llm_client.mcp:
        raise HTTPException(503, "MCP subsystem not initialized on gateway.")

    async def _sse_gen():
        yield "event: endpoint\ndata: /mcp\n\n"
        yield f": veloroute-mcp-gateway ready (tools={len(llm_client.mcp.list_tools())})\n\n"

    return StreamingResponse(
        _sse_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/mcp/v1/tools")
async def mcp_list_tools(
    format: str = Query("mcp", description="Output format: 'mcp' or 'openai'"),
    server: Optional[str] = Query(None, description="Optional server filter"),
):
    """List all registered MCP tools in MCP standard format or OpenAI tool calling format."""
    if not hasattr(llm_client, "mcp") or not llm_client.mcp:
        raise HTTPException(503, "MCP subsystem not initialized on gateway.")

    if format.lower() == "openai":
        return {"tools": llm_client.mcp.to_openai_tools(server_name=server)}
    else:
        tools = [
            {**t.to_mcp_dict(), "server": t.server_name}
            for t in llm_client.mcp.list_tools(server_name=server)
        ]
        return {"tools": tools}


@router.post("/mcp/v1/call")
async def mcp_call_tool(req: Dict[str, Any]):
    """Direct REST invocation of an MCP tool."""
    if not hasattr(llm_client, "mcp") or not llm_client.mcp:
        raise HTTPException(503, "MCP subsystem not initialized on gateway.")

    name = req.get("name")
    if not name:
        raise HTTPException(400, "Missing 'name' in tool call request.")

    arguments = req.get("arguments") or {}
    timeout = float(req.get("timeout", 30.0))

    result = await llm_client.mcp.call_tool(name, arguments=arguments, timeout=timeout)
    return JSONResponse(
        status_code=200 if not result.is_error else 400,
        content=result.to_mcp_dict(),
    )


@router.post("/mcp/v1/tools/register")
async def mcp_register_tool(req: Dict[str, Any], _: str = Depends(auth)):
    """Register an MCP tool definition via REST (Admin authenticated + SSRF validated)."""
    if not hasattr(llm_client, "mcp") or not llm_client.mcp:
        raise HTTPException(503, "MCP subsystem not initialized on gateway.")

    name = (req.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Tool 'name' is required.")

    description = req.get("description", "")
    input_schema = (
        req.get("input_schema")
        or req.get("inputSchema")
        or req.get("parameters")
        or {"type": "object", "properties": {}}
    )
    server_name = req.get("server_name") or req.get("server") or "custom"

    endpoint = (req.get("endpoint") or req.get("endpoint_url") or "").strip()
    if endpoint:
        from veloroute.core.webhooks import WebhookDispatcher
        try:
            endpoint = WebhookDispatcher.validate_webhook_url(endpoint)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

        import httpx

        async def _remote_handler(**kwargs):
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                res = await http_client.post(endpoint, json=kwargs)
                res.raise_for_status()
                return res.json()

        handler = _remote_handler
    else:
        static_response = req.get("mock_response")

        def _echo_handler(**kwargs):
            if static_response is not None:
                return static_response
            return {"status": "success", "tool": name, "received": kwargs}

        handler = _echo_handler

    tool = llm_client.mcp.register_tool(
        name=name,
        handler=handler,
        description=description,
        input_schema=input_schema,
        server_name=server_name,
    )
    return {"registered": True, "tool": {**tool.to_mcp_dict(), "server": tool.server_name}}


@router.delete("/mcp/v1/tools/{name}")
async def mcp_unregister_tool(name: str, _: str = Depends(auth)):
    """Unregister a custom MCP tool."""
    if not hasattr(llm_client, "mcp") or not llm_client.mcp:
        raise HTTPException(503, "MCP subsystem not initialized on gateway.")
    existing = llm_client.mcp.get_tool(name)
    if not existing:
        raise HTTPException(404, f"Tool '{name}' not found.")
    if existing.server_name == "system":
        raise HTTPException(400, f"Built-in system tool '{name}' cannot be deleted (use policy deny-list instead).")
    llm_client.mcp.unregister_tool(name)
    return {"status": "ok", "deleted": name}


@router.get("/mcp/v1/health")
async def mcp_health():
    """Health check for MCP subsystem."""
    has_mcp = hasattr(llm_client, "mcp") and llm_client.mcp is not None
    tools_count = len(llm_client.mcp.list_tools()) if has_mcp else 0
    return {
        "status": "healthy" if has_mcp else "unavailable",
        "mcp_enabled": has_mcp,
        "tools_count": tools_count,
    }


@router.get("/api/v1/mcp/audit")
async def get_mcp_security_audit(_: str = Depends(auth)):
    """Run MCP security posture and tool schema audit."""
    if not hasattr(llm_client, "mcp") or not llm_client.mcp:
        raise HTTPException(503, "MCP subsystem not initialized on gateway.")
    return llm_client.mcp.audit_security()


@router.get("/api/v1/mcp/policy")
async def get_mcp_policy(_: str = Depends(auth)):
    """Retrieve current MCP security authorization and sandboxing policy."""
    if not hasattr(llm_client, "mcp") or not llm_client.mcp:
        raise HTTPException(503, "MCP subsystem not initialized on gateway.")
    return llm_client.mcp.get_policy()


@router.post("/api/v1/mcp/policy")
async def update_mcp_policy(req: Dict[str, Any], _: str = Depends(auth)):
    """Update MCP security authorization and sandboxing policy."""
    if not hasattr(llm_client, "mcp") or not llm_client.mcp:
        raise HTTPException(503, "MCP subsystem not initialized on gateway.")
    return llm_client.mcp.set_policy(
        mode=req.get("mode"),
        allowed_tools=req.get("allowed_tools"),
        denied_tools=req.get("denied_tools"),
        block_dangerous_args=req.get("block_dangerous_args"),
    )

