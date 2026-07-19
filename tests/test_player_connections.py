from pathlib import Path

from app import create_app
from game.engine import GameEngine


ROOT = Path(__file__).parents[1]


def host_headers(client):
    token = client.application.config["HOST_AUTH"].token
    response = client.post("/api/host/login", json={"token": token})
    return {"X-CSRF-Token": response.get_json()["csrf_token"]}


def post(client, path, body, key):
    return client.post(path, json=body, headers={"Idempotency-Key": key})


def test_player_page_contains_assets_management_and_request_controls():
    app = create_app({"TESTING": True})
    html = app.test_client().get("/player").get_data(as_text=True)
    for element_id in (
        "financeAssetsPanel",
        "financeTaxPanel",
        "financeLoanPanel",
        "financeHistoryPanel",
        "requestPanel",
        "managementPanel",
        "manageAction",
        "tradeAction",
        "purchaseSpecial",
        "reviveAction",
        "tradeModal",
    ):
        assert f'id="{element_id}"' in html
    assert 'id="manageAction" hidden' not in html
    assert 'id="tradeAction" hidden' not in html
    assert "규칙 결정 대기" not in html


def test_player_javascript_connects_every_existing_player_mutation_and_deduplicates_clicks():
    source = (ROOT / "static/js/player.js").read_text(encoding="utf-8")
    for endpoint in (
        "/api/roll",
        "/api/end-turn",
        "/api/purchase-land",
        "/api/purchase-special",
        "/api/build",
        "/api/sell-building",
        "/api/trade/land/propose",
        "/api/trade/land/respond",
        "/api/operating-right/transfer/propose",
        "/api/operating-right/transfer/respond",
        "/api/usage-change/request",
        "/api/usage-change/respond",
        "/api/operating-right/recall",
        "/api/revive",
        "/api/event/acknowledge",
        "/api/bankruptcy/takeover/respond",
    ):
        assert endpoint in source
    assert "hasBlockingRequestForCurrentTurn()" in source
    assert "button.disabled = clientLocked || !rule.allowed" in source
    assert "button.disabled = actionInFlight" not in source
    assert "special.initial_price_won" in source
    assert "state.special_region_details" in source
    assert "currentSpecial" not in source
    assert "privateData?.pending_action" in source
    assert "토지 구매는 건물 행동을 소비하지 않습니다." in source
    assert "토지 구매 포기" in source
    assert "이번 방문 건설하지 않기" in source
    assert "boardGrid.innerHTML = \"\"" not in source
    assert "new AbortController()" in source
    assert "scheduleRefresh" in source
    assert "/api/player/${encodeURIComponent(playerId)}/state" in source
    assert "/api/player/reconnect" in source


def test_private_state_has_server_allowed_actions_and_complete_asset_details():
    engine = GameEngine(ROOT / "data")
    engine.configure({"total_slots": 2, "slot_types": ["human", "human"]})
    owner = engine.join("Owner")
    engine.join("Other")
    engine.start_game()
    engine.create_land_ownership(owner["id"], "gimcheon")
    engine.create_building(owner["id"], "gimcheon", "commercial")
    engine.set_player_position(owner["id"], 1)
    engine._set_turn_step("MANAGEMENT_DECISION", "test_management", player_id=owner["id"])

    private = engine.player_private_state(owner["id"])
    assert private["allowed_actions"]["manage"]["allowed"] is True
    assert private["allowed_actions"]["sell_building"]["allowed"] is True
    building = private["assets"]["buildings"][0]
    assert building["region_name"] == "김천"
    assert building["nominal_owner_name"] == "Owner"
    assert building["ownership_chain_names"] == ["Owner"]
    assert building["sale_mode"] == "현재 시세 50%를 다음 출발지에서 지급"
    assert building["scheduled_refund_won"] > 0
    assert building["usage_change_options"]["residential"]["cost_won"] == 900_000
    assert building["recall_preview"]["current_chain"] == [owner["id"]]


def test_private_information_requires_joined_browser_session_and_public_is_redacted():
    app = create_app({"TESTING": True})
    host = app.test_client()
    alice_client = app.test_client()
    bob_client = app.test_client()
    headers = host_headers(host)
    host.post(
        "/api/config",
        json={"total_slots": 2, "slot_types": ["human", "human"]},
        headers={**headers, "Idempotency-Key": "config"},
    )
    alice = post(alice_client, "/api/join", {"nickname": "Alice"}, "join-a").get_json()
    bob = post(bob_client, "/api/join", {"nickname": "Bob"}, "join-b").get_json()
    host.post("/api/start", json={}, headers={**headers, "Idempotency-Key": "start"})

    own = alice_client.get(f"/api/player/{alice['id']}/private", headers={"X-Player-Id": alice["id"]})
    assert own.status_code == 200
    stolen = bob_client.get(f"/api/player/{alice['id']}/private", headers={"X-Player-Id": alice["id"]})
    assert stolen.status_code == 403
    assert bob_client.get(f"/api/player/{bob['id']}/private", headers={"X-Player-Id": bob["id"]}).status_code == 200

    public = alice_client.get("/api/state").get_json()
    assert all("cash_won" not in player for player in public["players"])
    assert "pending_commercial_sale_refunds" not in public
    assert "bankruptcy_records" not in public


def test_land_trade_is_visible_only_to_participants_and_acceptance_updates_state(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({"TESTING": True, "APP_MODE": "development"})
    host = app.test_client()
    seller_client = app.test_client()
    buyer_client = app.test_client()
    outsider_client = app.test_client()
    headers = host_headers(host)

    def host_post(path, body, key):
        return host.post(path, json=body, headers={**headers, "Idempotency-Key": key})

    host_post("/api/config", {"total_slots": 3, "slot_types": ["human", "human", "human"]}, "config")
    seller = post(seller_client, "/api/join", {"nickname": "Seller"}, "join-s").get_json()
    buyer = post(buyer_client, "/api/join", {"nickname": "Buyer"}, "join-b").get_json()
    outsider = post(outsider_client, "/api/join", {"nickname": "Outsider"}, "join-o").get_json()
    host_post("/api/start", {}, "start")
    host_post("/api/dev/create-land", {"player_id": seller["id"], "region_id": "gimcheon"}, "land")
    host_post("/api/dev/set-position", {"player_id": seller["id"], "position": 1}, "position")

    proposed = post(
        seller_client,
        "/api/trade/land/propose",
        {"requester_id": seller["id"], "buyer_id": buyer["id"], "region_id": "gimcheon"},
        "offer",
    )
    assert proposed.status_code == 200
    assert "land_trade_offer" not in seller_client.get("/api/state").get_json()

    buyer_private = buyer_client.get(f"/api/player/{buyer['id']}/private", headers={"X-Player-Id": buyer["id"]}).get_json()
    assert buyer_private["related_requests"][0]["price_won"] == 700_000
    outsider_private = outsider_client.get(f"/api/player/{outsider['id']}/private", headers={"X-Player-Id": outsider["id"]}).get_json()
    assert outsider_private["related_requests"] == []

    accepted = post(
        buyer_client,
        "/api/trade/land/respond",
        {"responder_id": buyer["id"], "accept": True},
        "accept",
    )
    assert accepted.status_code == 200
    assert accepted.get_json()["land_ownership"]["gimcheon"] == buyer["id"]


def test_special_initial_price_and_current_value_are_distinct_fields():
    engine = GameEngine(ROOT / "data")
    engine.configure({"total_slots": 2, "slot_types": ["human", "bot"]})
    player = engine.join("Owner")
    engine.start_game()
    engine.state.special_ownership["pyeongchang"] = player["id"]
    engine.set_special_external_visits("pyeongchang", 3)
    special = engine.player_private_state(player["id"])["assets"]["special_regions"][0]
    assert special["initial_price_won"] == 2_000_000
    assert special["current_value_won"] == 3_200_000
    assert special["external_visits"] == 3
    assert special["next_increase_won"] == 400_000


def test_bot_declines_stale_build_after_using_visit_edit_opportunity():
    engine = GameEngine(ROOT / "data")
    engine.configure({"total_slots": 2, "slot_types": ["bot", "bot"], "bot_action_delay": 0})
    engine.start_game()
    bot = engine.current_player()
    engine.state.pending_action = {
        "type": "build",
        "player_id": bot.id,
        "region_id": "gimcheon",
        "available_buildings": ["residential"],
    }
    engine.state.successful_build_edit_this_visit = True
    engine.bot_controller.perform_investment(bot)
    assert engine.state.pending_action is None
