import sqlite3
from pathlib import Path

from sqlite_utils import Database as SqliteUtilsDatabase

from ..migrations import migrations
from ..sync import extract_pdf_page_images


def apply_schema(db_path: Path):
    db = SqliteUtilsDatabase(str(db_path))
    migrations.apply(db)
    db.conn.close()


def store_pdf(db_path: Path, pdf_bytes: bytes, filename: str) -> tuple[int, int]:
    """Store a PDF and its extracted page images. Returns (document_id, page_count)."""
    page_images = extract_pdf_page_images(pdf_bytes)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES (?, ?, ?) RETURNING id",
        ("upload", len(page_images), f'{{"title": "{filename}"}}'),
    )
    document_id: int = cursor.fetchone()[0]

    cursor.execute(
        "INSERT INTO datasette_ca460_document_files(document_id, filename, content) VALUES (?, ?, ?)",
        (document_id, filename, pdf_bytes),
    )

    for page_number, image_bytes in enumerate(page_images, start=1):
        cursor.execute(
            "INSERT INTO datasette_ca460_pages(document_id, page_number, image) VALUES (?, ?, ?)",
            (document_id, page_number, image_bytes),
        )

    conn.commit()
    conn.close()
    return document_id, len(page_images)


def get_pages(db_path: Path, document_id: int) -> list[tuple[int, int]]:
    """Get (page_id, page_number) pairs for a document."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        "SELECT id, page_number FROM datasette_ca460_pages WHERE document_id = ? ORDER BY page_number",
        (document_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return rows
