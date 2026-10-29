"""
Storage data models — Pydantic v2.
Entities: Workplace → Team → User → Session → Request → ToolCall → Feedback → History
"""
from __future__ import annotations
import time
import uuid
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field


def _uid() -> str:
    return str(uuid.uuid4())

def _now() -> float:
    return time.time()


# ─── Request Status ───────────────────────────────────────────────────────────

RequestStatus = Literal["success", "error", "cancelled", "timeout", "fallback"]
"""
Request lifecycle statuses:
  success   - completed normally
  error     - provider returned an error
  cancelled - mid-stream or pre-response cancellation by the caller
  timeout   - exceeded the configured timeout_ms
  fallback  - succeeded but only after failing at least one provider
"""


# ─── Org Entities ─────────────────────────────────────────────────────────────

class Workplace(BaseModel):
    id: str = Field(default_factory=_uid)
    name: str
    settings: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Team(BaseModel):
    id: str = Field(default_factory=_uid)
    name: str
    workplace_id: str
    member_ids: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class User(BaseModel):
    id: str = Field(default_factory=_uid)
    username: str
    email: Optional[str] = None
    role: str = "member"           # "admin" | "member" | "viewer"
    team_id: Optional[str] = None
    workplace_id: Optional[str] = None
    hashed_password: Optional[str] = None
    created_at: float = Field(default_factory=_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    id: str = Field(default_factory=_uid)
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    model: str = ""
    started_at: float = Field(default_factory=_now)
    ended_at: Optional[float] = None
    total_requests: int = 0
    total_tokens: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ─── Core Request ─────────────────────────────────────────────────────────────

class LLMRequest(BaseModel):
    """
    A single LLM request lifecycle record.

    Auto-saved by LLMCycle when storage= is configured, or saved manually.

    Status values:
        success    - completed normally
        error      - provider returned an error
        cancelled  - caller cancelled mid-stream (asyncio.CancelledError or stop_event)
        timeout    - exceeded timeout_ms limit
        fallback   - succeeded but after at least one provider failure

    Tool calls: if the model returned function/tool calls, they are saved
    separately via save_tool_call() and linked by request_id.

    Cost: if cost_usd is populated, analytics can aggregate total spend.
    """
    id: str = Field(default_factory=_uid)
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    workplace_id: Optional[str] = None
    # Multi-turn / agentic chaining
    parent_request_id: Optional[str] = None  # links to the parent request in a tool loop
    turn_number: int = 0                      # 0 = first turn, 1 = after first tool call, etc.
    model: str
    provider: str = ""
    prompt: str = ""
    response: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0               # auto-computed if not set
    latency_ms: float = 0.0
    time_to_first_token_ms: Optional[float] = None  # streaming only
    status: str = "success"             # see RequestStatus
    error: Optional[str] = None
    fallback_used: bool = False
    retries: int = 0
    cancelled_at: Optional[float] = None   # set when status="cancelled"
    timeout_ms: Optional[float] = None     # configured timeout if any
    # Cost tracking
    cost_usd: Optional[float] = None           # computed or externally set
    input_cost_per_1k: Optional[float] = None  # price used for input tokens
    output_cost_per_1k: Optional[float] = None # price used for output tokens
    # Metadata
    tags: List[str] = Field(default_factory=list)  # free-form labels
    has_tool_calls: bool = False           # True if tool calls were returned
    is_cached: bool = False                # True if served from prompt cache
    created_at: float = Field(default_factory=_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        # Auto-compute total_tokens if not provided
        if self.total_tokens == 0 and (self.prompt_tokens or self.completion_tokens):
            self.total_tokens = self.prompt_tokens + self.completion_tokens
        # Auto-compute cost_usd from pricing if not set
        if self.cost_usd is None and self.input_cost_per_1k and self.output_cost_per_1k:
            self.cost_usd = (
                (self.prompt_tokens / 1000) * self.input_cost_per_1k
                + (self.completion_tokens / 1000) * self.output_cost_per_1k
            )


# ─── Tool Calls ───────────────────────────────────────────────────────────────

class ToolCall(BaseModel):
    """
    A single tool/function call returned by the LLM.

    Linked to the parent LLMRequest via request_id.

    Usage::

        tool = ToolCall(
            request_id=req.id,
            name="get_weather",
            arguments={"city": "London"},
        )
        await store.save_tool_call(tool)

        # After executing the tool, save the result
        tool.result = '{"temp": 18, "condition": "cloudy"}'
        tool.executed_at = time.time()
        await store.update_tool_call(tool)
    """
    id: str = Field(default_factory=_uid)
    request_id: str                        # parent LLMRequest.id
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    name: str                              # function name
    arguments: Dict[str, Any] = Field(default_factory=dict)  # parsed args
    arguments_raw: str = ""               # raw JSON string from LLM
    result: Optional[str] = None          # tool execution result (JSON string)
    result_tokens: int = 0                # tokens in the result
    executed_at: Optional[float] = None   # when the tool was executed
    status: str = "pending"               # "pending" | "success" | "error"
    error: Optional[str] = None
    created_at: float = Field(default_factory=_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ─── Feedback ─────────────────────────────────────────────────────────────────

class RequestFeedback(BaseModel):
    """
    Human feedback on a completed LLMRequest (thumbs up/down, rating, comment).

    Usage::

        await store.save_feedback(RequestFeedback(
            request_id=req.id,
            user_id="user-123",
            rating=5,
            thumbs_up=True,
            comment="Perfect answer!",
        ))

        # Aggregate
        fb = await store.analytics.feedback_summary()
        # {"avg_rating": 4.2, "thumbs_up_rate": 0.91, "total": 340}
    """
    id: str = Field(default_factory=_uid)
    request_id: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    thumbs_up: Optional[bool] = None     # True / False / None (no vote)
    rating: Optional[int] = None         # 1-5 star rating
    comment: Optional[str] = None        # free text
    tags: List[str] = Field(default_factory=list)  # e.g. ["hallucination", "too_long"]
    created_at: float = Field(default_factory=_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ─── History ──────────────────────────────────────────────────────────────────

class HistoryMessage(BaseModel):
    id: str = Field(default_factory=_uid)
    session_id: str
    request_id: Optional[str] = None
    role: str                              # "user" | "assistant" | "system" | "tool"
    content: str
    tool_call_id: Optional[str] = None     # for role="tool" — links to ToolCall.id
    created_at: float = Field(default_factory=_now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

# ─── Config Store ─────────────────────────────────────────────────────────────

class StoreConfig(BaseModel):
    """Generic Key-Value store for dynamic configurations (groups, etc)."""
    key: str
    value: Dict[str, Any] = Field(default_factory=dict)
    updated_at: float = Field(default_factory=_now)
