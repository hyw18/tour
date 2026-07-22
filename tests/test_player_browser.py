from threading import Thread
import os
from time import monotonic, sleep
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from app import create_app


playwright_api = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[1]
LOCAL_PLAYWRIGHT_LIBS = ROOT / ".playwright-libs/root/usr/lib/x86_64-linux-gnu"
if LOCAL_PLAYWRIGHT_LIBS.exists():
    current_library_path = os.environ.get("LD_LIBRARY_PATH")
    os.environ["LD_LIBRARY_PATH"] = f"{LOCAL_PLAYWRIGHT_LIBS}{':' + current_library_path if current_library_path else ''}"


def launch_chromium(playwright):
    try:
        return playwright.chromium.launch(headless=True)
    except playwright_api.Error as exc:
        pytest.skip(f"Playwright Chromium is not installed: {exc}")


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
            browser = launch_chromium(playwright)
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
            player.locator("#turnTimer").filter(has_text="토지 구매").wait_for()
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


def finish_current_turn_without_browser_wait(engine, player_id):
    for _ in range(10):
        if engine.current_player().id != player_id:
            return
        private = engine.player_private_state(player_id)
        if engine.state.pending_action and private["allowed_actions"]["decline_action"]["allowed"]:
            engine.decline_pending_action(player_id)
            engine.complete_turn_presentation(player_id)
            continue
        pending_events = private.get("pending_event_occurrences") or []
        if pending_events:
            engine.acknowledge_events(player_id, len(engine.state.event_history), pending_events[0]["occurrence_id"])
            engine.complete_turn_presentation(player_id)
            continue
        if private["allowed_actions"]["end_turn"]["allowed"]:
            engine.end_turn(player_id)
            continue
        if not (engine.state.turn_step or {}).get("user_input_required"):
            engine.complete_turn_presentation(player_id)
            continue
        return


def browser_roll_button_state(page):
    return page.evaluate("""() => {
        const button = document.querySelector("#rollDice");
        const primary = document.querySelector("#primaryActions");
        const secondary = document.querySelector("#secondaryActions");
        if (!button) return {exists: false};
        const style = window.getComputedStyle(button);
        return {
            exists: true,
            disabled: button.disabled,
            hidden: button.hidden,
            display: style.display,
            visibility: style.visibility,
            text: button.textContent.trim(),
            parent_id: button.parentElement?.id || null,
            primary_text: primary?.textContent.trim() || "",
            secondary_text: secondary?.textContent.trim() || "",
        };
    }""")


def test_browser_one_hundred_human_turns_have_no_stale_roll_lock(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({
        "TESTING": True,
        "APP_MODE": "development",
        "HOST_TOKEN": "browser-test-token",
        "DISABLE_AUTOMATION": True,
    })
    client = app.test_client()
    csrf = client.post("/api/host/login", json={"token": "browser-test-token"}).get_json()["csrf_token"]
    config = client.post("/api/config", json={
        "total_slots": 4,
        "slot_types": ["human", "bot", "bot", "bot"],
        "bot_strategies": ["balanced", "balanced", "balanced", "balanced"],
        "total_rounds": 100,
        "fast_simulation": True,
        "bot_action_delay": 0,
    }, headers={"X-CSRF-Token": csrf, "Idempotency-Key": "config-browser-100"})
    assert config.status_code == 200
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    console_errors = []
    server_errors = []
    stale_locks = []
    disabled_rolls = []

    try:
        with playwright_api.sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            context = browser.new_context(viewport={"width": 1280, "height": 720})
            page = context.new_page()
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.on("response", lambda response: server_errors.append(response.url) if response.status >= 500 else None)
            page.goto(f"{base_url}/player")
            page.evaluate("localStorage.setItem('tour_animation_preference', 'minimal')")
            page.locator("#nickname").fill("Browser100")
            page.locator("#joinForm button").click()
            page.locator("#playerBadge").filter(has_text="Browser100").wait_for()
            page.locator("#helpModal").wait_for(state="visible")
            page.locator("#closeHelp").click()
            player_id = page.evaluate("localStorage.getItem('tour_player_id')")

            start = client.post("/api/start", json={}, headers={"X-CSRF-Token": csrf, "Idempotency-Key": "start-browser-100"})
            assert start.status_code == 200
            engine = app.config["GAME_ENGINE"]

            for turn in range(100):
                while engine.current_player().id != player_id:
                    engine.take_turn_for_player(engine.current_player().id, source="browser_test_bot")
                page.evaluate("scheduleRefresh(true)")
                page.wait_for_function(
                    "() => window.getTourDebugState && window.getTourDebugState().currentRollServerAllowed === true",
                    timeout=5000,
                )
                try:
                    page.locator("#rollDice:not([disabled])").wait_for(timeout=5000)
                except playwright_api.TimeoutError as exc:
                    raise AssertionError({
                        "turn": turn,
                        "debug": page.evaluate("window.getTourDebugState()"),
                        "button": browser_roll_button_state(page),
                    }) from exc
                debug = page.evaluate("window.getTourDebugState()")
                stale = [
                    task for task in debug["animationTasks"]
                    if task.get("blocking") and task.get("turnId") != debug["lastPrivateTurnStep"].get("turn_id")
                ]
                if stale:
                    stale_locks.append({"turn": turn, "debug": debug, "stale": stale})
                if debug["rollButtonDisabled"]:
                    disabled_rolls.append({"turn": turn, "debug": debug})
                    raise AssertionError({
                        "turn": turn,
                        "button": browser_roll_button_state(page),
                        "debug": {
                            "actionInFlight": debug.get("actionInFlight"),
                            "requestLockIdentity": debug.get("requestLockIdentity"),
                            "turnPresentationState": debug.get("turnPresentationState"),
                            "animationTasks": debug.get("animationTasks"),
                            "animationState": debug.get("animationState"),
                            "currentRollServerAllowed": debug.get("currentRollServerAllowed"),
                            "lastPrivateTurnStep": debug.get("lastPrivateTurnStep"),
                            "lastPrivateAllowedRoll": debug.get("lastPrivateAllowedActions", {}).get("roll"),
                        },
                    })
                engine.set_forced_dice((turn % 6) + 1)
                page.locator("#rollDice").click()
                deadline = monotonic() + 5
                while not engine.state.turn_has_rolled and monotonic() < deadline:
                    sleep(0.05)
                assert engine.state.turn_has_rolled is True
                finish_current_turn_without_browser_wait(engine, player_id)

            page.wait_for_function(
                """() => window.getTourDebugState
                    && window.getTourDebugState().animationTasks.every((task) => !task.blocking)""",
                timeout=10000,
            )
            final_debug = page.evaluate("window.getTourDebugState()")
            orphan_blocking = [task for task in final_debug["animationTasks"] if task.get("blocking")]
            assert disabled_rolls == []
            assert stale_locks == []
            assert orphan_blocking == []
            assert console_errors == []
            assert server_errors == []
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=3)
