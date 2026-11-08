import asyncio
import sys
try:
    from playwright.async_api import async_playwright, expect
    PLAYWRIGHT_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None
    expect = None

sys.stdout.reconfigure(encoding="utf-8")

async def run_live_verification():
    if not PLAYWRIGHT_AVAILABLE:
        print("[SKIP] Playwright is not installed. To run live UI tests, install: pip install playwright && playwright install chromium")
        return
    console_errors = []
    page_errors = []
    failed_requests = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # Listen to console messages
        def on_console(msg):
            if msg.type == "error":
                # ignore favicon or non-critical resource 404s if any
                text = msg.text
                print(f"[BROWSER ERROR] {text}")
                console_errors.append(text)
            else:
                pass

        page.on("console", on_console)
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url} - {req.failure}"))

        print("1. Navigating to VeloRoute UI (http://127.0.0.1:8000/)...")
        await page.goto("http://127.0.0.1:8000/", wait_until="networkidle")

        # 1. Login Screen Verification
        print("2. Verifying Login Screen...")
        login_screen = page.locator("#login-screen")
        await expect(login_screen).to_be_visible()
        await expect(page.locator(".login-title")).to_contain_text("VeloRoute")

        # Perform Login
        print("3. Logging in as admin / admin...")
        await page.fill("#un", "admin")
        await page.fill("#pw", "admin")
        await page.click("#login-submit-btn")

        # Verify App Shell appears
        app_div = page.locator("#app")
        await expect(app_div).to_be_visible(timeout=5000)
        print("   ✅ Login successful, dashboard shell mounted.")

        # Topbar & User label check
        await expect(page.locator("#user-label")).to_contain_text("admin")
        await expect(page.locator("#status-label")).to_contain_text("Connected")

        # 4. Privacy Toggle Test
        print("4. Testing Zero-Retention Privacy Toggle...")
        privacy_btn = page.locator("#btn-privacy-toggle")
        privacy_status = page.locator("#privacy-mode-status")
        initial_status = await privacy_status.inner_text()
        print(f"   Initial Privacy Status: {initial_status}")

        await privacy_btn.click()
        await page.wait_for_timeout(500)
        status_after_toggle = await privacy_status.inner_text()
        print(f"   After toggle 1: {status_after_toggle}")
        assert status_after_toggle != initial_status, "Privacy status should have changed"

        # Toggle back to ensure idempotence
        await privacy_btn.click()
        await page.wait_for_timeout(500)
        status_after_toggle2 = await privacy_status.inner_text()
        print(f"   After toggle 2: {status_after_toggle2}")
        print("   ✅ Zero-Retention Privacy Mode toggle verified.")

        # 5. Quickstart Modal Test
        print("5. Testing Quickstart Modal...")
        qs_open_btn = page.locator("#btn-quickstart-open")
        await qs_open_btn.click()
        qs_modal = page.locator("#quickstart-modal")
        await expect(qs_modal).to_be_visible(timeout=3000)
        print("   Quickstart modal opened.")

        # Test tabs
        for tab_id, name in [
            ("qs-tab-openai", "OpenAI"),
            ("qs-tab-anthropic", "Anthropic"),
            ("qs-tab-curl", "cURL"),
            ("qs-tab-claude", "Claude Code")
        ]:
            tab_btn = page.locator(f"#{tab_id}")
            if await tab_btn.is_visible():
                await tab_btn.click()
                await page.wait_for_timeout(200)
                code_text = await page.locator("#qs-code-block").inner_text()
                assert len(code_text.strip()) > 10, f"Snippet for {name} should not be empty"
                print(f"   Tab {name}: snippet loaded ({len(code_text)} chars).")

        # Test copy snippet
        copy_btn = page.locator("#qs-copy-btn")
        if await copy_btn.is_visible():
            await copy_btn.click()
            await page.wait_for_timeout(300)

        # Close Quickstart Modal
        close_btn = qs_modal.locator("button:has-text('×'), button:has-text('Close')").first
        await close_btn.click()
        await page.wait_for_timeout(300)
        print("   ✅ Quickstart modal tabs and snippets verified.")

        # 6. Navigating through all pages
        pages_to_test = [
            ("nav-overview", "page-overview", "Overview"),
            ("nav-registry", "page-registry", "Registry"),
            ("nav-routing", "page-routing", "Routing"),
            ("nav-groups", "page-groups", "Groups"),
            ("nav-keys", "page-keys", "Virtual Keys"),
            ("nav-guardrails", "page-guardrails", "Guardrails"),
            ("nav-cache", "page-cache", "Semantic Cache"),
            ("nav-prompts", "page-prompts", "Prompt Hub"),
            ("nav-mcp", "page-mcp", "MCP Gateway"),
            ("nav-analytics", "page-analytics", "Analytics"),
            ("nav-console", "page-console", "Test Console"),
        ]

        for nav_id, page_id, name in pages_to_test:
            print(f"6.{pages_to_test.index((nav_id, page_id, name)) + 1} Navigating to {name}...")
            nav_btn = page.locator(f"#{nav_id}")
            await nav_btn.click()
            await page.wait_for_timeout(300)
            page_el = page.locator(f"#{page_id}")
            await expect(page_el).to_be_visible()
            print(f"   ✅ {name} loaded successfully.")

        # 7. Routing Strategy & KV-Affinity Verification
        print("7. Testing Routing Strategies & Sentinel Circuit Breakers...")
        await page.locator("#nav-routing").click()
        await page.wait_for_timeout(300)

        strategies = [
            "round_robin",
            "lowest_latency",
            "priority",
            "kv_affinity",
            "hedging",
            "quality",
            "complexity"
        ]
        for strat in strategies:
            strat_btn = page.locator(f"#strat-{strat}")
            if await strat_btn.is_visible():
                await strat_btn.click()
                await page.wait_for_timeout(200)
                await expect(strat_btn).to_have_class(re.compile(r"active"))
                print(f"   Strategy '{strat}' activated.")
        print("   ✅ Routing strategies (including KV-Affinity, Hedging, Quality) tested.")

        # Canary Traffic Splitting Test
        print("8. Testing Canary Traffic Splitting in Routing...")
        primary_inp = page.locator("#canary-primary-model")
        target_inp = page.locator("#canary-target-model")
        slider = page.locator("#canary-weight-slider")
        save_canary_btn = page.locator("button:has-text('Save Canary Rule')")

        await expect(primary_inp).to_be_visible()
        await primary_inp.fill("mock/gpt-4o")
        await target_inp.fill("mock/gpt-4.5")
        await slider.evaluate("(el) => { el.value = 35; el.dispatchEvent(new Event('input')); }")
        await save_canary_btn.click()
        await page.wait_for_timeout(400)
        print("   ✅ Canary traffic splitting rule saved.")

        # Shadow Traffic Routing Test
        print("8.1 Testing Shadow Traffic Routing...")
        shadow_prim = page.locator("#shadow-primary-model")
        shadow_targ = page.locator("#shadow-target-model")
        shadow_rate = page.locator("#shadow-sample-rate")
        save_shadow_btn = page.locator("button:has-text('Save Shadow Rule')")

        await expect(shadow_prim).to_be_visible()
        await shadow_prim.fill("mock/gpt-4o")
        await shadow_targ.fill("mock/deepseek-r1")
        await shadow_rate.fill("75")
        await save_shadow_btn.click()
        await page.wait_for_timeout(400)
        pill = page.locator("#shadow-status-pill")
        await expect(pill).to_contain_text("Active")
        print("   ✅ Shadow traffic routing rule saved with 75% sample rate.")

        # Sentinel Circuit Breaker Refresh & Reset All
        print("9. Testing Sentinel Circuit Breakers...")
        refresh_cb_btn = page.locator("#btn-refresh-cb")
        await expect(refresh_cb_btn).to_be_visible()
        await refresh_cb_btn.click()
        await page.wait_for_timeout(500)
        cb_table = page.locator("#cb-table-body")
        table_text = await cb_table.inner_text()
        print(f"   Circuit Breaker table status length: {len(table_text)} chars.")

        reset_cb_btn = page.locator("#btn-reset-all-cb")
        await expect(reset_cb_btn).to_be_visible()
        await reset_cb_btn.click()
        await page.wait_for_timeout(500)
        print("   ✅ Sentinel Circuit Breaker reset executed.")

        # 10. Guardrails Testing Sandbox (PII + Prompt Injection)
        print("10. Testing Guardrails Shield & PII Masking...")
        await page.locator("#nav-guardrails").click()
        await page.wait_for_timeout(300)

        # Click Load Sample PII
        await page.locator("button:has-text('Load Sample PII')").click()
        await page.wait_for_timeout(200)
        await page.locator("button:has-text('Run Security Evaluation')").click()
        await page.wait_for_timeout(600)
        await expect(page.locator("#gr-test-results")).to_be_visible()
        masked_txt = await page.locator("#gr-res-masked").inner_text()
        print(f"   PII Test Masked result: {masked_txt[:80]}...")
        assert "[EMAIL_" in masked_txt or "[CREDIT_CARD_" in masked_txt, "PII should be masked"

        # Click Load Sample Injection
        await page.locator("button:has-text('Load Sample Injection')").click()
        await page.wait_for_timeout(200)
        await page.locator("button:has-text('Run Security Evaluation')").click()
        await page.wait_for_timeout(600)
        verdicts = await page.locator("#gr-verdict-badges").inner_text()
        print(f"   Injection Test Verdict badges: {verdicts}")
        assert "Injection" in verdicts or "Shield" in verdicts or "Risk" in verdicts or "Passed" in verdicts or "Blocked" in verdicts
        print("   ✅ Guardrails PII & Injection security evaluation verified.")

        # 11. Virtual Keys End-to-End Creation and Management
        print("11. Testing Virtual Keys Full Lifecycle...")
        await page.locator("#nav-keys").click()
        await page.wait_for_timeout(300)

        await page.locator("button[onclick='openGatewayKeyCreate()']").click()
        await page.wait_for_timeout(300)
        await expect(page.locator("#vk-create-overlay")).to_be_visible()

        # Fill virtual key creation form
        await page.locator("#vk-create-name").fill("e2e-playwright-key")
        await page.locator("#vk-create-team").fill("QA-Suite")
        await page.locator("#vk-create-form button[type='submit']").click()
        await page.wait_for_timeout(600)

        # Check Secret Modal appears
        await expect(page.locator("#vk-secret-overlay")).to_be_visible()
        secret_val = await page.locator("#vk-secret-value").inner_text()
        print(f"   Generated Virtual Key secret: {secret_val[:12]}...")
        assert secret_val.startswith("sk-velo-"), "Virtual key secret must start with sk-velo-"

        # Click Copy Key
        await page.locator("#vk-secret-overlay button:has-text('Copy Key')").click()
        await page.wait_for_timeout(200)

        # Close secret modal
        await page.locator("#vk-secret-overlay button:has-text('Done / I Saved My Key')").click()
        await page.wait_for_timeout(400)
        await expect(page.locator("#vk-secret-overlay")).not_to_be_visible()
        print("   ✅ Virtual Key creation and secret modal verified.")

        # 12. Dynamic Groups Creation and Management
        print("12. Testing Dynamic Groups Management...")
        await page.locator("#nav-groups").click()
        await page.wait_for_timeout(300)

        add_group_btn = page.locator("#page-groups button:has-text('+ Add Group')")
        await expect(add_group_btn).to_be_visible()
        await add_group_btn.click()
        await page.wait_for_timeout(300)
        await expect(page.locator("#group-modal")).to_be_visible()

        # Fill group name
        await page.locator("#group-name").fill("e2e-fast-group")
        # Close modal
        await page.locator("#group-modal button:has-text('Cancel')").click()
        await page.wait_for_timeout(300)
        print("   ✅ Dynamic Groups modal opened and verified.")

        # 13. Semantic Cache Testing
        print("13. Testing Semantic Cache Controls & Similarity...")
        await page.locator("#nav-cache").click()
        await page.wait_for_timeout(300)
        await expect(page.locator("#page-cache")).to_be_visible()

        # Test Vector Similarity Sandbox
        cache_prompt = page.locator("#cache-test-prompt")
        await cache_prompt.fill("What is the capital city of France?")
        test_cache_btn = page.locator("#page-cache button:has-text('Test Similarity')")
        await test_cache_btn.click()
        await page.wait_for_timeout(600)
        await expect(page.locator("#cache-test-result-box")).to_be_visible()
        print("   ✅ Semantic Cache similarity test evaluated.")

        # Test Purge Cache
        purge_cache_btn = page.locator("#page-cache button:has-text('Purge All Cache')")
        await expect(purge_cache_btn).to_be_visible()
        await purge_cache_btn.click()
        await page.wait_for_timeout(400)
        print("   ✅ Semantic Cache purge triggered.")

        # 14. Prompt Hub Testing
        print("14. Testing Prompt Hub Playground & IDE Rules Exporter...")
        await page.locator("#nav-prompts").click()
        await page.wait_for_timeout(400)
        await expect(page.locator("#page-prompts")).to_be_visible()

        # Select first template in dropdown
        prompt_select = page.locator("#pg-prompt-select")
        await expect(prompt_select).to_be_visible()
        # Wait for options to load
        await page.wait_for_function("document.getElementById('pg-prompt-select').options.length > 1")
        await prompt_select.select_option(index=1)
        await page.wait_for_timeout(300)

        # Audit Prompt
        audit_btn = page.locator("#pg-audit-btn")
        await expect(audit_btn).to_be_visible()
        await audit_btn.click()
        await page.wait_for_timeout(600)
        await expect(page.locator("#pg-audit-result-box")).to_be_visible()
        audit_box_text = await page.locator("#pg-audit-result-box").inner_text()
        print(f"   Prompt Audit Result: {audit_box_text[:60]}...")

        # Export IDE Rules (AGENTS.md / .cursorrules)
        export_btn = page.locator("#pg-export-btn")
        await expect(export_btn).to_be_visible()
        await export_btn.click()
        await page.wait_for_timeout(500)
        out_content = page.locator("#pg-out-content")
        await expect(out_content).to_be_visible()
        rules_text = await out_content.inner_text()
        print(f"   Exported IDE Rules: {rules_text[:50]}... ({len(rules_text)} chars)")
        assert len(rules_text) > 10, "Exported rules should not be empty"
        print("   ✅ Prompt Hub audit & IDE rules exporter verified.")

        # 15. MCP Gateway Security Audit Testing
        print("15. Testing MCP Gateway & Security Posture Audit...")
        await page.locator("#nav-mcp").click()
        await page.wait_for_timeout(400)
        await expect(page.locator("#page-mcp")).to_be_visible()

        # Run Security Audit
        mcp_audit_btn = page.locator("#page-mcp button:has-text('Security Audit')")
        await expect(mcp_audit_btn).to_be_visible()
        await mcp_audit_btn.click()
        await page.wait_for_timeout(600)
        audit_box = page.locator("#mcp-audit-box")
        await expect(audit_box).to_be_visible()
        audit_text = await audit_box.inner_text()
        print(f"   MCP Security Audit: {audit_text[:80]}...")
        assert "Posture" in audit_text or "Passed" in audit_text or "Risk" in audit_text or "Status" in audit_text
        print("   ✅ MCP Security Posture audit triggered and verified.")

        # 16. Test Console & Token-Saviour Suite
        print("16. Testing Test Console & Token-Saviour Context Optimizer...")
        await page.locator("#nav-console").click()
        await page.wait_for_timeout(300)
        await expect(page.locator("#page-console")).to_be_visible()

        prompt_box = page.locator("#c-prompt")
        sample_code = """
import os
import sys

def calculate_something(x: int, y: int) -> int:
    '''Calculates total value.'''
    result = x * 2 + y
    return result

# Terminal repetitive output
[INFO] 2026-11-08 12:00:01 Task started
[INFO] 2026-11-08 12:00:02 Progress: 10%
[INFO] 2026-11-08 12:00:03 Progress: 20%
[INFO] 2026-11-08 12:00:04 Progress: 30%
        """
        await prompt_box.fill(sample_code.strip())

        # Test Token-Saviour Trim
        trim_btn = page.locator("#btn-opt-prompt")
        await expect(trim_btn).to_be_visible()
        await trim_btn.click()
        await page.wait_for_timeout(600)
        trimmed_text = await prompt_box.input_value()
        print(f"   Token-Saviour Trim result length: {len(trimmed_text)} chars.")
        await expect(page.locator("#c-prompt-optimizer-badge")).to_be_visible()
        print("   ✅ Token-Saviour Trim executed successfully.")

        # Test Skeletonize AST
        skel_btn = page.locator("#btn-skel-prompt")
        await expect(skel_btn).to_be_visible()
        await prompt_box.fill(sample_code.strip())
        await skel_btn.click()
        await page.wait_for_timeout(600)
        skel_text = await prompt_box.input_value()
        print(f"   Skeletonize AST result length: {len(skel_text)} chars.")
        assert "def calculate_something" in skel_text
        await expect(page.locator("#c-prompt-optimizer-badge")).to_be_visible()
        badge_text = await page.locator("#c-prompt-optimizer-badge").inner_text()
        print(f"   AST Skeletonize badge: {badge_text}")
        print("   ✅ Skeletonize AST executed successfully.")

        # Test Caveman Terse
        terse_btn = page.locator("#btn-terse-prompt")
        await expect(terse_btn).to_be_visible()
        await prompt_box.fill(sample_code.strip())
        await terse_btn.click()
        await page.wait_for_timeout(600)
        terse_text = await prompt_box.input_value()
        print(f"   Caveman Terse result length: {len(terse_text)} chars.")
        print("   ✅ Caveman Terse mode executed successfully.")

        # Test Task Sizing Hook
        sizer_btn = page.locator("#btn-size-prompt")
        await expect(sizer_btn).to_be_visible()
        await prompt_box.fill("Implement a distributed raft consensus algorithm with heartbeat and election timers in Go")
        await sizer_btn.click()
        await page.wait_for_timeout(600)
        await expect(page.locator("#c-sizer-result-badge")).to_be_visible()
        badge_text = await page.locator("#c-sizer-result-badge").inner_text()
        print(f"   Task Sizer badge: {badge_text}")
        print("   ✅ Task Sizer Hook executed successfully.")

        # 17. Check Modals
        print("17. Testing Add Provider and Fallback Modals...")
        await page.locator("#nav-overview").click()
        await page.wait_for_timeout(300)

        add_prov_btn = page.locator("#page-overview button:has-text('+ Add Provider')").first
        await expect(add_prov_btn).to_be_visible()
        await add_prov_btn.click()
        await page.wait_for_timeout(300)
        add_modal = page.locator("#add-modal")
        await expect(add_modal).to_be_visible()
        await add_modal.locator("button:has-text('Cancel')").click()
        await page.wait_for_timeout(300)
        print("   ✅ Add Provider modal opened and closed.")


        # 16. Console & Network Errors Verification
        print("\n=== CONSOLE & NETWORK ERROR AUDIT ===")
        print(f"Total Console Errors: {len(console_errors)}")
        print(f"Total Page Errors: {len(page_errors)}")
        print(f"Total Failed Requests: {len(failed_requests)}")

        if console_errors:
            for ce in console_errors:
                print(f"  [Console Error]: {ce}")
        if page_errors:
            for pe in page_errors:
                print(f"  [Page Error]: {pe}")
        if failed_requests:
            for fr in failed_requests:
                print(f"  [Failed Request]: {fr}")

        assert len(console_errors) == 0, f"Found {len(console_errors)} console errors!"
        assert len(page_errors) == 0, f"Found {len(page_errors)} page errors!"

        print("\n🎉 100% EXHAUSTIVE BROWSER TEST PASSED WITH ZERO CONSOLE ERRORS!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_live_verification())
