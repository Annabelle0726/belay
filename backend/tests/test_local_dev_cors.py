# SPDX-License-Identifier: AGPL-3.0-only
"""Real datascience startup must capture local settings before pack imports."""

import os
import subprocess
import sys
from pathlib import Path


def test_datascience_launcher_cors_and_auth_without_database_initialization(tmp_path):
    script = r"""
import os, sys, types
from pathlib import Path
from app.local_dev import DemoHost, configure

# This focused startup test does not provision or connect a SQL database.
migration = types.ModuleType('app.conversations.migration')
migration.migrate = lambda engine: None
sys.modules[migration.__name__] = migration
host = DemoHost('http://127.0.0.1:8002')
host.origin = 'http://127.0.0.1:5175'
data = Path(sys.argv[1])
configure(host, data, True)
from app.config import settings
assert settings.cors_origins == [host.origin], settings.cors_origins
assert settings.auth_issuer == host.origin
assert settings.auth_public_key_file == str(data / 'public-key.pem')
assert settings.dialogue_enabled
from app.store import db
db.init_db = lambda: None
from sqlalchemy import event
@event.listens_for(db.engine, 'connect')
def forbid_sql(*args):
    raise AssertionError('This regression must not connect or initialize SQL')
from app.main import app
from fastapi.testclient import TestClient
client = TestClient(app)
requested = 'authorization,content-type,x-belay-class,x-belay-institution'
preflight = {'Origin':host.origin,'Access-Control-Request-Method':'GET',
             'Access-Control-Request-Headers':requested}
response = client.options('/api/curriculum',headers=preflight)
assert response.status_code == 200, response.text
assert response.headers['access-control-allow-origin'] == host.origin
allowed = response.headers['access-control-allow-headers'].lower()
assert all(header in allowed for header in requested.split(','))
foreign = client.options('/api/curriculum',headers={**preflight,'Origin':'http://127.0.0.1:5176'})
assert foreign.status_code == 400
assert 'access-control-allow-origin' not in foreign.headers
denied = client.get('/api/curriculum',headers={'Origin':host.origin})
assert denied.status_code == 401
assert denied.headers['access-control-allow-origin'] == host.origin
headers = {'Origin':host.origin,'Content-Type':'application/json',
           'Authorization':'Bearer '+host.token(),
           'X-Belay-Class':'local-class','X-Belay-Institution':'local-demo'}
response = client.get('/api/curriculum',headers=headers)
assert response.status_code == 200, response.text
assert response.headers['access-control-allow-origin'] == host.origin
ids = [e['id'] for m in response.json()['modules'] for e in m['exercises']]
assert ids == ['ds-foundations','ds-regression','ds-mlp'], ids
assert client.get('/api/curriculum',headers={**headers,'X-Belay-Class':'ungranted'}).status_code == 404
assert not (data / 'demo.sqlite3').exists()
print('Exact-origin preflight, authenticated original three exercises, denial, no SQL: passed')
"""
    env = dict(os.environ)
    for name in tuple(env):
        if name.startswith(("AUTH_", "DIALOGUE_", "CONTROLS_")):
            del env[name]
    env.update(
        TUTOR_PACK="datascience", CORS_ORIGINS="http://localhost:5173", BELAY_ENV="production"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
