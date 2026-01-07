from datasette import hookimpl, Response
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
import uuid
from datetime import datetime
import traceback
import llm

from .form460_page_type import Form460PageTypeModel, PROMPT as PAGE_TYPE_PROMPT
from .form460_summary_page import Form460SummaryPage, PROMPT as SUMMARY_PAGE_PROMPT
from .form_460_schedule_a import Form460ScheduleA, PROMPT as SCHEDULE_A_PROMPT


@contextmanager
def timer():
    """Context manager to time code execution."""
    start = time.time()
    yield lambda: time.time() - start


def crop_page_image_for_prediction(page_image: bytes) -> bytes:
    """
    Crop the page image to the top-left 1/6th corner for page type prediction.
    """
    img = Image.open(BytesIO(page_image))
    crop_width = img.width // 2
    crop_height = img.height // 6
    cropped_img = img.crop((0, 0, crop_width, crop_height))
    buffer = BytesIO()
    cropped_img.save(buffer, format="PNG")
    image = buffer.getbuffer()
    return bytes(image)


def gif_to_jpeg(contents: bytes, quality: int = 95) -> bytes:
    """Convert GIF bytes to JPEG bytes."""
    buf = BytesIO(contents)
    with Image.open(buf) as im:
        try:
            im.seek(0)
        except EOFError:
            pass
        rgb = im.convert("RGB")
        out = BytesIO()
        rgb.save(out, format="JPEG", quality=quality)
        return out.getvalue()


SCHEMA = (Path(__file__).parent / "schema.sql").read_text()


async def log_event(db, sync_job_id: str, event_type: str, message: str):
    """Log a sync event to the database."""
    def _log(conn):
        conn.execute(
            "INSERT INTO sync_events (sync_job_id, event_type, message) VALUES (?, ?, ?)",
            (sync_job_id, event_type, message)
        )
        conn.commit()

    await db.execute_write_fn(_log)


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
                "INSERT INTO documents (id, page_count, data) VALUES (?, ?, ?)",
                (document.id, document.page_count, json.dumps(document.data))
            )
        conn.commit()

    await db.execute_write_fn(_sync)
    return document.id


async def sync_page(db, document_id: int, page_number: int) -> int:
    """Sync a page to the database if it doesn't exist. Returns page_id."""
    def _sync(conn):
        cursor = conn.execute(
            "SELECT id FROM pages WHERE document_id = ? AND page_number = ?",
            (document_id, page_number)
        )
        row = cursor.fetchone()

        if row:
            return row[0]

        cursor = conn.execute(
            "INSERT INTO pages (document_id, page_number) VALUES (?, ?)",
            (document_id, page_number)
        )
        conn.commit()
        return cursor.lastrowid

    return await db.execute_write_fn(_sync)


async def predict_page_type(
    datasette,
    db,
    page_id: int,
    document,
    page_number: int,
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

    # Get and process the page image
    page_image_url: str = document.get_xlarge_image_url(page_number)

    # Fetch image in thread pool since httpx.get is sync
    loop = asyncio.get_event_loop()
    page_image = await loop.run_in_executor(
        None,
        lambda: httpx.get(page_image_url).content
    )

    cropped_page_image = crop_page_image_for_prediction(page_image)
    cropped_page_jpeg = gif_to_jpeg(cropped_page_image, quality=95)

    # Make prediction using LlmWrapper
    llm_wrapper = LlmWrapper(datasette)
    model = llm_wrapper.get_async_model(page_type_model)
    with timer() as get_elapsed:
        response = await model.prompt(
            PAGE_TYPE_PROMPT,
            schema=Form460PageTypeModel,
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


async def parse_summary_page(
    datasette,
    db,
    page_id: int,
    document,
    page_number: int,
    parser_model: str
) -> None:
    """Parse a summary page if not already parsed with this model."""
    # Get and process the page image
    page_image_url: str = document.get_xlarge_image_url(page_number)

    loop = asyncio.get_event_loop()
    page_image = await loop.run_in_executor(
        None,
        lambda: httpx.get(page_image_url).content
    )

    page_jpeg = gif_to_jpeg(page_image, quality=95)

    # Parse the page using LlmWrapper
    llm_wrapper = LlmWrapper(datasette)
    model = llm_wrapper.get_async_model(parser_model)
    with timer() as get_elapsed:
        response = await model.prompt(
            SUMMARY_PAGE_PROMPT,
            schema=Form460SummaryPage,
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
                "campaign_disclosure_summary_page",
                parser_model,
                json.dumps(asdict(response_usage)),
                json.dumps({"time_taken_s": get_elapsed()}),
                json.dumps(data)
            )
        )
        conn.commit()

    await db.execute_write_fn(_store_parsed)


async def parse_schedule_a_page(
    datasette,
    db,
    page_id: int,
    document,
    page_number: int,
    parser_model: str
) -> None:
    """Parse a Schedule A page if not already parsed with this model."""
    # Get and process the page image
    page_image_url: str = document.get_xlarge_image_url(page_number)

    loop = asyncio.get_event_loop()
    page_image = await loop.run_in_executor(
        None,
        lambda: httpx.get(page_image_url).content
    )

    page_jpeg = gif_to_jpeg(page_image, quality=95)

    # Parse the page using LlmWrapper
    llm_wrapper = LlmWrapper(datasette)
    model = llm_wrapper.get_async_model(parser_model)
    with timer() as get_elapsed:
        response = await model.prompt(
            SCHEDULE_A_PROMPT,
            schema=Form460ScheduleA,
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
                "schedule_a",
                parser_model,
                json.dumps(asdict(response_usage)),
                json.dumps({"time_taken_s": get_elapsed()}),
                json.dumps(data)
            )
        )
        conn.commit()

    await db.execute_write_fn(_store_parsed)


async def sync_project(
    datasette,
    db,
    sync_job_id: str,
    project_id: int,
    page_type_model: str,
    parser_model: str
):
    """Sync a DocumentCloud project to the database."""
    # Initialize database schema
    def init_schema(conn):
        conn.executescript(SCHEMA)

    await db.execute_write_fn(init_schema)

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

        # Sync all pages for this document
        for page_idx in range(document.page_count):
            page_number = page_idx + 1
            page_id = await sync_page(db, document_id, page_number)

            # Predict page type if not already done with this model
            await predict_page_type(
                datasette,
                db,
                page_id,
                document,
                page_number,
                page_type_model
            )

        await log_event(db, sync_job_id, "info", f"Completed page type predictions for document {document.id}")

    # Parse summary pages for this project
    def _get_summary_pages(conn):
        cursor = conn.execute(
            """SELECT DISTINCT p.id, p.document_id, p.page_number
            FROM pages p
            JOIN page_type_predictions ptp ON p.id = ptp.page_id
            LEFT JOIN page_parsed pp ON p.id = pp.page_id
                AND pp.page_type = 'campaign_disclosure_summary_page'
                AND pp.model = ?
            WHERE ptp.predicted_page_type = 'campaign_disclosure_summary_page'
            AND ptp.model = ?
            AND pp.id IS NULL""",
            (parser_model, page_type_model)
        )
        return cursor.fetchall()

    summary_pages = await db.execute_write_fn(_get_summary_pages)

    if not summary_pages:
        await log_event(db, sync_job_id, "info", "No summary pages to parse")
    else:
        await log_event(db, sync_job_id, "info", f"Parsing {len(summary_pages)} summary pages...")
        for page_id, document_id, page_number in summary_pages:
            # Get the document object
            document = next(
                (d for d in project.documents if d.id == document_id),
                None
            )
            if not document:
                await log_event(db, sync_job_id, "warning", f"Could not find document {document_id}, skipping page {page_number}")
                continue

            await parse_summary_page(
                datasette,
                db,
                page_id,
                document,
                page_number,
                parser_model
            )
            await log_event(db, sync_job_id, "info", f"Parsed summary page {page_number} from document {document_id}")

    # Parse Schedule A pages for this project
    def _get_schedule_a_pages(conn):
        cursor = conn.execute(
            """SELECT DISTINCT p.id, p.document_id, p.page_number
            FROM pages p
            JOIN page_type_predictions ptp ON p.id = ptp.page_id
            LEFT JOIN page_parsed pp ON p.id = pp.page_id
                AND pp.page_type = 'schedule_a'
                AND pp.model = ?
            WHERE ptp.predicted_page_type IN ('schedule_a', 'schedule_a_continuation')
            AND ptp.model = ?
            AND pp.id IS NULL""",
            (parser_model, page_type_model)
        )
        return cursor.fetchall()

    schedule_a_pages = await db.execute_write_fn(_get_schedule_a_pages)

    if not schedule_a_pages:
        await log_event(db, sync_job_id, "info", "No Schedule A pages to parse")
    else:
        await log_event(db, sync_job_id, "info", f"Parsing {len(schedule_a_pages)} Schedule A pages...")
        for page_id, document_id, page_number in schedule_a_pages:
            # Get the document object
            document = next(
                (d for d in project.documents if d.id == document_id),
                None
            )
            if not document:
                await log_event(db, sync_job_id, "warning", f"Could not find document {document_id}, skipping page {page_number}")
                continue

            await parse_schedule_a_page(
                datasette,
                db,
                page_id,
                document,
                page_number,
                parser_model
            )
            await log_event(db, sync_job_id, "info", f"Parsed Schedule A page {page_number} from document {document_id}")

    await log_event(db, sync_job_id, "success", "Sync complete!")


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
        await log_event(db, sync_job_id, "error", error_msg)

        def _fail_job(conn):
            conn.execute(
                "UPDATE sync_jobs SET status = 'failed', completed_at = ?, error = ? WHERE id = ?",
                (datetime.now().isoformat(), str(e), sync_job_id)
            )
            conn.commit()

        await db.execute_write_fn(_fail_job)


@hookimpl
def register_routes():
    return [
        (r"^/(?P<database>[^/]+)/-/ca460$", ca460_view),
        (r"^/(?P<database>[^/]+)/-/ca460/(?P<sync_job_id>[^/]+)/events$", ca460_events_view),
    ]


async def ca460_view(request, datasette):
    """Handle the CA 460 sync page."""
    database_name = request.url_vars["database"]

    # Check database exists
    try:
        db = datasette.get_database(database_name)
    except KeyError:
        return Response.html(
            f"<h1>Database not found</h1><p>Database '{database_name}' does not exist.</p>",
            status=404
        )

    # Get available LLM models
    llm_wrapper = LlmWrapper(datasette)
    available_models = list(map(lambda x: x.model_id, llm_wrapper.get_async_models()))

    # Handle POST request (form submission)
    if request.method == "POST":
        formdata = await request.post_vars()
        project_id = formdata.get("project_id")
        page_type_model = formdata.get("page_type_model", "llama-server")
        parser_model = formdata.get("parser_model", "gemini-3-flash-preview")

        if not project_id:
            return Response.html(
                await datasette.render_template(
                    "ca460_sync.html",
                    {
                        "database": database_name,
                        "url": datasette.urls.path(f"/{database_name}/-/ca460"),
                        "message": "Please provide a DocumentCloud project ID",
                        "message_type": "error",
                        "available_models": available_models,
                    },
                    request=request
                )
            )

        try:
            project_id = int(project_id)
        except ValueError:
            return Response.html(
                await datasette.render_template(
                    "ca460_sync.html",
                    {
                        "database": database_name,
                        "url": datasette.urls.path(f"/{database_name}/-/ca460"),
                        "message": "Project ID must be a number",
                        "message_type": "error",
                        "project_id": project_id,
                        "available_models": available_models,
                    },
                    request=request
                )
            )

        # Initialize schema first
        def init_schema(conn):
            conn.executescript(SCHEMA)

        await db.execute_write_fn(init_schema)

        # Create sync job
        sync_job_id = str(uuid.uuid4())

        def _create_job(conn):
            conn.execute(
                "INSERT INTO sync_jobs (id, project_id, page_type_model, parser_model) VALUES (?, ?, ?, ?)",
                (sync_job_id, project_id, page_type_model, parser_model)
            )
            conn.commit()

        await db.execute_write_fn(_create_job)

        # Start background sync
        asyncio.create_task(
            run_sync_in_background(
                datasette,
                database_name,
                sync_job_id,
                project_id,
                page_type_model,
                parser_model
            )
        )

        # Return immediately with sync job ID
        return Response.html(
            await datasette.render_template(
                "ca460_sync.html",
                {
                    "database": database_name,
                    "url": datasette.urls.path(f"/{database_name}/-/ca460"),
                    "message": f"Sync job started for project {project_id}",
                    "message_type": "success",
                    "sync_job_id": sync_job_id,
                    "project_id": project_id,
                    "page_type_model": page_type_model,
                    "parser_model": parser_model,
                    "available_models": available_models,
                },
                request=request
            )
        )

    # Handle GET request (show form)
    return Response.html(
        await datasette.render_template(
            "ca460_sync.html",
            {
                "database": database_name,
                "url": datasette.urls.path(f"/{database_name}/-/ca460"),
                "available_models": available_models,
            },
            request=request
        )
    )


async def ca460_events_view(request, datasette):
    """API endpoint to get sync events for a job."""
    database_name = request.url_vars["database"]
    sync_job_id = request.url_vars["sync_job_id"]

    # Check database exists
    try:
        db = datasette.get_database(database_name)
    except KeyError:
        return Response.json(
            {"error": "Database not found"},
            status=404
        )

    # Get job status and events
    def _get_data(conn):
        # Get job info
        cursor = conn.execute(
            "SELECT status, error, started_at, completed_at FROM sync_jobs WHERE id = ?",
            (sync_job_id,)
        )
        job = cursor.fetchone()

        if not job:
            return None

        # Get events
        cursor = conn.execute(
            "SELECT event_type, message, created_at FROM sync_events WHERE sync_job_id = ? ORDER BY id",
            (sync_job_id,)
        )
        events = cursor.fetchall()

        return {
            "job": {
                "status": job[0],
                "error": job[1],
                "started_at": job[2],
                "completed_at": job[3],
            },
            "events": [
                {
                    "type": e[0],
                    "message": e[1],
                    "created_at": e[2],
                }
                for e in events
            ]
        }

    data = await db.execute_write_fn(_get_data)

    if data is None:
        return Response.json(
            {"error": "Sync job not found"},
            status=404
        )

    return Response.json(data)
