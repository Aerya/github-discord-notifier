import requests
from urllib.parse import quote

ICON_BASE = "https://raw.githubusercontent.com/Aerya/github-discord-notifier/main/app/static/octicons"

ICONS = {
    "issue": f"{ICON_BASE}/issue-opened.png",
    "pr": f"{ICON_BASE}/git-pull-request.png",
    "action": f"{ICON_BASE}/workflow.png",
    "fork": f"{ICON_BASE}/repo-forked.png",
    "star": f"{ICON_BASE}/star.png",
}


def _repo_link(repo):
    return f"[{repo}](https://github.com/{repo})"


def _actor_link(actor):
    if not actor:
        return "inconnu"
    return f"[{actor}](https://github.com/{quote(actor, safe='-')})"


def _base(title, url, description, repo, actor, icon):
    embed = {
        "title": title,
        "url": url,
        "description": (description or "")[:3500],
        "fields": [
            {
                "name": "Dépôt",
                "value": _repo_link(repo),
                "inline": True,
            },
            {
                "name": "Auteur",
                "value": _actor_link(actor),
                "inline": True,
            },
        ],
        "footer": {"text": "GitHub Discord Notifier"},
    }
    if actor:
        embed["author"] = {
            "name": actor,
            "url": f"https://github.com/{quote(actor, safe='-')}",
            "icon_url": ICONS[icon],
        }
    return embed


def issue_embed(repo, issue):
    e = _base(
        f"Nouvelle issue #{issue['number']}",
        issue["html_url"],
        issue.get("title"),
        repo,
        (issue.get("user") or {}).get("login"),
        "issue",
    )
    labels = [
        x.get("name")
        for x in issue.get("labels", [])
        if x.get("name")
    ]
    if labels:
        e["fields"].append({
            "name": "Labels",
            "value": ", ".join(labels)[:1024],
            "inline": False,
        })
    e["timestamp"] = issue.get("created_at")
    return e


def pr_embed(repo, pr):
    e = _base(
        f"Pull Request #{pr['number']}",
        pr["html_url"],
        pr.get("title"),
        repo,
        (pr.get("user") or {}).get("login"),
        "pr",
    )
    e["fields"].append({
        "name": "Branches",
        "value": (
            f"{(pr.get('head') or {}).get('ref', '?')} "
            f"→ {(pr.get('base') or {}).get('ref', '?')}"
        ),
        "inline": False,
    })
    e["timestamp"] = pr.get("created_at")
    return e


def action_embed(repo, run):
    conclusion = run.get("conclusion") or run.get("status") or "inconnu"
    labels = {
        "success": "Succès",
        "failure": "Échec",
        "cancelled": "Annulé",
    }
    status = labels.get(conclusion, conclusion)

    e = _base(
        f"{run.get('name', 'Workflow')} — {status}",
        run.get("html_url"),
        f"Workflow terminé : **{status}**",
        repo,
        (run.get("actor") or {}).get("login"),
        "action",
    )
    e["fields"] += [
        {
            "name": "Branche",
            "value": run.get("head_branch") or "—",
            "inline": True,
        },
        {
            "name": "Événement",
            "value": run.get("event") or "—",
            "inline": True,
        },
    ]
    e["timestamp"] = run.get("updated_at") or run.get("created_at")
    return e


def fork_embed(repo, fork):
    owner = (fork.get("owner") or {}).get("login") or "inconnu"
    fork_name = fork.get("full_name") or "?"
    fork_url = fork.get("html_url") or f"https://github.com/{fork_name}"

    e = _base(
        "Nouveau fork",
        fork_url,
        f"Le dépôt a été forké vers [{fork_name}]({fork_url}).",
        repo,
        owner,
        "fork",
    )
    e["timestamp"] = fork.get("created_at")
    return e


def star_embed(repo, star):
    user = (star.get("user") or {}).get("login") or "inconnu"
    url = f"https://github.com/{repo}/stargazers"

    e = _base(
        "Nouvelle étoile",
        url,
        f"**{user}** vient d’ajouter une étoile au dépôt.",
        repo,
        user,
        "star",
    )
    e["timestamp"] = star.get("starred_at")
    return e


def send(webhook_url, embed):
    r = requests.post(
        webhook_url,
        json={
            "embeds": [embed],
            "allowed_mentions": {"parse": []},
        },
        timeout=12,
    )
    r.raise_for_status()


def test(webhook_url):
    r = requests.post(
        webhook_url,
        json={
            "embeds": [{
                "title": "GitHub Discord Notifier",
                "description": "Le webhook Discord fonctionne correctement.",
                "author": {
                    "name": "GitHub Discord Notifier",
                    "icon_url": ICONS["action"],
                },
                "footer": {"text": "Message de test"},
            }],
            "allowed_mentions": {"parse": []},
        },
        timeout=12,
    )
    r.raise_for_status()
