# 한 턴 단계 분리 및 단계별 제한시간 감사

- 분석 기준 main HEAD: `5cf5b6a8edd0ac27f40efb262cec87cea381107c`
- 구현·검증일: 2026-07-17

## 기존 단일 타이머

기존 서버는 `_start_turn()`에서 `turn_started_at`을 한 번 기록하고
`elapsed_turn_seconds()`를 주사위 선택부터 최종 턴 종료까지 계속 증가시켰다. 따라서 서버
주사위 계산, 클라이언트 주사위·이동·도착·경제 연출, 구매·건설 판단이 같은 제한시간을
소비했다. 호스트 일시중지는 `turn_elapsed_before_pause`로 보정했고, 토지·운영권 거래는
제안자의 턴 시계를 별도로 멈췄다. 거래·용도 변경 승인·파산 인수는 각 요청의
`created_at` 또는 `approver_started_at`을 기준으로 10초를 계산했다. 전체 턴 만료는
무행동 횟수를 증가시키고 바로 다음 플레이어로 넘겼다.

## 서버 단계 모델

`GameState.turn_step`은 `turn_id`, `step_id`, `step_sequence`, `player_id`, `label`,
`started_at`, `deadline_at`, `duration_seconds`, `timeout_action`,
`user_input_required`, `status`를 가진다. 서버가 유일한 deadline 기준이며 클라이언트에는
계산된 `remaining_seconds`와 `turn_total_remaining_seconds`를 제공한다. 동일 step을 다시
요청하면 기존 객체를 반환하므로 모달 재열기, 폴링, 새로고침, 재접속, 멱등 재전송은
시간을 초기화하지 않는다.

핵심 흐름은 다음과 같다.

`ROLL_DECISION → ROLL_RESOLUTION → ARRIVAL_PRESENTATION/SETTLEMENT_PRESENTATION →
도착별 선택 → RESULT_CONFIRMATION → TURN_END_DECISION → TURN_COMPLETE`

무주지는 `LAND_PURCHASE_DECISION`, 구매 성공 후 `BUILD_DECISION`, 본인 토지는
`MANAGEMENT_DECISION`, 건설 UI는 `BUILD_TYPE_SELECTION → BUILD_CONFIRMATION`, 거래 작성은
`TRADE_CONFIGURATION`, 이벤트 공개 후에는 `EVENT_CONFIRMATION`을 사용한다. 거래·용도
변경 응답은 각각 `TRADE_RESPONSE`, `USAGE_CHANGE_RESPONSE`로 표시하지만 공식 10초
요청 시계를 그대로 사용하며 현재 턴의 누적 선택시간에는 포함하지 않는다.

## 기본 제한시간과 전체 상한

| 단계 | 기본 |
|---|---:|
| 주사위 | 15초 |
| 토지·특수지역 구매 | 15초 |
| 건설 여부 | 20초 |
| 건물 유형·확인 | 각 20초 |
| 관리 | 25초 |
| 거래 작성 | 30초 |
| 이벤트 확인 | 15초 |
| 턴 종료 | 10초 |

프리셋은 빠름(단순 10초·복잡 15초·전체 60초), 기본(전체 120초), 여유(단순
25초·복잡 40초·전체 180초), 직접 설정, 무제한이다. 전체 상한은 사용자 입력 단계에서
경과한 시간만 누적한다. 서버 계산, 연출, 거래 상대 응답, 일시중지와 빠른 시뮬레이션은
제외한다.

## timeout과 자동 퇴장

- 주사위: 서버 자동 주사위
- 토지·특수지역 구매: 구매 포기
- 건설 여부·유형·확인: 건설하지 않음; 유형 자동 선택 금지
- 관리·거래 작성: 해당 행동 없이 턴 종료 단계로 이동
- 이벤트: 확인 처리 후 턴 종료 단계로 이동
- 턴 종료: 자동 종료
- 전체 상한: pending과 미완료 거래를 정리하고 턴 종료

사용자 선택 단계 timeout은 `no_action_count`를 1 증가시킨다. 자동 단계, 서버 오류,
거래 상대 응답 대기는 증가시키지 않는다. 기존 `EVENT-011`에 따라 이벤트 확인 timeout은
자동 퇴장 횟수로 남기지 않는다. 정상 포기와 정상 행동은 활동으로 기록된다. 모든 timeout은
`step_timeout` 또는 `turn_total_timeout` 구조화 로그와 사용자 메시지를 남기며, 전역 잠금과
step sequence 변화로 동시 timeout도 한 번만 적용된다.

## 일시중지·재접속·봇

호스트 일시중지는 단계의 `started_at`·`deadline_at`, 전체 누적시간, 거래·승인 요청
시각을 함께 보정한다. 일반 새로고침은 유예나 초기화를 만들지 않는다. 호스트가 선택한
경우에만 새 세션의 토큰 재접속에 5초 또는 10초를 같은 단계에서 한 번 제공하며 사용
기록을 남긴다. 기본값은 악용을 피하기 위해 0초다.

봇은 사람과 같은 `turn_step` 전환 메서드를 사용하지만 전략을 즉시 실행하므로 timeout에
의존하지 않는다. 일반 게임의 화면 pacing만 클라이언트에서 적용하고 빠른 시뮬레이션은
모든 단계 deadline과 표현 대기를 생략한다.

## UI와 검증

상단 타이머는 `단계명 · 남은 단계 시간 · 전체 최대 남은 시간`을 표시한다. 자동 단계는
`제한시간 정지`, 10초 이하는 주의, 5초 이하는 긴급 상태다. 단계 표시기는 이번 턴에 실제로
거친 단계만 완료·현재·예정 상태로 표시한다.

엔진 테스트는 단계 생성, 자동 단계 정지, 구매·건설 새 시간, 모달·새로고침 deadline
보존, 안전 timeout, 자동 주사위, 전체 상한, 일시중지, 프리셋, 봇·빠른 시뮬레이션,
동시 timeout, 한 단계당 1회 재접속 유예를 검사한다. Chromium 테스트는 단계명,
연출 중 정지 문구, 구매 단계, 건설 확인 단계, 구매 모달 재열기 deadline 보존과 기존
호스트 1·플레이어 4 흐름을 검증했다.

## 남은 실기기 조정

Android Chrome, Samsung Internet, iOS Safari에서 좁은 가로 화면의 긴 단계명, 5초
긴급 색상 인지성, 백그라운드 복귀 직후 서버 보정 체감을 확인해야 한다. 파산 토지 인수와
부활은 현재도 독립 공식 요청/자격 규칙을 사용하며, 여러 플레이어의 별도 요청을 하나의
`turn_step`에 합치지 않았다. 장시간 이벤트·거래·파산 실기기 시나리오는 후속 검증 항목이다.
