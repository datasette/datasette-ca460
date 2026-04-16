"""Tests for the DocumentSource abstraction."""

import json

import pytest
import pytest_asyncio
from datasette.app import Datasette

from datasette_ca460.sources import (
    DocumentCloudSource,
    UploadSource,
    get_source_for_document,
    get_source_for_page,
)
from sqlite_utils import Database as SqliteUtilsDatabase

from datasette_ca460.migrations import migrations


@pytest_asyncio.fixture
async def ds():
    """Create a Datasette instance with an in-memory database and schema."""
    datasette = Datasette(memory=True)
    db = datasette.get_database("_memory")

    def _apply_migrations(conn):
        migrations.apply(SqliteUtilsDatabase(conn))

    await db.execute_write_fn(_apply_migrations)
    return datasette, db


@pytest.mark.asyncio
async def test_upload_source_store_page(ds):
    _datasette, db = ds
    source = UploadSource()

    # Create a document
    def _create_doc(conn):
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES (?, ?, ?) RETURNING id",
            ("upload", 1, json.dumps({"title": "test.pdf"})),
        )
        doc_id = cursor.fetchone()[0]
        conn.commit()
        return doc_id

    doc_id = await db.execute_write_fn(_create_doc)

    # Store a page with image blob
    image_bytes = b"\x89PNG fake image data"
    page_id = await source.store_page(db, doc_id, 1, image=image_bytes)
    assert page_id is not None

    # Verify stored correctly
    def _check(conn):
        cursor = conn.execute(
            "SELECT image FROM datasette_ca460_pages WHERE id = ?", (page_id,)
        )
        return cursor.fetchone()[0]

    assert await db.execute_write_fn(_check) == image_bytes


@pytest.mark.asyncio
async def test_upload_source_get_page_image_bytes(ds):
    _datasette, db = ds
    source = UploadSource()

    image_bytes = b"\x89PNG test image"

    def _create(conn):
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES (?, ?, ?) RETURNING id",
            ("upload", 1, "{}"),
        )
        doc_id = cursor.fetchone()[0]
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_pages(document_id, page_number, image) VALUES (?, ?, ?) RETURNING id",
            (doc_id, 1, image_bytes),
        )
        page_id = cursor.fetchone()[0]
        conn.commit()
        return page_id

    page_id = await db.execute_write_fn(_create)

    result = await source.get_page_image_bytes(db, page_id)
    assert result == image_bytes


@pytest.mark.asyncio
async def test_upload_source_image_response_returns_bytes(ds):
    _datasette, db = ds
    source = UploadSource()

    image_bytes = b"\x89PNG test image"

    def _create(conn):
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES (?, ?, ?) RETURNING id",
            ("upload", 1, "{}"),
        )
        doc_id = cursor.fetchone()[0]
        conn.execute(
            "INSERT INTO datasette_ca460_pages(document_id, page_number, image) VALUES (?, ?, ?)",
            (doc_id, 1, image_bytes),
        )
        conn.commit()
        return doc_id

    doc_id = await db.execute_write_fn(_create)

    data, content_type = await source.get_image_response_for_page(db, doc_id, 1)
    assert data == image_bytes
    assert content_type == "image/png"


@pytest.mark.asyncio
async def test_upload_source_thumbnail_url(ds):
    source = UploadSource()
    assert source.thumbnail_url({"title": "test"}, 1) is None


@pytest.mark.asyncio
async def test_upload_source_embed_url(ds):
    source = UploadSource()
    assert source.embed_url({"title": "test"}) is None


@pytest.mark.asyncio
async def test_upload_source_pdf_response_redirect(ds):
    _datasette, db = ds
    source = UploadSource()

    def _create(conn):
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES (?, ?, ?) RETURNING id",
            ("upload", 1, "{}"),
        )
        doc_id = cursor.fetchone()[0]
        conn.execute(
            "INSERT INTO datasette_ca460_document_files(document_id, filename, file_id) VALUES (?, ?, ?)",
            (doc_id, "test.pdf", "df-pdf123"),
        )
        conn.commit()
        return doc_id

    doc_id = await db.execute_write_fn(_create)

    url, filename = await source.get_pdf_response(db, doc_id)
    assert url == "/-/files/df-pdf123/download"
    assert filename is None  # signals redirect


@pytest.mark.asyncio
async def test_dc_source_store_url_not_blob(ds):
    _datasette, db = ds
    source = DocumentCloudSource()

    def _create_doc(conn):
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES (?, ?, ?) RETURNING id",
            ("documentcloud", 5, json.dumps({"title": "DC doc"})),
        )
        doc_id = cursor.fetchone()[0]
        conn.commit()
        return doc_id

    doc_id = await db.execute_write_fn(_create_doc)

    cdn_url = "https://assets.documentcloud.org/documents/123/pages/slug-p1-large.gif"
    page_id = await source.store_page(db, doc_id, 1, image_url=cdn_url)

    # Verify stored URL
    def _check(conn):
        cursor = conn.execute(
            "SELECT image, image_url FROM datasette_ca460_pages WHERE id = ?", (page_id,)
        )
        return cursor.fetchone()

    row = await db.execute_write_fn(_check)
    assert row[0] is None  # no blob
    assert row[1] == cdn_url


@pytest.mark.asyncio
async def test_dc_source_image_response_returns_url_for_redirect(ds):
    _datasette, db = ds
    source = DocumentCloudSource()

    cdn_url = "https://assets.documentcloud.org/documents/123/pages/slug-p1-large.gif"

    def _create(conn):
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES (?, ?, ?) RETURNING id",
            ("documentcloud", 1, "{}"),
        )
        doc_id = cursor.fetchone()[0]
        conn.execute(
            "INSERT INTO datasette_ca460_pages(document_id, page_number, image_url) VALUES (?, ?, ?)",
            (doc_id, 1, cdn_url),
        )
        conn.commit()
        return doc_id

    doc_id = await db.execute_write_fn(_create)

    data, content_type = await source.get_image_response_for_page(db, doc_id, 1)
    assert data == cdn_url
    assert content_type is None  # signals redirect


@pytest.mark.asyncio
async def test_dc_source_thumbnail_url(ds):
    source = DocumentCloudSource()
    doc_data = {
        "id": 12345,
        "asset_url": "https://assets.documentcloud.org/",
        "slug": "my-doc",
    }
    url = source.thumbnail_url(doc_data, 3)
    assert url == "https://assets.documentcloud.org/documents/12345/pages/my-doc-p3-small.gif"


@pytest.mark.asyncio
async def test_dc_source_embed_url(ds):
    source = DocumentCloudSource()
    assert source.embed_url({"id": 999}) == "https://www.documentcloud.org/documents/999"
    assert source.embed_url({}) is None


@pytest.mark.asyncio
async def test_dc_source_pdf_response(ds):
    _datasette, db = ds
    source = DocumentCloudSource()

    doc_data = {
        "id": 12345,
        "asset_url": "https://assets.documentcloud.org/",
        "slug": "my-doc",
    }

    def _create(conn):
        conn.execute(
            "INSERT INTO datasette_ca460_documents(id, source, page_count, data) VALUES (?, ?, ?, ?)",
            (12345, "documentcloud", 1, json.dumps(doc_data)),
        )
        conn.commit()

    await db.execute_write_fn(_create)

    url, filename = await source.get_pdf_response(db, 12345)
    assert url == "https://assets.documentcloud.org/documents/12345/my-doc.pdf"
    assert filename is None  # signals redirect


@pytest.mark.asyncio
async def test_factory_returns_upload_source(ds):
    _datasette, db = ds

    def _create(conn):
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES (?, ?, ?) RETURNING id",
            ("upload", 1, "{}"),
        )
        doc_id = cursor.fetchone()[0]
        conn.execute(
            "INSERT INTO datasette_ca460_pages(document_id, page_number, image) VALUES (?, ?, ?)",
            (doc_id, 1, b"fake"),
        )
        conn.commit()
        return doc_id

    doc_id = await db.execute_write_fn(_create)

    source = await get_source_for_document(db, doc_id)
    assert isinstance(source, UploadSource)

    # Also test page-level factory
    def _get_page_id(conn):
        cursor = conn.execute(
            "SELECT id FROM datasette_ca460_pages WHERE document_id = ?", (doc_id,)
        )
        return cursor.fetchone()[0]

    page_id = await db.execute_write_fn(_get_page_id)
    source = await get_source_for_page(db, page_id)
    assert isinstance(source, UploadSource)


@pytest.mark.asyncio
async def test_factory_returns_dc_source(ds):
    _datasette, db = ds

    def _create(conn):
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES (?, ?, ?) RETURNING id",
            ("documentcloud", 1, "{}"),
        )
        doc_id = cursor.fetchone()[0]
        conn.execute(
            "INSERT INTO datasette_ca460_pages(document_id, page_number, image_url) VALUES (?, ?, ?)",
            (doc_id, 1, "https://example.com/page.gif"),
        )
        conn.commit()
        return doc_id

    doc_id = await db.execute_write_fn(_create)

    source = await get_source_for_document(db, doc_id)
    assert isinstance(source, DocumentCloudSource)

    def _get_page_id(conn):
        cursor = conn.execute(
            "SELECT id FROM datasette_ca460_pages WHERE document_id = ?", (doc_id,)
        )
        return cursor.fetchone()[0]

    page_id = await db.execute_write_fn(_get_page_id)
    source = await get_source_for_page(db, page_id)
    assert isinstance(source, DocumentCloudSource)


@pytest.mark.asyncio
async def test_dc_source_store_page_upserts(ds):
    """Storing a page twice for same doc+page_number updates the existing row."""
    _datasette, db = ds
    source = DocumentCloudSource()

    def _create_doc(conn):
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES (?, ?, ?) RETURNING id",
            ("documentcloud", 1, "{}"),
        )
        doc_id = cursor.fetchone()[0]
        conn.commit()
        return doc_id

    doc_id = await db.execute_write_fn(_create_doc)

    page_id1 = await source.store_page(db, doc_id, 1, image_url="https://old.url")
    page_id2 = await source.store_page(db, doc_id, 1, image_url="https://new.url")
    assert page_id1 == page_id2

    def _check(conn):
        cursor = conn.execute(
            "SELECT image_url FROM datasette_ca460_pages WHERE id = ?", (page_id1,)
        )
        return cursor.fetchone()[0]

    assert await db.execute_write_fn(_check) == "https://new.url"
