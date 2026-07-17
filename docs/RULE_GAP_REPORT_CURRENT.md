# RULE_GAP_REPORT_CURRENT

- 작업 전 커밋: `d0fa8bf2f4bfa7a5d99eeb35dbdda62c92123dd3`
- 작업 후 커밋: `UNCOMMITTED_WORKTREE`
- 테스트를 실제 실행한 커밋: `d0fa8bf2f4bfa7a5d99eeb35dbdda62c92123dd3` + working tree changes
- 브라우저 테스트를 실행한 커밋: `NOT_RUN_NODE_NOT_INSTALLED`

## 해결됨

| 항목 | 상태 | 근거 |
| --- | --- | --- |
| 단계 timeout과 무조작 턴 분리 | RESOLVED | `GameState.turn_activity`, `tests/test_turn_step_timers.py` |
| 건설 3단계 시간 반복 | RESOLVED | 건설 서버 입력 단계는 `BUILD_DECISION` 하나, 모달 변화는 `client_substep` |
| 단계 재접속 유예 반복 | RESOLVED | 유예 키에 `game_instance_id + turn_id + player_id + step_sequence` 사용 |
| 옛 숨은 타이머 제출 | RESOLVED | 호스트 UI에서 hidden `turnLimit` 제거, `legacy_turn_limit_seconds`로 호환 |
| timeout 메시지 모호함 | RESOLVED | 단계별 한국어 자동 처리 메시지 |

## 부분 해결

| 항목 | 상태 | 남은 일 |
| --- | --- | --- |
| 서버 단계와 클라이언트 장면 분리 | PARTIAL | 화면 표시 묶음은 분리했지만 독립 `ClientPresentationScene` 데이터 모델은 없음 |
| 결과 확인/턴 종료 중복 | PARTIAL | 단순 결과는 비입력 표현 단계지만 중요 결과의 `next_step_behavior` 명시 필드는 없음 |
| 전체 wall-clock 안전 상한 | PARTIAL | 공개 필드는 추가했으나 강제 로직은 없음 |
| 봇 presentation backlog | PARTIAL | 정책은 문서화했지만 `presentation_backlog` API 필드는 없음 |

## UNRESOLVED

다음 공식 규칙은 임의 확정하지 않았다.

- 미개발 토지세 0.5%p
- 이벤트 카드 공식 승인
- 복합 건물 최종 정산가
- 실제 기기 UX 검증
