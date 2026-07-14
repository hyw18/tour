import argparse
import json
import random
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from game.engine import GameEngine, GameRuleError  # noqa: E402


FAIL_DIR = ROOT / "validation_failures"


def assert_game_invariants(engine):
    state = engine.state
    player_ids = [player.id for player in state.players]
    assert len(player_ids) == len(set(player_ids)), "duplicate player id"
    existing = set(player_ids)
    active = [player for player in state.players if player.status == "active"]
    assert len(active) == len({player.id for player in active}), "duplicate active player"
    current = engine.current_player()
    if state.phase == "active" and not state.ended and current:
        assert current.status == "active", "current player is not active"
    for region_id, owner_id in state.land_ownership.items():
        assert owner_id in existing, f"land owner missing: {region_id}"
        assert engine.region_by_id(region_id)["land_price"] == engine.data["building_prices"][region_id]["land"], f"land price drift: {region_id}"
    region_type_counts = {}
    building_ids = set()
    for building in state.buildings:
        assert building["id"] not in building_ids, "duplicate building id"
        building_ids.add(building["id"])
        chain = building.get("ownership_chain", [])
        assert chain, f"empty ownership chain: {building['id']}"
        assert len(chain) == len(set(chain)), f"duplicate chain member: {building['id']}"
        assert all(member in existing for member in chain), f"missing chain member: {building['id']}"
        assert chain[0] == building["nominal_owner_id"], f"nominal owner mismatch: {building['id']}"
        assert chain[-1] == building["operator_id"], f"operator mismatch: {building['id']}"
        assert state.land_ownership.get(building["region_id"]) == building["nominal_owner_id"], f"land/building owner mismatch: {building['id']}"
        if building["building_type"] in {"industrial", "mixed_use"}:
            key = (building["region_id"], building["building_type"])
            region_type_counts[key] = region_type_counts.get(key, 0) + 1
            assert region_type_counts[key] <= 1, f"too many {building['building_type']} in {building['region_id']}"
        assert isinstance(building["market_value_won"], int), "non-integer building value"
    for player in state.players:
        assert isinstance(player.cash_won, int), f"non-integer cash: {player.id}"
        loan = state.loans.get(player.id)
        if loan:
            assert loan["remaining_due_won"] >= 0, f"negative loan: {player.id}"
    refund_keys = {(item["player_id"], item["region_id"], item["refund_won"]) for item in state.pending_commercial_sale_refunds}
    assert len(refund_keys) == len(state.pending_commercial_sale_refunds), "duplicate pending refund"
    public_assets = engine.public_wealth()["players"]
    final_assets = engine._final_asset_totals()
    for row in public_assets:
        assert row["total_asset_won"] == final_assets[row["player_id"]], "public/final asset mismatch"
    for event in state.active_events:
        assert event["duration_rounds"] > 0, "event duration must be positive"
        assert event["recovery_rounds"] >= 0, "event recovery negative"


def snapshot(engine, seed, config, exc):
    FAIL_DIR.mkdir(exist_ok=True)
    path = FAIL_DIR / f"failure_seed_{seed}_{int(time.time())}.json"
    payload = {
        "seed": seed,
        "config": config,
        "error": str(exc),
        "traceback": traceback.format_exc(),
        "state": engine.host_state() if engine else None,
        "recent_log": list(engine.state.game_log[-100:]) if engine else [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def run_game(seed, players, rounds, strategies, events):
    random.seed(seed)
    engine = GameEngine("data")
    config = {
        "total_slots": players,
        "slot_types": ["bot"] * players,
        "bot_strategies": [strategies[index % len(strategies)] for index in range(players)],
        "total_rounds": rounds,
        "turn_limit_seconds": 30,
        "bot_action_delay": 0,
        "fast_simulation": True,
    }
    engine.configure(config)
    assert_game_invariants(engine)
    engine.start_game()
    assert_game_invariants(engine)
    if events == "high":
        for event in engine.data["events"][:2]:
            if engine.state.ended:
                break
            player = engine.current_player() or engine.state.players[0]
            engine.trigger_event(event["id"], player.id, engine._first_region_id(), "manual")
            assert_game_invariants(engine)
    guard = 0
    while not engine.state.ended and guard < rounds * players * 4:
        player = engine.current_player()
        if not player:
            break
        engine.take_turn_for_player(player.id, "bot" if player.is_bot else "dev")
        assert_game_invariants(engine)
        guard += 1
    assert engine.state.ended, "game did not end"
    assert guard < rounds * players * 4, "turn guard exhausted"
    result = engine.finalize_game("validation")
    assert result == engine.finalize_game("validation-repeat"), "final result not fixed"
    assert_game_invariants(engine)
    return {
        "seed": seed,
        "players": players,
        "rounds": rounds,
        "strategies": strategies,
        "events": events,
        "final_round": engine.state.global_round,
        "rankings": result["rankings"],
        "assets": result["assets"],
        "loans": sum(1 for player_id in engine.state.loans),
        "revivals": sum(engine.state.revival_counts.values()),
    }


def run_repro(seed, players, rounds, strategies, events):
    first = run_game(seed, players, rounds, strategies, events)
    second = run_game(seed, players, rounds, strategies, events)
    assert first["rankings"] == second["rankings"], "ranking reproducibility failed"
    assert first["assets"] == second["assets"], "asset reproducibility failed"
    return first


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=300)
    parser.add_argument("--repro-seeds", type=int, default=25)
    parser.add_argument("--seed-base", type=int, default=20260714)
    parser.add_argument("--output", default="validation_results.json")
    args = parser.parse_args()

    player_options = [2, 3, 4]
    round_options = [10, 30, 50, 100, 300]
    strategy_options = [
        ["balanced"],
        ["aggressive"],
        ["conservative"],
        ["random"],
        ["balanced", "aggressive", "conservative", "random"],
    ]
    event_options = ["none", "default", "high"]
    results = []
    failures = []
    start = time.perf_counter()
    for index in range(args.games):
        seed = args.seed_base + index
        players = player_options[index % len(player_options)]
        rounds = round_options[(index // len(player_options)) % len(round_options)]
        strategies = strategy_options[(index // (len(player_options) * len(round_options))) % len(strategy_options)]
        events = event_options[(index // (len(player_options) * len(round_options) * len(strategy_options))) % len(event_options)]
        try:
            results.append(run_game(seed, players, rounds, strategies, events))
        except Exception as exc:  # failure is serialized and re-raised after the batch
            engine = locals().get("engine")
            failures.append({"seed": seed, "error": str(exc), "snapshot": str(snapshot(engine, seed, {"players": players, "rounds": rounds, "strategies": strategies, "events": events}, exc))})
    repro = []
    for index in range(args.repro_seeds):
        seed = args.seed_base + 100_000 + index
        try:
            repro.append(run_repro(seed, 4, 30, ["balanced", "aggressive", "conservative", "random"], "default"))
        except Exception as exc:
            failures.append({"seed": seed, "error": str(exc), "snapshot": str(snapshot(locals().get("engine"), seed, {"repro": True}, exc))})
    elapsed = time.perf_counter() - start
    summary = {
        "games_requested": args.games,
        "games_completed": len(results),
        "repro_requested": args.repro_seeds,
        "repro_completed": len(repro),
        "failures": failures,
        "elapsed_seconds": round(elapsed, 3),
        "average_seconds_per_game": round(elapsed / max(1, len(results)), 6),
        "strategy_wins": {},
    }
    for result in results:
        winner_id = min((rank, player_id) for player_id, rank in result["rankings"].items() if rank is not None)[1]
        summary["strategy_wins"][winner_id] = summary["strategy_wins"].get(winner_id, 0) + 1
    Path(args.output).write_text(json.dumps({"summary": summary, "results": results[:200]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
