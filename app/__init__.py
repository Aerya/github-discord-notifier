from datetime import datetime, timezone
import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .db import init_db
from .routes import bp


def now():
    return datetime.now(timezone.utc)


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("APP_SECRET_KEY", ""),
        DATABASE=os.environ.get("DATABASE_PATH", "/data/app.db"),
        ENCRYPTION_KEY=os.environ.get("APP_ENCRYPTION_KEY", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=(
            os.environ.get("APP_COOKIE_SECURE", "false").lower() == "true"
        ),
        PERMANENT_SESSION_LIFETIME=43200,
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        TESTING=False,
    )

    if test_config:
        app.config.update(test_config)

    if not app.config["TESTING"]:
        if len(app.config["SECRET_KEY"]) < 32:
            raise RuntimeError(
                "APP_SECRET_KEY doit contenir au moins 32 caractères."
            )
        if not app.config["ENCRYPTION_KEY"]:
            raise RuntimeError("APP_ENCRYPTION_KEY est obligatoire.")

    if os.environ.get("APP_TRUST_PROXY", "false").lower() == "true":
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
        )

    init_db(app)
    app.register_blueprint(bp)

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self'; "
            "script-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    app.jinja_env.globals["now"] = now
    return app
