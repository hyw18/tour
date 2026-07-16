from threading import Thread

import pytest
from werkzeug.serving import make_server

from app import create_app


playwright_api = pytest.importorskip("playwright.sync_api")


def test_landscape_player_ui_purchase_build_sell_and_refresh(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({
        "TESTING": True,
        "APP_MODE": "development",
        "HOST_TOKEN": "browser-test-token",
        "DISABLE_AUTOMATION": True,
    })
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with playwright_api.sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
            except playwright_api.Error as exc:
                pytest.skip(f"Playwright Chromium is not installed: {exc}")
            host_context = browser.new_context(viewport={"width": 1280, "height": 720})
            player_contexts = [browser.new_context(viewport={"width": 1280, "height": 720}) for _ in range(4)]
            host = host_context.new_page()
            players = [context.new_page() for context in player_contexts]
            player = players[0]
            console_errors = []
            server_errors = []
            for page in [host, *players]:
                page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                page.on("response", lambda response: server_errors.append(response.url) if response.status >= 500 else None)

            host.goto(f"{base_url}/host")
            host.locator("#hostToken").fill("browser-test-token")
            host.locator("#hostLogin").click()
            host.locator("#totalSlots").wait_for(state="visible")
            host.locator("#totalSlots").select_option("4")
            for index in range(4):
                host.locator(f'[data-slot-type="{index}"]').select_option("human")
            host.locator("#saveConfig").click()

            for index, page in enumerate(players):
                page.goto(f"{base_url}/player")
                page.locator("#nickname").fill("Mobile" if index == 0 else f"Player{index + 1}")
                page.locator("#joinForm button").click()
                page.locator("#playerBadge").filter(has_text="Mobile" if index == 0 else f"Player{index + 1}").wait_for()
                page.locator("#helpModal").wait_for(state="visible")
                page.locator("#closeHelp").click()
            player_id = player.evaluate("localStorage.getItem('tour_player_id')")

            host.locator("#startGame").wait_for(state="visible")
            host.locator("#startGame").click()
            player.locator("#rollDice:not([disabled])").wait_for()
            player.locator("#turnTimer").filter(has_text="주사위 선택").wait_for()
            player.locator("#turnStepIndicator").filter(has_text="주사위").wait_for()

            host.locator("#forcedDice").fill("1")
            host.locator('[data-dev="force-dice"]').click()
            player.locator("#rollDice").click()
            player.locator("#turnTimer").filter(has_text="제한시간 정지").wait_for()
            player.locator("#purchaseLand:not([disabled])").wait_for()
            player.locator("#turnTimer").filter(has_text="토지 구매 결정").wait_for()
            player.wait_for_function("turnPerformanceLog.length > 0")
            first_timeline = player.evaluate("turnPerformanceLog.at(-1)")
            assert first_timeline["scene_order"][:3] == ["DICE_REVEAL", "PIECE_MOVEMENT", "ARRIVAL_REVEAL"]
            assert first_timeline["input_enabled_after_ms"] >= 2000
            assert first_timeline["input_enabled_after_ms"] < 7000
            player.locator("#purchaseLand").click()
            player.locator("#actionConfirmModal").wait_for(state="visible")
            step_before_reopen = player.evaluate("async (id) => (await (await fetch(`/api/player/${id}/private`)).json()).turn_step", player_id)
            player.locator("#cancelActionConfirm").click()
            player.locator("#purchaseLand").click()
            player.locator("#actionConfirmModal").wait_for(state="visible")
            step_after_reopen = player.evaluate("async (id) => (await (await fetch(`/api/player/${id}/private`)).json()).turn_step", player_id)
            assert step_after_reopen["step_sequence"] == step_before_reopen["step_sequence"]
            assert step_after_reopen["deadline_at"] == step_before_reopen["deadline_at"]
            player.locator("#confirmAction").click()
            player.locator("#actionConfirmModal").wait_for(state="hidden")

            for _ in range(4):
                host.locator('[data-dev="force-end-turn"]').click()
            host.locator("#targetPlayerId").fill(player_id)
            host.locator("#targetPosition").fill("0")
            host.locator('[data-dev="set-position"]').click()
            host.locator("#forcedDice").fill("1")
            host.locator('[data-dev="force-dice"]').click()
            player.locator("#rollDice:not([disabled])").wait_for()
            player.locator("#rollDice").click()
            player.locator("#buildingType").select_option("commercial")
            player.locator("#build:not([disabled])").click()
            player.locator("#buildConfirmModal").wait_for(state="visible")
            player.locator("#turnTimer").filter(has_text="건물 건설 확인").wait_for()
            player.locator("#confirmBuild:not([disabled])").click()
            player.locator("#buildConfirmModal").wait_for(state="hidden")

            player.locator("#openFinance").click()
            player.locator("#financeAssetsPanel").filter(has_text="김천 · 상업").wait_for()
            player.locator("#closeFinance").click()
            player.reload()
            player.locator("#playerBadge").filter(has_text="Mobile").wait_for()
            assert player.locator("#joinForm").is_hidden()
            player.set_viewport_size({"width": 720, "height": 1280})
            player.set_viewport_size({"width": 1280, "height": 720})

            for _ in range(4):
                host.locator('[data-dev="force-end-turn"]').click()
            host.locator("#targetPosition").fill("0")
            host.locator('[data-dev="set-position"]').click()
            host.locator("#forcedDice").fill("1")
            host.locator('[data-dev="force-dice"]').click()
            player.locator("#rollDice:not([disabled])").wait_for()
            player.locator("#rollDice").click()
            player.locator("#manageAction:not([disabled])").click()
            sell = player.locator('[data-manage="sell"]:not([disabled])')
            sell.wait_for()
            sell.click()
            player.locator("#actionConfirmModal").wait_for(state="visible")
            player.locator("#confirmAction").click()
            player.locator("#actionMessage").filter(has_text="행동을 완료했습니다").wait_for()
            player.locator("#openFinance").click()
            player.locator('[data-finance-tab="history"]').click()
            player.locator("#financeHistoryPanel").filter(has_text="예정 환급").wait_for()
            assert "550,000원" in player.locator("#financeHistoryPanel").inner_text()
            assert console_errors == []
            assert server_errors == []

            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=3)
