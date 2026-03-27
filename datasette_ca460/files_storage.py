"""
Helpers for reading files from datasette-files using its Python internals.

Bypasses the HTTP API (and its permission checks) for server-side access.
"""

from __future__ import annotations


async def read_from_datasette_files(datasette, file_id: str) -> bytes:
    """Read file content from datasette-files. Returns bytes."""
    from datasette_files import _sources

    db = datasette.get_internal_database()
    row = (
        await db.execute(
            """
            SELECT f.path, s.slug as source_slug
            FROM datasette_files f
            JOIN datasette_files_sources s ON f.source_id = s.id
            WHERE f.id = ?
            """,
            [file_id],
        )
    ).first()
    if not row:
        raise RuntimeError(f"File not found in datasette-files: {file_id}")

    source_slug = row["source_slug"]
    if source_slug not in _sources:
        raise RuntimeError(f"datasette-files source not configured: {source_slug}")

    storage = _sources[source_slug]
    return await storage.read_file(row["path"])


async def get_file_metadata(datasette, file_id: str) -> dict:
    """Get file metadata from datasette-files. Returns dict."""
    db = datasette.get_internal_database()
    row = (
        await db.execute(
            "SELECT id, filename, content_type, size FROM datasette_files WHERE id = ?",
            [file_id],
        )
    ).first()
    if not row:
        raise RuntimeError(f"File not found in datasette-files: {file_id}")
    return dict(row)
