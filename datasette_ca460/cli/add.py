import asyncio
from pathlib import Path

import click

from ._db import apply_schema, store_pdf, get_pages
from ..sync import predict_page_type, parse_page, get_page_image, PAGE_TYPES


def _create_datasette(db_path: Path):
    """Create a minimal Datasette instance for LLM access."""
    from datasette.app import Datasette

    return Datasette(files=[str(db_path)])


async def _process_document(
    db_path: Path,
    document_id: int,
    page_type_model: str,
    parser_model: str,
):
    """Classify and parse all pages, printing progress."""
    ds = _create_datasette(db_path)
    await ds.invoke_startup()
    db = ds.get_database(db_path.stem)

    pages = get_pages(db_path, document_id)

    # Classify
    click.echo(f"Classifying {len(pages)} pages...")
    classifications: dict[int, str] = {}
    for page_id, page_number in pages:
        predicted = await predict_page_type(ds, db, page_id, page_type_model)
        classifications[page_id] = predicted
        click.echo(f"  Page {page_number}: {predicted}")

    click.echo("Classification complete.")

    # Parse
    page_types_found = set(classifications.values())
    for page_type in PAGE_TYPES:
        if page_type == "unknown" or page_type not in page_types_found:
            continue

        matching = [
            (pid, pn)
            for pid, pn in pages
            if classifications.get(pid) == page_type
        ]

        click.echo(f"Parsing {len(matching)} {page_type} page{'s' if len(matching) != 1 else ''}...")
        for page_id, page_number in matching:
            await parse_page(ds, db, page_id, page_type, parser_model)
            click.echo(f"  Parsed page {page_number}")

    click.echo("Done.")


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
def ca460_add(pdf_path, db_path_str, model, classifier_model, parser_model):
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

    asyncio.run(_process_document(db_path, document_id, cls_model, prs_model))
