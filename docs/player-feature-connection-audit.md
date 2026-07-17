# player-feature-connection-audit

- 작업 전 커밋: `d0fa8bf2f4bfa7a5d99eeb35dbdda62c92123dd3`
- 작업 후 커밋: `UNCOMMITTED_WORKTREE`
- 테스트를 실제 실행한 커밋: `d0fa8bf2f4bfa7a5d99eeb35dbdda62c92123dd3` + working tree changes
- 브라우저 테스트를 실행한 커밋: `ATTEMPTED_SKIPPED_LIBNSPR4_MISSING`

## 플레이어 연결 상태

플레이어는 `/api/player/<player_id>/private`에서 현재 단계, 남은 시간, 전체 선택시간, 마지막 timeout 메시지를 받는다. `last_step_timeout`은 같은 `step_sequence` 메시지를 중복 표시하지 않도록 클라이언트에서 관찰한다.

## UI 변경

상단 타이머는 긴 내부 단계명 대신 사용자용 이름을 표시한다.

- `BUILD_CONFIRMATION` -> 건물 건설
- `MANAGEMENT_DECISION` -> 자산 관리
- `TURN_END_DECISION` -> 턴 마무리

진행 표시기는 내부 서버 단계를 아래 흐름으로 묶는다.

```text
이동 -> 도착 -> 행동 선택 -> 턴 마무리
```

## 연결/재접속

재접속 유예는 같은 게임, 같은 턴, 같은 플레이어, 같은 step sequence에서 한 번만 적용된다. 다른 브라우저나 같은 reconnect token 반복 요청도 같은 키를 공유한다.

## 남은 검증

- Android Chrome: REAL_DEVICE_TEST_REQUIRED
- Samsung Internet: REAL_DEVICE_TEST_REQUIRED
- iOS Safari: REAL_DEVICE_TEST_REQUIRED
- 네트워크 전환 후 유예 1회: UNIT_TESTED, REAL_DEVICE_TEST_REQUIRED
- 좁은 가로 화면 타이머/현금 겹침: REAL_DEVICE_TEST_REQUIRED
- Playwright Chromium: ATTEMPTED, skipped because `libnspr4.so` is missing
