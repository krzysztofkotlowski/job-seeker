from fastapi.testclient import TestClient


def test_backup_unsupported_db(monkeypatch, client: TestClient):
    # Force a non-postgres DATABASE_URL to trigger the friendly error.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
    from importlib import reload
    import app.routers.backup as backup_module

    reload(backup_module)

    r = client.post("/api/v1/backup/create")
    assert r.status_code == 501
    body = r.json()
    assert body["error"]["code"] == "BACKUP_UNSUPPORTED_DB"

