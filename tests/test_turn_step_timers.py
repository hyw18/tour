from concurrent.futures import ThreadPoolExecutor

import pytest

from game.engine import GameEngine


def started(*, preset="default", fast=False, total=None):
    engine = GameEngine("data")
    payload = {
        "total_slots": 2, "slot_types": ["human", "human"],
        "step_time_preset": preset, "fast_simulation": fast,
    }
    if total is not None:
        payload["turn_total_limit_seconds"] = total
    engine.configure(payload)
    first = engine.join("A")
    second = engine.join("B")
    engine.start_game()
    return engine, first, second


def arrive_at_unowned_land(engine, player_id):
    engine.set_forced_dice(1)
    engine.roll_dice(player_id)
    assert engine.state.turn_step["step_id"] == "ARRIVAL_PRESENTATION"
    assert engine.state.turn_step["deadline_at"] is None
    engine.complete_turn_presentation(player_id)
    assert engine.state.turn_step["step_id"] == "LAND_PURCHASE_DECISION"


def test_turn_starts_with_authoritative_roll_step_and_default_limits():
    engine, first, _ = started()
    step = engine.player_private_state(first["id"])["turn_step"]
    assert step["step_id"] == "ROLL_DECISION"
    assert step["duration_seconds"] == 15
    assert step["user_input_required"] is True
    assert 0 < step["remaining_seconds"] <= 15
    assert engine.turn_total_remaining_seconds() <= 120


def test_roll_resolution_stops_choice_clock_then_arrival_starts_fresh_purchase_clock():
    engine, first, _ = started()
    initial_sequence = engine.state.turn_step["step_sequence"]
    arrive_at_unowned_land(engine, first["id"])
    step = engine.state.turn_step
    assert step["step_sequence"] > initial_sequence
    assert step["duration_seconds"] == 15
    assert step["timeout_action"] == "decline_land_purchase"


def test_purchase_result_is_automatic_then_build_gets_new_twenty_second_clock():
    engine, first, _ = started()
    arrive_at_unowned_land(engine, first["id"])
    purchase_sequence = engine.state.turn_step["step_sequence"]
    engine.purchase_land(first["id"])
    assert engine.state.turn_step["step_id"] == "RESULT_CONFIRMATION"
    assert engine.state.turn_step["deadline_at"] is None
    engine.complete_turn_presentation(first["id"])
    assert engine.state.turn_step["step_id"] == "BUILD_DECISION"
    assert engine.state.turn_step["duration_seconds"] == 20
    assert engine.state.turn_step["step_sequence"] > purchase_sequence


def test_build_modal_steps_advance_once_and_reopening_does_not_reset_deadline():
    engine, first, _ = started()
    arrive_at_unowned_land(engine, first["id"])
    engine.purchase_land(first["id"])
    engine.complete_turn_presentation(first["id"])
    engine.enter_build_step(first["id"], "BUILD_TYPE_SELECTION")
    engine.enter_build_step(first["id"], "BUILD_CONFIRMATION")
    sequence = engine.state.turn_step["step_sequence"]
    deadline = engine.state.turn_step["deadline_at"]
    engine.enter_build_step(first["id"], "BUILD_CONFIRMATION")
    assert engine.state.turn_step["step_sequence"] == sequence
    assert engine.state.turn_step["deadline_at"] == deadline
    assert engine.player_private_state(first["id"])["turn_step"]["deadline_at"] == deadline


def test_refresh_does_not_create_duplicate_step_or_reset_time():
    engine, first, _ = started()
    before = engine.player_private_state(first["id"])["turn_step"]
    for _ in range(5):
        current = engine.player_private_state(first["id"])["turn_step"]
        assert current["step_sequence"] == before["step_sequence"]
        assert current["deadline_at"] == before["deadline_at"]


def test_purchase_and_build_timeouts_decline_without_automatic_construction():
    engine, first, _ = started()
    arrive_at_unowned_land(engine, first["id"])
    engine.state.turn_step["deadline_at"] = 0
    engine.advance_automation()
    assert engine.state.pending_action is None
    assert "gimcheon" not in engine.state.land_ownership
    assert engine.state.turn_step["step_id"] == "TURN_END_DECISION"

    engine.force_end_current_turn()
    engine.force_end_current_turn()
    engine.create_land_ownership(first["id"], "gimcheon")
    engine.set_player_position(first["id"], 0)
    engine.set_forced_dice(1)
    engine.roll_dice(first["id"])
    engine.complete_turn_presentation(first["id"])
    assert engine.state.turn_step["step_id"] == "MANAGEMENT_DECISION"
    engine.enter_build_step(first["id"], "BUILD_TYPE_SELECTION")
    engine.state.turn_step["deadline_at"] = 0
    engine.advance_automation()
    assert engine.state.buildings == []


def test_roll_timeout_auto_rolls_once_and_counts_only_user_timeout():
    engine, first, _ = started()
    engine.state.turn_step["deadline_at"] = 0
    engine.advance_automation()
    assert engine.state.turn_has_rolled is True
    assert engine.state.no_action_counts[first["id"]] == 1
    assert engine.state.turn_step["user_input_required"] is False


def test_absolute_turn_cap_applies_to_choice_time_and_finishes_turn():
    engine, first, second = started(total=120)
    engine.state.turn_total_input_elapsed = 120
    engine.advance_automation()
    assert engine.current_player().id == second["id"]
    assert engine.state.no_action_counts[first["id"]] == 1
    assert engine.state.last_step_timeout["automatic_action"] == "finish_turn"


def test_pause_shifts_step_deadline_and_preserves_remaining(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("game.engine.monotonic", lambda: clock[0])
    engine, first, _ = started()
    before = engine.player_private_state(first["id"])["turn_step"]["remaining_seconds"]
    clock[0] += 3
    engine.pause()
    paused = engine.player_private_state(first["id"])["turn_step"]["remaining_seconds"]
    clock[0] += 30
    engine.resume()
    resumed = engine.player_private_state(first["id"])["turn_step"]["remaining_seconds"]
    assert paused == pytest.approx(before - 3, abs=.1)
    assert resumed == pytest.approx(paused, abs=.1)


def test_fast_simulation_uses_same_steps_without_deadlines():
    engine, first, _ = started(fast=True)
    assert engine.state.turn_step["step_id"] == "ROLL_DECISION"
    assert engine.state.turn_step["deadline_at"] is None
    engine.take_turn_for_player(first["id"], source="dev")
    assert engine.state.turn_sequence == 2


def test_concurrent_timeout_is_applied_once():
    engine, first, _ = started()
    engine.state.turn_step["deadline_at"] = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda _: engine.run_serialized(engine.advance_automation), range(30)))
    timeout_logs = [item for item in engine.state.game_log if item["category"] == "turn_step" and item["message"] == "step_timeout"]
    assert len(timeout_logs) == 1
    assert engine.state.no_action_counts[first["id"]] == 1


def test_presets_and_official_response_timers_remain_independent():
    fast, _, _ = started(preset="fast")
    assert fast.state.config.turn_total_limit_seconds == 60
    assert fast._effective_step_limits()["ROLL_DECISION"] == 10
    leisurely, _, _ = started(preset="leisurely")
    assert leisurely.state.config.turn_total_limit_seconds == 180
    assert leisurely._effective_step_limits()["TRADE_CONFIGURATION"] == 40
    assert leisurely.rules["constants"]["request_timeout_seconds"] == 10


def test_reconnect_grace_is_optional_and_applied_only_once_per_step():
    engine = GameEngine("data")
    engine.configure({
        "total_slots": 2, "slot_types": ["human", "human"],
        "reconnect_grace_seconds": 5,
    })
    first = engine.join("A")
    engine.join("B")
    token = "reconnect-test-token"
    engine.state.reconnect_token_hashes[first["id"]] = engine._reconnect_token_hash(token)
    engine.start_game()
    before = engine.state.turn_step["deadline_at"]
    engine.reconnect_player(first["id"], token, engine.state.game_instance_id)
    once = engine.state.turn_step["deadline_at"]
    engine.reconnect_player(first["id"], token, engine.state.game_instance_id)
    assert once == before + 5
    assert engine.state.turn_step["deadline_at"] == once
