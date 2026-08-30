from cryptography.fernet import Fernet
from app import create_app

def make_app(tmp_path):
    return create_app({'TESTING':True,'SECRET_KEY':'test','DATABASE':str(tmp_path/'test.db'),'ENCRYPTION_KEY':Fernet.generate_key().decode()})

def test_health(tmp_path):
    r=make_app(tmp_path).test_client().get('/health')
    assert r.status_code==200 and r.data==b'OK'

def test_redirects_to_bootstrap(tmp_path):
    r=make_app(tmp_path).test_client().get('/connexion')
    assert r.status_code==302 and '/initialisation' in r.headers['Location']
