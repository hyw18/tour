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
    assert "presentationLocked = hasBlockingPresentationForCurrentTurn()" in script
    assert "await syncPresentationSnapshot(result.action_id, { identity: rollIdentity })" in script


def test_speed_modes_and_scene_minimums_are_not_one_global_delay():
    script, template = sources()
    assert 'value="leisurely">여유롭게' in template
    assert "leisurely: 1.3" in script
    assert "fast: 0.6" in script
    assert "minimal: 0" in script
    assert "cell?.type === \"start\" ? 1200" in script
    assert "hasDecision ? 900 : 700" in script
    assert "ECONOMIC_PRESENTATION_TIME_SCALE = 3" in script
    assert "action.action_type === \"start_settlement\" ? 12000" in script


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
    assert "await playDiceSequence(incomingRoll, { identity: rollIdentity, blocking: identityMatchesCurrentTurn(rollIdentity) });" in script
    assert "finishPresentation(rollIdentity);" in script


def test_snapshot_guard_compares_turn_and_step_sequence():
    script, _ = sources()
    assert "function isStaleSnapshot(snapshot)" in script
    assert "snapshot.public.game_instance_id !== lastState.game_instance_id) return false" in script
    assert "snapshotStepSequence(snapshot) <" in script


def test_roll_button_is_not_blocked_by_global_animation_playing():
    script, _ = sources()
    assert "function hasBlockingAnimationForCurrentTurn()" in script
    assert "button.disabled = clientLocked || !rule.allowed" in script
    assert "button.disabled = actionInFlight || animationState.playing" not in script
    assert "button.disabled = actionInFlight ||" not in script
    assert "button.disabled = clientLocked || !rule.allowed" in script


def test_economic_animation_is_non_blocking_and_identity_scoped():
    script, _ = sources()
    assert "const animationTasks = new Map()" in script
    assert "function identityFromEconomicAction(action = {})" in script
    assert 'animationController.enqueue("economic", action.action_id' in script
    assert "{ identity, blocking: false, timeoutMs: 24000 }" in script
    assert "runPresentationScene(presentationPhases.ECONOMIC_RESULT" in script
    assert "{ identity, blocking: false }" in script


def test_finish_presentation_uses_turn_identity_and_roll_convergence():
    script, _ = sources()
    assert "function finishPresentation(identityOrActionId)" in script
    assert "identityMatchesCurrentTurn(identity)" in script
    assert "function clearStaleLocksForRollSnapshot(snapshot)" in script
    assert "function convergeCurrentRollDecision()" in script
    assert "DEADLOCK_RECOVERED_CLIENT" in script
