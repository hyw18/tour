import json
import re
from pathlib import Path

import pytest
from jsonschema import validate

from game.data_loader import GameDataLoader
from game.engine import GameEngine, GameRuleError
from game.models import (
    ALLOWED_ROUNDS,
    ALLOWED_SLOTS,
    ALLOWED_TURN_LIMITS,
    BOARD_SIZE,
    MAX_EMERGENCY_LOAN_PRINCIPAL_WON,
    STARTING_CASH_WON,
    START_BONUS_WON,
)
from scripts.generate_rule_docs import generate_matrix, generate_rules


ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "data" / "rules" / "game_rules.json"
SCHEMA_PATH = ROOT / "data" / "schemas" / "game_rules.schema.json"
RULE_ID_PATTERN = re.compile(r"^[A-Z]+-\d{3}$")


def official_rules():
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def configured_engine(total_rounds=120):
    engine = GameEngine(ROOT / "data")
    engine.configure(
        {
            "total_slots": 2,
            "slot_types": ["human", "bot"],
            "bot_strategies": ["balanced", "balanced"],
            "total_rounds": total_rounds,
            "turn_limit_seconds": 30,
            "bot_action_delay": 0,
            "fast_simulation": False,
        }
    )
    human = engine.join("official-rule-test")
    engine.start_game()
    return engine, human


def test_official_rules_schema_version_authority_and_unique_ids():
    rules = official_rules()
    validate(rules, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    ids = [item["id"] for item in rules["rules"]]
    assert rules["rules_version"] == "2026.07.16.1"
    assert rules["authority_order"] == [
        "data/rules/game_rules.json",
        "docs/GAME_RULES.md",
        "code",
        "tests",
    ]
    assert len(ids) == len(set(ids)) == 106
    assert all(RULE_ID_PATTERN.fullmatch(rule_id) for rule_id in ids)
    assert {item["rule_id"] for item in rules["unresolved"]} == {
        "TAX-005",
        "EVENT-010",
        "ASSET-006",
    }


def test_generated_rule_documents_have_no_drift_from_canonical_json():
    rules = official_rules()
    assert (ROOT / "docs" / "GAME_RULES.md").read_text(encoding="utf-8") == generate_rules(rules)
    assert (ROOT / "docs" / "RULE_IMPLEMENTATION_MATRIX.md").read_text(encoding="utf-8") == generate_matrix(rules)
    matrix_ids = re.findall(r"^\| ([A-Z]+-\d{3}) \|", generate_matrix(rules), re.MULTILINE)
    assert matrix_ids == [item["id"] for item in rules["rules"]]


def test_runtime_loads_official_rules_and_exposes_version():
    loaded = GameDataLoader(ROOT / "data").load()
    engine = GameEngine(ROOT / "data")
    assert loaded["official_rules"] == official_rules()
    assert engine.rules is engine.data["official_rules"]
    assert engine.public_state()["rules_version"] == official_rules()["rules_version"]


def test_official_setup_money_board_and_host_boundaries_match_runtime():
    constants = official_rules()["constants"]
    assert STARTING_CASH_WON == constants["starting_cash_won"] == 10_000_000
    assert START_BONUS_WON == constants["start_bonus_won"] == 3_000_000
    assert BOARD_SIZE == constants["board_counts"]["total"] == 40
    assert ALLOWED_SLOTS == set(range(constants["players"]["minimum"], constants["players"]["maximum"] + 1))
    assert (ALLOWED_ROUNDS.start, ALLOWED_ROUNDS.stop - 1) == (
        constants["rounds"]["minimum"],
        constants["rounds"]["maximum"],
    )
    assert ALLOWED_TURN_LIMITS == set(constants["turn_limit_seconds"])


def test_official_price_tables_are_the_runtime_tables_and_land_is_fixed():
    rules = official_rules()
    loaded = GameDataLoader(ROOT / "data").load()
    assert rules["land_prices_won"] == {item["id"]: item["land_price"] for item in loaded["regions"]}
    assert rules["building_prices_won"] == loaded["building_prices"]
    assert {key: item["initial_price_won"] for key, item in rules["special_regions"].items()} == {
        item["id"]: item["initial_price"] for item in loaded["special_regions"]
    }
    protected = {"land_price", "starting_cash", "start_bonus", "loan_principal_limit"}
    assert all(protected.isdisjoint(event["targets"]) for event in loaded["events"])


def test_special_region_external_visit_has_no_visit_fee():
    engine = GameEngine(ROOT / "data")
    engine.configure({
        "total_slots": 2,
        "slot_types": ["human", "human"],
        "bot_strategies": ["balanced", "balanced"],
        "total_rounds": 10,
        "turn_limit_seconds": 30,
        "bot_action_delay": 0,
        "fast_simulation": False,
    })
    owner = engine.join("special-owner")
    visitor = engine.join("special-visitor")
    engine.start_game()
    engine.state.special_ownership["pyeongchang"] = owner["id"]
    owner_before = engine._find_player(owner["id"]).cash_won
    visitor_before = engine._find_player(visitor["id"]).cash_won
    engine._resolve_special_arrival(engine._find_player(visitor["id"]), "pyeongchang")
    assert engine._find_player(owner["id"]).cash_won == owner_before
    assert engine._find_player(visitor["id"]).cash_won == visitor_before


def test_official_commercial_and_return_rates_match_engine_without_double_adjustment():
    rules = official_rules()["constants"]
    engine = GameEngine(ROOT / "data")
    actual = {str(grade): numerator * 10 for grade, (numerator, denominator) in engine.COMMERCIAL_VISIT_FEE_RATES.items() if denominator == 1000}
    assert actual == rules["commercial_visit_rate_bps_by_grade"]
    assert actual == {"1": 2700, "2": 2430, "3": 2250, "4": 2070, "5": 1800}
    assert engine.state.industrial_return_rate_bps == rules["industrial_return"]["base_bps"] == 1200
    assert (rules["industrial_return"]["minimum_bps"], rules["industrial_return"]["maximum_bps"]) == (0, 2400)
    assert rules["mixed_return"] == {"industrial_delta_bps": -200, "minimum_bps": 0, "maximum_bps": 2200}


def test_official_start_settlement_order_and_loan_limit_boundary():
    rules = official_rules()
    engine, human = configured_engine()
    engine.set_player_cash(human["id"], -23_000_000)
    settlement = engine.settle_start_for_player(human["id"])
    assert [step.split(". ", 1)[1] for step in settlement["steps"]] == [
        "industrial_and_mixed_income_loss",
        "taxable_income_fixed",
        "tax_notice_and_payment",
        "non_taxable_start_bonus",
        "existing_loan_auto_payment",
        "new_loan_decision",
        "limit_maturity_bankruptcy",
        "settlement_created",
        "ready_for_turn_end",
    ]
    assert rules["settlement_order"][0:6] == [step.split(". ", 1)[1] for step in settlement["steps"]][0:6]
    assert engine.state.loans[human["id"]]["principal_won"] == MAX_EMERGENCY_LOAN_PRINCIPAL_WON == 20_000_000


def test_official_loan_maturity_rejects_one_won_at_exact_third_start():
    engine, human = configured_engine()
    engine.create_loan(human["id"], 1)
    loan = engine.state.loans[human["id"]]
    loan["remaining_due_won"] = 1
    engine.state.lap_numbers[human["id"]] = loan["due_lap"]
    engine._check_loan_maturity(engine._find_player(human["id"]))
    assert engine._find_player(human["id"]).status == "bankrupt"


def test_official_operating_right_chain_rejects_duplicate_members():
    engine, owner = configured_engine()
    other = next(player for player in engine.state.players if player.id != owner["id"])
    engine.create_land_ownership(owner["id"], "gimcheon")
    engine.create_building(owner["id"], "gimcheon", "commercial")
    building_id = engine.state.buildings[0]["id"]
    with pytest.raises(GameRuleError, match="duplicate"):
        engine.create_ownership_chain(building_id, [owner["id"], other.id, other.id])


def test_official_event_multipliers_round_only_once_after_full_composition():
    engine, human = configured_engine()
    engine.create_building(human["id"], "gimcheon", "commercial")
    building = engine.state.buildings[0]
    building["market_value_won"] = 71_668
    engine.trigger_event("regional_boom_01", human["id"], "gimcheon", "manual")
    engine.trigger_event("nationwide_boom_01", human["id"], "gimcheon", "manual")
    for event in engine.state.active_events:
        event["age_rounds"] = 1
    assert engine.adjusted_building_value(building) == 50_000


def test_official_revival_rejects_exact_fifteen_round_bankruptcy_gap():
    engine = GameEngine(ROOT / "data")
    engine.configure({
        "total_slots": 3,
        "slot_types": ["human", "human", "bot"],
        "bot_strategies": ["balanced"] * 3,
        "total_rounds": 120,
        "turn_limit_seconds": 30,
        "bot_action_delay": 0,
        "fast_simulation": False,
    })
    first = engine.join("first")
    second = engine.join("second")
    engine.start_game()
    engine.force_bankruptcy(first["id"], "test")
    engine.state.global_round = 16
    engine.force_bankruptcy(second["id"], "test")
    engine.state.global_round = 40
    engine._find_player(first["id"]).status = "active"
    assert engine._can_revive(engine._find_player(second["id"])) is False
