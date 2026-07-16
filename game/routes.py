import json
import os
import re
from functools import wraps

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request, session

from .engine import GameRuleError, IdempotencyConflict


bp = Blueprint("game", __name__)
dev_bp = Blueprint("development", __name__)
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class PermissionDenied(GameRuleError):
    pass


class PhaseConflict(GameRuleError):
    pass


class ResourceNotFound(GameRuleError):
    pass


def engine():
    return current_app.config["GAME_ENGINE"]


def authenticator():
    return current_app.config["HOST_AUTH"]


def views():
    return current_app.config["GAME_VIEWS"]


def simulation_jobs():
    return current_app.config["SIMULATION_JOBS"]


def debug_tools_enabled():
    return os.environ.get("DEBUG_GAME_TOOLS", "").lower() == "true" and current_app.config.get("APP_MODE") == "development"


def json_error(message, status=400):
    return jsonify({"error": message}), status


def boolean_field(payload, name):
    value = payload.get(name)
    if not isinstance(value, bool):
        raise GameRuleError(f"{name} must be boolean")
    return value


def validate_idempotency_key(value):
    if not value or not IDEMPOTENCY_KEY_PATTERN.fullmatch(value):
        raise GameRuleError("Idempotency-Key must be 1..128 characters using letters, numbers, '.', '_', ':', or '-'")
    return value


def mutating_route(handler=None, *, allow_ended=False, bump_state=True, record_activity=True):
    def decorator(route_handler):
        @wraps(route_handler)
        def wrapper(*args, **kwargs):
            key = request.headers.get("Idempotency-Key")
            try:
                key = validate_idempotency_key(key)
                request_instance_id = request.headers.get("X-Game-Instance-Id")
                scope_instance_id = request_instance_id or engine().state.game_instance_id
                scoped_key = f"{scope_instance_id}:{request.path}:{key}" if key else key
                payload = request.get_json(silent=True)
                signature = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                def execute():
                    if request_instance_id and request_instance_id != engine().state.game_instance_id:
                        raise PhaseConflict("previous game instance has expired")
                    if engine().state.ended and not allow_ended:
                        raise PhaseConflict("current phase does not allow this action")
                    if isinstance(payload, dict) and payload.get("expected_state_version") is not None:
                        if payload["expected_state_version"] != engine().state.state_version:
                            raise PhaseConflict("game state changed; review the latest confirmation details")
                    before = engine().economic_snapshot()
                    pending_before = dict(engine().state.pending_action or {})
                    result = route_handler(*args, **kwargs)
                    if record_activity:
                        record_authenticated_activity(payload)
                    economic_action = None
                    actor_player_id = None
                    if isinstance(payload, dict):
                        actor_player_id = payload.get("player_id") or payload.get("requester_id") or payload.get("responder_id") or payload.get("approver_id")
                    context = {
                        "region_id": (payload or {}).get("region_id") or pending_before.get("region_id"),
                        "special_region_id": pending_before.get("special_region_id"),
                        "building_id": (payload or {}).get("building_id"),
                        "building_type": (payload or {}).get("building_type"),
                    }
                    economic_action = engine().record_economic_action(None, actor_player_id, before, {key: value for key, value in context.items() if value is not None})
                    result_events = engine().domain_events_since(before, scoped_key)
                    if bump_state:
                        engine().mark_state_changed()
                    if isinstance(result, dict):
                        result["game_instance_id"] = engine().state.game_instance_id
                        result["state_version"] = engine().state.state_version
                        if economic_action:
                            economic_action["state_version"] = engine().state.state_version
                            result["economic_action"] = economic_action
                        if result_events:
                            for event in result_events:
                                event["state_version"] = engine().state.state_version
                            result["result_events"] = result_events
                    return result

                return jsonify(engine().with_idempotency(scoped_key, execute, signature))
            except PermissionDenied as exc:
                return json_error(str(exc), 403)
            except PhaseConflict as exc:
                return json_error(str(exc), 409)
            except IdempotencyConflict as exc:
                return json_error(str(exc), 409)
            except ResourceNotFound as exc:
                return json_error(str(exc), 404)
            except GameRuleError as exc:
                return json_error(str(exc))

        return wrapper

    return decorator(handler) if handler else decorator


def record_authenticated_activity(payload):
    if not isinstance(payload, dict):
        return
    player_id = payload.get("player_id") or payload.get("requester_id") or payload.get("approver_id") or payload.get("responder_id")
    if player_id and player_id in session.get("player_ids", []):
        player = engine()._find_player(player_id)
        if player:
            engine()._record_activity(player)


@bp.errorhandler(GameRuleError)
def handle_rule_error(exc):
    if isinstance(exc, PermissionDenied):
        return json_error(str(exc), 403)
    if isinstance(exc, PhaseConflict):
        return json_error(str(exc), 409)
    return json_error(str(exc))


@bp.route("/")
@bp.route("/host")
def host_page():
    return render_template("host.html", debug_tools=debug_tools_enabled(), host_authenticated=authenticator().is_authenticated())


@bp.post("/api/host/login")
def api_host_login():
    payload = request.get_json(force=True, silent=True) or {}
    result = authenticator().login(payload.get("token"), request.remote_addr or "unknown")
    if result == "rate_limited":
        return json_error("too many host login attempts", 429)
    if result != "authenticated":
        return json_error("invalid host token", 401)
    return jsonify({"authenticated": True, "csrf_token": authenticator().csrf_token()})


@bp.post("/api/host/logout")
def api_host_logout():
    if not authenticator().is_authenticated():
        return json_error("host permission is required", 403)
    if not authenticator().valid_csrf(request):
        return json_error("invalid CSRF token", 403)
    authenticator().logout()
    return jsonify({"authenticated": False})


@bp.get("/api/host/session")
def api_host_session():
    return jsonify({
        "authenticated": authenticator().is_authenticated(),
        "csrf_token": authenticator().csrf_token(),
    })


@bp.route("/player")
def player_page():
    return render_template("player.html")


@bp.get("/api/state")
def api_state():
    return jsonify(views().public())


@bp.get("/api/host/state")
def api_host_state():
    require_host()
    return jsonify(views().host())


@bp.get("/api/player/<player_id>/private")
def api_player_private_state(player_id):
    require_player(player_id)
    return jsonify(engine().player_private_state(player_id))


@bp.get("/api/player/<player_id>/state")
def api_player_state(player_id):
    require_player(player_id)
    return jsonify(engine().run_serialized(lambda: {
        "game_instance_id": engine().state.game_instance_id,
        "state_version": engine().state.state_version,
        "public": views().public(),
        "private": engine().player_private_state(player_id),
    }))


@bp.get("/api/player/<player_id>/build-preview")
def api_build_preview(player_id):
    require_player(player_id)
    return jsonify(engine().run_serialized(lambda: engine().build_preview(
        player_id,
        request.args.get("region_id"),
        request.args.get("building_type"),
    )))


@bp.post("/api/config")
@mutating_route
def api_config():
    require_host()
    require_phase("setup", "lobby")
    return engine().configure(request.get_json(force=True, silent=True) or {})


@bp.post("/api/join")
@mutating_route
def api_join():
    payload = request.get_json(force=True, silent=True) or {}
    player = engine().join(payload.get("nickname"))
    current_ids = {item.id for item in engine().state.players}
    player_ids = [item for item in session.get("player_ids", []) if item in current_ids]
    if player["id"] not in player_ids:
        player_ids.append(player["id"])
    session["player_ids"] = player_ids
    session["player_id"] = player["id"]
    return {
        **player,
        "reconnect_token": engine().issue_reconnect_token(player["id"]),
        "game_instance_id": engine().state.game_instance_id,
    }


@bp.post("/api/player/reconnect")
@mutating_route(bump_state=False, record_activity=False, allow_ended=True)
def api_player_reconnect():
    payload = request.get_json(force=True, silent=True) or {}
    if payload.get("game_instance_id") != engine().state.game_instance_id:
        raise PhaseConflict("previous game instance has expired")
    try:
        player = engine().reconnect_player(
            payload.get("player_id"),
            payload.get("reconnect_token"),
            payload.get("game_instance_id"),
        )
    except LookupError as exc:
        raise ResourceNotFound(str(exc)) from exc
    except PermissionError as exc:
        raise PermissionDenied(str(exc)) from exc
    current_ids = {item.id for item in engine().state.players}
    player_ids = [item for item in session.get("player_ids", []) if item in current_ids]
    if player["id"] not in player_ids:
        player_ids.append(player["id"])
    session["player_ids"] = player_ids
    session["player_id"] = player["id"]
    return {**player, "game_instance_id": engine().state.game_instance_id}


@bp.post("/api/start")
@mutating_route
def api_start():
    require_host()
    require_phase("setup", "lobby")
    return engine().start_game()


@bp.post("/api/pause")
@mutating_route
def api_pause():
    require_host()
    require_phase("active")
    return engine().pause()


@bp.post("/api/resume")
@mutating_route
def api_resume():
    require_host()
    require_phase("paused")
    return engine().resume()


@bp.post("/api/host/end")
@mutating_route(allow_ended=True)
def api_host_end():
    require_host()
    return engine().close_hosting()


@bp.post("/api/host/finish")
@mutating_route
def api_host_finish():
    require_host()
    require_phase("active", "paused")
    return engine().end_game()


@bp.post("/api/host/new-game")
@mutating_route(allow_ended=True)
def api_host_new_game():
    require_host()
    require_phase("finished")
    payload = request.get_json(force=True, silent=True) or {}
    return engine().prepare_new_game(bool(payload.get("keep_config", True)))


@bp.post("/api/host/reset")
@mutating_route(allow_ended=True)
def api_host_reset():
    require_host()
    return engine().reset_game(keep_config=False)


@bp.post("/api/roll")
@mutating_route
def api_roll():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("player_id"))
    return engine().roll_dice(payload.get("player_id"))


@bp.post("/api/end-turn")
@mutating_route
def api_end_turn():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("player_id"))
    engine().end_turn(payload.get("player_id"))
    return views().public()


@bp.post("/api/purchase-land")
@mutating_route
def api_purchase_land():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("player_id"))
    engine().purchase_land(payload.get("player_id"))
    return views().public()


@bp.post("/api/decline-action")
@mutating_route
def api_decline_action():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("player_id"))
    engine().decline_pending_action(payload.get("player_id"))
    return views().public()


@bp.post("/api/build")
@mutating_route
def api_build():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("player_id"))
    engine().validate_build_confirmation(payload.get("player_id"), payload)
    engine().build_on_land(payload.get("player_id"), payload.get("building_type"))
    return views().public()


@bp.post("/api/sell-building")
@mutating_route
def api_sell_building():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("player_id"))
    engine().sell_building(payload.get("player_id"), payload.get("building_id"))
    return views().public()


@bp.post("/api/purchase-special")
@mutating_route
def api_purchase_special():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("player_id"))
    engine().purchase_special_region(payload.get("player_id"))
    return views().public()


@bp.post("/api/trade/land/propose")
@mutating_route
def api_trade_land_propose():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("requester_id"))
    engine().propose_land_trade(payload.get("requester_id"), payload.get("buyer_id"), payload.get("region_id"))
    return views().public()


@bp.post("/api/trade/land/respond")
@mutating_route
def api_trade_land_respond():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("responder_id"))
    engine().respond_land_trade(payload.get("responder_id"), boolean_field(payload, "accept"))
    return views().public()


@bp.post("/api/operating-right/transfer/propose")
@mutating_route
def api_operating_right_transfer_propose():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("requester_id"))
    engine().propose_operating_right_transfer(
        payload.get("requester_id"),
        payload.get("target_id"),
        payload.get("building_id"),
        payload.get("price_won"),
    )
    return views().public()


@bp.post("/api/operating-right/transfer/respond")
@mutating_route
def api_operating_right_transfer_respond():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("responder_id"))
    engine().respond_operating_right_transfer(payload.get("responder_id"), boolean_field(payload, "accept"))
    return views().public()


@bp.post("/api/usage-change/request")
@mutating_route
def api_usage_change_request():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("requester_id"))
    engine().request_usage_change(payload.get("requester_id"), payload.get("building_id"), payload.get("new_type"))
    return views().public()


@bp.post("/api/usage-change/respond")
@mutating_route
def api_usage_change_respond():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("approver_id"))
    engine().respond_usage_change(payload.get("approver_id"), boolean_field(payload, "approve"))
    return views().public()


@bp.post("/api/operating-right/recall")
@mutating_route
def api_operating_right_recall():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("requester_id"))
    engine().recall_operating_rights(payload.get("requester_id"), payload.get("building_id"))
    return views().public()


@bp.post("/api/revive")
@mutating_route
def api_revive():
    payload = request.get_json(force=True, silent=True) or {}
    require_player(payload.get("player_id"))
    engine().revive_player(payload.get("player_id"))
    return views().public()


@bp.post("/api/event/acknowledge")
@mutating_route
def api_event_acknowledge():
    payload = request.get_json(force=True, silent=True) or {}
    player_id = payload.get("player_id")
    require_player(player_id)
    return engine().acknowledge_events(
        player_id,
        payload.get("last_seen_event_version", payload.get("event_version")),
        payload.get("occurrence_id"),
    )


@bp.post("/api/economic/acknowledge")
@mutating_route(bump_state=False, record_activity=False, allow_ended=True)
def api_economic_acknowledge():
    payload = request.get_json(force=True, silent=True) or {}
    player_id = payload.get("player_id")
    require_player(player_id)
    return engine().acknowledge_economic_actions(player_id, payload.get("sequence"))


@bp.post("/api/event/trigger")
@mutating_route
def api_event_trigger():
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().trigger_event(
        payload.get("event_id"),
        payload.get("player_id"),
        payload.get("region_id"),
        payload.get("source", "manual"),
    )


@bp.post("/api/bankruptcy/takeover/respond")
@mutating_route
def api_bankruptcy_takeover_respond():
    payload = request.get_json(force=True, silent=True) or {}
    player_id = payload.get("player_id")
    require_player(player_id)
    return engine().respond_land_takeover(player_id, boolean_field(payload, "accept"))


@bp.get("/api/report/<player_id>")
def api_personal_report(player_id):
    require_player(player_id)
    return jsonify(engine().personal_report(player_id))


@bp.get("/api/export/<kind>")
def api_export(kind):
    require_host()
    exported = engine().export_results(kind)
    if kind == "csv":
        return Response(exported["body"], mimetype=exported["content_type"], headers={"Content-Disposition": f"attachment; filename={exported['filename']}"})
    return jsonify(exported)


@bp.post("/api/quick-game/configure")
@mutating_route
def api_quick_game_configure():
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().configure_quick_game(payload.get("preset", "custom"), payload.get("custom"), payload.get("pause_at_round"))


@bp.post("/api/quick-game/run")
@mutating_route
def api_quick_game_run():
    require_host()
    return engine().run_quick_game()


@bp.post("/api/bot-simulation")
@mutating_route(allow_ended=True)
def api_bot_simulation():
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return simulation_jobs().create(payload)


@bp.get("/api/bot-simulation/<job_id>")
def api_bot_simulation_status(job_id):
    require_host()
    return jsonify(simulation_jobs().get(job_id))


@bp.get("/api/bot-simulation/<job_id>/result")
def api_bot_simulation_result(job_id):
    require_host()
    return jsonify(simulation_jobs().get(job_id, include_results=True))


@bp.post("/api/bot-simulation/<job_id>/cancel")
@mutating_route(allow_ended=True)
def api_bot_simulation_cancel(job_id):
    require_host()
    return simulation_jobs().cancel(job_id)


@bp.get("/api/bot-simulation/<job_id>/export/<kind>")
def api_bot_simulation_export(job_id, kind):
    require_host()
    exported = simulation_jobs().export(job_id, kind)
    if kind == "csv":
        return Response(exported, mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=simulation-{job_id}.csv"})
    return jsonify(exported)


@dev_bp.post("/api/dev/run-bot-simulation")
@mutating_route
def dev_run_bot_simulation():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().run_bot_simulation(payload)


def require_debug_tools():
    if not debug_tools_enabled():
        abort(404)


def require_host():
    if not authenticator().is_authenticated():
        raise PermissionDenied("host permission is required")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not authenticator().valid_csrf(request):
        raise PermissionDenied("invalid CSRF token")


def require_phase(*allowed):
    if engine().ui_phase() not in allowed:
        raise PhaseConflict("current phase does not allow this action")


def require_player(player_id):
    claimed_player_id = request.headers.get("X-Player-Id")
    if claimed_player_id is not None and claimed_player_id != player_id:
        raise PermissionDenied("player permission is required")
    if not player_id or player_id not in session.get("player_ids", []):
        raise PermissionDenied("player permission is required")


@dev_bp.get("/api/dev/state")
def dev_state():
    require_debug_tools()
    require_host()
    return jsonify(views().debug())


@dev_bp.post("/api/dev/force-end-turn")
@mutating_route
def dev_force_end_turn():
    require_debug_tools()
    require_host()
    return engine().force_end_current_turn()


@dev_bp.post("/api/dev/set-position")
@mutating_route
def dev_set_position():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().set_player_position(payload.get("player_id"), payload.get("position"))


@dev_bp.post("/api/dev/set-cash")
@mutating_route
def dev_set_cash():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().set_player_cash(payload.get("player_id"), payload.get("cash_won"))


@dev_bp.post("/api/dev/set-industrial-rate")
@mutating_route
def dev_set_industrial_rate():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().set_industrial_return_rate(
        payload.get("rate_bps"),
        bool(payload.get("explicit_override", False)),
    )


@dev_bp.post("/api/dev/set-tax-rate")
@mutating_route
def dev_set_tax_rate():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().set_player_tax_rate(payload.get("player_id"), payload.get("tax_rate_bps"))


@dev_bp.post("/api/dev/create-loan")
@mutating_route
def dev_create_loan():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().create_loan(payload.get("player_id"), payload.get("principal_won"))


@dev_bp.post("/api/dev/settle-start")
@mutating_route
def dev_settle_start():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().settle_start_for_player(payload.get("player_id"))


@dev_bp.post("/api/dev/run-laps")
@mutating_route
def dev_run_laps():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().run_laps(payload.get("player_id"), payload.get("laps", 1))


@dev_bp.get("/api/dev/bot-summary")
def dev_bot_summary():
    require_debug_tools()
    require_host()
    return jsonify(engine().bot_economy_summary())


@dev_bp.post("/api/dev/create-land")
@mutating_route
def dev_create_land():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().create_land_ownership(payload.get("player_id"), payload.get("region_id"))


@dev_bp.post("/api/dev/create-building")
@mutating_route
def dev_create_building():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().create_building(payload.get("player_id"), payload.get("region_id"), payload.get("building_type"))


@dev_bp.post("/api/dev/sell-building")
@mutating_route
def dev_sell_building():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().sell_building(payload.get("player_id"), payload.get("building_id"))


@dev_bp.post("/api/dev/create-chain")
@mutating_route
def dev_create_chain():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().create_ownership_chain(payload.get("building_id"), payload.get("chain", []))


@dev_bp.post("/api/dev/force-approval")
@mutating_route
def dev_force_approval():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().force_approval_response(payload.get("player_id"), bool(payload.get("approve")))


@dev_bp.post("/api/dev/force-bankruptcy")
@mutating_route
def dev_force_bankruptcy():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().force_bankruptcy(payload.get("player_id"), payload.get("reason", "forced"))


@dev_bp.post("/api/dev/set-takeover-decision")
@mutating_route
def dev_set_takeover_decision():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().set_takeover_decision(payload.get("player_id"), bool(payload.get("accept")))


@dev_bp.post("/api/dev/respond-takeover")
@mutating_route
def dev_respond_takeover():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().respond_land_takeover(payload.get("player_id"), bool(payload.get("accept")))


@dev_bp.post("/api/dev/set-no-action-count")
@mutating_route
def dev_set_no_action_count():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().set_no_action_count(payload.get("player_id"), payload.get("count", 0))


@dev_bp.post("/api/dev/skip-revival-wait")
@mutating_route
def dev_skip_revival_wait():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().skip_revival_wait(payload.get("player_id"), payload.get("rounds", 20))


@dev_bp.post("/api/dev/revive")
@mutating_route
def dev_revive():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().revive_player(payload.get("player_id"))


@dev_bp.post("/api/dev/force-special-sale-dice")
@mutating_route
def dev_force_special_sale_dice():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().force_special_sale_dice(payload.get("dice"))


@dev_bp.post("/api/dev/set-special-visits")
@mutating_route
def dev_set_special_visits():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().set_special_external_visits(payload.get("special_region_id"), payload.get("visits", 0))


@dev_bp.post("/api/dev/run-bot-land-trade")
@mutating_route
def dev_run_bot_land_trade():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().run_bot_land_trade(payload.get("seller_id"), payload.get("buyer_id"), payload.get("region_id"))


@dev_bp.post("/api/dev/change-bot-strategy")
@mutating_route
def dev_change_bot_strategy():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().change_bot_strategy(payload.get("player_id"), payload.get("strategy"))


@dev_bp.post("/api/dev/run-next-turns")
@mutating_route
def dev_run_next_turns():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().run_next_turns(payload.get("turns", 1))


@dev_bp.post("/api/dev/force-dice")
@mutating_route
def dev_force_dice():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().set_forced_dice(payload.get("dice"))


@dev_bp.post("/api/dev/fast-forward-rounds")
@mutating_route
def dev_fast_forward_rounds():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().fast_forward_rounds(payload.get("rounds", 1))


@dev_bp.post("/api/dev/bot-auto")
@mutating_route
def dev_bot_auto():
    require_debug_tools()
    require_host()
    payload = request.get_json(force=True, silent=True) or {}
    return engine().set_bot_auto(payload.get("enabled", False))


@dev_bp.post("/api/dev/run-all-bot-max-speed")
@mutating_route
def dev_run_all_bot_max_speed():
    require_debug_tools()
    require_host()
    return engine().run_all_bot_max_speed()
