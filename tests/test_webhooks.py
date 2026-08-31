from cryptography.fernet import Fernet

from app import create_app
from app.webhooks import process_github_delivery


def make_app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test",
        "DATABASE": str(tmp_path / "test.db"),
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
    })


def test_dependabot_pr_can_be_ignored(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        from app.db import get_db

        db = get_db()
        db.execute(
            "INSERT INTO repositories(id,full_name,owner_login,selected,ignore_dependabot_prs) VALUES(?,?,?,?,?)",
            (1, "Aerya/example", "Aerya", 1, 1),
        )
        db.commit()
        assert process_github_delivery(app, db, "pull_request", {
            "action": "opened",
            "repository": {"id": 1, "full_name": "Aerya/example"},
            "sender": {"login": "a-reviewer"},
            "pull_request": {
                "number": 1,
                "title": "Bump package",
                "user": {"login": "dependabot[bot]"},
            },
        }, "dependabot-delivery")
        event = db.execute("SELECT result,reason FROM event_logs").fetchone()
        assert (event["result"], event["reason"]) == ("ignored", "PR créée par Dependabot")
