# 최신 HEAD 전체 기능·UI 재감사

- 분석 기준 HEAD: `bd3d295fc1eb7eecb668492f6aa5f2e8c34619e2`
- 분석일: 2026-07-16
- 공식 규칙 버전: `2026.07.16.1`
- 감사 범위: 기준 HEAD와 본 감사 작업 트리의 서버, 플레이어 UI, 애니메이션, 동시성, 접근성

과거 `dbf54825` 보고 결과는 검증 근거로 재사용하지 않았다. 현재 분류는 코드 존재와
실행 검증을 구분하며, 브라우저와 실제 기기에서 실행하지 못한 항목을 완료로 판정하지 않는다.

## 발견한 차이와 현재 상태

| 항목 | 발견한 차이 | 상태 |
|---|---|---|
| 멱등 키 | 누락만 거부하고 공백·길이·문자 검증과 동일 키 네트워크 재시도가 없었음 | UNIT_TESTED |
| 위험 행동 확인 | 건설 외 구매·매각·거래·회수·부활이 즉시 POST됨 | UNIT_TESTED |
| 거래 상태 | 제안·성립·거절·만료가 경로 기반 경제 유형으로 합쳐짐 | UNIT_TESTED |
| 경제 연출 경계 | 첫 개인 조회에서 모든 과거 action을 확인 처리해 조회 중 경합 가능 | UNIT_TESTED |
| 자산 강조 | 모든 `.asset-row`를 강조함 | UNIT_TESTED |
| 이벤트 탭 | 내부 ID 노출, 프런트 진행률 재계산 | UNIT_TESTED |
| 최근 원장 | 내부 source 코드만 표시하고 라운드·턴·상대가 없었음 | UNIT_TESTED |
| 사운드 | 실제 효과음 없이 음소거 설정 노출 | UNIT_TESTED |
| 실제 Chromium | `libnspr4.so` 부재로 Playwright 시작 불가 | REAL_DEVICE_TEST_REQUIRED |

## 상태 분류 요약

- CODE_PRESENT: 공통 확인 모달, 서버 이벤트 진행률, 경제 커서, 관련 자산 식별자.
- UNIT_TESTED: 키 형식·재시도 계약, 거래 거절 무결제, 정산 순서, 이벤트 ID 비노출, 커서 경계.
- MULTI_CLIENT_TESTED: 기존 100회 동일 키 실행, 재접속, 4세션 상태 일치 테스트가 최신 작업 트리에서 재실행됨.
- BROWSER_TESTED: 없음. Chromium이 실행되지 않았으므로 부여하지 않음.
- REAL_DEVICE_TEST_REQUIRED: Android Chrome, Samsung Internet, iOS/WebKit의 회전·터치·장시간 성능.
- CONFLICT: 현재 확인된 공식 확정 규칙 충돌 없음.
- UNRESOLVED: TAX-005, EVENT-010, ASSET-006.

## 변경 금지 UNRESOLVED

- TAX-005: 미개발 토지 0.5%p
- EVENT-010: 현재 이벤트 카드 공식 승인 여부
- ASSET-006: 복합 건물 최종 정산가 0원 여부

세 항목은 계산을 변경하지 않았으며 화면의 공식 결정 대기 표시를 유지한다.
