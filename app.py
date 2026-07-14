from pathlib import Path

from flask import Flask

from game.engine import GameEngine
from game.routes import bp


def create_app(test_config=None):
    app = Flask(__name__)
    app.secret_key = "local-dev-secret"
    app.config.update(test_config or {})
    data_dir = app.config.get("DATA_DIR") or Path(__file__).parent / "data"
    app.config["GAME_ENGINE"] = app.config.get("GAME_ENGINE") or GameEngine(data_dir)
    app.register_blueprint(bp)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
