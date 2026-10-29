"""
Custom exceptions for LLMCycle.
All errors map from HTTP status codes and provider payloads (OpenAI, Anthropic, Gemini, DeepSeek, Groq, etc.)
so the router knows exactly what to do: retry, rotate key, failover, or stop.
"""
import json
from typing import Optional, Any, List

class LLMCycleError(Exception):
    """Base error for all LLMCycle exceptions."""
    def __init__(self, message: str, provider: str = "", model: str = "", status_code: int = 0):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.status_code = status_code

class RateLimitError(LLMCycleError):
    """429: Rate limit exceeded (RPM/TPM). Rotate key and retry."""
    pass

class AuthenticationError(LLMCycleError):
    """401: Invalid API key or unauthenticated. Disable key permanently."""
    pass

class PermissionDeniedError(LLMCycleError):
    """403: Forbidden, permission denied, country blocked or organization restricted."""
    pass

class NotFoundError(LLMCycleError):
    """404: Resource, model, or deployment not found."""
    pass

class BadRequestError(LLMCycleError):
    """400: Malformed request or invalid parameters."""
    pass

class ProviderError(LLMCycleError):
    """General provider-side error. Try next provider."""
    pass

class QuotaExceededError(LLMCycleError):
    """402 or 429 with quota message: Key quota exhausted or billing required."""
    pass

class ContentPolicyError(LLMCycleError):
    """400/403: Content policy or safety filter violation. Do NOT retry - fail fast."""
    pass

class InternalServerError(LLMCycleError):
    """500: Provider internal server error."""
    pass

class BadGatewayError(LLMCycleError):
    """502: Bad gateway from upstream provider or proxy."""
    pass

class ServiceUnavailableError(LLMCycleError):
    """503/529: Provider overloaded or temporarily unavailable."""
    pass

class GatewayTimeoutError(LLMCycleError):
    """504: Gateway timeout waiting for provider response."""
    pass

class APIConnectionError(LLMCycleError):
    """Network connection, DNS, or socket failure connecting to provider."""
    pass

class APIResponseError(LLMCycleError):
    """Provider returned unexpected, unparseable, or invalid response body."""
    pass

class StreamInterruptedError(LLMCycleError):
    """Mid-stream disconnection. Contains partial text generated so far."""
    def __init__(self, message: str, partial_text: str = "", **kwargs):
        super().__init__(message, **kwargs)
        self.partial_text = partial_text

class AllProvidersFailedError(LLMCycleError):
    """Raised when every provider in the fallback chain fails."""
    def __init__(self, errors: list):
        if errors:
            msg = f"All {len(errors)} providers failed. Last error: {errors[-1]}"
        else:
            msg = "All providers failed. No errors recorded (the model may not be supported by any configured provider)."
        super().__init__(msg)
        self.errors = errors

class MaxToolCallsExceededError(LLMCycleError):
    """
    Raised when an agentic tool-calling loop exceeds max_tool_calls.

    Attributes:
        tool_call_count:   How many tool calls were executed before stopping.
        max_tool_calls:    The configured limit.
        partial_messages:  The message list accumulated so far.
    """
    def __init__(self, tool_call_count: int, max_tool_calls: int, partial_messages: list = None):
        super().__init__(
            f"Tool call loop exceeded limit: {tool_call_count}/{max_tool_calls} calls used."
        )
        self.tool_call_count = tool_call_count
        self.max_tool_calls = max_tool_calls
        self.partial_messages = partial_messages or []

class BudgetExceededError(LLMCycleError):
    """
    Raised when accumulated cost on a client exceeds max_cost_usd.

    Attributes:
        spent:  Total USD spent so far (tracked by storage).
        budget: Configured max_cost_usd limit.
    """
    def __init__(self, spent: float, budget: float):
        super().__init__(f"Budget exceeded: ${spent:.4f} spent of ${budget:.4f} limit.")
        self.spent = spent
        self.budget = budget

class ContextWindowError(LLMCycleError):
    """
    Raised when the prompt exceeds the model's context window
    and auto-truncation is disabled.

    Attributes:
        token_count:   Estimated token count of the prompt.
        context_limit: Model's maximum context window.
    """
    def __init__(self, token_count: int = 0, context_limit: int = 0, model: str = "", message: str = ""):
        msg = message or f"Prompt has ~{token_count} tokens but model context is {context_limit} tokens."
        super().__init__(
            msg,
            model=model,
        )
        self.token_count = token_count
        self.context_limit = context_limit

class StructuredOutputError(LLMCycleError):
    """
    Raised when the LLM response cannot be parsed into the requested Pydantic schema.

    Attributes:
        raw_response: The raw text returned by the model.
    """
    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response


# ─── Comprehensive HTTP Error Classifier ─────────────────────────────────────

def _extract_error_detail(response_text: str) -> str:
    """Extract human-readable error message from OpenAI, Anthropic, Gemini, or DeepSeek JSON."""
    if not response_text:
        return ""
    try:
        data = json.loads(response_text)
        if isinstance(data, dict):
            # 1. OpenAI / Groq / Mistral / DeepSeek format: {"error": {"message": ...}}
            err_obj = data.get("error")
            if isinstance(err_obj, dict):
                return err_obj.get("message") or err_obj.get("code") or str(err_obj)
            elif isinstance(err_obj, str):
                return err_obj

            # 2. Anthropic format: {"type": "error", "error": {"type": ..., "message": ...}}
            if "type" in data and isinstance(data.get("error"), dict):
                return data["error"].get("message", "")

            # 3. Gemini format: {"error": {"code": 400, "message": ..., "status": ...}}
            # handled by err_obj above

            # 4. Direct message field
            if "message" in data:
                return str(data["message"])
            if "detail" in data:
                return str(data["detail"])
    except Exception:
        pass
    return response_text


def classify_http_error(
    status_code: int, response_text: str, provider: str, model: str
) -> LLMCycleError:
    """
    Factory: Convert an HTTP status code and response payload into the correct
    unified typed LLMCycle exception.
    """
    raw_text = response_text or ""
    detail = _extract_error_detail(raw_text)
    text_lower = f"{raw_text.lower()} {detail.lower()}"

    # 1. Status 401 is always AuthenticationError
    if status_code == 401:
        return AuthenticationError(
            f"[{provider}] Auth failed (401): {detail or raw_text}",
            provider=provider, model=model, status_code=status_code,
        )

    # 2. Status 402 is always QuotaExceededError (Payment Required)
    if status_code == 402:
        return QuotaExceededError(
            f"[{provider}] Quota / Payment required (402): {detail or raw_text}",
            provider=provider, model=model, status_code=status_code,
        )

    # 3. Status 404 is always NotFoundError
    if status_code == 404:
        return NotFoundError(
            f"[{provider}] Not found (404): {detail or raw_text}",
            provider=provider, model=model, status_code=status_code,
        )

    # 4. Status 429: Rate limit or Quota exhaustion
    if status_code == 429:
        quota_indicators = (
            "insufficient_quota",
            "exceeded your current quota",
            "check your plan and billing",
            "credit balance is too low",
            "insufficient credit",
            "insufficient_balance",
            "account deactivated",
            "quota exhausted",
        )
        if any(ind in text_lower for ind in quota_indicators):
            return QuotaExceededError(
                f"[{provider}] Quota / Billing exceeded (429): {detail or raw_text}",
                provider=provider, model=model, status_code=status_code,
            )
        return RateLimitError(
            f"[{provider}] Rate limited (429): {detail or raw_text}",
            provider=provider, model=model, status_code=status_code,
        )

    # 5. Check for Context Window Exceeded (often returned under 400 or 413)
    context_window_indicators = (
        "context_length_exceeded",
        "maximum context length",
        "context limit",
        "string too long",
        "tokens exceed",
        "exceeds the available context size",
        "input too long",
        "max_tokens is too large",
        "prompt is too long",
        "exceeds the maximum number of tokens allowed",
    )
    if any(ind in text_lower for ind in context_window_indicators):
        return ContextWindowError(
            token_count=0,
            context_limit=0,
            model=model,
            message=f"[{provider}] Context limit exceeded ({status_code}): {detail or raw_text}",
        )

    # 6. Check for Content Policy / Safety violations (returned under 400 or 403)
    safety_indicators = (
        "content_policy",
        "content policy",
        "content_filter",
        "content filter",
        "safety_policy",
        "safety policy",
        "safety filter",
        "blocked by safety",
        "moderation",
        "prompt was filtered",
        "inappropriate content",
        "policy violation",
        "terms of service violation",
    )
    if any(ind in text_lower for ind in safety_indicators):
        return ContentPolicyError(
            f"[{provider}] Content policy ({status_code}): {detail or raw_text}",
            provider=provider, model=model, status_code=status_code,
        )

    # 7. Status code mappings for other 4xx and 5xx
    if status_code == 403:
        return PermissionDeniedError(
            f"[{provider}] Permission denied (403): {detail or raw_text}",
            provider=provider, model=model, status_code=status_code,
        )

    if status_code in (400, 413, 422):
        return BadRequestError(
            f"[{provider}] Bad request ({status_code}): {detail or raw_text}",
            provider=provider, model=model, status_code=status_code,
        )

    if status_code == 500:
        return InternalServerError(
            f"[{provider}] Internal server error (500): {detail or raw_text[:200]}",
            provider=provider, model=model, status_code=status_code,
        )

    if status_code == 502:
        return BadGatewayError(
            f"[{provider}] Bad gateway (502): {detail or raw_text[:200]}",
            provider=provider, model=model, status_code=status_code,
        )

    if status_code in (503, 529):
        return ServiceUnavailableError(
            f"[{provider}] Service unavailable ({status_code}): {detail or raw_text[:200]}",
            provider=provider, model=model, status_code=status_code,
        )

    if status_code in (504, 408):
        return GatewayTimeoutError(
            f"[{provider}] Gateway timeout ({status_code}): {detail or raw_text[:200]}",
            provider=provider, model=model, status_code=status_code,
        )

    # Fallback generic provider error
    return ProviderError(
        f"[{provider}] HTTP {status_code}: {detail or raw_text[:200]}",
        provider=provider, model=model, status_code=status_code,
    )
