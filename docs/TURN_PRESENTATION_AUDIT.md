# TURN_PRESENTATION_AUDIT

- 작업 전 커밋: `d7dc9d26deebd464fda0f44c78f77b0c7b9f2647`
- 작업 후 커밋: `UNCOMMITTED_WORKTREE`
- 테스트를 실제 실행한 커밋: `d7dc9d26deebd464fda0f44c78f77b0c7b9f2647` + working tree changes
- 브라우저 테스트를 실행한 커밋: `ATTEMPTED_SKIPPED_LIBNSPR4_MISSING`

## 서버 단계와 화면 장면

서버의 공식 단계는 `turn_step`이 계속 담당한다. 사용자 입력 가능 여부, deadline, timeout action, allowed actions는 서버 모델이다.

클라이언트 표현은 별도 의미로 묶었다.

| 화면 묶음 | 포함 단계 |
| --- | --- |
| 이동 | `ROLL_RESOLUTION` |
| 도착 | `ARRIVAL_PRESENTATION`, `SETTLEMENT_PRESENTATION`, `RESULT_CONFIRMATION` |
| 행동 선택 | 구매, 건설, 관리, 거래, 이벤트 확인 |
| 턴 마무리 | `TURN_END_DECISION`, `TURN_COMPLETE` |

플레이어 상단 타이머는 `BUILD_CONFIRMATION` 같은 내부 단계명을 직접 표시하지 않고 `건물 건설`, `자산 관리`, `턴 마무리`처럼 묶은 이름을 표시한다. 진행 표시기는 서버가 실제로 내려준 단계만 표시하며, 클라이언트가 `TURN_END_DECISION`을 임의로 덧붙이지 않는다.

## 결과 확인 중복

현재 서버는 `RESULT_CONFIRMATION`을 비입력 표현 단계로 유지한다. 결과 표현 뒤 남은 행동이 턴 종료뿐이면 `complete_turn_presentation`이 즉시 다음 플레이어 턴으로 넘긴다. 따라서 비용 없는 칸, 구매 포기, 건설 포기, 출발지 정산, 방문료 처리처럼 추가 선택지가 없는 흐름은 별도 "턴 종료" 클릭을 요구하지 않는다.

서버 공개 상태의 `turn_completion_policy`는 현재 단계가 `auto_end`, `manual_end`, `continue_to_decision` 중 어떤 종료 정책인지 알려준다. `MANAGEMENT_DECISION`처럼 실제 추가 행동이 가능한 단계에서만 수동 종료 버튼이 허용된다.

## 최신 스냅샷 보호

플레이어 클라이언트는 `game_instance_id`, `state_version`, `turn_sequence`, `step_sequence`를 비교해 오래된 snapshot을 렌더링하지 않는다. 이전 턴 또는 이전 단계 응답이 늦게 도착해도 최신 턴의 주사위 버튼 상태를 덮어쓰지 않도록 보호한다.

## Timeout 안내

timeout 메시지는 원인, 자동 처리, 다음 단계를 포함하도록 바뀌었다.

- 주사위 선택 시간이 끝나 자동으로 굴렸습니다. 도착 칸을 확인하세요.
- 토지 구매 시간이 끝나 구매하지 않았습니다. 턴 마무리로 이동합니다.
- 건설 시간이 끝나 이번 방문에는 건설하지 않습니다. 턴 마무리로 이동합니다.
- 관리 선택 시간이 끝나 턴 마무리로 이동합니다.
- 턴 마무리 시간이 끝나 자동으로 종료했습니다.

## Backlog

공개 상태에는 아직 `presentation_backlog` 수치가 없다. 현재 경제 애니메이션 커서는 플레이어별로 존재하지만 서버 턴 sequence와 최신 표시 턴 sequence의 차이를 직접 계산하는 필드는 후속 작업이 필요하다.
