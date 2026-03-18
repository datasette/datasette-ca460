from pathlib import Path
from typing import Optional, Annotated
from datasette_llm_accountant import LlmWrapper
from datasette import Response
from datasette_plugin_router import Body
from pydantic import BaseModel
import json
from .sync import run_sync_in_background, run_process_document_in_background, upload_pdf, ensure_schema
from .router import router, check_permission
import asyncio
import uuid

async def _render_vite_entry(datasette, entrypoint: str) -> str:
    return await datasette.render_template(
        "ca460_vite_entry.html",
        {
            "entry_name": entrypoint,
        }
    )

@router.GET(r"^/(?P<database>[^/]+)/-/ca460$")
@check_permission()
async def ca460_index_view(request, datasette, database: str):

    # Check database exists
    try:
        _db = datasette.get_database(database)
    except KeyError:
        return Response.html(
            f"<h1>Database not found</h1><p>Database '{database}' does not exist.</p>",
            status=404
        )

    return Response.html(
        await _render_vite_entry(datasette, "src/index_view.ts")
    )
    
@router.GET(r"^/(?P<database>[^/]+)/-/ca460/sync$")
@check_permission()
async def ca460_sync_view(request, datasette, database: str):
    """Handle the CA 460 sync page with Svelte UI."""

    # Check database exists
    try:
        _db = datasette.get_database(database)
    except KeyError:
        return Response.html(
            f"<h1>Database not found</h1><p>Database '{database}' does not exist.</p>",
            status=404
        )

    return Response.html(
        await _render_vite_entry(datasette, "src/sync_view.ts")
    )


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/document/(?P<document_id>\d+)$")
@check_permission()
async def ca460_document_view(request, datasette, database: str, document_id: str):
    try:
        _db = datasette.get_database(database)
    except KeyError:
        return Response.html(
            f"<h1>Database not found</h1><p>Database '{database}' does not exist.</p>",
            status=404
        )

    return Response.html(
        await _render_vite_entry(datasette, "src/document_view.ts")
    )


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/document/(?P<document_id>\d+)/page/(?P<page_number>\d+)$")
@check_permission()
async def ca460_page_detail_view(request, datasette, database: str, document_id: str, page_number: str):
    try:
        _db = datasette.get_database(database)
    except KeyError:
        return Response.html("Database not found", status=404)

    return Response.html(
        await _render_vite_entry(datasette, "src/page_detail_view.ts")
    )


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/models$")
@check_permission()
async def ca460_api_models(request, datasette):
    """API endpoint to get available LLM models."""
    database_name = request.url_vars["database"]

    try:
        _db = datasette.get_database(database_name)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    llm_wrapper = LlmWrapper(datasette)
    available_models = list(map(lambda x: x.model_id, llm_wrapper.get_async_models()))

    return Response.json({"models": available_models})


class DocumentListItem(BaseModel):
    id: int
    source: str
    page_count: int
    title: Optional[str]
    filer_name: Optional[str]
    period_from: Optional[str]
    period_through: Optional[str]
    pages_classified: int
    pages_parsed: int
    model_count: int

class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]

@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/documents$", output=DocumentListResponse)
@check_permission()
async def ca460_api_documents(request, datasette):
    """API endpoint to get list of all documents with status."""
    database_name = request.url_vars["database"]

    try:
        db = datasette.get_database(database_name)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    def _get_documents(conn):
        cursor = conn.execute("""
            SELECT
                d.id,
                d.source,
                d.page_count,
                d.data->>'title' as title,
                (
                    SELECT pp.parsed_data->>'committee_name'
                    FROM page_parsed pp
                    JOIN pages p ON pp.page_id = p.id
                    WHERE p.document_id = d.id
                      AND pp.page_type IN ('cover-page-part-1', 'summary-page')
                    LIMIT 1
                ) as filer_name,
                (
                    SELECT pp.parsed_data->>'statement_covers_period_from'
                    FROM page_parsed pp
                    JOIN pages p ON pp.page_id = p.id
                    WHERE p.document_id = d.id
                      AND pp.page_type IN ('cover-page-part-1', 'summary-page')
                    LIMIT 1
                ) as period_from,
                (
                    SELECT pp.parsed_data->>'statement_covers_period_through'
                    FROM page_parsed pp
                    JOIN pages p ON pp.page_id = p.id
                    WHERE p.document_id = d.id
                      AND pp.page_type IN ('cover-page-part-1', 'summary-page')
                    LIMIT 1
                ) as period_through,
                (
                    SELECT COUNT(DISTINCT ptp.page_id)
                    FROM pages p
                    JOIN page_type_predictions ptp ON p.id = ptp.page_id
                    WHERE p.document_id = d.id
                ) as pages_classified,
                (
                    SELECT COUNT(DISTINCT pp.page_id)
                    FROM pages p
                    JOIN page_parsed pp ON p.id = pp.page_id
                    WHERE p.document_id = d.id
                ) as pages_parsed,
                (
                    SELECT COUNT(DISTINCT pp.model)
                    FROM pages p
                    JOIN page_parsed pp ON p.id = pp.page_id
                    WHERE p.document_id = d.id
                ) as model_count
            FROM documents d
            ORDER BY d.id DESC
        """)
        rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "source": row[1],
                "page_count": row[2],
                "title": row[3],
                "filer_name": row[4],
                "period_from": row[5],
                "period_through": row[6],
                "pages_classified": row[7],
                "pages_parsed": row[8],
                "model_count": row[9],
            }
            for row in rows
        ]

    try:
        documents = await db.execute_fn(_get_documents)
    except Exception:
        # Table might not exist yet
        documents = []

    response = DocumentListResponse(
        documents=[DocumentListItem(**doc) for doc in documents]
    )
    return Response.json(response.model_dump())


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/document/(?P<document_id>\d+)/parsed$")
@check_permission()
async def ca460_api_document_parsed(request, datasette, database: str, document_id: str):
    """API endpoint to get all data for a document: pages, classifications, and parsed data."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    def _get_data(conn):
        # Document info
        cursor = conn.execute(
            "SELECT id, source, page_count, data FROM documents WHERE id = ?",
            (document_id,)
        )
        doc_row = cursor.fetchone()
        if not doc_row:
            return None

        doc_data = json.loads(doc_row[3]) if doc_row[3] else {}

        # Pages with classifications
        cursor = conn.execute("""
            SELECT
                p.id,
                p.page_number,
                (p.image IS NOT NULL) as has_image,
                ptp.model as classification_model,
                ptp.predicted_page_type
            FROM pages p
            LEFT JOIN page_type_predictions ptp ON p.id = ptp.page_id
            WHERE p.document_id = ?
            ORDER BY p.page_number
        """, (document_id,))

        pages_raw = cursor.fetchall()
        pages = []
        for row in pages_raw:
            pages.append({
                "page_id": row[0],
                "page_number": row[1],
                "has_image": bool(row[2]),
                "classification_model": row[3],
                "page_type": row[4],
            })

        # Parsed data grouped by model
        cursor = conn.execute("""
            SELECT
                pp.model,
                pp.page_type,
                p.page_number,
                pp.parsed_data,
                pp.timing,
                pp.created_at
            FROM page_parsed pp
            JOIN pages p ON pp.page_id = p.id
            WHERE p.document_id = ?
            ORDER BY pp.model, p.page_number
        """, (document_id,))

        rows = cursor.fetchall()
        models = {}
        for row in rows:
            model = row[0]
            if model not in models:
                models[model] = []

            parsed = json.loads(row[3]) if row[3] else {}
            timing = json.loads(row[4]) if row[4] else {}

            models[model].append({
                "page_type": row[1],
                "page_number": row[2],
                "parsed_data": parsed,
                "timing": timing,
                "created_at": row[5],
            })

        # Check if PDF file exists
        cursor = conn.execute(
            "SELECT filename FROM document_files WHERE document_id = ?",
            (document_id,)
        )
        pdf_row = cursor.fetchone()

        return {
            "document": {
                "id": doc_row[0],
                "source": doc_row[1],
                "page_count": doc_row[2],
                "title": doc_data.get("title", f"Document {doc_row[0]}"),
                "has_pdf": pdf_row is not None,
                "pdf_filename": pdf_row[0] if pdf_row else None,
            },
            "pages": pages,
            "models": models,
        }

    try:
        data = await db.execute_fn(_get_data)
    except Exception as e:
        return Response.json({"error": str(e)}, status=500)

    if data is None:
        return Response.json({"error": "Document not found"}, status=404)

    return Response.json(data)


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/document/(?P<document_id>\d+)/page/(?P<page_number>\d+)/image$")
@check_permission()
async def ca460_api_page_image(request, datasette, database: str, document_id: str, page_number: str):
    """Serve a page image as PNG."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.html("Not found", status=404)

    def _get_image(conn):
        cursor = conn.execute(
            "SELECT image FROM pages WHERE document_id = ? AND page_number = ?",
            (document_id, page_number)
        )
        row = cursor.fetchone()
        return bytes(row[0]) if row and row[0] else None

    image_bytes = await db.execute_fn(_get_image)
    if not image_bytes:
        return Response.html("Not found", status=404)

    return Response(
        body=image_bytes,
        content_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )



@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/document/(?P<document_id>\d+)/pdf$")
@check_permission()
async def ca460_api_document_pdf(request, datasette, database: str, document_id: str):
    """Serve the original PDF file."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.html("Not found", status=404)

    def _get_pdf(conn):
        cursor = conn.execute(
            "SELECT filename, content FROM document_files WHERE document_id = ?",
            (document_id,)
        )
        row = cursor.fetchone()
        return (row[0], bytes(row[1])) if row else None

    result = await db.execute_fn(_get_pdf)
    if not result:
        return Response.html("Not found", status=404)

    filename, pdf_bytes = result
    return Response(
        body=pdf_bytes,
        content_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/sync/(?P<sync_job_id>[^/]+)/events$")
@check_permission()
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

class SyncParams(BaseModel):
    project_id: int
    page_type_model: str
    parser_model: str
class SyncOutput(BaseModel):
    sync_job_id: str
    project_id: int
    page_type_model: str
    parser_model: str

@router.POST(r"^/(?P<database>[^/]+)/-/ca460/api/sync$", output=SyncOutput)
@check_permission()
async def ca460_api_sync(request, datasette, database: str, params: Annotated[SyncParams, Body()]):
    """API endpoint to start a DocumentCloud sync job."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    await ensure_schema(db)

    # Create sync job
    sync_job_id = str(uuid.uuid4())

    def _create_job(conn):
        conn.execute(
            "INSERT INTO sync_jobs (id, project_id, page_type_model, parser_model) VALUES (?, ?, ?, ?)",
            (sync_job_id, params.project_id, params.page_type_model, params.parser_model)
        )
        conn.commit()

    await db.execute_write_fn(_create_job)

    # Start background sync
    asyncio.create_task(
        run_sync_in_background(
            datasette,
            database,
            sync_job_id,
            params.project_id,
            params.page_type_model,
            params.parser_model
        )
    )

    return Response.json(SyncOutput(
        sync_job_id=sync_job_id,
        project_id=params.project_id,
        page_type_model=params.page_type_model,
        parser_model=params.parser_model
    ).model_dump())


class UploadRequest(BaseModel):
    file_data: str
    filename: str

class UploadResponse(BaseModel):
    document_id: int
    page_count: int
    filename: str

@router.POST(r"^/(?P<database>[^/]+)/-/ca460/api/upload$", output=UploadResponse)
@check_permission()
async def ca460_api_upload(request, datasette, database: str, body: Annotated[UploadRequest, Body()]):
    """API endpoint to upload a PDF for processing."""
    import base64

    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    try:
        pdf_bytes = base64.b64decode(body.file_data)
    except Exception:
        return Response.json({"error": "Invalid base64 file data"}, status=400)

    try:
        document_id = await upload_pdf(db, pdf_bytes, body.filename)
    except ValueError as e:
        return Response.json({"error": str(e)}, status=400)

    def _get_page_count(conn):
        cursor = conn.execute(
            "SELECT page_count FROM documents WHERE id = ?", (document_id,)
        )
        return cursor.fetchone()[0]

    page_count = await db.execute_write_fn(_get_page_count)

    return Response.json(UploadResponse(
        document_id=document_id,
        page_count=page_count,
        filename=body.filename,
    ).model_dump())


class ProcessDocumentParams(BaseModel):
    document_id: int
    page_type_model: str
    parser_model: str

class ProcessDocumentOutput(BaseModel):
    sync_job_id: str
    document_id: int

@router.POST(r"^/(?P<database>[^/]+)/-/ca460/api/process$", output=ProcessDocumentOutput)
@check_permission()
async def ca460_api_process(request, datasette, database: str, params: Annotated[ProcessDocumentParams, Body()]):
    """Start classifying and parsing a document."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    await ensure_schema(db)

    sync_job_id = str(uuid.uuid4())

    def _create_job(conn):
        conn.execute(
            "INSERT INTO sync_jobs (id, page_type_model, parser_model) VALUES (?, ?, ?)",
            (sync_job_id, params.page_type_model, params.parser_model)
        )
        conn.commit()

    await db.execute_write_fn(_create_job)

    asyncio.create_task(
        run_process_document_in_background(
            datasette,
            database,
            sync_job_id,
            params.document_id,
            params.page_type_model,
            params.parser_model,
        )
    )

    return Response.json(ProcessDocumentOutput(
        sync_job_id=sync_job_id,
        document_id=params.document_id,
    ).model_dump())

