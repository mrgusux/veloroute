"""
Production schema models with Pydantic v2.
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, ConfigDict, Field
import time


class Message(BaseModel):
    """
    A single chat message.

    Unknown fields are intentionally preserved.  Providers increasingly rely on
    OpenAI extensions that are not part of the base schema (``cache_control``,
    ``reasoning_content``, ``refusal``, ``audio``, ``annotations`` …).  Dropping
    them silently changes request semantics, so they are forwarded verbatim.
    """
    model_config = ConfigDict(extra="allow")

    role: str
    content: Optional[Union[str, List[Dict[str, Any]]]] = None
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None



class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: List[Message]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop: Optional[Union[str, List[str]]] = None
    tools: Optional[List[Dict[str, Any]]] = None       # OpenAI tool definitions
    tool_choice: Optional[Any] = None                  # "auto" | "none" | {type, function}
    response_format: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None
    user: Optional[str] = None
    n: Optional[int] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = None
    parallel_tool_calls: Optional[bool] = None
    stream_options: Optional[Dict[str, Any]] = None
    reasoning_effort: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

    def to_api_dict(self) -> dict:
        """Serialize for sending to OpenAI-compatible API."""
        d = self.model_dump(exclude_none=True, exclude={"extra"})
        d["messages"] = [m.model_dump(exclude_none=True) for m in self.messages]
        if self.extra:
            d.update(self.extra)
        return d


class ToolParameter(BaseModel):
    """A single parameter definition for a Tool."""
    type: str = "string"
    description: str = ""
    enum: Optional[List[str]] = None


class Tool(BaseModel):
    """
    A clean, Pythonic way to define an LLM tool (function).

    Instead of writing raw OpenAI-format dicts, use this class:

        from llmcycle import Tool, ToolParameter

        weather_tool = Tool(
            name="get_weather",
            description="Get the current weather for a city.",
            parameters={
                "city": ToolParameter(type="string", description="City name, e.g. London"),
                "unit": ToolParameter(type="string", description="Unit", enum=["celsius", "fahrenheit"]),
            },
            required=["city"],
        )

        response = await client.complete_with_tools(
            model="openai/gpt-4o-mini",
            prompt="What is the weather in London?",
            tools=[weather_tool],     # ← pass Tool objects directly
            tool_executor=my_handler,
        )
    """
    name: str
    description: str = ""
    parameters: Dict[str, ToolParameter] = Field(default_factory=dict)
    required: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to OpenAI-compatible tool definition dict."""
        props = {}
        for param_name, param in self.parameters.items():
            prop: Dict[str, Any] = {"type": param.type, "description": param.description}
            if param.enum:
                prop["enum"] = param.enum
            props[param_name] = prop

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": self.required or list(self.parameters.keys()),
                },
            },
        }


class CompletionResponse(BaseModel):
    id: str
    model: str
    provider: str
    content: str
    reasoning_content: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: Optional[float] = None
    created_at: float = Field(default_factory=time.time)
    tool_calls: Optional[List[Any]] = None  # Populated when model returns tool calls
    # ── Reliability / provenance metadata ────────────────────────────────
    request_id: Optional[str] = None       # internal storage request id
    finish_reason: Optional[str] = None
    fallback_used: bool = False            # a provider/key failed before success
    retries: int = 0                       # failed attempts before success
    cached: bool = False                   # served from prompt/semantic cache


class StreamChunk(BaseModel):
    content: str
    model: str
    provider: str
    reasoning_content: Optional[str] = None
    done: bool = False


class StreamEvent(BaseModel):
    """
    Structured streaming event.

    ``LLMCycle.stream()`` keeps yielding plain strings for backwards
    compatibility.  ``LLMCycle.stream_events()`` yields these objects so
    callers can faithfully forward reasoning content, tool-call deltas,
    usage and finish reasons.
    """
    type: str                               # content|reasoning|tool_call|usage|finish|done|error
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_call: Optional[Dict[str, Any]] = None
    usage: Optional[Dict[str, int]] = None
    finish_reason: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    id: Optional[str] = None
    error: Optional[str] = None
    fallback_used: bool = False
    retries: int = 0


class EmbeddingUsage(BaseModel):
    prompt_tokens: int = 0
    total_tokens: int = 0


class EmbeddingData(BaseModel):
    object: str = "embedding"
    index: int = 0
    embedding: List[float] = Field(default_factory=list)


class EmbeddingRequest(BaseModel):
    model: str
    input: Union[str, List[str], List[int], List[List[int]]]
    encoding_format: Optional[str] = None
    dimensions: Optional[int] = None
    user: Optional[str] = None

    def to_api_dict(self) -> dict:
        d = self.model_dump(exclude_none=True)
        return d


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData] = Field(default_factory=list)
    model: str = ""
    usage: EmbeddingUsage = Field(default_factory=EmbeddingUsage)
    provider: Optional[str] = None
    latency_ms: float = 0.0

