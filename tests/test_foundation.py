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
    assert client.get("/api/host/state").status_code == 400


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
    assert client.get("/api/host/state").status_code == 400


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


def test_host_csrf_logout_and_production_debug_404(monkeypatch):
    monkeypatch.setenv("DEBUG_GAME_TOOLS", "true")
    app = create_app({"TESTING": True, "APP_MODE": "production", "HOST_TOKEN": "known-token"})
    client = app.test_client()
    headers = login(client)
    assert client.post("/api/config", json={"total_slots": 2}, headers={"Idempotency-Key": "missing-csrf"}).status_code == 400
    assert client.post("/api/dev/force-dice", json={"dice": 2}, headers=headers).status_code == 404
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
