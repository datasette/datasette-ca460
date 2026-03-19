import asyncio
import uuid
from pathlib import Path

import click

from ._db import apply_schema, store_pdf
from ..sync import (
    process_document,
    CliProgressReporter,
    DEFAULT_WORKERS,
)


def _create_datasette(db_path: Path):
    """Create a minimal Datasette instance for LLM access."""
    from datasette.app import Datasette

    return Datasette(files=[str(db_path)])


async def _process_document(
    db_path: Path,
    document_id: int,
    page_type_model: str,
    parser_model: str,
    num_workers: int,
):
    """Classify and parse all pages using parallel workers."""
    ds = _create_datasette(db_path)
    await ds.invoke_startup()
    db = ds.get_database(db_path.stem)

    sync_job_id = str(uuid.uuid4())

    # Create a sync job record
    def _create_job(conn):
        conn.execute(
            "INSERT INTO datasette_ca460_sync_jobs(id, page_type_model, parser_model) VALUES (?, ?, ?)",
            (sync_job_id, page_type_model, parser_model)
        )
        conn.commit()

    await db.execute_write_fn(_create_job)

    reporter = CliProgressReporter()

    await process_document(
        ds, db, sync_job_id, document_id,
        page_type_model, parser_model, num_workers, reporter,
    )

    # Mark job completed
    def _complete_job(conn):
        from datetime import datetime
        conn.execute(
            "UPDATE datasette_ca460_sync_jobs SET status = 'completed', completed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), sync_job_id)
        )
        conn.commit()

    await db.execute_write_fn(_complete_job)


@click.command(name="add")
@click.argument("pdf_path", type=click.Path(exists=True))
@click.option(
    "-o", "--output", "db_path_str",
    type=click.Path(),
    default=None,
    help="Database path (default: derived from PDF name)",
)
@click.option(
    "-m", "--model",
    default=None,
    help="LLM model for both classification and parsing",
)
@click.option("--classifier-model", default=None, help="Model for page classification")
@click.option("--parser-model", default=None, help="Model for page parsing")
@click.option(
    "--workers", "-w",
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

    click.echo(f"Extracting pages from {pdf_path.name}...")
    apply_schema(db_path)
    document_id, page_count = store_pdf(db_path, pdf_bytes, pdf_path.name)
    click.echo(f"Stored {page_count} pages as document #{document_id} in {db_path}")

    click.echo(f"Using classifier: {cls_model}")
    click.echo(f"Using parser: {prs_model}")

    asyncio.run(_process_document(db_path, document_id, cls_model, prs_model, workers))
