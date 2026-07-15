import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path

import pytest

from game.data_loader import DataValidationError, GameDataLoader
from game.economy import round_fraction_to_50k
from game.engine import GameEngine, GameRuleError
from game.views import GameViews


DATA_DIR = Path("data")


def configure(engine, slots=("human", "bot"), rounds=120):
    engine.configure({
        "total_slots": len(slots),
        "slot_types": list(slots),
        "bot_strategies": ["balanced"] * len(slots),
        "total_rounds": rounds,
        "turn_limit_seconds": 30,
        "bot_action_delay": 0,
        "fast_simulation": False,
    })


def started_engine(slots=("human", "bot"), rounds=120):
    engine = GameEngine(DATA_DIR)
    configure(engine, slots, rounds)
    humans = [engine.join(f"P{index}") for index, kind in enumerate(slots) if kind == "human"]
    engine.start_game()
    return engine, humans


def test_pause_preserves_about_seven_seconds_after_three_seconds_and_long_pause(monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr("game.engine.monotonic", lambda: clock["now"])
    engine, players = started_engine(("human", "human"))
    seller, buyer = players
    engine.create_land_ownership(seller["id"], "gimcheon")
    engine.set_player_position(seller["id"], 1)
    engine.propose_land_trade(seller["id"], buyer["id"], "gimcheon")
    clock["now"] = 103.0
    engine.pause()
    clock["now"] = 133.0
    engine.resume()
    private = engine.player_private_state(buyer["id"])
    assert private["related_requests"][0]["remaining_seconds"] == pytest.approx(7.0, abs=0.1)
    clock["now"] = 139.9
    engine.expire_land_trade()
    assert engine.state.land_trade_offer is not None
    clock["now"] = 140.1
    engine.expire_land_trade()
    assert engine.state.land_trade_offer is None


def test_pause_adjusts_every_request_and_each_usage_approver_clock(monkeypatch):
    clock = {"now": 10.0}
    monkeypatch.setattr("game.engine.monotonic", lambda: clock["now"])
    engine, players = started_engine(("human", "human"))
    base = {"created_at": 10.0, "timeout_seconds": 10}
    engine.state.land_trade_offer = dict(base)
    engine.state.operating_right_offer = dict(base)
    engine.state.usage_change_request = {**base, "approver_started_at": {players[1]["id"]: 10.0}}
    engine.state.pending_land_takeover = dict(base)
    clock["now"] = 13.0
    engine.pause()
    clock["now"] = 43.0
    engine.resume()
    assert all(request["created_at"] == 40.0 for request in (
        engine.state.land_trade_offer,
        engine.state.operating_right_offer,
        engine.state.usage_change_request,
        engine.state.pending_land_takeover,
    ))
    assert engine.state.usage_change_request["approver_started_at"][players[1]["id"]] == 40.0


def test_loan_maturity_second_and_third_start_one_won_boundaries():
    engine, players = started_engine()
    player = engine._find_player(players[0]["id"])
    engine.create_loan(player.id, 1)
    loan = engine.state.loans[player.id]
    loan["remaining_due_won"] = 1
    engine.state.lap_numbers[player.id] = loan["due_lap"] - 1
    engine._check_loan_maturity(player)
    assert player.status == "active"
    engine.state.lap_numbers[player.id] = loan["due_lap"]
    engine._check_loan_maturity(player)
    assert player.status == "bankrupt"

    paid, paid_players = started_engine()
    paid_player = paid._find_player(paid_players[0]["id"])
    paid.create_loan(paid_player.id, 1)
    paid.state.loans[paid_player.id]["remaining_due_won"] = 0
    paid.state.lap_numbers[paid_player.id] = paid.state.loans[paid_player.id]["due_lap"]
    paid._check_loan_maturity(paid_player)
    assert paid_player.status == "active"


def test_common_income_deposit_records_once_and_reduces_loan_before_retaining_cash():
    engine, players = started_engine(("human", "human"))
    owner, visitor = (engine._find_player(item["id"]) for item in players)
    engine.create_loan(owner.id, 1_000_000)
    owner.cash_won = 0
    before_due = engine.state.loans[owner.id]["remaining_due_won"]
    engine._pay_land_fee(visitor, owner.id, "gimcheon")
    entry = engine._ledger(owner)["income_entries"][-1]
    assert entry["source"] == "land_fee"
    assert engine._ledger(owner)["income_entries"].count(entry) == 1
    assert engine.state.loans[owner.id]["remaining_due_won"] < before_due
    assert owner.cash_won == 0


def test_special_accumulated_value_is_purchase_price_and_survives_forced_sale():
    engine, players = started_engine(("human", "human"))
    owner = engine._find_player(players[0]["id"])
    engine.set_special_external_visits("pyeongchang", 2)
    assert engine.state.special_values["pyeongchang"] == 2_800_000
    engine._resolve_special_arrival(owner, "pyeongchang")
    assert engine.state.pending_action["price_won"] == 2_800_000
    before = owner.cash_won
    engine.purchase_special_region(owner.id)
    assert owner.cash_won == before - 2_800_000
    engine.force_special_sale_dice(5)
    engine._resolve_special_arrival(owner, "pyeongchang")
    assert "pyeongchang" not in engine.state.special_ownership
    assert engine.state.special_values["pyeongchang"] == 2_800_000


def test_land_trade_allows_one_external_rights_holder_and_rejects_distribution():
    engine, players = started_engine(("human", "human", "human"))
    a, b, c = players
    engine.create_land_ownership(a["id"], "gimcheon")
    engine.create_building(a["id"], "gimcheon", "commercial")
    first = engine.state.buildings[0]
    engine.create_ownership_chain(first["id"], [a["id"], b["id"]])
    engine.set_player_position(a["id"], 1)
    engine.propose_land_trade(a["id"], b["id"], "gimcheon")
    engine.respond_land_trade(b["id"], True)
    assert first["ownership_chain"] == [b["id"]]
    assert first["nominal_owner_id"] == engine.state.land_ownership["gimcheon"] == b["id"]

    engine.create_land_ownership(a["id"], "jinju")
    engine.create_building(a["id"], "jinju", "commercial")
    engine.create_building(a["id"], "jinju", "residential")
    buildings = [item for item in engine.state.buildings if item["region_id"] == "jinju"]
    engine.create_ownership_chain(buildings[0]["id"], [a["id"], b["id"]])
    engine.create_ownership_chain(buildings[1]["id"], [a["id"], c["id"]])
    engine.state.current_turn_index = 0
    jinju_index = next(cell["index"] for cell in engine.data["board"] if cell.get("region_id") == "jinju")
    engine.set_player_position(a["id"], jinju_index)
    with pytest.raises(GameRuleError, match="split"):
        engine.propose_land_trade(a["id"], b["id"], "jinju")


def test_multiple_bankrupt_land_takeovers_are_queued_without_overwriting():
    engine, players = started_engine(("human", "human", "human"))
    owner, candidate, _ = players
    for region_id in ("gimcheon", "jinju"):
        engine.create_land_ownership(owner["id"], region_id)
        engine.create_building(owner["id"], region_id, "commercial")
        building = next(item for item in engine.state.buildings if item["region_id"] == region_id)
        engine.create_ownership_chain(building["id"], [owner["id"], candidate["id"]])
    engine.force_bankruptcy(owner["id"], "test")
    first_region = engine.state.pending_land_takeover["region_id"]
    assert len(engine.state.pending_land_takeover_queue) == 1
    engine.respond_land_takeover(candidate["id"], True)
    assert engine.state.pending_land_takeover is not None
    assert engine.state.pending_land_takeover["region_id"] != first_region


def test_three_event_composition_rounds_once_and_override_disappears():
    engine, players = started_engine()
    player = engine._find_player(players[0]["id"])
    engine.create_building(player.id, "gimcheon", "commercial")
    building = engine.state.buildings[0]
    building["market_value_won"] = 71_668
    engine.state.active_events = [
        {"id": f"e{index}", "scope": "nationwide", "effects": [{"target": "building_market_value", "operation": "multiply", "value_bps": value}], "age_rounds": 1, "duration_rounds": 1, "recovery_rounds": 0}
        for index, value in enumerate((15_000, 8_000, 11_000))
    ]
    exact = Fraction(71_668) * Fraction(15, 10) * Fraction(8, 10) * Fraction(11, 10)
    assert engine.adjusted_building_value(building) == round_fraction_to_50k(exact.numerator, exact.denominator)
    assert round_fraction_to_50k(25_000) == 50_000
    assert round_fraction_to_50k(-25_000) == -50_000

    engine.trigger_event("nationwide_extreme_01", player.id, "gimcheon", "manual")
    extreme = engine.state.active_events[-1]
    extreme["age_rounds"] = extreme["duration_rounds"]
    assert engine._adjusted_industrial_rate_bps(player, "gimcheon") < 0
    engine.state.active_events = []
    assert 0 <= engine._adjusted_industrial_rate_bps(player, "gimcheon") <= 2400


def test_start_settlement_is_once_only_under_one_hundred_concurrent_calls():
    engine, players = started_engine()
    player_id = players[0]["id"]
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: engine.settle_start_for_player(player_id), range(100)))
    assert results == [results[0]] * 100
    assert engine.state.lap_numbers[player_id] == 1
    assert engine._find_player(player_id).cash_won == 13_000_000
    assert engine._ledger(engine._find_player(player_id))["start_bonus"] == 3_000_000


@pytest.mark.parametrize("mutation, message", [
    ("unknown_region", "unknown region"),
    ("unknown_industry", "unknown industry"),
    ("unknown_chain", "unknown chained event"),
    ("self_cycle", "cannot chain to itself"),
    ("long_cycle", "cycle detected"),
])
def test_event_semantic_reference_and_cycle_validation(tmp_path, mutation, message):
    copied = tmp_path / "data"
    shutil.copytree(DATA_DIR, copied)
    path = copied / "events.json"
    events = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "unknown_region":
        events[0]["region_id"] = "missing"
    elif mutation == "unknown_industry":
        events[0]["industry_id"] = "missing"
    elif mutation == "unknown_chain":
        events[0]["chained_event_pool"] = ["missing"]
    elif mutation == "self_cycle":
        events[0]["chained_event_pool"] = [events[0]["id"]]
    else:
        events[0]["chained_event_pool"] = [events[1]["id"]]
        events[1]["chained_event_pool"] = [events[2]["id"]]
        events[2]["chained_event_pool"] = [events[0]["id"]]
    path.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(DataValidationError, match=message):
        GameDataLoader(copied).load()


def test_ranking_tie_uses_logged_server_dice_and_host_view_has_log_without_finances(monkeypatch):
    class TieThenResolveRandom:
        def __init__(self, seed):
            self.values = iter((3, 3, 6, 2))

        def randint(self, low, high):
            return next(self.values)

    monkeypatch.setattr("game.engine.Random", TieThenResolveRandom)
    engine, _ = started_engine(("human", "human"))
    result = engine.finalize_game("tie-test")
    assert sorted(rank for rank in result["rankings"].values() if rank is not None) == [1, 2]
    dice_logs = [item for item in engine.state.game_log if item["message"] == "tie_break_dice"]
    assert len(dice_logs) == 2
    assert all("seed" in item["details"] and all(1 <= roll <= 6 for roll in item["details"]["rolls"].values()) for item in dice_logs)
    public = GameViews(engine).public()
    host = GameViews(engine).host()
    assert "game_log" not in public
    assert host["game_log"] == engine.state.game_log
    assert all("cash_won" not in player for player in host["players"])
    assert "loans" not in host


def test_common_player_activity_resets_inactivity_count():
    engine, players = started_engine(("human", "human"))
    player_id = players[0]["id"]
    engine.state.no_action_counts[player_id] = 2
    assert engine.record_player_activity(player_id) == {"player_id": player_id, "recorded": True}
    assert engine.state.no_action_counts[player_id] == 0
