# 플레이어 기능 연결 조사

이 문서는 UI 수정 전에 `game/routes.py`, `game/engine.py`, `templates/player.html`,
`static/js/player.js`, `game/bots.py`를 대조한 결과와 연결 후 상태를 기록한다.

## 기능 매트릭스

| 기능 | 백엔드 | API | 작업 전 플레이어 UI | 구현 상태 | 작업 전 문제 / 현재 조치 |
|---|---|---|---|---|---|
| 주사위 | `roll_dice` | `POST /api/roll` | 버튼·리스너 있음 | COMPLETE | 서버 `allowed_actions.roll`로 활성화 |
| 턴 종료 | `end_turn` | `POST /api/end-turn` | 버튼·리스너 있음 | COMPLETE | 서버 차례 판정으로 활성화 |
| 토지 구매 | `purchase_land` | `POST /api/purchase-land` | 연결됨 | COMPLETE | 별도 토지가 결제 후 같은 방문의 선택 건설 단계로 전환 |
| 토지 구매 포기 | `decline_pending_action` | `POST /api/decline-action` | 연결됨 | COMPLETE | `purchase_land` 대기일 때 “토지 구매 포기”로 표시 |
| 건물 건설·포기 | `build_on_land`, `decline_pending_action` | `POST /api/build`, `POST /api/decline-action` | 연결됨 | COMPLETE | 구매 직후 가격·예상 잔액·제한 사유 표시, “이번 방문 건설하지 않기” 제공 |
| 건물 매각 | `sell_building` | `POST /api/sell-building` | UI·리스너 없음 | COMPLETE | 건물 선택, 방식·지급액 표시, API 연결 |
| 특수지역 구매 | `purchase_special_region` | `POST /api/purchase-special` | UI·리스너 없음 | COMPLETE | 구매 버튼과 대기 행동 연결 |
| 일반토지 거래 | `propose_land_trade` | `POST /api/trade/land/propose` | 숨은 거래 버튼만 존재 | COMPLETE | 현재 토지·고정가·가능 상대를 서버 응답으로 표시 |
| 운영권 양도 | `propose_operating_right_transfer` | `POST /api/operating-right/transfer/propose` | UI 없음 | COMPLETE | 건물·상대·금액·체인 표시 후 제안 |
| 거래 수락·거절 | `respond_land_trade`, `respond_operating_right_transfer` | 각 `/respond` | 모달은 표시 전용 | COMPLETE | 관계자 모달에 수락·거절 및 자동 거절 시간 표시 |
| 용도 변경 신청 | `request_usage_change` | `POST /api/usage-change/request` | UI 없음 | COMPLETE | 건물·변경 유형 선택 후 신청 |
| 용도 변경 승인·거절 | `respond_usage_change` | `POST /api/usage-change/respond` | 표시 전용 | COMPLETE | 승인자에게만 버튼과 자동 승인 시간 표시 |
| 권한 회수 | `recall_operating_rights` | `POST /api/operating-right/recall` | UI 없음 | COMPLETE | 지급 능력 포함 서버 판정과 선택 건물 연결 |
| 이벤트 확인 | `trigger_event`, `record_player_activity` | 조회와 `POST /api/event/acknowledge` | 요약 탭 있음 | COMPLETE | 본인 적용 이벤트를 표시하고 확인 입력을 활동으로 기록; 플레이어 임의 발생은 차단 |
| 세금 확인 | 원장·`_calculate_tax_rate_bps` | `GET /api/player/<id>/private` | 세율만 표시 | COMPLETE | 과세소득·세율·예상/확정 세금 표시 |
| 대출 확인 | 대출·자동상환 | 같은 비공개 API | 남은 금액만 표시 | COMPLETE | 원금·이자·총상환액·마감·자동상환 표시 |
| 상업 매각 예정 환급 | `pending_commercial_sale_refunds` | 같은 비공개 API | 공개 상태에 있었고 UI 없음 | COMPLETE | 본인에게만 지역·예정액 표시, 공개 응답에서 제거 |
| 파산 상태 | `_bankrupt_player` | 같은 비공개 API | 배지만 표시 | COMPLETE | 사유·라운드·관전·부활 제한 표시 |
| 파산 후 토지 인수 | `respond_land_takeover` | `POST /api/bankruptcy/takeover/respond` | UI 없음 | COMPLETE | 토지가·현재 현금·남은 시간과 인수·포기 버튼 표시, 미응답 자동 포기 |
| 부활 | `revive_player` | `POST /api/revive` 추가 | UI 없음 | COMPLETE | 서버 가능 판정과 부활 버튼 연결 |
| 최종 정산 | `finalize_game` | `/api/state`의 `final_results` | 전용 표시 없음 | COMPLETE | 종료 사유·순위·최종 자산 표시 |

## 경계 규칙 확인

- 토지 구매와 건물 편집 분리: 구매 성공은 `land_purchased_this_visit`만 설정하고
  가격과 수량 제한을 재계산한 `build` 대기 상태를 만든다. 건설 성공 때만
  `successful_build_edit_this_visit`가 설정되며, 건설 포기·실패는 편집 기회를 소비하지 않는다.
- 구매 직후 행동 제한: 같은 방문에는 선택 건설 또는 턴 종료만 허용하며 매각·거래·운영권
  양도·용도 변경·권한 회수는 서버와 UI 모두 차단한다.
- 권리 통합 토지 거래: 명목 소유자를 제외한 외부 권리자가 한 명일 때만 그 사람에게
  토지를 넘기고 모든 건물 체인을 새 명목 소유자로 정규화한다. 상태 `COMPLETE`.
- 승인별 독립 타이머: 용도 변경 승인자는 각자의 `approver_started_at`과 남은 시간을
  가지며 일시중지 기간은 모든 승인 시각에서 제외한다. 상태 `COMPLETE`.
- 부활 경계: 파산 라운드 차이 15 이하는 거부하고 16부터 허용한다. 상태 `COMPLETE`.
- 파산 후 토지 인수: A→B→C→D에서 D 인수 후 D→B→C를 복구하며 사람 플레이어가
  실제 API와 모달로 응답한다. 상태 `COMPLETE`.

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
