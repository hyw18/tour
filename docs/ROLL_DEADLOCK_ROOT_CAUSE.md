# ROLL_DEADLOCK_ROOT_CAUSE

- 기준 커밋: `a37a8be8d546985f598a584d006203d88a2f31f7`
- 실행 대상: `a37a8be8d546985f598a584d006203d88a2f31f7` 위 working tree 수정본
- 판정: `BROWSER_LONG_RUN_PASSED`
- 브라우저 장시간 검증: `100_HUMAN_TURNS_REAL_CHROMIUM_PASSED`
- 장시간 서버 검증: `SERVER_300_TURNS_PASSED`

## 첨부 화면과 같은 모순

첨부 화면의 모순은 서버가 새 턴 `ROLL_DECISION`을 열었는데 클라이언트 전역 잠금이 이전 턴 연출 상태를 계속 버튼 disabled 산식에 넣는 구조에서 발생한다.

수정 전 차단 경로:

```js
button.disabled = actionInFlight || animationState.playing || presentationLocked || !rule.allowed;
```

이 구조에서는 다음 상태가 동시에 가능했다.

- 서버: `current_turn_player_id == player_id`
- 서버: `turn_step.step_id == "ROLL_DECISION"`
- 서버: `allowed_actions.roll.allowed == true`
- 클라이언트: `animationState.playing == true`
- 클라이언트: `turnPresentationState.lockReason == "경제 결과를 표시하는 중입니다."`
- 결과: 주사위 버튼 disabled

## 대표 재현 상태

엔진 대표 시나리오:

1. A가 주사위를 굴려 김천 도착
2. A가 토지 구매 경제 action 생성
3. A가 건설을 포기하고 자동 턴 종료
4. B 턴을 종료
5. A의 새 턴이 `ROLL_DECISION`으로 열림

기록된 상태:

```text
game_instance_id: 015bc6a036ed41c2b31f8c4f4ad661d7
current_turn_player_id: human_389ce0129e
turn_id: turn_015bc6a036ed41c2b31f8c4f4ad661d7_3
turn_sequence: 3
turn_step: ROLL_DECISION
step_sequence: 11
turn_has_rolled: false
pending_action: null
allowed_actions.roll.allowed: true
allowed_actions.roll.reason_code: null
allowed_actions.roll.turn_sequence: 3
allowed_actions.roll.step_sequence: 11
allowed_actions.end_turn.allowed: false
previous_economic_action.action_id: econ_015bc6a036ed41c2b31f8c4f4ad661d7_1
previous_economic_action.turn_id: turn_015bc6a036ed41c2b31f8c4f4ad661d7_1
previous_economic_action.turn_sequence: 1
previous_economic_action.step_sequence: 5
```

이전 경제 action과 현재 주사위 턴의 identity가 다르므로, 해당 경제 action은 현재 주사위 입력을 막으면 안 된다.

## 원인

- 버튼 잠금이 서버 `can_roll`보다 클라이언트 전역 `animationState.playing`을 우선했다.
- 경제 animation queue가 `blocking`과 `non-blocking`을 구분하지 않았다.
- `finishPresentation(actionId)`가 action id만 받아 늦게 끝난 이전 턴 presentation과 현재 턴 presentation을 구분하기 어려웠다.
- refresh 중 `animationState.playing || turnPresentationState.inputLocked`이면 최신 snapshot을 `pendingSnapshot`으로 미루는 경로가 있었다.
- `roll_result`에 `turn_id`와 `step_sequence`가 없어, 관전/지연 수신된 봇 주사위 결과가 현재 사람 턴 identity로 정규화될 수 있었다.

## 변경

- `can_roll(player_id)`가 `turn_id`, `turn_sequence`, `step_id`, `step_sequence`, `recoverable`을 반환한다.
- 경제 action에 `game_instance_id`, `turn_id`, `turn_sequence`, `step_sequence`를 기록한다.
- 주사위 결과에도 `game_instance_id`, `turn_id`, `turn_sequence`, `step_sequence`를 기록하고, 클라이언트가 이 identity를 우선 사용한다.
- 클라이언트 `animationTasks` map을 추가하고 task마다 `token`, `turnId`, `turnSequence`, `stepSequence`, `blocking`, `status`, `timeoutMs`를 둔다.
- `hasBlockingAnimationForCurrentTurn()`만 현재 턴 애니메이션 차단 여부를 결정한다.
- 경제 animation은 `blocking:false`로 enqueue된다.
- 버튼 disabled 산식은 `clientLocked || !rule.allowed`로 바뀌었고, `clientLocked`는 현재 턴 request/presentation/animation만 본다.
- `finishPresentation(identity)`가 turn identity를 검증한다.
- 최신 snapshot이 본인 `ROLL_DECISION`이고 서버 `allowed_actions.roll.allowed == true`이면 `clearStaleLocksForRollSnapshot()`과 `convergeCurrentRollDecision()`이 stale lock을 해제한다.
- 주사위 선택 수렴 시 현재 턴과 맞지 않는 blocking queue 항목도 즉시 제거한다.
- `window.getTourDebugState()`에 실제 roll disabled, blocking reason, animation task queue, presentation identity를 노출한다.

## 회귀 테스트

- `tests/test_turn_presentation_contract.py`
  - 전역 `animationState.playing`이 버튼 disabled 산식에 들어가면 실패
  - 경제 animation이 `blocking:false`가 아니면 실패
  - `finishPresentation(identity)`와 ROLL 수렴 watchdog이 없으면 실패
- `tests/test_turn_step_timers.py`
  - 자동 종료 후 다음 플레이어 `ROLL_DECISION`과 `can_roll.allowed == true` 확인
  - 경제 action에 turn identity가 없는 경우 실패
- `tests/test_multiclient_stability.py`
  - 서버 300턴 동안 현재 플레이어 `allowed_actions.roll.allowed`가 false로 남는 경우 실패
- `tests/test_player_browser.py::test_browser_one_hundred_human_turns_have_no_stale_roll_lock`
  - 실제 Chromium에서 사람 1명 + 봇 3명, 100번의 사람 주사위 턴 동안 `currentRollServerAllowed == true`인데 버튼이 비활성/비표시인 상태가 한 번이라도 있으면 실패
  - 현재 턴과 다른 stale blocking animation task, 최종 orphan blocking task, 콘솔 error, 서버 500 응답이 있으면 실패

## 검증 결과

- `.venv/bin/python -m pytest -q`: `244 passed`
- `.venv/bin/ruff check .`: passed
- `.venv/bin/python -m compileall app.py game tests`: passed
- `.venv/bin/flask --app app routes`: passed
- `node --check static/js/player.js`: `node: command not found`
- QuickJS syntax check for `static/js/host.js` and `static/js/player.js`: syntax passed, stopped only at expected browser globals
- `.venv/bin/python -m pytest tests/test_player_browser.py::test_browser_one_hundred_human_turns_have_no_stale_roll_lock -q -rs`: `1 passed in 135.58s`
- `.venv/bin/python -m pytest tests/test_player_browser.py::test_landscape_player_ui_purchase_build_sell_and_refresh -q -rs`: `1 passed in 42.08s`

## 브라우저 증거

로컬 Playwright Chromium은 시스템 `libnspr4/libnss3/libasound2`가 없어 처음에는 실행되지 않았다. 이번 검증에서는 해당 런타임 라이브러리를 `.playwright-libs/root/usr/lib/x86_64-linux-gnu`에 추출하고 `tests/test_player_browser.py`가 존재 시 `LD_LIBRARY_PATH`에 추가하도록 하여 실제 Chromium을 실행했다.

검증된 범위는 1 human + 3 bot 구성, `fast_simulation=true`, 브라우저 animation preference `minimal`, 서버 보조 봇 진행이다. 이 범위에서는 100번의 사람 주사위 턴 동안 버튼 교착, stale blocking lock, orphan blocking lock, 콘솔 에러, 서버 500 응답이 0건이었다.
