from pathlib import Path

import pytest

from app import create_app
from game.engine import GameEngine, GameRuleError


ROOT = Path(__file__).parents[1]


def started_engine():
    engine = GameEngine(ROOT / "data")
    engine.configure({
        "total_slots": 2,
        "slot_types": ["human", "human"],
        "bot_strategies": ["balanced", "balanced"],
        "total_rounds": 10,
        "turn_limit_seconds": None,
        "bot_action_delay": 0,
        "fast_simulation": False,
    })
    players = [engine.join("A"), engine.join("B")]
    engine.start_game()
    return engine, players


@pytest.mark.parametrize(
    ("building_type", "tax_bps", "limit", "description"),
    [
        ("residential", 0, None, "방문료와 바퀴 수익 없음"),
        ("commercial", 100, None, "방문 시 방문료"),
        ("industrial", 300, 1, "수익 또는 손실"),
        ("mixed_use", 500, 1, "바퀴 수익"),
    ],
)
def test_build_preview_is_server_authoritative_for_all_types(building_type, tax_bps, limit, description):
    engine, players = started_engine()
    player_id = players[0]["id"]
    engine.set_forced_dice(1)
    engine.roll_dice(player_id)
    engine.purchase_land(player_id)

    preview = engine.build_preview(player_id, "gimcheon", building_type)

    assert preview["building_type"] == building_type
    assert preview["price_won"] == engine.data["building_prices"]["gimcheon"][building_type]
    assert preview["cash_after_won"] == preview["current_cash_won"] - preview["price_won"]
    assert preview["tax_base_add_bps"] == tax_bps
    assert preview["limit"] == limit
    assert description in preview["income_description"]
    assert preview["edit_action_consumed_on_success"] is True


def test_build_confirmation_rejects_stale_state_price_and_wrong_type():
    engine, players = started_engine()
    player_id = players[0]["id"]
    engine.set_forced_dice(1)
    engine.roll_dice(player_id)
    engine.purchase_land(player_id)
    preview = engine.build_preview(player_id, "gimcheon", "commercial")
    payload = {
        **preview,
        "preview_price_won": preview["price_won"],
    }
    engine.validate_build_confirmation(player_id, payload)

    with pytest.raises(GameRuleError, match="다시 확인"):
        engine.validate_build_confirmation(player_id, {**payload, "state_version": preview["state_version"] + 1})
    with pytest.raises(GameRuleError, match="다시 확인"):
        engine.validate_build_confirmation(player_id, {**payload, "preview_price_won": preview["price_won"] - 1})


def test_economic_action_uses_exact_server_cash_and_assets_and_private_visibility():
    engine, players = started_engine()
    player_id = players[0]["id"]
    engine.set_forced_dice(1)
    engine.roll_dice(player_id)
    before = engine.economic_snapshot()
    engine.purchase_land(player_id)
    action = engine.record_economic_action("land_purchase", player_id, before, {"region_id": "gimcheon"})

    assert action["action_id"].startswith("econ_")
    assert action["game_instance_id"] == engine.state.game_instance_id
    assert action["cash_changes"] == [{
        "player_id": player_id,
        "amount_won": -700_000,
        "reason": "land_purchase",
        "cash_before_won": 10_000_000,
        "cash_after_won": 9_300_000,
    }]
    assert action["asset_changes"][0]["type"] == "land_owner_changed"
    assert engine.player_private_state(player_id)["economic_actions"][-1] == action
    assert engine.player_private_state(players[1]["id"])["economic_actions"] == []
    assert "economic_actions" not in engine.client_public_state()


def test_counterparty_sees_transfer_amount_but_not_other_players_balance():
    engine, players = started_engine()
    visitor_id, owner_id = players[0]["id"], players[1]["id"]
    engine.create_land_ownership(owner_id, "gimcheon")
    before = engine.economic_snapshot()
    engine._pay_land_fee(engine._find_player(visitor_id), owner_id, "gimcheon")
    engine.record_economic_action("visit_fee", visitor_id, before, {"region_id": "gimcheon"})

    for viewer_id, other_id in ((visitor_id, owner_id), (owner_id, visitor_id)):
        action = engine.player_private_state(viewer_id)["economic_actions"][-1]
        own = next(item for item in action["cash_changes"] if item["player_id"] == viewer_id)
        other = next(item for item in action["cash_changes"] if item["player_id"] == other_id)
        assert "cash_before_won" in own and "cash_after_won" in own
        assert "cash_before_won" not in other and "cash_after_won" not in other
        assert abs(own["amount_won"]) == abs(other["amount_won"]) == 50_000


def test_build_confirmation_route_executes_once_and_returns_economic_action():
    app = create_app({"TESTING": True})
    client = app.test_client()
    def post(path, body, key):
        return client.post(path, json=body, headers={"Idempotency-Key": key})

    assert post("/api/config", {
        "total_slots": 2, "slot_types": ["human", "bot"],
        "bot_strategies": ["balanced", "balanced"], "total_rounds": 10,
    }, "config").status_code == 403
    host = client.post("/api/host/login", json={"token": app.config["HOST_AUTH"].token})
    csrf = host.get_json()["csrf_token"]
    def headers(key):
        return {"Idempotency-Key": key, "X-CSRF-Token": csrf}

    client.post("/api/config", json={
        "total_slots": 2, "slot_types": ["human", "bot"],
        "bot_strategies": ["balanced", "balanced"], "total_rounds": 10,
    }, headers=headers("config-ok"))
    player = client.post("/api/join", json={"nickname": "A"}, headers=headers("join")).get_json()
    client.post("/api/start", json={}, headers=headers("start"))
    engine = app.config["GAME_ENGINE"]
    engine.set_forced_dice(1)
    client.post("/api/roll", json={"player_id": player["id"]}, headers=headers("roll"))
    purchase = client.post("/api/purchase-land", json={"player_id": player["id"]}, headers=headers("purchase"))
    assert purchase.get_json()["economic_action"]["action_type"] == "land_purchase"
    preview = client.get(f"/api/player/{player['id']}/build-preview?region_id=gimcheon&building_type=residential").get_json()
    body = {
        "player_id": player["id"], "game_instance_id": preview["game_instance_id"],
        "state_version": preview["state_version"], "region_id": preview["region_id"],
        "building_type": preview["building_type"], "preview_price_won": preview["price_won"],
    }
    first = client.post("/api/build", json=body, headers=headers("build-once"))
    repeated = client.post("/api/build", json=body, headers=headers("build-once"))

    assert first.status_code == repeated.status_code == 200
    assert first.get_json()["economic_action"] == repeated.get_json()["economic_action"]
    assert first.get_json()["economic_action"]["action_type"] == "building_purchase"
    assert len(engine.state.buildings) == 1
    assert engine._find_player(player["id"]).cash_won == 8_400_000


def test_player_ui_requires_confirmation_and_uses_one_shared_queue():
    source = (ROOT / "static/js/player.js").read_text(encoding="utf-8")
    template = (ROOT / "templates/player.html").read_text(encoding="utf-8")
    assert 'build.addEventListener("click", openBuildConfirmation)' in source
    assert 'performAction(event.currentTarget, "/api/build"' not in source
    assert "loadBuildPreview" in source
    assert "confirmBuildAction" in source
    assert "enqueueEconomicAction" in source
    assert "animateCashCounter" in source
    assert "new EconomicAnimationQueue" not in source
    assert 'id="buildConfirmModal"' in template
    assert 'id="economicStage"' in template
