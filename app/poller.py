import threading
import time

from .db import get_db, setting_get
from .security import decrypt_secret
from .github_client import recent_issues, recent_pulls, recent_forks, recent_stars, recent_workflow_runs
from .discord import issue_embed, pr_embed, fork_embed, star_embed, action_embed, send

_thread = None
_stop = threading.Event()

def _seen(db, key):
    return db.execute('SELECT 1 FROM seen_events WHERE event_key=?', (key,)).fetchone() is not None

def _mark(db, key):
    db.execute('INSERT OR IGNORE INTO seen_events(event_key) VALUES(?)', (key,))

def _log(db, repo, event_type, result, title=None, actor=None, reason=None):
    db.execute('INSERT INTO event_logs(repository,event_type,result,title,actor,reason) VALUES(?,?,?,?,?,?)', (repo,event_type,result,title,actor,reason))

def _urls(db, repo_id):
    rows = db.execute('SELECT d.url_encrypted FROM discord_webhooks d JOIN repository_webhooks rw ON rw.webhook_id=d.id WHERE rw.repository_id=?', (repo_id,)).fetchall()
    return [decrypt_secret(r['url_encrypted']) for r in rows]

def _notify(db, repo, typ, key, embed, title, actor):
    if _seen(db, key):
        return
    urls = _urls(db, repo['id'])
    if not urls:
        _mark(db, key)
        _log(db, repo['full_name'], typ, 'ignored', title, actor, 'Aucun webhook Discord associé')
        db.commit()
        return
    sent = 0
    for url in urls:
        try:
            send(url, embed)
            sent += 1
        except Exception:
            _log(db, repo['full_name'], typ, 'failed', title, actor, 'Échec d’envoi Discord')
    _mark(db, key)
    if sent:
        _log(db, repo['full_name'], typ, 'sent', title, actor, f'{sent} destination(s)')
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

def poll_once(app):
    with app.app_context():
        db = get_db()
        token_enc = setting_get('github_token')
        if not token_enc:
            return
        token = decrypt_secret(token_enc)
        login = (setting_get('github_login', '') or '').lower()
        repos = db.execute('SELECT * FROM repositories WHERE selected=1 ORDER BY full_name').fetchall()
        for repo in repos:
            full = repo['full_name']
            try:
                if repo['issues_enabled']:
                    items = recent_issues(token, full)
                    key = lambda x: f'issue:{repo["id"]}:{x["id"]}'
                    if not _baseline(db, repo, 'issues', items, key):
                        for x in reversed(items):
                            _notify(db, repo, 'issues', key(x), issue_embed(full,x), x.get('title'), (x.get('user') or {}).get('login'))
                if repo['prs_enabled']:
                    items = recent_pulls(token, full)
                    key = lambda x: f'pr:{repo["id"]}:{x["id"]}'
                    if not _baseline(db, repo, 'prs', items, key):
                        for x in reversed(items):
                            actor=(x.get('user') or {}).get('login')
                            k=key(x)
                            if _seen(db,k):
                                continue
                            if repo['ignore_own_prs'] and actor and actor.lower()==login:
                                _mark(db,k); _log(db,full,'prs','ignored',x.get('title'),actor,'PR créée par mon compte GitHub'); db.commit()
                            else:
                                _notify(db,repo,'prs',k,pr_embed(full,x),x.get('title'),actor)
                if repo['forks_enabled']:
                    items=recent_forks(token,full); key=lambda x:f'fork:{repo["id"]}:{x["id"]}'
                    if not _baseline(db,repo,'forks',items,key):
                        for x in reversed(items): _notify(db,repo,'forks',key(x),fork_embed(full,x),x.get('full_name'),(x.get('owner') or {}).get('login'))
                if repo['stars_enabled']:
                    items=recent_stars(token,full); key=lambda x:f'star:{repo["id"]}:{(x.get("user") or {}).get("id")}:{x.get("starred_at")}'
                    if not _baseline(db,repo,'stars',items,key):
                        for x in reversed(items): _notify(db,repo,'stars',key(x),star_embed(full,x),'Nouvelle étoile',(x.get('user') or {}).get('login'))
                if repo['actions_enabled']:
                    items=[x for x in recent_workflow_runs(token,full) if x.get('status')=='completed']; key=lambda x:f'action:{repo["id"]}:{x["id"]}:{x.get("run_attempt",1)}'
                    if not _baseline(db,repo,'actions',items,key):
                        for x in reversed(items):
                            k=key(x)
                            if _seen(db,k): continue
                            c=x.get('conclusion')
                            wanted=(c=='success' and repo['action_success']) or (c=='failure' and repo['action_failure']) or (c=='cancelled' and repo['action_cancelled'])
                            if not wanted: _mark(db,k); db.commit(); continue
                            _notify(db,repo,'actions',k,action_embed(full,x),x.get('name'),(x.get('actor') or {}).get('login'))
                db.execute('UPDATE repositories SET last_sync_at=CURRENT_TIMESTAMP WHERE id=?',(repo['id'],)); db.commit()
            except Exception as exc:
                _log(db,full,'poll','failed',reason=f'Erreur GitHub: {type(exc).__name__}'); db.commit()
        db.execute('DELETE FROM event_logs WHERE id NOT IN (SELECT id FROM event_logs ORDER BY id DESC LIMIT 2000)'); db.commit()

def _loop(app):
    time.sleep(3)
    while not _stop.is_set():
        try: poll_once(app)
        except Exception: app.logger.exception('Erreur du poller')
        with app.app_context():
            try: interval=max(60,min(3600,int(setting_get('poll_interval','300'))))
            except Exception: interval=300
        _stop.wait(interval)

def start_poller(app):
    global _thread
    if app.config.get('TESTING'): return
    if _thread and _thread.is_alive(): return
    _thread=threading.Thread(target=_loop,args=(app,),name='github-poller',daemon=True); _thread.start()
