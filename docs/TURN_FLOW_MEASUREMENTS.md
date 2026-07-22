# TURN_FLOW_MEASUREMENTS

- 작업 전 커밋: `a37a8be8d546985f598a584d006203d88a2f31f7`
- 작업 후 상태: `a37a8be8d546985f598a584d006203d88a2f31f7` 위 working tree 수정본
- 테스트를 실제 실행한 대상: `a37a8be8d546985f598a584d006203d88a2f31f7` 위 working tree 수정본
- 브라우저 테스트: `REAL_CHROMIUM_100_HUMAN_TURNS_PASSED`

측정 방식: 엔진 단위 시나리오와 테스트 계약을 기준으로 서버 step sequence, 부여 시간, 클릭 수를 계측했다. 추가로 실제 Chromium에서 1 human + 3 bot 구성으로 사람 주사위 턴 100회를 실행해 서버 주사위 허용과 브라우저 버튼 활성 상태가 어긋나지 않는지 검증했다.

| 시나리오 | step_id 순서 | 부여 시간 | 사용자 클릭 수 | 자동 단계 | 결과 확인 | 총 경과시간 | 서버/화면 최대 차이 |
| --- | --- | --- | ---: | --- | ---: | --- | --- |
| 비용 없는 칸 | `ROLL_DECISION -> ARRIVAL_PRESENTATION -> next ROLL_DECISION` | 12초 | 1 | 도착 표현 뒤 자동 턴 종료 | 0 | 입력 기준 최대 12초 | NOT_BROWSER_MEASURED |
| 무주 일반지역 구매 포기 | `ROLL_DECISION -> ARRIVAL_PRESENTATION -> LAND_PURCHASE_DECISION -> RESULT_CONFIRMATION -> next ROLL_DECISION` | 12초, 15초 | 2 | 결과 표현 뒤 자동 턴 종료 | 0 | 입력 기준 최대 27초 | NOT_BROWSER_MEASURED |
| 토지 구매 후 건설하지 않기 | `ROLL_DECISION -> ARRIVAL_PRESENTATION -> LAND_PURCHASE_DECISION -> RESULT_CONFIRMATION -> BUILD_DECISION -> RESULT_CONFIRMATION -> next ROLL_DECISION` | 12초, 15초, 25초 | 3 | 결과 표현 뒤 자동 턴 종료 | 0 | 입력 기준 최대 52초 | NOT_BROWSER_MEASURED |
| 토지 구매 후 건물 건설 | 위와 같고 `BUILD_DECISION` 안에서 확인 | 12초, 15초, 25초 | 3~4 | 결과 표현 뒤 자동 턴 종료 | 0 | 입력 기준 최대 52초 | NOT_BROWSER_MEASURED |
| 내 토지에서 관리하지 않고 종료 | `ROLL_DECISION -> ARRIVAL_PRESENTATION -> MANAGEMENT_DECISION -> next ROLL_DECISION` | 12초, 25초 | 2 | 도착 표현 | 0 | 입력 기준 최대 37초 | NOT_BROWSER_MEASURED |
| 내 토지에서 건물 매각 | `ROLL_DECISION -> ARRIVAL_PRESENTATION -> MANAGEMENT_DECISION -> RESULT_CONFIRMATION -> next ROLL_DECISION` | 12초, 25초 | 2~3 | 결과 표현 뒤 자동 턴 종료 | 0 | 입력 기준 최대 37초 | NOT_BROWSER_MEASURED |
| 타인 상업지역 방문 | `ROLL_DECISION -> ARRIVAL_PRESENTATION -> next ROLL_DECISION` | 12초 | 1 | 방문료 경제 애니메이션 뒤 자동 턴 종료 | 0 | 입력 기준 최대 12초 | NOT_BROWSER_MEASURED |
| 특수지역 구매 | `ROLL_DECISION -> ARRIVAL_PRESENTATION -> SPECIAL_PURCHASE_DECISION -> RESULT_CONFIRMATION -> next ROLL_DECISION` | 12초, 15초 | 2 | 결과 표현 뒤 자동 턴 종료 | 0 | 입력 기준 최대 27초 | NOT_BROWSER_MEASURED |
| 특수지역 강제매각 | `ROLL_DECISION -> ARRIVAL_PRESENTATION -> RESULT_CONFIRMATION -> next ROLL_DECISION` | 12초 | 1 | 강제매각 경제 애니메이션 뒤 자동 턴 종료 | 1 | 입력 기준 최대 12초 | NOT_BROWSER_MEASURED |
| 이벤트 | `ROLL_DECISION -> ARRIVAL_PRESENTATION -> EVENT_CONFIRMATION -> next ROLL_DECISION` | 12초, 20초 | 2 | 이벤트 확인 뒤 자동 턴 종료 | 1 | 입력 기준 최대 32초 | NOT_BROWSER_MEASURED |
| 출발지 정산 | `ROLL_DECISION -> SETTLEMENT_PRESENTATION -> next ROLL_DECISION` | 12초 | 1 | 정산 표현 뒤 자동 턴 종료 | 1 | 입력 기준 최대 12초 | NOT_BROWSER_MEASURED |
| 긴급대출 | 서비스 처리 + 결과 표현 | 공식 응답시간 별도 | 상황 의존 | 경제 애니메이션 | 1 | NOT_BROWSER_MEASURED | NOT_BROWSER_MEASURED |
| 파산 | 파산 판정 + 인수/부활 단계 | 15초 내외 | 상황 의존 | 파산 처리 | 1 | NOT_BROWSER_MEASURED | NOT_BROWSER_MEASURED |
| 부활 | `REVIVAL_DECISION` | 15초 | 1 | 없음 | 1 | 입력 기준 최대 15초 | NOT_BROWSER_MEASURED |
| 거래 제안과 응답 | `MANAGEMENT_DECISION -> TRADE_CONFIGURATION -> TRADE_RESPONSE -> RESULT_CONFIRMATION` | 25초, 30초, 공식 10초 | 2~3 | 상대 응답 대기 | 1 | 입력 기준 55초 + 공식 10초 | NOT_BROWSER_MEASURED |
| 봇 3명 연속 턴 뒤 사람 주사위 | 서버 봇 전략 실행 뒤 `ROLL_DECISION` | 사용자 입력 없음 + 12초 | 1 | 봇 자동 실행 | 중요 결과만 표시 | 100회 사람 턴 실브라우저 통과 | 0건 |

## 관찰

- 단순 행동은 결과 확인 클릭을 추가로 요구하지 않는다.
- 추가 행동지가 없는 턴은 별도 턴 종료 클릭 없이 서버가 자동 종료한다.
- 건설은 한 서버 입력 단계 안에서 유형 선택과 최종 확인을 처리한다.
- 단계 timeout만으로는 `no_action_counts`가 증가하지 않는다.
- 실브라우저 100회 사람 주사위 턴에서 `currentRollServerAllowed == true`인데 버튼이 disabled/hidden인 상태, stale blocking task, orphan blocking task, 콘솔 error, 서버 500 응답은 0건이었다.
