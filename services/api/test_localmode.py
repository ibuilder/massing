"""Single-operator local mode: admin features open without a login.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_localmode.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./localmode_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_local"
os.environ["AEC_LOCAL_MODE"] = "1"          # must be set before importing the app
os.environ.pop("AEC_RBAC", None)
for f in ("./localmode_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    # capabilities advertises local mode so the web can drop Sign-in + open admin UI
    assert c.get("/capabilities").json()["local_mode"] is True

    # NO login/token — admin-gated endpoints are open to the local operator
    lst = c.get("/connections").json()
    assert "connections" in lst and any(x["id"] == "local" for x in lst["connections"]), lst
    made = c.post("/connections", json={"name": "Local PG", "type": "postgres",
                                        "config": {"dsn": "postgresql://u:p@h:5432/d"}})
    assert made.status_code == 201, (made.status_code, made.text)
    assert c.delete(f"/connections/{made.json()['id']}").json()["ok"]

    # settings (admin-gated) also open without login
    s = c.get("/settings/integrations")
    assert s.status_code == 200 and "groups" in s.json(), (s.status_code, s.text)

    print("LOCAL MODE OK - capabilities.local_mode, connections + settings open without login")
