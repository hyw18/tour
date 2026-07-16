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
            player_context = browser.new_context(viewport={"width": 1280, "height": 720})
            host = host_context.new_page()
            player = player_context.new_page()

            host.goto(f"{base_url}/host")
            host.locator("#hostToken").fill("browser-test-token")
            host.locator("#hostLogin").click()
            host.locator("#totalSlots").wait_for(state="visible")
            host.locator("#totalSlots").select_option("3")
            host.locator('[data-slot-type="0"]').select_option("human")
            host.locator('[data-slot-type="1"]').select_option("bot")
            host.locator('[data-slot-type="2"]').select_option("bot")
            host.locator("#saveConfig").click()

            player.goto(f"{base_url}/player")
            player.locator("#nickname").fill("Mobile")
            player.locator("#joinForm button").click()
            player.locator("#playerBadge").filter(has_text="Mobile").wait_for()
            player_id = player.evaluate("localStorage.getItem('tour_player_id')")

            host.locator("#startGame").wait_for(state="visible")
            host.locator("#startGame").click()
            player.locator("#rollDice:not([disabled])").wait_for()

            host.locator("#forcedDice").fill("1")
            host.locator('[data-dev="force-dice"]').click()
            player.locator("#rollDice").click()
            player.locator("#purchaseLand:not([disabled])").wait_for()
            player.locator("#purchaseLand").click()
            player.locator("#actionConfirmModal").wait_for(state="visible")
            player.locator("#confirmAction").click()
            player.locator("#actionConfirmModal").wait_for(state="hidden")

            for _ in range(3):
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
            player.locator("#confirmBuild:not([disabled])").click()
            player.locator("#buildConfirmModal").wait_for(state="hidden")

            player.locator("#openFinance").click()
            player.locator("#assetPanel").filter(has_text="김천 · 상업").wait_for()
            player.locator("#closeFinance").click()
            player.reload()
            player.locator("#playerBadge").filter(has_text="Mobile").wait_for()
            assert player.locator("#joinForm").is_hidden()

            for _ in range(3):
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
            player.locator("#actionMessage").filter(has_text="처리되었습니다").wait_for()
            player.locator("#openFinance").click()
            player.locator('[data-finance-tab="history"]').click()
            player.locator("#assetPanel").filter(has_text="상업 매각 예정 환급").wait_for()
            assert "550,000원" in player.locator("#assetPanel").inner_text()

            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=3)
