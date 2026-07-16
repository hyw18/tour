from pathlib import Path

import pytest

from app import create_app
from game.automation import AutomationWorker
from game.engine import GameEngine


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


@pytest.mark.parametrize("key", [None, "", "   ", "bad/key", "x" * 129])
def test_idempotency_key_format_is_enforced_at_server_boundary(key):
    app = create_app({"TESTING": True})
    client = app.test_client()
    headers = {} if key is None else {"Idempotency-Key": key}
    response = client.post("/api/join", json={"nickname": "A"}, headers=headers)
    assert response.status_code == 400
    assert "Idempotency-Key" in response.get_json()["error"]


def test_post_json_reuses_one_key_for_network_retries():
    source = (ROOT / "static/js/common.js").read_text(encoding="utf-8")
    assert "const logicalKey = options.idempotencyKey || idempotencyKey()" in source
    assert '"Idempotency-Key": logicalKey' in source
    assert "for (let attempt = 0; attempt <= retryCount" in source


def test_trade_rejection_emits_status_without_economic_animation():
    engine, players = started_engine()
    seller, buyer = players
    engine.create_land_ownership(seller["id"], "gimcheon")
    engine.set_player_position(seller["id"], 1)
    engine.propose_land_trade(seller["id"], buyer["id"], "gimcheon")
    before = engine.economic_snapshot()
    engine.respond_land_trade(buyer["id"], False)

    assert engine.record_economic_action(None, buyer["id"], before) is None
    assert engine.state.domain_events[-1]["event_type"] == "land_trade_rejected"
    assert engine._find_player(seller["id"]).cash_won == 10_000_000
    assert engine._find_player(buyer["id"]).cash_won == 10_000_000


def test_event_view_uses_server_progress_and_player_ui_does_not_render_internal_id():
    engine, players = started_engine()
    engine.trigger_event("nationwide_boom_01", players[0]["id"], "gimcheon")
    event = engine.player_private_state(players[0]["id"])["active_events"][0]
    assert event["title"]
    assert event["phase"] == "growing"
    assert event["phase_progress_bps"] == 0
    assert event["rounds_remaining"] == event["duration_rounds"] + event["recovery_rounds"]
    assert event["current_effect_summary"]

    source = (ROOT / "static/js/player.js").read_text(encoding="utf-8")
    render_events = source[source.index("function renderEvents"):source.index("function renderSettlement")]
    assert "event.id" not in render_events
    assert "event.phase_progress_bps" in render_events
    assert "event.age_rounds /" not in render_events


def test_economic_cursor_prevents_first_snapshot_gap_and_reconnect_replay():
    engine, players = started_engine()
    player_id = players[0]["id"]
    token = engine.issue_reconnect_token(player_id)
    engine.set_forced_dice(1)
    engine.roll_dice(player_id)
    before = engine.economic_snapshot()
    engine.purchase_land(player_id)
    action = engine.record_economic_action(None, player_id, before)

    private = engine.player_private_state(player_id)
    assert private["animation_cursor"] < action["sequence"]
    assert [item["action_id"] for item in private["unread_economic_actions"]] == [action["action_id"]]
    engine.acknowledge_economic_actions(player_id, action["sequence"])
    assert engine.player_private_state(player_id)["unread_economic_actions"] == []

    engine.reconnect_player(player_id, token, engine.state.game_instance_id)
    assert engine.player_private_state(player_id)["animation_cursor"] == engine.state.economic_sequence


def test_start_settlement_result_events_preserve_server_order():
    engine, players = started_engine()
    player_id = players[0]["id"]
    engine.set_player_position(player_id, 39)
    engine.set_forced_dice(1)
    before = engine.economic_snapshot()
    engine.roll_dice(player_id)
    event_types = [event["event_type"] for event in engine.domain_events_since(before)]
    expected = [
        "lap_income_and_loss", "taxable_income_fixed", "tax_paid", "start_bonus_received",
        "loan_repaid", "loan_decision_completed", "bankruptcy_check_completed", "final_cash_confirmed",
    ]
    positions = [event_types.index(item) for item in expected]
    assert positions == sorted(positions)


def test_irreversible_actions_use_confirmation_and_only_affected_assets_are_highlighted():
    source = (ROOT / "static/js/player.js").read_text(encoding="utf-8")
    template = (ROOT / "templates/player.html").read_text(encoding="utf-8")
    for path in (
        "/api/purchase-land", "/api/purchase-special", "/api/sell-building",
        "/api/trade/land/propose", "/api/operating-right/transfer/propose",
        "/api/usage-change/request", "/api/operating-right/recall", "/api/revive",
    ):
        assert path in source
    assert source.count("confirmedRequest(") >= 10
    assert 'id="actionConfirmModal"' in template
    assert 'aria-modal="true"' in template
    assert "trapConfirmationFocus" in source
    assert 'document.querySelectorAll(".asset-row").forEach' not in source
    assert "data-building-id" in source and "data-finance-section" in source


def test_sound_control_matches_unimplemented_sound_state_and_force_state_cancels_queue():
    source = (ROOT / "static/js/player.js").read_text(encoding="utf-8")
    template = (ROOT / "templates/player.html").read_text(encoding="utf-8")
    assert "효과음 준비 중" in template
    assert "animationMuted" not in source
    assert "state.game_instance_id !== lastState.game_instance_id" in source
    assert "privateData?.player?.status === \"bankrupt\"" in source
    assert "animationController.cancel()" in source


def test_bot_automation_emits_only_public_asset_changes_without_financial_details():
    engine = GameEngine(ROOT / "data")
    engine.configure({
        "total_slots": 2, "slot_types": ["bot", "bot"],
        "bot_strategies": ["aggressive", "balanced"], "total_rounds": 10,
        "turn_limit_seconds": None, "bot_action_delay": 0, "fast_simulation": False,
    })
    engine.start_game()
    engine.set_forced_dice(1)
    AutomationWorker(engine).tick()

    public_actions = engine.client_public_state()["public_economic_actions"]
    assert public_actions
    assert all(action["cash_changes"] == [] for action in public_actions)
    assert all(
        change["type"] in {"building_added", "building_removed", "building_updated", "land_owner_changed", "special_owner_changed"}
        for action in public_actions for change in action["asset_changes"]
    )
