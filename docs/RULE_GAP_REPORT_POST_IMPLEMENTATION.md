# 최신 HEAD 보완 후 검증 보고서

- 분석 기준 HEAD: `5cf5b6a8edd0ac27f40efb262cec87cea381107c`
- 검증일: 2026-07-16
- 공식 규칙 버전: `2026.07.16.1`

## 검증 상태

| 기능 | 상태 | 최신 작업 트리 근거 |
|---|---|---|
| 멱등 키 누락·공백·길이·문자 거부 | UNIT_TESTED | `tests/test_latest_head_audit.py` |
| 동일 논리 요청 네트워크 재시도 키 유지 | UNIT_TESTED | 공통 `postJson` 계약 검사 |
| 동일 키 100회·payload 충돌·게임별 범위 | MULTI_CLIENT_TESTED | `tests/test_multiclient_stability.py` 재실행 |
| 건설 및 위험 행동 확인 단계 | UNIT_TESTED | 공통 모달·상태 버전·focus trap 계약 |
| 거래 제안·수락·거절·만료 구분 | UNIT_TESTED | 엔진 request domain event와 무결제 거절 테스트 |
| 출발지 정산 결과 순서 | UNIT_TESTED | 서버 settlement event 순서 테스트 |
| 이벤트 제목·진행률·현재 효과 | UNIT_TESTED | 서버 계산값과 내부 ID 비노출 테스트 |
| 경제 시퀀스·커서·재접속 생략 정책 | UNIT_TESTED | unread/ack/reconnect 경계 테스트 |
| 관련 자산만 강조·삭제 흐림 | UNIT_TESTED | data 식별자와 선택자 계약 테스트 |
| 실제 브라우저 UI | BROWSER_TESTED | 임시 공유 라이브러리 경로로 Chromium 실행 |
| 서버 제공 다음 행동·우선순위 | BROWSER_TESTED | `next_action_message`, `action_priority`, 호스트 1·플레이어 4 Chromium |
| 현재 도착비용 식별 | UNIT_TESTED | action/turn/arrival/state 식별자 불일치 비용 제외 |
| 독립 재무 탭·관리 전환 | BROWSER_TESTED | 네 개 `tabpanel`, 스크롤 보존, 모달 닫기 후 포커스 이동 |
| 모바일 비활성 사유 | BROWSER_TESTED | 다른 행동 목록의 탭 가능한 사유 버튼과 status 패널 |
| 턴 장면·입력 잠금 | BROWSER_TESTED | 주사위→이동→도착→요약 순서와 3.276초 입력 활성화 계측 |
| 이벤트 연출 시간 제외 | UNIT_TESTED | 뒤집기·확인 요청 제외, 공개 후 읽기 시간 정상 경과 |
| 출발지 단계 정산 | UNIT_TESTED | 8개 `settlement_steps` 순서와 전후 현금·수익·지출 요약 |

## 이번 실행 결과

- `pytest -q`: `224 passed` (Chromium 공유 라이브러리를 임시 경로로 제공)
- `ruff check .`: 통과
- `python -m compileall .`: 통과
- `flask --app app routes`: 통과
- `node --check static/js/*.js`: Node 실행 파일 부재로 실행 불가
- QuickJS 대체 구문 컴파일: `common.js`, `host.js`, `player.js` 통과
- `git diff --check`: 통과
- Playwright: `/tmp`에 `libnspr4`, `libnss3`, `libasound`를 비권한 방식으로 풀어 실행한 별도 검증 통과. 호스트 1·플레이어 4, 콘솔 오류 0, HTTP 500 0. 무주 토지 도착은 서버 13ms, 입력 활성화 3,276ms로 계측됐다.

## 남은 검증

- 이벤트·출발지 정산·거래·강제매각·긴급대출·파산까지 이어지는 장시간 브라우저 시나리오
- Android Chrome, Samsung Internet, iOS Safari/WebKit에서 모달 포커스·뒤로가기·회전
- 네트워크 전환·백그라운드 복귀·300라운드 발열 및 프레임 저하
- 자산 패널 스크롤 위치와 소프트 키보드 가림 여부
- UNRESOLVED: TAX-005, EVENT-010, ASSET-006
