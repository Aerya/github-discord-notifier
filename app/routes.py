from flask import Blueprint,render_template,request,redirect,url_for,session,flash,abort,current_app
from .db import get_db,setting_get,setting_set
from .security import hash_password,verify_password,csrf_token,require_csrf,login_required,encrypt_secret,decrypt_secret,validate_discord_webhook
from .github_client import authenticated_user,list_repositories,rate_limit
from .discord import test as discord_test_message
from .poller import poll_once

bp=Blueprint('main',__name__); bp.add_app_template_global(csrf_token,'csrf_token')
def _count_users(): return get_db().execute('SELECT COUNT(*) c FROM users').fetchone()['c']
def _store_repositories(repos):
    db=get_db()
    for r in repos:
        db.execute('INSERT INTO repositories(id,full_name,private,owner_login,html_url) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET full_name=excluded.full_name,private=excluded.private,owner_login=excluded.owner_login,html_url=excluded.html_url',(r['id'],r['full_name'],int(bool(r.get('private'))),(r.get('owner') or {}).get('login',''),r.get('html_url')))
    db.commit()

@bp.get('/health')
def health(): return 'OK',200,{'Content-Type':'text/plain; charset=utf-8'}
@bp.route('/initialisation',methods=['GET','POST'])
def bootstrap():
    if _count_users(): return redirect(url_for('main.login'))
    if request.method=='POST':
        require_csrf(); u=request.form.get('username','').strip(); p=request.form.get('password',''); c=request.form.get('confirm','')
        if not 3<=len(u)<=64: flash('Le nom d’utilisateur doit contenir entre 3 et 64 caractères.','error')
        elif len(p)<12: flash('Le mot de passe doit contenir au moins 12 caractères.','error')
        elif p!=c: flash('Les mots de passe ne correspondent pas.','error')
        else:
            db=get_db(); db.execute('INSERT INTO users(username,password_hash) VALUES(?,?)',(u,hash_password(p))); db.commit(); flash('Compte administrateur créé.','success'); return redirect(url_for('main.login'))
    return render_template('bootstrap.html')
@bp.route('/connexion',methods=['GET','POST'])
def login():
    if not _count_users(): return redirect(url_for('main.bootstrap'))
    if session.get('user_id'): return redirect(url_for('main.dashboard'))
    if request.method=='POST':
        require_csrf(); row=get_db().execute('SELECT * FROM users WHERE username=?',(request.form.get('username','').strip(),)).fetchone()
        if row and verify_password(row['password_hash'],request.form.get('password','')):
            session.clear(); session['user_id']=row['id']; session['username']=row['username']; session.permanent=True; csrf_token(); return redirect(url_for('main.dashboard'))
        flash('Identifiants incorrects.','error')
    return render_template('login.html')
@bp.post('/deconnexion')
@login_required
def logout(): require_csrf(); session.clear(); return redirect(url_for('main.login'))
@bp.get('/')
@login_required
def dashboard():
    db=get_db(); counts={'repos':db.execute('SELECT COUNT(*) c FROM repositories WHERE selected=1').fetchone()['c'],'webhooks':db.execute('SELECT COUNT(*) c FROM discord_webhooks').fetchone()['c'],'sent':db.execute("SELECT COUNT(*) c FROM event_logs WHERE result='sent'").fetchone()['c'],'errors':db.execute("SELECT COUNT(*) c FROM event_logs WHERE result='failed'").fetchone()['c']}; recent=db.execute('SELECT * FROM event_logs ORDER BY id DESC LIMIT 10').fetchall(); return render_template('dashboard.html',counts=counts,recent=recent,github_login=setting_get('github_login'))
@bp.route('/github',methods=['GET','POST'])
@login_required
def github():
    if request.method=='POST':
        require_csrf(); token=request.form.get('token','').strip()
        try: user,_=authenticated_user(token)
        except Exception: flash('Connexion GitHub refusée. Vérifiez le token.','error')
        else:
            setting_set('github_token',encrypt_secret(token)); setting_set('github_login',user['login'])
            try: repos=list_repositories(token); _store_repositories(repos); msg=f"Compte GitHub connecté : {user['login']} · {len(repos)} dépôt(s) trouvés."
            except Exception: msg=f"Compte GitHub connecté : {user['login']}. La synchronisation des dépôts pourra être relancée."
            flash(msg,'success'); return redirect(url_for('main.repositories'))
    rate=None
    if setting_get('github_token'):
        try: rate=rate_limit(decrypt_secret(setting_get('github_token')))
        except Exception: pass
    return render_template('github.html',connected=bool(setting_get('github_token')),github_login=setting_get('github_login'),poll_interval=setting_get('poll_interval','300'),rate=rate)
@bp.post('/github/deconnecter')
@login_required
def github_disconnect(): require_csrf(); setting_set('github_token',''); setting_set('github_login',''); flash('Compte GitHub déconnecté.','success'); return redirect(url_for('main.github'))
@bp.post('/github/intervalle')
@login_required
def github_interval():
    require_csrf()
    try: v=int(request.form.get('poll_interval','300'))
    except ValueError: v=300
    setting_set('poll_interval',max(60,min(3600,v))); flash('Intervalle enregistré.','success'); return redirect(url_for('main.github'))
@bp.get('/depots')
@login_required
def repositories():
    db=get_db(); rows=db.execute('SELECT * FROM repositories ORDER BY full_name COLLATE NOCASE').fetchall(); hooks=db.execute('SELECT id,name FROM discord_webhooks ORDER BY name').fetchall(); links=db.execute('SELECT repository_id,webhook_id FROM repository_webhooks').fetchall(); m={}
    for x in links: m.setdefault(x['repository_id'],set()).add(x['webhook_id'])
    return render_template('repositories.html',repositories=rows,webhooks=hooks,link_map=m)
@bp.post('/depots/synchroniser')
@login_required
def sync_repositories():
    require_csrf(); enc=setting_get('github_token')
    if not enc: flash('Connectez d’abord GitHub.','error'); return redirect(url_for('main.github'))
    try: repos=list_repositories(decrypt_secret(enc))
    except Exception: flash('Impossible de récupérer les dépôts GitHub.','error'); return redirect(url_for('main.github'))
    _store_repositories(repos); flash(f'{len(repos)} dépôt(s) synchronisé(s).','success'); return redirect(url_for('main.repositories'))
@bp.post('/depots/<int:repo_id>/enregistrer')
@login_required
def repository_save(repo_id):
    require_csrf(); db=get_db(); repo=db.execute('SELECT * FROM repositories WHERE id=?',(repo_id,)).fetchone()
    if not repo: abort(404)
    db.execute('UPDATE repositories SET selected=?,issues_enabled=?,prs_enabled=?,actions_enabled=?,forks_enabled=?,stars_enabled=?,ignore_own_prs=?,action_success=?,action_failure=?,action_cancelled=? WHERE id=?',(int('selected'in request.form),int('issues_enabled'in request.form),int('prs_enabled'in request.form),int('actions_enabled'in request.form),int('forks_enabled'in request.form),int('stars_enabled'in request.form),int('ignore_own_prs'in request.form),int('action_success'in request.form),int('action_failure'in request.form),int('action_cancelled'in request.form),repo_id))
    db.execute('DELETE FROM repository_webhooks WHERE repository_id=?',(repo_id,))
    for wid in request.form.getlist('webhook_id'):
        if wid.isdigit(): db.execute('INSERT OR IGNORE INTO repository_webhooks(repository_id,webhook_id) VALUES(?,?)',(repo_id,int(wid)))
    db.commit(); flash(f"Configuration de {repo['full_name']} enregistrée.",'success'); return redirect(url_for('main.repositories')+f'#repo-{repo_id}')
@bp.route('/discord',methods=['GET','POST'])
@login_required
def discord():
    db=get_db()
    if request.method=='POST':
        require_csrf(); name=request.form.get('name','').strip(); url=request.form.get('url','').strip()
        if not 2<=len(name)<=80: flash('Nom de webhook invalide.','error')
        elif not validate_discord_webhook(url): flash('URL de webhook Discord invalide.','error')
        else: db.execute('INSERT INTO discord_webhooks(name,url_encrypted) VALUES(?,?)',(name,encrypt_secret(url))); db.commit(); flash('Webhook Discord ajouté.','success'); return redirect(url_for('main.discord'))
    return render_template('discord.html',webhooks=db.execute('SELECT id,name,created_at FROM discord_webhooks ORDER BY name').fetchall())
@bp.post('/discord/<int:webhook_id>/tester')
@login_required
def discord_test(webhook_id):
    require_csrf(); row=get_db().execute('SELECT * FROM discord_webhooks WHERE id=?',(webhook_id,)).fetchone()
    if not row: abort(404)
    try: discord_test_message(decrypt_secret(row['url_encrypted'])); flash('Message de test envoyé.','success')
    except Exception: flash('Échec du test Discord.','error')
    return redirect(url_for('main.discord'))
@bp.post('/discord/<int:webhook_id>/supprimer')
@login_required
def discord_delete(webhook_id): require_csrf(); db=get_db(); db.execute('DELETE FROM discord_webhooks WHERE id=?',(webhook_id,)); db.commit(); flash('Webhook supprimé.','success'); return redirect(url_for('main.discord'))
@bp.get('/journaux')
@login_required
def logs(): return render_template('logs.html',logs=get_db().execute('SELECT * FROM event_logs ORDER BY id DESC LIMIT 500').fetchall())
@bp.post('/journaux/vider')
@login_required
def logs_clear(): require_csrf(); db=get_db(); db.execute('DELETE FROM event_logs'); db.commit(); flash('Journaux vidés.','success'); return redirect(url_for('main.logs'))
@bp.post('/verifier-maintenant')
@login_required
def poll_now(): require_csrf(); poll_once(current_app._get_current_object()); flash('Vérification GitHub terminée.','success'); return redirect(url_for('main.dashboard'))
@bp.route('/compte',methods=['GET','POST'])
@login_required
def account():
    if request.method=='POST':
        require_csrf(); db=get_db(); user=db.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone(); cur=request.form.get('current_password',''); new=request.form.get('new_password',''); conf=request.form.get('confirm_password','')
        if not verify_password(user['password_hash'],cur): flash('Mot de passe actuel incorrect.','error')
        elif len(new)<12: flash('Le nouveau mot de passe doit contenir au moins 12 caractères.','error')
        elif new!=conf: flash('Les mots de passe ne correspondent pas.','error')
        else: db.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(new),user['id'])); db.commit(); session.clear(); flash('Mot de passe modifié. Reconnectez-vous.','success'); return redirect(url_for('main.login'))
    return render_template('account.html')
