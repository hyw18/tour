import pytest

from game.data_loader import DataValidationError, GameDataLoader
from game.economy import apply_rate, round_to_50k
from game.engine import GameEngine, GameRuleError


DATA_DIR = "data"


def configure(engine, **overrides):
    payload = {
        "total_slots": 2,
        "slot_types": ["human", "bot"],
        "bot_strategies": ["balanced", "balanced"],
        "total_rounds": 10,
        "turn_limit_seconds": 30,
        "bot_action_delay": 1,
        "fast_simulation": False,
    }
    payload.update(overrides)
    return engine.configure(payload)


def test_data_loader_accepts_required_json_files():
    data = GameDataLoader(DATA_DIR).load()
    assert len(data["board"]) == 40
    counts = {cell_type: 0 for cell_type in ("start", "region", "special", "event", "transport")}
    for cell in data["board"]:
        counts[cell["type"]] += 1
    assert counts == {"start": 1, "region": 25, "special": 4, "event": 9, "transport": 1}
    assert data["regions"][0]["name"] == "김천"
    assert data["regions"][-1]["name"] == "부산"
    assert data["building_prices"]["gimcheon"]["land"] == 700_000
    assert data["building_prices"]["busan"]["mixed_use"] == 20_150_000
    assert {"balanced", "aggressive", "conservative", "random"}.issubset(data["bot_strategies"])
    assert len(data["events"]) >= 20
    scopes = {scope: sum(1 for event in data["events"] if event["scope"] == scope) for scope in ("personal", "regional", "nationwide")}
    assert scopes["personal"] >= 6
    assert scopes["regional"] >= 7
    assert scopes["nationwide"] >= 7


def test_data_loader_reports_file_and_item_for_invalid_board(tmp_path):
    for name in GameDataLoader.REQUIRED_FILES.values():
        (tmp_path / name).write_text("[]", encoding="utf-8")
    (tmp_path / "board.json").write_text('[{"index": 1, "name": "bad", "type": "land"}]', encoding="utf-8")
    (tmp_path / "schemas").mkdir()
    for name in [
        "board.schema.json",
        "regions.schema.json",
        "building_prices.schema.json",
        "industries.schema.json",
        "special_regions.schema.json",
        "events.schema.json",
        "bot_strategies.schema.json",
    ]:
        (tmp_path / "schemas" / name).write_text("{}", encoding="utf-8")
    with pytest.raises(DataValidationError, match="board.json"):
        GameDataLoader(tmp_path).load()


def test_regions_and_building_prices_land_must_match(tmp_path):
    for name in GameDataLoader.REQUIRED_FILES.values():
        source = __import__("pathlib").Path(DATA_DIR) / name
        (tmp_path / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "schemas").mkdir()
    for source in __import__("pathlib").Path(DATA_DIR, "schemas").iterdir():
        (tmp_path / "schemas" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    prices = (tmp_path / "building_prices.json").read_text(encoding="utf-8")
    (tmp_path / "building_prices.json").write_text(prices.replace('"land": 700000', '"land": 710000', 1), encoding="utf-8")
    with pytest.raises(DataValidationError, match="land_price differs"):
        GameDataLoader(tmp_path).load()


def test_events_reject_protected_targets(tmp_path):
    for name in GameDataLoader.REQUIRED_FILES.values():
        source = __import__("pathlib").Path(DATA_DIR) / name
        (tmp_path / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "schemas").mkdir()
    for source in __import__("pathlib").Path(DATA_DIR, "schemas").iterdir():
        (tmp_path / "schemas" / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    events = (tmp_path / "events.json").read_text(encoding="utf-8")
    (tmp_path / "events.json").write_text(events.replace('"building_market_value"', '"land_price"', 1), encoding="utf-8")
    with pytest.raises(DataValidationError, match="protected target"):
        GameDataLoader(tmp_path).load()


def test_money_uses_integer_won_and_rounds_after_rate_calculation():
    assert apply_rate(1_000_000, 12, 100) == 120_000
    assert round_to_50k(124_999) == 100_000
    assert round_to_50k(125_000) == 150_000
    with pytest.raises(TypeError):
        apply_rate(1000.5, 10, 100)


def test_lobby_join_rules_and_initial_economy():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "human"])
    first = engine.join("Alice")
    assert first["join_order"] == 1
    assert first["cash_won"] == 10_000_000
    assert first["position"] == 0
    assert first["lands"] == []
    assert first["buildings"] == []
    assert first["loans"] == []
    assert first["operating_rights"] == []
    with pytest.raises(GameRuleError, match="blank"):
        engine.join(" ")
    with pytest.raises(GameRuleError, match="already"):
        engine.join("Alice")
    engine.join("Bob")
    with pytest.raises(GameRuleError, match="full"):
        engine.join("Cara")


def test_start_with_bots_and_no_human_for_observer_simulation():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["bot", "bot"], fast_simulation=False)
    state = engine.start_game()
    assert state["phase"] == "active"
    assert all(player["is_bot"] for player in state["players"])
    assert all(player["status"] == "active" for player in state["players"])


def test_fast_simulation_runs_all_bot_game_to_temporary_end():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["bot", "bot"], fast_simulation=True, total_rounds=10, bot_action_delay=2)
    state = engine.start_game()
    assert state["phase"] == "finished"
    assert state["ended"] is True


def test_core_settings_locked_after_start_and_new_join_blocked():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    engine.join("Alice")
    engine.start_game()
    with pytest.raises(GameRuleError, match="started"):
        configure(engine, total_rounds=20)
    with pytest.raises(GameRuleError, match="started"):
        engine.join("Bob")


def test_turn_server_dice_forced_start_stop_and_round_increment():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "human"])
    a = engine.join("Alice")
    b = engine.join("Bob")
    engine.start_game()
    engine.set_forced_dice(6)
    result = engine.roll_dice(a["id"])
    assert result["dice"] == 6
    assert result["position"] == result["to_position"] == 6
    assert result["from_position"] == 0
    assert result["movement_path"] == [1, 2, 3, 4, 5, 6]
    assert engine.state.pending_action["type"] == "purchase_land"
    with pytest.raises(GameRuleError, match="already"):
        engine.roll_dice(a["id"])
    engine.decline_pending_action(a["id"])
    engine.end_turn(a["id"])
    engine.set_forced_dice(3)
    engine.roll_dice(b["id"])
    engine.decline_pending_action(b["id"])
    state = engine.end_turn(b["id"])
    assert state["global_round"] == 2


def test_only_current_player_can_act_and_humans_bots_share_engine_rules():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], bot_action_delay=0)
    human = engine.join("Alice")
    state = engine.start_game()
    bot_id = next(player["id"] for player in state["players"] if player["is_bot"])
    with pytest.raises(GameRuleError, match="only current"):
        engine.roll_dice(bot_id)
    engine.set_forced_dice(2)
    engine.take_turn_for_player(human["id"], source="dev")
    engine.set_forced_dice(2)
    engine.take_turn_for_player(bot_id, source="bot")
    players = {player["id"]: player for player in engine.public_state()["players"]}
    assert players[human["id"]]["position"] == 2
    assert players[bot_id]["position"] == 2


def test_board_wrap_forces_stop_at_start_and_discards_remaining_move():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.set_player_position(human["id"], 38)
    engine.set_forced_dice(5)
    assert engine.roll_dice(human["id"])["position"] == 0


def test_land_purchase_decline_and_cash_rules_are_server_side():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.set_forced_dice(1)
    engine.roll_dice(human["id"])
    assert engine.state.pending_action["region_id"] == "gimcheon"
    state = engine.purchase_land(human["id"])
    player = next(player for player in state["players"] if player["id"] == human["id"])
    assert player["cash_won"] == 9_300_000
    assert state["land_ownership"]["gimcheon"] == human["id"]
    engine.decline_pending_action(human["id"])
    engine.end_turn(human["id"])


def test_land_purchase_fails_without_cash_and_failure_does_not_clear_pending():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.set_player_cash(human["id"], 100)
    engine.set_forced_dice(1)
    engine.roll_dice(human["id"])
    with pytest.raises(GameRuleError, match="not enough cash"):
        engine.purchase_land(human["id"])
    assert engine.state.pending_action["type"] == "purchase_land"


def test_other_player_land_without_commercial_or_mixed_charges_five_percent_and_can_go_negative():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "human"])
    owner = engine.join("Owner")
    visitor = engine.join("Visitor")
    engine.start_game()
    engine.create_land_ownership(owner["id"], "jinju")
    engine.end_turn(owner["id"])
    engine.set_player_cash(visitor["id"], 10_000)
    engine.set_forced_dice(3)
    engine.roll_dice(visitor["id"])
    players = {player.id: player for player in engine.state.players}
    assert players[visitor["id"]].cash_won == -40_000
    assert players[owner["id"]].cash_won == 10_050_000


def test_building_rules_owner_limits_initial_value_and_one_success_per_visit():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.set_forced_dice(1)
    engine.roll_dice(human["id"])
    state = engine.build_on_land(human["id"], "industrial")
    building = state["buildings"][0]
    assert building["owner_id"] == human["id"]
    assert building["nominal_owner_id"] == human["id"]
    assert building["ownership_chain"] == [human["id"]]
    assert building["construction_cost_won"] == 1_450_000
    assert building["market_value_won"] == 1_450_000
    engine.state.pending_action = {"type": "build", "player_id": human["id"], "region_id": "gimcheon"}
    with pytest.raises(GameRuleError, match="only one successful"):
        engine.build_on_land(human["id"], "residential")
    assert len(engine.state.buildings) == 1


def test_successful_build_clears_pending_action_to_prevent_duplicate_bot_build():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.set_forced_dice(1)
    engine.roll_dice(human["id"])
    engine.build_on_land(human["id"], "residential")
    assert engine.state.pending_action is None


def test_failed_build_action_does_not_spend_visit_edit_count():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.set_forced_dice(1)
    engine.roll_dice(human["id"])
    with pytest.raises(GameRuleError, match="unsupported"):
        engine.build_on_land(human["id"], "hotel")
    engine.build_on_land(human["id"], "residential")
    assert len(engine.state.buildings) == 1


def test_industrial_and_mixed_are_limited_one_per_region_but_residential_commercial_are_unlimited():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.create_building(human["id"], "gimcheon", "residential")
    engine.create_building(human["id"], "gimcheon", "residential")
    engine.create_building(human["id"], "gimcheon", "commercial")
    engine.create_building(human["id"], "gimcheon", "commercial")
    engine.create_building(human["id"], "gimcheon", "industrial")
    with pytest.raises(GameRuleError, match="limited"):
        engine.create_building(human["id"], "gimcheon", "industrial")
    engine.create_building(human["id"], "gimcheon", "mixed_use")
    with pytest.raises(GameRuleError, match="limited"):
        engine.create_building(human["id"], "gimcheon", "mixed_use")


def test_commercial_visit_rates_are_adjusted_once_by_grade():
    engine = GameEngine(DATA_DIR)
    assert engine.commercial_visit_fee_rate("daegu") == (270, 1000)
    assert engine.commercial_visit_fee_rate("gimcheon") == (180, 1000)


def test_bot_investment_uses_same_cash_and_position_rules():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], bot_strategies=["balanced", "aggressive"], bot_action_delay=0)
    human = engine.join("Alice")
    engine.start_game()
    engine.end_turn(human["id"])
    bot = engine.current_player()
    engine.set_forced_dice(1)
    state = engine.take_turn_for_player(bot.id, source="bot")
    bot_state = next(player for player in state["players"] if player["id"] == bot.id)
    assert "gimcheon" in bot_state["lands"]
    assert bot_state["cash_won"] == 7_400_000
    assert len(bot_state["buildings"]) == 1


def test_bot_strategy_build_preferences_and_cash_reserve():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], bot_strategies=["balanced", "aggressive"], bot_action_delay=0)
    human = engine.join("Alice")
    engine.start_game()
    engine.end_turn(human["id"])
    bot = engine.current_player()
    engine.create_land_ownership(bot.id, "gimcheon")
    engine.set_forced_dice(1)
    state = engine.take_turn_for_player(bot.id, source="bot")
    assert state["buildings"][0]["building_type"] == "mixed_use"


def test_commercial_and_mixed_visit_fees_sum_per_building_and_skip_land_fee():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "human"])
    owner = engine.join("Owner")
    visitor = engine.join("Visitor")
    engine.start_game()
    engine.create_land_ownership(owner["id"], "gimcheon")
    engine.create_building(owner["id"], "gimcheon", "commercial")
    engine.create_building(owner["id"], "gimcheon", "mixed_use")
    for building in engine.state.buildings:
        engine.set_building_market_value(building["id"], 1_000_000)
    engine.end_turn(owner["id"])
    engine.set_forced_dice(1)
    engine.roll_dice(visitor["id"])
    players = {player.id: player for player in engine.state.players}
    assert players[visitor["id"]].cash_won == 9_650_000
    assert players[owner["id"]].cash_won == 10_350_000
    owner_ledger = engine.state.ledgers[owner["id"]]
    assert owner_ledger["gross_income"] == 350_000
    assert len(owner_ledger["income_entries"]) == 2


def test_residential_has_no_visit_or_lap_income_and_market_value_floor():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "human"])
    owner = engine.join("Owner")
    visitor = engine.join("Visitor")
    engine.start_game()
    engine.create_land_ownership(owner["id"], "gimcheon")
    engine.create_building(owner["id"], "gimcheon", "residential")
    building_id = engine.state.buildings[0]["id"]
    engine.set_building_market_value(building_id, -1)
    assert engine.state.buildings[0]["market_value_won"] == 0
    engine.end_turn(owner["id"])
    engine.set_forced_dice(1)
    engine.roll_dice(visitor["id"])
    players = {player.id: player for player in engine.state.players}
    assert players[visitor["id"]].cash_won == 9_950_000
    assert players[owner["id"]].cash_won == 10_050_000


def test_start_settlement_order_tax_bonus_loan_and_ledger_fields():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.set_player_cash(human["id"], 0)
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.create_building(human["id"], "gimcheon", "industrial")
    engine.set_building_market_value(engine.state.buildings[0]["id"], 10_000_000)
    settlement = engine.settle_start_for_player(human["id"])
    ledger = settlement["ledger"]
    assert settlement["steps"] == [
        "1. industrial_and_mixed_income_loss",
        "2. taxable_income_fixed",
        "3. tax_notice_and_payment",
        "4. non_taxable_start_bonus",
        "5. existing_loan_auto_payment",
        "6. new_loan_decision",
        "7. limit_maturity_bankruptcy",
        "8. settlement_created",
        "9. ready_for_turn_end",
    ]
    assert ledger["gross_income"] == 1_200_000
    assert ledger["taxable_income"] == 1_200_000
    assert ledger["tax_rate"] == 300
    assert ledger["tax_due"] == 50_000
    assert ledger["start_bonus"] == 3_000_000
    assert settlement["cash_after"] == 4_150_000


def test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.create_land_ownership(human["id"], "jinju")
    engine.create_building(human["id"], "gimcheon", "commercial")
    engine.create_building(human["id"], "gimcheon", "industrial")
    assert engine._calculate_tax_rate_bps(engine._find_player(human["id"])) == 550
    engine.set_player_tax_rate(human["id"], 1234)
    assert engine._calculate_tax_rate_bps(engine._find_player(human["id"])) == 1234


def test_land_purchase_lap_exempts_undeveloped_tax_until_next_lap():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.set_forced_dice(1)
    engine.roll_dice(human["id"])
    engine.purchase_land(human["id"])
    assert engine._calculate_tax_rate_bps(engine._find_player(human["id"])) == 0
    engine.settle_start_for_player(human["id"])
    assert engine._calculate_tax_rate_bps(engine._find_player(human["id"])) == 50


def test_industrial_rate_clamps_and_mixed_lap_rate_clamps():
    engine = GameEngine(DATA_DIR)
    assert engine.set_industrial_return_rate(5000)["industrial_return_rate_bps"] == 2400
    assert engine.set_industrial_return_rate(-100)["industrial_return_rate_bps"] == 0
    assert engine.set_industrial_return_rate(-500, explicit_override=True)["industrial_return_rate_bps"] == -500


def test_explicit_override_event_allows_negative_mixed_lap_loss():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.set_player_cash(human["id"], 0)
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.create_building(human["id"], "gimcheon", "mixed_use")
    engine.set_building_market_value(engine.state.buildings[0]["id"], 10_000_000)
    engine.apply_event({"industrial_return_rate_bps": -500, "explicit_override": True})
    settlement = engine.settle_start_for_player(human["id"])
    assert settlement["ledger"]["losses"] == 700_000
    assert settlement["cash_after"] == 2_300_000


def test_emergency_loan_exact_limit_duplicate_maturity_and_bankruptcy():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.set_player_cash(human["id"], -23_000_000)
    settlement = engine.settle_start_for_player(human["id"])
    assert settlement["cash_after"] == 0
    assert engine.state.loans[human["id"]]["principal_won"] == 20_000_000
    assert engine.state.loans[human["id"]]["remaining_due_won"] == 22_000_000
    with pytest.raises(GameRuleError, match="duplicate"):
        engine.create_loan(human["id"], 1)
    engine.run_laps(human["id"], 4)
    assert engine._find_player(human["id"]).status == "bankrupt"


def test_start_settlement_existing_unpaid_loan_with_negative_cash_bankrupts_without_unhandled_duplicate():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], total_rounds=120)
    human = engine.join("Alice")
    engine.start_game()
    engine.create_loan(human["id"], 1_000_000)
    engine.set_player_cash(human["id"], -5_000_000)
    settlement = engine.settle_start_for_player(human["id"])
    assert settlement["status_after"] == "bankrupt"
    assert engine._find_player(human["id"]).status == "bankrupt"


def test_emergency_loan_excess_need_bankrupts_player():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.set_player_cash(human["id"], -23_000_001)
    engine.settle_start_for_player(human["id"])
    assert engine._find_player(human["id"]).status == "bankrupt"


def test_existing_loan_auto_repaid_from_start_bonus_after_tax():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.set_player_cash(human["id"], 0)
    engine.create_loan(human["id"], 1_000_000)
    engine.set_player_cash(human["id"], 0)
    settlement = engine.settle_start_for_player(human["id"])
    assert settlement["ledger"]["loan_payment"] == 1_100_000
    assert settlement["cash_after"] == 1_900_000
    assert human["id"] not in engine.state.loans


def test_negative_cash_blocks_human_and_bot_investment():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], bot_strategies=["balanced", "aggressive"], bot_action_delay=0)
    human = engine.join("Alice")
    engine.start_game()
    engine.set_player_cash(human["id"], -1)
    engine.set_forced_dice(1)
    engine.roll_dice(human["id"])
    with pytest.raises(GameRuleError, match="negative cash"):
        engine.purchase_land(human["id"])
    engine.force_end_current_turn()
    bot = engine.current_player()
    engine.set_player_cash(bot.id, -1)
    engine.set_forced_dice(1)
    engine.take_turn_for_player(bot.id, source="bot")
    assert "gimcheon" not in bot.lands
    assert any("negative cash" in item["message"] for item in engine.state.bot_debug_log)


def test_negative_cash_allows_building_sale_but_not_investment():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.create_building(human["id"], "gimcheon", "residential")
    building_id = engine.state.buildings[0]["id"]
    engine.set_building_market_value(building_id, 1_000_000)
    engine.set_player_position(human["id"], 1)
    engine.set_player_cash(human["id"], -500_000)
    state = engine.sell_building(human["id"], building_id)
    player = next(player for player in state["players"] if player["id"] == human["id"])
    assert player["cash_won"] == 500_000
    assert state["buildings"] == []


def test_building_sale_rules_by_type_and_commercial_delayed_refund():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.create_building(human["id"], "gimcheon", "commercial")
    building_id = engine.state.buildings[0]["id"]
    engine.set_building_market_value(building_id, 2_000_000)
    engine.set_player_position(human["id"], 1)
    before = engine._find_player(human["id"]).cash_won
    state = engine.sell_building(human["id"], building_id)
    assert engine._find_player(human["id"]).cash_won == before
    assert state["pending_commercial_sale_refunds"][0]["refund_won"] == 1_000_000
    settlement = engine.settle_start_for_player(human["id"])
    assert settlement["ledger"]["gross_income"] >= 1_000_000
    assert engine.state.pending_commercial_sale_refunds == []


def test_building_sale_requires_exact_region_single_chain_and_edit_available():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.create_building(human["id"], "gimcheon", "residential")
    building_id = engine.state.buildings[0]["id"]
    with pytest.raises(GameRuleError, match="exactly"):
        engine.sell_building(human["id"], building_id)
    engine.set_player_position(human["id"], 1)
    engine.state.buildings[0]["ownership_chain"].append("other")
    with pytest.raises(GameRuleError, match="split"):
        engine.sell_building(human["id"], building_id)


def test_industrial_and_mixed_sale_remove_building_without_refund():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.create_building(human["id"], "gimcheon", "industrial")
    building_id = engine.state.buildings[0]["id"]
    engine.set_player_position(human["id"], 1)
    before = engine._find_player(human["id"]).cash_won
    state = engine.sell_building(human["id"], building_id)
    assert engine._find_player(human["id"]).cash_won == before
    assert state["buildings"] == []


def test_land_trade_fixed_price_timeout_acceptance_and_rights_constraints():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "human"])
    seller = engine.join("Seller")
    buyer = engine.join("Buyer")
    engine.start_game()
    engine.create_land_ownership(seller["id"], "gimcheon")
    engine.set_player_position(seller["id"], 1)
    state = engine.propose_land_trade(seller["id"], buyer["id"], "gimcheon")
    assert state["land_trade_offer"]["price_won"] == 700_000
    state = engine.respond_land_trade(buyer["id"], True)
    assert state["land_ownership"]["gimcheon"] == buyer["id"]
    assert engine._find_player(seller["id"]).cash_won == 10_700_000
    engine.end_turn(seller["id"])
    engine.create_building(buyer["id"], "gimcheon", "residential")
    engine.state.buildings[0]["ownership_chain"] = [buyer["id"], seller["id"]]
    engine.set_player_position(buyer["id"], 1)
    state = engine.propose_land_trade(buyer["id"], seller["id"], "gimcheon")
    assert state["land_trade_offer"]["buyer_id"] == seller["id"]


def test_land_trade_auto_rejects_after_timeout_and_bot_responds_immediately():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], bot_strategies=["balanced", "aggressive"])
    human = engine.join("Seller")
    engine.start_game()
    bot = next(player for player in engine.state.players if player.is_bot)
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.set_player_position(human["id"], 1)
    engine.propose_land_trade(human["id"], bot.id, "gimcheon")
    assert engine.state.land_trade_offer is None
    assert engine.state.land_ownership["gimcheon"] == bot.id


def test_special_region_purchase_external_visit_forced_sale_and_endgame_value():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "human"], total_rounds=10)
    owner = engine.join("Owner")
    visitor = engine.join("Visitor")
    engine.start_game()
    engine.set_forced_dice(5)
    engine.roll_dice(owner["id"])
    assert engine.state.pending_action["type"] == "purchase_special"
    engine.purchase_special_region(owner["id"])
    assert engine.state.special_ownership["pyeongchang"] == owner["id"]
    engine.end_turn(owner["id"])
    engine.set_forced_dice(5)
    engine.roll_dice(visitor["id"])
    assert engine.state.special_values["pyeongchang"] == 2_400_000
    engine.end_turn(visitor["id"])
    engine.force_special_sale_dice(6)
    engine.set_player_position(owner["id"], 0)
    engine.set_forced_dice(5)
    engine.roll_dice(owner["id"])
    assert engine.state.last_settlement["payout_won"] == 2_500_000
    assert "pyeongchang" not in engine.state.special_ownership


def test_special_region_endgame_pays_current_value_120_percent_and_transfer_is_blocked():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], total_rounds=10)
    human = engine.join("Owner")
    engine.start_game()
    engine.state.special_ownership["seoul"] = human["id"]
    engine.state.special_values["seoul"] = 12_000_000
    engine.state.global_round = 10
    engine.take_turn_for_player(human["id"], source="dev")
    bot_id = engine.current_player().id
    state = engine.take_turn_for_player(bot_id, source="bot")
    assert state["ended"] is True
    assert engine._find_player(human["id"]).cash_won >= 24_400_000
    assert engine.state.special_ownership == {}


def test_operating_right_transfer_builds_a_to_b_to_c_to_d_chain_and_operator_gets_income():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=4, slot_types=["human", "human", "human", "human"])
    a = engine.join("A")
    b = engine.join("B")
    c = engine.join("C")
    d = engine.join("D")
    engine.start_game()
    engine.create_land_ownership(a["id"], "gimcheon")
    engine.create_building(a["id"], "gimcheon", "commercial")
    building_id = engine.state.buildings[0]["id"]
    engine.set_building_market_value(building_id, 1_000_000)
    engine.set_player_position(a["id"], 1)
    engine.propose_operating_right_transfer(a["id"], b["id"], building_id, 100_000)
    engine.respond_operating_right_transfer(b["id"], True)
    engine.state.successful_build_edit_this_visit = False
    engine.state.current_turn_index = 1
    engine.set_player_position(b["id"], 1)
    engine.propose_operating_right_transfer(b["id"], c["id"], building_id, 100_000)
    engine.respond_operating_right_transfer(c["id"], True)
    engine.state.successful_build_edit_this_visit = False
    engine.state.current_turn_index = 2
    engine.set_player_position(c["id"], 1)
    engine.propose_operating_right_transfer(c["id"], d["id"], building_id, 100_000)
    state = engine.respond_operating_right_transfer(d["id"], True)
    building = state["buildings"][0]
    assert building["ownership_chain"] == [a["id"], b["id"], c["id"], d["id"]]
    assert building["operator_id"] == d["id"]
    before = engine._find_player(d["id"]).cash_won
    engine._pay_building_visit_fees(engine._find_player(b["id"]), "gimcheon")
    assert engine._find_player(d["id"]).cash_won > before
    assert engine._find_player(d["id"]).cash_won > 9_900_000


def test_transferred_building_tax_only_last_operator_gets_one_percent_point():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=4, slot_types=["human", "human", "human", "human"])
    a = engine.join("A")
    b = engine.join("B")
    c = engine.join("C")
    d = engine.join("D")
    engine.start_game()
    engine.create_building(a["id"], "gimcheon", "industrial")
    building_id = engine.state.buildings[0]["id"]
    engine.create_ownership_chain(building_id, [a["id"], b["id"], c["id"], d["id"]])
    assert engine._calculate_tax_rate_bps(engine._find_player(a["id"])) == 0
    assert engine._calculate_tax_rate_bps(engine._find_player(b["id"])) == 0
    assert engine._calculate_tax_rate_bps(engine._find_player(c["id"])) == 0
    assert engine._calculate_tax_rate_bps(engine._find_player(d["id"])) == 100


def test_usage_change_d_request_reorders_chain_after_all_approvals():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=4, slot_types=["human", "human", "human", "human"])
    a = engine.join("A")
    b = engine.join("B")
    c = engine.join("C")
    d = engine.join("D")
    engine.start_game()
    engine.create_building(a["id"], "gimcheon", "residential")
    building_id = engine.state.buildings[0]["id"]
    engine.create_ownership_chain(building_id, [a["id"], b["id"], c["id"], d["id"]])
    engine.state.current_turn_index = 3
    engine.set_player_position(d["id"], 1)
    engine.request_usage_change(d["id"], building_id, "commercial")
    engine.respond_usage_change(a["id"], True)
    engine.respond_usage_change(b["id"], True)
    state = engine.respond_usage_change(c["id"], True)
    building = state["buildings"][0]
    assert building["building_type"] == "commercial"
    assert building["ownership_chain"] == [a["id"], d["id"], b["id"], c["id"]]
    assert building["operator_id"] == c["id"]


def test_usage_change_rejection_does_not_spend_edit_and_same_visit_repeat_blocked():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=2, slot_types=["human", "human"])
    a = engine.join("A")
    b = engine.join("B")
    engine.start_game()
    engine.create_building(a["id"], "gimcheon", "residential")
    building_id = engine.state.buildings[0]["id"]
    engine.create_ownership_chain(building_id, [a["id"], b["id"]])
    engine.state.current_turn_index = 1
    engine.set_player_position(b["id"], 1)
    engine.request_usage_change(b["id"], building_id, "commercial")
    engine.respond_usage_change(a["id"], False)
    assert engine.state.successful_build_edit_this_visit is False
    with pytest.raises(GameRuleError, match="same usage"):
        engine.request_usage_change(b["id"], building_id, "commercial")


def test_recall_by_middle_manager_truncates_lower_chain_and_nominal_owner_pays_operator():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=4, slot_types=["human", "human", "human", "human"])
    a = engine.join("A")
    b = engine.join("B")
    c = engine.join("C")
    d = engine.join("D")
    engine.start_game()
    engine.create_building(a["id"], "gimcheon", "commercial")
    building_id = engine.state.buildings[0]["id"]
    engine.set_building_market_value(building_id, 1_000_000)
    engine.create_ownership_chain(building_id, [a["id"], b["id"], c["id"], d["id"]])
    engine.state.current_turn_index = 1
    engine.set_player_position(b["id"], 1)
    state = engine.recall_operating_rights(b["id"], building_id)
    building = state["buildings"][0]
    assert building["ownership_chain"] == [a["id"], b["id"]]
    assert engine._find_player(a["id"]).cash_won == 9_000_000
    assert engine._find_player(d["id"]).cash_won == 11_000_000
    engine.state.current_turn_index = 0
    engine.set_player_position(a["id"], 1)
    with pytest.raises(GameRuleError, match="building edit"):
        engine.sell_building(a["id"], building_id)


def test_bot_operating_right_negotiation_and_usage_approval_are_logged():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], bot_strategies=["balanced", "aggressive"])
    a = engine.join("A")
    engine.start_game()
    bot = next(player for player in engine.state.players if player.is_bot)
    engine.create_building(a["id"], "gimcheon", "industrial")
    building_id = engine.state.buildings[0]["id"]
    engine.set_player_position(a["id"], 1)
    engine.propose_operating_right_transfer(a["id"], bot.id, building_id, 1)
    assert engine.state.buildings[0]["operator_id"] == bot.id
    assert any("operating right" in entry["message"] for entry in engine.state.bot_debug_log)


def test_event_trigger_from_event_cell_and_chain_uses_json_effects():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.set_forced_dice(2)
    engine.roll_dice(human["id"])
    assert engine.state.active_events
    engine.trigger_event("personal_chain_01", human["id"], "gimcheon", "chain")
    assert any(item["source"] == "chain" for item in engine.state.event_history)


def test_event_multiplier_stacks_without_intermediate_money_rounding():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.create_building(human["id"], "gimcheon", "commercial")
    building = engine.state.buildings[0]
    building["market_value_won"] = 1_234_567
    engine.trigger_event("regional_boom_01", human["id"], "gimcheon", "manual")
    engine.trigger_event("nationwide_boom_01", human["id"], "gimcheon", "manual")
    for event in engine.state.active_events:
        event["age_rounds"] = event["duration_rounds"]
    adjusted = engine.adjusted_building_value(building)
    assert adjusted == round_to_50k(apply_rate(apply_rate(1_234_567, 11500, 10000), 10800, 10000))


def test_event_duration_recovery_and_removal():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.trigger_event("nationwide_boom_01", human["id"], "gimcheon", "manual")
    event = engine.state.active_events[0]
    assert engine._event_intensity_bps(event) == 0
    for _ in range(event["duration_rounds"]):
        engine._advance_event_steps()
    assert engine._event_intensity_bps(event) == 10_000
    for _ in range(event["recovery_rounds"] + 1):
        engine._advance_event_steps()
    assert engine.state.active_events == []


def test_event_industrial_clamp_and_explicit_override():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.trigger_event("nationwide_extreme_01", human["id"], "gimcheon", "manual")
    engine.state.active_events[0]["age_rounds"] = 5
    assert engine._adjusted_industrial_rate_bps(engine._find_player(human["id"]), "gimcheon") < 0


def test_personal_report_contains_required_sections():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("Alice")
    engine.start_game()
    engine.create_building(human["id"], "gimcheon", "industrial")
    engine.trigger_event("personal_industry_01", human["id"], "gimcheon", "manual")
    report = engine.personal_report(human["id"])
    assert {"building_value_changes", "return_rate_changes", "tax_rate_changes", "major_events", "industry_impact", "risk_factors", "outlook"}.issubset(report)


def test_bot_mass_simulation_uses_real_engine_and_returns_metrics():
    engine = GameEngine(DATA_DIR)
    result = engine.run_bot_simulation({
        "players": 2,
        "strategies": ["balanced", "aggressive"],
        "total_rounds": 10,
        "events_enabled": True,
        "event_frequency": 2,
        "starting_cash": 10_000_000,
        "start_bonus": 3_000_000,
        "commercial_rate_multiplier_bps": 10_000,
        "industrial_base_return_bps": 1200,
        "industrial_min_bps": 0,
        "industrial_max_bps": 2400,
        "seed": 7,
        "runs": 3,
    })
    assert result["runs"] == 3
    assert "strategy_win_rates" in result
    assert "event_average_impact" in result
    assert "average_top_asset_gap" in result


def test_bankruptcy_d_removes_last_operator_and_c_becomes_operator():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=4, slot_types=["human", "human", "human", "human"])
    a = engine.join("A")
    b = engine.join("B")
    c = engine.join("C")
    d = engine.join("D")
    engine.start_game()
    engine.create_building(a["id"], "gimcheon", "commercial")
    building_id = engine.state.buildings[0]["id"]
    engine.create_ownership_chain(building_id, [a["id"], b["id"], c["id"], d["id"]])
    engine.force_bankruptcy(d["id"], "forced")
    building = engine.state.buildings[0]
    assert building["ownership_chain"] == [a["id"], b["id"], c["id"]]
    assert building["operator_id"] == c["id"]
    assert engine._find_player(d["id"]).status == "bankrupt"


def test_bankruptcy_middle_member_removed_but_bottom_operator_stays():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=4, slot_types=["human", "human", "human", "human"])
    a = engine.join("A")
    b = engine.join("B")
    c = engine.join("C")
    d = engine.join("D")
    engine.start_game()
    engine.create_building(a["id"], "gimcheon", "commercial")
    building_id = engine.state.buildings[0]["id"]
    engine.create_ownership_chain(building_id, [a["id"], b["id"], c["id"], d["id"]])
    engine.force_bankruptcy(b["id"], "forced")
    building = engine.state.buildings[0]
    assert building["ownership_chain"] == [a["id"], c["id"], d["id"]]
    assert building["operator_id"] == d["id"]


def test_bankruptcy_c_member_removed_but_d_operator_stays():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=4, slot_types=["human", "human", "human", "human"])
    a = engine.join("A")
    b = engine.join("B")
    c = engine.join("C")
    d = engine.join("D")
    engine.start_game()
    engine.create_building(a["id"], "gimcheon", "commercial")
    building_id = engine.state.buildings[0]["id"]
    engine.create_ownership_chain(building_id, [a["id"], b["id"], c["id"], d["id"]])
    engine.force_bankruptcy(c["id"], "forced")
    building = engine.state.buildings[0]
    assert building["ownership_chain"] == [a["id"], b["id"], d["id"]]
    assert building["operator_id"] == d["id"]


def test_bankruptcy_a_takeover_success_requires_land_price_payment():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=4, slot_types=["human", "human", "human", "human"])
    a = engine.join("A")
    b = engine.join("B")
    c = engine.join("C")
    d = engine.join("D")
    engine.start_game()
    engine.create_land_ownership(a["id"], "gimcheon")
    engine.create_building(a["id"], "gimcheon", "commercial")
    building_id = engine.state.buildings[0]["id"]
    engine.create_ownership_chain(building_id, [a["id"], b["id"], c["id"], d["id"]])
    before = engine._find_player(d["id"]).cash_won
    engine.set_takeover_decision(d["id"], True)
    engine.force_bankruptcy(a["id"], "forced")
    assert engine.state.land_ownership["gimcheon"] == d["id"]
    assert engine._find_player(d["id"]).cash_won == before - 700_000
    assert engine.state.buildings[0]["nominal_owner_id"] == d["id"]
    assert engine.state.buildings[0]["ownership_chain"] == [d["id"], b["id"], c["id"]]


def test_bankruptcy_a_takeover_decline_removes_buildings_and_refunds_bottom_operator():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=4, slot_types=["human", "human", "human", "human"])
    a = engine.join("A")
    b = engine.join("B")
    c = engine.join("C")
    d = engine.join("D")
    engine.start_game()
    engine.create_land_ownership(a["id"], "gimcheon")
    engine.create_building(a["id"], "gimcheon", "commercial")
    building_id = engine.state.buildings[0]["id"]
    engine.set_building_market_value(building_id, 1_000_000)
    engine.create_ownership_chain(building_id, [a["id"], b["id"], c["id"], d["id"]])
    before = engine._find_player(d["id"]).cash_won
    engine.set_takeover_decision(d["id"], False)
    engine.force_bankruptcy(a["id"], "forced")
    assert "gimcheon" not in engine.state.land_ownership
    assert engine.state.buildings == []
    assert engine._find_player(d["id"]).cash_won == before + 1_000_000


def test_standalone_assets_cash_special_refund_disappear_on_bankruptcy():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("A")
    engine.start_game()
    engine.create_land_ownership(human["id"], "gimcheon")
    engine.create_building(human["id"], "gimcheon", "commercial")
    engine.state.special_ownership["seoul"] = human["id"]
    engine.state.pending_commercial_sale_refunds.append({"player_id": human["id"], "refund_won": 1_000_000, "region_id": "gimcheon"})
    engine.force_bankruptcy(human["id"], "forced")
    assert engine._find_player(human["id"]).cash_won == 0
    assert "seoul" not in engine.state.special_ownership
    assert engine.state.pending_commercial_sale_refunds == []


def test_auto_exit_is_distinct_from_bankruptcy_and_cannot_revive():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("A")
    engine.start_game()
    engine.set_no_action_count(human["id"], 3)
    player = engine._find_player(human["id"])
    assert player.status == "exited"
    assert engine.state.rankings[human["id"]] is None
    with pytest.raises(GameRuleError, match="revival"):
        engine.revive_player(human["id"])


def test_bot_action_failure_records_no_action_without_auto_exit():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("A")
    engine.start_game()
    bot = next(player for player in engine.state.players if player.is_bot)
    for _ in range(3):
        engine.record_bot_action_failure(bot.id)
    assert engine.state.no_action_counts[bot.id] == 3
    assert bot.status == "active"
    assert any("action failure" in item["message"] for item in engine.state.bot_debug_log)
    assert engine._find_player(human["id"]).status == "active"


def test_pause_does_not_increment_auto_exit_count():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"])
    human = engine.join("A")
    engine.start_game()
    engine.pause()
    engine.set_no_action_count(human["id"], 3)
    assert engine._find_player(human["id"]).status == "active"


def test_bankruptcy_on_own_turn_becomes_last_action_of_round():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=3, slot_types=["human", "human", "human"], total_rounds=50)
    a = engine.join("A")
    b = engine.join("B")
    c = engine.join("C")
    engine.start_game()
    engine.force_bankruptcy(a["id"], "forced")
    assert engine.state.global_round == 2
    assert engine.current_player().id == b["id"]
    assert engine._find_player(c["id"]).status == "active"


def test_revival_conditions_and_limits():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], total_rounds=120)
    human = engine.join("A")
    engine.start_game()
    engine.force_bankruptcy(human["id"], "forced")
    engine.state.global_round = 25
    engine.skip_revival_wait(human["id"], 20)
    state = engine.revive_player(human["id"])
    player = next(player for player in state["players"] if player["id"] == human["id"])
    assert player["status"] == "active"
    assert player["cash_won"] == 10_000_000
    assert player["position"] == 0
    assert player["lands"] == []
    assert player["loans"] == []


def test_revival_rejects_low_remaining_round_gap_and_max_limit():
    low_remaining = GameEngine(DATA_DIR)
    configure(low_remaining, slot_types=["human", "bot"], total_rounds=50)
    human = low_remaining.join("A")
    low_remaining.start_game()
    low_remaining.state.global_round = 15
    low_remaining.force_bankruptcy(human["id"], "forced")
    low_remaining.state.global_round = 40
    low_remaining.skip_revival_wait(human["id"], 20)
    with pytest.raises(GameRuleError, match="revival"):
        low_remaining.revive_player(human["id"])

    close_gap = GameEngine(DATA_DIR)
    configure(close_gap, total_slots=3, slot_types=["human", "human", "human"], total_rounds=120)
    a = close_gap.join("A")
    b = close_gap.join("B")
    close_gap.join("C")
    close_gap.start_game()
    close_gap.force_bankruptcy(a["id"], "forced")
    close_gap.state.global_round = 10
    close_gap.force_bankruptcy(b["id"], "forced")
    close_gap.state.global_round = 35
    close_gap.skip_revival_wait(b["id"], 20)
    with pytest.raises(GameRuleError, match="revival"):
        close_gap.revive_player(b["id"])

    max_once = GameEngine(DATA_DIR)
    configure(max_once, total_slots=3, slot_types=["human", "human", "bot"], total_rounds=100)
    player = max_once.join("A")
    max_once.join("B")
    max_once.start_game()
    max_once.force_bankruptcy(player["id"], "forced")
    max_once.state.global_round = 25
    max_once.skip_revival_wait(player["id"], 20)
    max_once.revive_player(player["id"])
    max_once.force_bankruptcy(player["id"], "forced")
    max_once.state.global_round = 50
    max_once.skip_revival_wait(player["id"], 20)
    with pytest.raises(GameRuleError, match="revival"):
        max_once.revive_player(player["id"])


def test_bot_revival_strategy_logs_decision():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], bot_strategies=["balanced", "balanced"], total_rounds=120)
    engine.join("A")
    engine.start_game()
    bot = next(player for player in engine.state.players if player.is_bot)
    engine.force_bankruptcy(bot.id, "forced")
    engine.state.global_round = 25
    engine.skip_revival_wait(bot.id, 20)
    engine.evaluate_bot_revivals()
    assert bot.status == "active"
    assert any("revive" in item["message"] for item in engine.state.bot_debug_log)


def test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=2, slot_types=["human", "human"], total_rounds=10)
    a = engine.join("A")
    b = engine.join("B")
    engine.start_game()
    engine.create_land_ownership(a["id"], "gimcheon")
    engine.create_building(a["id"], "gimcheon", "commercial")
    building_id = engine.state.buildings[0]["id"]
    engine.set_building_market_value(building_id, 2_000_000)
    engine.create_ownership_chain(building_id, [a["id"], b["id"]])
    engine.state.pending_commercial_sale_refunds.append({"player_id": a["id"], "refund_won": 9_999_999, "region_id": "gimcheon"})
    totals = engine.finalize_game("test")["assets"]
    assert totals[a["id"]] == 10_700_000 + 1_000_000
    assert totals[b["id"]] == 11_000_000

    solo = GameEngine(DATA_DIR)
    configure(solo, total_slots=2, slot_types=["human", "human"])
    owner = solo.join("Owner")
    solo.join("Other")
    solo.start_game()
    solo.create_land_ownership(owner["id"], "gimcheon")
    solo.create_building(owner["id"], "gimcheon", "commercial")
    solo.set_building_market_value(solo.state.buildings[0]["id"], 2_000_000)
    solo_totals = solo.finalize_game("test")["assets"]
    assert solo_totals[owner["id"]] == 12_700_000


def test_final_ranking_survivors_bankrupts_exited_and_tie_breakers():
    engine = GameEngine(DATA_DIR)
    configure(engine, total_slots=4, slot_types=["human", "human", "human", "human"], total_rounds=120)
    a = engine.join("A")
    b = engine.join("B")
    c = engine.join("C")
    d = engine.join("D")
    engine.start_game()
    engine.create_land_ownership(a["id"], "busan")
    engine.force_bankruptcy(b["id"], "forced")
    engine.state.global_round = 20
    engine.force_bankruptcy(c["id"], "forced")
    engine.set_no_action_count(d["id"], 3)
    rankings = engine.finalize_game("test")["rankings"]
    assert rankings[a["id"]] == 1
    assert rankings[c["id"]] < rankings[b["id"]]
    assert rankings[d["id"]] is None


def test_single_solvent_player_early_end_and_result_is_fixed():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "human"], total_rounds=120)
    a = engine.join("A")
    b = engine.join("B")
    engine.start_game()
    engine.force_bankruptcy(b["id"], "forced")
    result = engine.state.final_results
    assert engine.state.ended is True
    assert result["reason"] == "single_solvent_player"
    with pytest.raises(GameRuleError, match="ended"):
        engine.force_bankruptcy(a["id"], "forced")
    assert engine.finalize_game("again") == result


def test_game_log_contains_required_categories_and_exports():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], total_rounds=10)
    human = engine.join("A")
    engine.start_game()
    engine.set_forced_dice(1)
    engine.roll_dice(human["id"])
    engine.purchase_land(human["id"])
    engine.finalize_game("test")
    categories = {entry["category"] for entry in engine.export_results("log")["log"]}
    assert {"config", "lobby", "game", "turn", "asset", "money", "final"}.issubset(categories)
    assert "results.csv" == engine.export_results("csv")["filename"]
    assert "asset_history" in engine.export_results("asset-history")
    assert "bot_strategies" in engine.export_results("bot-strategies")


def test_integrated_bot_games_and_pause_preset_paths():
    two = GameEngine(DATA_DIR)
    configure(two, slot_types=["human", "bot"], bot_strategies=["balanced", "aggressive"], total_rounds=10, fast_simulation=True, bot_action_delay=0)
    two.join("A")
    two.start_game()
    while not two.state.ended:
        player = two.current_player()
        two.take_turn_for_player(player.id, source="bot" if player.is_bot else "dev")
    assert two.state.final_results["rankings"]

    one_plus_three = GameEngine(DATA_DIR)
    configure(
        one_plus_three,
        total_slots=4,
        slot_types=["human", "bot", "bot", "bot"],
        bot_strategies=["balanced", "balanced", "aggressive", "conservative"],
        total_rounds=10,
        fast_simulation=True,
        bot_action_delay=0,
    )
    one_plus_three.join("A")
    one_plus_three.start_game()
    while not one_plus_three.state.ended:
        player = one_plus_three.current_player()
        one_plus_three.take_turn_for_player(player.id, source="bot" if player.is_bot else "dev")
    assert one_plus_three.state.final_results["public_wealth"]["players"]

    four = GameEngine(DATA_DIR)
    configure(four, total_slots=4, slot_types=["bot", "bot", "bot", "bot"], bot_strategies=["balanced", "aggressive", "conservative", "random"], total_rounds=100, fast_simulation=True, bot_action_delay=0)
    four.start_game()
    assert four.state.ended is True
    assert four.state.final_results["public_wealth"]["players"]

    transition = GameEngine(DATA_DIR)
    configure(transition, total_slots=4, slot_types=["human", "human", "human", "human"], total_rounds=100)
    a = transition.join("A")
    transition.join("B")
    transition.join("C")
    transition.join("D")
    transition.start_game()
    transition.force_bankruptcy(a["id"], "forced")
    assert len([player for player in transition.state.players if player.status == "active"]) == 3

    tied = GameEngine(DATA_DIR)
    configure(tied, total_slots=2, slot_types=["human", "human"], total_rounds=10)
    tied.join("A")
    tied.join("B")
    tied.start_game()
    rankings = tied.finalize_game("tie")["rankings"]
    assert sorted(rankings.values()) == [1, 2]

    paused = GameEngine(DATA_DIR)
    paused.configure_quick_game("fast_10", pause_at_round=2)
    paused.join("A")
    paused.start_game()
    state = paused.run_quick_game()
    assert state["paused"] is True or state["ended"] is True


def test_step_timeout_auto_rolls_then_end_step_finishes_and_pause_stops_timer(monkeypatch):
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "human"], turn_limit_seconds=15)
    a = engine.join("Alice")
    b = engine.join("Bob")
    engine.start_game()
    engine.state.turn_step["deadline_at"] -= 16
    engine.advance_automation()
    assert engine.current_player().id == a["id"]
    assert engine.state.turn_has_rolled is True
    engine.complete_turn_presentation(a["id"])
    if engine.state.pending_action:
        engine.decline_pending_action(a["id"])
        engine.complete_turn_presentation(a["id"])
    engine.state.turn_step["deadline_at"] -= 20
    engine.advance_automation()
    assert engine.current_player().id == b["id"]
    engine.pause()
    paused_player = engine.current_player().id
    if engine.state.turn_step["deadline_at"] is not None:
        engine.state.turn_step["deadline_at"] -= 99
    engine.advance_automation()
    assert engine.current_player().id == paused_player
    engine.resume()
    if engine.state.turn_step["deadline_at"] is not None:
        engine.state.turn_step["deadline_at"] -= 20
    engine.advance_automation()
    if engine.current_player().id == paused_player:
        assert engine.state.turn_has_rolled is True


def test_final_round_reaches_temporary_end():
    engine = GameEngine(DATA_DIR)
    configure(engine, slot_types=["human", "bot"], total_rounds=10)
    human = engine.join("Alice")
    engine.start_game()
    engine.state.global_round = 10
    engine.take_turn_for_player(human["id"], source="dev")
    bot_id = engine.current_player().id
    state = engine.take_turn_for_player(bot_id, source="bot")
    assert state["phase"] == "finished"
    assert state["ended"] is True


def test_idempotency_returns_same_result_without_duplicate_execution():
    engine = GameEngine(DATA_DIR)
    result1 = engine.with_idempotency("join:1", lambda: engine.join("Alice"))
    result2 = engine.with_idempotency("join:1", lambda: engine.join("Bob"))
    assert result1 == result2
    assert len(engine.state.players) == 1
