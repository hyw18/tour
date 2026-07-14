# Local Economy Board Game

Python Flask 기반 로컬 네트워크 멀티플레이 경제 보드게임 구현입니다.

## 실행 방법

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app run --host 0.0.0.0 --debug
```

호스트 컴퓨터에서는 `http://127.0.0.1:5000/host`로 접속합니다.
같은 네트워크의 스마트폰에서는 `http://<호스트_IP>:5000/player`로 접속합니다.

개발용 테스트 제어를 켜면 주사위 고정, 현금 지정, 위치 변경, 토지/건물 생성, 봇 전략 변경, N턴 자동 실행을 사용할 수 있습니다.

```bash
DEBUG_GAME_TOOLS=true flask --app app run --host 0.0.0.0 --debug
```

## 테스트

```bash
source .venv/bin/activate
pytest -q
```

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
