"""
Core sync and processing logic for datasette-ca460.

Architecture overview
---------------------
Processing a Form 460 PDF happens in two phases per page:

  1. **Classify** — an LLM looks at the top-left corner of the page image and
     predicts its page type (e.g. "schedule-a", "cover-page-part-1").
  2. **Parse** — a type-specific LLM prompt extracts structured data from the
     full page image into a Pydantic schema.

Both phases are tracked as rows in the ``page_tasks`` table (see schema.sql).

Parallel task queue
~~~~~~~~~~~~~~~~~~~
Rather than processing pages sequentially, work is broken into small tasks
stored in ``page_tasks`` with a status lifecycle::

    pending → running → completed
                      → failed

Multiple async **workers** (default 8) run in an ``asyncio.TaskGroup``. Each
worker loop:

  1. Claims a pending task via an atomic
     ``UPDATE … WHERE id = (SELECT … LIMIT 1) RETURNING …`` query.
  2. Executes the LLM call (classify or parse).
  3. Marks the task completed/failed.
  4. If it was a classify task, inserts a new *parse* task for the page.
  5. Loops back to claim the next task; exits when nothing is left.

Workers prefer classify tasks over parse tasks so that parse work becomes
available as early as possible.

Crash recovery
~~~~~~~~~~~~~~
If the process dies mid-job, ``running`` tasks stay in the database. On the
next run (or via the ``/api/resume`` endpoint), ``reset_stale_tasks()`` moves
any task that has been ``running`` for longer than ``STALE_TASK_TIMEOUT_MINUTES``
back to ``pending``, and workers pick them up again. Both ``predict_page_type``
and ``parse_page`` are idempotent — re-running a completed task is safe (it
will be skipped by the duplicate check).

Progress reporting
~~~~~~~~~~~~~~~~~~
``ProgressReporter`` is a protocol with two implementations:

- ``DbProgressReporter`` — writes to ``sync_events`` for the web UI to poll.
- ``CliProgressReporter`` — prints to the terminal via ``click.echo()``.

Both are passed into ``process_document()`` / ``run_workers()`` so the same
worker code serves the web background task and the CLI ``add`` command.

Entry points
~~~~~~~~~~~~
- ``process_document()`` — called for PDF uploads (web + CLI). Creates classify
  tasks, then runs workers.
- ``sync_project()`` — called for DocumentCloud syncs. Fetches pages from the
  API first, then creates classify tasks and runs workers.
- ``resume_job()`` — re-enters a stalled job. Resets stale tasks, then runs
  workers against the existing task queue.
- ``run_*_in_background()`` — thin wrappers that catch exceptions and update
  ``sync_jobs.status`` to ``completed`` or ``failed``.
"""

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
from datetime import datetime, timedelta
from typing import Protocol
import traceback
import llm
import pdf_lib

from extract_ca460 import PageClassification, CLASSIFIER_PROMPT, PAGE_TYPES


STALE_TASK_TIMEOUT_MINUTES = 5
DEFAULT_WORKERS = 8


# ---------------------------------------------------------------------------
# Progress reporting
# ---------------------------------------------------------------------------

class ProgressReporter(Protocol):
    async def report(self, event_type: str, message: str) -> None: ...


class DbProgressReporter:
    """Reports progress by logging events to the database (for web UI polling)."""
    def __init__(self, db, sync_job_id: str):
        self.db = db
        self.sync_job_id = sync_job_id

    async def report(self, event_type: str, message: str) -> None:
        await log_event(self.db, self.sync_job_id, event_type, message)


class CliProgressReporter:
    """Reports progress by printing to the terminal (for CLI usage)."""
    async def report(self, event_type: str, message: str) -> None:
        import click
        click.echo(f"  {message}")


# ---------------------------------------------------------------------------
# Image utilities
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# LLM operations (classify + parse) — called by workers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Task queue — SQLite-backed work queue for parallel page processing
#
# Each unit of work (classify one page, parse one page) is a row in
# page_tasks. Workers atomically claim tasks with UPDATE ... RETURNING.
# On crash, stale "running" tasks are reset to "pending" on the next run.
# ---------------------------------------------------------------------------

async def create_classify_tasks(
    db,
    sync_job_id: str,
    document_id: int,
    page_type_model: str,
):
    """Create classify tasks for all pages of a document."""
    def _create(conn):
        cursor = conn.execute(
            "SELECT id, page_number FROM pages WHERE document_id = ? ORDER BY page_number",
            (document_id,)
        )
        pages = cursor.fetchall()
        for page_id, page_number in pages:
            # Skip if already classified with this model
            existing = conn.execute(
                "SELECT 1 FROM page_type_predictions WHERE page_id = ? AND model = ?",
                (page_id, page_type_model)
            ).fetchone()
            if existing:
                continue
            # Skip if task already exists
            existing_task = conn.execute(
                "SELECT 1 FROM page_tasks WHERE sync_job_id = ? AND page_id = ? AND task_type = 'classify'",
                (sync_job_id, page_id)
            ).fetchone()
            if existing_task:
                continue
            conn.execute(
                """INSERT INTO page_tasks
                (sync_job_id, document_id, page_id, page_number, task_type, model, status)
                VALUES (?, ?, ?, ?, 'classify', ?, 'pending')""",
                (sync_job_id, document_id, page_id, page_number, page_type_model)
            )
        conn.commit()
        return len(pages)

    return await db.execute_write_fn(_create)


async def reset_stale_tasks(db, sync_job_id: str):
    """Reset tasks that have been running for too long back to pending."""
    def _reset(conn):
        cutoff = (datetime.now() - timedelta(minutes=STALE_TASK_TIMEOUT_MINUTES)).isoformat()
        cursor = conn.execute(
            """UPDATE page_tasks SET status = 'pending', started_at = NULL
            WHERE sync_job_id = ? AND status = 'running' AND started_at < ?""",
            (sync_job_id, cutoff)
        )
        conn.commit()
        return cursor.rowcount

    return await db.execute_write_fn(_reset)


async def claim_task(db, sync_job_id: str, preferred_type: str = "classify"):
    """Claim the next pending task. Tries preferred_type first, then the other type.
    Returns task dict or None."""
    other_type = "parse" if preferred_type == "classify" else "classify"

    def _claim(conn):
        now = datetime.now().isoformat()
        for task_type in (preferred_type, other_type):
            cursor = conn.execute(
                """UPDATE page_tasks SET status = 'running', started_at = ?
                WHERE id = (
                    SELECT id FROM page_tasks
                    WHERE sync_job_id = ? AND status = 'pending' AND task_type = ?
                    ORDER BY id LIMIT 1
                ) RETURNING id, page_id, page_number, task_type, page_type, model, document_id""",
                (now, sync_job_id, task_type)
            )
            row = cursor.fetchone()
            if row:
                conn.commit()
                return {
                    "id": row[0],
                    "page_id": row[1],
                    "page_number": row[2],
                    "task_type": row[3],
                    "page_type": row[4],
                    "model": row[5],
                    "document_id": row[6],
                }
        return None

    return await db.execute_write_fn(_claim)


async def complete_task(db, task_id: int):
    """Mark a task as completed."""
    def _complete(conn):
        conn.execute(
            "UPDATE page_tasks SET status = 'completed', completed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), task_id)
        )
        conn.commit()

    await db.execute_write_fn(_complete)


async def fail_task(db, task_id: int, error: str):
    """Mark a task as failed."""
    def _fail(conn):
        conn.execute(
            "UPDATE page_tasks SET status = 'failed', completed_at = ?, error = ? WHERE id = ?",
            (datetime.now().isoformat(), error, task_id)
        )
        conn.commit()

    await db.execute_write_fn(_fail)


async def create_parse_task_for_page(
    db,
    sync_job_id: str,
    document_id: int,
    page_id: int,
    page_number: int,
    page_type: str,
    parser_model: str,
):
    """Create a parse task after classification, if the page type is parseable."""
    if page_type == "unknown" or page_type not in PAGE_TYPES:
        return

    def _create(conn):
        # Skip if already parsed with this model
        existing = conn.execute(
            "SELECT 1 FROM page_parsed WHERE page_id = ? AND page_type = ? AND model = ?",
            (page_id, page_type, parser_model)
        ).fetchone()
        if existing:
            return
        # Skip if parse task already exists
        existing_task = conn.execute(
            "SELECT 1 FROM page_tasks WHERE sync_job_id = ? AND page_id = ? AND task_type = 'parse'",
            (sync_job_id, page_id)
        ).fetchone()
        if existing_task:
            return
        conn.execute(
            """INSERT INTO page_tasks
            (sync_job_id, document_id, page_id, page_number, task_type, page_type, model, status)
            VALUES (?, ?, ?, ?, 'parse', ?, ?, 'pending')""",
            (sync_job_id, document_id, page_id, page_number, page_type, parser_model)
        )
        conn.commit()

    await db.execute_write_fn(_create)


async def get_task_progress(db, sync_job_id: str) -> dict:
    """Get task progress counts for a job."""
    def _progress(conn):
        cursor = conn.execute(
            "SELECT task_type, status, COUNT(*) FROM page_tasks WHERE sync_job_id = ? GROUP BY task_type, status",
            (sync_job_id,)
        )
        results = {}
        for task_type, status, count in cursor.fetchall():
            if task_type not in results:
                results[task_type] = {}
            results[task_type][status] = count
        return results

    return await db.execute_write_fn(_progress)


# ---------------------------------------------------------------------------
# Workers — the core parallel execution loop
# ---------------------------------------------------------------------------

async def worker(
    datasette,
    db,
    sync_job_id: str,
    parser_model: str,
    reporter: ProgressReporter,
    worker_id: int,
):
    """A single worker that claims and executes tasks from the queue.

    Each worker runs in its own asyncio task. It loops: claim a task, execute
    the LLM call, mark it done, repeat. When no tasks remain it returns,
    allowing the TaskGroup to collect all workers.

    Classify tasks are preferred over parse tasks so that new parse work
    becomes available as soon as possible.
    """
    while True:
        task = await claim_task(db, sync_job_id, preferred_type="classify")
        if task is None:
            return

        task_id = task["id"]
        page_id = task["page_id"]
        page_number = task["page_number"]
        task_type = task["task_type"]

        try:
            if task_type == "classify":
                predicted = await predict_page_type(
                    datasette, db, page_id, task["model"]
                )
                await complete_task(db, task_id)
                await reporter.report(
                    "info",
                    f"Classified page {page_number}: {predicted}"
                )
                # Create a parse task for this page
                await create_parse_task_for_page(
                    db, sync_job_id, task["document_id"],
                    page_id, page_number, predicted, parser_model,
                )
            elif task_type == "parse":
                page_type = task["page_type"]
                await parse_page(
                    datasette, db, page_id, page_type, task["model"]
                )
                await complete_task(db, task_id)
                await reporter.report(
                    "info",
                    f"Parsed {page_type} page {page_number}"
                )
        except Exception as e:
            await fail_task(db, task_id, str(e))
            await reporter.report(
                "error",
                f"Failed {task_type} page {page_number}: {e}"
            )


async def run_workers(
    datasette,
    db,
    sync_job_id: str,
    parser_model: str,
    reporter: ProgressReporter,
    num_workers: int = DEFAULT_WORKERS,
):
    """Run N workers in parallel to process the task queue."""
    # Reset any stale tasks from a previous crashed run
    reset_count = await reset_stale_tasks(db, sync_job_id)
    if reset_count:
        await reporter.report("info", f"Reset {reset_count} stale tasks")

    async with asyncio.TaskGroup() as tg:
        for i in range(num_workers):
            tg.create_task(
                worker(datasette, db, sync_job_id, parser_model, reporter, i)
            )


async def get_job_summary(db, sync_job_id: str) -> str:
    """Get a summary string of the job results."""
    progress = await get_task_progress(db, sync_job_id)
    classify = progress.get("classify", {})
    parse = progress.get("parse", {})
    classified = classify.get("completed", 0)
    parsed = parse.get("completed", 0)
    errors = classify.get("failed", 0) + parse.get("failed", 0)
    return f"Complete: {classified} classified, {parsed} parsed, {errors} errors"


# ---------------------------------------------------------------------------
# Resume — pick up a crashed or stalled job
# ---------------------------------------------------------------------------

async def resume_job(
    datasette,
    db,
    sync_job_id: str,
    parser_model: str,
    num_workers: int = DEFAULT_WORKERS,
    reporter: ProgressReporter | None = None,
):
    """Resume a stalled job by running workers against existing tasks."""
    if reporter is None:
        reporter = DbProgressReporter(db, sync_job_id)

    reset_count = await reset_stale_tasks(db, sync_job_id)
    if reset_count:
        await reporter.report("info", f"Reset {reset_count} stale tasks")

    await reporter.report("info", f"Resuming with {num_workers} workers...")
    await run_workers(datasette, db, sync_job_id, parser_model, reporter, num_workers)

    summary = await get_job_summary(db, sync_job_id)
    await reporter.report("success", summary)


async def run_resume_in_background(
    datasette,
    database_name: str,
    sync_job_id: str,
    parser_model: str,
    num_workers: int = DEFAULT_WORKERS,
):
    """Run job resume in background, updating job status."""
    db = datasette.get_database(database_name)

    try:
        await resume_job(datasette, db, sync_job_id, parser_model, num_workers)

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


# ---------------------------------------------------------------------------
# Upload flow
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# DocumentCloud sync flow
# ---------------------------------------------------------------------------

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
    parser_model: str,
    num_workers: int = DEFAULT_WORKERS,
):
    """Sync a DocumentCloud project to the database."""
    await ensure_schema(db)

    reporter = DbProgressReporter(db, sync_job_id)
    await reporter.report("info", f"Starting sync for project {project_id}")

    # Get project and documents
    await reporter.report("info", "Fetching project from DocumentCloud...")
    loop = asyncio.get_event_loop()
    client = DocumentCloud()
    project = await loop.run_in_executor(
        None,
        lambda: client.projects.get_by_id(project_id)
    )

    await reporter.report("info", f"Found {len(project.documents)} documents")

    # Sync documents and pages (sequential — needs network I/O per page)
    for document in project.documents:
        document_id = await sync_document(db, document)
        await reporter.report("info", f"Syncing document {document.id} ({document.page_count} pages)...")

        for page_idx in range(document.page_count):
            page_number = page_idx + 1
            await sync_page_image(db, document, document_id, page_number)

        # Create classify tasks for this document
        await create_classify_tasks(db, sync_job_id, document_id, page_type_model)

    await reporter.report("info", "All pages synced, starting classification and parsing...")

    # Run parallel workers for classify + parse
    await run_workers(datasette, db, sync_job_id, parser_model, reporter, num_workers)

    summary = await get_job_summary(db, sync_job_id)
    await reporter.report("success", summary)


# ---------------------------------------------------------------------------
# High-level entry points — called by routes.py and cli/add.py
# ---------------------------------------------------------------------------

async def process_document(
    datasette,
    db,
    sync_job_id: str,
    document_id: int,
    page_type_model: str,
    parser_model: str,
    num_workers: int = DEFAULT_WORKERS,
    reporter: ProgressReporter | None = None,
):
    """Classify and parse all pages of a document using parallel workers.

    This is the main entry point for PDF uploads. It creates one classify task
    per page, then launches workers that process them in parallel. As each
    classify task completes, a parse task is automatically enqueued for that
    page (unless the page type is "unknown").
    """
    await ensure_schema(db)

    if reporter is None:
        reporter = DbProgressReporter(db, sync_job_id)

    # Create classify tasks for all pages
    page_count = await create_classify_tasks(db, sync_job_id, document_id, page_type_model)
    await reporter.report("info", f"Processing {page_count} pages with {num_workers} workers...")

    # Run workers — they'll classify pages and auto-create parse tasks
    await run_workers(datasette, db, sync_job_id, parser_model, reporter, num_workers)

    summary = await get_job_summary(db, sync_job_id)
    await reporter.report("success", summary)


# ---------------------------------------------------------------------------
# Background wrappers — catch exceptions and update sync_jobs.status
# ---------------------------------------------------------------------------

async def run_process_document_in_background(
    datasette,
    database_name: str,
    sync_job_id: str,
    document_id: int,
    page_type_model: str,
    parser_model: str,
    num_workers: int = DEFAULT_WORKERS,
):
    """Run document processing in background, updating job status."""
    db = datasette.get_database(database_name)

    try:
        await process_document(
            datasette, db, sync_job_id, document_id,
            page_type_model, parser_model, num_workers,
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
