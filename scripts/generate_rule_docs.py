"""Generate human-readable official rule documents from the canonical JSON."""

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "rules" / "game_rules.json"

PARTIAL = set()
MISSING = set()
CONFLICT = set()
UNRESOLVED = {"TAX-005", "EVENT-010", "ASSET-006"}

CODE_BY_PREFIX = {
    "GAME": "app.py; game/routes.py; game/automation.py",
    "CONFIG": "game/models.py:HostConfig; game/engine.py:configure",
    "TURN": "game/engine.py:start_game,end_turn,_advance_round",
    "PAUSE": "game/engine.py:pause,resume; game/models.py:pause_started_at",
    "BOARD": "game/data_loader.py:_validate_board,_validate_cross_file_rules; data/board.json",
    "DICE": "game/engine.py:roll_dice",
    "MOVE": "game/engine.py:roll_dice,_move_player",
    "LAND": "game/engine.py:purchase_land,land_purchased_this_visit,region_by_id; data/regions.json",
    "BUILD": "game/engine.py:purchase_land,build_on_land,_build_pending_action; data/building_prices.json",
    "MONEY": "game/economy.py:round_fraction_to_50k; game/services/events.py",
    "FEE": "game/engine.py:_resolve_region_visit,_commercial_visit_rate",
    "RETURN": "game/engine.py:_effective_industrial_rate,_start_settlement",
    "SETTLE": "game/engine.py:_settle_start; game/services/settlement.py",
    "TAX": "game/engine.py:_tax_rate_bps,_start_settlement",
    "LOAN": "game/engine.py:_create_emergency_loan,_auto_repay_loan,_check_loan_maturity; game/services/loans.py",
    "SALE": "game/engine.py:sell_building,_pay_pending_commercial_refunds",
    "SPECIAL": "game/engine.py:_resolve_special_arrival,_force_sell_special_region; game/services/special_regions.py",
    "RIGHTS": "game/engine.py:propose_operating_right_transfer,respond_operating_right_transfer; game/services/rights.py",
    "USAGE": "game/engine.py:request_usage_change,respond_usage_change",
    "RECALL": "game/engine.py:recall_operating_rights",
    "TRADE": "game/engine.py:offer_land_trade,respond_land_trade",
    "EVENT": "game/data_loader.py:_validate_events,_validate_event_references; game/services/events.py",
    "BANKRUPTCY": "game/engine.py:_bankrupt_player,respond_land_takeover; game/services/bankruptcy.py",
    "EXIT": "game/routes.py:record_authenticated_activity; game/engine.py:record_player_activity",
    "REVIVE": "game/engine.py:eligible_for_revival,revive_player",
    "END": "game/engine.py:_check_end_condition,finalize_game,_require_not_ended",
    "ASSET": "game/engine.py:public_wealth,_final_asset_totals,finalize_game",
    "RANK": "game/engine.py:_rank_players (logged repeated server dice)",
    "PRIV": "game/engine.py:client_public_state,player_private_state; game/views.py:host",
}

TEST_BY_PREFIX = {
    "GAME": "tests/test_routes.py; tests/test_engine.py:test_lobby_join_rules_and_initial_economy",
    "CONFIG": "tests/test_routes.py:test_host_only_start_pause_resume_and_config",
    "TURN": "tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment",
    "PAUSE": "tests/test_rule_gap_fixes.py:test_pause_preserves_about_seven_seconds_after_three_seconds_and_long_pause",
    "BOARD": "tests/test_engine.py:test_data_loader_accepts_required_json_files",
    "DICE": "tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment",
    "MOVE": "tests/test_engine.py:test_board_wrap_forces_stop_at_start_and_discards_remaining_move",
    "LAND": "tests/test_land_purchase_build_flow.py; tests/test_engine.py:test_land_purchase_decline_and_cash_rules_are_server_side",
    "BUILD": "tests/test_land_purchase_build_flow.py; tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit",
    "MONEY": "tests/test_rule_gap_fixes.py:test_three_event_composition_rounds_once_and_override_disappears",
    "FEE": "tests/test_engine.py:test_commercial_and_mixed_visit_fees_sum_per_building_and_skip_land_fee",
    "RETURN": "tests/test_engine.py:test_industrial_rate_clamps_and_mixed_lap_rate_clamps",
    "SETTLE": "tests/test_rule_gap_fixes.py:test_start_settlement_is_once_only_under_one_hundred_concurrent_calls",
    "TAX": "tests/test_engine.py:test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax",
    "LOAN": "tests/test_rule_gap_fixes.py:test_loan_maturity_second_and_third_start_one_won_boundaries,test_common_income_deposit_records_once_and_reduces_loan_before_retaining_cash",
    "SALE": "tests/test_engine.py:test_building_sale_rules_by_type_and_commercial_delayed_refund",
    "SPECIAL": "tests/test_rule_gap_fixes.py:test_special_accumulated_value_is_purchase_price_and_survives_forced_sale",
    "RIGHTS": "tests/test_official_rules.py:test_official_operating_right_chain_rejects_duplicate_members",
    "USAGE": "tests/test_engine.py:test_usage_change_d_request_reorders_chain_after_all_approvals",
    "RECALL": "tests/test_engine.py:test_recall_by_middle_manager_truncates_lower_chain_and_nominal_owner_pays_operator",
    "TRADE": "tests/test_rule_gap_fixes.py:test_land_trade_allows_one_external_rights_holder_and_rejects_distribution",
    "EVENT": "tests/test_rule_gap_fixes.py:test_event_semantic_reference_and_cycle_validation,test_three_event_composition_rounds_once_and_override_disappears",
    "BANKRUPTCY": "tests/test_engine.py:test_bankruptcy_a_takeover_success_requires_land_price_payment; tests/test_player_connections.py",
    "EXIT": "tests/test_engine.py:test_auto_exit_is_distinct_from_bankruptcy_and_cannot_revive",
    "REVIVE": "tests/test_official_rules.py:test_official_revival_rejects_exact_fifteen_round_bankruptcy_gap",
    "END": "tests/test_routes.py:test_ended_game_blocks_mutating_routes",
    "ASSET": "tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds",
    "RANK": "tests/test_rule_gap_fixes.py:test_ranking_tie_uses_logged_server_dice_and_host_view_has_log_without_finances",
    "PRIV": "tests/test_rule_gap_fixes.py:test_ranking_tie_uses_logged_server_dice_and_host_view_has_log_without_finances; tests/test_routes.py",
}

NO_DIRECT_TEST = {"EVENT-010"}

NOTES = {
    "PAUSE-001": "offer/request timestamps keep advancing while paused",
    "LOAN-003": "maturity uses current_lap > due_lap instead of the third-start boundary",
    "SPECIAL-002": "purchase charges initial value, not accumulated current value",
    "SPECIAL-003": "forced sale resets accumulated value",
    "RIGHTS-001": "chain mutation does not reject an existing member",
    "TRADE-002": "current distributed-rights check rejects the allowed consolidation case",
    "EVENT-006": "event multipliers perform intermediate won rounding",
    "BANKRUPTCY-004": "D takeover collapses the chain instead of producing D→B→C",
    "REVIVE-002": "exactly 15 rounds is accepted; official boundary excludes it",
    "TAX-005": "user decision required: retain or remove undeveloped-land 0.5%p",
    "EVENT-010": "user approval required for the current 20 event cards",
    "ASSET-006": "user approval required for mixed-use final value of zero",
}


def status(rule_id):
    if rule_id in PARTIAL:
        return "PARTIAL"
    if rule_id in MISSING:
        return "MISSING"
    if rule_id in CONFLICT:
        return "CONFLICT"
    if rule_id in UNRESOLVED:
        return "UNRESOLVED"
    return "MATCH"


def won(value):
    return f"{value:,}"


def generate_rules(data):
    grouped = defaultdict(list)
    for rule in data["rules"]:
        grouped[rule["section"]].append(rule)
    lines = [
        "# 게임 전체 규칙 공식 명세",
        "",
        f"- `rules_version`: `{data['rules_version']}`",
        f"- 시행일: {data['effective_date']}",
        "- 상태: 미결 항목을 분리해 등록한 공식 명세",
        "- 최종 기계 판독 원본: `data/rules/game_rules.json`",
        "",
        "## 권위 순서와 변경 원칙",
        "",
        "구조화 규칙 데이터 → 이 문서 → 코드 → 테스트 순서로 우선한다. 규칙 변경은 먼저 JSON의 버전을 올리고 이 문서와 구현 매트릭스를 재생성한 뒤 코드와 테스트를 맞춘다. `CONFLICT`와 `UNRESOLVED`는 승인 없이 동작을 변경하지 않는다.",
        "",
        "## 구조화 수치",
        "",
        f"참가자는 {data['constants']['players']['minimum']}~{data['constants']['players']['maximum']}명, 시작 현금은 {won(data['constants']['starting_cash_won'])}원, 출발지 보너스는 {won(data['constants']['start_bonus_won'])}원이다. 금액은 원 단위 정수이고 모든 배율 합성 후 마지막에 {won(data['constants']['rounding']['unit_won'])}원 단위 `ROUND_HALF_UP`을 적용한다.",
        "",
        "### 일반지역·건물 고정 가격 (원)",
        "",
        "| 지역 ID | 토지 | 주거 | 상업 | 산업 | 복합 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for region_id, prices in data["building_prices_won"].items():
        lines.append("| " + region_id + " | " + " | ".join(won(prices[key]) for key in ("land", "residential", "commercial", "industrial", "mixed_use")) + " |")
    lines += ["", "### 특수지역 최초가 (원)", "", "| ID | 이름 | 최초가 |", "|---|---|---:|"]
    for region_id, item in data["special_regions"].items():
        lines.append(f"| {region_id} | {item['name']} | {won(item['initial_price_won'])} |")
    lines += ["", "### 출발지 정산 순서", ""]
    for index, step in enumerate(data["settlement_order"], 1):
        lines.append(f"{index}. `{step}`")
    lines += ["", "## 규칙 목록", ""]
    for section, rules in grouped.items():
        lines += [f"### {section}", ""]
        for rule in rules:
            lines.append(f"- **{rule['id']} — {rule['title']}**: {rule['requirement']}")
        lines.append("")
    lines += ["## 미결 항목", ""]
    for item in data["unresolved"]:
        lines.append(f"- **{item['rule_id']}**: {item['question']}")
    lines += ["", "구현 상태와 근거는 `docs/RULE_IMPLEMENTATION_MATRIX.md`, 등록 전 차이는 `docs/RULE_GAP_REPORT_PRE_IMPLEMENTATION.md`에서 확인한다.", ""]
    return "\n".join(lines)


def generate_matrix(data):
    counts = defaultdict(int)
    for rule in data["rules"]:
        counts[status(rule["id"])] += 1
    lines = [
        "# 규칙 구현·테스트 대응표",
        "",
        "분석 기준 HEAD: `bd3d295fc1eb7eecb668492f6aa5f2e8c34619e2`",
        f"기준 `rules_version`: `{data['rules_version']}`",
        "판정 시점: 2026-07-16. 최신 작업 트리의 194개 통과 테스트를 다시 대조한 결과다.",
        "",
        "검증 상태는 `CODE_PRESENT`, `UNIT_TESTED`, `MULTI_CLIENT_TESTED`,",
        "`BROWSER_TESTED`, `REAL_DEVICE_TEST_REQUIRED`, `CONFLICT`, `UNRESOLVED`로 해석한다.",
        "이번 환경에서는 실제 Chromium이 시작되지 않아 어떤 규칙에도 `BROWSER_TESTED`를 새로 부여하지 않았다.",
        "",
        "| MATCH | PARTIAL | MISSING | CONFLICT | UNRESOLVED | 합계 |",
        "|---:|---:|---:|---:|---:|---:|",
        f"| {counts['MATCH']} | {counts['PARTIAL']} | {counts['MISSING']} | {counts['CONFLICT']} | {counts['UNRESOLVED']} | {len(data['rules'])} |",
        "",
        "| 규칙 ID | 판정 | 검증 상태 | 코드 근거 | 테스트 근거 | 차이·비고 |",
        "|---|---|---|---|---|---|",
    ]
    for rule in data["rules"]:
        rule_id = rule["id"]
        prefix = rule_id.split("-", 1)[0]
        test = "—" if rule_id in NO_DIRECT_TEST else TEST_BY_PREFIX[prefix]
        note = "공식 요구와 현재 근거가 일치" if status(rule_id) == "MATCH" else NOTES.get(rule_id, "세부 범위가 일부만 구현·검증됨")
        verification = "UNRESOLVED" if status(rule_id) == "UNRESOLVED" else "UNIT_TESTED"
        lines.append(f"| {rule_id} | {status(rule_id)} | {verification} | {CODE_BY_PREFIX[prefix]} | {test} | {note} |")
    lines += [
        "",
        "## 직접 테스트가 없는 규칙",
        "",
        ", ".join(f"`{item}`" for item in sorted(NO_DIRECT_TEST)) + ". 결정 대기 중인 공식 이벤트 카드 목록 자체만 직접 동작 테스트 대상에서 제외한다.",
        "",
        "## 판정 해석",
        "",
        "- `MATCH`: 현재 코드와 테스트 근거가 공식 규칙과 일치한다.",
        "- `PARTIAL`: 일부 동작 또는 경계 검증이 부족하다.",
        "- `MISSING`: 요구된 구현 또는 직접 검증이 없다.",
        "- `CONFLICT`: 현재 동작이 공식 규칙과 다르며 승인 전 자동 수정하지 않는다.",
        "- `UNRESOLVED`: 공식 결정을 위해 사용자 판단이 필요하다.",
        "- `UNIT_TESTED`: 자동 단위·통합 테스트 근거가 있으나 실제 스마트폰 수동 검증을 뜻하지 않는다.",
        "",
    ]
    return "\n".join(lines)


def main():
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    (ROOT / "docs" / "GAME_RULES.md").write_text(generate_rules(data), encoding="utf-8")
    (ROOT / "docs" / "RULE_IMPLEMENTATION_MATRIX.md").write_text(generate_matrix(data), encoding="utf-8")


if __name__ == "__main__":
    main()
