from concurrent.futures import ThreadPoolExecutor

import pytest

from game.engine import GameEngine, GameRuleError


DATA_DIR = "data"


def started_engine(slot_types=None, strategies=None):
    slot_types = slot_types or ["human", "bot"]
    strategies = strategies or ["balanced"] * len(slot_types)
    engine = GameEngine(DATA_DIR)
    engine.configure({
        "total_slots": len(slot_types),
        "slot_types": slot_types,
        "bot_strategies": strategies,
        "total_rounds": 10,
        "turn_limit_seconds": 30,
        "bot_action_delay": 0,
        "fast_simulation": False,
    })
    humans = [engine.join(f"P{index}") for index, kind in enumerate(slot_types) if kind == "human"]
    engine.start_game()
    return engine, humans


def arrive_and_buy(engine, player_id, cash_won=None):
    if cash_won is not None:
        engine.set_player_cash(player_id, cash_won)
    engine.set_forced_dice(1)
    engine.roll_dice(player_id)
    land_price = engine.region_by_id("gimcheon")["land_price"]
    engine.purchase_land(player_id)
    engine.complete_turn_presentation(player_id)
    return land_price


def test_purchase_only_keeps_land_and_does_not_consume_build_edit():
    engine, players = started_engine()
    player_id = players[0]["id"]
    arrive_and_buy(engine, player_id)

    assert engine.state.land_ownership["gimcheon"] == player_id
    assert engine.state.land_purchased_this_visit is True
    assert engine.state.pending_action["type"] == "build"
    assert engine.state.successful_build_edit_this_visit is False

    engine.decline_pending_action(player_id)
    assert engine.state.buildings == []
    assert engine.state.successful_build_edit_this_visit is False


def test_purchase_then_residential_build_uses_separate_prices_and_one_edit():
    engine, players = started_engine()
    player_id = players[0]["id"]
    land_price = arrive_and_buy(engine, player_id)
    build_price = engine.data["building_prices"]["gimcheon"]["residential"]

    engine.build_on_land(player_id, "residential")

    player = engine._find_player(player_id)
    assert player.cash_won == 10_000_000 - land_price - build_price
    assert len(engine.state.buildings) == 1
    assert engine.state.buildings[0]["building_type"] == "residential"
    assert engine.state.successful_build_edit_this_visit is True
    assert engine.state.pending_action is None


def test_purchase_then_decline_build_preserves_land_and_unused_edit():
    engine, players = started_engine()
    player_id = players[0]["id"]
    arrive_and_buy(engine, player_id)
    engine.decline_pending_action(player_id)

    assert engine.state.land_ownership["gimcheon"] == player_id
    assert not engine.state.buildings
    assert engine.state.pending_action is None
    assert engine.state.successful_build_edit_this_visit is False


def test_purchase_then_second_build_is_rejected():
    engine, players = started_engine()
    player_id = players[0]["id"]
    arrive_and_buy(engine, player_id)
    engine.build_on_land(player_id, "residential")
    engine.state.pending_action = engine._build_pending_action(engine._find_player(player_id), "gimcheon", "owned_land_visit")

    with pytest.raises(GameRuleError, match="only one successful"):
        engine.build_on_land(player_id, "commercial")
    assert len(engine.state.buildings) == 1


def test_purchase_succeeds_when_remaining_cash_cannot_fund_any_build():
    engine, players = started_engine()
    player_id = players[0]["id"]
    arrive_and_buy(engine, player_id, cash_won=800_000)

    assert engine._find_player(player_id).cash_won == 100_000
    assert engine.state.pending_action["affordable_buildings"] == []
    private = engine.player_private_state(player_id)
    assert private["allowed_actions"]["build"]["allowed"] is False
    assert private["allowed_actions"]["decline_build"]["allowed"] is True
    assert engine._find_player(player_id).cash_won >= 0


@pytest.mark.parametrize("building_type", ["industrial", "mixed_use"])
def test_build_pending_excludes_existing_limited_type_but_keeps_other_types(building_type):
    engine, players = started_engine()
    player = engine._find_player(players[0]["id"])
    engine.create_building(player.id, "gimcheon", building_type)
    player.position = 1
    engine.state.pending_action = engine._build_pending_action(player, "gimcheon", "owned_land_visit")

    option = engine.state.pending_action["building_options"][building_type]
    assert option["allowed"] is False
    assert "지역당 하나" in option["reason"]
    assert "residential" in engine.state.pending_action["affordable_buildings"]


def test_private_refresh_keeps_post_purchase_build_pending_and_hides_purchase():
    engine, players = started_engine()
    player_id = players[0]["id"]
    arrive_and_buy(engine, player_id)

    first = engine.player_private_state(player_id)
    refreshed = engine.player_private_state(player_id)
    assert first["pending_action"] == refreshed["pending_action"]
    assert refreshed["pending_action"]["type"] == "build"
    assert refreshed["pending_action"]["source"] == "land_purchase"
    assert refreshed["allowed_actions"]["purchase_land"]["allowed"] is False
    assert refreshed["allowed_actions"]["decline_build"]["allowed"] is True


def test_post_purchase_management_is_blocked_and_visit_state_resets_next_turn():
    engine, players = started_engine(["human", "human"])
    player_id = players[0]["id"]
    arrive_and_buy(engine, player_id)

    with pytest.raises(GameRuleError, match="only optional building"):
        engine.propose_land_trade(player_id, players[1]["id"], "gimcheon")
    assert engine.player_private_state(player_id)["allowed_actions"]["manage"]["allowed"] is False

    engine.decline_pending_action(player_id)
    engine.end_turn(player_id)
    assert engine.state.land_purchased_this_visit is False
    assert engine.state.successful_build_edit_this_visit is False


def test_bot_buys_then_makes_followup_build_decision():
    engine, players = started_engine(["human", "bot"], ["balanced", "aggressive"])
    engine.end_turn(players[0]["id"])
    bot = engine.current_player()
    engine.set_forced_dice(1)
    state = engine.take_turn_for_player(bot.id, source="bot")
    bot_state = next(item for item in state["players"] if item["id"] == bot.id)

    assert "gimcheon" in bot_state["lands"]
    assert len(bot_state["buildings"]) == 1
    assert any("pending=build" in entry["message"] for entry in engine.state.bot_debug_log if entry["player_id"] == bot.id)


def test_one_hundred_duplicate_purchase_build_and_decline_requests_execute_once():
    engine, players = started_engine()
    player_id = players[0]["id"]
    engine.set_forced_dice(1)
    engine.roll_dice(player_id)

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda _: engine.with_idempotency("purchase-100", lambda: engine.purchase_land(player_id), "purchase"), range(100)))
    assert engine._find_player(player_id).cash_won == 9_300_000
    assert engine._find_player(player_id).lands.count("gimcheon") == 1

    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda _: engine.with_idempotency("build-100", lambda: engine.build_on_land(player_id, "residential"), "residential"), range(100)))
    assert len(engine.state.buildings) == 1
    assert engine._find_player(player_id).cash_won == 8_400_000

    engine.state.pending_action = engine._build_pending_action(engine._find_player(player_id), "gimcheon", "owned_land_visit")
    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda _: engine.with_idempotency("decline-100", lambda: engine.decline_pending_action(player_id), "decline"), range(100)))
    assert engine.state.pending_action is None
    assert len([entry for entry in engine.state.game_log if entry["message"] == "building_declined"]) == 1
