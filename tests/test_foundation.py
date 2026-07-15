from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import sleep

from app import create_app
from game.engine import GameEngine
from game.simulation import SimulationJobManager
from game.automation import AutomationWorker


DATA_DIR = Path(__file__).parents[1] / "data"


def login(client):
    token = client.application.config["HOST_AUTH"].token
    result = client.post("/api/host/login", json={"token": token})
    csrf = result.get_json()["csrf_token"]
    return {"X-CSRF-Token": csrf, "Idempotency-Key": "test-key"}


def test_host_page_does_not_authenticate_and_bad_token_is_rejected():
    app = create_app({"TESTING": True, "HOST_TOKEN": "known-token"})
    client = app.test_client()
    assert client.get("/host").status_code == 200
    assert client.get("/api/host/session").get_json()["authenticated"] is False
    assert client.post("/api/host/login", json={"token": "wrong"}).status_code == 401
    assert client.get("/api/host/state").status_code == 403


def test_correct_host_token_grants_state_and_logout_revokes_it():
    app = create_app({"TESTING": True, "HOST_TOKEN": "known-token"})
    client = app.test_client()
    result = client.post("/api/host/login", json={"token": "known-token"})
    assert result.status_code == 200
    with client.session_transaction() as session:
        assert session["is_host"] is True
    assert client.get("/api/host/state").status_code == 200
    csrf = result.get_json()["csrf_token"]
    assert client.post("/api/host/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/host/state").status_code == 403


def test_host_login_attempts_are_rate_limited():
    app = create_app({"TESTING": True, "HOST_TOKEN": "known-token"})
    client = app.test_client()
    for _ in range(5):
        assert client.post("/api/host/login", json={"token": "wrong"}).status_code == 401
    assert client.post("/api/host/login", json={"token": "wrong"}).status_code == 429


def test_host_client_does_not_poll_state_before_authentication_or_mix_origins():
    source = (Path(__file__).parents[1] / "static" / "js" / "host.js").read_text()
    assert 'fetch("/api/host/state")' in source
    assert "http://localhost" not in source
    assert "http://127.0.0.1" not in source
    assert "setInterval(() => refresh" not in source
    assert "if (!authenticated) return" in source


def test_startup_prints_host_token_banner(monkeypatch, capsys):
    monkeypatch.setenv("HOST_TOKEN", "example-secure-token")
    create_app({"DISABLE_AUTOMATION": True})
    output = capsys.readouterr().err
    assert "========================================" in output
    assert "HOST TOKEN: example-secure-token" in output
    assert "HOST URL: http://127.0.0.1:5000/host" in output


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("APP_SECRET_KEY", raising=False)
    try:
        create_app({"APP_MODE": "production", "DISABLE_AUTOMATION": True})
    except RuntimeError as exc:
        assert "SECRET_KEY" in str(exc)
    else:
        raise AssertionError("production app accepted a missing SECRET_KEY")


def test_session_cookie_security_defaults():
    app = create_app({"TESTING": True})
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["SESSION_COOKIE_SECURE"] is False


def test_all_templates_render_and_dynamic_routes_are_registered():
    app = create_app({"TESTING": True})
    client = app.test_client()
    assert client.get("/host").status_code == 200
    assert client.get("/player").status_code == 200
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/player/<player_id>/private" in rules
    assert "/api/report/<player_id>" in rules
    assert "/api/export/<kind>" in rules


def test_get_state_endpoints_do_not_mutate_game_state():
    app = create_app({"TESTING": True, "HOST_TOKEN": "known-token"})
    client = app.test_client()
    login(client)
    engine = app.config["GAME_ENGINE"]
    before = repr(engine.state)
    assert client.get("/api/state").status_code == 200
    assert client.get("/api/host/state").status_code == 200
    assert repr(engine.state) == before


def test_host_csrf_logout_and_production_debug_404(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({"TESTING": True, "APP_MODE": "production", "HOST_TOKEN": "known-token"})
    client = app.test_client()
    headers = login(client)
    assert client.post("/api/config", json={"total_slots": 2}, headers={"Idempotency-Key": "missing-csrf"}).status_code == 403
    assert client.post("/api/dev/force-dice", json={"dice": 2}, headers=headers).status_code == 404
    assert not any(rule.rule.startswith("/api/dev/") for rule in app.url_map.iter_rules())
    assert client.post("/api/host/logout", headers=headers).status_code == 200
    assert client.get("/api/host/session").get_json()["authenticated"] is False


def test_idempotency_check_and_mutation_are_one_critical_section():
    engine = GameEngine(DATA_DIR)
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        sleep(0.005)
        return {"calls": calls}

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: engine.with_idempotency("same", operation), range(100)))
    assert calls == 1
    assert results == [{"calls": 1}] * 100


def test_idempotency_store_is_bounded():
    engine = GameEngine(DATA_DIR)
    for index in range(engine.MAX_PROCESSED_KEYS + 10):
        engine.with_idempotency(str(index), lambda index=index: {"index": index})
    assert len(engine.state.processed_keys) == engine.MAX_PROCESSED_KEYS


def test_new_game_keeps_or_resets_config_and_is_idempotent():
    engine = GameEngine(DATA_DIR)
    engine.configure({"total_slots": 4, "slot_types": ["bot"] * 4})
    engine.prepare_new_game(keep_config=True)
    assert engine.state.config.total_slots == 4
    assert engine.state.players == []
    assert engine.state.global_round == 1
    engine.reset_game()
    engine.reset_game()
    assert engine.state.config.total_slots == 2
    assert engine.state.players == []


def test_simulation_job_progress_result_and_isolation():
    real_engine = GameEngine(DATA_DIR)
    before = real_engine.client_public_state()
    manager = SimulationJobManager(DATA_DIR, max_jobs=1, max_runs=3)
    job = manager.create({"players": 2, "runs": 2, "total_rounds": 10, "seed": 3})
    for _ in range(200):
        status = manager.get(job["id"], include_results=True)
        if status["status"] in {"completed", "failed"}:
            break
        sleep(0.01)
    assert status["status"] == "completed"
    assert status["completed_runs"] == 2
    assert len(status["results"]) == 2
    assert real_engine.client_public_state() == before


def test_simulation_job_can_be_cancelled():
    manager = SimulationJobManager(DATA_DIR, max_jobs=1, max_runs=100)
    job = manager.create({"players": 4, "runs": 100, "total_rounds": 100, "seed": 9})
    manager.cancel(job["id"])
    for _ in range(200):
        status = manager.get(job["id"])
        if status["status"] == "cancelled":
            break
        sleep(0.01)
    assert status["status"] == "cancelled"
    assert status["completed_runs"] < status["total_runs"]


def test_automation_advances_bot_without_state_reads_and_pause_stops_it():
    engine = GameEngine(DATA_DIR)
    engine.configure({
        "total_slots": 2,
        "slot_types": ["bot", "bot"],
        "bot_strategies": ["balanced", "aggressive"],
        "total_rounds": 10,
        "bot_action_delay": 0,
    })
    engine.start_game()
    worker = AutomationWorker(engine)
    first_player = engine.current_player().id
    worker.tick()
    assert engine.state.last_activity_player_id != first_player or engine.state.global_round > 1
    engine.pause()
    snapshot = (engine.state.global_round, engine.state.current_turn_index)
    worker.tick()
    assert (engine.state.global_round, engine.state.current_turn_index) == snapshot


def test_phase_transitions_unlock_configuration_for_a_second_game():
    app = create_app({"TESTING": True, "HOST_TOKEN": "known-token"})
    client = app.test_client()
    headers = login(client)

    def post_host(path, body=None, key="key"):
        return client.post(path, json=body or {}, headers={**headers, "Idempotency-Key": key})

    first_config = {
        "total_slots": 2,
        "slot_types": ["bot", "bot"],
        "bot_strategies": ["balanced", "balanced"],
        "total_rounds": 10,
    }
    assert post_host("/api/config", first_config, "config-1").status_code == 200
    assert post_host("/api/start", key="start-1").status_code == 200
    assert post_host("/api/config", first_config, "active-config").status_code == 409
    assert post_host("/api/pause", key="pause-1").get_json()["phase"] == "paused"
    assert post_host("/api/config", first_config, "paused-config").status_code == 409
    assert post_host("/api/resume", key="resume-1").get_json()["phase"] == "active"
    assert post_host("/api/host/finish", key="finish-1").status_code == 200
    assert client.get("/api/host/state").get_json()["phase"] == "finished"
    assert post_host("/api/config", first_config, "finished-config").status_code == 409
    assert post_host("/api/host/new-game", {"keep_config": True}, "new-1").get_json()["phase"] == "setup"

    second_config = {
        "total_slots": 4,
        "slot_types": ["bot"] * 4,
        "bot_strategies": ["aggressive", "balanced", "conservative", "random"],
        "total_rounds": 50,
    }
    saved = post_host("/api/config", second_config, "config-2").get_json()
    assert saved["config"]["total_slots"] == 4
    assert saved["config"]["total_rounds"] == 50
    assert post_host("/api/start", key="start-2").get_json()["phase"] == "active"


def test_reset_restores_defaults_and_duplicate_transition_keys_reuse_result():
    app = create_app({"TESTING": True, "HOST_TOKEN": "known-token"})
    client = app.test_client()
    headers = login(client)

    def post_host(path, body=None, key="same"):
        return client.post(path, json=body or {}, headers={**headers, "Idempotency-Key": key})

    config = {"total_slots": 2, "slot_types": ["bot", "bot"], "total_rounds": 10}
    post_host("/api/config", config, "config")
    first_start = post_host("/api/start", key="start-once").get_json()
    second_start = post_host("/api/start", key="start-once").get_json()
    assert first_start == second_start
    first_finish = post_host("/api/host/finish", key="finish-once").get_json()
    second_finish = post_host("/api/host/finish", key="finish-once").get_json()
    assert first_finish == second_finish
    first_reset = post_host("/api/host/reset", key="reset-once").get_json()
    second_reset = post_host("/api/host/reset", key="reset-once").get_json()
    assert first_reset == second_reset
    assert first_reset["phase"] == "setup"
    assert first_reset["config"]["total_slots"] == 2
    assert first_reset["config"]["total_rounds"] == 10


def test_twenty_game_lifecycle_repetitions_remain_configurable():
    engine = GameEngine(DATA_DIR)
    for index in range(20):
        slots = 2 + (index % 3)
        engine.configure({"total_slots": slots, "slot_types": ["bot"] * slots, "total_rounds": 10})
        engine.start_game()
        engine.end_game()
        assert engine.ui_phase() == "finished"
        engine.prepare_new_game(keep_config=True)
        assert engine.ui_phase() == "setup"
        assert engine.state.players == []


def test_host_frontend_uses_one_phase_control_reducer_and_preserves_slot_values():
    source = (Path(__file__).parents[1] / "static" / "js" / "host.js").read_text()
    assert "function updateControlsForPhase(state)" in source
    assert 'const editable = ["setup", "lobby"].includes(phase)' in source
    assert 'phase !== "finished"' in source
    assert "const currentTypes" in source
    assert 'if (configDirty) { showError("설정을 먼저 적용하세요")' in source
    assert 'document.querySelector("#hostConfigPanel").addEventListener' in source
    assert 'document.querySelector("#saveConfig").disabled = !editable;' in source
    assert 'addEventListener("change", handleConfigFormChange)' in source
    assert 'if (event.target.matches("#totalSlots")) renderSlots();' in source
