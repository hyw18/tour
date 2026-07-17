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
    assert engine.state.no_action_counts[player_id] == 2


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


def test_event_presentation_finish_is_idempotent_and_clears_pause():
    engine, player_id = configured_engine()
    engine.trigger_event(player_id=player_id, region_id="gimcheon", source="event_cell")
    occurrence_id = engine.state.event_history[-1]["occurrence_id"]
    started = engine.start_event_presentation(player_id, occurrence_id)
    assert started["exclusion_token"]
    assert engine.state.event_timer_pause

    first = engine.finish_event_presentation(player_id, occurrence_id, started["exclusion_token"], "cancelled")
    second = engine.finish_event_presentation(player_id, occurrence_id, started["exclusion_token"], "cancelled")

    assert first["event_timer_resumed"] is True
    assert second["event_timer_resumed"] is False
    assert engine.state.event_timer_pause is None


def test_event_acknowledge_with_occurrence_is_idempotent_and_advances_step():
    engine, player_id = configured_engine()
    engine.trigger_event(player_id=player_id, region_id="gimcheon", source="event_cell")
    occurrence_id = engine.state.event_history[-1]["occurrence_id"]
    event_version = len(engine.state.event_history)
    engine._set_turn_step("EVENT_CONFIRMATION", "test_event", player_id=player_id)

    first = engine.acknowledge_events(player_id, event_version, occurrence_id)
    second = engine.acknowledge_events(player_id, event_version, occurrence_id)

    assert first["acknowledged"] is True
    assert second["acknowledged"] is True
    assert second["duplicate"] is True
    assert engine.state.turn_step["step_id"] == "RESULT_CONFIRMATION"
    assert engine.state.event_timer_pause is None


def test_event_pause_watchdog_recovers_stale_and_wrong_turn_pause(monkeypatch):
    engine, player_id = configured_engine()
    engine.trigger_event(player_id=player_id, region_id="gimcheon", source="event_cell")
    occurrence_id = engine.state.event_history[-1]["occurrence_id"]
    clock = [100.0]
    monkeypatch.setattr("game.engine.monotonic", lambda: clock[0])
    engine.start_event_presentation(player_id, occurrence_id)
    engine.state.event_timer_pause["started_at"] = 80.0
    clock[0] = 101.0

    recovered = engine.recover_turn_deadlocks()

    assert recovered is True
    assert engine.state.event_timer_pause is None
    assert any(entry["message"] == "deadlock_recovered" for entry in engine.state.game_log)


def test_missing_presentation_complete_auto_advances_to_decision(monkeypatch):
    engine, player_id = configured_engine()
    engine.set_forced_dice(1)
    engine.roll_dice(player_id)
    assert engine.state.turn_step["step_id"] == "ARRIVAL_PRESENTATION"
    engine.state.turn_step["presentation_deadline_at"] = 0

    engine.advance_automation()

    assert engine.state.turn_step["step_id"] == "LAND_PURCHASE_DECISION"


def test_next_turn_clears_event_pause_and_allows_roll():
    engine, player_id = configured_engine()
    engine.state.event_timer_pause = {
        "token": "orphan",
        "player_id": player_id,
        "occurrence_id": "missing",
        "turn_id": "old",
        "step_sequence": 1,
        "reason": "event_animation",
        "started_at": 0,
        "status": "active",
    }
    engine.force_end_current_turn()
    while engine.current_player().id != player_id:
        engine.force_end_current_turn()

    private = engine.player_private_state(player_id)
    assert engine.state.event_timer_pause is None
    assert engine.state.turn_has_rolled is False
    assert engine.state.pending_action is None
    assert private["allowed_actions"]["roll"]["allowed"] is True


def test_one_human_three_bots_one_hundred_rounds_leave_no_orphan_event_pause():
    engine = GameEngine("data")
    engine.configure({
        "total_slots": 4,
        "slot_types": ["human", "bot", "bot", "bot"],
        "total_rounds": 100,
        "fast_simulation": True,
        "bot_action_delay": 0,
    })
    human = engine.join("긴급검증")
    engine.start_game()

    safety = 0
    while engine.state.phase == "active" and engine.state.global_round <= 100 and safety < 500:
        player = engine.current_player()
        assert player
        if safety % 37 == 0:
            engine.state.event_timer_pause = {
                "token": f"stale-{safety}",
                "player_id": player.id,
                "occurrence_id": "missing",
                "turn_id": (engine.state.turn_step or {}).get("turn_id"),
                "step_sequence": (engine.state.turn_step or {}).get("step_sequence"),
                "reason": "event_animation",
                "started_at": 0,
                "status": "active",
            }
        engine.advance_automation(force=True)
        if player.is_bot:
            engine.take_turn_for_player(player.id, source="bot")
        else:
            private = engine.player_private_state(human["id"])
            assert private["allowed_actions"]["roll"]["allowed"] is True
            engine.force_end_current_turn()
        assert engine.state.event_timer_pause is None
        safety += 1

    assert safety < 500
    assert engine.state.event_timer_pause is None


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
