from concurrent.futures import ThreadPoolExecutor

from app import create_app


def post(client, path, body=None, key="key", game_instance_id=None, csrf=None):
    headers = {"Idempotency-Key": key}
    if game_instance_id:
        headers["X-Game-Instance-Id"] = game_instance_id
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return client.post(path, json=body or {}, headers=headers)


def host_login(app):
    client = app.test_client()
    response = client.post("/api/host/login", json={"token": app.config["HOST_AUTH"].token})
    return client, response.get_json()["csrf_token"]


def configure_humans(host, csrf, count, rounds=30):
    response = post(host, "/api/config", {
        "total_slots": count,
        "slot_types": ["human"] * count,
        "bot_strategies": ["balanced"] * count,
        "total_rounds": rounds,
        "turn_limit_seconds": None,
        "bot_action_delay": 0,
        "fast_simulation": False,
    }, "config", csrf=csrf)
    assert response.status_code == 200
    return response.get_json()["game_instance_id"]


def join_players(app, count, game_instance_id):
    joined = []
    for index in range(count):
        client = app.test_client()
        response = post(client, "/api/join", {"nickname": f"P{index}"}, f"join-{index}", game_instance_id)
        assert response.status_code == 200
        joined.append((client, response.get_json()))
    return joined


def test_all_mutations_require_idempotency_key_and_conflicts_are_scoped_to_game():
    app = create_app({"TESTING": True})
    host, csrf = host_login(app)
    missing = host.post("/api/config", json={"total_slots": 2}, headers={"X-CSRF-Token": csrf})
    assert missing.status_code == 400
    assert "Idempotency-Key" in missing.get_json()["error"]

    game_id = configure_humans(host, csrf, 2, 10)
    stale = post(host, "/api/config", {"total_slots": 2}, "stale", "not-current", csrf)
    assert stale.status_code == 409
    assert game_id == app.config["GAME_ENGINE"].state.game_instance_id


def test_reconnect_restores_session_and_rejects_bad_deleted_and_previous_game_tokens():
    app = create_app({"TESTING": True})
    host, csrf = host_login(app)
    game_id = configure_humans(host, csrf, 2, 10)
    joined = join_players(app, 2, game_id)
    original_client, credentials = joined[0]
    engine = app.config["GAME_ENGINE"]
    engine.create_land_ownership(credentials["id"], "gimcheon")
    engine.set_player_position(credentials["id"], 1)

    fresh_client = app.test_client()
    reconnect = post(fresh_client, "/api/player/reconnect", {
        "player_id": credentials["id"],
        "reconnect_token": credentials["reconnect_token"],
        "game_instance_id": game_id,
    }, "reconnect", game_id)
    assert reconnect.status_code == 200
    restored = fresh_client.get(
        f"/api/player/{credentials['id']}/state",
        headers={"X-Player-Id": credentials["id"]},
    )
    assert restored.status_code == 200
    private_player = restored.get_json()["private"]["player"]
    assert private_player["position"] == 1
    assert private_player["lands"] == ["gimcheon"]

    bad_client = app.test_client()
    bad = post(bad_client, "/api/player/reconnect", {
        "player_id": credentials["id"], "reconnect_token": "wrong", "game_instance_id": game_id,
    }, "bad-reconnect", game_id)
    assert bad.status_code == 403

    assert post(host, "/api/host/reset", {}, "reset", game_id, csrf).status_code == 200
    stale = post(app.test_client(), "/api/player/reconnect", {
        "player_id": credentials["id"],
        "reconnect_token": credentials["reconnect_token"],
        "game_instance_id": game_id,
    }, "stale-reconnect", game_id)
    assert stale.status_code == 409
    assert original_client is not fresh_client


def test_integrated_player_state_has_one_revision_and_mutations_increment_once():
    app = create_app({"TESTING": True})
    host, csrf = host_login(app)
    game_id = configure_humans(host, csrf, 2, 10)
    joined = join_players(app, 2, game_id)
    player_client, player = joined[0]
    post(host, "/api/start", {}, "start", game_id, csrf)

    before = player_client.get(f"/api/player/{player['id']}/state", headers={"X-Player-Id": player["id"]}).get_json()
    assert before["state_version"] == before["public"]["state_version"] == before["private"]["state_version"]
    roll = post(player_client, "/api/roll", {"player_id": player["id"]}, "roll", game_id)
    assert roll.status_code == 200
    assert roll.get_json()["state_version"] == before["state_version"] + 1
    after = player_client.get(f"/api/player/{player['id']}/state", headers={"X-Player-Id": player["id"]}).get_json()
    assert after["state_version"] == after["public"]["state_version"] == after["private"]["state_version"]


def test_lobby_slot_shrink_and_human_to_bot_remove_stale_players_and_tokens():
    app = create_app({"TESTING": True})
    host, csrf = host_login(app)
    game_id = configure_humans(host, csrf, 4, 10)
    joined = join_players(app, 4, game_id)
    removed_ids = {joined[2][1]["id"], joined[3][1]["id"]}
    engine = app.config["GAME_ENGINE"]
    assert removed_ids <= set(engine.state.reconnect_token_hashes)

    shrink = post(host, "/api/config", {
        "total_slots": 2,
        "slot_types": ["human", "bot"],
        "bot_strategies": ["balanced", "balanced"],
        "total_rounds": 10,
    }, "shrink", game_id, csrf)
    assert shrink.status_code == 200
    remaining_humans = {player.id for player in engine.state.players if not player.is_bot}
    assert remaining_humans == {joined[0][1]["id"]}
    assert not removed_ids & set(engine.state.reconnect_token_hashes)
    assert joined[1][1]["id"] not in engine.state.reconnect_token_hashes


def test_invalid_spoofed_duplicate_and_empty_event_ack_do_not_record_activity():
    app = create_app({"TESTING": True})
    host, csrf = host_login(app)
    game_id = configure_humans(host, csrf, 2, 10)
    joined = join_players(app, 2, game_id)
    a_client, a = joined[0]
    b_client, b = joined[1]
    post(host, "/api/start", {}, "start", game_id, csrf)
    engine = app.config["GAME_ENGINE"]
    engine.state.no_action_counts[b["id"]] = 2

    wrong_turn = post(b_client, "/api/roll", {"player_id": b["id"]}, "wrong-turn", game_id)
    assert wrong_turn.status_code == 400
    assert engine.state.no_action_counts[b["id"]] == 2
    spoofed = post(b_client, "/api/roll", {"player_id": a["id"]}, "spoofed", game_id)
    assert spoofed.status_code == 403
    assert engine.state.no_action_counts[b["id"]] == 2

    post(host, "/api/event/trigger", {
        "event_id": "personal_bonus_01", "player_id": a["id"], "region_id": "gimcheon",
    }, "event", game_id, csrf)
    event_version = len(engine.state.event_history)
    engine.state.no_action_counts[a["id"]] = 2
    first = post(a_client, "/api/event/acknowledge", {
        "player_id": a["id"], "event_version": event_version,
    }, "ack", game_id)
    assert first.status_code == 200
    assert engine.state.no_action_counts[a["id"]] == 0
    engine.state.no_action_counts[a["id"]] = 1
    duplicate = post(a_client, "/api/event/acknowledge", {
        "player_id": a["id"], "event_version": event_version,
    }, "ack", game_id)
    assert duplicate.status_code == 200
    assert engine.state.no_action_counts[a["id"]] == 1
    empty = post(a_client, "/api/event/acknowledge", {
        "player_id": a["id"], "event_version": event_version,
    }, "ack-again", game_id)
    assert empty.status_code == 400
    assert engine.state.no_action_counts[a["id"]] == 1


def test_four_independent_clients_complete_thirty_rounds_without_server_error():
    app = create_app({"TESTING": True})
    host, csrf = host_login(app)
    game_id = configure_humans(host, csrf, 4, 30)
    joined = join_players(app, 4, game_id)
    clients = {player["id"]: client for client, player in joined}
    assert post(host, "/api/start", {}, "start", game_id, csrf).status_code == 200

    for turn in range(120):
        state = host.get("/api/host/state").get_json()
        player_id = state["current_turn_player_id"]
        client = clients[player_id]
        roll = post(client, "/api/roll", {"player_id": player_id}, f"roll-{turn}", game_id)
        assert roll.status_code == 200
        complete = post(client, "/api/turn-step/presentation-complete", {"player_id": player_id}, f"arrival-complete-{turn}", game_id)
        assert complete.status_code == 200
        private = client.get(f"/api/player/{player_id}/private").get_json()
        if private["pending_action"]:
            decline = post(client, "/api/decline-action", {"player_id": player_id}, f"decline-{turn}", game_id)
            assert decline.status_code == 200
            post(client, "/api/turn-step/presentation-complete", {"player_id": player_id}, f"decline-complete-{turn}", game_id)
        private = client.get(f"/api/player/{player_id}/private").get_json()
        if private["allowed_actions"]["end_turn"]["allowed"]:
            end = post(client, "/api/end-turn", {"player_id": player_id}, f"end-{turn}", game_id)
            assert end.status_code == 200

    final = host.get("/api/host/state").get_json()
    assert final["ended"] is True
    assert len(final["players"]) == 4


def test_three_hundred_server_turns_never_leave_current_player_roll_disabled():
    app = create_app({"TESTING": True})
    host, csrf = host_login(app)
    response = post(
        host,
        "/api/config",
        {
            "total_slots": 4,
            "slot_types": ["human", "human", "human", "human"],
            "total_rounds": 300,
            "fast_simulation": True,
            "bot_action_delay": 0,
        },
        "config-300",
        csrf=csrf,
    )
    assert response.status_code == 200
    game_id = response.get_json()["game_instance_id"]
    players = [player for _, player in join_players(app, 4, game_id)]
    assert post(host, "/api/start", {}, "start-300", game_id, csrf).status_code == 200
    engine = app.config["GAME_ENGINE"]

    blocked = []
    for turn in range(300):
        current_id = engine.current_player().id
        private = engine.player_private_state(current_id)
        roll = private["allowed_actions"]["roll"]
        if not roll["allowed"]:
            blocked.append({
                "turn": turn,
                "current_id": current_id,
                "roll": roll,
                "debug": engine.debug_turn_state(),
            })
            break
        engine.set_forced_dice((turn % 6) + 1)
        engine.roll_dice(current_id)
        engine.complete_turn_presentation(current_id)
        for _ in range(8):
            if engine.current_player().id != current_id:
                break
            current_private = engine.player_private_state(current_id)
            if engine.state.pending_action and current_private["allowed_actions"]["decline_action"]["allowed"]:
                engine.decline_pending_action(current_id)
                engine.complete_turn_presentation(current_id)
                continue
            pending_events = current_private.get("pending_event_occurrences") or []
            if pending_events:
                engine.acknowledge_events(current_id, len(engine.state.event_history), pending_events[0]["occurrence_id"])
                engine.complete_turn_presentation(current_id)
                continue
            if current_private["allowed_actions"]["end_turn"]["allowed"]:
                engine.end_turn(current_id)
                continue
            if not (engine.state.turn_step or {}).get("user_input_required"):
                engine.complete_turn_presentation(current_id)
                continue
            break

    assert blocked == []
    assert {player["id"] for player in players}


def test_one_hundred_concurrent_roll_purchase_build_and_trade_accept_execute_once():
    app = create_app({"TESTING": True})
    host, csrf = host_login(app)
    game_id = configure_humans(host, csrf, 2, 10)
    joined = join_players(app, 2, game_id)
    a_client, a = joined[0]
    b_client, b = joined[1]
    post(host, "/api/start", {}, "start", game_id, csrf)
    engine = app.config["GAME_ENGINE"]
    engine.set_forced_dice(1)

    extra_clients = []
    for index in range(20):
        client = app.test_client()
        response = post(client, "/api/player/reconnect", {
            "player_id": a["id"], "reconnect_token": a["reconnect_token"], "game_instance_id": game_id,
        }, f"reconnect-a-{index}", game_id)
        assert response.status_code == 200
        extra_clients.append(client)

    def concurrent_post(path, body, key, clients_for_requests):
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(
                lambda index: post(clients_for_requests[index % len(clients_for_requests)], path, body, key, game_id),
                range(100),
            ))
        assert {response.status_code for response in results} == {200}

    concurrent_post("/api/roll", {"player_id": a["id"]}, "roll-100", extra_clients)
    post(a_client, "/api/turn-step/presentation-complete", {"player_id": a["id"]}, "arrival-complete", game_id)
    concurrent_post("/api/purchase-land", {"player_id": a["id"]}, "purchase-100", extra_clients)
    post(a_client, "/api/turn-step/presentation-complete", {"player_id": a["id"]}, "purchase-complete", game_id)
    preview = engine.build_preview(a["id"], "gimcheon", "residential")
    concurrent_post("/api/build", {
        "player_id": a["id"],
        "game_instance_id": preview["game_instance_id"],
        "state_version": preview["state_version"],
        "region_id": preview["region_id"],
        "building_type": preview["building_type"],
        "preview_price_won": preview["price_won"],
    }, "build-100", extra_clients)
    assert engine._find_player(a["id"]).cash_won == 8_400_000
    assert len(engine.state.buildings) == 1

    post(a_client, "/api/turn-step/presentation-complete", {"player_id": a["id"]}, "build-complete", game_id)
    post(a_client, "/api/end-turn", {"player_id": a["id"]}, "end-a", game_id)
    engine.force_end_current_turn()
    engine._set_turn_step("MANAGEMENT_DECISION", "test_trade_configuration", player_id=a["id"])
    offer = post(a_client, "/api/trade/land/propose", {
        "requester_id": a["id"], "buyer_id": b["id"], "region_id": "gimcheon",
    }, "offer", game_id)
    assert offer.status_code == 200

    buyer_clients = []
    for index in range(20):
        client = app.test_client()
        response = post(client, "/api/player/reconnect", {
            "player_id": b["id"], "reconnect_token": b["reconnect_token"], "game_instance_id": game_id,
        }, f"reconnect-b-{index}", game_id)
        assert response.status_code == 200
        buyer_clients.append(client)
    concurrent_post("/api/trade/land/respond", {"responder_id": b["id"], "accept": True}, "accept-100", buyer_clients)
    assert engine.state.land_ownership["gimcheon"] == b["id"]
