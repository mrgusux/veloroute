"""
Model Context Protocol (MCP) Gateway & Tool Registry
======================================================
Provides standard Model Context Protocol (Anthropic MCP standard) tool registration,
routing, validation, and JSON-RPC 2.0 proxy execution.
Compatible with Cursor, Claude Code, OpenCode, and enterprise agent gateways
(ContextForge, EnkryptAI, AshrafMd-1 mcp-router, Plano, Obot).
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Callable, Dict, List, Optional, Union, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """Definition of an MCP tool."""
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    handler: Optional[Callable] = None
    server_name: str = "local"
    enabled: bool = True

    def to_mcp_dict(self) -> Dict[str, Any]:
        """Format for MCP tools/list protocol."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema or {"type": "object", "properties": {}},
        }

    def to_openai_dict(self) -> Dict[str, Any]:
        """Convert MCP tool to OpenAI function calling tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema or {"type": "object", "properties": {}},
            },
        }


@dataclass
class MCPCallResult:
    """Result of an MCP tool invocation."""
    content: List[Dict[str, Any]]
    is_error: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_mcp_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "isError": self.is_error,
        }

    @classmethod
    def text(cls, text_content: str, is_error: bool = False, **meta) -> "MCPCallResult":
        return cls(
            content=[{"type": "text", "text": str(text_content)}],
            is_error=is_error,
            metadata=meta,
        )

    @classmethod
    def json_data(cls, data: Any, is_error: bool = False, **meta) -> "MCPCallResult":
        text_payload = json.dumps(data, indent=2, default=str)
        return cls(
            content=[{"type": "text", "text": text_payload}],
            is_error=is_error,
            metadata=meta,
        )


class MCPAuthMode(str, Enum):
    ALLOW_ALL = "allow_all"
    RESTRICTED = "restricted"
    ALLOWLIST_ONLY = "allowlist_only"


@dataclass
class MCPAuthorizationPolicy:
    """Security authorization and sandboxing policy for MCP tool calls."""
    mode: MCPAuthMode = MCPAuthMode.ALLOW_ALL
    allowed_tools: List[str] = field(default_factory=list)
    denied_tools: List[str] = field(default_factory=list)
    block_dangerous_args: bool = True
    dangerous_patterns: List[str] = field(default_factory=lambda: [
        r"(rm\s+-rf|del\s+/f|format\s+[a-z]:|rmdir\s+/s)",
        r"(/etc/shadow|/etc/passwd|C:\\Windows\\System32\\SAM)",
        r"(DROP\s+DATABASE|DROP\s+TABLE|TRUNCATE\s+TABLE)",
        r"(\beval\s*\(|\bexec\s*\(|__import__\s*\()",
    ])

    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Verify if a tool and its arguments are authorized according to policy."""
        # 1. Mode check
        if self.mode == MCPAuthMode.ALLOWLIST_ONLY:
            if tool_name not in self.allowed_tools:
                return False, f"Tool '{tool_name}' is not permitted under strict allowlist policy."

        if self.mode in (MCPAuthMode.RESTRICTED, MCPAuthMode.ALLOW_ALL):
            if tool_name in self.denied_tools:
                return False, f"Tool '{tool_name}' is explicitly denied by security policy."

        # 2. Argument safety inspection if enabled
        if self.block_dangerous_args and arguments:
            arg_str = json.dumps(arguments, default=str)
            for pattern in self.dangerous_patterns:
                if re.search(pattern, arg_str, re.IGNORECASE):
                    return False, f"Tool call blocked: argument matched dangerous payload pattern '{pattern}'"

        return True, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value if isinstance(self.mode, MCPAuthMode) else str(self.mode),
            "allowed_tools": list(self.allowed_tools),
            "denied_tools": list(self.denied_tools),
            "block_dangerous_args": self.block_dangerous_args,
            "dangerous_patterns_count": len(self.dangerous_patterns),
        }


class MCPRegistry:
    """
    Central registry for Model Context Protocol (MCP) tools and JSON-RPC dispatch.
    Thread-safe and async-compatible.
    """

    def __init__(self, llm_client: Optional[Any] = None):
        self._tools: Dict[str, MCPTool] = {}
        self._lock = threading.Lock()
        self.llm_client = llm_client
        self.policy = MCPAuthorizationPolicy()
        self._register_default_tools()

    def register_tool(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        input_schema: Optional[Dict[str, Any]] = None,
        server_name: str = "local",
    ) -> MCPTool:
        """Register a Python callable (sync or async) as an MCP tool."""
        schema = input_schema or {"type": "object", "properties": {}}
        tool = MCPTool(
            name=name,
            description=description or getattr(handler, "__doc__", "") or "",
            input_schema=schema,
            handler=handler,
            server_name=server_name,
        )
        with self._lock:
            self._tools[name] = tool
        logger.info(f"Registered MCP tool '{name}' (server: {server_name})")
        return tool

    def tool(
        self,
        name: Optional[str] = None,
        description: str = "",
        input_schema: Optional[Dict[str, Any]] = None,
        server_name: str = "local",
    ) -> Callable:
        """Decorator to register a function as an MCP tool (FastMCP style)."""
        def decorator(fn: Callable) -> Callable:
            tool_name = name or fn.__name__
            self.register_tool(
                name=tool_name,
                handler=fn,
                description=description or getattr(fn, "__doc__", "") or "",
                input_schema=input_schema,
                server_name=server_name,
            )
            return fn
        return decorator

    def register_tool_object(self, tool: MCPTool) -> None:
        """Register an existing MCPTool object."""
        with self._lock:
            self._tools[tool.name] = tool
        logger.info(f"Registered MCP tool '{tool.name}' (server: {tool.server_name})")

    def unregister_tool(self, name: str) -> bool:
        """Remove a tool by name."""
        with self._lock:
            return self._tools.pop(name, None) is not None

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Retrieve a registered tool by name."""
        with self._lock:
            return self._tools.get(name)

    def list_tools(self, server_name: Optional[str] = None) -> List[MCPTool]:
        """List registered tools, optionally filtered by server."""
        with self._lock:
            tools = list(self._tools.values())
        if server_name:
            tools = [t for t in tools if t.server_name == server_name]
        return [t for t in tools if t.enabled]

    def to_openai_tools(self, server_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Export all registered MCP tools in OpenAI tool calling format."""
        return [t.to_openai_dict() for t in self.list_tools(server_name)]

    def get_policy(self) -> Dict[str, Any]:
        """Return current MCP authorization and execution policy."""
        return self.policy.to_dict()

    def set_policy(
        self,
        mode: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        denied_tools: Optional[List[str]] = None,
        block_dangerous_args: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Update MCP authorization and execution policy."""
        if mode:
            try:
                self.policy.mode = MCPAuthMode(mode.lower())
            except ValueError:
                self.policy.mode = MCPAuthMode.ALLOW_ALL
        if allowed_tools is not None:
            self.policy.allowed_tools = list(allowed_tools)
        if denied_tools is not None:
            self.policy.denied_tools = list(denied_tools)
        if block_dangerous_args is not None:
            self.policy.block_dangerous_args = bool(block_dangerous_args)
        return self.policy.to_dict()

    async def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> MCPCallResult:
        """
        Execute an MCP tool with argument validation and timeout protection.
        """
        args = arguments or {}

        # 1. Security Authorization & Sandboxing policy check
        is_auth, auth_err = self.policy.validate_tool_call(name, args)
        if not is_auth:
            return MCPCallResult.text(
                f"Tool execution blocked by security policy: {auth_err}",
                is_error=True,
                status_code=403,
            )

        tool = self.get_tool(name)
        if not tool or not tool.enabled:
            return MCPCallResult.text(f"Tool '{name}' not found or disabled.", is_error=True)

        if not tool.handler:
            return MCPCallResult.text(f"Tool '{name}' has no executable handler registered.", is_error=True)

        args = arguments or {}

        # Validate required arguments if defined in schema
        schema = tool.input_schema or {}
        required_fields = schema.get("required", [])
        missing = [rf for rf in required_fields if rf not in args]
        if missing:
            return MCPCallResult.text(
                f"Missing required argument(s) for tool '{name}': {', '.join(missing)}",
                is_error=True,
            )

        t0 = time.monotonic()
        try:
            handler = tool.handler
            # Inspect signature to gracefully filter arguments if handler does not accept **kwargs
            sig = inspect.signature(handler)
            has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            if not has_varkw:
                valid_keys = set(sig.parameters.keys())
                call_args = {k: v for k, v in args.items() if k in valid_keys}
            else:
                call_args = dict(args)

            if inspect.iscoroutinefunction(handler):
                coro = handler(**call_args)
                raw_result = await asyncio.wait_for(coro, timeout=timeout)
            else:
                loop = asyncio.get_running_loop()
                raw_result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: handler(**call_args)),
                    timeout=timeout,
                )

            latency_ms = round((time.monotonic() - t0) * 1000, 2)

            if isinstance(raw_result, MCPCallResult):
                raw_result.metadata["latency_ms"] = latency_ms
                return raw_result
            elif isinstance(raw_result, (dict, list)):
                return MCPCallResult.json_data(raw_result, latency_ms=latency_ms)
            else:
                text_out = self._compress_tool_output(str(raw_result))
                return MCPCallResult.text(text_out, latency_ms=latency_ms)

        except asyncio.TimeoutError:
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            logger.warning(f"MCP tool '{name}' timed out after {timeout}s")
            return MCPCallResult.text(
                f"Tool '{name}' execution timed out after {timeout}s",
                is_error=True,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            logger.error(f"MCP tool '{name}' raised error: {exc}", exc_info=True)
            return MCPCallResult.text(
                f"Error executing tool '{name}': {str(exc)}",
                is_error=True,
                latency_ms=latency_ms,
            )

    @staticmethod
    def _compress_tool_output(text: str) -> str:
        """
        RTK-style (Rust Token Killer) tool output compression:
        strips ANSI escape sequences, progress-bar carriage returns, and excessive blank lines.
        """
        if not text:
            return text
        # Strip ANSI color/cursor codes
        cleaned = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
        # Collapse 3+ consecutive newlines to 2
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip() if len(cleaned) != len(text) else text

    def audit_security(self) -> Dict[str, Any]:
        """
        Audit registered MCP tools and security policy for OWASP Agentic / MCP risks
        (schema completeness, dangerous argument blocking, remote proxy endpoints).
        """
        tools = self.list_tools()
        findings: List[Dict[str, Any]] = []
        score = 100

        if not self.policy.block_dangerous_args:
            score -= 30
            findings.append({
                "severity": "high",
                "tool": "global_policy",
                "issue": "Dangerous argument payload blocking is disabled.",
                "remediation": "Enable block_dangerous_args in MCP Authorization Policy.",
            })

        for t in tools:
            schema = t.input_schema or {}
            props = schema.get("properties", {})
            if not t.description or len(t.description.strip()) < 10:
                score -= 5
                findings.append({
                    "severity": "low",
                    "tool": t.name,
                    "issue": "Tool description is missing or too terse for safe LLM selection.",
                    "remediation": "Provide a clear description of purpose and side effects.",
                })
            for prop_name, prop_spec in props.items():
                if isinstance(prop_spec, dict) and not prop_spec.get("type"):
                    score -= 5
                    findings.append({
                        "severity": "medium",
                        "tool": t.name,
                        "issue": f"Parameter '{prop_name}' lacks an explicit JSON schema type.",
                        "remediation": "Specify explicit 'type' ('string', 'number', 'boolean') in inputSchema.",
                    })

        score = max(0, min(100, score))
        return {
            "score": score,
            "status": "secure" if score >= 85 else ("warning" if score >= 60 else "critical"),
            "total_tools_audited": len(tools),
            "tool_count": len(tools),
            "policy_mode": self.policy.mode.value if isinstance(self.policy.mode, MCPAuthMode) else str(self.policy.mode),
            "block_dangerous_args": self.policy.block_dangerous_args,
            "findings": findings,
        }

    async def handle_jsonrpc(
        self, request_data: Union[Dict[str, Any], List[Dict[str, Any]]]
    ) -> Union[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Handle a standard Model Context Protocol JSON-RPC 2.0 request or batch.
        Supports:
          - 'initialize'
          - 'notifications/initialized'
          - 'tools/list', 'tools/call'
          - 'resources/list', 'prompts/list'
          - 'ping', 'logging/setLevel', 'completion/complete'
        """
        if isinstance(request_data, list):
            if not request_data:
                return {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Invalid Request: empty batch"},
                }
            responses = []
            for item in request_data:
                if isinstance(item, dict):
                    resp = await self._handle_single_jsonrpc(item)
                    if resp is not None:
                        responses.append(resp)
                else:
                    responses.append({
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32600, "message": "Invalid Request: batch element must be object"},
                    })
            return responses

        if isinstance(request_data, dict):
            return await self._handle_single_jsonrpc(request_data)

        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request: expected object or array"},
        }

    async def _handle_single_jsonrpc(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        is_notification = "id" not in request_data
        req_id = request_data.get("id")
        method = request_data.get("method")
        params = request_data.get("params") or {}

        if not method:
            if is_notification:
                return None
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32600, "message": "Invalid Request: missing method"},
            }

        # Lifecycle notifications (Cursor, Claude Code, OpenCode)
        if method.startswith("notifications/") or method == "$/cancelRequest":
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {},
                        "prompts": {},
                    },
                    "serverInfo": {
                        "name": "veloroute-mcp-gateway",
                        "version": "2.1.0",
                    },
                },
            }

        elif method == "tools/list":
            tools = [t.to_mcp_dict() for t in self.list_tools()]
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools},
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            if not tool_name:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Missing 'name' in tools/call params"},
                }

            tool = self.get_tool(tool_name)
            if not tool or not tool.enabled:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool '{tool_name}' not found or disabled"},
                }

            result = await self.call_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result.to_mcp_dict(),
            }

        elif method in ("resources/list", "resources/templates/list"):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"resources": [], "resourceTemplates": []},
            }

        elif method == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"prompts": []},
            }

        elif method == "logging/setLevel":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {},
            }

        elif method == "completion/complete":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"completion": {"values": []}},
            }

        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {},
            }

        else:
            if is_notification:
                return None
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method '{method}' not found"},
            }

    def _register_default_tools(self) -> None:
        """Register built-in utility tools."""
        import ast
        import datetime
        import operator

        _SAFE_OPS = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod: operator.mod,
            ast.Pow: operator.pow,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        _SAFE_FUNCS = {
            "sin": math.sin, "cos": math.cos, "tan": math.tan,
            "sqrt": math.sqrt, "log": math.log, "exp": math.exp,
            "pi": math.pi, "e": math.e, "abs": abs, "round": round,
            "pow": pow,
        }

        def _eval_node(node):
            if isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float)):
                    return node.value
                raise ValueError("Only numeric constants are allowed.")
            elif isinstance(node, ast.BinOp):
                left = _eval_node(node.left)
                right = _eval_node(node.right)
                op_type = type(node.op)
                if op_type not in _SAFE_OPS:
                    raise ValueError(f"Unsupported binary operator: {op_type.__name__}")
                if op_type is ast.Pow and (isinstance(right, (int, float)) and right > 1000):
                    raise ValueError("Exponent too large (DoS protection).")
                return _SAFE_OPS[op_type](left, right)
            elif isinstance(node, ast.UnaryOp):
                operand = _eval_node(node.operand)
                op_type = type(node.op)
                if op_type not in _SAFE_OPS:
                    raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
                return _SAFE_OPS[op_type](operand)
            elif isinstance(node, ast.Name):
                if node.id in _SAFE_FUNCS:
                    return _SAFE_FUNCS[node.id]
                raise ValueError(f"Unsupported identifier: {node.id}")
            elif isinstance(node, ast.Call):
                func = _eval_node(node.func)
                args = [_eval_node(a) for a in node.args]
                return func(*args)
            raise ValueError(f"Unsupported expression construct: {type(node).__name__}")

        # 1. Calculator
        def _calculator(expression: str) -> str:
            """Safely evaluate mathematical expressions via AST."""
            clean_expr = expression.strip()
            if not clean_expr:
                return "0"
            if len(clean_expr) > 200:
                raise ValueError("Expression exceeds maximum allowed length.")
            tree = ast.parse(clean_expr, mode="eval")
            val = _eval_node(tree.body)
            return str(val)

        self.register_tool(
            name="calculator",
            handler=_calculator,
            description="Evaluate mathematical calculations (arithmetic, sqrt, trig, powers).",
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression, e.g. 'sqrt(144) * 2'"}
                },
                "required": ["expression"],
            },
            server_name="system",
        )

        # 2. Route estimator tool
        def _route_estimator(prompt: str, model: Optional[str] = None) -> Dict[str, Any]:
            """Estimate the routing target, complexity score, and estimated cost for a prompt."""
            if not self.llm_client:
                return {"error": "VeloRoute client not bound to MCP registry."}

            complexity = 0.0
            if hasattr(self.llm_client, "router") and hasattr(self.llm_client.router, "complexity_evaluator"):
                complexity = self.llm_client.router.complexity_evaluator.evaluate(prompt=prompt)

            target_model = model or "openai/gpt-4o"
            routes = self.llm_client.router.get_route(target_model, prompt=prompt) if hasattr(self.llm_client, "router") else [(target_model, target_model)]

            est_tokens = self.llm_client._estimate_tokens(prompt) if hasattr(self.llm_client, "_estimate_tokens") else len(prompt.split())
            est_cost = self.llm_client._estimate_cost(target_model, est_tokens, int(est_tokens * 0.5)) if hasattr(self.llm_client, "_estimate_cost") else 0.0

            return {
                "target_model": target_model,
                "complexity_score": complexity,
                "is_complex": complexity >= 0.5,
                "recommended_route": [{"provider": p, "model": m} for p, m in routes],
                "estimated_prompt_tokens": est_tokens,
                "estimated_cost_usd": est_cost,
            }

        self.register_tool(
            name="veloroute_route_estimate",
            handler=_route_estimator,
            description="Inspect VeloRoute dynamic route recommendation, complexity score, and cost estimate for a prompt.",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The user prompt to analyze"},
                    "model": {"type": "string", "description": "Optional model name or alias"}
                },
                "required": ["prompt"],
            },
            server_name="system",
        )

        # 3. System UTC Clock & Timestamp Converter
        def _system_clock() -> Dict[str, Any]:
            """Return current UTC ISO-8601 timestamp and epoch seconds."""
            now = datetime.datetime.now(datetime.timezone.utc)
            return {
                "utc_iso": now.isoformat(),
                "unix_epoch": round(now.timestamp(), 3),
                "date": now.strftime("%Y-%m-%d"),
                "day_of_week": now.strftime("%A"),
            }

        self.register_tool(
            name="system_clock",
            handler=_system_clock,
            description="Return current UTC ISO-8601 timestamp, date, and Unix epoch seconds.",
            input_schema={"type": "object", "properties": {}},
            server_name="system",
        )

        # 4. JSON Schema & Syntax Validator
        def _json_validator(payload: str) -> Dict[str, Any]:
            """Validate JSON syntax and report parsed structure summary."""
            try:
                parsed = json.loads(payload)
                kind = type(parsed).__name__
                keys = list(parsed.keys())[:25] if isinstance(parsed, dict) else []
                length = len(parsed) if isinstance(parsed, (dict, list, str)) else 1
                return {"valid": True, "type": kind, "length": length, "top_keys": keys}
            except Exception as exc:
                return {"valid": False, "error": str(exc)}

        self.register_tool(
            name="json_validator",
            handler=_json_validator,
            description="Validate JSON string syntax and inspect top-level keys and types.",
            input_schema={
                "type": "object",
                "properties": {
                    "payload": {"type": "string", "description": "JSON string to validate"}
                },
                "required": ["payload"],
            },
            server_name="system",
        )

        # 5. Markdown Structure & Heading Outliner
        def _markdown_outline(markdown: str) -> Dict[str, Any]:
            """Extract hierarchical headings and code block count from Markdown text."""
            headings = []
            for line in (markdown or "").splitlines():
                m = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
                if m:
                    headings.append({"level": len(m.group(1)), "title": m.group(2).strip()})
            code_blocks = len(re.findall(r"```", markdown or "")) // 2
            return {
                "heading_count": len(headings),
                "code_blocks": code_blocks,
                "headings": headings[:50],
            }

        self.register_tool(
            name="markdown_outline",
            handler=_markdown_outline,
            description="Extract structured TOC headings and code-block statistics from Markdown documents.",
            input_schema={
                "type": "object",
                "properties": {
                    "markdown": {"type": "string", "description": "Markdown text to outline"}
                },
                "required": ["markdown"],
            },
            server_name="system",
        )

        # 6. Token & Context Budget Counter
        def _token_counter(text: str, model: str = "openai/gpt-4o") -> Dict[str, Any]:
            """Estimate token count, word count, and input cost for a text payload."""
            words = len((text or "").split())
            chars = len(text or "")
            est_tokens = max(1, int(words * 1.3)) if words else 0
            cost = 0.0
            if self.llm_client and hasattr(self.llm_client, "_estimate_cost"):
                cost = self.llm_client._estimate_cost(model, est_tokens, 0)
            return {
                "model": model,
                "characters": chars,
                "words": words,
                "estimated_tokens": est_tokens,
                "estimated_input_cost_usd": round(cost, 8),
            }

        self.register_tool(
            name="token_counter",
            handler=_token_counter,
            description="Count estimated tokens, words, characters, and prompt cost for any text.",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to count tokens for"},
                    "model": {"type": "string", "description": "Target model for cost estimation"}
                },
                "required": ["text"],
            },
            server_name="system",
        )

        # 7. Prompt Security & PII Scanner
        def _prompt_security_scan(prompt: str) -> Dict[str, Any]:
            """Scan text for PII/secrets and adversarial prompt injection patterns."""
            from veloroute.core.guardrail import GuardrailManager
            from veloroute.core.injection import InjectionGuard

            gm = GuardrailManager()
            masked = gm.mask_prompt(prompt or "")
            inj = InjectionGuard().scan(prompt or "")
            return {
                "safe": (not inj.blocked) and (len(gm.mask_to_secret) == 0),
                "pii_or_secrets_found": len(gm.mask_to_secret),
                "redacted_preview": masked,
                "injection_score": inj.score,
                "injection_blocked": inj.blocked,
                "injection_matches": inj.matches,
            }

        self.register_tool(
            name="prompt_security_scan",
            handler=_prompt_security_scan,
            description="Scan any prompt or tool output for PII leaks, high-entropy secrets, and prompt injection attacks.",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Text payload to scan for security risks"}
                },
                "required": ["prompt"],
            },
            server_name="system",
        )
