import os
import tempfile

import pytest

# Isolated data folder for tests (must be set before importing the app).
# To test against PostgreSQL + database storage, export VAULT_DATABASE_URL and VAULT_STORAGE_BACKEND=database.
os.environ["VAULT_DATA_DIR"] = tempfile.mkdtemp(prefix="vault_test_")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.drop_all(bind=engine)  # clean slate (relevant when pointing to a real Postgres)
    with TestClient(app) as test_client:
        yield test_client


def login(client, username, password):
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_headers(client):
    return login(client, os.getenv("VAULT_ADMIN_USER", "admin"), os.getenv("VAULT_ADMIN_PASSWORD", "Admin123*"))
