from pathlib import Path
from ipaddress import ip_address
import os
import secrets
import sys

from flask import Flask

from game.engine import GameEngine
from game.routes import bp, dev_bp
from game.automation import AutomationWorker
from game.security import HostAuthenticator
from game.views import GameViews
from game.simulation import SimulationJobManager


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(test_config or {})
    app.config.setdefault("APP_MODE", os.environ.get("APP_MODE", "development"))
    secret_key = app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY") or os.environ.get("APP_SECRET_KEY")
    if not secret_key and app.config["APP_MODE"] == "production" and not app.config.get("TESTING"):
        raise RuntimeError("SECRET_KEY is required in production")
    app.secret_key = secret_key or secrets.token_urlsafe(48)
    cookie_secure_env = os.environ.get("SESSION_COOKIE_SECURE", "").lower() == "true"
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=bool(app.config.get("SESSION_COOKIE_SECURE", cookie_secure_env)),
    )
    data_dir = app.config.get("DATA_DIR") or Path(__file__).parent / "data"
    app.config["GAME_ENGINE"] = app.config.get("GAME_ENGINE") or GameEngine(data_dir)
    app.config["HOST_AUTH"] = app.config.get("HOST_AUTH") or HostAuthenticator.create(
        app.config.get("HOST_TOKEN") or os.environ.get("HOST_TOKEN")
    )
    app.config["GAME_VIEWS"] = GameViews(app.config["GAME_ENGINE"])
    app.config["AUTOMATION_WORKER"] = AutomationWorker(app.config["GAME_ENGINE"])
    app.config["SIMULATION_JOBS"] = SimulationJobManager(data_dir)
    app.register_blueprint(bp)
    if app.config["APP_MODE"] == "development" and os.environ.get("DEBUG_GAME_TOOLS", "").lower() == "true":
        app.register_blueprint(dev_bp)

    if not app.config.get("TESTING") and not app.config.get("DISABLE_AUTOMATION"):
        app.config["AUTOMATION_WORKER"].start()

    if not app.config.get("TESTING"):
        host = os.environ.get("FLASK_HOST", "127.0.0.1")
        try:
            display_host = "127.0.0.1" if ip_address(host).is_unspecified else host
        except ValueError:
            display_host = host
        print(
            "\n========================================\n"
            f"HOST TOKEN: {app.config['HOST_AUTH'].token}\n"
            f"HOST URL: http://{display_host}:5000/host\n"
            "========================================",
            file=sys.stderr,
            flush=True,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=os.environ.get("FLASK_HOST", "127.0.0.1"), debug=False, use_reloader=False)
