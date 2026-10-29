# LLMCycle Local Setup

This folder (`G:\llmcycle`) is configured with `llmcycle` inside a virtual environment (`.venv`).

## Quick Launchers (Windows)

- **`menu.bat`**: Interactive terminal launcher with numbered menus for:
  - Starting the Web Dashboard (auto-opens browser)
  - Adding / Editing / Deleting Providers and API Keys
  - Removing individual keys
  - Dynamic live models inspection
  - Testing provider connectivity (Ping)
  - Managing egress proxy settings
  - Running sample Python scripts
- **`dashboard.bat`**: One-click launcher for the Web Dashboard (`http://127.0.0.1:8000`).

## CLI Usage

You can run the `llmcycle` CLI directly (with automatic Windows UTF-8 console output handling):

```powershell
# Help & Overview
.\.venv\Scripts\llmcycle.exe help

# Provider & Key Management
.\.venv\Scripts\llmcycle.exe providers add apinex sk-key1,sk-key2 --base-url https://api.apinex.com/v1
.\.venv\Scripts\llmcycle.exe providers edit apinex --base-url https://api.apinex.com/v2
.\.venv\Scripts\llmcycle.exe keys remove apinex sk-key1
.\.venv\Scripts\llmcycle.exe providers remove apinex

# List configured providers & keys
.\.venv\Scripts\llmcycle.exe list
.\.venv\Scripts\llmcycle.exe keys list

# Egress Proxy Configuration
.\.venv\Scripts\llmcycle.exe proxy set http://127.0.0.1:8080
.\.venv\Scripts\llmcycle.exe proxy show
.\.venv\Scripts\llmcycle.exe proxy clear

# Connectivity and Live Models
.\.venv\Scripts\llmcycle.exe ping
.\.venv\Scripts\llmcycle.exe models

# Start Web Dashboard
.\.venv\Scripts\llmcycle.exe ui --port 8000
```

## Gateway API Keys

Create and manage keys in the dashboard's **Virtual Keys** screen or through the authenticated admin API at `/api/v1/gateway/keys`. The API supports listing, creation, limit/scope updates, rotation, revocation, and deletion. Obtain an admin token by posting the configured dashboard username and password to `/api/v1/token`; key management requires that token as a bearer credential. A key's plaintext appears only at creation or rotation; store it securely. Creating the first key enables API-key checks on `/v1/*` endpoints. Set `LLMCYCLE_REQUIRE_API_KEY=1` to require a key before any virtual key has been created. Budgeted keys reject models without configured pricing so unpriced traffic cannot silently bypass the spend limit.

The gateway also exposes `/v1/images/generations` when the selected upstream implements the OpenAI-compatible image generation endpoint. Image spend is provider-specific and is not derived from token prices, so image generation is rejected for keys with spend budgets until per-image pricing is configured. Audio transcription and speech are also rejected for budgeted keys until usage can be priced from provider-reported audio usage. These routes are not native adapters for every provider in `PROVIDER_REGISTRY`.

Use a virtual key as the bearer token in an OpenAI-compatible client pointed at `http://127.0.0.1:8000/v1`:

```powershell
$env:OPENAI_BASE_URL = "http://127.0.0.1:8000/v1"
$env:OPENAI_API_KEY = "<virtual key>"
```

The dashboard is same-origin by default. If a separate frontend needs cross-origin API access, set `LLMCYCLE_CORS_ORIGINS` to a comma-separated list of trusted origins.

## Python Usage

Run the sample script:
```powershell
.\.venv\Scripts\python.exe example.py
```
