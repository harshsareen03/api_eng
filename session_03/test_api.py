# test_api.py
import pytest
from fastapi.testclient import TestClient
from index import app, init_db, engine, SQLModel, Task

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    # recreate tables for tests (in-memory or test file)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)

def test_create_and_get_task():
    payload = {"title": "Write tests", "description": "Write tests for API"}
    r = client.post("/api/v1/tasks", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Write tests"
    tid = data["id"]

    r2 = client.get(f"/api/v1/tasks/{tid}")
    assert r2.status_code == 200
    assert r2.json()["id"] == tid

def test_validation_rejects_empty_title():
    payload = {"title": ""}
    r = client.post("/api/v1/tasks", json=payload)
    assert r.status_code == 422  # Unprocessable Entity (validation)


