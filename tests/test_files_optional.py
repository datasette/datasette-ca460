"""Tests for datasette-files being an optional dependency."""

import pytest
import pytest_asyncio
from datasette.app import Datasette
from sqlite_utils import Database as SqliteUtilsDatabase

from datasette_ca460 import files_storage
from datasette_ca460.migrations import migrations


@pytest_asyncio.fixture
async def ds():
    datasette = Datasette(
        memory=True,
        config={"permissions": {"ca460_access": {"id": "*"}}},
    )
    await datasette.invoke_startup()
    db = datasette.get_database("_memory")

    def _apply(conn):
        migrations.apply(SqliteUtilsDatabase(conn))

    await db.execute_write_fn(_apply)
    return datasette


@pytest.fixture
def auth_cookies(ds):
    return {"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")}


@pytest.fixture
def files_unavailable(monkeypatch):
    """Force is_files_available() to return False regardless of install state."""
    monkeypatch.setattr(files_storage, "is_files_available", lambda: False)
    # routes.py imports the symbol directly — patch there too
    from datasette_ca460 import routes
    monkeypatch.setattr(routes, "is_files_available", lambda: False)


def test_is_files_available_installed():
    """In this test env datasette-files is in the dev group, so this returns True."""
    files_storage.is_files_available.cache_clear()
    assert files_storage.is_files_available() is True


@pytest.mark.asyncio
async def test_process_file_id_returns_501_when_files_unavailable(ds, auth_cookies, files_unavailable):
    response = await ds.client.post(
        "/_memory/-/ca460/api/process",
        json={
            "file_id": "df-fake",
            "page_type_model": "m1",
            "parser_model": "m2",
        },
        cookies=auth_cookies,
    )
    assert response.status_code == 501
    body = response.json()
    assert "datasette-ca460[files]" in body["error"]


@pytest.mark.asyncio
async def test_process_document_id_still_works_without_files(ds, auth_cookies, files_unavailable):
    """Re-processing an existing document doesn't need datasette-files."""
    db = ds.get_database("_memory")

    def _create_doc(conn):
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES ('documentcloud', 1, '{}') RETURNING id"
        )
        doc_id = cursor.fetchone()[0]
        conn.commit()
        return doc_id

    doc_id = await db.execute_write_fn(_create_doc)

    response = await ds.client.post(
        "/_memory/-/ca460/api/process",
        json={
            "document_id": doc_id,
            "page_type_model": "m1",
            "parser_model": "m2",
        },
        cookies=auth_cookies,
    )
    # 200 means it accepted the job (it'll fail in the background worker,
    # but that's not the path we're testing here).
    assert response.status_code == 200
    assert response.json()["document_id"] == doc_id


@pytest.mark.asyncio
async def test_index_view_injects_files_available_flag(ds, auth_cookies):
    """The pageData blob should carry files_available for the frontend."""
    response = await ds.client.get("/_memory/-/ca460", cookies=auth_cookies)
    assert response.status_code == 200
    # pageData is emitted as an inline JSON script tag
    assert '"files_available": true' in response.text or '"files_available":true' in response.text


@pytest.mark.asyncio
async def test_index_view_files_available_false_when_unavailable(ds, auth_cookies, files_unavailable):
    response = await ds.client.get("/_memory/-/ca460", cookies=auth_cookies)
    assert response.status_code == 200
    assert '"files_available": false' in response.text or '"files_available":false' in response.text
