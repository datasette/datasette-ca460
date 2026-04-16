import asyncio
import json
import uuid
from pathlib import Path

import click

from ._db import apply_schema
from ..sync import (
    process_document,
    extract_pdf_page_images,
    CliProgressReporter,
    DEFAULT_WORKERS,
)
from ..sources import UploadSource


def _create_datasette(db_path: Path):
    """Create a minimal Datasette instance for LLM access."""
    from datasette.app import Datasette

    return Datasette(files=[str(db_path)])


async def _store_and_process(
    db_path: Path,
    pdf_bytes: bytes,
    filename: str,
    page_type_model: str,
    parser_model: str,
    num_workers: int,
):
    """Extract pages from PDF, store as blobs, classify and parse."""
    ds = _create_datasette(db_path)
    await ds.invoke_startup()
    db = ds.get_database(db_path.stem)

    loop = asyncio.get_event_loop()
    page_images = await loop.run_in_executor(None, extract_pdf_page_images, pdf_bytes)

    # Create document record
    def _create_doc(conn):
        cursor = conn.execute(
            "INSERT INTO datasette_ca460_documents(source, page_count, data) VALUES (?, ?, ?) RETURNING id",
            ("upload", len(page_images), json.dumps({"title": filename}))
        )
        document_id = cursor.fetchone()[0]
        conn.commit()
        return document_id

    document_id = await db.execute_write_fn(_create_doc)

    # Store each page image as a blob
    source = UploadSource()
    for page_number, image_bytes in enumerate(page_images, start=1):
        await source.store_page(db, document_id, page_number, image=image_bytes)

    page_count = len(page_images)
    click.echo(f"Stored {page_count} pages as document #{document_id}")

    # Create sync job and run classification/parsing
    sync_job_id = str(uuid.uuid4())

    def _create_job(conn):
        conn.execute(
            "INSERT INTO datasette_ca460_sync_jobs(id, page_type_model, parser_model) VALUES (?, ?, ?)",
            (sync_job_id, page_type_model, parser_model),
        )
        conn.commit()

    await db.execute_write_fn(_create_job)

    reporter = CliProgressReporter()

    await process_document(
        ds,
        db,
        sync_job_id,
        document_id,
        page_type_model,
        parser_model,
        num_workers,
        reporter,
    )

    # Mark job completed
    def _complete_job(conn):
        from datetime import datetime

        conn.execute(
            "UPDATE datasette_ca460_sync_jobs SET status = 'completed', completed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), sync_job_id),
        )
        conn.commit()

    await db.execute_write_fn(_complete_job)


@click.command(name="add")
@click.argument("pdf_path", type=click.Path(exists=True))
@click.option(
    "-o",
    "--output",
    "db_path_str",
    type=click.Path(),
    default=None,
    help="Database path (default: derived from PDF name)",
)
@click.option(
    "-m",
    "--model",
    default=None,
    help="LLM model for both classification and parsing",
)
@click.option("--classifier-model", default=None, help="Model for page classification")
@click.option("--parser-model", default=None, help="Model for page parsing")
@click.option(
    "--workers",
    "-w",
    default=DEFAULT_WORKERS,
    type=int,
    show_default=True,
    help="Number of parallel workers",
)
def ca460_add(pdf_path, db_path_str, model, classifier_model, parser_model, workers):
    "Add a Form 460 PDF to a database"

    pdf_path = Path(pdf_path)
    pdf_bytes = pdf_path.read_bytes()

    if db_path_str is None:
        db_path = Path(f"{pdf_path.stem}.db")
    else:
        db_path = Path(db_path_str)

    # Resolve model names
    cls_model = classifier_model or model
    prs_model = parser_model or model

    if not cls_model or not prs_model:
        raise click.ClickException(
            "Specify a model with -m/--model, or use --classifier-model and --parser-model separately"
        )

    click.echo(f"Processing {pdf_path.name}...")
    apply_schema(db_path)

    click.echo(f"Using classifier: {cls_model}")
    click.echo(f"Using parser: {prs_model}")

    asyncio.run(
        _store_and_process(db_path, pdf_bytes, pdf_path.name, cls_model, prs_model, workers)
    )
