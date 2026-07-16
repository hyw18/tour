# 최신 HEAD 기능 안정성 재감사

- 분석 기준 HEAD: `dbf54825042eb60dfa877c7461762718024e9118`
- 분석일: 2026-07-16
- 공식 규칙 버전: `2026.07.16.1`
- 규칙 판정: MATCH 103, UNRESOLVED 3, 합계 106

이 보고서는 과거 `6b34b87` 분석을 재사용하지 않고 최신 코드, 라우트 목록,
클라이언트 코드와 실행 테스트를 다시 대조한 결과다.

## 재현된 안정성 차이

| 항목 | 수정 전 재현 결과 | 현재 상태 |
|---|---|---|
| 재접속 | Flask 세션 쿠키 손실 시 `player_id`만으로 복구 불가 | MULTI_CLIENT_TESTED |
| 상태 시점 | 공개·개인 상태를 순차 요청해 revision 혼합 가능 | MULTI_CLIENT_TESTED |
| 멱등 범위 | 키 필수화는 있었으나 게임 초기화 전후 범위 구분 없음 | MULTI_CLIENT_TESTED |
| 활동 기록 | `GameRuleError`도 활동으로 기록, 이벤트 확인은 이중 기록 | MULTI_CLIENT_TESTED |
| 보드 폴링 | 매초 40칸 DOM과 리스너 전체 재생성 | UNIT_TESTED |
| 폴링 누적 | 고정 1초 interval, 오래된 요청 취소와 가시성 조절 없음 | UNIT_TESTED |
| 실제 브라우저 | Playwright 브라우저가 `libnspr4.so` 부재로 시작 실패 | MANUAL_DEVICE_TEST_REQUIRED |

## 변경 금지 UNRESOLVED

- TAX-005: 미개발 토지 0.5%p
- EVENT-010: 현재 이벤트 카드 공식 승인 여부
- ASSET-006: 복합 건물 최종 정산가 0원 여부

세 항목은 코드와 화면의 결정 대기 표시를 유지했다.
