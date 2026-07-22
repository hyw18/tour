# TURN_STEP_TIMER_AUDIT

- 작업 전 커밋: `a37a8be8d546985f598a584d006203d88a2f31f7`
- 작업 후 상태: `a37a8be8d546985f598a584d006203d88a2f31f7` 위 working tree 수정본
- 테스트를 실제 실행한 대상: `a37a8be8d546985f598a584d006203d88a2f31f7` 위 working tree 수정본
- 브라우저 테스트: `REAL_CHROMIUM_100_HUMAN_TURNS_PASSED`

## 결론

최신 HEAD의 단계형 턴 시스템은 서버 규칙 단계와 화면 표시 단계를 같은 `turn_step`으로 다루는 경향이 있었다. 특히 `BUILD_DECISION -> BUILD_TYPE_SELECTION -> BUILD_CONFIRMATION`이 각각 별도 제한시간을 받아 한 번의 건설에 시간이 반복 지급될 수 있었고, 단계 timeout마다 `no_action_counts`를 증가시켜 "3회의 무조작 턴" 규칙이 "3개의 무조작 단계"처럼 작동할 위험이 있었다.

이번 작업 후 서버 사용자 입력 단계는 다음으로 정리됐다.

| 흐름 | 서버 단계 | 기본 시간 |
| --- | --- | --- |
| 주사위 | `ROLL_DECISION` | 12초 |
| 토지/특수지역 구매 | `LAND_PURCHASE_DECISION`, `SPECIAL_PURCHASE_DECISION` | 15초 |
| 건설 | `BUILD_DECISION` | 25초 |
| 관리 | `MANAGEMENT_DECISION` | 25초 |
| 거래 작성 | `TRADE_CONFIGURATION` | 30초 |
| 이벤트 확인 | `EVENT_CONFIRMATION` | 20초 |
| 턴 마무리 | `TURN_END_DECISION` | 8초, legacy/fallback only |

건설 모달의 유형 변경, 미리보기, 최종 확인은 같은 `step_sequence` 안의 `client_substep`으로만 기록된다. 같은 모달을 다시 열어도 deadline은 초기화되지 않는다. 추가 행동이 남아 있지 않은 표현 단계는 `TURN_END_DECISION`을 새 입력 단계로 만들지 않고 `_finish_turn`으로 바로 다음 플레이어의 `ROLL_DECISION`을 연다.

## Timeout과 무조작 턴

`turn_activity`를 도입해 단계 timeout과 턴 단위 무조작을 분리했다.

```text
had_valid_user_input
step_timeout_count
automatic_actions
last_valid_input_at
```

단계 timeout은 `step_timeout_count`와 `automatic_actions`만 갱신한다. `no_action_counts`는 턴 종료 시 `had_valid_user_input == false`인 경우에만 최대 1회 증가한다. 정상 구매 포기, 건설 포기, 턴 종료, 구매/건설 확정은 유효 입력으로 기록된다. 자동 주사위, 자동 이벤트 확인, 거래 상대 응답 대기, 서버 표현 단계는 유효 입력으로 기록하지 않는다.

## 입력 상한

기존 `turn_total_limit_seconds`는 실제 의미가 "사용자 입력 누적 상한"이므로 공개 설정에 `turn_input_limit_seconds` 별칭을 추가했다. 현재 서버 처리와 표현 유예를 포함하는 별도 wall-clock 안전 상한은 `turn_wall_clock_safety_limit_seconds: null`로 노출하며, 실제 강제 로직은 아직 도입하지 않았다.

## 재접속 유예

재접속 유예 키를 `(game_instance_id, turn_id, player_id, step_sequence)`로 확장해 같은 단계에서 브라우저/기기/토큰 재사용으로 반복 연장되지 않게 했다.

## 검증

- `.venv/bin/python -m pytest -q`: 244 passed
- `.venv/bin/ruff check .`: passed
- `.venv/bin/flask --app app routes`: passed
- `.venv/bin/python -m compileall app.py game tests`: passed
- `node --check static/js/*.js`: `node` not installed
- QuickJS syntax check for `static/js/host.js` and `static/js/player.js`: syntax passed, stopped only at expected browser globals
- `.venv/bin/python -m pytest tests/test_player_browser.py::test_browser_one_hundred_human_turns_have_no_stale_roll_lock -q -rs`: 1 passed in 135.58s
- `.venv/bin/python -m pytest tests/test_player_browser.py::test_landscape_player_ui_purchase_build_sell_and_refresh -q -rs`: 1 passed in 42.08s
