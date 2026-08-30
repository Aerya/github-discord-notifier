import threading
import time

from .db import get_db, setting_get
from .security import decrypt_secret
from .github_client import (
    recent_issues,
    recent_pulls,
    recent_forks,
    recent_stars,
    recent_workflow_runs,
)
from .discord import (
    issue_embed,
    pr_embed,
    fork_embed,
    star_embed,
    action_embed,
    send,
)

_thread = None
_stop = threading.Event()


def _seen(db, key):
    return (
        db.execute(
            "SELECT 1 FROM seen_events WHERE event_key=?",
            (key,),
        ).fetchone()
        is not None
    )


def _mark(db, key):
    db.execute(
        "INSERT OR IGNORE INTO seen_events(event_key) VALUES(?)",
        (key,),
    )


def _log(db, repo, event_type, result, title=None, actor=None, reason=None):
    db.execute(
        """
        INSERT INTO event_logs(repository,event_type,result,title,actor,reason)
        VALUES(?,?,?,?,?,?)
        """,
        (repo, event_type, result, title, actor, reason),
    )


def _urls(db, repo_id):
    rows = db.execute(
        """
        SELECT d.url_encrypted
        FROM discord_webhooks d
        JOIN repository_webhooks rw ON rw.webhook_id=d.id
        WHERE rw.repository_id=?
        """,
        (repo_id,),
    ).fetchall()

    # Destination implicite : s'il n'existe qu'un seul webhook Discord
    # configuré, il sert de destination par défaut aux dépôts sans mapping.
    if not rows:
        all_hooks = db.execute(
            "SELECT url_encrypted FROM discord_webhooks ORDER BY id"
        ).fetchall()
        if len(all_hooks) == 1:
            rows = all_hooks

    return [decrypt_secret(row["url_encrypted"]) for row in rows]


def _notify(app, db, repo, typ, key, embed, title, actor):
    if _seen(db, key):
        return

    urls = _urls(db, repo["id"])

    if not urls:
        _mark(db, key)
        _log(
            db,
            repo["full_name"],
            typ,
            "ignored",
            title,
            actor,
            "Aucun webhook Discord associé",
        )
        db.commit()
        app.logger.warning(
            "%s · %s · événement ignoré: aucun webhook Discord associé",
            repo["full_name"],
            typ,
        )
        return

    sent = 0

    for url in urls:
        try:
            send(url, embed)
            sent += 1
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            _log(
                db,
                repo["full_name"],
                typ,
                "failed",
                title,
                actor,
                reason,
            )
            app.logger.exception(
                "%s · %s · échec Discord",
                repo["full_name"],
                typ,
            )

    _mark(db, key)

    if sent:
        _log(
            db,
            repo["full_name"],
            typ,
            "sent",
            title,
            actor,
            f"{sent} destination(s)",
        )
        app.logger.info(
            "%s · %s · notification envoyée: %s",
            repo["full_name"],
            typ,
            title or key,
        )

    db.commit()


def _baseline(db, repo, typ, items, key_fn):
    marker = f'baseline:{repo["id"]}:{typ}'

    if _seen(db, marker):
        return False

    for item in items:
        _mark(db, key_fn(item))

    _mark(db, marker)
    db.commit()
    return True


def _poll_category(app, db, repo, typ, fetcher, key_fn, handler):
    full = repo["full_name"]

    try:
        items = fetcher()

        if _baseline(db, repo, typ, items, key_fn):
            app.logger.info(
                "%s · %s · référence initiale créée (%d événement(s))",
                full,
                typ,
                len(items),
            )
            return

        for item in reversed(items):
            handler(item)

    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        _log(
            db,
            full,
            typ,
            "failed",
            reason=reason,
        )
        db.commit()
        app.logger.exception(
            "%s · %s · erreur de vérification: %s",
            full,
            typ,
            exc,
        )


def poll_once(app):
    with app.app_context():
        db = get_db()
        token_enc = setting_get("github_token")

        if not token_enc:
            app.logger.warning("Poll GitHub ignoré: aucun token configuré")
            return

        token = decrypt_secret(token_enc)
        login = (setting_get("github_login", "") or "").lower()

        repos = db.execute(
            """
            SELECT *
            FROM repositories
            WHERE selected=1
            ORDER BY full_name
            """
        ).fetchall()

        app.logger.info(
            "Début vérification GitHub · %d dépôt(s)",
            len(repos),
        )

        for repo in repos:
            full = repo["full_name"]

            if repo["issues_enabled"]:
                key_fn = lambda x, rid=repo["id"]: f'issue:{rid}:{x["id"]}'

                def issue_handler(x, repo=repo, key_fn=key_fn):
                    _notify(
                        app,
                        db,
                        repo,
                        "issues",
                        key_fn(x),
                        issue_embed(repo["full_name"], x),
                        x.get("title"),
                        (x.get("user") or {}).get("login"),
                    )

                _poll_category(
                    app,
                    db,
                    repo,
                    "issues",
                    lambda full=full: recent_issues(token, full),
                    key_fn,
                    issue_handler,
                )

            if repo["prs_enabled"]:
                key_fn = lambda x, rid=repo["id"]: f'pr:{rid}:{x["id"]}'

                def pr_handler(x, repo=repo, key_fn=key_fn):
                    actor = (x.get("user") or {}).get("login")
                    key = key_fn(x)

                    if _seen(db, key):
                        return

                    if (
                        repo["ignore_own_prs"]
                        and actor
                        and actor.lower() == login
                    ):
                        _mark(db, key)
                        _log(
                            db,
                            repo["full_name"],
                            "prs",
                            "ignored",
                            x.get("title"),
                            actor,
                            "PR créée par mon compte GitHub",
                        )
                        db.commit()
                        return

                    _notify(
                        app,
                        db,
                        repo,
                        "prs",
                        key,
                        pr_embed(repo["full_name"], x),
                        x.get("title"),
                        actor,
                    )

                _poll_category(
                    app,
                    db,
                    repo,
                    "prs",
                    lambda full=full: recent_pulls(token, full),
                    key_fn,
                    pr_handler,
                )

            if repo["forks_enabled"]:
                key_fn = lambda x, rid=repo["id"]: f'fork:{rid}:{x["id"]}'

                def fork_handler(x, repo=repo, key_fn=key_fn):
                    _notify(
                        app,
                        db,
                        repo,
                        "forks",
                        key_fn(x),
                        fork_embed(repo["full_name"], x),
                        x.get("full_name"),
                        (x.get("owner") or {}).get("login"),
                    )

                _poll_category(
                    app,
                    db,
                    repo,
                    "forks",
                    lambda full=full: recent_forks(token, full),
                    key_fn,
                    fork_handler,
                )

            if repo["stars_enabled"]:
                key_fn = lambda x, rid=repo["id"]: (
                    f'star:{rid}:'
                    f'{(x.get("user") or {}).get("id")}:'
                    f'{x.get("starred_at")}'
                )

                def star_handler(x, repo=repo, key_fn=key_fn):
                    _notify(
                        app,
                        db,
                        repo,
                        "stars",
                        key_fn(x),
                        star_embed(repo["full_name"], x),
                        "Nouvelle étoile",
                        (x.get("user") or {}).get("login"),
                    )

                _poll_category(
                    app,
                    db,
                    repo,
                    "stars",
                    lambda full=full: recent_stars(token, full),
                    key_fn,
                    star_handler,
                )

            if repo["actions_enabled"]:
                key_fn = lambda x, rid=repo["id"]: (
                    f'action:{rid}:{x["id"]}:{x.get("run_attempt", 1)}'
                )

                def actions_fetch(full=full):
                    return [
                        x
                        for x in recent_workflow_runs(token, full)
                        if x.get("status") == "completed"
                    ]

                def action_handler(x, repo=repo, key_fn=key_fn):
                    key = key_fn(x)

                    if _seen(db, key):
                        return

                    conclusion = x.get("conclusion")
                    wanted = (
                        (conclusion == "success" and repo["action_success"])
                        or (conclusion == "failure" and repo["action_failure"])
                        or (
                            conclusion == "cancelled"
                            and repo["action_cancelled"]
                        )
                    )

                    if not wanted:
                        _mark(db, key)
                        db.commit()
                        return

                    _notify(
                        app,
                        db,
                        repo,
                        "actions",
                        key,
                        action_embed(repo["full_name"], x),
                        x.get("name"),
                        (x.get("actor") or {}).get("login"),
                    )

                _poll_category(
                    app,
                    db,
                    repo,
                    "actions",
                    actions_fetch,
                    key_fn,
                    action_handler,
                )

            db.execute(
                """
                UPDATE repositories
                SET last_sync_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (repo["id"],),
            )
            db.commit()

        db.execute(
            """
            DELETE FROM event_logs
            WHERE id NOT IN (
                SELECT id FROM event_logs ORDER BY id DESC LIMIT 2000
            )
            """
        )
        db.commit()

        app.logger.info(
            "Fin vérification GitHub · %d dépôt(s)",
            len(repos),
        )


def _loop(app):
    time.sleep(3)

    while not _stop.is_set():
        try:
            poll_once(app)
        except Exception:
            app.logger.exception("Erreur générale du poller")

        with app.app_context():
            try:
                interval = max(
                    60,
                    min(
                        3600,
                        int(setting_get("poll_interval", "300")),
                    ),
                )
            except Exception:
                interval = 300

        _stop.wait(interval)


def start_poller(app):
    global _thread

    if app.config.get("TESTING"):
        return

    if _thread and _thread.is_alive():
        return

    _thread = threading.Thread(
        target=_loop,
        args=(app,),
        name="github-poller",
        daemon=True,
    )
    _thread.start()
