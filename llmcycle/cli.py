"""
LLMCycle CLI — command-line interface for the LLM router.

Commands
--------
  llmcycle help                   Show all commands with examples
  llmcycle version                Show installed version
  llmcycle list                   List all loaded providers + key health
  llmcycle providers              Alias for 'list'
  llmcycle ping [provider]        Test connectivity to one or all providers
  llmcycle keys add               Add / append API key(s) to .env
  llmcycle keys list              Show all keys in .env (masked)
  llmcycle keys remove            Remove a provider's keys from .env
  llmcycle config                 Show active configuration
  llmcycle cache show             Show model-info cache stats + location
  llmcycle cache clear            Clear the disk + memory cache
  llmcycle cache set-dir <path>   Override the cache directory
  llmcycle ui                     Start the web dashboard
"""
from __future__ import annotations
import os
import sys
import argparse
from pathlib import Path

# Fix Windows console Unicode encoding (charmap crash on emojis/symbols)
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        if sys.stdin and hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ─── .env loader ─────────────────────────────────────────────────────────────

def _safe_load_env(dotenv_path: str = ".env", override: bool = False) -> None:
    """Load .env handling UTF-8 BOM, UTF-16 (Windows Notepad), and plain ASCII."""
    path = Path(dotenv_path)
    if not path.exists():
        return
    for enc in ("utf-8-sig", "utf-16", "utf-8", "latin-1"):
        try:
            content = path.read_text(encoding=enc)
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and (override or key not in os.environ):
                    os.environ[key] = val
            return
        except (UnicodeDecodeError, UnicodeError):
            continue


# ─── .env writer helpers ──────────────────────────────────────────────────────

def _read_env_file(path: Path) -> list[str]:
    """Return raw lines from .env, or [] if file doesn't exist."""
    if not path.exists():
        return []
    for enc in ("utf-8-sig", "utf-16", "utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc).splitlines()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return []


def _write_env_file(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _set_env_key(env_path: Path, env_key: str, value: str) -> None:
    """Set or replace a key in the .env file."""
    lines = _read_env_file(env_path)
    new_lines = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{env_key}=") or stripped.startswith(f"{env_key} ="):
            new_lines.append(f"{env_key}={value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"{env_key}={value}")
    _write_env_file(env_path, new_lines)


def _remove_env_key(env_path: Path, env_key: str) -> bool:
    """Remove a key from .env. Returns True if the key was found."""
    lines = _read_env_file(env_path)
    new_lines = [
        l for l in lines
        if not l.strip().startswith(f"{env_key}=")
        and not l.strip().startswith(f"{env_key} =")
    ]
    removed = len(new_lines) < len(lines)
    if removed:
        _write_env_file(env_path, new_lines)
    return removed


def _mask(key: str) -> str:
    """Mask an API key for display: show first 6 + last 4 chars."""
    if len(key) <= 10:
        return key[:2] + "***"
    return key[:6] + "..." + key[-4:]


# ─── Colour helpers ───────────────────────────────────────────────────────────

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def _c(text: str, *codes: str) -> str:
    """Colourize text if stdout supports ANSI (skipped on Windows without VT)."""
    if sys.stdout.isatty():
        return "".join(codes) + text + RESET
    return text


# ─── Command handlers ─────────────────────────────────────────────────────────

def cmd_help(_args) -> None:
    print(f"""
{_c('LLMCycle', BOLD, CYAN)} — Universal LLM Router  {_c('♻️', BOLD)}
{_c('https://github.com/Bishwajitgarai/llmcycle', DIM)}

{_c('USAGE', BOLD)}
  llmcycle <command> [options]

{_c('COMMANDS', BOLD)}
  {_c('help', CYAN)}                                Show this help message
  {_c('version', CYAN)}                             Show installed version
  {_c('list', CYAN)}                                List loaded providers + key health
  {_c('providers list', CYAN)}                      List configured providers + health
  {_c('providers add', CYAN)} <p> <keys> [--url U]  Add custom/registry provider to .env
  {_c('providers edit', CYAN)} <p> [--url U] [--keys K] Edit provider URL and/or keys
  {_c('providers remove', CYAN)} <p>                Delete provider and keys from .env
  {_c('keys add', CYAN)} <p> <keys>                 Add / append API keys to .env
  {_c('keys edit', CYAN)} <p> <keys>                Replace all API keys for provider
  {_c('keys list', CYAN)}                           Show all keys in .env (masked)
  {_c('keys remove', CYAN)} <p> [key]               Remove provider's keys or single key
  {_c('models', CYAN)} [provider]                   Fetch dynamic live models
  {_c('ping', CYAN)} [provider]                     Test connectivity to one or all providers
  {_c('aliases', CYAN)} [list|add|remove]           Manage universal model aliases
  {_c('circuit', CYAN)} [list|reset]                Inspect and reset resilient circuit breakers
  {_c('proxy', CYAN)} [show|set|clear]              Manage egress proxy configuration
  {_c('config', CYAN)}                              Show active LLMCycle configuration
  {_c('cache show', CYAN)}                          Show model-info cache stats + file location
  {_c('cache clear', CYAN)}                         Wipe the model-info cache (LRU + disk)
  {_c('cache set-dir', CYAN)} <path>                Override the cache directory (writes to .env)
  {_c('ui', CYAN)} [--port N] [--host H]           Start the web dashboard

{_c('EXAMPLES', BOLD)}
  # Add custom provider with Base URL and keys
  llmcycle providers add apinex sk-mykey --base-url https://api.apinex.com/v1

  # Edit provider Base URL
  llmcycle providers edit apinex --base-url https://api.apinex.com/v2

  # Delete provider and all its configuration
  llmcycle providers remove apinex

  # Add OpenAI keys
  llmcycle keys add openai sk-key1,sk-key2

  # Remove a single key from OpenAI
  llmcycle keys remove openai sk-key1

  # Configure egress proxy
  llmcycle proxy set http://127.0.0.1:8080

  # Show active config
  llmcycle config

{_c('ENVIRONMENT', BOLD)}
  {_c('*_API_KEYS', YELLOW)}              Comma-separated keys per provider (e.g. OPENAI_API_KEYS)
  {_c('*_BASE_URL', YELLOW)}              Override base URL per provider   (e.g. OLLAMA_BASE_URL)
  {_c('LLMCYCLE_CACHE_DIR', YELLOW)}      Model-info cache directory       (default: ./llmcycle/storage/model_info)
  {_c('LLMCYCLE_UI_HOST', YELLOW)}        Dashboard host  (default: 127.0.0.1)
  {_c('LLMCYCLE_UI_PORT', YELLOW)}        Dashboard port  (default: 8000)
""")


def cmd_version(_args) -> None:
    try:
        from llmcycle import __version__
        print(f"llmcycle {_c(__version__, BOLD, GREEN)}")
    except ImportError:
        print("llmcycle (version unknown)")


def cmd_list(_args) -> None:
    from llmcycle import LLMCycle
    client = LLMCycle()
    providers = client.get_providers()
    if not providers:
        print(_c("  No providers loaded.", YELLOW))
        print(_c("  Add keys with:  llmcycle keys add <provider> <key>", DIM))
        return

    print(f"\n{_c(f'Loaded providers ({len(providers)}):', BOLD)}\n")
    for p in providers:
        stats = client.key_manager.key_count(p)
        active = stats["active"]
        total  = stats["total"]
        tripped = stats.get("circuit_broken", 0)
        health = _c(f"{active}/{total} keys", GREEN) if active > 0 else _c(f"0/{total} keys", RED)
        tripped_str = f"  ({_c(f'{tripped} circuit-broken', RED)})" if tripped > 0 else ""
        status = _c("✓", GREEN) if active > 0 else _c("✗", RED)
        print(f"  {status}  {_c(p, BOLD):<30s}  {health}{tripped_str}")
    print()


def cmd_circuit(args) -> None:
    from llmcycle import LLMCycle
    _safe_load_env()
    client = LLMCycle()
    subcmd = getattr(args, "circuit_cmd", "list") or "list"

    if subcmd == "reset":
        provider = getattr(args, "provider", None)
        cnt = client.key_manager.reset_circuit_breaker(provider)
        target = f"for {provider}" if provider else "across all providers"
        print(f"\n{_c('✓', GREEN)}  Reset {_c(str(cnt), BOLD)} circuit breaker(s) {target}\n")
    else:
        providers = client.get_providers()
        if not providers:
            print(_c("\n  No providers loaded.\n", YELLOW))
            return
        print(f"\n{_c('Circuit Breaker Status & Key Health:', BOLD, CYAN)}\n")
        total_tripped = 0
        for p in providers:
            stats = client.key_manager.get_stats(p)
            p_state = client.key_manager.get_provider_circuit_state(p)
            p_badge = _c("CLOSED (HEALTHY)", GREEN) if p_state == "closed" else (_c("HALF-OPEN (PROBING)", YELLOW) if p_state == "half_open" else _c("OPEN (ALL TRIPPED)", RED))
            print(f"  {_c(p.upper(), BOLD):<20s} [State: {p_badge}]")
            for s in stats:
                hint = s.get("hint")
                state = s.get("circuit_state", "closed")
                trips = s.get("circuit_trips", 0)
                reqs = s.get("total_requests", 0)
                errs = s.get("total_errors", 0)
                status_str = s.get("status")
                badge = _c("closed", GREEN) if state == "closed" else (_c("half_open", YELLOW) if state == "half_open" else _c("OPEN (TRIPPED)", RED))
                if state == "open" or status_str == "circuit_broken":
                    total_tripped += 1
                print(f"    - Key {hint:<14s}  Circuit: {badge:<18s}  Trips: {trips:<3d}  Reqs: {reqs:<4d}  Errors: {errs:<3d}")
            print()
        if total_tripped > 0:
            print(_c(f"  Warning: {total_tripped} key(s) currently circuit-broken. Reset with: llmcycle circuit reset\n", YELLOW))
        else:
            print(_c("  ✓ All circuit breakers are healthy.\n", GREEN))


def cmd_aliases(args) -> None:
    from llmcycle import LLMCycle
    _safe_load_env()
    client = LLMCycle()
    subcmd = getattr(args, "alias_cmd", "list") or "list"

    if subcmd == "add":
        name = args.name.strip()
        target = args.target.strip()
        client.alias(name, target)
        print(f"\n{_c('✓', GREEN)}  Registered alias {_c(name, BOLD, CYAN)} -> {_c(target, YELLOW)}\n")
    elif subcmd in ("remove", "delete", "rm"):
        name = args.name.strip()
        removed = client.remove_alias(name)
        if removed:
            print(f"\n{_c('✓', GREEN)}  Removed alias {_c(name, BOLD)}\n")
        else:
            print(f"\n{_c('✗', RED)}  Alias {_c(name, BOLD)} not found\n")
    else:
        aliases = client.list_aliases()
        if not aliases:
            print(_c("\n  No model aliases configured.\n", DIM))
            print(_c("  Add with:  llmcycle aliases add <name> <target>\n", DIM))
            return
        print(f"\n{_c('Universal Model Aliases:', BOLD, CYAN)}\n")
        for name, target in sorted(aliases.items()):
            print(f"  🏷️  {_c(name, BOLD, CYAN):<25s} ->  {_c(target, YELLOW)}")
        print()


def cmd_models(args) -> None:
    import asyncio
    from llmcycle import LLMCycle

    _safe_load_env()
    client = LLMCycle()

    if args.provider:
        p_name = args.provider.lower()
        if p_name not in client.get_providers():
            print(_c(f"  Error: provider '{args.provider}' is not loaded or has no API keys.", RED))
            return
        print(f"\n{_c(f'Fetching live models for {p_name}...', BOLD)}\n")
        try:
            models = asyncio.run(client.get_models(p_name))
            if not models:
                print(_c("  No models returned or provider has no active keys.", YELLOW))
            else:
                for m in models:
                    print(f"  {_c('•', GREEN)}  {_c(m, BOLD)}")
                print(f"\n  Total: {_c(str(len(models)), GREEN)} model(s)\n")
        except Exception as e:
            print(_c(f"  Error fetching models: {e}", RED))
    else:
        print(f"\n{_c('Fetching all live models across configured providers...', BOLD)}\n")
        try:
            results = asyncio.run(client.get_all_live_models())
            if not results:
                print(_c("  No providers loaded. Add keys using 'llmcycle keys add <provider> <key>'.", YELLOW))
                return
            for p, models in results.items():
                p_hdr = f"  {_c(p, BOLD, CYAN)} ({len(models)} models)"
                print(p_hdr)
                print("  " + "—" * 40)
                if not models:
                    print(_c("    (No active models or failed to connect)", DIM))
                else:
                    for m in sorted(models):
                        print(f"    {_c('•', GREEN)}  {m}")
                print()
        except Exception as e:
            print(_c(f"  Error: {e}", RED))


def cmd_ping(args) -> None:
    import asyncio, time
    from llmcycle import LLMCycle

    _safe_load_env()
    client = LLMCycle()
    providers = [args.provider.lower()] if getattr(args, "provider", None) else client.get_providers()

    if not providers:
        print(_c("  No providers loaded.", YELLOW))
        return

    print(f"\n{_c('Pinging providers...', BOLD)}\n")

    async def _ping_one(name: str) -> dict:
        prov = client._providers.get(name)
        key  = client.key_manager.get_next_key(name)
        if not prov or not key:
            return {"provider": name, "ok": False, "error": "No active keys", "latency_ms": 0}
        t0 = time.monotonic()
        try:
            # Use /models as a lightweight probe
            await prov.get_models(key)
            latency = round((time.monotonic() - t0) * 1000, 1)
            return {"provider": name, "ok": True, "latency_ms": latency}
        except Exception as e:
            return {"provider": name, "ok": False, "error": str(e)[:60], "latency_ms": 0}

    async def _run():
        results = await asyncio.gather(*[_ping_one(p) for p in providers])
        for r in results:
            if r["ok"]:
                lat = _c(f"{r['latency_ms']:.0f}ms", GREEN if r["latency_ms"] < 500 else YELLOW)
                print(f"  {_c('✓', GREEN)}  {_c(r['provider'], BOLD):<28s}  {lat}")
            else:
                err = _c(r.get("error", "failed"), RED)
                print(f"  {_c('✗', RED)}  {_c(r['provider'], BOLD):<28s}  {err}")
        print()

    asyncio.run(_run())


def cmd_keys_add(args) -> None:
    env_path = Path(args.env_file)
    provider = args.provider.upper()
    env_key  = f"{provider}_API_KEYS"
    new_keys = [k.strip() for k in args.keys.split(",") if k.strip()]

    if not new_keys:
        print(_c("  Error: no valid keys provided.", RED))
        sys.exit(1)

    # Merge with existing keys
    existing_raw = os.environ.get(env_key, "")
    existing_keys = [k.strip() for k in existing_raw.split(",") if k.strip()]
    combined = list(dict.fromkeys(existing_keys + new_keys))  # dedup, preserve order

    _set_env_key(env_path, env_key, ",".join(combined))

    print(f"\n{_c('✓', GREEN)}  Saved {_c(str(len(new_keys)), BOLD)} key(s) for "
          f"{_c(provider, BOLD)} to {_c(str(env_path), DIM)}\n")
    for k in new_keys:
        print(f"      {_c(_mask(k), CYAN)}")

    added = len(combined) - len(existing_keys)
    if added < len(new_keys):
        dupes = len(new_keys) - added
        print(_c(f"\n  Note: {dupes} duplicate key(s) skipped.", YELLOW))
    print()


def cmd_keys_list(args) -> None:
    env_path = Path(args.env_file)
    lines = _read_env_file(env_path)
    found: list[tuple[str, list[str]]] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if any(marker in stripped for marker in ("_API_KEYS=", "_API_KEYS =", "_API_KEY=", "_API_KEY =")):
            k, _, v = stripped.partition("=")
            provider = k.strip().replace("_API_KEYS", "").replace("_API_KEY", "")
            keys     = [x.strip() for x in v.strip().split(",") if x.strip()]
            found.append((provider, keys))

    if not found:
        print(_c("\n  No API keys found in .env\n", YELLOW))
        print(_c("  Add one with:  llmcycle keys add openai sk-xxx\n", DIM))
        return

    total_keys = sum(len(ks) for _, ks in found)
    print(f"\n{_c(f'Stored keys ({total_keys} total across {len(found)} provider(s)):', BOLD)}\n")
    for provider, keys in found:
        print(f"  {_c(provider, BOLD, CYAN)}")
        for k in keys:
            print(f"      {_c(_mask(k), DIM)}")
    print()


def cmd_keys_edit(args) -> None:
    env_path = Path(args.env_file)
    provider = args.provider.upper()
    env_key  = f"{provider}_API_KEYS"
    new_keys = [k.strip() for k in args.keys.split(",") if k.strip()]

    if not new_keys:
        print(_c("  Error: no valid keys provided.", RED))
        sys.exit(1)

    _set_env_key(env_path, env_key, ",".join(new_keys))
    os.environ[env_key] = ",".join(new_keys)

    print(f"\n{_c('✓', GREEN)}  Updated keys for {_c(provider, BOLD)} to {_c(str(env_path), DIM)}\n")
    for k in new_keys:
        print(f"      {_c(_mask(k), CYAN)}")
    print()


def cmd_keys_remove(args) -> None:
    env_path = Path(args.env_file)
    provider = args.provider.upper()
    env_key  = f"{provider}_API_KEYS"
    target_key = getattr(args, "key", None)

    if target_key:
        target_key = target_key.strip()
        existing_raw = os.environ.get(env_key, "")
        if not existing_raw:
            lines = _read_env_file(env_path)
            for l in lines:
                if l.strip().startswith(f"{env_key}=") or l.strip().startswith(f"{env_key} ="):
                    _, _, existing_raw = l.partition("=")
                    existing_raw = existing_raw.strip().strip('"').strip("'")
                    break

        keys = [k.strip() for k in existing_raw.split(",") if k.strip()]
        matched = [k for k in keys if k == target_key or _mask(k) == target_key]
        if not matched:
            print(_c(f"\n  Key '{target_key}' not found for provider {provider}.\n", YELLOW))
            return

        remaining = [k for k in keys if k not in matched]
        if remaining:
            _set_env_key(env_path, env_key, ",".join(remaining))
            os.environ[env_key] = ",".join(remaining)
            _remove_env_key(env_path, f"{provider}_API_KEY")
            os.environ.pop(f"{provider}_API_KEY", None)
            print(f"\n{_c('✓', GREEN)}  Removed key from {_c(provider, BOLD)}. {len(remaining)} key(s) remaining in {_c(str(env_path), DIM)}\n")
        else:
            _remove_env_key(env_path, env_key)
            _remove_env_key(env_path, f"{provider}_API_KEY")
            os.environ.pop(env_key, None)
            os.environ.pop(f"{provider}_API_KEY", None)
            print(f"\n{_c('✓', GREEN)}  Removed last key for {_c(provider, BOLD)} from {_c(str(env_path), DIM)}\n")
    else:
        removed1 = _remove_env_key(env_path, env_key)
        removed2 = _remove_env_key(env_path, f"{provider}_API_KEY")
        os.environ.pop(env_key, None)
        os.environ.pop(f"{provider}_API_KEY", None)
        if getattr(args, "clean_url", False):
            _remove_env_key(env_path, f"{provider}_BASE_URL")
            os.environ.pop(f"{provider}_BASE_URL", None)

        if removed1 or removed2:
            print(f"\n{_c('✓', GREEN)}  Removed keys for {_c(provider, BOLD)} from {_c(str(env_path), DIM)}\n")
        else:
            print(_c(f"\n  No keys found for {provider} in {env_path}\n", YELLOW))


def cmd_providers_add(args) -> None:
    env_path = Path(args.env_file)
    provider = args.provider.upper()
    keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    if not keys:
        print(_c("  Error: at least one API key is required.", RED))
        sys.exit(1)

    _set_env_key(env_path, f"{provider}_API_KEYS", ",".join(keys))
    os.environ[f"{provider}_API_KEYS"] = ",".join(keys)

    if getattr(args, "base_url", None):
        base_url = args.base_url.strip().rstrip("/")
        _set_env_key(env_path, f"{provider}_BASE_URL", base_url)
        os.environ[f"{provider}_BASE_URL"] = base_url

    print(f"\n{_c('✓', GREEN)}  Successfully added provider {_c(provider, BOLD)} to {_c(str(env_path), DIM)}")
    if getattr(args, "base_url", None):
        print(f"      Base URL: {_c(args.base_url.strip().rstrip('/'), CYAN)}")
    print(f"      Keys ({len(keys)}): {', '.join(_mask(k) for k in keys)}\n")


def cmd_providers_edit(args) -> None:
    env_path = Path(args.env_file)
    provider = args.provider.upper()
    updated = False

    if getattr(args, "base_url", None):
        base_url = args.base_url.strip().rstrip("/")
        _set_env_key(env_path, f"{provider}_BASE_URL", base_url)
        os.environ[f"{provider}_BASE_URL"] = base_url
        print(f"  {_c('✓', GREEN)}  Updated Base URL for {_c(provider, BOLD)}: {_c(base_url, CYAN)}")
        updated = True

    if getattr(args, "keys", None):
        keys = [k.strip() for k in args.keys.split(",") if k.strip()]
        if keys:
            _set_env_key(env_path, f"{provider}_API_KEYS", ",".join(keys))
            os.environ[f"{provider}_API_KEYS"] = ",".join(keys)
            print(f"  {_c('✓', GREEN)}  Updated Keys for {_c(provider, BOLD)}: {len(keys)} key(s)")
            updated = True

    if not updated:
        print(_c("\n  Nothing to update. Provide --base-url or --keys.\n", YELLOW))
    else:
        print()


def cmd_providers_remove(args) -> None:
    env_path = Path(args.env_file)
    provider = args.provider.upper()

    k_rm = _remove_env_key(env_path, f"{provider}_API_KEYS")
    k_rm2 = _remove_env_key(env_path, f"{provider}_API_KEY")
    u_rm = _remove_env_key(env_path, f"{provider}_BASE_URL")
    os.environ.pop(f"{provider}_API_KEYS", None)
    os.environ.pop(f"{provider}_API_KEY", None)
    os.environ.pop(f"{provider}_BASE_URL", None)

    if k_rm or k_rm2 or u_rm:
        print(f"\n{_c('✓', GREEN)}  Completely deleted provider {_c(provider, BOLD)} and its configuration from {_c(str(env_path), DIM)}\n")
    else:
        print(_c(f"\n  Provider {provider} was not found in {env_path}\n", YELLOW))


def cmd_proxy(args) -> None:
    env_path = Path(getattr(args, "env_file", ".env"))
    if getattr(args, "proxy_cmd", None) == "show":
        current = os.environ.get("LLMCYCLE_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        if current:
            print(f"\n  {_c('Active Proxy:', BOLD)} {_c(current, CYAN)}\n")
        else:
            print(_c("\n  No proxy configured.\n", DIM))

    elif args.proxy_cmd == "set":
        url = args.url.strip()
        _set_env_key(env_path, "LLMCYCLE_PROXY", url)
        os.environ["LLMCYCLE_PROXY"] = url
        print(f"\n{_c('✓', GREEN)}  Proxy set to {_c(url, CYAN)} in {_c(str(env_path), DIM)}\n")

    elif args.proxy_cmd == "clear":
        _remove_env_key(env_path, "LLMCYCLE_PROXY")
        os.environ.pop("LLMCYCLE_PROXY", None)
        print(f"\n{_c('✓', GREEN)}  Proxy cleared from {_c(str(env_path), DIM)}\n")
    else:
        cmd_proxy_show = os.environ.get("LLMCYCLE_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        print(f"\n  Proxy: {cmd_proxy_show or 'None'}\n")


def cmd_config(_args) -> None:
    from llmcycle import LLMCycle, __version__
    from llmcycle.providers.cache import get_model_info_cache
    client = LLMCycle()
    providers = client.get_providers()
    cache = get_model_info_cache()
    cs = cache.stats()

    strategy = client.router.strategy.value if hasattr(client, "router") else "priority"
    ui_host  = os.environ.get("LLMCYCLE_UI_HOST", "127.0.0.1")
    ui_port  = os.environ.get("LLMCYCLE_UI_PORT", "8000")

    storage_backend = os.environ.get("LLMCYCLE_STORAGE_BACKEND", _c("not configured", DIM))
    storage_url     = os.environ.get("LLMCYCLE_STORAGE_URL",     _c("not configured", DIM))
    cache_dir_env   = os.environ.get("LLMCYCLE_CACHE_DIR",       _c("default (./llmcycle/storage/model_info)", DIM))

    print(f"""
{_c('LLMCycle Configuration', BOLD, CYAN)}

  {_c('Version', BOLD)}            {_c(__version__, GREEN)}
  {_c('Routing strategy', BOLD)}   {_c(strategy, CYAN)}
  {_c('Providers loaded', BOLD)}   {_c(str(len(providers)), GREEN)} — {", ".join(providers) or _c("none", RED)}

  {_c('Dashboard host', BOLD)}     {ui_host}
  {_c('Dashboard port', BOLD)}     {ui_port}

  {_c('Storage backend', BOLD)}    {storage_backend}
  {_c('Storage URL', BOLD)}        {storage_url[:60] + "..." if len(str(storage_url)) > 60 else storage_url}

  {_c('Cache dir', BOLD)}          {_c(cs['cache_dir'], CYAN)}
  {_c('Cache file', BOLD)}         {_c(cs['cache_file'], DIM)}
  {_c('Cache entries', BOLD)}      {cs['lru_entries']} / {cs['lru_max']} (LRU)   disk: {'yes' if cs['disk_exists'] else 'no'} ({cs['disk_size_kb']} KB)
  {_c('Cache env override', BOLD)} {cache_dir_env}

  {_c('Env file', BOLD)}           {_c(".env", DIM)} (in current directory)
""")


# ─── Cache commands ───────────────────────────────────────────────────────────

def cmd_cache_show(_args) -> None:
    from llmcycle.providers.cache import get_model_info_cache
    cache = get_model_info_cache()
    cs = cache.stats()
    keys = cache.keys()

    print(f"""
{_c('Model Info Cache', BOLD, CYAN)}

  {_c('Directory', BOLD)}   {_c(cs['cache_dir'], CYAN)}
  {_c('File', BOLD)}        {_c(cs['cache_file'], DIM)}
  {_c('Disk exists', BOLD)} {'yes  ' + _c(f"({cs['disk_size_kb']} KB)", DIM) if cs['disk_exists'] else _c('no', YELLOW)}
  {_c('LRU entries', BOLD)} {cs['lru_entries']} / {cs['lru_max']}
""")
    if keys:
        print(f"  {_c('Cached models:', BOLD)}")
        for k in sorted(keys):
            print(f"      {_c(k, DIM)}")
    else:
        print(f"  {_c('No models cached yet — they will be fetched on first use.', DIM)}")
    print()


def cmd_cache_clear(args) -> None:
    from llmcycle.providers.cache import get_model_info_cache
    cache = get_model_info_cache()
    cs    = cache.stats()
    n     = len(cache)

    if n == 0 and not cs["disk_exists"]:
        print(_c("\n  Cache is already empty.\n", DIM))
        return

    # Confirm unless --yes was passed
    if not getattr(args, "yes", False):
        disk_note = f" + disk file {_c(cs['cache_file'], DIM)}" if cs["disk_exists"] else ""
        answer = input(
            f"\n  Clear {_c(str(n), BOLD)} cached model entries{disk_note}? "
            f"[{_c('y', GREEN)}/N] "
        ).strip().lower()
        if answer not in ("y", "yes"):
            print(_c("  Aborted.\n", YELLOW))
            return

    cache.clear()
    print(f"\n{_c('✓', GREEN)}  Model info cache cleared.\n")


def cmd_cache_set_dir(args) -> None:
    """Write LLMCYCLE_CACHE_DIR to .env (with override confirmation if already set)."""
    new_dir  = Path(args.directory).resolve()
    env_path = Path(args.env_file)
    env_key  = "LLMCYCLE_CACHE_DIR"

    # Check if already set
    existing = os.environ.get(env_key, "").strip()
    if existing and existing != str(new_dir):
        if not getattr(args, "yes", False):
            answer = input(
                f"\n  {_c('LLMCYCLE_CACHE_DIR', YELLOW)} is already set to:\n"
                f"    {_c(existing, DIM)}\n"
                f"  Override with {_c(str(new_dir), CYAN)}? [{_c('y', GREEN)}/N] "
            ).strip().lower()
            if answer not in ("y", "yes"):
                print(_c("  Aborted.\n", YELLOW))
                return

    _set_env_key(env_path, env_key, str(new_dir))
    print(
        f"\n{_c('✓', GREEN)}  Cache directory set to {_c(str(new_dir), CYAN)}\n"
        f"    Written to {_c(str(env_path), DIM)}\n"
        f"    Folder structure: {_c(str(new_dir / 'model_info.json'), DIM)}\n"
    )
def cmd_ui(args) -> None:
    import uvicorn
    host = args.host or os.environ.get("LLMCYCLE_UI_HOST", "127.0.0.1")
    port = args.port or int(os.environ.get("LLMCYCLE_UI_PORT", "8000"))
    print(f"\n{_c('LLMCycle Dashboard', BOLD, CYAN)} → {_c(f'http://{host}:{port}', GREEN)}\n")
    uvicorn.run(
        "llmcycle.ui.app:app",
        host=host,
        port=port,
        reload=args.reload,
    )


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    _safe_load_env()

    parser = argparse.ArgumentParser(
        prog="llmcycle",
        description="LLMCycle — Universal LLM Router",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    sub = parser.add_subparsers(dest="command")

    # help
    sub.add_parser("help", help="Show detailed help and examples")

    # version
    sub.add_parser("version", help="Show installed version")

    # list
    sub.add_parser("list", help="List loaded providers + key health")

    # providers subcommand
    prov_p   = sub.add_parser("providers", help="Manage providers in .env")
    prov_sub = prov_p.add_subparsers(dest="prov_cmd")

    prov_sub.add_parser("list", help="List loaded providers + key health")

    prov_add_p = prov_sub.add_parser("add", help="Add custom or standard provider with keys and optional base URL")
    prov_add_p.add_argument("provider", help="Provider name (e.g. openai, apinex, deepseek)")
    prov_add_p.add_argument("keys", help="Comma-separated API key(s)")
    prov_add_p.add_argument("--base-url", default=None, dest="base_url", help="Base URL for custom/OpenAI-compatible endpoints")
    prov_add_p.add_argument("--env-file", default=".env", dest="env_file")

    prov_edit_p = prov_sub.add_parser("edit", help="Update provider base URL or API keys")
    prov_edit_p.add_argument("provider", help="Provider name to edit")
    prov_edit_p.add_argument("--base-url", default=None, dest="base_url", help="New base URL")
    prov_edit_p.add_argument("--keys", default=None, dest="keys", help="New comma-separated API keys")
    prov_edit_p.add_argument("--env-file", default=".env", dest="env_file")

    prov_rm_p = prov_sub.add_parser("remove", help="Delete provider and its keys and base URL from .env")
    prov_rm_p.add_argument("provider", help="Provider name to delete")
    prov_rm_p.add_argument("--env-file", default=".env", dest="env_file")

    prov_del_p = prov_sub.add_parser("delete", help="Alias for 'remove'")
    prov_del_p.add_argument("provider", help="Provider name to delete")
    prov_del_p.add_argument("--env-file", default=".env", dest="env_file")

    # ping
    ping_p = sub.add_parser("ping", help="Test connectivity to one or all providers")
    ping_p.add_argument("provider", nargs="?", default=None,
                        help="Provider name (omit to ping all)")

    # models
    models_p = sub.add_parser("models", help="Fetch and list dynamic live models across configured providers")
    models_p.add_argument("provider", nargs="?", default=None,
                          help="Provider name (omit to show models for all)")

    # config
    sub.add_parser("config", help="Show active configuration (includes cache info)")

    # keys subcommand
    keys_p   = sub.add_parser("keys", help="Manage API keys in .env")
    keys_sub = keys_p.add_subparsers(dest="keys_cmd")

    keys_add_p = keys_sub.add_parser("add", help="Add / append API key(s) to .env")
    keys_add_p.add_argument("provider", help="Provider name (e.g. openai, groq, deepseek)")
    keys_add_p.add_argument("keys", help="Comma-separated key(s)  e.g. sk-key1,sk-key2")
    keys_add_p.add_argument("--env-file", default=".env", dest="env_file")

    keys_edit_p = keys_sub.add_parser("edit", help="Replace all API keys for provider in .env")
    keys_edit_p.add_argument("provider", help="Provider name")
    keys_edit_p.add_argument("keys", help="New comma-separated keys")
    keys_edit_p.add_argument("--env-file", default=".env", dest="env_file")

    keys_list_p = keys_sub.add_parser("list", help="Show all keys in .env (masked)")
    keys_list_p.add_argument("--env-file", default=".env", dest="env_file")

    keys_rm_p = keys_sub.add_parser("remove", help="Remove a provider's keys or single key from .env")
    keys_rm_p.add_argument("provider", help="Provider name")
    keys_rm_p.add_argument("key", nargs="?", default=None, help="Optional specific key or masked hint to remove")
    keys_rm_p.add_argument("--clean-url", action="store_true", default=False, dest="clean_url",
                           help="Also remove provider base URL from .env")
    keys_rm_p.add_argument("--env-file", default=".env", dest="env_file")

    # proxy subcommand
    proxy_p   = sub.add_parser("proxy", help="Manage egress proxy setting")
    proxy_sub = proxy_p.add_subparsers(dest="proxy_cmd")

    proxy_show_p = proxy_sub.add_parser("show", help="Show active egress proxy")
    proxy_show_p.add_argument("--env-file", default=".env", dest="env_file")

    proxy_set_p = proxy_sub.add_parser("set", help="Set egress proxy URL (writes to .env)")
    proxy_set_p.add_argument("url", help="Proxy URL (e.g. http://127.0.0.1:8080)")
    proxy_set_p.add_argument("--env-file", default=".env", dest="env_file")

    proxy_clr_p = proxy_sub.add_parser("clear", help="Clear egress proxy URL from .env")
    proxy_clr_p.add_argument("--env-file", default=".env", dest="env_file")

    # cache subcommand
    cache_p   = sub.add_parser("cache", help="Manage the model-info disk cache")
    cache_sub = cache_p.add_subparsers(dest="cache_cmd")

    cache_sub.add_parser("show", help="Show cache stats and file location")

    cache_clr = cache_sub.add_parser("clear", help="Wipe LRU + disk cache (asks to confirm)")
    cache_clr.add_argument("-y", "--yes", action="store_true",
                           help="Skip confirmation prompt")

    cache_dir_p = cache_sub.add_parser(
        "set-dir", help="Override cache directory (writes LLMCYCLE_CACHE_DIR to .env)"
    )
    cache_dir_p.add_argument("directory", help="New cache directory path")
    cache_dir_p.add_argument("--env-file", default=".env", dest="env_file")
    cache_dir_p.add_argument("-y", "--yes", action="store_true",
                             help="Override without confirmation if already set")

    # aliases subcommand
    alias_p   = sub.add_parser("aliases", aliases=["alias"], help="Manage universal model aliases")
    alias_sub = alias_p.add_subparsers(dest="alias_cmd")
    alias_sub.add_parser("list", help="List configured model aliases")
    alias_add_p = alias_sub.add_parser("add", help="Add a model alias")
    alias_add_p.add_argument("name", help="Alias name (e.g. smart-model)")
    alias_add_p.add_argument("target", help="Target model (e.g. openai/gpt-4o)")
    alias_rm_p = alias_sub.add_parser("remove", aliases=["rm", "delete"], help="Remove a model alias")
    alias_rm_p.add_argument("name", help="Alias name to remove")

    # circuit subcommand
    circ_p   = sub.add_parser("circuit", help="Inspect and reset circuit breakers")
    circ_sub = circ_p.add_subparsers(dest="circuit_cmd")
    circ_sub.add_parser("list", help="List circuit breaker states across providers and keys")
    circ_reset_p = circ_sub.add_parser("reset", help="Reset circuit breakers")
    circ_reset_p.add_argument("provider", nargs="?", default=None, help="Provider name (omit to reset all)")

    # ui
    ui_p = sub.add_parser("ui", help="Start the web dashboard")
    ui_p.add_argument("--host", default=None,
                      help="Host to bind (default: LLMCYCLE_UI_HOST or 127.0.0.1)")
    ui_p.add_argument("--port", type=int, default=None,
                      help="Port (default: LLMCYCLE_UI_PORT or 8000)")
    ui_p.add_argument("--reload", action="store_true", default=False,
                      help="Auto-reload on code changes (dev mode)")

    # ── dispatch ──────────────────────────────────────────────────────────────
    args = parser.parse_args()

    if args.command in ("help", None):
        cmd_help(args)

    elif args.command == "version":
        cmd_version(args)

    elif args.command == "list":
        cmd_list(args)

    elif args.command == "providers":
        if not args.prov_cmd or args.prov_cmd == "list":
            cmd_list(args)
        elif args.prov_cmd == "add":
            cmd_providers_add(args)
        elif args.prov_cmd == "edit":
            cmd_providers_edit(args)
        elif args.prov_cmd in ("remove", "delete"):
            cmd_providers_remove(args)

    elif args.command == "ping":
        cmd_ping(args)

    elif args.command == "models":
        cmd_models(args)

    elif args.command == "config":
        cmd_config(args)

    elif args.command in ("aliases", "alias"):
        if not args.alias_cmd:
            args.alias_cmd = "list"
        cmd_aliases(args)

    elif args.command == "circuit":
        if not args.circuit_cmd:
            args.circuit_cmd = "list"
        cmd_circuit(args)

    elif args.command == "keys":
        if not args.keys_cmd:
            keys_p.print_help()
        elif args.keys_cmd == "add":
            cmd_keys_add(args)
        elif args.keys_cmd == "edit":
            cmd_keys_edit(args)
        elif args.keys_cmd == "list":
            cmd_keys_list(args)
        elif args.keys_cmd == "remove":
            cmd_keys_remove(args)

    elif args.command == "proxy":
        if not args.proxy_cmd:
            args.proxy_cmd = "show"
        cmd_proxy(args)

    elif args.command == "cache":
        if not args.cache_cmd:
            cache_p.print_help()
        elif args.cache_cmd == "show":
            cmd_cache_show(args)
        elif args.cache_cmd == "clear":
            cmd_cache_clear(args)
        elif args.cache_cmd == "set-dir":
            cmd_cache_set_dir(args)

    elif args.command == "ui":
        cmd_ui(args)

    else:
        cmd_help(args)


if __name__ == "__main__":
    main()
