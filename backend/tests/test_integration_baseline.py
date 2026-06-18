from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from backend.modules.rag.schemas import RagChunkMatch
from backend.tests.conftest import csrf_headers


@pytest.mark.asyncio
async def test_health_live(app_client: AsyncClient) -> None:
    response = await app_client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_celery_orchestration_tasks_registered() -> None:
    import backend.workers.orchestration  # noqa: F401 — register task names on the app
    from backend.workers.celery_app import celery_app

    expected = {
        "backend.workers.orchestration.run_task",
        "backend.workers.orchestration.memory_expiration_sweep",
        "backend.workers.orchestration.process_memory_ingest_jobs",
    }
    assert expected.issubset(set(celery_app.tasks.keys()))


def test_celery_beat_registers_memory_expiration_sweep() -> None:
    from backend.workers.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule or {}
    assert "memory-expiration-sweep" in schedule
    assert schedule["memory-expiration-sweep"]["task"] == (
        "backend.workers.orchestration.memory_expiration_sweep"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_cookie_flow(auth_client: AsyncClient, verified_user) -> None:
    from backend.core.config import settings

    user, _password = verified_user
    assert settings.ACCESS_COOKIE_NAME in auth_client.cookies

    me = await auth_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    payload = me.json()
    assert payload["id"] == user.id
    assert payload["email"] == user.email

    refresh = await auth_client.post("/api/v1/auth/refresh")
    assert refresh.status_code == 200
    assert refresh.json()["user"]["id"] == user.id

    logout = await auth_client.post("/api/v1/auth/logout")
    assert logout.status_code == 204

    unauthorized = await auth_client.get("/api/v1/auth/me")
    assert unauthorized.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_project_crud(auth_client: AsyncClient) -> None:
    slug = f"it-{uuid.uuid4().hex[:10]}"
    headers = csrf_headers(auth_client)

    create = await auth_client.post(
        "/api/v1/orchestration/projects",
        headers=headers,
        json={
            "name": "Integration Test Project",
            "slug": slug,
            "description": "Created by integration baseline test",
        },
    )
    assert create.status_code == 201, create.text
    project = create.json()
    project_id = project["id"]
    assert project["slug"] == slug

    fetched = await auth_client.get(f"/api/v1/orchestration/projects/{project_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == project_id

    listed = await auth_client.get("/api/v1/orchestration/projects")
    assert listed.status_code == 200
    assert any(item["id"] == project_id for item in listed.json())

    updated = await auth_client.patch(
        f"/api/v1/orchestration/projects/{project_id}",
        headers=headers,
        json={"description": "Updated by integration test"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Updated by integration test"

    deleted = await auth_client.delete(
        f"/api/v1/orchestration/projects/{project_id}",
        headers=headers,
    )
    assert deleted.status_code == 204

    missing = await auth_client.get(f"/api/v1/orchestration/projects/{project_id}")
    assert missing.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rag_search_endpoint_with_mocked_retriever(auth_client: AsyncClient) -> None:
    slug = f"rag-{uuid.uuid4().hex[:10]}"
    headers = csrf_headers(auth_client)

    project = await auth_client.post(
        "/api/v1/orchestration/projects",
        headers=headers,
        json={"name": "RAG Integration Project", "slug": slug},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    mock_match = RagChunkMatch(
        chunk_id="chunk-1",
        document_id="doc-1",
        title="README.md",
        content="Troop uses pgvector for retrieval.",
        chunk_index=0,
        score=0.92,
        metadata={"source_kind": "upload"},
    )

    try:
        with patch(
            "backend.modules.rag.router.RagService.retrieve",
            new=AsyncMock(return_value=[mock_match]),
        ):
            search = await auth_client.post(
                f"/api/v1/rag/projects/{project_id}/search",
                headers=headers,
                json={"query": "pgvector", "top_k": 3},
            )
        assert search.status_code == 200, search.text
        hits = search.json()
        assert len(hits) == 1
        assert hits[0]["chunk_id"] == "chunk-1"
        assert hits[0]["score"] == pytest.approx(0.92)
        assert "pgvector" in hits[0]["content"]
    finally:
        await auth_client.delete(
            f"/api/v1/orchestration/projects/{project_id}",
            headers=headers,
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_lifecycle_smoke(auth_client: AsyncClient) -> None:
    slug = f"run-{uuid.uuid4().hex[:10]}"
    headers = csrf_headers(auth_client)

    project = await auth_client.post(
        "/api/v1/orchestration/projects",
        headers=headers,
        json={"name": "Run Smoke Project", "slug": slug},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    task = await auth_client.post(
        f"/api/v1/orchestration/projects/{project_id}/tasks",
        headers=headers,
        json={"title": "Integration smoke task", "status": "queued"},
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]

    try:
        run = await auth_client.post(
            f"/api/v1/orchestration/projects/{project_id}/tasks/{task_id}/runs",
            headers=headers,
            json={"run_mode": "single_agent", "input_payload": {"prompt": "integration smoke"}},
        )
        assert run.status_code == 201, run.text
        run_id = run.json()["id"]
        assert run.json()["project_id"] == project_id
        assert run.json()["task_id"] == task_id
        assert run.json()["status"] in {"queued", "in_progress", "completed", "failed", "blocked"}

        fetched = await auth_client.get(f"/api/v1/orchestration/runs/{run_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == run_id

        events = await auth_client.get(f"/api/v1/orchestration/runs/{run_id}/events")
        assert events.status_code == 200
        assert isinstance(events.json(), list)
    finally:
        await auth_client.delete(
            f"/api/v1/orchestration/projects/{project_id}",
            headers=headers,
        )
