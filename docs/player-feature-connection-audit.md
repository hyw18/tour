# 플레이어 기능 연결 조사

분석 기준 HEAD는 `5cf5b6a8edd0ac27f40efb262cec87cea381107c`이다. 이 문서는
`game/routes.py`, `game/engine.py`, `templates/player.html`, `static/js/player.js`,
`game/bots.py`를 실제 테스트와 함께 대조한 결과를 기록한다.

## 기능 매트릭스

현재 플레이어 화면은 서버의 `allowed_actions`, `next_action_message`, `action_priority`를
단일 기준으로 사용한다. `turnTitle`은 현재 턴 주체만, `mainGuide`는 다음 행동만 표시한다.

| 기능 | 백엔드 | API | 작업 전 플레이어 UI | 구현 상태 | 작업 전 문제 / 현재 조치 |
|---|---|---|---|---|---|
| 주사위 | `roll_dice` | `POST /api/roll` | 버튼·리스너 있음 | MULTI_CLIENT_TESTED | 100회 동시 요청에서 한 번 실행 |
| 턴 종료 | `end_turn` | `POST /api/end-turn` | 버튼·리스너 있음 | MULTI_CLIENT_TESTED | 4세션 120턴 진행 |
| 토지 구매 | `purchase_land` | `POST /api/purchase-land` | 연결됨 | MULTI_CLIENT_TESTED | 별도 토지가 결제 후 같은 방문의 선택 건설 단계로 전환 |
| 토지 구매 포기 | `decline_pending_action` | `POST /api/decline-action` | 연결됨 | UNIT_TESTED | `purchase_land` 대기일 때 “토지 구매 포기”로 표시 |
| 건물 건설·포기 | `build_on_land`, `decline_pending_action` | `POST /api/build`, `POST /api/decline-action` | 연결됨 | MULTI_CLIENT_TESTED | 구매 직후 가격·예상 잔액·제한 사유 표시, “이번 방문 건설하지 않기” 제공 |
| 건물 매각 | `sell_building` | `POST /api/sell-building` | UI·리스너 없음 | UNIT_TESTED | 건물 선택, 방식·지급액 표시, API 연결 |
| 특수지역 구매 | `purchase_special_region` | `POST /api/purchase-special` | UI·리스너 없음 | UNIT_TESTED | 구매 버튼과 대기 행동 연결 |
| 일반토지 거래 | `propose_land_trade` | `POST /api/trade/land/propose` | 숨은 거래 버튼만 존재 | MULTI_CLIENT_TESTED | 현재 토지·고정가·가능 상대와 100회 응답 검증 |
| 운영권 양도 | `propose_operating_right_transfer` | `POST /api/operating-right/transfer/propose` | UI 없음 | UNIT_TESTED | 건물·상대·금액·체인 표시 후 제안 |
| 거래 수락·거절 | `respond_land_trade`, `respond_operating_right_transfer` | 각 `/respond` | 모달은 표시 전용 | MULTI_CLIENT_TESTED | 토지 거래 수락 100회 동시 요청 검증 |
| 용도 변경 신청 | `request_usage_change` | `POST /api/usage-change/request` | UI 없음 | UNIT_TESTED | 건물·변경 유형 선택 후 신청 |
| 용도 변경 승인·거절 | `respond_usage_change` | `POST /api/usage-change/respond` | 표시 전용 | UNIT_TESTED | 승인자에게만 버튼과 자동 승인 시간 표시 |
| 권한 회수 | `recall_operating_rights` | `POST /api/operating-right/recall` | UI 없음 | UNIT_TESTED | 지급 능력 포함 서버 판정과 선택 건물 연결 |
| 이벤트 확인 | `trigger_event`, `acknowledge_events` | 조회와 `POST /api/event/acknowledge` | 요약 탭 있음 | MULTI_CLIENT_TESTED | 새 event_version 한 번만 활동 인정 |
| 세금 확인 | 원장·`_calculate_tax_rate_bps` | 통합 플레이어 상태 API | 세율만 표시 | UNIT_TESTED | 과세소득·세율·예상/확정 세금 표시 |
| 대출 확인 | 대출·자동상환 | 통합 플레이어 상태 API | 남은 금액만 표시 | UNIT_TESTED | 원금·이자·총상환액·마감·자동상환 표시 |
| 상업 매각 예정 환급 | `pending_commercial_sale_refunds` | 통합 플레이어 상태 API | 공개 상태에 있었고 UI 없음 | UNIT_TESTED | 본인에게만 지역·예정액 표시 |
| 파산 상태 | `_bankrupt_player` | 통합 플레이어 상태 API | 배지만 표시 | UNIT_TESTED | 사유·라운드·관전·부활 제한 표시 |
| 파산 후 토지 인수 | `respond_land_takeover` | `POST /api/bankruptcy/takeover/respond` | UI 없음 | UNIT_TESTED | 토지가·현재 현금·남은 시간과 응답 표시 |
| 부활 | `revive_player` | `POST /api/revive` | UI 없음 | UNIT_TESTED | 서버 가능 판정과 부활 버튼 연결 |
| 최종 정산 | `finalize_game` | `/api/state`의 `final_results` | 전용 표시 없음 | UNIT_TESTED | 종료 사유·순위·최종 자산 표시 |

## 접속·동기화 안정성

| 기능 | 상태 | 근거 |
|---|---|---|
| 재접속 토큰 | MULTI_CLIENT_TESTED | 쿠키 없는 별도 세션에서 자산·위치 복구 |
| 공개·개인 revision | MULTI_CLIENT_TESTED | 단일 잠금 통합 API와 동일 state_version |
| 부분 보드 갱신 | UNIT_TESTED | 40칸 최초 생성 후 클래스·텍스트·말만 갱신 |
| 적응형 폴링 | UNIT_TESTED | 중복 방지, AbortController, visibility/pageshow 처리 |
| 실제 스마트폰 2~4대 | REAL_DEVICE_TEST_REQUIRED | 현재 실행 환경에서 물리 기기 검증 불가 |
| 호스트 1·플레이어 4 Chromium | BROWSER_TESTED | 독립 컨텍스트 입장·도움말·구매·건설·재무·재접속·회전, 콘솔/500 오류 0 |

## 최신 플레이어 사용성 감사

| 연결 | 상태 | 현재 구현 |
|---|---|---|
| 도착 카드 → 행동 | BROWSER_TESTED | 명령 영역과 같은 `invokeAction`, `actionInFlight`, 멱등 요청 사용 |
| 현재 방문비용 | UNIT_TESTED | 네 식별자가 현재 도착과 일치하는 지출만 합산 |
| 건설 선택 | BROWSER_TESTED | 서버가 허용한 때만 표시, placeholder 후 명시 선택 |
| 비활성 사유 | BROWSER_TESTED | 접힌 “다른 행동” 안의 터치 가능한 사유와 status 도움말 |
| 재무 탭 | BROWSER_TESTED | 자산·세금·대출·최근 내역 독립 렌더와 ARIA 탭 |
| 자산 관리 이동 | BROWSER_TESTED | 상세 선택 후 명시 버튼, 모달 닫기, 선택 유지, 포커스 이동 |
| 최초·상황별 도움말 | BROWSER_TESTED | 확인 여부와 설정만 localStorage 저장 |
| 개발자 규칙 문구 | CODE_PRESENT | 플레이어 상단/이벤트에서 제거, 계산과 호스트 규칙 상태 유지 |

## 주사위·이벤트 화면 연출

| 기능 | 상태 | 근거 |
|---|---|---|
| 서버 확정 주사위·이동 경로 | UNIT_TESTED | 1·6 결과와 출발지 강제 정지 경로 검증 |
| 2D 주사위·말 순차 이동 | UNIT_TESTED | Promise 큐, 최종 서버 결과 고정, 부분 DOM 이동 |
| 이벤트 occurrence·노출 범위 | UNIT_TESTED | 동일 카드 반복, 개인·지역·전국, 연쇄 순서 검증 |
| 이벤트 확인 큐·중복 방지 | UNIT_TESTED | occurrence 단위 확인과 재표시 차단 |
| reduced motion·건너뛰기 | UNIT_TESTED | 정적 UI 계약과 JavaScript 문법 검증 |
| 실제 모바일 애니메이션 | REAL_DEVICE_TEST_REQUIRED | Android Chrome·Samsung Internet·iOS Safari 필요 |

## 최신 확인·경제 UI 감사

| 항목 | 상태 | 근거 |
|---|---|---|
| 일반토지·특수지역 구매 확인 | UNIT_TESTED | POST 전 공통 확인과 서버 state_version 재검증 |
| 건물 건설 접근성 | UNIT_TESTED | dialog/label, 안전 버튼 초기 포커스, focus trap, Esc·뒤로가기, 포커스 복원 |
| 건물 매각·운영권 양도·권한 회수 강한 확인 | UNIT_TESTED | 대상·금액·잔액·권리 변경·비가역성 표시 |
| 거래 수락·파산 토지 인수·부활 확인 | UNIT_TESTED | 수락/인수/부활만 확인 후 POST, 거절·포기는 즉시 처리 |
| 거래 상태와 경제 성립 분리 | UNIT_TESTED | proposed/accepted/rejected/expired domain event; 변화 없으면 경제 action 없음 |
| 경제 action 초기 경계 | UNIT_TESTED | 서버 sequence/cursor/unread, 새 입장 기준선, 재접속 요약 후 생략 정책 |
| 관련 자산 강조 | UNIT_TESTED | region/building/special/finance/refund data 식별자 사용 |
| 이벤트 탭 | UNIT_TESTED | 서버 제목·대상·phase·진행률·현재/최대 효과 사용, 내부 ID 미표시 |
| 최근 수익·지출 | UNIT_TESTED | 중앙 display_name, 라운드·턴·지역·상대·건물 메타데이터 |
| 실제 브라우저 포커스·레이아웃 | BROWSER_TESTED | Chromium 독립 컨텍스트 실행; 물리 기기는 별도 필수 |

## 경계 규칙 확인

- 토지 구매와 건물 편집 분리: 구매 성공은 `land_purchased_this_visit`만 설정하고
  가격과 수량 제한을 재계산한 `build` 대기 상태를 만든다. 건설 성공 때만
  `successful_build_edit_this_visit`가 설정되며, 건설 포기·실패는 편집 기회를 소비하지 않는다.
- 구매 직후 행동 제한: 같은 방문에는 선택 건설 또는 턴 종료만 허용하며 매각·거래·운영권
  양도·용도 변경·권한 회수는 서버와 UI 모두 차단한다.
- 권리 통합 토지 거래: 명목 소유자를 제외한 외부 권리자가 한 명일 때만 그 사람에게
  토지를 넘기고 모든 건물 체인을 새 명목 소유자로 정규화한다. 상태 `UNIT_TESTED`.
- 승인별 독립 타이머: 용도 변경 승인자는 각자의 `approver_started_at`과 남은 시간을
  가지며 일시중지 기간은 모든 승인 시각에서 제외한다. 상태 `UNIT_TESTED`.
- 부활 경계: 파산 라운드 차이 15 이하는 거부하고 16부터 허용한다. 상태 `UNIT_TESTED`.
- 파산 후 토지 인수: A→B→C→D에서 D 인수 후 D→B→C를 복구하며 사람 플레이어가
  실제 API와 모달로 응답한다. 상태 `UNIT_TESTED`.

## 조사 당시 연결되지 않았던 요소

- `manageAction`, `tradeAction`은 `hidden`과 `aria-hidden` 상태였으며 이벤트 리스너가 없었다.
- `tradeModal`은 공개 offer 요약을 HTML로 표시했지만 응답 버튼과 API 호출이 없었다.
- `/api/sell-building`, `/api/purchase-special`, 거래·운영권·용도 변경·회수 API는
  플레이어 JavaScript에서 전혀 호출되지 않았다.
- 공개 상태에는 모든 플레이어의 현금은 제거되어 있었지만 예정 환급과 거래 상태 일부가
  포함되어 있었다. 비공개 API는 임의의 `X-Player-Id`만 맞추면 조회할 수 있었다.
- 특수지역 최초 가격과 현재 가치가 모두 `state.special_values`로 표시됐다.
- 봇의 `choose_action`은 `game/bots.py`에 있었지만 실제 투자·매각·거래 승인 전략은
  `GameEngine._bot_*` 메서드에 분산되어 있었다.

## 현재 정보 경계

- 공개: 위치, 상태, 공용 총재산·순위, 토지/건물/운영권 구조, 공개 이벤트,
  특수지역 최초가와 현재가.
- 본인 세션 전용: 현금, 원장, 세금, 대출, 예정 환급, 자산별 관리 가능 여부,
  파산·부활 상세.
- 거래 관계자 전용: 거래 금액, 대상 자산, 현재/예상 권리 체인, 응답과 남은 시간.
- 호스트 전용: 설정과 운영 API. 수동 이벤트 발생은 호스트 인증과 CSRF 검증이 필요하다.

## 봇 책임

- `GameEngine`: 상태 변경, 규칙 검증, 금전·권리 실행.
- `BotController`: 현재 가능한 대기 행동 조회, 행동 실행 순서, 거래/승인 응답 연결.
- `BotStrategy`: 전략별 준비금, 건물 선호, 거래·승인 판단. 상태를 변경하지 않는다.
