"""
Thin async client wrapping the DocumentCloud REST API.

Replaces the ``python-documentcloud`` library with direct httpx calls so we
control authentication, pagination, and error handling without pulling in a
large dependency tree.
"""

from __future__ import annotations

import re
from typing import Any

import httpx


BASE_URL = "https://api.www.documentcloud.org/api"

# Patterns for parsing DocumentCloud URLs
_DOC_URL_RE = re.compile(
    r"documentcloud\.org/documents/(\d+)", re.IGNORECASE
)
_PROJECT_URL_RE = re.compile(
    r"documentcloud\.org/projects/[^/]*?(\d+)", re.IGNORECASE
)


class DocumentCloudClient:
    """Async HTTP client for the DocumentCloud public API."""

    def __init__(self, token: str | None = None):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=headers,
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "DocumentCloudClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        q: str,
        page: int = 1,
        per_page: int = 25,
        ordering: str = "-created_at",
    ) -> dict:
        """Full-text search across public (and private, if authed) documents."""
        resp = await self._client.get(
            "/documents/search/",
            params={
                "q": q,
                "page": page,
                "per_page": per_page,
                "ordering": ordering,
            },
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Single document
    # ------------------------------------------------------------------

    async def get_document(self, doc_id: int) -> dict:
        resp = await self._client.get(f"/documents/{doc_id}/")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    async def get_project(self, project_id: int) -> dict:
        resp = await self._client.get(f"/projects/{project_id}/")
        resp.raise_for_status()
        return resp.json()

    async def list_project_documents(
        self,
        project_id: int,
        page: int = 1,
        per_page: int = 25,
    ) -> dict:
        """Return paginated documents belonging to a project."""
        resp = await self._client.get(
            "/documents/search/",
            params={
                "q": f"+project:{project_id}",
                "page": page,
                "per_page": per_page,
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def list_my_projects(self) -> dict:
        """List projects owned by the authenticated user. Requires a token."""
        resp = await self._client.get("/projects/")
        resp.raise_for_status()
        return resp.json()


# ------------------------------------------------------------------
# URL parsing
# ------------------------------------------------------------------


def parse_documentcloud_url(url: str) -> dict | None:
    """Parse a DocumentCloud URL into ``{type, id}``.

    Recognises:
    - ``https://www.documentcloud.org/documents/12345-slug``
    - ``https://www.documentcloud.org/projects/some-project-67890/``

    Returns ``None`` if the URL doesn't match.
    """
    m = _DOC_URL_RE.search(url)
    if m:
        return {"type": "document", "id": int(m.group(1))}

    m = _PROJECT_URL_RE.search(url)
    if m:
        return {"type": "project", "id": int(m.group(1))}

    return None


def page_image_url(
    asset_url: str, doc_id: int, slug: str, page_number: int, size: str = "large"
) -> str:
    """Build the CDN URL for a page image.

    Sizes: ``thumbnail``, ``small``, ``normal``, ``large``.
    """
    return f"{asset_url}documents/{doc_id}/pages/{slug}-p{page_number}-{size}.gif"
