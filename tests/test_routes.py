from pathlib import Path

import pytest

from app import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DEBUG_GAME_TOOLS", raising=False)
    app = create_app({"TESTING": True, "APP_MODE": "development"})
    return app.test_client()


def post(client, url, body=None, key="k"):
    with client.session_transaction() as session:
        csrf = session.get("csrf_token")
    headers = {"Idempotency-Key": key}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return client.post(url, json=body or {}, headers=headers)


def authenticate(client):
    token = client.application.config["HOST_AUTH"].token
    response = client.post("/api/host/login", json={"token": token})
    assert response.status_code == 200
    return response


def test_host_and_player_pages_are_separate(client):
    host = client.get("/host")
    player = client.get("/player")
    assert b"host.js" in host.data
    assert b"player.js" in player.data


def test_host_dashboard_keeps_board_and_initialization_contract(client):
    host = client.get("/host")
    assert b'id="hostBoardGrid"' in host.data
    assert b'id="boardStatus"' in host.data
    assert b'id="serverStatus"' in host.data
    assert b'id="hostingStatusText"' in host.data
    source = (Path(client.application.static_folder) / "js/host.js").read_text()
    assert "function renderHostBoard(state)" in source
    assert "state.board.length !== 40" in source
    assert "async function initializeHostPage()" in source
    assert 'document.addEventListener("DOMContentLoaded", initializeHostPage' in source
    assert "await initializeHostDashboard()" in source


def test_host_lifecycle_preserves_real_board_for_twenty_cycles(client):
    authenticate(client)
    for cycle in range(20):
        configured = post(client, "/api/config", {
            "total_slots": 3,
            "slot_types": ["bot", "bot", "bot"],
            "bot_strategies": ["balanced", "aggressive", "conservative"],
            "total_rounds": 10,
        }, f"config-{cycle}")
        assert configured.status_code == 200
        setup = client.get("/api/host/state").get_json()
        assert setup["server_status"] == "online"
        assert setup["phase"] == "setup"
        assert len(setup["board"]) == 40
        assert post(client, "/api/start", key=f"start-{cycle}").status_code == 200
        active = client.get("/api/host/state").get_json()
        assert active["phase"] == "active"
        assert len(active["board"]) == 40
        assert post(client, "/api/pause", key=f"pause-{cycle}").status_code == 200
        assert post(client, "/api/resume", key=f"resume-{cycle}").status_code == 200
        assert post(client, "/api/host/finish", key=f"finish-{cycle}").status_code == 200
        assert post(client, "/api/host/new-game", {"keep_config": True}, f"new-{cycle}").status_code == 200
        prepared = client.get("/api/host/state").get_json()
        assert prepared["phase"] == "setup"
        assert len(prepared["board"]) == 40


def test_host_only_start_pause_resume_and_config(client):
    response = post(client, "/api/config", {"total_slots": 2})
    assert response.status_code == 403
    assert "host permission" in response.get_json()["error"]
    client.get("/host")
    assert post(client, "/api/config", {"total_slots": 2}, "still-blocked").status_code == 403
    authenticate(client)
    response = post(client, "/api/config", {
        "total_slots": 2,
        "slot_types": ["bot", "bot"],
        "bot_strategies": ["balanced", "random"],
        "total_rounds": 10,
        "turn_limit_seconds": 30,
        "bot_action_delay": 1,
        "fast_simulation": False,
    }, "cfg")
    assert response.status_code == 200
    assert post(client, "/api/start", key="start").status_code == 200
    assert post(client, "/api/pause", key="pause").status_code == 200
    assert post(client, "/api/resume", key="resume").status_code == 200


def test_join_idempotency_and_server_state(client):
    authenticate(client)
    post(client, "/api/config", {
        "total_slots": 2,
        "slot_types": ["human", "bot"],
        "bot_strategies": ["balanced", "balanced"],
    }, "cfg")
    first = post(client, "/api/join", {"nickname": "Alice"}, "join-key").get_json()
    assert first["nickname"] == "Alice"
    second_response = post(client, "/api/join", {"nickname": "Bob"}, "join-key")
    assert second_response.status_code == 409
    assert "different payload" in second_response.get_json()["error"]
    state = client.get("/api/state").get_json()
    assert len([player for player in state["players"] if not player["is_bot"]]) == 1


def test_debug_tools_are_404_when_env_disabled(client):
    authenticate(client)
    response = post(client, "/api/dev/force-dice", {"dice": 3}, "dev")
    assert response.status_code == 404


def test_debug_tools_visible_and_operational_when_enabled(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({"TESTING": True, "APP_MODE": "development"})
    client = app.test_client()
    authenticate(client)
    host = client.get("/host")
    assert b"debug-tools" in host.data
    post(client, "/api/config", {
        "total_slots": 2,
        "slot_types": ["human", "bot"],
        "bot_strategies": ["balanced", "balanced"],
        "total_rounds": 10,
        "turn_limit_seconds": 30,
        "bot_action_delay": 1,
        "fast_simulation": False,
    }, "cfg")
    player = post(client, "/api/join", {"nickname": "Alice"}, "join").get_json()
    post(client, "/api/start", key="start")
    assert post(client, "/api/dev/force-dice", {"dice": 4}, "dice").status_code == 200
    assert post(client, "/api/dev/set-position", {"player_id": player["id"], "position": 39}, "pos").status_code == 200
    assert post(client, "/api/dev/set-cash", {"player_id": player["id"], "cash_won": 12345}, "cash").status_code == 200
    assert post(client, "/api/dev/set-industrial-rate", {"rate_bps": 1200}, "rate").status_code == 200
    assert post(client, "/api/dev/set-tax-rate", {"player_id": player["id"], "tax_rate_bps": 100}, "taxrate").status_code == 200
    assert post(client, "/api/dev/create-loan", {"player_id": player["id"], "principal_won": 1000000}, "loan").status_code == 200
    assert post(client, "/api/dev/settle-start", {"player_id": player["id"]}, "settle").status_code == 200
    assert post(client, "/api/dev/run-laps", {"player_id": player["id"], "laps": 1}, "laps").status_code == 200
    assert post(client, "/api/dev/create-land", {"player_id": player["id"], "region_id": "gimcheon"}, "land").status_code == 200
    assert post(client, "/api/dev/create-building", {
        "player_id": player["id"],
        "region_id": "gimcheon",
        "building_type": "residential",
    }, "building").status_code == 200
    assert post(client, "/api/dev/set-special-visits", {"special_region_id": "pyeongchang", "visits": 2}, "spvisit").status_code == 200
    assert post(client, "/api/dev/force-special-sale-dice", {"dice": 6}, "spdice").status_code == 200
    state = client.get("/api/state").get_json()
    bot_id = next(item["id"] for item in state["players"] if item["is_bot"])
    assert post(client, "/api/dev/change-bot-strategy", {
        "player_id": bot_id,
        "strategy": "conservative",
    }, "strategy").status_code == 200
    assert post(client, "/api/dev/run-next-turns", {"turns": 1}, "turns").status_code == 200
    assert client.get("/api/dev/bot-summary").status_code == 200
    assert post(client, "/api/dev/run-bot-simulation", {"players": 2, "runs": 1, "total_rounds": 10}, "sim").status_code == 200


def test_operating_right_routes_are_idempotent_and_server_validated(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({"TESTING": True, "APP_MODE": "development"})
    client = app.test_client()
    authenticate(client)
    post(client, "/api/config", {
        "total_slots": 2,
        "slot_types": ["human", "human"],
        "bot_strategies": ["balanced", "balanced"],
    }, "cfg")
    a = post(client, "/api/join", {"nickname": "A"}, "join-a").get_json()
    b = post(client, "/api/join", {"nickname": "B"}, "join-b").get_json()
    post(client, "/api/start", key="start")
    post(client, "/api/dev/create-land", {"player_id": a["id"], "region_id": "gimcheon"}, "land")
    post(client, "/api/dev/create-building", {"player_id": a["id"], "region_id": "gimcheon", "building_type": "commercial"}, "build")
    state = client.get("/api/state").get_json()
    building_id = state["buildings"][0]["id"]
    post(client, "/api/dev/set-position", {"player_id": a["id"], "position": 1}, "pos")
    first = post(client, "/api/operating-right/transfer/propose", {
        "requester_id": a["id"],
        "target_id": b["id"],
        "building_id": building_id,
        "price_won": 1000,
    }, "offer")
    second = post(client, "/api/operating-right/transfer/propose", {
        "requester_id": a["id"],
        "target_id": b["id"],
        "building_id": building_id,
        "price_won": 999999,
    }, "offer")
    assert first.status_code == 200
    assert second.status_code == 409
    assert "different payload" in second.get_json()["error"]


def test_event_trigger_and_report_routes(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({"TESTING": True, "APP_MODE": "development"})
    client = app.test_client()
    authenticate(client)
    post(client, "/api/config", {"total_slots": 2, "slot_types": ["human", "bot"], "bot_strategies": ["balanced", "balanced"]}, "cfg")
    player = post(client, "/api/join", {"nickname": "A"}, "join").get_json()
    post(client, "/api/start", key="start")
    response = post(client, "/api/event/trigger", {"event_id": "personal_bonus_01", "player_id": player["id"], "region_id": "gimcheon"}, "event")
    assert response.status_code == 200
    report = client.get(f"/api/report/{player['id']}", headers={"X-Player-Id": player["id"]})
    assert report.status_code == 200
    assert "major_events" in report.get_json()


def test_bankruptcy_revival_debug_routes(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({"TESTING": True, "APP_MODE": "development"})
    client = app.test_client()
    authenticate(client)
    post(client, "/api/config", {
        "total_slots": 3,
        "slot_types": ["human", "human", "human"],
        "bot_strategies": ["balanced", "balanced", "balanced"],
        "total_rounds": 120,
    }, "cfg")
    a = post(client, "/api/join", {"nickname": "A"}, "join-a").get_json()
    b = post(client, "/api/join", {"nickname": "B"}, "join-b").get_json()
    post(client, "/api/join", {"nickname": "C"}, "join-c")
    post(client, "/api/start", key="start")
    post(client, "/api/dev/create-land", {"player_id": a["id"], "region_id": "gimcheon"}, "land")
    post(client, "/api/dev/create-building", {"player_id": a["id"], "region_id": "gimcheon", "building_type": "commercial"}, "build")
    state = client.get("/api/state").get_json()
    building_id = state["buildings"][0]["id"]
    assert post(client, "/api/dev/create-chain", {"building_id": building_id, "chain": [a["id"], b["id"]]}, "chain").status_code == 200
    assert post(client, "/api/dev/set-takeover-decision", {"player_id": b["id"], "accept": True}, "decision").status_code == 200
    bankrupt = post(client, "/api/dev/force-bankruptcy", {"player_id": a["id"], "reason": "forced"}, "bankrupt")
    assert bankrupt.status_code == 200
    assert bankrupt.get_json()["land_ownership"]["gimcheon"] == b["id"]
    assert post(client, "/api/dev/set-no-action-count", {"player_id": b["id"], "count": 1}, "noaction").status_code == 200
    assert post(client, "/api/dev/skip-revival-wait", {"player_id": a["id"], "rounds": 20}, "skip").status_code == 200
    revive = post(client, "/api/dev/revive", {"player_id": a["id"]}, "revive")
    assert revive.status_code == 200
    revived = next(player for player in revive.get_json()["players"] if player["id"] == a["id"])
    assert revived["status"] == "active"


def test_player_purchase_and_build_routes_use_server_state(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({"TESTING": True, "APP_MODE": "development"})
    client = app.test_client()
    authenticate(client)
    post(client, "/api/config", {
        "total_slots": 2,
        "slot_types": ["human", "bot"],
        "bot_strategies": ["balanced", "balanced"],
        "total_rounds": 10,
        "turn_limit_seconds": 30,
        "bot_action_delay": 1,
        "fast_simulation": False,
    }, "cfg")
    player = post(client, "/api/join", {"nickname": "Alice"}, "join").get_json()
    post(client, "/api/start", key="start")
    post(client, "/api/dev/force-dice", {"dice": 1}, "dice")
    roll = post(client, "/api/roll", {"player_id": player["id"]}, "roll").get_json()
    assert roll["position"] == 1
    post(client, "/api/turn-step/presentation-complete", {"player_id": player["id"]}, "arrival-complete")
    bought = post(client, "/api/purchase-land", {"player_id": player["id"]}, "buy").get_json()
    assert bought["land_ownership"]["gimcheon"] == player["id"]


def test_public_private_host_security_and_exports(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({"TESTING": True, "APP_MODE": "development"})
    client = app.test_client()
    authenticate(client)
    post(client, "/api/config", {"total_slots": 2, "slot_types": ["human", "bot"], "bot_strategies": ["balanced", "balanced"], "total_rounds": 10}, "cfg")
    player = post(client, "/api/join", {"nickname": "A"}, "join").get_json()
    post(client, "/api/start", key="start")
    post(client, "/api/dev/create-loan", {"player_id": player["id"], "principal_won": 1000000}, "loan")
    public_state = client.get("/api/state").get_json()
    assert "ledgers" not in public_state
    assert "loans" not in public_state
    assert all("cash_won" not in player for player in public_state["players"])
    assert "public_wealth" in public_state
    blocked = client.get(f"/api/player/{player['id']}/private", headers={"X-Player-Id": "other"})
    assert blocked.status_code == 403
    private = client.get(f"/api/player/{player['id']}/private", headers={"X-Player-Id": player["id"]})
    assert private.status_code == 200
    assert "loan" in private.get_json()
    host_state = client.get("/api/host/state")
    assert "loans" not in host_state.get_json()
    assert "game_log" in host_state.get_json()
    assert "game_log" not in public_state
    assert "loans" in client.get("/api/dev/state").get_json()
    csv_response = client.get("/api/export/csv")
    assert csv_response.status_code == 200
    assert b"player_id,nickname,status,total_asset_won,rank" in csv_response.data


def test_ended_game_blocks_mutating_routes(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({"TESTING": True, "APP_MODE": "development"})
    client = app.test_client()
    authenticate(client)
    post(client, "/api/config", {"total_slots": 2, "slot_types": ["human", "human"], "total_rounds": 10}, "cfg")
    player = post(client, "/api/join", {"nickname": "A"}, "join-a").get_json()
    other = post(client, "/api/join", {"nickname": "B"}, "join-b").get_json()
    post(client, "/api/start", key="start")
    post(client, "/api/dev/force-bankruptcy", {"player_id": other["id"]}, "bankrupt")
    state = client.get("/api/state").get_json()
    assert state["ended"] is True
    response = post(client, "/api/roll", {"player_id": player["id"]}, "roll-after-end")
    assert response.status_code == 409
    assert "current phase" in response.get_json()["error"]


def test_host_can_end_hosting_during_play_and_after_game_end(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({"TESTING": True, "APP_MODE": "development"})
    client = app.test_client()
    authenticate(client)
    post(client, "/api/config", {"total_slots": 2, "slot_types": ["human", "bot"], "bot_strategies": ["balanced", "balanced"]}, "cfg")
    post(client, "/api/join", {"nickname": "A"}, "join")
    post(client, "/api/start", key="start")
    active_end = post(client, "/api/host/end", key="end-active")
    assert active_end.status_code == 200
    state = active_end.get_json()
    assert state["phase"] == "setup"
    assert state["players"] == []
    assert state["ended"] is False
    assert state["public_wealth"]["players"] == []

    post(client, "/api/config", {"total_slots": 2, "slot_types": ["human", "human"]}, "cfg2")
    post(client, "/api/join", {"nickname": "B"}, "join-b")
    second = post(client, "/api/join", {"nickname": "C"}, "join-c").get_json()
    post(client, "/api/start", key="start2")
    post(client, "/api/dev/force-bankruptcy", {"player_id": second["id"]}, "bankrupt")
    assert client.get("/api/state").get_json()["ended"] is True
    ended_end = post(client, "/api/host/end", key="end-ended")
    assert ended_end.status_code == 200
    assert ended_end.get_json()["phase"] == "setup"
