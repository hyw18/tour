import pytest

from game.engine import GameEngine, GameRuleError


def configured_engine():
    engine = GameEngine("data")
    engine.configure({"total_slots": 3, "slot_types": ["human", "bot", "bot"]})
    player = engine.join("처음사용자")
    engine.start_game()
    return engine, player["id"]


def test_private_state_supplies_next_action_and_server_priority():
    engine, player_id = configured_engine()
    private = engine.player_private_state(player_id)
    assert private["next_action_message"] == "주사위를 굴리세요."
    assert private["action_priority"]["primary"] == ["roll"]


def test_current_arrival_expenses_require_exact_arrival_identifier():
    engine, player_id = configured_engine()
    engine.state.forced_dice = 1
    first = engine.roll_dice(player_id)
    player = engine._find_player(player_id)
    engine._add_expense(player, 100_000, "land_fee", "gimcheon")
    current = engine.player_private_state(player_id)
    assert current["current_arrival"]["arrival_id"] == first["arrival_id"]
    assert current["current_arrival_expenses"][0]["amount_won"] == 100_000

    engine.state.last_roll = {
        **first,
        "action_id": "second-roll",
        "arrival_id": "second-arrival",
    }
    refreshed = engine.player_private_state(player_id)
    assert refreshed["current_arrival"]["arrival_id"] == "second-arrival"
    assert refreshed["current_arrival_expenses"] == []


def test_unacknowledged_event_does_not_count_toward_automatic_exit(monkeypatch):
    engine, player_id = configured_engine()
    player = engine._find_player(player_id)
    engine.state.no_action_counts[player_id] = 2
    engine.trigger_event(player_id=player_id, region_id="gimcheon", source="event_cell")
    engine._set_turn_step("EVENT_CONFIRMATION", "test_event", player_id=player_id)
    engine.state.turn_step["deadline_at"] = 0
    engine.advance_automation()
    assert player.status == "active"
    assert engine.state.no_action_counts[player_id] == 0


def test_event_animation_time_is_excluded_but_reading_time_runs(monkeypatch):
    engine, player_id = configured_engine()
    engine.trigger_event(player_id=player_id, region_id="gimcheon", source="event_cell")
    occurrence_id = engine.state.event_history[-1]["occurrence_id"]
    clock = [10.0]
    monkeypatch.setattr("game.engine.monotonic", lambda: clock[0])
    engine.state.turn_started_at = 0.0
    engine.start_event_presentation(player_id, occurrence_id)
    clock[0] = 12.0
    assert engine.elapsed_turn_seconds() == 10.0
    engine.finish_event_presentation_animation(player_id, occurrence_id)
    clock[0] = 15.0
    assert engine.elapsed_turn_seconds() == 13.0


def test_turn_end_rejects_required_arrival_decision():
    engine, player_id = configured_engine()
    engine.state.pending_action = {
        "type": "purchase_land", "player_id": player_id, "region_id": "gimcheon", "price_won": 700_000
    }
    assert engine.player_private_state(player_id)["allowed_actions"]["end_turn"]["allowed"] is False
    with pytest.raises(GameRuleError, match="pending arrival decision"):
        engine.end_turn(player_id)


def test_start_settlement_returns_ordered_presentation_steps():
    engine, player_id = configured_engine()
    settlement = engine.settle_start_for_player(player_id)
    assert [step["type"] for step in settlement["settlement_steps"]] == [
        "building_income", "building_loss", "taxable_income", "tax",
        "start_bonus", "loan_repayment", "new_loan", "final_cash",
    ]
    assert settlement["cash_before"] == 10_000_000
    assert settlement["cash_after"] == 13_000_000
