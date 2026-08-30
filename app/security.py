import hmac
import hashlib
import secrets
from functools import wraps
from urllib.parse import urlparse

from argon2 import PasswordHasher
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, session, request, abort, redirect, url_for

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password):
    return ph.hash(password)


def verify_password(password_hash, password):
    try:
        return ph.verify(password_hash, password)
    except Exception:
        return False


def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def require_csrf():
    supplied = request.form.get("_csrf", "")
    expected = session.get("_csrf", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        abort(400, "Jeton CSRF invalide.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("main.login"))
        return view(*args, **kwargs)
    return wrapped


def fernet():
    return Fernet(current_app.config["ENCRYPTION_KEY"].encode())


def encrypt_secret(value):
    return fernet().encrypt(value.encode()).decode()


def decrypt_secret(value):
    try:
        return fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        raise RuntimeError("Impossible de déchiffrer un secret. Vérifiez APP_ENCRYPTION_KEY.")


def verify_github_signature(body, signature, secret):
    if not signature or not signature.startswith("sha256=") or not secret:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def validate_discord_webhook(url):
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme != "https":
        return False
    if parsed.hostname not in {"discord.com", "www.discord.com", "discordapp.com"}:
        return False
    parts = [p for p in parsed.path.split("/") if p]
    # /api/webhooks/{id}/{token}
    return len(parts) >= 4 and parts[0] == "api" and parts[1] == "webhooks"
