# Local Economy Board Game

Python Flask 기반 로컬 네트워크 멀티플레이 경제 보드게임 구현입니다.

## 공식 게임 규칙

현재 공식 규칙 버전은 `2026.07.16.1`입니다. 기계 판독 기준은
`data/rules/game_rules.json`이며, 사람이 읽는 명세는
`docs/GAME_RULES.md`, 코드·테스트 대응과 차이 판정은
`docs/RULE_IMPLEMENTATION_MATRIX.md`에 있습니다. 규칙 데이터 → 공식 문서 →
코드 → 테스트 순서로 우선합니다.

최신 안정성 감사 기준 HEAD는 `bd3d295fc1eb7eecb668492f6aa5f2e8c34619e2`입니다.
최신 작업 트리 자동 검증은 `194 passed, 1 skipped`이며, 4개 독립 세션 30라운드와 주요 변경 요청
100회 동시 전송을 통과했습니다. 실제 스마트폰 2~4대 검증은
`REAL_DEVICE_TEST_REQUIRED`로 남아 있습니다. Chromium은 현재 환경의 `libnspr4.so`
부재로 실행되지 않았으므로 브라우저 검증 완료로 분류하지 않습니다.

## 실행 방법

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

시작 시 터미널에 한 번 표시되는 호스트 토큰을 `/host` 화면에 입력해야 합니다.
기본 주소는 `127.0.0.1:5000`입니다. 로컬 네트워크에 공개할 때만
`FLASK_HOST=0.0.0.0 python app.py`로 실행하세요.

실행 화면 예시:

```text
========================================
HOST TOKEN: AbCdEfGhIjKlMnOpQrStUvWx
HOST URL: http://127.0.0.1:5000/host
========================================
```

토큰을 고정해야 하는 환경에서는 실행 전에 `HOST_TOKEN`을 설정할 수 있습니다.

```bash
HOST_TOKEN='충분히-길고-안전한-토큰' python app.py
```

호스트 로그인 절차:

1. 서버와 같은 origin의 터미널 출력에 표시된 `HOST URL`을 엽니다.
2. 첫 화면의 호스트 토큰 입력란에 `HOST TOKEN` 값을 입력합니다.
3. 로그인에 성공하면 호스트 상태와 제어 화면이 표시됩니다.
4. 작업을 마치면 화면의 로그아웃 버튼으로 호스트 세션을 종료합니다.

페이지와 API는 모두 `/api/...` 상대경로를 사용합니다. 브라우저에서는 처음 연
호스트 주소를 유지하고 `localhost`, `127.0.0.1`, LAN IP를 중간에 바꾸지 마세요.

개발 서버는 운영 실행과 분리합니다.

```bash
APP_MODE=development DEBUG_GAME_TOOLS=true \
  flask --app app run --host 127.0.0.1 --debug --no-reload
```

호스트 컴퓨터에서는 `http://127.0.0.1:5000/host`로 접속합니다.
같은 네트워크의 스마트폰에서는 `http://<호스트_IP>:5000/player`로 접속합니다.

개발용 테스트 제어를 켜면 주사위 고정, 현금 지정, 위치 변경, 토지/건물 생성, 봇 전략 변경, N턴 자동 실행을 사용할 수 있습니다.

플레이어 화면은 서버 확정 주사위 결과와 이동 경로를 2D 주사위·말 이동으로 표시하고,
미확인 이벤트 발생을 `occurrence_id` 순서대로 공개합니다. 기본·빠르게·최소화 설정과
각 연출 건너뛰기를 제공하며 `prefers-reduced-motion`을 지원합니다.

구매·건설·매각·거래·권한 변경·파산 토지 인수·부활처럼 되돌리기 어려운 행동은
서버 상태 버전과 금액을 표시하는 최종 확인을 거칩니다. 경제 연출은 서버가 확정한
domain event만 표시하며 클라이언트가 현금이나 소유권 결과를 계산하지 않습니다.

개발 도구는 `APP_MODE=development`, `DEBUG_GAME_TOOLS=true`, 호스트 인증의
세 조건을 모두 만족할 때만 사용할 수 있습니다.

## 테스트

```bash
source .venv/bin/activate
pytest -q
ruff check .
python -m compileall .
```

전체 품질 검증 도구는 `pip install -r requirements-dev.txt`로 설치합니다.

실제 Chromium에서 플레이어 UI 흐름까지 검증하려면 최초 한 번 브라우저를 설치합니다.

```bash
playwright install chromium
pytest -q tests/test_player_browser.py
```

플레이어 화면은 브라우저의 서명된 세션과 `localStorage`의 플레이어 ID를 함께
사용하므로 회전·새로고침 후에도 본인 상태를 복원하며, 다른 브라우저 세션에서는
해당 플레이어의 현금·세금·대출·거래 상세를 조회할 수 없습니다.

## 운영 실행

운영 모드에서는 `SECRET_KEY`가 반드시 필요하며, Flask 개발 서버 대신 WSGI
서버를 사용해야 합니다. HTTPS 환경에서는 `SESSION_COOKIE_SECURE=true`에
해당하는 애플리케이션 설정도 활성화하세요. LAN HTTP 개발 환경에서는 secure
쿠키를 강제하지 않으므로 로그인 쿠키가 정상 동작합니다.

```bash
APP_MODE=production \
SECRET_KEY='충분히-길고-고정된-비밀키' \
HOST_TOKEN='충분히-길고-안전한-호스트-토큰' \
SESSION_COOKIE_SECURE=true \
gunicorn 'app:create_app()'
```

개발 모드의 자동 진행 루프가 reloader에 의해 중복 생성되지 않도록 문서의 개발
명령은 `--no-reload`를 사용합니다.

## 구조

```text
.
├── app.py
├── data/
│   └── schemas/
├── game/
├── requirements.txt
├── static/
│   ├── css/
│   └── js/
├── tests/
└── templates/
```
