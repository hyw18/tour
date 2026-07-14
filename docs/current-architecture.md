# 1단계 기반 구조 분석 기준선

이 문서는 변경 전 커밋 `54f4e5d`를 기준으로 작성했다. 게임 규칙과 경제 수치는
`tests/test_engine.py`의 70여 개 규칙 테스트가 고정한다.

## 파일과 책임

- `app.py`: Flask 앱 팩토리, 전역 엔진 생성, 서버 실행.
- `game/models.py`: 플레이어, 호스트 설정, 모든 런타임 상태와 상수.
- `game/engine.py`: 턴, 이동, 자산, 경제, 이벤트, 파산, 봇, 시뮬레이션,
  결과/응답 직렬화까지 담당하는 단일 조정자.
- `game/routes.py`: 페이지/API, 권한 검사, 멱등성 래퍼, 개발 도구.
- `game/data_loader.py`: JSON/스키마 로딩과 교차 파일 불변식 검증.
- `game/economy.py`: 원화 타입/비율/5만원 단위 반올림.
- `game/bots.py`: 자동 봇 반복과 명목상 행동 선택기. 실제 투자 판단은 엔진에 있음.
- `templates`, `static`: 호스트/플레이어 UI와 폴링 클라이언트.
- `scripts/final_validation.py`: 대량 규칙 검증 스크립트.
- `tests`: 엔진 규칙 및 HTTP 회귀 테스트.

## GameEngine 책임

설정/로비, 턴 수명주기, 주사위/이동/도착 처리, 토지와 건물, 특수지역,
토지 거래, 운영권 체인과 용도 변경, 원장/세금/대출/정산, 이벤트, 파산/퇴장/
부활, 봇 투자와 자동 진행, 대량 시뮬레이션, 최종 자산/순위/내보내기,
public/host/private 응답 직렬화를 모두 포함했다.

## GameState 상태 묶음

- 로비: `config`, `players`, `phase`, `created_at`
- 턴: current index/round, pause/end, turn clocks, dice, activity, pending action
- 보드/자산: land ownership, buildings, special ownership/value, purchase laps
- 경제: ledgers, tax overrides, loans, settlements, rates, refunds
- 거래: land/operating-right offers, usage request, takeover and forced decisions
- 이벤트: active events, history, personal reports and multipliers
- 결과: bankruptcy/revival/no-action, rankings, log/history/final result
- 도구/시뮬레이션: forced values, processed keys, quick presets, simulation result

모든 필드가 한 객체에 평면 배치되고 서비스별 쓰기 소유권이 없었다.

## 라우트와 엔진 대응

| 라우트군 | 엔진 메서드 |
|---|---|
| config/join/start/pause/resume/end | configure, join, start_game, pause, resume, close_hosting |
| roll/end-turn | roll_dice, end_turn |
| purchase/build/sell | purchase_land, purchase_special_region, build_on_land, sell_building |
| trade | propose/respond_land_trade |
| operating right/usage | propose/respond transfer, request/respond change, recall |
| event/report/export | trigger_event, personal_report, export_results |
| quick game/simulation | configure/run_quick_game, run_bot_simulation |
| `/api/dev/*` | force/set/create/run 계열 진단 메서드 |

## 처리 흐름

- 사람: join → start → roll → 서버 도착 판정/pending action → 선택 행동 → end turn.
- 봇: turn 대상 확인 → roll → 자산 매각 검토 → pending 투자 검토 → finish turn.
  balanced/aggressive/conservative/random의 준비금과 건물 선호는 엔진 내부에 있었고,
  `BotController.choose_action`의 `roll_and_end`와 실제 실행 경로가 달랐다.
- 타이머/자동화: 변경 전에는 `/api/state`와 `/api/host/state` GET이
  `advance_automation`을 호출했다. timeout, 봇, 거래/승인 만료가 조회 빈도에 종속됐다.
- 설정: POST config가 서버에 저장했지만 host.js는 응답 config를 폼에 적용하지 않고
  `renderSlots()` 기본값으로 슬롯을 재생성했다.
- 시뮬레이션: 한 요청 스레드가 모든 run을 동기 실행하고 실제 엔진 state에 마지막
  결과를 저장했다. 브라우저 중단은 로컬 boolean만 변경했다.

## 위험과 결합

Critical: `/host` 방문 즉시 권한, 고정 secret, debug 실행.
High: 전역 상태 무잠금, 멱등 검사/변경 비원자성, GET의 상태 변경, 동기 시뮬레이션.
Medium: host 응답의 원장/대출/세금 노출, 설정 UI 불일치, 초기화 수명주기 부재.
구조 결합의 중심은 2,300줄 `GameEngine`, 평면 `GameState`, 엔진 내부를 직접 아는
라우트와 UI다.

## 변경 전 완성도

- 정상: 핵심 턴/이동, 토지/건물, 경제/대출/정산, 거래/운영권, 이벤트,
  파산/부활, 최종 결과와 해당 규칙 테스트.
- 부분: public/private view, 전략별 봇 투자, reset_runtime, 멱등성, 설정 UI.
- 껍데기: 호스트 권한 모델, `BotController.choose_action`, UI 시뮬레이션 중단.
- 미구현: 토큰 인증/CSRF, 서버 자동 진행기, 원자적 상태 변경, 작업형 시뮬레이션,
  서비스/하위 상태 경계, 새 게임과 전체 초기화 API.
