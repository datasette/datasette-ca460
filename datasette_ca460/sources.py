"""
Document source abstraction.

Each source type (upload, documentcloud) defines its own storage, image
retrieval, PDF access, and embedding behavior.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from io import BytesIO

import httpx
from PIL import Image

from .documentcloud import page_image_url


class DocumentSource(ABC):
    """Abstract base for document sources."""

    # --- Page images ---

    @abstractmethod
    async def get_page_image_bytes(self, db, page_id: int, *, datasette=None) -> bytes:
        """Raw image bytes for LLM processing."""

    @abstractmethod
    async def get_image_response_for_page(
        self, db, document_id: int, page_number: int, *, datasette=None
    ) -> tuple:
        """Returns (bytes, content_type) for blobs, or (url, None) to signal redirect."""

    @abstractmethod
    def thumbnail_url(self, doc_data: dict, page_number: int) -> str | None:
        """Direct URL for thumbnail display. None if served via API."""

    # --- Document-level ---

    @abstractmethod
    async def get_page_count(self, db, document_id: int) -> int:
        """Number of pages in the document."""

    @abstractmethod
    async def get_pdf_response(self, db, document_id: int, *, datasette=None) -> tuple:
        """Returns (bytes, filename) for blob, or (url, None) for redirect."""

    @abstractmethod
    def embed_url(self, doc_data: dict) -> str | None:
        """URL for iframe embedding. None if not available."""

    # --- Storage ---

    @abstractmethod
    async def store_page(
        self, db, document_id: int, page_number: int, *, datasette=None, **kwargs
    ) -> int:
        """Store a page record. Returns page_id."""


class UploadSource(DocumentSource):
    """Source for uploaded PDF documents — page images stored as blobs."""

    async def get_page_image_bytes(self, db, page_id: int, *, datasette=None) -> bytes:
        def _get(conn):
            cursor = conn.execute(
                "SELECT image FROM datasette_ca460_pages WHERE id = ?",
                (page_id,),
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                raise ValueError(f"No image for page {page_id}")
            return row[0]

        return await db.execute_write_fn(_get)

    async def get_image_response_for_page(
        self, db, document_id: int, page_number: int, *, datasette=None
    ) -> tuple:
        def _get(conn):
            cursor = conn.execute(
                "SELECT image FROM datasette_ca460_pages WHERE document_id = ? AND page_number = ?",
                (document_id, page_number),
            )
            row = cursor.fetchone()
            return row[0] if row else None

        image = await db.execute_write_fn(_get)
        if not image:
            return (None, None)
        return (image, "image/png")

    def thumbnail_url(self, doc_data: dict, page_number: int) -> str | None:
        return None

    async def get_page_count(self, db, document_id: int) -> int:
        def _get(conn):
            cursor = conn.execute(
                "SELECT page_count FROM datasette_ca460_documents WHERE id = ?",
                (document_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0

        return await db.execute_write_fn(_get)

    async def get_pdf_response(self, db, document_id: int, *, datasette=None) -> tuple:
        def _get(conn):
            cursor = conn.execute(
                "SELECT filename, file_id FROM datasette_ca460_document_files WHERE document_id = ?",
                (document_id,),
            )
            row = cursor.fetchone()
            return (row[0], row[1]) if row else (None, None)

        filename, file_id = await db.execute_write_fn(_get)
        if not file_id:
            return (None, None)
        # Signal redirect to datasette-files download URL
        return (f"/-/files/{file_id}/download", None)

    def embed_url(self, doc_data: dict) -> str | None:
        return None

    async def store_page(
        self, db, document_id: int, page_number: int, *, datasette=None, **kwargs
    ) -> int:
        image = kwargs.get("image")

        def _store(conn):
            cursor = conn.execute(
                "INSERT INTO datasette_ca460_pages(document_id, page_number, image) VALUES (?, ?, ?) RETURNING id",
                (document_id, page_number, image),
            )
            row_id = cursor.fetchone()[0]
            conn.commit()
            return row_id

        return await db.execute_write_fn(_store)


class DocumentCloudSource(DocumentSource):
    """Source for DocumentCloud documents — images served via CDN redirect."""

    async def get_page_image_bytes(self, db, page_id: int, *, datasette=None) -> bytes:
        """Fetch image bytes for LLM processing. Tries blob first, then CDN URL."""

        def _get(conn):
            cursor = conn.execute(
                "SELECT image_url FROM datasette_ca460_pages WHERE id = ?", (page_id,)
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"No page found with id {page_id}")
            return row[0]

        url = await db.execute_write_fn(_get)

        if not url:
            raise ValueError(f"No image data for page {page_id}")

        async with httpx.AsyncClient() as http:
            resp = await http.get(url)
            resp.raise_for_status()
            raw = resp.content

        # Convert GIF to PNG for consistency
        img = Image.open(BytesIO(raw))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def get_image_response_for_page(
        self, db, document_id: int, page_number: int, *, datasette=None
    ) -> tuple:
        """Returns (url, None) for redirect."""

        def _get(conn):
            cursor = conn.execute(
                "SELECT image_url FROM datasette_ca460_pages WHERE document_id = ? AND page_number = ?",
                (document_id, page_number),
            )
            row = cursor.fetchone()
            return row[0] if row else None

        url = await db.execute_write_fn(_get)

        if url:
            return (url, None)  # signal redirect
        return (None, None)

    def thumbnail_url(self, doc_data: dict, page_number: int) -> str | None:
        asset_url = doc_data.get("asset_url", "")
        slug = doc_data.get("slug", "")
        doc_id = doc_data.get("id")
        if not asset_url or not slug or not doc_id:
            return None
        return page_image_url(asset_url, doc_id, slug, page_number, size="small")

    async def get_page_count(self, db, document_id: int) -> int:
        def _get(conn):
            cursor = conn.execute(
                "SELECT page_count FROM datasette_ca460_documents WHERE id = ?",
                (document_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else 0

        return await db.execute_write_fn(_get)

    async def get_pdf_response(self, db, document_id: int, *, datasette=None) -> tuple:
        """Return (url, None) for redirect to DC-hosted PDF."""

        def _get(conn):
            cursor = conn.execute(
                "SELECT data FROM datasette_ca460_documents WHERE id = ?",
                (document_id,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

        import json

        raw = await db.execute_write_fn(_get)
        if not raw:
            return (None, None)
        doc_data = json.loads(raw)
        asset_url = doc_data.get("asset_url", "")
        slug = doc_data.get("slug", "")
        doc_id = doc_data.get("id", document_id)
        if not asset_url or not slug:
            return (None, None)
        pdf_url = f"{asset_url}documents/{doc_id}/{slug}.pdf"
        return (pdf_url, None)

    def embed_url(self, doc_data: dict) -> str | None:
        doc_id = doc_data.get("id")
        if not doc_id:
            return None
        return f"https://www.documentcloud.org/documents/{doc_id}"

    async def store_page(
        self, db, document_id: int, page_number: int, *, datasette=None, **kwargs
    ) -> int:
        image_url = kwargs.get("image_url")

        def _store(conn):
            # Check if page already exists
            cursor = conn.execute(
                "SELECT id FROM datasette_ca460_pages WHERE document_id = ? AND page_number = ?",
                (document_id, page_number),
            )
            existing = cursor.fetchone()
            if existing:
                conn.execute(
                    "UPDATE datasette_ca460_pages SET image_url = ? WHERE id = ?",
                    (image_url, existing[0]),
                )
                conn.commit()
                return existing[0]
            cursor = conn.execute(
                "INSERT INTO datasette_ca460_pages(document_id, page_number, image_url) VALUES (?, ?, ?) RETURNING id",
                (document_id, page_number, image_url),
            )
            row_id = cursor.fetchone()[0]
            conn.commit()
            return row_id

        return await db.execute_write_fn(_store)


# --- Factory functions ---

_SOURCES = {
    "upload": UploadSource(),
    "documentcloud": DocumentCloudSource(),
}


async def get_source_for_document(db, document_id: int) -> DocumentSource:
    def _get(conn):
        cursor = conn.execute(
            "SELECT source FROM datasette_ca460_documents WHERE id = ?",
            (document_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    source = await db.execute_write_fn(_get)
    if source not in _SOURCES:
        raise ValueError(f"Unknown source type: {source}")
    return _SOURCES[source]


async def get_source_for_page(db, page_id: int) -> DocumentSource:
    def _get(conn):
        cursor = conn.execute(
            "SELECT d.source FROM datasette_ca460_documents d JOIN datasette_ca460_pages p ON p.document_id = d.id WHERE p.id = ?",
            (page_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    source = await db.execute_write_fn(_get)
    if source not in _SOURCES:
        raise ValueError(f"Unknown source type: {source}")
    return _SOURCES[source]
