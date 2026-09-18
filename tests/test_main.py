from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_and_get_task():
    response = client.post("/tasks", json={"title": "Deploy with ArgoCD"})
    assert response.status_code == 201
    task = response.json()
    assert task["title"] == "Deploy with ArgoCD"
    assert task["done"] is False

    response = client.get(f"/tasks/{task['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == task["id"]


def test_delete_task():
    response = client.post("/tasks", json={"title": "Temp task"})
    task_id = response.json()["id"]

    response = client.delete(f"/tasks/{task_id}")
    assert response.status_code == 204

    response = client.get(f"/tasks/{task_id}")
    assert response.status_code == 404


def test_get_missing_task():
    response = client.get("/tasks/does-not-exist")
    assert response.status_code == 404
