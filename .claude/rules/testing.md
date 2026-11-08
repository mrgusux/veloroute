---
paths:
  - "tests/**"
  - "**/*test*"
---

# Testing & Quality Rules (Claude Code)

- **Determinism**: Keep all tests 100% deterministic and mock all external network / AI API calls.
- **Coverage**: Verify both happy paths and negative edge cases (empty strings, invalid tokens, rate limit 429s, server 500s).
- **Integrity**: Never delete, skip, or weaken an existing test assertion. All 219+ unit tests must pass.
- **Verification**:
  - Run `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"`
  - Run Next.js build: `cd website; npm run build`
