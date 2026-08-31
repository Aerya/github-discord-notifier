import secrets
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .db import get_db, setting_get, setting_set
from .discord import test as discord_test_message
from .github_client import (
    authenticated_user,
    delete_repository_hook,
    list_repositories,
    rate_limit,
    sync_repository_hook,
)
from .security import (
    csrf_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    login_required,
    require_csrf,
    validate_discord_webhook,
    verify_github_signature,
    verify_password,
)
from .webhooks import process_github_delivery

bp = Blueprint("main", __name__)
bp.add_app_template_global(csrf_token, "csrf_token")


def _count_users():
    return get_db().execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


def _store_repositories(repos):
    db = get_db()
    for r in repos:
        db.execute(
            """
            INSERT INTO repositories(id,full_name,private,owner_login,html_url)
            VALUES(?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                full_name=excluded.full_name,
                private=excluded.private,
                owner_login=excluded.owner_login,
                html_url=excluded.html_url
            """,
            (
                r["id"],
                r["full_name"],
                int(bool(r.get("private"))),
                (r.get("owner") or {}).get("login", ""),
                r.get("html_url"),
            ),
        )
    db.commit()


def _normalise_public_url(value):
    value = (value or "").strip().rstrip("/")
    if value.endswith("/webhook/github"):
        value = value[:-15]
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("L’URL publique doit être une URL HTTPS valide.")
    return value.rstrip("/")


def _webhook_endpoint():
    base = setting_get("github_public_url", "")
    return f"{base.rstrip('/')}/webhook/github" if base else ""


def _webhook_secret(create=False):
    encrypted = setting_get("github_webhook_secret", "")
    if encrypted:
        return decrypt_secret(encrypted)
    if not create:
        return ""
    secret = secrets.token_urlsafe(48)
    setting_set("github_webhook_secret", encrypt_secret(secret))
    return secret


def _events_for_repo(repo):
    events = []
    if repo["issues_enabled"]:
        events.append("issues")
    if repo["prs_enabled"]:
        events.append("pull_request")
    if repo["actions_enabled"]:
        events.append("workflow_run")
    if repo["forks_enabled"]:
        events.append("fork")
    if repo["stars_enabled"]:
        events.append("star")
    return events


def _sync_all_hooks():
    db = get_db()
    token_enc = setting_get("github_token", "")
    endpoint = _webhook_endpoint()

    if not token_enc:
        return 0, 0, 0, "Aucun PAT GitHub configuré."
    if not endpoint:
        return 0, 0, 0, "URL publique non configurée."

    token = decrypt_secret(token_enc)
    secret = _webhook_secret(create=True)
    repos = db.execute(
        """
        SELECT * FROM repositories
        WHERE selected=1 OR github_hook_id IS NOT NULL
        ORDER BY full_name COLLATE NOCASE
        """
    ).fetchall()

    active = removed = errors = 0

    for repo in repos:
        events = _events_for_repo(repo)
        try:
            if repo["selected"] and events:
                hook = sync_repository_hook(
                    token,
                    repo["full_name"],
                    endpoint,
                    secret,
                    events,
                    repo["github_hook_id"],
                )
                db.execute(
                    """
                    UPDATE repositories
                    SET github_hook_id=?,
                        github_hook_status='active',
                        github_hook_error=NULL,
                        github_hook_updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (hook["id"], repo["id"]),
                )
                active += 1
            elif repo["github_hook_id"]:
                delete_repository_hook(
                    token,
                    repo["full_name"],
                    repo["github_hook_id"],
                )
                db.execute(
                    """
                    UPDATE repositories
                    SET github_hook_id=NULL,
                        github_hook_status='disabled',
                        github_hook_error=NULL,
                        github_hook_updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (repo["id"],),
                )
                removed += 1
        except Exception as exc:
            errors += 1
            reason = f"{type(exc).__name__}: {exc}"
            db.execute(
                """
                UPDATE repositories
                SET github_hook_status='error',
                    github_hook_error=?,
                    github_hook_updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (reason[:1500], repo["id"]),
            )
            db.execute(
                """
                INSERT INTO event_logs(repository,event_type,result,title,actor,reason)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    repo["full_name"],
                    "webhook",
                    "failed",
                    "Synchronisation du webhook GitHub",
                    None,
                    reason[:1500],
                ),
            )
    db.commit()
    return active, removed, errors, None


def _flash_sync(result):
    active, removed, errors, message = result
    if message:
        flash(message, "error")
        return
    text = f"{active} hook(s) actif(s)"
    if removed:
        text += f" · {removed} supprimé(s)"
    if errors:
        flash(text + f" · {errors} erreur(s)", "error")
    else:
        flash(text + ".", "success")


@bp.get("/health")
def health():
    return "OK", 200, {"Content-Type": "text/plain; charset=utf-8"}


@bp.route("/initialisation", methods=["GET", "POST"])
def bootstrap():
    if _count_users():
        return redirect(url_for("main.login"))
    if request.method == "POST":
        require_csrf()
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        c = request.form.get("confirm", "")
        if not 3 <= len(u) <= 64:
            flash("Le nom d’utilisateur doit contenir entre 3 et 64 caractères.", "error")
        elif len(p) < 12:
            flash("Le mot de passe doit contenir au moins 12 caractères.", "error")
        elif p != c:
            flash("Les mots de passe ne correspondent pas.", "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO users(username,password_hash) VALUES(?,?)",
                (u, hash_password(p)),
            )
            db.commit()
            flash("Compte administrateur créé.", "success")
            return redirect(url_for("main.login"))
    return render_template("bootstrap.html")


@bp.route("/connexion", methods=["GET", "POST"])
def login():
    if not _count_users():
        return redirect(url_for("main.bootstrap"))
    if session.get("user_id"):
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        require_csrf()
        row = get_db().execute(
            "SELECT * FROM users WHERE username=?",
            (request.form.get("username", "").strip(),),
        ).fetchone()
        if row and verify_password(
            row["password_hash"],
            request.form.get("password", ""),
        ):
            session.clear()
            session["user_id"] = row["id"]
            session["username"] = row["username"]
            session.permanent = True
            csrf_token()
            return redirect(url_for("main.dashboard"))
        flash("Identifiants incorrects.", "error")
    return render_template("login.html")


@bp.post("/deconnexion")
@login_required
def logout():
    require_csrf()
    session.clear()
    return redirect(url_for("main.login"))


@bp.get("/")
@login_required
def dashboard():
    db = get_db()
    counts = {
        "repos": db.execute(
            "SELECT COUNT(*) c FROM repositories WHERE selected=1"
        ).fetchone()["c"],
        "hooks": db.execute(
            """
            SELECT COUNT(*) c FROM repositories
            WHERE selected=1 AND github_hook_status='active'
            """
        ).fetchone()["c"],
        "webhooks": db.execute(
            "SELECT COUNT(*) c FROM discord_webhooks"
        ).fetchone()["c"],
        "sent": db.execute(
            "SELECT COUNT(*) c FROM event_logs WHERE result='sent'"
        ).fetchone()["c"],
        "errors": db.execute(
            "SELECT COUNT(*) c FROM event_logs WHERE result='failed'"
        ).fetchone()["c"],
    }
    recent = db.execute(
        "SELECT * FROM event_logs ORDER BY id DESC LIMIT 10"
    ).fetchall()
    return render_template(
        "dashboard.html",
        counts=counts,
        recent=recent,
        github_login=setting_get("github_login"),
        webhook_endpoint=_webhook_endpoint(),
    )


@bp.route("/github", methods=["GET", "POST"])
@login_required
def github():
    if request.method == "POST":
        require_csrf()
        token = request.form.get("token", "").strip()
        try:
            user, _ = authenticated_user(token)
            repos = list_repositories(token)
        except Exception:
            flash(
                "Connexion GitHub refusée. Vérifiez le PAT et ses permissions.",
                "error",
            )
        else:
            setting_set("github_token", encrypt_secret(token))
            setting_set("github_login", user["login"])
            _store_repositories(repos)
            flash(
                f"Compte GitHub connecté : {user['login']} · {len(repos)} dépôt(s) trouvé(s).",
                "success",
            )
            if _webhook_endpoint():
                _flash_sync(_sync_all_hooks())
            return redirect(url_for("main.github"))

    rate = None
    if setting_get("github_token"):
        try:
            rate = rate_limit(
                decrypt_secret(setting_get("github_token"))
            )
        except Exception:
            pass

    db = get_db()
    hook_counts = {
        "selected": db.execute(
            "SELECT COUNT(*) c FROM repositories WHERE selected=1"
        ).fetchone()["c"],
        "active": db.execute(
            """
            SELECT COUNT(*) c FROM repositories
            WHERE selected=1 AND github_hook_status='active'
            """
        ).fetchone()["c"],
        "errors": db.execute(
            """
            SELECT COUNT(*) c FROM repositories
            WHERE selected=1 AND github_hook_status='error'
            """
        ).fetchone()["c"],
    }
    return render_template(
        "github.html",
        connected=bool(setting_get("github_token")),
        github_login=setting_get("github_login"),
        rate=rate,
        public_url=setting_get("github_public_url", ""),
        webhook_endpoint=_webhook_endpoint(),
        hook_counts=hook_counts,
    )


@bp.post("/github/deconnecter")
@login_required
def github_disconnect():
    require_csrf()
    setting_set("github_token", "")
    setting_set("github_login", "")
    flash(
        "PAT supprimé. Les hooks GitHub déjà installés continuent de fonctionner.",
        "success",
    )
    return redirect(url_for("main.github"))


@bp.post("/github/webhook")
@login_required
def github_webhook_config():
    require_csrf()
    try:
        public_url = _normalise_public_url(request.form.get("public_url", ""))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.github"))
    setting_set("github_public_url", public_url)
    _webhook_secret(create=True)
    _flash_sync(_sync_all_hooks())
    return redirect(url_for("main.github"))


@bp.post("/github/webhooks/synchroniser")
@login_required
def github_webhooks_sync():
    require_csrf()
    _flash_sync(_sync_all_hooks())
    return redirect(url_for("main.github"))


@bp.get("/depots")
@login_required
def repositories():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM repositories ORDER BY full_name COLLATE NOCASE"
    ).fetchall()
    hooks = db.execute(
        "SELECT id,name FROM discord_webhooks ORDER BY name"
    ).fetchall()
    links = db.execute(
        "SELECT repository_id,webhook_id FROM repository_webhooks"
    ).fetchall()
    link_map = {}
    for x in links:
        link_map.setdefault(x["repository_id"], set()).add(x["webhook_id"])
    return render_template(
        "repositories.html",
        repositories=rows,
        webhooks=hooks,
        link_map=link_map,
        webhook_ready=bool(_webhook_endpoint()),
    )


@bp.post("/depots/synchroniser")
@login_required
def sync_repositories():
    require_csrf()
    enc = setting_get("github_token")
    if not enc:
        flash("Connectez d’abord GitHub.", "error")
        return redirect(url_for("main.github"))
    try:
        repos = list_repositories(decrypt_secret(enc))
    except Exception:
        flash("Impossible de récupérer les dépôts GitHub.", "error")
        return redirect(url_for("main.github"))
    _store_repositories(repos)
    flash(f"{len(repos)} dépôt(s) synchronisé(s).", "success")
    return redirect(url_for("main.repositories"))


@bp.post("/depots/selection")
@login_required
def repositories_selection():
    require_csrf()
    db = get_db()
    selected_ids = {
        int(x)
        for x in request.form.getlist("repository_id")
        if str(x).isdigit()
    }
    for row in db.execute("SELECT id FROM repositories").fetchall():
        db.execute(
            "UPDATE repositories SET selected=? WHERE id=?",
            (int(row["id"] in selected_ids), row["id"]),
        )
    db.commit()
    flash(f"{len(selected_ids)} dépôt(s) sélectionné(s).", "success")
    if _webhook_endpoint() and setting_get("github_token"):
        _flash_sync(_sync_all_hooks())
    return redirect(url_for("main.repositories"))


@bp.post("/depots/<int:repository_id>/dependabot")
@login_required
def repository_dependabot(repository_id):
    require_csrf()
    db = get_db()
    repo = db.execute(
        "SELECT id,full_name FROM repositories WHERE id=?", (repository_id,)
    ).fetchone()
    if not repo:
        abort(404)
    enabled = int("ignore_dependabot_prs" in request.form)
    db.execute(
        "UPDATE repositories SET ignore_dependabot_prs=? WHERE id=?",
        (enabled, repository_id),
    )
    db.commit()
    state = "ignorées" if enabled else "à nouveau notifiées"
    flash(f"Les PR Dependabot de {repo['full_name']} seront {state}.", "success")
    return redirect(url_for("main.repositories"))


@bp.post("/depots/appliquer-global")
@login_required
def repositories_apply_global():
    require_csrf()
    db = get_db()
    repos = db.execute(
        "SELECT id FROM repositories WHERE selected=1"
    ).fetchall()
    if not repos:
        flash("Sélectionnez au moins un dépôt à surveiller.", "error")
        return redirect(url_for("main.repositories"))

    values = (
        int("issues_enabled" in request.form),
        int("prs_enabled" in request.form),
        int("actions_enabled" in request.form),
        int("forks_enabled" in request.form),
        int("stars_enabled" in request.form),
        int("ignore_own_prs" in request.form),
        int("ignore_dependabot_prs" in request.form),
        int("action_success" in request.form),
        int("action_failure" in request.form),
        int("action_cancelled" in request.form),
    )
    webhook_ids = [
        int(x)
        for x in request.form.getlist("webhook_id")
        if str(x).isdigit()
    ]

    for repo in repos:
        repo_id = repo["id"]
        db.execute(
            """
            UPDATE repositories SET
                issues_enabled=?,prs_enabled=?,actions_enabled=?,
                forks_enabled=?,stars_enabled=?,ignore_own_prs=?,
                ignore_dependabot_prs=?,
                action_success=?,action_failure=?,action_cancelled=?
            WHERE id=?
            """,
            values + (repo_id,),
        )
        db.execute(
            "DELETE FROM repository_webhooks WHERE repository_id=?",
            (repo_id,),
        )
        for webhook_id in webhook_ids:
            db.execute(
                """
                INSERT OR IGNORE INTO repository_webhooks(repository_id,webhook_id)
                VALUES(?,?)
                """,
                (repo_id, webhook_id),
            )
    db.commit()
    flash(
        f"Configuration globale appliquée à {len(repos)} dépôt(s).",
        "success",
    )
    if _webhook_endpoint() and setting_get("github_token"):
        _flash_sync(_sync_all_hooks())
    return redirect(url_for("main.repositories"))


@bp.route("/discord", methods=["GET", "POST"])
@login_required
def discord():
    db = get_db()
    if request.method == "POST":
        require_csrf()
        name = request.form.get("name", "").strip()
        url = request.form.get("url", "").strip()
        if not 2 <= len(name) <= 80:
            flash("Nom de webhook invalide.", "error")
        elif not validate_discord_webhook(url):
            flash("URL de webhook Discord invalide.", "error")
        else:
            db.execute(
                "INSERT INTO discord_webhooks(name,url_encrypted) VALUES(?,?)",
                (name, encrypt_secret(url)),
            )
            db.commit()
            flash("Webhook Discord ajouté.", "success")
            return redirect(url_for("main.discord"))
    return render_template(
        "discord.html",
        webhooks=db.execute(
            "SELECT id,name,created_at FROM discord_webhooks ORDER BY name"
        ).fetchall(),
    )


@bp.post("/discord/<int:webhook_id>/tester")
@login_required
def discord_test(webhook_id):
    require_csrf()
    row = get_db().execute(
        "SELECT * FROM discord_webhooks WHERE id=?",
        (webhook_id,),
    ).fetchone()
    if not row:
        abort(404)
    try:
        discord_test_message(decrypt_secret(row["url_encrypted"]))
        flash("Message de test envoyé.", "success")
    except Exception:
        flash("Échec du test Discord.", "error")
    return redirect(url_for("main.discord"))


@bp.post("/discord/<int:webhook_id>/supprimer")
@login_required
def discord_delete(webhook_id):
    require_csrf()
    db = get_db()
    db.execute(
        "DELETE FROM discord_webhooks WHERE id=?",
        (webhook_id,),
    )
    db.commit()
    flash("Webhook supprimé.", "success")
    return redirect(url_for("main.discord"))


@bp.get("/journaux")
@login_required
def logs():
    return render_template(
        "logs.html",
        logs=get_db().execute(
            "SELECT * FROM event_logs ORDER BY id DESC LIMIT 500"
        ).fetchall(),
    )


@bp.post("/journaux/vider")
@login_required
def logs_clear():
    require_csrf()
    db = get_db()
    db.execute("DELETE FROM event_logs")
    db.commit()
    flash("Journaux vidés.", "success")
    return redirect(url_for("main.logs"))


@bp.post("/webhook/github")
def github_webhook_receiver():
    encrypted = setting_get("github_webhook_secret", "")
    if not encrypted:
        return {"ok": False, "error": "webhook_not_configured"}, 503

    body = request.get_data(cache=True)
    signature = request.headers.get("X-Hub-Signature-256", "")
    secret = decrypt_secret(encrypted)

    if not verify_github_signature(body, signature, secret):
        current_app.logger.warning("Webhook GitHub refusé: signature invalide")
        return {"ok": False, "error": "invalid_signature"}, 401

    delivery_id = request.headers.get("X-GitHub-Delivery", "").strip()
    event = request.headers.get("X-GitHub-Event", "").strip()
    payload = request.get_json(silent=True)

    if not delivery_id or not event:
        return {"ok": False, "error": "missing_headers"}, 400
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid_json"}, 400

    ok = process_github_delivery(
        current_app._get_current_object(),
        get_db(),
        event,
        payload,
        delivery_id,
    )
    return ({"ok": True}, 200) if ok else ({"ok": False}, 502)


@bp.route("/compte", methods=["GET", "POST"])
@login_required
def account():
    if request.method == "POST":
        require_csrf()
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE id=?",
            (session["user_id"],),
        ).fetchone()
        cur = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        conf = request.form.get("confirm_password", "")
        if not verify_password(user["password_hash"], cur):
            flash("Mot de passe actuel incorrect.", "error")
        elif len(new) < 12:
            flash("Le nouveau mot de passe doit contenir au moins 12 caractères.", "error")
        elif new != conf:
            flash("Les mots de passe ne correspondent pas.", "error")
        else:
            db.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (hash_password(new), user["id"]),
            )
            db.commit()
            session.clear()
            flash("Mot de passe modifié. Reconnectez-vous.", "success")
            return redirect(url_for("main.login"))
    return render_template("account.html")
