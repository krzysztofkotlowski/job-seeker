from unittest.mock import patch

from fastapi.testclient import TestClient


def test_backup_unsupported_db(client: TestClient):
    with patch("app.routers.backup.get_database_url", return_value="sqlite:///test.db"):
        r = client.post("/api/v1/backup/create")
    assert r.status_code == 501
    body = r.json()
    assert body["error"]["code"] == "BACKUP_UNSUPPORTED_DB"

