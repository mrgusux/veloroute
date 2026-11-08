---
paths:
  - "**/*"
---

# Security & OWASP Rules (Claude Code)

- **Zero Hardcoded Secrets**: Load all API keys, database credentials, and secrets through environment variables or secure key stores.
- **Timing Attacks**: Use `secrets.compare_digest` for all token comparisons.
- **SQL & Command Injections**: Always use parameterized queries. Never interpolate untrusted user strings into SQL or shell commands.
- **SSRF Protection**: Prohibit routing requests to private IP ranges (`127.0.0.1`, RFC 1918) and validate upstream hostnames.
- **Secret Redaction**: Always mask virtual and upstream API keys in audit logs and user-facing responses.
- **Prompt Injection Defense**: Scan untrusted user messages with heuristic and entropy guardrails before dispatching to upstream LLMs.
