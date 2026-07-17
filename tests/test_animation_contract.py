from pathlib import Path

import pytest

from game.engine import GameEngine


ROOT = Path(__file__).parents[1]


def started_engine():
    engine = GameEngine(ROOT / "data")
    engine.configure({
        "total_slots": 2,
        "slot_types": ["human", "human"],
        "bot_strategies": ["balanced", "balanced"],
        "total_rounds": 30,
        "turn_limit_seconds": None,
        "bot_action_delay": 0,
        "fast_simulation": False,
    })
    a = engine.join("A")
    b = engine.join("B")
    engine.start_game()
    return engine, a, b


@pytest.mark.parametrize("dice", [1, 6])
def test_roll_animation_contract_uses_server_result_and_path(dice):
    engine, player, _ = started_engine()
    engine.set_forced_dice(dice)
    result = engine.roll_dice(player["id"])

    assert result["action"] == "dice_roll"
    assert result["action_id"].startswith("roll_")
    assert result["dice"] == dice
    assert result["from_position"] == 0
    assert result["to_position"] == dice
    assert result["movement_path"] == list(range(1, dice + 1))
    assert result["arrival_type"] == engine.data["board"][dice]["type"]
    assert engine.client_public_state()["last_roll"] == result


def test_roll_path_stops_at_start_and_discards_remaining_dice_steps():
    engine, player, _ = started_engine()
    engine.set_player_position(player["id"], 38)
    engine.set_forced_dice(5)
    result = engine.roll_dice(player["id"])

    assert result["to_position"] == 0
    assert result["movement_path"] == [39, 0]
    assert result["passed_start"] is True
    assert result["stopped_at_start"] is True


def test_same_event_card_creates_distinct_ordered_occurrences():
    engine, a, _ = started_engine()
    engine.trigger_event("personal_bonus_01", a["id"], "gimcheon")
    engine.trigger_event("personal_bonus_01", a["id"], "gimcheon")
    occurrences = engine.player_private_state(a["id"])["pending_event_occurrences"]

    assert [item["event_id"] for item in occurrences] == ["personal_bonus_01", "personal_bonus_01"]
    assert occurrences[0]["occurrence_id"] != occurrences[1]["occurrence_id"]


def test_personal_event_details_are_private_to_target_player():
    engine, a, b = started_engine()
    engine.trigger_event("personal_tax_01", a["id"], "gimcheon")

    public = engine.client_public_state()["event_history"][-1]
    assert public["scope"] == "personal"
    assert "effect_summary" not in public
    assert "effects" not in public
    assert "player_id" not in public
    assert engine.player_private_state(b["id"])["pending_event_occurrences"] == []
    target = engine.player_private_state(a["id"])["pending_event_occurrences"][0]
    assert target["title"] == "세무 점검"
    assert target["target_name"] == "A"
    assert target["effect_summary"]


@pytest.mark.parametrize(
    ("event_id", "scope", "target"),
    [("regional_boom_01", "regional", "김천"), ("nationwide_boom_01", "nationwide", "전체 플레이어")],
)
def test_shared_event_occurrences_are_visible_with_target(event_id, scope, target):
    engine, a, b = started_engine()
    engine.trigger_event(event_id, a["id"], "gimcheon")

    for player_id in (a["id"], b["id"]):
        occurrence = engine.player_private_state(player_id)["pending_event_occurrences"][0]
        assert occurrence["scope"] == scope
        assert occurrence["target_name"] == target


def test_chained_events_keep_occurrence_order_and_acknowledge_exactly_once():
    engine, a, _ = started_engine()
    engine.trigger_event("personal_chain_01", a["id"], "gimcheon")
    pending = engine.player_private_state(a["id"])["pending_event_occurrences"]
    assert [item["source"] for item in pending] == ["manual", "chain"]

    first = pending[0]
    version = len(engine.state.event_history)
    acknowledged = engine.acknowledge_events(a["id"], version, first["occurrence_id"])
    assert acknowledged["occurrence_id"] == first["occurrence_id"]
    remaining = engine.player_private_state(a["id"])["pending_event_occurrences"]
    assert [item["occurrence_id"] for item in remaining] == [pending[1]["occurrence_id"]]
    duplicate = engine.acknowledge_events(a["id"], version, first["occurrence_id"])
    assert duplicate["duplicate"] is True


def test_event_effect_exists_before_ack_and_reset_removes_old_occurrences():
    engine, a, _ = started_engine()
    engine.trigger_event("personal_industry_01", a["id"], "gimcheon")
    assert engine.state.active_events
    assert engine.player_private_state(a["id"])["pending_event_occurrences"]
    previous_game_id = engine.state.game_instance_id

    engine.reset_game()
    assert engine.state.game_instance_id != previous_game_id
    assert engine.state.event_history == []
    assert engine.state.event_acknowledged_occurrences == {}


def test_player_animation_ui_has_sequence_skip_reduced_motion_and_partial_board_contracts():
    source = (ROOT / "static/js/player.js").read_text(encoding="utf-8")
    template = (ROOT / "templates/player.html").read_text(encoding="utf-8")
    css = (ROOT / "static/css/style.css").read_text(encoding="utf-8")

    for token in (
        "class AnimationSequenceController",
        "playDiceAnimation",
        "playMovementAnimation",
        "revealEventOccurrence",
        "pendingSnapshot",
        "animationController.skip()",
        "window.requestAnimationFrame",
        "prefers-reduced-motion: reduce",
    ):
        assert token in source or token in css
    assert 'id="diceFace"' in template
    assert 'id="eventReveal"' in template
    assert 'id="skipAnimation"' in template
    assert 'id="skipEventReveal"' in template
    assert 'boardGrid.innerHTML = ""' not in source
