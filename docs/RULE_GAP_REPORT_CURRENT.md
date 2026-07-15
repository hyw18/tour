# 최신 코드 기준 규칙 차이 재분석

분석 기준 커밋: `6b34b87` (`main`)  
분석일: 2026-07-15  
공식 규칙 버전: `2026.07.15.1`

이 보고서는 수정 작업을 시작하기 직전 `game/engine.py`, `game/data_loader.py`,
`game/routes.py`, `game/views.py`, 프런트엔드와 테스트를 다시 대조한 결과다.
기존 사전 보고서의 9개 CONFLICT, 10개 PARTIAL, 4개 MISSING은 모두 최신 코드에서도
재현되므로 수정 전 분류 수는 변경하지 않는다.

| 분류 | 수정 전 개수 |
|---|---:|
| MATCH | 78 |
| PARTIAL | 10 |
| MISSING | 4 |
| CONFLICT | 9 |
| UNRESOLVED | 3 |
| 합계 | 104 |

## 재확인한 CONFLICT

| 규칙 | 최신 코드 근거 | 재분석 결과 |
|---|---|---|
| PAUSE-001 | `GameEngine.pause`, `resume`; 요청별 `created_at` | 재개 시 요청 시각을 보정하지 않아 정지 시간이 만료시간에 포함된다. |
| LOAN-003 | `_check_loan_maturity` | `current_lap > due_lap`이어서 네 번째 출발지까지 유예된다. |
| SPECIAL-002 | `purchase_special_region` | 구매가가 최초가다. |
| SPECIAL-003 | `_resolve_special_arrival` | 강제매각 후 누적가를 최초가로 초기화한다. |
| RIGHTS-001 | `create_ownership_chain`, `respond_operating_right_transfer` | 중복 player ID 검증이 없다. |
| TRADE-002 | `propose_land_trade` | 명목 소유자를 외부 권리자로 함께 세어 허용된 통합 거래를 거부한다. |
| EVENT-006 | `_event_multiplier_bps` | 효과마다 정수 bps로 중간 반올림한다. |
| BANKRUPTCY-004 | `respond_land_takeover` | D 인수 시 기존 B·C 상대 순서를 보존하지 못한다. |
| REVIVE-002 | `_can_revive` | `< 15`를 사용해 정확히 15를 허용한다. |

## 재확인한 PARTIAL

- MONEY-002: 일반 금액 반올림은 일치하지만 이벤트 배율 합성은 중간 반올림한다.
- RETURN-003: `industrial_return_explicit_override`가 전역 상태에 잔류한다.
- LOAN-005: 출발지 자동상환만 있고 모든 현금 유입 공통 경로가 없다.
- USAGE-002: 요청 전체가 단일 타이머를 공유한다.
- TRADE-003: 권리 통합 거래가 막혀 거래 후 체인 정규화가 완전하지 않다.
- EVENT-002: 일부 metric은 로드되지만 경제 계산 소비처가 없다.
- BANKRUPTCY-003: 엔진 응답은 있으나 사람 플레이어용 완전한 응답 정보·UI 흐름이 부족하다.
- EXIT-003: 유효 입력이 공통 활동 기록 함수로 통합되지 않았다.
- RANK-002: 플레이어 ID 기반 1회 난수이며 재굴림과 로그가 없다.
- PRIV-001: 공개 응답 범위가 공식 공개 목록보다 넓다.

## 재확인한 MISSING

- SETTLE-003: 동일 정산 식별자에 대한 결과 캐시와 동시 실행 차단이 없다.
- EVENT-008: 지역·산업·연쇄 이벤트 참조의 의미 검증이 불완전하다.
- EVENT-009: 이벤트 연쇄 그래프 순환 검증이 없다.
- PRIV-003: 호스트 기본 뷰에 전체 게임 로그가 없다.

## 변경 금지 UNRESOLVED

- TAX-005: 미개발 토지 0.5%p
- EVENT-010: 현재 이벤트 카드 공식 승인 여부
- ASSET-006: 복합 건물 최종 정산가 0원 확정 여부

위 세 동작은 이번 수정에서 유지하며 문서와 화면에 결정 대기 상태를 표시한다.
