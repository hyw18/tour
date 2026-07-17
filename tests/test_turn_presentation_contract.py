from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sources():
    return (
        (ROOT / "static/js/player.js").read_text(encoding="utf-8"),
        (ROOT / "templates/player.html").read_text(encoding="utf-8"),
    )


def test_turn_presentation_has_explicit_ordered_scenes_and_state_lock():
    script, _ = sources()
    for phase in (
        "ACTION_REQUEST", "DICE_REVEAL", "PIECE_MOVEMENT", "ARRIVAL_REVEAL",
        "ECONOMIC_RESULT", "EVENT_REVEAL", "RESULT_SUMMARY", "PLAYER_DECISION", "TURN_COMPLETE",
    ):
        assert f'{phase}: "{phase}"' in script
    assert "turnPresentationState" in script
    assert "presentationLocked = turnPresentationState.inputLocked" in script
    assert "await syncPresentationSnapshot(result.action_id)" in script


def test_speed_modes_and_scene_minimums_are_not_one_global_delay():
    script, template = sources()
    assert 'value="leisurely">여유롭게' in template
    assert "leisurely: 1.3" in script
    assert "fast: 0.6" in script
    assert "minimal: 0" in script
    assert "cell?.type === \"start\" ? 1200" in script
    assert "hasDecision ? 900 : 700" in script
    assert "action.action_type === \"start_settlement\" ? 4000" in script


def test_result_summary_and_development_timeline_are_exposed():
    script, template = sources()
    assert 'id="resultSummary"' in template
    assert 'id="continuePresentation"' in template
    for field in (
        "server_response_ms", "dice_animation_ms", "movement_ms",
        "arrival_hold_ms", "economic_animation_ms", "input_enabled_after_ms",
    ):
        assert field in script
    assert "window.turnPerformanceLog" in script


def test_observed_opponent_dice_animation_releases_presentation_lock():
    script, _ = sources()
    assert 'animationController.enqueue("dice", incomingRoll.action_id, async () => {' in script
    assert "await playDiceSequence(incomingRoll);" in script
    assert "finishPresentation(incomingRoll.action_id);" in script
