import sqlite3
from pathlib import Path

from sqlite_utils import Database as SqliteUtilsDatabase

from ..migrations import migrations


def apply_schema(db_path: Path):
    db = SqliteUtilsDatabase(str(db_path))
    migrations.apply(db)
    db.conn.close()


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
