"""Tests for the /api/ingest endpoint used by third-party services."""

import asyncio

import pytest
import pytest_asyncio
from datasette.app import Datasette
from sqlite_utils import Database as SqliteUtilsDatabase

from datasette_ca460.migrations import migrations


@pytest_asyncio.fixture
async def ds(monkeypatch):
    """Datasette with ca460 access granted to anyone, schema applied, and a
    stubbed default model list so the endpoint doesn't need real LLM providers."""

    # Pin a single model for both ca460 purposes so the endpoint always
    # resolves a default.
    datasette = Datasette(
        memory=True,
        config={
            "permissions": {
                "datasette-ca460-access": {"id": "*"},
                "datasette-ca460-ingest": {"id": "*"},
            },
            "plugins": {
                "datasette-llm": {
                    "purposes": {
                        "ca460-classify": {"models": ["gemini/gemini-3-flash-preview"]},
                        "ca460-parse": {"models": ["gemini/gemini-3-flash-preview"]},
                    }
                }
            },
        },
    )
    await datasette.invoke_startup()

    db = datasette.get_database("_memory")

    def _apply(conn):
        migrations.apply(SqliteUtilsDatabase(conn))

    await db.execute_write_fn(_apply)

    # Intercept the background task so the test doesn't hit DocumentCloud.
    from datasette_ca460 import routes
    recorded = {}

    async def fake_run(datasette, database_name, sync_job_id, document_ids, *args, **kwargs):
        recorded["called"] = True
        recorded["database_name"] = database_name
        recorded["sync_job_id"] = sync_job_id
        recorded["document_ids"] = document_ids
        recorded["actor"] = kwargs.get("actor")

    monkeypatch.setattr(routes, "run_sync_documents_in_background", fake_run)

    # Also stub the model listing so the endpoint doesn't need real LLM keys.
    class FakeModel:
        def __init__(self, mid):
            self.model_id = mid

    class FakeLLM:
        def __init__(self, datasette):
            pass

        async def models(self, purpose=None, actor=None):
            return [FakeModel("gemini/gemini-3-flash-preview")]

    monkeypatch.setattr(routes, "LLM", FakeLLM)

    return datasette, recorded


@pytest.fixture
def auth_cookies():
    def _cookies(ds):
        return {"ds_actor": ds.sign({"a": {"id": "service"}}, "actor")}
    return _cookies


@pytest.mark.asyncio
async def test_ingest_document_url_creates_sync_job(ds, auth_cookies):
    datasette, recorded = ds
    response = await datasette.client.post(
        "/_memory/-/ca460/api/ingest",
        json={"url": "https://www.documentcloud.org/documents/12345-my-doc"},
        cookies=auth_cookies(datasette),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document_ids"] == [12345]
    assert body["sync_job_id"]

    # Let the background asyncio.create_task run
    await asyncio.sleep(0)

    # Background task was triggered with the resolved ID + actor
    assert recorded["called"] is True
    assert recorded["document_ids"] == [12345]
    assert recorded["sync_job_id"] == body["sync_job_id"]
    assert recorded["actor"] == {"id": "service"}

    # A sync_jobs row was created
    db = datasette.get_database("_memory")

    def _read(conn):
        return conn.execute(
            "SELECT id, page_type_model, parser_model FROM datasette_ca460_sync_jobs WHERE id = ?",
            (body["sync_job_id"],),
        ).fetchone()

    row = await db.execute_write_fn(_read)
    assert row is not None
    assert row[1] == "gemini/gemini-3-flash-preview"
    assert row[2] == "gemini/gemini-3-flash-preview"


@pytest.mark.asyncio
async def test_ingest_rejects_non_documentcloud_url(ds, auth_cookies):
    datasette, _ = ds
    response = await datasette.client.post(
        "/_memory/-/ca460/api/ingest",
        json={"url": "https://example.com/nope"},
        cookies=auth_cookies(datasette),
    )
    assert response.status_code == 400
    assert "Unrecognised" in response.json()["error"]


@pytest.mark.asyncio
async def test_ingest_rejects_project_url(ds, auth_cookies):
    datasette, _ = ds
    response = await datasette.client.post(
        "/_memory/-/ca460/api/ingest",
        json={"url": "https://www.documentcloud.org/projects/my-proj-67890"},
        cookies=auth_cookies(datasette),
    )
    assert response.status_code == 400
    assert "document URLs" in response.json()["error"]


@pytest.mark.asyncio
async def test_ingest_requires_authorization(ds):
    """Without an actor, the datasette-ca460-ingest permission denies access."""
    datasette, _ = ds
    response = await datasette.client.post(
        "/_memory/-/ca460/api/ingest",
        json={"url": "https://www.documentcloud.org/documents/12345-x"},
    )
    assert response.status_code == 403


@pytest_asyncio.fixture
async def ds_access_only(monkeypatch):
    """Datasette granting only datasette-ca460-access (no ingest)."""
    datasette = Datasette(
        memory=True,
        config={
            "permissions": {"datasette-ca460-access": {"id": "*"}},
        },
    )
    await datasette.invoke_startup()

    # Stub out the background task + LLM so the test never reaches DC.
    from datasette_ca460 import routes

    async def fake_run(*args, **kwargs):
        pass

    class FakeModel:
        model_id = "fake"

    class FakeLLM:
        def __init__(self, datasette):
            pass

        async def models(self, purpose=None, actor=None):
            return [FakeModel()]

    monkeypatch.setattr(routes, "run_sync_documents_in_background", fake_run)
    monkeypatch.setattr(routes, "LLM", FakeLLM)
    return datasette


@pytest.mark.asyncio
async def test_ingest_requires_ingest_permission_not_just_access(ds_access_only):
    """An actor with only datasette-ca460-access should still be 403 on ingest."""
    cookies = {"ds_actor": ds_access_only.sign({"a": {"id": "viewer"}}, "actor")}
    response = await ds_access_only.client.post(
        "/_memory/-/ca460/api/ingest",
        json={"url": "https://www.documentcloud.org/documents/12345-x"},
        cookies=cookies,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_ingest_accepts_model_overrides(ds, auth_cookies):
    datasette, _ = ds
    response = await datasette.client.post(
        "/_memory/-/ca460/api/ingest",
        json={
            "url": "https://www.documentcloud.org/documents/777-x",
            "page_type_model": "override-classify",
            "parser_model": "override-parse",
        },
        cookies=auth_cookies(datasette),
    )
    assert response.status_code == 200

    db = datasette.get_database("_memory")
    sync_job_id = response.json()["sync_job_id"]

    def _read(conn):
        return conn.execute(
            "SELECT page_type_model, parser_model FROM datasette_ca460_sync_jobs WHERE id = ?",
            (sync_job_id,),
        ).fetchone()

    row = await db.execute_write_fn(_read)
    assert row[0] == "override-classify"
    assert row[1] == "override-parse"
