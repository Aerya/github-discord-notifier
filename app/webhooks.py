from .db import setting_get
from .discord import (
    action_embed,
    fork_embed,
    issue_embed,
    pr_embed,
    send,
    star_embed,
)
from .security import decrypt_secret


def _seen(db, key):
    return db.execute(
        "SELECT 1 FROM seen_events WHERE event_key=?",
        (key,),
    ).fetchone() is not None


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


def _destinations(db, repo_id):
    rows = db.execute(
        """
        SELECT d.id,d.name,d.url_encrypted
        FROM discord_webhooks d
        JOIN repository_webhooks rw ON rw.webhook_id=d.id
        WHERE rw.repository_id=?
        ORDER BY d.id
        """,
        (repo_id,),
    ).fetchall()

    if not rows:
        all_hooks = db.execute(
            "SELECT id,name,url_encrypted FROM discord_webhooks ORDER BY id"
        ).fetchall()
        if len(all_hooks) == 1:
            rows = all_hooks

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "url": decrypt_secret(row["url_encrypted"]),
        }
        for row in rows
    ]


def _touch_repo(db, repo_id):
    db.execute(
        """
        UPDATE repositories
        SET last_hook_delivery_at=CURRENT_TIMESTAMP,
            github_hook_status='active',
            github_hook_error=NULL
        WHERE id=?
        """,
        (repo_id,),
    )


def _finish_ignored(db, repo, delivery_key, event_type, title, actor, reason):
    _mark(db, delivery_key)
    _touch_repo(db, repo["id"])
    _log(
        db,
        repo["full_name"],
        event_type,
        "ignored",
        title,
        actor,
        reason,
    )
    db.commit()
    return True


def _send_to_discord(
    app,
    db,
    repo,
    delivery_id,
    delivery_key,
    event_type,
    embed,
    title,
    actor,
):
    destinations = _destinations(db, repo["id"])
    if not destinations:
        _log(
            db,
            repo["full_name"],
            event_type,
            "failed",
            title,
            actor,
            "Aucun webhook Discord associé",
        )
        db.commit()
        app.logger.error(
            "%s · %s · aucun webhook Discord associé",
            repo["full_name"],
            event_type,
        )
        return False

    failures = []
    sent = 0

    for destination in destinations:
        destination_key = f"discord:{delivery_id}:{destination['id']}"
        if _seen(db, destination_key):
            continue
        try:
            send(destination["url"], embed)
            _mark(db, destination_key)
            sent += 1
        except Exception as exc:
            failures.append(
                f"{destination['name']}: {type(exc).__name__}: {exc}"
            )
            app.logger.exception(
                "%s · %s · échec Discord vers %s",
                repo["full_name"],
                event_type,
                destination["name"],
            )

    if failures:
        _log(
            db,
            repo["full_name"],
            event_type,
            "failed",
            title,
            actor,
            " | ".join(failures)[:1500],
        )
        db.commit()
        return False

    _mark(db, delivery_key)
    _touch_repo(db, repo["id"])
    _log(
        db,
        repo["full_name"],
        event_type,
        "sent",
        title,
        actor,
        f"{sent or len(destinations)} destination(s)",
    )
    db.commit()
    app.logger.info(
        "%s · %s · notification envoyée: %s",
        repo["full_name"],
        event_type,
        title,
    )
    return True


def process_github_delivery(app, db, event, payload, delivery_id):
    repository = payload.get("repository") or {}
    repo_id = repository.get("id")
    full_name = repository.get("full_name") or "GitHub"
    delivery_key = f"delivery:{delivery_id}"

    if event == "ping":
        if repo_id:
            _touch_repo(db, repo_id)
            db.commit()
        app.logger.info("%s · webhook GitHub ping reçu", full_name)
        return True

    if _seen(db, delivery_key):
        return True

    repo = None
    if repo_id:
        repo = db.execute(
            "SELECT * FROM repositories WHERE id=?",
            (repo_id,),
        ).fetchone()
    if repo is None and full_name:
        repo = db.execute(
            "SELECT * FROM repositories WHERE full_name=?",
            (full_name,),
        ).fetchone()

    if repo is None or not repo["selected"]:
        _mark(db, delivery_key)
        db.commit()
        return True

    action = payload.get("action")
    sender = (payload.get("sender") or {}).get("login") or "inconnu"

    if event == "issues":
        if action != "opened" or not repo["issues_enabled"]:
            _mark(db, delivery_key)
            db.commit()
            return True
        issue = payload.get("issue") or {}
        return _send_to_discord(
            app,
            db,
            repo,
            delivery_id,
            delivery_key,
            "issues",
            issue_embed(repo["full_name"], issue),
            issue.get("title") or f"Issue #{issue.get('number', '?')}",
            sender,
        )

    if event == "pull_request":
        if action != "opened" or not repo["prs_enabled"]:
            _mark(db, delivery_key)
            db.commit()
            return True
        pr = payload.get("pull_request") or {}
        login = (setting_get("github_login", "") or "").lower()
        pr_author = (pr.get("user") or {}).get("login") or sender
        is_dependabot = pr_author.lower() == "dependabot[bot]"
        if repo["ignore_dependabot_prs"] and is_dependabot:
            return _finish_ignored(
                db,
                repo,
                delivery_key,
                "prs",
                pr.get("title"),
                pr_author,
                "PR créée par Dependabot",
            )
        if repo["ignore_own_prs"] and sender.lower() == login:
            return _finish_ignored(
                db,
                repo,
                delivery_key,
                "prs",
                pr.get("title"),
                sender,
                "PR créée par mon compte GitHub",
            )
        return _send_to_discord(
            app,
            db,
            repo,
            delivery_id,
            delivery_key,
            "prs",
            pr_embed(repo["full_name"], pr),
            pr.get("title") or f"PR #{pr.get('number', '?')}",
            sender,
        )

    if event == "workflow_run":
        if action != "completed" or not repo["actions_enabled"]:
            _mark(db, delivery_key)
            db.commit()
            return True
        run = payload.get("workflow_run") or {}
        conclusion = run.get("conclusion")
        wanted = (
            (conclusion == "success" and repo["action_success"])
            or (conclusion == "failure" and repo["action_failure"])
            or (conclusion == "cancelled" and repo["action_cancelled"])
        )
        if not wanted:
            _mark(db, delivery_key)
            db.commit()
            return True
        return _send_to_discord(
            app,
            db,
            repo,
            delivery_id,
            delivery_key,
            "actions",
            action_embed(repo["full_name"], run),
            run.get("name") or "GitHub Actions",
            sender,
        )

    if event == "fork":
        if not repo["forks_enabled"]:
            _mark(db, delivery_key)
            db.commit()
            return True
        fork = payload.get("forkee") or {}
        return _send_to_discord(
            app,
            db,
            repo,
            delivery_id,
            delivery_key,
            "forks",
            fork_embed(repo["full_name"], fork),
            fork.get("full_name") or "Nouveau fork",
            sender,
        )

    if event == "star":
        if action != "created" or not repo["stars_enabled"]:
            _mark(db, delivery_key)
            db.commit()
            return True
        star = {
            "user": payload.get("sender") or {},
            "starred_at": payload.get("starred_at"),
        }
        return _send_to_discord(
            app,
            db,
            repo,
            delivery_id,
            delivery_key,
            "stars",
            star_embed(repo["full_name"], star),
            "Nouvelle étoile",
            sender,
        )

    _mark(db, delivery_key)
    db.commit()
    return True
