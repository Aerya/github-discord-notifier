import requests

def _base(title, url, description, repo, actor, emoji):
    return {
        'title': f'{emoji} {title}',
        'url': url,
        'description': (description or '')[:3500],
        'fields': [
            {'name': 'Dépôt', 'value': repo, 'inline': True},
            {'name': 'Auteur', 'value': actor or 'inconnu', 'inline': True},
        ],
        'footer': {'text': 'GitHub Discord Notifier'},
    }

def issue_embed(repo, issue):
    e = _base(f"Nouvelle issue #{issue['number']}", issue['html_url'], issue.get('title'), repo, issue.get('user', {}).get('login'), '🐛')
    labels = [x.get('name') for x in issue.get('labels', []) if x.get('name')]
    if labels:
        e['fields'].append({'name': 'Labels', 'value': ', '.join(labels)[:1024], 'inline': False})
    e['timestamp'] = issue.get('created_at')
    return e

def pr_embed(repo, pr):
    e = _base(f"Nouvelle Pull Request #{pr['number']}", pr['html_url'], pr.get('title'), repo, pr.get('user', {}).get('login'), '🔀')
    e['fields'].append({'name': 'Branches', 'value': f"{pr.get('head', {}).get('ref', '?')} → {pr.get('base', {}).get('ref', '?')}", 'inline': False})
    e['timestamp'] = pr.get('created_at')
    return e

def action_embed(repo, run):
    conclusion = run.get('conclusion') or run.get('status') or 'inconnu'
    icon = {'success':'✅','failure':'❌','cancelled':'⏹️'}.get(conclusion, '⚙️')
    e = _base(f"Action {conclusion} — {run.get('name','Workflow')}", run.get('html_url'), f"Workflow terminé : **{conclusion}**", repo, (run.get('actor') or {}).get('login'), icon)
    e['fields'] += [
        {'name':'Branche','value':run.get('head_branch') or '—','inline':True},
        {'name':'Événement','value':run.get('event') or '—','inline':True},
    ]
    e['timestamp'] = run.get('updated_at') or run.get('created_at')
    return e

def fork_embed(repo, fork):
    owner = (fork.get('owner') or {}).get('login') or 'inconnu'
    e = _base('Nouveau fork', fork.get('html_url'), f"Le dépôt a été forké vers **{fork.get('full_name','?')}**.", repo, owner, '🍴')
    e['timestamp'] = fork.get('created_at')
    return e

def star_embed(repo, star):
    user = (star.get('user') or {}).get('login') or 'inconnu'
    e = _base('Nouvelle étoile', f'https://github.com/{repo}/stargazers', f'**{user}** vient d’ajouter une étoile au dépôt.', repo, user, '⭐')
    e['timestamp'] = star.get('starred_at')
    return e

def send(webhook_url, embed):
    r = requests.post(webhook_url, json={'embeds':[embed], 'allowed_mentions':{'parse':[]}}, timeout=12)
    r.raise_for_status()

def test(webhook_url):
    r = requests.post(webhook_url, json={'embeds':[{'title':'✅ GitHub Discord Notifier','description':'Le webhook Discord fonctionne correctement.','footer':{'text':'Message de test'}}], 'allowed_mentions':{'parse':[]}}, timeout=12)
    r.raise_for_status()
