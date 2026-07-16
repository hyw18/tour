# 규칙 구현·테스트 대응표

분석 기준 HEAD: `bd3d295fc1eb7eecb668492f6aa5f2e8c34619e2`
기준 `rules_version`: `2026.07.16.1`
판정 시점: 2026-07-16. 최신 작업 트리의 194개 통과 테스트를 다시 대조한 결과다.

검증 상태는 `CODE_PRESENT`, `UNIT_TESTED`, `MULTI_CLIENT_TESTED`,
`BROWSER_TESTED`, `REAL_DEVICE_TEST_REQUIRED`, `CONFLICT`, `UNRESOLVED`로 해석한다.
이번 환경에서는 실제 Chromium이 시작되지 않아 어떤 규칙에도 `BROWSER_TESTED`를 새로 부여하지 않았다.

| MATCH | PARTIAL | MISSING | CONFLICT | UNRESOLVED | 합계 |
|---:|---:|---:|---:|---:|---:|
| 103 | 0 | 0 | 0 | 3 | 106 |

| 규칙 ID | 판정 | 검증 상태 | 코드 근거 | 테스트 근거 | 차이·비고 |
|---|---|---|---|---|---|
| GAME-001 | MATCH | UNIT_TESTED | app.py; game/routes.py; game/automation.py | tests/test_routes.py; tests/test_engine.py:test_lobby_join_rules_and_initial_economy | 공식 요구와 현재 근거가 일치 |
| GAME-002 | MATCH | UNIT_TESTED | app.py; game/routes.py; game/automation.py | tests/test_routes.py; tests/test_engine.py:test_lobby_join_rules_and_initial_economy | 공식 요구와 현재 근거가 일치 |
| GAME-003 | MATCH | UNIT_TESTED | app.py; game/routes.py; game/automation.py | tests/test_routes.py; tests/test_engine.py:test_lobby_join_rules_and_initial_economy | 공식 요구와 현재 근거가 일치 |
| CONFIG-001 | MATCH | UNIT_TESTED | game/models.py:HostConfig; game/engine.py:configure | tests/test_routes.py:test_host_only_start_pause_resume_and_config | 공식 요구와 현재 근거가 일치 |
| CONFIG-002 | MATCH | UNIT_TESTED | game/models.py:HostConfig; game/engine.py:configure | tests/test_routes.py:test_host_only_start_pause_resume_and_config | 공식 요구와 현재 근거가 일치 |
| CONFIG-003 | MATCH | UNIT_TESTED | game/models.py:HostConfig; game/engine.py:configure | tests/test_routes.py:test_host_only_start_pause_resume_and_config | 공식 요구와 현재 근거가 일치 |
| TURN-001 | MATCH | UNIT_TESTED | game/engine.py:start_game,end_turn,_advance_round | tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment | 공식 요구와 현재 근거가 일치 |
| TURN-002 | MATCH | UNIT_TESTED | game/engine.py:start_game,end_turn,_advance_round | tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment | 공식 요구와 현재 근거가 일치 |
| TURN-003 | MATCH | UNIT_TESTED | game/engine.py:start_game,end_turn,_advance_round | tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment | 공식 요구와 현재 근거가 일치 |
| TURN-004 | MATCH | UNIT_TESTED | game/engine.py:start_game,end_turn,_advance_round | tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment | 공식 요구와 현재 근거가 일치 |
| PAUSE-001 | MATCH | UNIT_TESTED | game/engine.py:pause,resume; game/models.py:pause_started_at | tests/test_rule_gap_fixes.py:test_pause_preserves_about_seven_seconds_after_three_seconds_and_long_pause | 공식 요구와 현재 근거가 일치 |
| BOARD-001 | MATCH | UNIT_TESTED | game/data_loader.py:_validate_board,_validate_cross_file_rules; data/board.json | tests/test_engine.py:test_data_loader_accepts_required_json_files | 공식 요구와 현재 근거가 일치 |
| DICE-001 | MATCH | UNIT_TESTED | game/engine.py:roll_dice | tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment | 공식 요구와 현재 근거가 일치 |
| MOVE-001 | MATCH | UNIT_TESTED | game/engine.py:roll_dice,_move_player | tests/test_engine.py:test_board_wrap_forces_stop_at_start_and_discards_remaining_move | 공식 요구와 현재 근거가 일치 |
| LAND-001 | MATCH | UNIT_TESTED | game/engine.py:purchase_land,land_purchased_this_visit,region_by_id; data/regions.json | tests/test_land_purchase_build_flow.py; tests/test_engine.py:test_land_purchase_decline_and_cash_rules_are_server_side | 공식 요구와 현재 근거가 일치 |
| LAND-002 | MATCH | UNIT_TESTED | game/engine.py:purchase_land,land_purchased_this_visit,region_by_id; data/regions.json | tests/test_land_purchase_build_flow.py; tests/test_engine.py:test_land_purchase_decline_and_cash_rules_are_server_side | 공식 요구와 현재 근거가 일치 |
| LAND-003 | MATCH | UNIT_TESTED | game/engine.py:purchase_land,land_purchased_this_visit,region_by_id; data/regions.json | tests/test_land_purchase_build_flow.py; tests/test_engine.py:test_land_purchase_decline_and_cash_rules_are_server_side | 공식 요구와 현재 근거가 일치 |
| BUILD-001 | MATCH | UNIT_TESTED | game/engine.py:purchase_land,build_on_land,_build_pending_action; data/building_prices.json | tests/test_land_purchase_build_flow.py; tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit | 공식 요구와 현재 근거가 일치 |
| BUILD-002 | MATCH | UNIT_TESTED | game/engine.py:purchase_land,build_on_land,_build_pending_action; data/building_prices.json | tests/test_land_purchase_build_flow.py; tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit | 공식 요구와 현재 근거가 일치 |
| BUILD-003 | MATCH | UNIT_TESTED | game/engine.py:purchase_land,build_on_land,_build_pending_action; data/building_prices.json | tests/test_land_purchase_build_flow.py; tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit | 공식 요구와 현재 근거가 일치 |
| BUILD-004 | MATCH | UNIT_TESTED | game/engine.py:purchase_land,build_on_land,_build_pending_action; data/building_prices.json | tests/test_land_purchase_build_flow.py; tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit | 공식 요구와 현재 근거가 일치 |
| BUILD-005 | MATCH | UNIT_TESTED | game/engine.py:purchase_land,build_on_land,_build_pending_action; data/building_prices.json | tests/test_land_purchase_build_flow.py; tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit | 공식 요구와 현재 근거가 일치 |
| BUILD-006 | MATCH | UNIT_TESTED | game/engine.py:purchase_land,build_on_land,_build_pending_action; data/building_prices.json | tests/test_land_purchase_build_flow.py; tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit | 공식 요구와 현재 근거가 일치 |
| MONEY-001 | MATCH | UNIT_TESTED | game/economy.py:round_fraction_to_50k; game/services/events.py | tests/test_rule_gap_fixes.py:test_three_event_composition_rounds_once_and_override_disappears | 공식 요구와 현재 근거가 일치 |
| MONEY-002 | MATCH | UNIT_TESTED | game/economy.py:round_fraction_to_50k; game/services/events.py | tests/test_rule_gap_fixes.py:test_three_event_composition_rounds_once_and_override_disappears | 공식 요구와 현재 근거가 일치 |
| FEE-001 | MATCH | UNIT_TESTED | game/engine.py:_resolve_region_visit,_commercial_visit_rate | tests/test_engine.py:test_commercial_and_mixed_visit_fees_sum_per_building_and_skip_land_fee | 공식 요구와 현재 근거가 일치 |
| FEE-002 | MATCH | UNIT_TESTED | game/engine.py:_resolve_region_visit,_commercial_visit_rate | tests/test_engine.py:test_commercial_and_mixed_visit_fees_sum_per_building_and_skip_land_fee | 공식 요구와 현재 근거가 일치 |
| FEE-003 | MATCH | UNIT_TESTED | game/engine.py:_resolve_region_visit,_commercial_visit_rate | tests/test_engine.py:test_commercial_and_mixed_visit_fees_sum_per_building_and_skip_land_fee | 공식 요구와 현재 근거가 일치 |
| FEE-004 | MATCH | UNIT_TESTED | game/engine.py:_resolve_region_visit,_commercial_visit_rate | tests/test_engine.py:test_commercial_and_mixed_visit_fees_sum_per_building_and_skip_land_fee | 공식 요구와 현재 근거가 일치 |
| RETURN-001 | MATCH | UNIT_TESTED | game/engine.py:_effective_industrial_rate,_start_settlement | tests/test_engine.py:test_industrial_rate_clamps_and_mixed_lap_rate_clamps | 공식 요구와 현재 근거가 일치 |
| RETURN-002 | MATCH | UNIT_TESTED | game/engine.py:_effective_industrial_rate,_start_settlement | tests/test_engine.py:test_industrial_rate_clamps_and_mixed_lap_rate_clamps | 공식 요구와 현재 근거가 일치 |
| RETURN-003 | MATCH | UNIT_TESTED | game/engine.py:_effective_industrial_rate,_start_settlement | tests/test_engine.py:test_industrial_rate_clamps_and_mixed_lap_rate_clamps | 공식 요구와 현재 근거가 일치 |
| RETURN-004 | MATCH | UNIT_TESTED | game/engine.py:_effective_industrial_rate,_start_settlement | tests/test_engine.py:test_industrial_rate_clamps_and_mixed_lap_rate_clamps | 공식 요구와 현재 근거가 일치 |
| SETTLE-001 | MATCH | UNIT_TESTED | game/engine.py:_settle_start; game/services/settlement.py | tests/test_rule_gap_fixes.py:test_start_settlement_is_once_only_under_one_hundred_concurrent_calls | 공식 요구와 현재 근거가 일치 |
| SETTLE-002 | MATCH | UNIT_TESTED | game/engine.py:_settle_start; game/services/settlement.py | tests/test_rule_gap_fixes.py:test_start_settlement_is_once_only_under_one_hundred_concurrent_calls | 공식 요구와 현재 근거가 일치 |
| SETTLE-003 | MATCH | UNIT_TESTED | game/engine.py:_settle_start; game/services/settlement.py | tests/test_rule_gap_fixes.py:test_start_settlement_is_once_only_under_one_hundred_concurrent_calls | 공식 요구와 현재 근거가 일치 |
| TAX-001 | MATCH | UNIT_TESTED | game/engine.py:_tax_rate_bps,_start_settlement | tests/test_engine.py:test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax | 공식 요구와 현재 근거가 일치 |
| TAX-002 | MATCH | UNIT_TESTED | game/engine.py:_tax_rate_bps,_start_settlement | tests/test_engine.py:test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax | 공식 요구와 현재 근거가 일치 |
| TAX-003 | MATCH | UNIT_TESTED | game/engine.py:_tax_rate_bps,_start_settlement | tests/test_engine.py:test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax | 공식 요구와 현재 근거가 일치 |
| TAX-004 | MATCH | UNIT_TESTED | game/engine.py:_tax_rate_bps,_start_settlement | tests/test_engine.py:test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax | 공식 요구와 현재 근거가 일치 |
| TAX-005 | UNRESOLVED | UNRESOLVED | game/engine.py:_tax_rate_bps,_start_settlement | tests/test_engine.py:test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax | user decision required: retain or remove undeveloped-land 0.5%p |
| LOAN-001 | MATCH | UNIT_TESTED | game/engine.py:_create_emergency_loan,_auto_repay_loan,_check_loan_maturity; game/services/loans.py | tests/test_rule_gap_fixes.py:test_loan_maturity_second_and_third_start_one_won_boundaries,test_common_income_deposit_records_once_and_reduces_loan_before_retaining_cash | 공식 요구와 현재 근거가 일치 |
| LOAN-002 | MATCH | UNIT_TESTED | game/engine.py:_create_emergency_loan,_auto_repay_loan,_check_loan_maturity; game/services/loans.py | tests/test_rule_gap_fixes.py:test_loan_maturity_second_and_third_start_one_won_boundaries,test_common_income_deposit_records_once_and_reduces_loan_before_retaining_cash | 공식 요구와 현재 근거가 일치 |
| LOAN-003 | MATCH | UNIT_TESTED | game/engine.py:_create_emergency_loan,_auto_repay_loan,_check_loan_maturity; game/services/loans.py | tests/test_rule_gap_fixes.py:test_loan_maturity_second_and_third_start_one_won_boundaries,test_common_income_deposit_records_once_and_reduces_loan_before_retaining_cash | 공식 요구와 현재 근거가 일치 |
| LOAN-004 | MATCH | UNIT_TESTED | game/engine.py:_create_emergency_loan,_auto_repay_loan,_check_loan_maturity; game/services/loans.py | tests/test_rule_gap_fixes.py:test_loan_maturity_second_and_third_start_one_won_boundaries,test_common_income_deposit_records_once_and_reduces_loan_before_retaining_cash | 공식 요구와 현재 근거가 일치 |
| LOAN-005 | MATCH | UNIT_TESTED | game/engine.py:_create_emergency_loan,_auto_repay_loan,_check_loan_maturity; game/services/loans.py | tests/test_rule_gap_fixes.py:test_loan_maturity_second_and_third_start_one_won_boundaries,test_common_income_deposit_records_once_and_reduces_loan_before_retaining_cash | 공식 요구와 현재 근거가 일치 |
| SALE-001 | MATCH | UNIT_TESTED | game/engine.py:sell_building,_pay_pending_commercial_refunds | tests/test_engine.py:test_building_sale_rules_by_type_and_commercial_delayed_refund | 공식 요구와 현재 근거가 일치 |
| SALE-002 | MATCH | UNIT_TESTED | game/engine.py:sell_building,_pay_pending_commercial_refunds | tests/test_engine.py:test_building_sale_rules_by_type_and_commercial_delayed_refund | 공식 요구와 현재 근거가 일치 |
| SALE-003 | MATCH | UNIT_TESTED | game/engine.py:sell_building,_pay_pending_commercial_refunds | tests/test_engine.py:test_building_sale_rules_by_type_and_commercial_delayed_refund | 공식 요구와 현재 근거가 일치 |
| SALE-004 | MATCH | UNIT_TESTED | game/engine.py:sell_building,_pay_pending_commercial_refunds | tests/test_engine.py:test_building_sale_rules_by_type_and_commercial_delayed_refund | 공식 요구와 현재 근거가 일치 |
| SPECIAL-001 | MATCH | UNIT_TESTED | game/engine.py:_resolve_special_arrival,_force_sell_special_region; game/services/special_regions.py | tests/test_rule_gap_fixes.py:test_special_accumulated_value_is_purchase_price_and_survives_forced_sale | 공식 요구와 현재 근거가 일치 |
| SPECIAL-002 | MATCH | UNIT_TESTED | game/engine.py:_resolve_special_arrival,_force_sell_special_region; game/services/special_regions.py | tests/test_rule_gap_fixes.py:test_special_accumulated_value_is_purchase_price_and_survives_forced_sale | 공식 요구와 현재 근거가 일치 |
| SPECIAL-003 | MATCH | UNIT_TESTED | game/engine.py:_resolve_special_arrival,_force_sell_special_region; game/services/special_regions.py | tests/test_rule_gap_fixes.py:test_special_accumulated_value_is_purchase_price_and_survives_forced_sale | 공식 요구와 현재 근거가 일치 |
| SPECIAL-004 | MATCH | UNIT_TESTED | game/engine.py:_resolve_special_arrival,_force_sell_special_region; game/services/special_regions.py | tests/test_rule_gap_fixes.py:test_special_accumulated_value_is_purchase_price_and_survives_forced_sale | 공식 요구와 현재 근거가 일치 |
| SPECIAL-005 | MATCH | UNIT_TESTED | game/engine.py:_resolve_special_arrival,_force_sell_special_region; game/services/special_regions.py | tests/test_rule_gap_fixes.py:test_special_accumulated_value_is_purchase_price_and_survives_forced_sale | 공식 요구와 현재 근거가 일치 |
| RIGHTS-001 | MATCH | UNIT_TESTED | game/engine.py:propose_operating_right_transfer,respond_operating_right_transfer; game/services/rights.py | tests/test_official_rules.py:test_official_operating_right_chain_rejects_duplicate_members | 공식 요구와 현재 근거가 일치 |
| RIGHTS-002 | MATCH | UNIT_TESTED | game/engine.py:propose_operating_right_transfer,respond_operating_right_transfer; game/services/rights.py | tests/test_official_rules.py:test_official_operating_right_chain_rejects_duplicate_members | 공식 요구와 현재 근거가 일치 |
| RIGHTS-003 | MATCH | UNIT_TESTED | game/engine.py:propose_operating_right_transfer,respond_operating_right_transfer; game/services/rights.py | tests/test_official_rules.py:test_official_operating_right_chain_rejects_duplicate_members | 공식 요구와 현재 근거가 일치 |
| RIGHTS-004 | MATCH | UNIT_TESTED | game/engine.py:propose_operating_right_transfer,respond_operating_right_transfer; game/services/rights.py | tests/test_official_rules.py:test_official_operating_right_chain_rejects_duplicate_members | 공식 요구와 현재 근거가 일치 |
| USAGE-001 | MATCH | UNIT_TESTED | game/engine.py:request_usage_change,respond_usage_change | tests/test_engine.py:test_usage_change_d_request_reorders_chain_after_all_approvals | 공식 요구와 현재 근거가 일치 |
| USAGE-002 | MATCH | UNIT_TESTED | game/engine.py:request_usage_change,respond_usage_change | tests/test_engine.py:test_usage_change_d_request_reorders_chain_after_all_approvals | 공식 요구와 현재 근거가 일치 |
| USAGE-003 | MATCH | UNIT_TESTED | game/engine.py:request_usage_change,respond_usage_change | tests/test_engine.py:test_usage_change_d_request_reorders_chain_after_all_approvals | 공식 요구와 현재 근거가 일치 |
| USAGE-004 | MATCH | UNIT_TESTED | game/engine.py:request_usage_change,respond_usage_change | tests/test_engine.py:test_usage_change_d_request_reorders_chain_after_all_approvals | 공식 요구와 현재 근거가 일치 |
| RECALL-001 | MATCH | UNIT_TESTED | game/engine.py:recall_operating_rights | tests/test_engine.py:test_recall_by_middle_manager_truncates_lower_chain_and_nominal_owner_pays_operator | 공식 요구와 현재 근거가 일치 |
| RECALL-002 | MATCH | UNIT_TESTED | game/engine.py:recall_operating_rights | tests/test_engine.py:test_recall_by_middle_manager_truncates_lower_chain_and_nominal_owner_pays_operator | 공식 요구와 현재 근거가 일치 |
| RECALL-003 | MATCH | UNIT_TESTED | game/engine.py:recall_operating_rights | tests/test_engine.py:test_recall_by_middle_manager_truncates_lower_chain_and_nominal_owner_pays_operator | 공식 요구와 현재 근거가 일치 |
| TRADE-001 | MATCH | UNIT_TESTED | game/engine.py:offer_land_trade,respond_land_trade | tests/test_rule_gap_fixes.py:test_land_trade_allows_one_external_rights_holder_and_rejects_distribution | 공식 요구와 현재 근거가 일치 |
| TRADE-002 | MATCH | UNIT_TESTED | game/engine.py:offer_land_trade,respond_land_trade | tests/test_rule_gap_fixes.py:test_land_trade_allows_one_external_rights_holder_and_rejects_distribution | 공식 요구와 현재 근거가 일치 |
| TRADE-003 | MATCH | UNIT_TESTED | game/engine.py:offer_land_trade,respond_land_trade | tests/test_rule_gap_fixes.py:test_land_trade_allows_one_external_rights_holder_and_rejects_distribution | 공식 요구와 현재 근거가 일치 |
| EVENT-001 | MATCH | UNIT_TESTED | game/data_loader.py:_validate_events,_validate_event_references; game/services/events.py | tests/test_rule_gap_fixes.py:test_event_semantic_reference_and_cycle_validation,test_three_event_composition_rounds_once_and_override_disappears | 공식 요구와 현재 근거가 일치 |
| EVENT-002 | MATCH | UNIT_TESTED | game/data_loader.py:_validate_events,_validate_event_references; game/services/events.py | tests/test_rule_gap_fixes.py:test_event_semantic_reference_and_cycle_validation,test_three_event_composition_rounds_once_and_override_disappears | 공식 요구와 현재 근거가 일치 |
| EVENT-003 | MATCH | UNIT_TESTED | game/data_loader.py:_validate_events,_validate_event_references; game/services/events.py | tests/test_rule_gap_fixes.py:test_event_semantic_reference_and_cycle_validation,test_three_event_composition_rounds_once_and_override_disappears | 공식 요구와 현재 근거가 일치 |
| EVENT-004 | MATCH | UNIT_TESTED | game/data_loader.py:_validate_events,_validate_event_references; game/services/events.py | tests/test_rule_gap_fixes.py:test_event_semantic_reference_and_cycle_validation,test_three_event_composition_rounds_once_and_override_disappears | 공식 요구와 현재 근거가 일치 |
| EVENT-005 | MATCH | UNIT_TESTED | game/data_loader.py:_validate_events,_validate_event_references; game/services/events.py | tests/test_rule_gap_fixes.py:test_event_semantic_reference_and_cycle_validation,test_three_event_composition_rounds_once_and_override_disappears | 공식 요구와 현재 근거가 일치 |
| EVENT-006 | MATCH | UNIT_TESTED | game/data_loader.py:_validate_events,_validate_event_references; game/services/events.py | tests/test_rule_gap_fixes.py:test_event_semantic_reference_and_cycle_validation,test_three_event_composition_rounds_once_and_override_disappears | 공식 요구와 현재 근거가 일치 |
| EVENT-007 | MATCH | UNIT_TESTED | game/data_loader.py:_validate_events,_validate_event_references; game/services/events.py | tests/test_rule_gap_fixes.py:test_event_semantic_reference_and_cycle_validation,test_three_event_composition_rounds_once_and_override_disappears | 공식 요구와 현재 근거가 일치 |
| EVENT-008 | MATCH | UNIT_TESTED | game/data_loader.py:_validate_events,_validate_event_references; game/services/events.py | tests/test_rule_gap_fixes.py:test_event_semantic_reference_and_cycle_validation,test_three_event_composition_rounds_once_and_override_disappears | 공식 요구와 현재 근거가 일치 |
| EVENT-009 | MATCH | UNIT_TESTED | game/data_loader.py:_validate_events,_validate_event_references; game/services/events.py | tests/test_rule_gap_fixes.py:test_event_semantic_reference_and_cycle_validation,test_three_event_composition_rounds_once_and_override_disappears | 공식 요구와 현재 근거가 일치 |
| EVENT-010 | UNRESOLVED | UNRESOLVED | game/data_loader.py:_validate_events,_validate_event_references; game/services/events.py | — | user approval required for the current 20 event cards |
| BANKRUPTCY-001 | MATCH | UNIT_TESTED | game/engine.py:_bankrupt_player,respond_land_takeover; game/services/bankruptcy.py | tests/test_engine.py:test_bankruptcy_a_takeover_success_requires_land_price_payment; tests/test_player_connections.py | 공식 요구와 현재 근거가 일치 |
| BANKRUPTCY-002 | MATCH | UNIT_TESTED | game/engine.py:_bankrupt_player,respond_land_takeover; game/services/bankruptcy.py | tests/test_engine.py:test_bankruptcy_a_takeover_success_requires_land_price_payment; tests/test_player_connections.py | 공식 요구와 현재 근거가 일치 |
| BANKRUPTCY-003 | MATCH | UNIT_TESTED | game/engine.py:_bankrupt_player,respond_land_takeover; game/services/bankruptcy.py | tests/test_engine.py:test_bankruptcy_a_takeover_success_requires_land_price_payment; tests/test_player_connections.py | 공식 요구와 현재 근거가 일치 |
| BANKRUPTCY-004 | MATCH | UNIT_TESTED | game/engine.py:_bankrupt_player,respond_land_takeover; game/services/bankruptcy.py | tests/test_engine.py:test_bankruptcy_a_takeover_success_requires_land_price_payment; tests/test_player_connections.py | 공식 요구와 현재 근거가 일치 |
| BANKRUPTCY-005 | MATCH | UNIT_TESTED | game/engine.py:_bankrupt_player,respond_land_takeover; game/services/bankruptcy.py | tests/test_engine.py:test_bankruptcy_a_takeover_success_requires_land_price_payment; tests/test_player_connections.py | 공식 요구와 현재 근거가 일치 |
| EXIT-001 | MATCH | UNIT_TESTED | game/routes.py:record_authenticated_activity; game/engine.py:record_player_activity | tests/test_engine.py:test_auto_exit_is_distinct_from_bankruptcy_and_cannot_revive | 공식 요구와 현재 근거가 일치 |
| EXIT-002 | MATCH | UNIT_TESTED | game/routes.py:record_authenticated_activity; game/engine.py:record_player_activity | tests/test_engine.py:test_auto_exit_is_distinct_from_bankruptcy_and_cannot_revive | 공식 요구와 현재 근거가 일치 |
| EXIT-003 | MATCH | UNIT_TESTED | game/routes.py:record_authenticated_activity; game/engine.py:record_player_activity | tests/test_engine.py:test_auto_exit_is_distinct_from_bankruptcy_and_cannot_revive | 공식 요구와 현재 근거가 일치 |
| REVIVE-001 | MATCH | UNIT_TESTED | game/engine.py:eligible_for_revival,revive_player | tests/test_official_rules.py:test_official_revival_rejects_exact_fifteen_round_bankruptcy_gap | 공식 요구와 현재 근거가 일치 |
| REVIVE-002 | MATCH | UNIT_TESTED | game/engine.py:eligible_for_revival,revive_player | tests/test_official_rules.py:test_official_revival_rejects_exact_fifteen_round_bankruptcy_gap | 공식 요구와 현재 근거가 일치 |
| REVIVE-003 | MATCH | UNIT_TESTED | game/engine.py:eligible_for_revival,revive_player | tests/test_official_rules.py:test_official_revival_rejects_exact_fifteen_round_bankruptcy_gap | 공식 요구와 현재 근거가 일치 |
| REVIVE-004 | MATCH | UNIT_TESTED | game/engine.py:eligible_for_revival,revive_player | tests/test_official_rules.py:test_official_revival_rejects_exact_fifteen_round_bankruptcy_gap | 공식 요구와 현재 근거가 일치 |
| REVIVE-005 | MATCH | UNIT_TESTED | game/engine.py:eligible_for_revival,revive_player | tests/test_official_rules.py:test_official_revival_rejects_exact_fifteen_round_bankruptcy_gap | 공식 요구와 현재 근거가 일치 |
| END-001 | MATCH | UNIT_TESTED | game/engine.py:_check_end_condition,finalize_game,_require_not_ended | tests/test_routes.py:test_ended_game_blocks_mutating_routes | 공식 요구와 현재 근거가 일치 |
| END-002 | MATCH | UNIT_TESTED | game/engine.py:_check_end_condition,finalize_game,_require_not_ended | tests/test_routes.py:test_ended_game_blocks_mutating_routes | 공식 요구와 현재 근거가 일치 |
| ASSET-001 | MATCH | UNIT_TESTED | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | 공식 요구와 현재 근거가 일치 |
| ASSET-002 | MATCH | UNIT_TESTED | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | 공식 요구와 현재 근거가 일치 |
| ASSET-003 | MATCH | UNIT_TESTED | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | 공식 요구와 현재 근거가 일치 |
| ASSET-004 | MATCH | UNIT_TESTED | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | 공식 요구와 현재 근거가 일치 |
| ASSET-005 | MATCH | UNIT_TESTED | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | 공식 요구와 현재 근거가 일치 |
| ASSET-006 | UNRESOLVED | UNRESOLVED | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | user approval required for mixed-use final value of zero |
| RANK-001 | MATCH | UNIT_TESTED | game/engine.py:_rank_players (logged repeated server dice) | tests/test_rule_gap_fixes.py:test_ranking_tie_uses_logged_server_dice_and_host_view_has_log_without_finances | 공식 요구와 현재 근거가 일치 |
| RANK-002 | MATCH | UNIT_TESTED | game/engine.py:_rank_players (logged repeated server dice) | tests/test_rule_gap_fixes.py:test_ranking_tie_uses_logged_server_dice_and_host_view_has_log_without_finances | 공식 요구와 현재 근거가 일치 |
| PRIV-001 | MATCH | UNIT_TESTED | game/engine.py:client_public_state,player_private_state; game/views.py:host | tests/test_rule_gap_fixes.py:test_ranking_tie_uses_logged_server_dice_and_host_view_has_log_without_finances; tests/test_routes.py | 공식 요구와 현재 근거가 일치 |
| PRIV-002 | MATCH | UNIT_TESTED | game/engine.py:client_public_state,player_private_state; game/views.py:host | tests/test_rule_gap_fixes.py:test_ranking_tie_uses_logged_server_dice_and_host_view_has_log_without_finances; tests/test_routes.py | 공식 요구와 현재 근거가 일치 |
| PRIV-003 | MATCH | UNIT_TESTED | game/engine.py:client_public_state,player_private_state; game/views.py:host | tests/test_rule_gap_fixes.py:test_ranking_tie_uses_logged_server_dice_and_host_view_has_log_without_finances; tests/test_routes.py | 공식 요구와 현재 근거가 일치 |
| PRIV-004 | MATCH | UNIT_TESTED | game/engine.py:client_public_state,player_private_state; game/views.py:host | tests/test_rule_gap_fixes.py:test_ranking_tie_uses_logged_server_dice_and_host_view_has_log_without_finances; tests/test_routes.py | 공식 요구와 현재 근거가 일치 |

## 직접 테스트가 없는 규칙

`EVENT-010`. 결정 대기 중인 공식 이벤트 카드 목록 자체만 직접 동작 테스트 대상에서 제외한다.

## 판정 해석

- `MATCH`: 현재 코드와 테스트 근거가 공식 규칙과 일치한다.
- `PARTIAL`: 일부 동작 또는 경계 검증이 부족하다.
- `MISSING`: 요구된 구현 또는 직접 검증이 없다.
- `CONFLICT`: 현재 동작이 공식 규칙과 다르며 승인 전 자동 수정하지 않는다.
- `UNRESOLVED`: 공식 결정을 위해 사용자 판단이 필요하다.
- `UNIT_TESTED`: 자동 단위·통합 테스트 근거가 있으나 실제 스마트폰 수동 검증을 뜻하지 않는다.
