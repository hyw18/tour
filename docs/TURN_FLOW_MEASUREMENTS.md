# TURN_FLOW_MEASUREMENTS

- 작업 전 커밋: `d7dc9d26deebd464fda0f44c78f77b0c7b9f2647`
- 작업 후 커밋: `UNCOMMITTED_WORKTREE`
- 테스트를 실제 실행한 커밋: `d7dc9d26deebd464fda0f44c78f77b0c7b9f2647` + working tree changes
- 브라우저 테스트를 실행한 커밋: `ATTEMPTED_SKIPPED_LIBNSPR4_MISSING`

측정 방식: 엔진 단위 시나리오와 테스트 계약을 기준으로 서버 step sequence, 부여 시간, 클릭 수를 계측했다. 실제 브라우저 애니메이션 시간과 콘솔 오류 검증은 `node` 부재와 Playwright Chromium의 `libnspr4.so` 의존성 부재로 수행하지 못했다.

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
| 봇 3명 연속 턴 | 서버 봇 전략 실행 | 사용자 입력 없음 | 0 | 봇 자동 실행 | 중요 결과만 표시 필요 | bot delay 설정 의존 | NOT_BROWSER_MEASURED |

## 관찰

- 단순 행동은 결과 확인 클릭을 추가로 요구하지 않는다.
- 추가 행동지가 없는 턴은 별도 턴 종료 클릭 없이 서버가 자동 종료한다.
- 건설은 한 서버 입력 단계 안에서 유형 선택과 최종 확인을 처리한다.
- 단계 timeout만으로는 `no_action_counts`가 증가하지 않는다.
- 브라우저 애니메이션 중 선택시간 손실은 Playwright/실기기 환경에서 추가 검증이 필요하다.
