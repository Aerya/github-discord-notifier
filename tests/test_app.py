from cryptography.fernet import Fernet
from app import create_app
from app.db import get_db

def make_app(tmp_path):
    return create_app({'TESTING':True,'SECRET_KEY':'test','DATABASE':str(tmp_path/'test.db'),'ENCRYPTION_KEY':Fernet.generate_key().decode()})

def test_health(tmp_path):
    r=make_app(tmp_path).test_client().get('/health')
    assert r.status_code==200 and r.data==b'OK'

def test_redirects_to_bootstrap(tmp_path):
    r=make_app(tmp_path).test_client().get('/connexion')
    assert r.status_code==302 and '/initialisation' in r.headers['Location']


def test_global_configuration_is_shown_after_applying_it(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO users(username,password_hash) VALUES('admin','hash')")
        db.execute(
            "INSERT INTO repositories(id,full_name,owner_login,selected) "
            "VALUES(1,'owner/repo','owner',1)"
        )
        db.execute(
            "INSERT INTO discord_webhooks(name,url_encrypted) VALUES('Discord','secret')"
        )
        db.commit()
    with client.session_transaction() as session:
        session["user_id"] = 1
        session["_csrf"] = "csrf"

    response = client.post(
        "/depots/appliquer-global",
        data={
            "_csrf": "csrf",
            "actions_enabled": "on",
            "action_success": "on",
            "action_cancelled": "on",
            "webhook_id": "1",
        },
    )
    assert response.status_code == 302

    page = client.get("/depots").get_data(as_text=True)
    assert 'name="actions_enabled" checked' in page
    assert 'name="action_success" checked' in page
    assert 'name="action_cancelled" checked' in page
    assert 'name="action_failure" >' in page
    assert 'name="webhook_id" value="1" checked' in page
