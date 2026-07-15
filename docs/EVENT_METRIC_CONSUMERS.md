# 이벤트 metric 소비처 대응표

| metric | 실제 계산 소비처 | scope 입력 | 효과 |
|---|---|---|---|
| building_market_value | `GameEngine._adjusted_building_value_fraction` | 최종 운영자, 건물 지역 | 건물 기준 시세 배율 |
| commercial_visit_rate | `GameEngine._building_visit_fee_rate_fraction` | 최종 운영자, 방문 지역 | 상업·복합 방문료율 배율·가산 |
| industrial_return_rate | `GameEngine._adjusted_industrial_rate_bps` | 최종 운영자, 건물 지역 | 산업·복합 수익률 가산·override |
| building_tax_rate | `GameEngine._calculate_tax_rate_bps` | 납세자, 건물 지역 | 건물 세율 가산 |
| cumulative_tax_rate | `GameEngine._calculate_tax_rate_bps` | 납세자, 관련 범위 | 누적 세율 가산 |
| economic_growth | `GameEngine._adjusted_industrial_rate_bps` | 최종 운영자, 건물 지역 | 전국 경제 배율을 산업 기준 수익률에 적용 |
| trade_balance | `GameEngine._adjusted_industrial_rate_bps` | 최종 운영자, 건물 지역 | 개인·지역·전국 범위의 무역 배율 적용 |
| regional_economy | `GameEngine._adjusted_industrial_rate_bps` | 최종 운영자, 건물 지역 | 해당 지역 산업 기준 수익률 배율 |
| industry_cycle | `GameEngine._adjusted_industrial_rate_bps` | 최종 운영자, 건물 지역 | 산업 경기 배율 적용 |

`personal` 이벤트는 대상 플레이어가 계산 입력과 일치할 때만, `regional` 이벤트는
대상 지역이 계산 입력과 일치할 때만 적용된다. `nationwide`는 모든 해당 계산에 적용된다.
소비처가 없는 metric은 현재 허용 목록에 없다.
