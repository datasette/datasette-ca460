from dataclasses import asdict
import json
import time
import httpx
from io import BytesIO
from PIL import Image
from pathlib import Path
from datasette_llm_accountant import LlmWrapper
import asyncio
from contextlib import contextmanager
from documentcloud import DocumentCloud
from datetime import datetime
import traceback
import llm
import pdf_lib

from extract_ca460 import PageClassification, CLASSIFIER_PROMPT, PAGE_TYPES


@contextmanager
def timer():
    """Context manager to time code execution."""
    start = time.time()
    yield lambda: time.time() - start


def crop_page_image_for_prediction(page_image: bytes) -> bytes:
    """Crop the page image to the top-left 1/6th corner for page type prediction."""
    img = Image.open(BytesIO(page_image))
    crop_width = img.width // 2
    crop_height = img.height // 6
    cropped_img = img.crop((0, 0, crop_width, crop_height))
    buffer = BytesIO()
    cropped_img.save(buffer, format="PNG")
    return bytes(buffer.getbuffer())


def to_jpeg(contents: bytes, quality: int = 95) -> bytes:
    """Convert image bytes to JPEG bytes."""
    buf = BytesIO(contents)
    with Image.open(buf) as im:
        rgb = im.convert("RGB")
        out = BytesIO()
        rgb.save(out, format="JPEG", quality=quality)
        return out.getvalue()


def extract_pdf_page_images(pdf_bytes: bytes) -> list[bytes]:
    """Extract one image per page from a scanned PDF."""
    doc = pdf_lib.Pdf.load(pdf_bytes)
    all_images = doc.extract_images()

    # Group images by page number
    pages: dict[int, list] = {}
    for img in all_images:
        pages.setdefault(img.page, []).append(img)

    if not pages:
        raise ValueError("PDF contains no images.")

    images = []
    for page_num in range(1, doc.page_count + 1):
        page_imgs = pages.get(page_num, [])
        if len(page_imgs) == 0:
            raise ValueError(
                f"Page {page_num} has no images. "
                "Expected scanned Form 460 PDFs with one image per page."
            )
        if len(page_imgs) > 1:
            raise ValueError(
                f"Page {page_num} has {len(page_imgs)} images. "
                "Expected exactly 1 image per page."
            )
        images.append(page_imgs[0].to_png())
    return images


SCHEMA = (Path(__file__).parent / "schema.sql").read_text()


async def ensure_schema(db):
    """Initialize database schema."""
    def init_schema(conn):
        conn.executescript(SCHEMA)
    await db.execute_write_fn(init_schema)


async def log_event(db, sync_job_id: str, event_type: str, message: str):
    """Log a sync event to the database."""
    def _log(conn):
        conn.execute(
            "INSERT INTO sync_events (sync_job_id, event_type, message) VALUES (?, ?, ?)",
            (sync_job_id, event_type, message)
        )
        conn.commit()

    await db.execute_write_fn(_log)


async def get_page_image(db, page_id: int) -> bytes:
    """Get the stored image for a page."""
    def _get(conn):
        cursor = conn.execute("SELECT image FROM pages WHERE id = ?", (page_id,))
        row = cursor.fetchone()
        if not row or not row[0]:
            raise ValueError(f"No image stored for page {page_id}")
        return bytes(row[0])
    return await db.execute_write_fn(_get)


async def predict_page_type(
    datasette,
    db,
    page_id: int,
    page_type_model: str
) -> str:
    """Predict page type if not already predicted with this model. Returns predicted page type."""
    # Check if already predicted
    def _check_existing(conn):
        cursor = conn.execute(
            "SELECT predicted_page_type FROM page_type_predictions WHERE page_id = ? AND model = ?",
            (page_id, page_type_model)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    existing = await db.execute_write_fn(_check_existing)
    if existing:
        return existing

    page_image = await get_page_image(db, page_id)
    cropped_page_image = crop_page_image_for_prediction(page_image)
    cropped_page_jpeg = to_jpeg(cropped_page_image, quality=95)

    # Make prediction using LlmWrapper
    llm_wrapper = LlmWrapper(datasette)
    model = llm_wrapper.get_async_model(page_type_model)
    with timer() as get_elapsed:
        response = await model.prompt(
            CLASSIFIER_PROMPT,
            schema=PageClassification,
            attachments=[
                llm.Attachment(
                    type="image/jpeg",
                    content=cropped_page_jpeg
                )
            ]
        )

    response_text = await response.text()
    data = json.loads(response_text)
    predicted_page_type = data["page_type"]

    response_usage = await response.usage()

    # Store prediction
    def _store_prediction(conn):
        conn.execute(
            """INSERT INTO page_type_predictions
            (page_id, model, predicted_page_type, model_usage, timing)
            VALUES (?, ?, ?, ?, ?)""",
            (
                page_id,
                page_type_model,
                predicted_page_type,
                json.dumps(asdict(response_usage)),
                json.dumps({"time_taken_s": get_elapsed()})
            )
        )
        conn.commit()

    await db.execute_write_fn(_store_prediction)
    return predicted_page_type


async def parse_page(
    datasette,
    db,
    page_id: int,
    page_type: str,
    parser_model: str
) -> None:
    """Parse a page of a given type if not already parsed with this model."""
    prompt, schema = PAGE_TYPES[page_type]

    page_image = await get_page_image(db, page_id)
    page_jpeg = to_jpeg(page_image, quality=95)

    # Parse the page using LlmWrapper
    llm_wrapper = LlmWrapper(datasette)
    model = llm_wrapper.get_async_model(parser_model)
    with timer() as get_elapsed:
        response = await model.prompt(
            prompt,
            schema=schema,
            attachments=[
                llm.Attachment(
                    type="image/jpeg",
                    content=page_jpeg
                )
            ]
        )

    response_text = await response.text()
    data = json.loads(response_text)

    response_usage = await response.usage()

    # Store parsed data
    def _store_parsed(conn):
        conn.execute(
            """INSERT INTO page_parsed
            (page_id, page_type, model, model_usage, timing, parsed_data)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                page_id,
                page_type,
                parser_model,
                json.dumps(asdict(response_usage)),
                json.dumps({"time_taken_s": get_elapsed()}),
                json.dumps(data)
            )
        )
        conn.commit()

    await db.execute_write_fn(_store_parsed)


# --- Upload flow ---

async def upload_pdf(db, pdf_bytes: bytes, filename: str) -> int:
    """Upload a PDF, extract page images, store everything. Returns document_id."""
    await ensure_schema(db)

    loop = asyncio.get_event_loop()
    page_images = await loop.run_in_executor(None, extract_pdf_page_images, pdf_bytes)

    def _store(conn):
        cursor = conn.execute(
            "INSERT INTO documents (source, page_count, data) VALUES (?, ?, ?)",
            ("upload", len(page_images), json.dumps({"title": filename}))
        )
        document_id = cursor.lastrowid

        conn.execute(
            "INSERT INTO document_files (document_id, filename, content) VALUES (?, ?, ?)",
            (document_id, filename, pdf_bytes)
        )

        for page_number, image_bytes in enumerate(page_images, start=1):
            conn.execute(
                "INSERT INTO pages (document_id, page_number, image) VALUES (?, ?, ?)",
                (document_id, page_number, image_bytes)
            )

        conn.commit()
        return document_id

    return await db.execute_write_fn(_store)


# --- DocumentCloud sync flow ---

async def sync_document(db, document) -> int:
    """Sync a document to the database if it doesn't exist. Returns document_id."""
    def _sync(conn):
        cursor = conn.execute(
            "SELECT id FROM documents WHERE id = ?",
            (document.id,)
        )
        row = cursor.fetchone()

        if not row:
            conn.execute(
                "INSERT INTO documents (id, source, page_count, data) VALUES (?, ?, ?, ?)",
                (document.id, "documentcloud", document.page_count, json.dumps(document.data))
            )
        conn.commit()

    await db.execute_write_fn(_sync)
    return document.id


async def sync_page_image(db, document, document_id: int, page_number: int) -> int:
    """Sync a page and its image to the database. Returns page_id."""
    def _check_existing(conn):
        cursor = conn.execute(
            "SELECT id, image FROM pages WHERE document_id = ? AND page_number = ?",
            (document_id, page_number)
        )
        return cursor.fetchone()

    existing = await db.execute_write_fn(_check_existing)
    if existing and existing[1] is not None:
        return existing[0]

    page_id = existing[0] if existing else None

    # Fetch image from DocumentCloud
    page_image_url: str = document.get_xlarge_image_url(page_number)
    loop = asyncio.get_event_loop()
    page_image = await loop.run_in_executor(
        None,
        lambda: httpx.get(page_image_url).content
    )

    # Convert GIF to PNG for consistent storage
    img = Image.open(BytesIO(page_image))
    buf = BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    def _store(conn):
        if page_id is not None:
            conn.execute(
                "UPDATE pages SET image = ? WHERE id = ?",
                (image_bytes, page_id)
            )
            conn.commit()
            return page_id
        else:
            cursor = conn.execute(
                "INSERT INTO pages (document_id, page_number, image) VALUES (?, ?, ?)",
                (document_id, page_number, image_bytes)
            )
            conn.commit()
            return cursor.lastrowid

    return await db.execute_write_fn(_store)


async def sync_project(
    datasette,
    db,
    sync_job_id: str,
    project_id: int,
    page_type_model: str,
    parser_model: str
):
    """Sync a DocumentCloud project to the database."""
    await ensure_schema(db)

    await log_event(db, sync_job_id, "info", f"Starting sync for project {project_id}")

    # Get project and documents
    await log_event(db, sync_job_id, "info", "Fetching project from DocumentCloud...")
    loop = asyncio.get_event_loop()
    client = DocumentCloud()
    project = await loop.run_in_executor(
        None,
        lambda: client.projects.get_by_id(project_id)
    )

    await log_event(db, sync_job_id, "info", f"Found {len(project.documents)} documents")

    # Sync documents and pages
    for document in project.documents:
        document_id = await sync_document(db, document)
        await log_event(db, sync_job_id, "info", f"Processing document {document.id} ({document.page_count} pages)...")

        # Sync all pages and their images for this document
        for page_idx in range(document.page_count):
            page_number = page_idx + 1
            page_id = await sync_page_image(db, document, document_id, page_number)

            # Predict page type
            await predict_page_type(
                datasette,
                db,
                page_id,
                page_type_model
            )

        await log_event(db, sync_job_id, "info", f"Completed page type predictions for document {document.id}")

    # Parse pages for each known page type
    for page_type in PAGE_TYPES:
        if page_type == "unknown":
            continue

        def _get_pages_for_type(conn, pt=page_type):
            cursor = conn.execute(
                """SELECT DISTINCT p.id, p.document_id, p.page_number
                FROM pages p
                JOIN page_type_predictions ptp ON p.id = ptp.page_id
                LEFT JOIN page_parsed pp ON p.id = pp.page_id
                    AND pp.page_type = ?
                    AND pp.model = ?
                WHERE ptp.predicted_page_type = ?
                AND ptp.model = ?
                AND pp.id IS NULL""",
                (pt, parser_model, pt, page_type_model)
            )
            return cursor.fetchall()

        pages_to_parse = await db.execute_write_fn(_get_pages_for_type)

        if not pages_to_parse:
            continue

        await log_event(db, sync_job_id, "info", f"Parsing {len(pages_to_parse)} {page_type} pages...")
        for page_id, document_id, page_number in pages_to_parse:
            await parse_page(
                datasette,
                db,
                page_id,
                page_type,
                parser_model
            )
            await log_event(db, sync_job_id, "info", f"Parsed {page_type} page {page_number} from document {document_id}")

    await log_event(db, sync_job_id, "success", "Sync complete!")


async def process_document(
    datasette,
    db,
    sync_job_id: str,
    document_id: int,
    page_type_model: str,
    parser_model: str
):
    """Classify and parse all pages of a document."""
    await ensure_schema(db)

    # Get all pages for this document
    def _get_pages(conn):
        cursor = conn.execute(
            "SELECT id, page_number FROM pages WHERE document_id = ? ORDER BY page_number",
            (document_id,)
        )
        return cursor.fetchall()

    pages = await db.execute_write_fn(_get_pages)
    await log_event(db, sync_job_id, "info", f"Classifying {len(pages)} pages...")

    for page_id, page_number in pages:
        await predict_page_type(datasette, db, page_id, page_type_model)

    await log_event(db, sync_job_id, "info", "Classification complete, parsing pages...")

    # Parse pages for each known page type
    for page_type in PAGE_TYPES:
        if page_type == "unknown":
            continue

        def _get_pages_for_type(conn, pt=page_type):
            cursor = conn.execute(
                """SELECT DISTINCT p.id, p.page_number
                FROM pages p
                JOIN page_type_predictions ptp ON p.id = ptp.page_id
                LEFT JOIN page_parsed pp ON p.id = pp.page_id
                    AND pp.page_type = ?
                    AND pp.model = ?
                WHERE p.document_id = ?
                AND ptp.predicted_page_type = ?
                AND ptp.model = ?
                AND pp.id IS NULL""",
                (pt, parser_model, document_id, pt, page_type_model)
            )
            return cursor.fetchall()

        pages_to_parse = await db.execute_write_fn(_get_pages_for_type)
        if not pages_to_parse:
            continue

        await log_event(db, sync_job_id, "info", f"Parsing {len(pages_to_parse)} {page_type} pages...")
        for page_id, page_number in pages_to_parse:
            await parse_page(datasette, db, page_id, page_type, parser_model)
            await log_event(db, sync_job_id, "info", f"Parsed {page_type} page {page_number}")

    await log_event(db, sync_job_id, "success", "Processing complete!")


async def run_process_document_in_background(
    datasette,
    database_name: str,
    sync_job_id: str,
    document_id: int,
    page_type_model: str,
    parser_model: str
):
    """Run document processing in background, updating job status."""
    db = datasette.get_database(database_name)

    try:
        await process_document(
            datasette, db, sync_job_id, document_id,
            page_type_model, parser_model
        )

        def _complete_job(conn):
            conn.execute(
                "UPDATE sync_jobs SET status = 'completed', completed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), sync_job_id)
            )
            conn.commit()
        await db.execute_write_fn(_complete_job)

    except Exception as e:
        error_msg = f"{str(e)}\n\n{traceback.format_exc()}"
        error_msg_short = str(e)
        await log_event(db, sync_job_id, "error", error_msg)

        def _fail_job(conn):
            conn.execute(
                "UPDATE sync_jobs SET status = 'failed', completed_at = ?, error = ? WHERE id = ?",
                (datetime.now().isoformat(), error_msg_short, sync_job_id)
            )
            conn.commit()
        await db.execute_write_fn(_fail_job)


async def run_sync_in_background(
    datasette,
    database_name: str,
    sync_job_id: str,
    project_id: int,
    page_type_model: str,
    parser_model: str
):
    """Run sync in background, updating job status."""
    db = datasette.get_database(database_name)

    try:
        await sync_project(
            datasette,
            db,
            sync_job_id,
            project_id,
            page_type_model,
            parser_model
        )

        # Mark job as completed
        def _complete_job(conn):
            conn.execute(
                "UPDATE sync_jobs SET status = 'completed', completed_at = ? WHERE id = ?",
                (datetime.now().isoformat(), sync_job_id)
            )
            conn.commit()

        await db.execute_write_fn(_complete_job)

    except Exception as e:
        # Log error and mark job as failed
        error_msg = f"{str(e)}\n\n{traceback.format_exc()}"
        error_msg_short = str(e)
        await log_event(db, sync_job_id, "error", error_msg)

        def _fail_job(conn):
            conn.execute(
                "UPDATE sync_jobs SET status = 'failed', completed_at = ?, error = ? WHERE id = ?",
                (datetime.now().isoformat(), error_msg_short, sync_job_id)
            )
            conn.commit()

        await db.execute_write_fn(_fail_job)
