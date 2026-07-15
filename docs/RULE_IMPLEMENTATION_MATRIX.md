# 규칙 구현·테스트 대응표

기준 `rules_version`: `2026.07.15.1`  
판정 시점: 2026-07-15. 이 표는 동작을 변경하지 않은 사전 대조 결과다.

| MATCH | PARTIAL | MISSING | CONFLICT | UNRESOLVED | 합계 |
|---:|---:|---:|---:|---:|---:|
| 78 | 10 | 4 | 9 | 3 | 104 |

| 규칙 ID | 판정 | 코드 근거 | 테스트 근거 | 차이·비고 |
|---|---|---|---|---|
| GAME-001 | MATCH | app.py; game/routes.py; game/automation.py | tests/test_routes.py; tests/test_engine.py:test_lobby_join_rules_and_initial_economy | 공식 요구와 현재 근거가 일치 |
| GAME-002 | MATCH | app.py; game/routes.py; game/automation.py | tests/test_routes.py; tests/test_engine.py:test_lobby_join_rules_and_initial_economy | 공식 요구와 현재 근거가 일치 |
| GAME-003 | MATCH | app.py; game/routes.py; game/automation.py | tests/test_routes.py; tests/test_engine.py:test_lobby_join_rules_and_initial_economy | 공식 요구와 현재 근거가 일치 |
| CONFIG-001 | MATCH | game/models.py:HostConfig; game/engine.py:configure | tests/test_routes.py:test_host_only_start_pause_resume_and_config | 공식 요구와 현재 근거가 일치 |
| CONFIG-002 | MATCH | game/models.py:HostConfig; game/engine.py:configure | tests/test_routes.py:test_host_only_start_pause_resume_and_config | 공식 요구와 현재 근거가 일치 |
| CONFIG-003 | MATCH | game/models.py:HostConfig; game/engine.py:configure | tests/test_routes.py:test_host_only_start_pause_resume_and_config | 공식 요구와 현재 근거가 일치 |
| TURN-001 | MATCH | game/engine.py:start_game,end_turn,_advance_round | tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment | 공식 요구와 현재 근거가 일치 |
| TURN-002 | MATCH | game/engine.py:start_game,end_turn,_advance_round | tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment | 공식 요구와 현재 근거가 일치 |
| TURN-003 | MATCH | game/engine.py:start_game,end_turn,_advance_round | tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment | 공식 요구와 현재 근거가 일치 |
| TURN-004 | MATCH | game/engine.py:start_game,end_turn,_advance_round | tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment | 공식 요구와 현재 근거가 일치 |
| PAUSE-001 | CONFLICT | game/engine.py:pause_game,resume_game,elapsed_turn_seconds | tests/test_engine.py:test_timeout_auto_ends_turn_and_pause_stops_timer | offer/request timestamps keep advancing while paused |
| BOARD-001 | MATCH | game/data_loader.py:_validate_board,_validate_cross_file_rules; data/board.json | tests/test_engine.py:test_data_loader_accepts_required_json_files | 공식 요구와 현재 근거가 일치 |
| DICE-001 | MATCH | game/engine.py:roll_dice | tests/test_engine.py:test_turn_server_dice_forced_start_stop_and_round_increment | 공식 요구와 현재 근거가 일치 |
| MOVE-001 | MATCH | game/engine.py:roll_dice,_move_player | tests/test_engine.py:test_board_wrap_forces_stop_at_start_and_discards_remaining_move | 공식 요구와 현재 근거가 일치 |
| LAND-001 | MATCH | game/engine.py:buy_land,region_by_id; data/regions.json | tests/test_engine.py:test_land_purchase_decline_and_cash_rules_are_server_side | 공식 요구와 현재 근거가 일치 |
| LAND-002 | MATCH | game/engine.py:buy_land,region_by_id; data/regions.json | tests/test_engine.py:test_land_purchase_decline_and_cash_rules_are_server_side | 공식 요구와 현재 근거가 일치 |
| BUILD-001 | MATCH | game/engine.py:build; data/building_prices.json | tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit | 공식 요구와 현재 근거가 일치 |
| BUILD-002 | MATCH | game/engine.py:build; data/building_prices.json | tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit | 공식 요구와 현재 근거가 일치 |
| BUILD-003 | MATCH | game/engine.py:build; data/building_prices.json | tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit | 공식 요구와 현재 근거가 일치 |
| BUILD-004 | MATCH | game/engine.py:build; data/building_prices.json | tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit | 공식 요구와 현재 근거가 일치 |
| BUILD-005 | MATCH | game/engine.py:build; data/building_prices.json | tests/test_engine.py:test_building_rules_owner_limits_initial_value_and_one_success_per_visit | 공식 요구와 현재 근거가 일치 |
| MONEY-001 | MATCH | game/economy.py:apply_rate,apply_rate_rounded_50k,round_to_50k | tests/test_engine.py:test_money_uses_integer_won_and_rounds_after_rate_calculation | 공식 요구와 현재 근거가 일치 |
| MONEY-002 | PARTIAL | game/economy.py:apply_rate,apply_rate_rounded_50k,round_to_50k | tests/test_engine.py:test_money_uses_integer_won_and_rounds_after_rate_calculation | 세부 범위가 일부만 구현·검증됨 |
| FEE-001 | MATCH | game/engine.py:_resolve_region_visit,_commercial_visit_rate | tests/test_engine.py:test_commercial_and_mixed_visit_fees_sum_per_building_and_skip_land_fee | 공식 요구와 현재 근거가 일치 |
| FEE-002 | MATCH | game/engine.py:_resolve_region_visit,_commercial_visit_rate | tests/test_engine.py:test_commercial_and_mixed_visit_fees_sum_per_building_and_skip_land_fee | 공식 요구와 현재 근거가 일치 |
| FEE-003 | MATCH | game/engine.py:_resolve_region_visit,_commercial_visit_rate | tests/test_engine.py:test_commercial_and_mixed_visit_fees_sum_per_building_and_skip_land_fee | 공식 요구와 현재 근거가 일치 |
| FEE-004 | MATCH | game/engine.py:_resolve_region_visit,_commercial_visit_rate | tests/test_engine.py:test_commercial_and_mixed_visit_fees_sum_per_building_and_skip_land_fee | 공식 요구와 현재 근거가 일치 |
| RETURN-001 | MATCH | game/engine.py:_effective_industrial_rate,_start_settlement | tests/test_engine.py:test_industrial_rate_clamps_and_mixed_lap_rate_clamps | 공식 요구와 현재 근거가 일치 |
| RETURN-002 | MATCH | game/engine.py:_effective_industrial_rate,_start_settlement | tests/test_engine.py:test_industrial_rate_clamps_and_mixed_lap_rate_clamps | 공식 요구와 현재 근거가 일치 |
| RETURN-003 | PARTIAL | game/engine.py:_effective_industrial_rate,_start_settlement | tests/test_engine.py:test_industrial_rate_clamps_and_mixed_lap_rate_clamps | 세부 범위가 일부만 구현·검증됨 |
| RETURN-004 | MATCH | game/engine.py:_effective_industrial_rate,_start_settlement | tests/test_engine.py:test_industrial_rate_clamps_and_mixed_lap_rate_clamps | 공식 요구와 현재 근거가 일치 |
| SETTLE-001 | MATCH | game/engine.py:_start_settlement | tests/test_engine.py:test_start_settlement_order_tax_bonus_loan_and_ledger_fields | 공식 요구와 현재 근거가 일치 |
| SETTLE-002 | MATCH | game/engine.py:_start_settlement | tests/test_engine.py:test_start_settlement_order_tax_bonus_loan_and_ledger_fields | 공식 요구와 현재 근거가 일치 |
| SETTLE-003 | MISSING | game/engine.py:_start_settlement | — | 세부 범위가 일부만 구현·검증됨 |
| TAX-001 | MATCH | game/engine.py:_tax_rate_bps,_start_settlement | tests/test_engine.py:test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax | 공식 요구와 현재 근거가 일치 |
| TAX-002 | MATCH | game/engine.py:_tax_rate_bps,_start_settlement | tests/test_engine.py:test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax | 공식 요구와 현재 근거가 일치 |
| TAX-003 | MATCH | game/engine.py:_tax_rate_bps,_start_settlement | tests/test_engine.py:test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax | 공식 요구와 현재 근거가 일치 |
| TAX-004 | MATCH | game/engine.py:_tax_rate_bps,_start_settlement | tests/test_engine.py:test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax | 공식 요구와 현재 근거가 일치 |
| TAX-005 | UNRESOLVED | game/engine.py:_tax_rate_bps,_start_settlement | tests/test_engine.py:test_tax_rate_components_include_building_types_undeveloped_and_direct_surtax | user decision required: retain or remove undeveloped-land 0.5%p |
| LOAN-001 | MATCH | game/engine.py:_resolve_emergency_loan,_apply_cash_to_loan,_check_loan_maturity | tests/test_engine.py:test_emergency_loan_exact_limit_duplicate_maturity_and_bankruptcy | 공식 요구와 현재 근거가 일치 |
| LOAN-002 | MATCH | game/engine.py:_resolve_emergency_loan,_apply_cash_to_loan,_check_loan_maturity | tests/test_engine.py:test_emergency_loan_exact_limit_duplicate_maturity_and_bankruptcy | 공식 요구와 현재 근거가 일치 |
| LOAN-003 | CONFLICT | game/engine.py:_resolve_emergency_loan,_apply_cash_to_loan,_check_loan_maturity | tests/test_engine.py:test_emergency_loan_exact_limit_duplicate_maturity_and_bankruptcy | maturity uses current_lap > due_lap instead of the third-start boundary |
| LOAN-004 | MATCH | game/engine.py:_resolve_emergency_loan,_apply_cash_to_loan,_check_loan_maturity | tests/test_engine.py:test_emergency_loan_exact_limit_duplicate_maturity_and_bankruptcy | 공식 요구와 현재 근거가 일치 |
| LOAN-005 | PARTIAL | game/engine.py:_resolve_emergency_loan,_apply_cash_to_loan,_check_loan_maturity | tests/test_engine.py:test_emergency_loan_exact_limit_duplicate_maturity_and_bankruptcy | 세부 범위가 일부만 구현·검증됨 |
| SALE-001 | MATCH | game/engine.py:sell_building,_pay_pending_commercial_refunds | tests/test_engine.py:test_building_sale_rules_by_type_and_commercial_delayed_refund | 공식 요구와 현재 근거가 일치 |
| SALE-002 | MATCH | game/engine.py:sell_building,_pay_pending_commercial_refunds | tests/test_engine.py:test_building_sale_rules_by_type_and_commercial_delayed_refund | 공식 요구와 현재 근거가 일치 |
| SALE-003 | MATCH | game/engine.py:sell_building,_pay_pending_commercial_refunds | tests/test_engine.py:test_building_sale_rules_by_type_and_commercial_delayed_refund | 공식 요구와 현재 근거가 일치 |
| SALE-004 | MATCH | game/engine.py:sell_building,_pay_pending_commercial_refunds | tests/test_engine.py:test_building_sale_rules_by_type_and_commercial_delayed_refund | 공식 요구와 현재 근거가 일치 |
| SPECIAL-001 | MATCH | game/engine.py:_resolve_special_visit,_special_forced_sale,finalize_game | tests/test_engine.py:test_special_region_purchase_external_visit_forced_sale_and_endgame_value | 공식 요구와 현재 근거가 일치 |
| SPECIAL-002 | CONFLICT | game/engine.py:_resolve_special_visit,_special_forced_sale,finalize_game | tests/test_engine.py:test_special_region_purchase_external_visit_forced_sale_and_endgame_value | purchase charges initial value, not accumulated current value |
| SPECIAL-003 | CONFLICT | game/engine.py:_resolve_special_visit,_special_forced_sale,finalize_game | tests/test_engine.py:test_special_region_purchase_external_visit_forced_sale_and_endgame_value | forced sale resets accumulated value |
| SPECIAL-004 | MATCH | game/engine.py:_resolve_special_visit,_special_forced_sale,finalize_game | tests/test_engine.py:test_special_region_purchase_external_visit_forced_sale_and_endgame_value | 공식 요구와 현재 근거가 일치 |
| SPECIAL-005 | MATCH | game/engine.py:_resolve_special_visit,_special_forced_sale,finalize_game | tests/test_engine.py:test_special_region_purchase_external_visit_forced_sale_and_endgame_value | 공식 요구와 현재 근거가 일치 |
| RIGHTS-001 | CONFLICT | game/engine.py:offer_operating_right,respond_operating_right | tests/test_engine.py:test_operating_right_transfer_builds_a_to_b_to_c_to_d_chain_and_operator_gets_income | chain mutation does not reject an existing member |
| RIGHTS-002 | MATCH | game/engine.py:offer_operating_right,respond_operating_right | tests/test_engine.py:test_operating_right_transfer_builds_a_to_b_to_c_to_d_chain_and_operator_gets_income | 공식 요구와 현재 근거가 일치 |
| RIGHTS-003 | MATCH | game/engine.py:offer_operating_right,respond_operating_right | tests/test_engine.py:test_operating_right_transfer_builds_a_to_b_to_c_to_d_chain_and_operator_gets_income | 공식 요구와 현재 근거가 일치 |
| RIGHTS-004 | MATCH | game/engine.py:offer_operating_right,respond_operating_right | tests/test_engine.py:test_operating_right_transfer_builds_a_to_b_to_c_to_d_chain_and_operator_gets_income | 공식 요구와 현재 근거가 일치 |
| USAGE-001 | MATCH | game/engine.py:request_usage_change,respond_usage_change | tests/test_engine.py:test_usage_change_d_request_reorders_chain_after_all_approvals | 공식 요구와 현재 근거가 일치 |
| USAGE-002 | PARTIAL | game/engine.py:request_usage_change,respond_usage_change | tests/test_engine.py:test_usage_change_d_request_reorders_chain_after_all_approvals | 세부 범위가 일부만 구현·검증됨 |
| USAGE-003 | MATCH | game/engine.py:request_usage_change,respond_usage_change | tests/test_engine.py:test_usage_change_d_request_reorders_chain_after_all_approvals | 공식 요구와 현재 근거가 일치 |
| USAGE-004 | MATCH | game/engine.py:request_usage_change,respond_usage_change | tests/test_engine.py:test_usage_change_d_request_reorders_chain_after_all_approvals | 공식 요구와 현재 근거가 일치 |
| RECALL-001 | MATCH | game/engine.py:recall_operating_rights | tests/test_engine.py:test_recall_by_middle_manager_truncates_lower_chain_and_nominal_owner_pays_operator | 공식 요구와 현재 근거가 일치 |
| RECALL-002 | MATCH | game/engine.py:recall_operating_rights | tests/test_engine.py:test_recall_by_middle_manager_truncates_lower_chain_and_nominal_owner_pays_operator | 공식 요구와 현재 근거가 일치 |
| RECALL-003 | MATCH | game/engine.py:recall_operating_rights | tests/test_engine.py:test_recall_by_middle_manager_truncates_lower_chain_and_nominal_owner_pays_operator | 공식 요구와 현재 근거가 일치 |
| TRADE-001 | MATCH | game/engine.py:offer_land_trade,respond_land_trade | tests/test_engine.py:test_land_trade_fixed_price_timeout_acceptance_and_rights_constraints | 공식 요구와 현재 근거가 일치 |
| TRADE-002 | CONFLICT | game/engine.py:offer_land_trade,respond_land_trade | tests/test_engine.py:test_land_trade_fixed_price_timeout_acceptance_and_rights_constraints | current distributed-rights check rejects the allowed consolidation case |
| TRADE-003 | PARTIAL | game/engine.py:offer_land_trade,respond_land_trade | tests/test_engine.py:test_land_trade_fixed_price_timeout_acceptance_and_rights_constraints | 세부 범위가 일부만 구현·검증됨 |
| EVENT-001 | MATCH | game/data_loader.py:_validate_events; game/engine.py:trigger_event,_event_multiplier | tests/test_engine.py:test_event_trigger_from_event_cell_and_chain_uses_json_effects | 공식 요구와 현재 근거가 일치 |
| EVENT-002 | PARTIAL | game/data_loader.py:_validate_events; game/engine.py:trigger_event,_event_multiplier | tests/test_engine.py:test_event_trigger_from_event_cell_and_chain_uses_json_effects | 세부 범위가 일부만 구현·검증됨 |
| EVENT-003 | MATCH | game/data_loader.py:_validate_events; game/engine.py:trigger_event,_event_multiplier | tests/test_engine.py:test_event_trigger_from_event_cell_and_chain_uses_json_effects | 공식 요구와 현재 근거가 일치 |
| EVENT-004 | MATCH | game/data_loader.py:_validate_events; game/engine.py:trigger_event,_event_multiplier | tests/test_engine.py:test_event_trigger_from_event_cell_and_chain_uses_json_effects | 공식 요구와 현재 근거가 일치 |
| EVENT-005 | MATCH | game/data_loader.py:_validate_events; game/engine.py:trigger_event,_event_multiplier | tests/test_engine.py:test_event_trigger_from_event_cell_and_chain_uses_json_effects | 공식 요구와 현재 근거가 일치 |
| EVENT-006 | CONFLICT | game/data_loader.py:_validate_events; game/engine.py:trigger_event,_event_multiplier | tests/test_engine.py:test_event_trigger_from_event_cell_and_chain_uses_json_effects | event multipliers perform intermediate won rounding |
| EVENT-007 | MATCH | game/data_loader.py:_validate_events; game/engine.py:trigger_event,_event_multiplier | tests/test_engine.py:test_event_trigger_from_event_cell_and_chain_uses_json_effects | 공식 요구와 현재 근거가 일치 |
| EVENT-008 | MISSING | game/data_loader.py:_validate_events; game/engine.py:trigger_event,_event_multiplier | — | 세부 범위가 일부만 구현·검증됨 |
| EVENT-009 | MISSING | game/data_loader.py:_validate_events; game/engine.py:trigger_event,_event_multiplier | — | 세부 범위가 일부만 구현·검증됨 |
| EVENT-010 | UNRESOLVED | game/data_loader.py:_validate_events; game/engine.py:trigger_event,_event_multiplier | — | user approval required for the current 20 event cards |
| BANKRUPTCY-001 | MATCH | game/engine.py:declare_bankruptcy,respond_land_takeover | tests/test_engine.py:test_bankruptcy_a_takeover_success_requires_land_price_payment | 공식 요구와 현재 근거가 일치 |
| BANKRUPTCY-002 | MATCH | game/engine.py:declare_bankruptcy,respond_land_takeover | tests/test_engine.py:test_bankruptcy_a_takeover_success_requires_land_price_payment | 공식 요구와 현재 근거가 일치 |
| BANKRUPTCY-003 | PARTIAL | game/engine.py:declare_bankruptcy,respond_land_takeover | tests/test_engine.py:test_bankruptcy_a_takeover_success_requires_land_price_payment | 세부 범위가 일부만 구현·검증됨 |
| BANKRUPTCY-004 | CONFLICT | game/engine.py:declare_bankruptcy,respond_land_takeover | tests/test_engine.py:test_bankruptcy_a_takeover_success_requires_land_price_payment | D takeover collapses the chain instead of producing D→B→C |
| BANKRUPTCY-005 | MATCH | game/engine.py:declare_bankruptcy,respond_land_takeover | tests/test_engine.py:test_bankruptcy_a_takeover_success_requires_land_price_payment | 공식 요구와 현재 근거가 일치 |
| EXIT-001 | MATCH | game/engine.py:_record_action_result,_auto_exit_player | tests/test_engine.py:test_auto_exit_is_distinct_from_bankruptcy_and_cannot_revive | 공식 요구와 현재 근거가 일치 |
| EXIT-002 | MATCH | game/engine.py:_record_action_result,_auto_exit_player | tests/test_engine.py:test_auto_exit_is_distinct_from_bankruptcy_and_cannot_revive | 공식 요구와 현재 근거가 일치 |
| EXIT-003 | PARTIAL | game/engine.py:_record_action_result,_auto_exit_player | tests/test_engine.py:test_auto_exit_is_distinct_from_bankruptcy_and_cannot_revive | 세부 범위가 일부만 구현·검증됨 |
| REVIVE-001 | MATCH | game/engine.py:eligible_for_revival,revive_player | tests/test_engine.py:test_revival_rejects_low_remaining_round_gap_and_max_limit | 공식 요구와 현재 근거가 일치 |
| REVIVE-002 | CONFLICT | game/engine.py:eligible_for_revival,revive_player | tests/test_engine.py:test_revival_rejects_low_remaining_round_gap_and_max_limit | exactly 15 rounds is accepted; official boundary excludes it |
| REVIVE-003 | MATCH | game/engine.py:eligible_for_revival,revive_player | tests/test_engine.py:test_revival_rejects_low_remaining_round_gap_and_max_limit | 공식 요구와 현재 근거가 일치 |
| REVIVE-004 | MATCH | game/engine.py:eligible_for_revival,revive_player | tests/test_engine.py:test_revival_rejects_low_remaining_round_gap_and_max_limit | 공식 요구와 현재 근거가 일치 |
| REVIVE-005 | MATCH | game/engine.py:eligible_for_revival,revive_player | tests/test_engine.py:test_revival_rejects_low_remaining_round_gap_and_max_limit | 공식 요구와 현재 근거가 일치 |
| END-001 | MATCH | game/engine.py:_check_end_condition,finalize_game,_require_not_ended | tests/test_routes.py:test_ended_game_blocks_mutating_routes | 공식 요구와 현재 근거가 일치 |
| END-002 | MATCH | game/engine.py:_check_end_condition,finalize_game,_require_not_ended | tests/test_routes.py:test_ended_game_blocks_mutating_routes | 공식 요구와 현재 근거가 일치 |
| ASSET-001 | MATCH | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | 공식 요구와 현재 근거가 일치 |
| ASSET-002 | MATCH | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | 공식 요구와 현재 근거가 일치 |
| ASSET-003 | MATCH | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | 공식 요구와 현재 근거가 일치 |
| ASSET-004 | MATCH | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | 공식 요구와 현재 근거가 일치 |
| ASSET-005 | MATCH | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | 공식 요구와 현재 근거가 일치 |
| ASSET-006 | UNRESOLVED | game/engine.py:public_wealth,_final_asset_totals,finalize_game | tests/test_engine.py:test_final_assets_split_commercial_without_double_counting_and_exclude_pending_refunds | user approval required for mixed-use final value of zero |
| RANK-001 | MATCH | game/engine.py:_calculate_rankings,_ranking_tie_key | tests/test_engine.py:test_final_ranking_survivors_bankrupts_exited_and_tie_breakers | 공식 요구와 현재 근거가 일치 |
| RANK-002 | PARTIAL | game/engine.py:_calculate_rankings,_ranking_tie_key | tests/test_engine.py:test_final_ranking_survivors_bankrupts_exited_and_tie_breakers | 세부 범위가 일부만 구현·검증됨 |
| PRIV-001 | PARTIAL | game/engine.py:client_public_state,private_state,host_state; game/routes.py | tests/test_routes.py:test_public_private_host_security_and_exports | 세부 범위가 일부만 구현·검증됨 |
| PRIV-002 | MATCH | game/engine.py:client_public_state,private_state,host_state; game/routes.py | tests/test_routes.py:test_public_private_host_security_and_exports | 공식 요구와 현재 근거가 일치 |
| PRIV-003 | MISSING | game/engine.py:client_public_state,private_state,host_state; game/routes.py | — | 세부 범위가 일부만 구현·검증됨 |
| PRIV-004 | MATCH | game/engine.py:client_public_state,private_state,host_state; game/routes.py | tests/test_routes.py:test_public_private_host_security_and_exports | 공식 요구와 현재 근거가 일치 |

## 직접 테스트가 없는 규칙

`EVENT-008`, `EVENT-009`, `EVENT-010`, `PRIV-003`, `SETTLE-003`. `CONFLICT` 경계 테스트는 공식 기대값을 보존하기 위해 검증 파일에서 `xfail`로 관리한다.

## 판정 해석

- `MATCH`: 현재 코드와 테스트 근거가 공식 규칙과 일치한다.
- `PARTIAL`: 일부 동작 또는 경계 검증이 부족하다.
- `MISSING`: 요구된 구현 또는 직접 검증이 없다.
- `CONFLICT`: 현재 동작이 공식 규칙과 다르며 승인 전 자동 수정하지 않는다.
- `UNRESOLVED`: 공식 결정을 위해 사용자 판단이 필요하다.
