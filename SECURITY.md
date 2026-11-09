# Security Policy

## Supported Versions

Only the latest release on the `main` branch is actively supported with security patches.

| Version | Supported |
| :--- | :--- |
| `main` (latest) | :white_check_mark: |
| Older releases | :x: |

## Reporting a Vulnerability

If you discover a potential security vulnerability within VeloRoute, **please DO NOT open a public issue or discussion.**

### How to Report

1. **GitHub Private Vulnerability Reporting (Preferred)**:  
   Navigate to the **Security** tab -> **Report a vulnerability**, or visit:  
   https://github.com/mrgusux/veloroute/security/advisories/new  
   This opens a confidential advisory visible only to you and the core maintainers.

2. **Alternative Disclosure**:  
   If GitHub private reporting is inaccessible, contact the maintainer privately via GitHub profile contacts.

### Vulnerability Scope

VeloRoute operates as a mission-critical AI gateway handling enterprise prompts, API tokens, and LLM responses. High-priority vulnerabilities include:

- **Guardrail & Injection Bypasses**: Exploits defeating prompt injection classifiers or secret/PII redacting regex engines.
- **SSRF in Routing & MCP**: Server-Side Request Forgery or arbitrary internal network probing via custom provider URLs or MCP tool endpoints.
- **Authentication & Secret Leaks**: Memory exposure, unmasked secrets in logging, or timing attacks in API key verification.
- **Remote Code Execution**: Any code injection vectors in template evaluation or context optimization.

### Response SLA

- **Initial triage**: Within 48 hours.
- **Severity rating**: Within 5 business days.
- **Fix deployment & CVE coordination**: Expedited based on severity.
