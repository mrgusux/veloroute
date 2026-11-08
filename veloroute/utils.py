from typing import Tuple, Dict, Any, List, Optional, Union, Sequence, Mapping
import re
import math

def parse_model(model_str: str) -> Tuple[str, str]:
    """
    Parse a model string into (provider, model).
    
    Examples:
        "openai/gpt-4o" -> ("openai", "gpt-4o")
        "gpt-4o"        -> ("gpt-4o", "gpt-4o")
        "groq"          -> ("groq", "groq")
    """
    s = (model_str or "").strip()
    if "/" in s:
        parts = s.split("/", 1)
        return parts[0].strip().lower(), parts[1].strip()
    # Bare model name — return as-is; caller resolves provider
    return s.lower(), s


def is_free_model(
    model_id: str,
    raw_info: Optional[Dict[str, Any]] = None,
    provider_name: str = "",
    base_url: str = "",
) -> bool:
    """
    Detect whether an upstream model is free vs paid based on ID patterns,
    returned pricing metadata, tags, and local provider indicators.
    """
    m_lower = (model_id or "").lower().strip()
    p_lower = (provider_name or "").lower().strip()
    b_lower = (base_url or "").lower().strip()

    # 1. Local / Self-hosted providers are free
    if any(x in p_lower for x in ("ollama", "lm_studio", "vllm", "llamafile", "localai")) or "localhost" in b_lower or "127.0.0.1" in b_lower:
        return True

    # 2. Obvious free indicators in model name
    if any(pattern in m_lower for pattern in (":free", "/free", "free/", "-free", "free-", "_free", "free_", "(free)")):
        return True
    if m_lower.endswith("free") and ("-free" in m_lower or ":free" in m_lower or "free" == m_lower):
        return True

    # 3. Check raw upstream metadata
    if isinstance(raw_info, dict):
        if raw_info.get("is_free") is True or raw_info.get("free") is True:
            return True

        pricing = raw_info.get("pricing")
        if isinstance(pricing, dict):
            # Extract numeric prices safely without treating 0/0.0 as falsy
            def _get_price(keys: Sequence[str]) -> Optional[float]:
                for k in keys:
                    if k in pricing and pricing[k] is not None:
                        try:
                            return float(pricing[k])
                        except (ValueError, TypeError):
                            continue
                return None

            p_in = _get_price(("prompt", "input", "input_cost_per_token"))
            p_out = _get_price(("completion", "output", "output_cost_per_token"))

            # Free if both prompt and completion are zero
            if p_in is not None and p_out is not None:
                if p_in == 0.0 and p_out == 0.0:
                    return True
            # Or if prompt is zero and completion is not specified (e.g. embeddings)
            elif p_in is not None and p_in == 0.0:
                return True

        tags = raw_info.get("tags") or raw_info.get("capabilities") or []
        if isinstance(tags, list) and any(str(t).lower() == "free" for t in tags):
            return True

    # 4. Check internal default pricing registry if exact match has 0 pricing
    pricing_entry = DEFAULT_PRICING.get(model_id)
    if pricing_entry and pricing_entry.get("input") == 0.0 and pricing_entry.get("output") == 0.0:
        return True

    return False


# ─── Pricing registry (USD per 1K tokens) ─────────────────────────────────────
# Override / extend via client.pricing["gpt-4o"] = {"input": 0.005, "output": 0.015}
DEFAULT_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI
    "gpt-4.5":                  {"input": 0.075,    "output": 0.15},
    "gpt-4.5-preview":          {"input": 0.075,    "output": 0.15},
    "gpt-4o":                   {"input": 0.0025,   "output": 0.01},
    "gpt-4o-2024-08-06":        {"input": 0.0025,   "output": 0.01},
    "gpt-4o-2024-11-20":        {"input": 0.0025,   "output": 0.01},
    "chatgpt-4o-latest":        {"input": 0.005,    "output": 0.015},
    "gpt-4o-mini":              {"input": 0.00015,  "output": 0.0006},
    "gpt-4-turbo":              {"input": 0.01,     "output": 0.03},
    "gpt-4":                    {"input": 0.03,     "output": 0.06},
    "gpt-3.5-turbo":            {"input": 0.0005,   "output": 0.0015},
    "o1":                       {"input": 0.015,    "output": 0.06},
    "o1-2024-12-17":            {"input": 0.015,    "output": 0.06},
    "o1-preview":               {"input": 0.015,    "output": 0.06},
    "o1-mini":                  {"input": 0.003,    "output": 0.012},
    "o3":                       {"input": 0.010,    "output": 0.040},
    "o3-mini":                  {"input": 0.0011,   "output": 0.0044},
    "o4-mini":                  {"input": 0.0011,   "output": 0.0044},
    "text-embedding-3-small":   {"input": 0.00002,  "output": 0.0},
    "text-embedding-3-large":   {"input": 0.00013,  "output": 0.0},
    "text-embedding-ada-002":   {"input": 0.0001,   "output": 0.0},

    # Anthropic
    "claude-3-7-sonnet":        {"input": 0.003,    "output": 0.015},
    "claude-3-7-sonnet-latest": {"input": 0.003,    "output": 0.015},
    "claude-3-7-sonnet-thinking":{"input": 0.003,   "output": 0.015},
    "claude-3-5-sonnet":        {"input": 0.003,    "output": 0.015},
    "claude-3-5-sonnet-latest": {"input": 0.003,    "output": 0.015},
    "claude-3-5-haiku":         {"input": 0.0008,   "output": 0.004},
    "claude-3-5-haiku-latest":  {"input": 0.0008,   "output": 0.004},
    "claude-3-opus":            {"input": 0.015,    "output": 0.075},
    "claude-3-sonnet":          {"input": 0.003,    "output": 0.015},
    "claude-3-haiku":           {"input": 0.00025,  "output": 0.00125},

    # DeepSeek
    "deepseek-chat":            {"input": 0.00014,  "output": 0.00028},
    "deepseek-reasoner":        {"input": 0.00055,  "output": 0.00219},
    "deepseek-v3":              {"input": 0.00014,  "output": 0.00028},
    "deepseek-r1":              {"input": 0.00055,  "output": 0.00219},
    "deepseek-r1-distill-llama-70b": {"input": 0.00059, "output": 0.00079},
    "deepseek-r1-distill-qwen-32b":  {"input": 0.0002,  "output": 0.0002},

    # Google Gemini
    "gemini-2.5-pro":           {"input": 0.00125,  "output": 0.005},
    "gemini-2.5-flash":         {"input": 0.0001,   "output": 0.0004},
    "gemini-2.0-flash":         {"input": 0.0001,   "output": 0.0004},
    "gemini-2.0-flash-lite":    {"input": 0.000075, "output": 0.0003},
    "gemini-2.0-pro-exp":       {"input": 0.00125,  "output": 0.005},
    "gemini-1.5-pro":           {"input": 0.00125,  "output": 0.005},
    "gemini-1.5-flash":         {"input": 0.000075, "output": 0.0003},
    "gemini-1.5-flash-8b":      {"input": 0.0000375,"output": 0.00015},
    "text-embedding-004":       {"input": 0.000025, "output": 0.0},

    # Meta Llama
    "llama-3.3-70b":            {"input": 0.00059,  "output": 0.00079},
    "llama-3.1-405b":           {"input": 0.0024,   "output": 0.0024},
    "llama-3.1-70b":            {"input": 0.00059,  "output": 0.00079},
    "llama-3.1-8b":             {"input": 0.00005,  "output": 0.00008},
    "llama-3.2-1b":             {"input": 0.00004,  "output": 0.00004},
    "llama-3.2-3b":             {"input": 0.00006,  "output": 0.00006},
    "llama-3.2-11b-vision":     {"input": 0.00018,  "output": 0.00018},
    "llama-3.2-90b-vision":     {"input": 0.0009,   "output": 0.0009},
    "llama-3-70b":              {"input": 0.00059,  "output": 0.00079},
    "llama-3-8b":               {"input": 0.00005,  "output": 0.00008},

    # Mistral
    "mistral-large":            {"input": 0.002,    "output": 0.006},
    "mistral-large-2411":       {"input": 0.002,    "output": 0.006},
    "mistral-small":            {"input": 0.0002,   "output": 0.0006},
    "codestral":                {"input": 0.0003,   "output": 0.0009},
    "codestral-2501":           {"input": 0.0003,   "output": 0.0009},
    "pixtral-12b":              {"input": 0.00015,  "output": 0.00015},
    "mistral-nemo":             {"input": 0.00015,  "output": 0.00015},
    "mixtral-8x7b":             {"input": 0.00024,  "output": 0.00024},
    "mixtral-8x22b":            {"input": 0.002,    "output": 0.006},

    # Qwen
    "qwen-2.5-72b":             {"input": 0.00035,  "output": 0.0004},
    "qwen-2.5-32b":             {"input": 0.0002,   "output": 0.0002},
    "qwen-2.5-14b":             {"input": 0.0001,   "output": 0.0001},
    "qwen-2.5-7b":              {"input": 0.00005,  "output": 0.00005},
    "qwen-2.5-coder-32b":       {"input": 0.0002,   "output": 0.0002},
    "qwen-2.5-coder-7b":        {"input": 0.00005,  "output": 0.00005},

    # Cohere
    "command-r-plus":           {"input": 0.0025,   "output": 0.01},
    "command-r":                {"input": 0.00015,  "output": 0.0006},

    # Perplexity
    "sonar":                    {"input": 0.001,    "output": 0.001},
    "sonar-pro":                {"input": 0.003,    "output": 0.015},
    "sonar-reasoning":          {"input": 0.001,    "output": 0.005},

    # Google Gemma & Microsoft Phi
    "gemma-7b-it":              {"input": 0.00007,  "output": 0.00007},
    "phi-4":                    {"input": 0.00007,  "output": 0.00007},
}

# ─── Context window registry (tokens) ─────────────────────────────────────────
DEFAULT_CONTEXT_WINDOWS: Dict[str, int] = {
    # OpenAI
    "gpt-4.5":                  128_000,
    "gpt-4.5-preview":          128_000,
    "gpt-4o":                   128_000,
    "gpt-4o-2024-08-06":        128_000,
    "gpt-4o-2024-11-20":        128_000,
    "chatgpt-4o-latest":        128_000,
    "gpt-4o-mini":              128_000,
    "gpt-4-turbo":              128_000,
    "gpt-4":                    8_192,
    "gpt-3.5-turbo":            16_385,
    "o1":                       200_000,
    "o1-2024-12-17":            200_000,
    "o1-preview":               128_000,
    "o1-mini":                  128_000,
    "o3":                       200_000,
    "o3-mini":                  200_000,
    "o4-mini":                  200_000,
    "text-embedding-3-small":   8_191,
    "text-embedding-3-large":   8_191,
    "text-embedding-ada-002":   8_191,

    # Anthropic
    "claude-3-7-sonnet":        200_000,
    "claude-3-7-sonnet-latest": 200_000,
    "claude-3-7-sonnet-thinking": 200_000,
    "claude-3-5-sonnet":        200_000,
    "claude-3-5-sonnet-latest": 200_000,
    "claude-3-5-haiku":         200_000,
    "claude-3-5-haiku-latest":  200_000,
    "claude-3-opus":            200_000,
    "claude-3-sonnet":          200_000,
    "claude-3-haiku":           200_000,

    # DeepSeek
    "deepseek-chat":            64_000,
    "deepseek-reasoner":        64_000,
    "deepseek-v3":              64_000,
    "deepseek-r1":              64_000,
    "deepseek-r1-distill-llama-70b": 128_000,
    "deepseek-r1-distill-qwen-32b":  128_000,

    # Google Gemini
    "gemini-2.5-pro":           1_000_000,
    "gemini-2.5-flash":         1_000_000,
    "gemini-2.0-flash":         1_000_000,
    "gemini-2.0-flash-lite":    1_000_000,
    "gemini-2.0-pro-exp":       2_000_000,
    "gemini-1.5-pro":           2_000_000,
    "gemini-1.5-flash":         1_000_000,
    "gemini-1.5-flash-8b":      1_000_000,
    "text-embedding-004":       2_048,

    # Meta Llama
    "llama-3.3-70b":            128_000,
    "llama-3.1-405b":           128_000,
    "llama-3.1-70b":            128_000,
    "llama-3.1-8b":             128_000,
    "llama-3.2-1b":             128_000,
    "llama-3.2-3b":             128_000,
    "llama-3.2-11b-vision":     128_000,
    "llama-3.2-90b-vision":     128_000,
    "llama-3-70b":              8_192,
    "llama-3-8b":               8_192,

    # Mistral
    "mistral-large":            128_000,
    "mistral-large-2411":       128_000,
    "mistral-small":            128_000,
    "codestral":                32_768,
    "codestral-2501":           256_000,
    "pixtral-12b":              128_000,
    "mistral-nemo":             128_000,
    "mixtral-8x7b":             32_768,
    "mixtral-8x22b":            65_536,

    # Qwen
    "qwen-2.5-72b":             128_000,
    "qwen-2.5-32b":             128_000,
    "qwen-2.5-14b":             128_000,
    "qwen-2.5-7b":              128_000,
    "qwen-2.5-coder-32b":       128_000,
    "qwen-2.5-coder-7b":        32_768,
    "phi-4":                    16_384,

    # Cohere
    "command-r-plus":           128_000,
    "command-r":                128_000,

    # Perplexity
    "sonar":                    128_000,
    "sonar-pro":                200_000,
    "sonar-reasoning":          128_000,

    # Google Gemma
    "gemma-7b-it":              8_192,
}

MODEL_PRICING = DEFAULT_PRICING
CONTEXT_WINDOWS = DEFAULT_CONTEXT_WINDOWS


# ─── Model Metadata Lookup Helpers ───────────────────────────────────────────

def _normalize_model_name(model_str: str) -> str:
    """Strip provider prefix and lowercase."""
    _, model = parse_model(model_str)
    return model.lower().strip()


def _find_model_match(norm: str, table: Dict[str, Any]) -> Optional[Any]:
    if not norm:
        return None

    # 1. Exact match
    if norm in table:
        return table[norm]

    # 2. Match without date/snapshot suffixes (e.g., -2024-08-06, -20241217, -0125)
    stripped = re.sub(r'-(?:\d{4}-\d{2}-\d{2}|\d{8}|\d{4})$', '', norm)
    if stripped in table:
        return table[stripped]

    # 3. Match without common release tags (-preview, -latest, -chat, -instruct)
    stripped_tag = re.sub(r'-(?:preview|latest|chat|instruct)$', '', stripped)
    if stripped_tag in table:
        return table[stripped_tag]

    # 4. Longest-prefix match (check longer, more specific model names FIRST)
    # e.g., "gpt-4o-mini" before "gpt-4o", "o1-mini" before "o1"
    for key in sorted(table.keys(), key=len, reverse=True):
        if norm == key:
            return table[key]
        if norm.startswith(f"{key}-") or norm.startswith(f"{key}/") or norm.startswith(f"{key}:") or norm.startswith(f"{key}."):
            return table[key]
        if key.startswith(f"{norm}-") or key.startswith(f"{norm}/"):
            return table[key]

    return None


def get_model_pricing(
    model_str: str,
    custom_pricing: Optional[Dict[str, Dict[str, float]]] = None
) -> Optional[Dict[str, float]]:
    """
    Find pricing for a model by exact match, date-suffix stripping, or longest prefix matching.
    """
    if not model_str:
        return None
    table = custom_pricing if custom_pricing is not None else DEFAULT_PRICING
    norm = _normalize_model_name(model_str)
    return _find_model_match(norm, table)


def get_model_context_window(
    model_str: str,
    custom_windows: Optional[Dict[str, int]] = None,
    default: int = 128_000
) -> int:
    """
    Find context window limit for a model by exact match, suffix stripping, or longest prefix matching.
    """
    if not model_str:
        return default
    table = custom_windows if custom_windows is not None else DEFAULT_CONTEXT_WINDOWS
    norm = _normalize_model_name(model_str)
    match = _find_model_match(norm, table)
    return match if match is not None else default


# ─── Token Counting Engine ───────────────────────────────────────────────────

_TIKTOKEN_ENCODERS: Dict[str, Any] = {}
_HAS_TIKTOKEN: Optional[bool] = None

def _get_tiktoken_encoder(model: str = "gpt-4o"):
    global _HAS_TIKTOKEN
    if _HAS_TIKTOKEN is False:
        return None
    try:
        import tiktoken
        _HAS_TIKTOKEN = True
        norm = _normalize_model_name(model)
        if norm in _TIKTOKEN_ENCODERS:
            return _TIKTOKEN_ENCODERS[norm]
        try:
            enc = tiktoken.encoding_for_model(norm)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        _TIKTOKEN_ENCODERS[norm] = enc
        return enc
    except ImportError:
        _HAS_TIKTOKEN = False
        return None
    except Exception:
        return None


def count_tokens(text_or_content: Any, model: str = "gpt-4o") -> int:
    """
    Count or estimate tokens in a string, list, or dict.
    Uses tiktoken if installed; otherwise uses a robust multilingual BPE heuristic
    accounting for CJK / non-ASCII character overhead and whitespace/punctuation.
    """
    if not text_or_content:
        return 0

    if isinstance(text_or_content, str):
        text = text_or_content
    elif isinstance(text_or_content, list):
        return sum(count_tokens(item, model=model) for item in text_or_content)
    elif isinstance(text_or_content, dict):
        if text_or_content.get("type") == "text":
            return count_tokens(text_or_content.get("text", ""), model=model)
        if text_or_content.get("type") == "image_url":
            # Standard OpenAI Vision tile estimate
            detail = text_or_content.get("image_url", {}).get("detail", "auto")
            return 85 if detail == "low" else 255
        # Fallback for generic dict
        return sum(count_tokens(v, model=model) for v in text_or_content.values() if isinstance(v, (str, list, dict)))
    else:
        text = str(text_or_content)

    if not text:
        return 0

    encoder = _get_tiktoken_encoder(model)
    if encoder is not None:
        try:
            return len(encoder.encode(text, disallowed_special=()))
        except Exception:
            pass

    # High-accuracy heuristic when tiktoken is not installed
    # CJK character range: 1.5 - 2.0 tokens per character
    cjk_count = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]', text))
    non_cjk_text = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]', '', text)

    # For standard text, tokens ~ words * 1.33 or characters * 0.28
    words = len(re.findall(r'\b\w+\b', non_cjk_text))
    special_chars = len(re.findall(r'[^\w\s]', non_cjk_text))

    ascii_tokens = math.ceil(words * 1.33 + special_chars * 0.5)
    estimated = ascii_tokens + math.ceil(cjk_count * 1.5)
    return max(1, estimated)


def count_message_tokens(messages: Sequence[Any], model: str = "gpt-4o") -> int:
    """
    Count tokens for chat messages according to the OpenAI/LiteLLM specification:
    - 3 tokens per message for delimiter overhead: <|im_start|>{role}\n...<|im_end|>\n
    - 1 token if name is specified
    - Tokens for role, name, and content
    - +3 tokens for priming the assistant response: <|im_start|>assistant<|message|>
    """
    if not messages:
        return 0

    norm = _normalize_model_name(model)
    tokens_per_message = 4 if "gpt-3.5-turbo-0301" in norm else 3
    tokens_per_name = -1 if "gpt-3.5-turbo-0301" in norm else 1

    total = 0
    for m in messages:
        total += tokens_per_message
        if isinstance(m, dict):
            role = m.get("role", "")
            content = m.get("content", "")
            name = m.get("name")
        else:
            role = getattr(m, "role", "")
            content = getattr(m, "content", "")
            name = getattr(m, "name", None)

        total += count_tokens(role, model=model)
        total += count_tokens(content, model=model)
        if name:
            total += tokens_per_name + count_tokens(name, model=model)

        # Count tokens for tool calls (name and arguments) if present
        tool_calls = m.get("tool_calls") if isinstance(m, dict) else getattr(m, "tool_calls", None)
        if tool_calls and isinstance(tool_calls, list):
            for tc in tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "") if isinstance(fn, dict) else getattr(fn, "name", "")
                    fn_args = fn.get("arguments", "") if isinstance(fn, dict) else getattr(fn, "arguments", "")
                    tc_id = tc.get("id", "")
                else:
                    fn = getattr(tc, "function", None)
                    fn_name = getattr(fn, "name", "") if fn else ""
                    fn_args = getattr(fn, "arguments", "") if fn else ""
                    tc_id = getattr(tc, "id", "")
                if fn_name:
                    total += count_tokens(fn_name, model=model)
                if fn_args:
                    total += count_tokens(fn_args, model=model)
                if tc_id:
                    total += count_tokens(tc_id, model=model)

        tool_call_id = m.get("tool_call_id") if isinstance(m, dict) else getattr(m, "tool_call_id", None)
        if tool_call_id:
            total += count_tokens(tool_call_id, model=model)

    total += 3  # Assistant reply priming
    return total


# ─── Dynamic Request Headers Utilities ───────────────────────────────────────

# Standard HTTP hop-by-hop and connection-level headers that should NEVER be forwarded
HOP_BY_HOP_HEADERS = frozenset({
    "host",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "cookie",
    "accept-encoding",
})
AUTH_HEADERS = frozenset({"authorization", "api-key", "x-api-key"})

def extract_forward_headers(
    headers: Mapping[str, str],
    strip_auth: bool = True,
    allowed_custom_prefixes: Sequence[str] = ("x-", "anthropic-", "openai-", "deepseek-")
) -> Dict[str, str]:
    """
    Extract headers from an incoming HTTP request that are safe and appropriate
    to forward to upstream LLM providers (e.g. Portkey & One-API style).
    Strips hop-by-hop headers and, by default, caller authentication headers
    so gateway keys do not leak upstream or overwrite provider credentials.
    """
    out: Dict[str, str] = {}
    for k, v in headers.items():
        k_lower = k.lower().strip()
        if k_lower in HOP_BY_HOP_HEADERS:
            continue
        if strip_auth and k_lower in AUTH_HEADERS:
            continue
        # Allow standard metadata headers and custom headers
        if (
            k_lower.startswith(tuple(allowed_custom_prefixes))
            or k_lower in ("user-agent", "referer", "origin", "x-request-id", "x-correlation-id")
        ):
            out[k] = v
    return out


def merge_request_headers(
    base_headers: Dict[str, str],
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Merge extra custom headers into base request headers (preserving Authorization case-insensitively).
    """
    merged = dict(base_headers)
    if extra_headers:
        base_auth_keys = {k.lower().strip() for k in base_headers.keys()}
        has_base_auth = "authorization" in base_auth_keys

        for k, v in extra_headers.items():
            k_lower = k.lower().strip()
            if k_lower in HOP_BY_HOP_HEADERS:
                continue
            if k_lower == "authorization" and has_base_auth:
                continue
            merged[k] = v
    return merged


def validate_url_ssrf(url: Optional[str], allow_private: Optional[bool] = None) -> str:
    """
    Validate that a URL uses http:// or https:// scheme and does not resolve to restricted
    SSRF targets (cloud metadata, loopback, link-local, private RFC 1918),
    unless VELOROUTE_ALLOW_PRIVATE_NETWORKS is explicitly enabled ('true', '1', 'yes').
    """
    if not url or not str(url).strip():
        return ""
    clean = str(url).strip()
    from urllib.parse import urlparse
    import socket
    import ipaddress
    import os

    parsed = urlparse(clean)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme '{parsed.scheme}'. URL must use http:// or https:// scheme.")

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("URL is missing a valid hostname.")

    # Explicit cloud metadata hostnames / well-known metadata targets
    if host in ("169.254.169.254", "metadata.google.internal", "metadata", "100.100.100.200"):
        raise ValueError(f"Webhook URL points to a restricted cloud metadata address: {host}")

    if allow_private is None:
        allow_private = os.environ.get("VELOROUTE_ALLOW_PRIVATE_NETWORKS", "false").lower() in ("true", "1", "yes")

    if not allow_private:
        # Check loopback hostnames
        if host in ("localhost", "local", "ip6-localhost", "ip6-loopback") or host.endswith(".local") or host.endswith(".internal"):
            raise ValueError(f"URL resolves to restricted or private loopback hostname: {host}")

        # Check IP literal or resolve via DNS
        resolved_ips: List[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]] = []
        try:
            resolved_ips.append(ipaddress.ip_address(host))
        except ValueError:
            # Check for alternative IPv4 representations (e.g. shorthand 127.1, hex, octal)
            try:
                resolved_ips.append(ipaddress.IPv4Address(socket.inet_aton(host)))
            except (OSError, ValueError):
                pass
            if not resolved_ips:
                # Domain name: attempt resolution
                try:
                    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
                    addr_info = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
                    for info in addr_info:
                        try:
                            resolved_ips.append(ipaddress.ip_address(info[4][0]))
                        except ValueError:
                            pass
                except (socket.gaierror, socket.herror, OSError):
                    resolved_ips = []

        for ip in resolved_ips:
            check_ip = getattr(ip, "ipv4_mapped", None) or ip
            if (
                check_ip.is_loopback
                or check_ip.is_private
                or check_ip.is_link_local
                or check_ip.is_multicast
                or check_ip.is_reserved
                or check_ip.is_unspecified
                or str(check_ip).startswith("169.254.")
            ):
                raise ValueError(f"URL resolves to restricted or private network address: {ip}")

    return clean

