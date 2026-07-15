# Local Economy Board Game

Python Flask 기반 로컬 네트워크 멀티플레이 경제 보드게임 구현입니다.

## 공식 게임 규칙

현재 공식 규칙 버전은 `2026.07.16.1`입니다. 기계 판독 기준은
`data/rules/game_rules.json`이며, 사람이 읽는 명세는
`docs/GAME_RULES.md`, 코드·테스트 대응과 차이 판정은
`docs/RULE_IMPLEMENTATION_MATRIX.md`에 있습니다. 규칙 데이터 → 공식 문서 →
코드 → 테스트 순서로 우선합니다.

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

개발 도구는 `APP_MODE=development`, `DEBUG_GAME_TOOLS=true`, 호스트 인증의
세 조건을 모두 만족할 때만 사용할 수 있습니다.

## 테스트

```bash
source .venv/bin/activate
pytest -q
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
