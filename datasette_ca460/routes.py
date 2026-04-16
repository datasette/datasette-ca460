from typing import Optional, Annotated
from datasette_llm import LLM
from datasette import Response
from datasette_plugin_router import Body
from pydantic import BaseModel
import json
import logging

logger = logging.getLogger("datasette_ca460")
from .sync import (
    run_sync_in_background,
    run_sync_documents_in_background,
    run_process_document_in_background,
    run_resume_in_background,
    process_uploaded_file,
    get_task_progress,
    reset_stale_tasks,
)
from .documentcloud import DocumentCloudClient, parse_documentcloud_url
from .sources import get_source_for_document
from .files_storage import is_files_available
from .router import router, check_permission, INGEST_PERMISSION
import asyncio
import uuid


async def _render_vite_entry(datasette, request, entrypoint: str, page_data: Optional[dict] = None) -> str:
    merged = {"files_available": is_files_available()}
    if page_data:
        merged.update(page_data)
    return await datasette.render_template(
        "ca460_vite_entry.html",
        {
            "entry_name": entrypoint,
            "page_data": merged,
        },
        request=request,
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
        await _render_vite_entry(datasette, request, "src/index_view.ts", {"database": database})
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
        await _render_vite_entry(datasette, request, "src/document_view.ts", {"database": database, "document_id": int(document_id)})
    )


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/document/(?P<document_id>\d+)/page/(?P<page_number>\d+)$")
@check_permission()
async def ca460_page_detail_view(request, datasette, database: str, document_id: str, page_number: str):
    try:
        _db = datasette.get_database(database)
    except KeyError:
        return Response.html("Database not found", status=404)

    return Response.html(
        await _render_vite_entry(datasette, request, "src/page_detail_view.ts", {"database": database, "document_id": int(document_id), "page_number": int(page_number)})
    )


class ModelsOutput(BaseModel):
    classify: list[str]
    parse: list[str]


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/models$", output=ModelsOutput)
@check_permission()
async def ca460_api_models(request, datasette):
    """Return LLM models allowed for each ca460 purpose, filtered for the actor."""
    database_name = request.url_vars["database"]

    try:
        _db = datasette.get_database(database_name)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    ds_llm = LLM(datasette)
    classify_models = [
        m.model_id for m in await ds_llm.models(purpose="ca460-classify", actor=request.actor)
    ]
    parse_models = [
        m.model_id for m in await ds_llm.models(purpose="ca460-parse", actor=request.actor)
    ]

    return Response.json(
        ModelsOutput(classify=classify_models, parse=parse_models).model_dump()
    )


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
                    FROM datasette_ca460_page_parsed pp
                    JOIN datasette_ca460_pages p ON pp.page_id = p.id
                    WHERE p.document_id = d.id
                      AND pp.page_type IN ('cover-page-part-1', 'summary-page')
                    LIMIT 1
                ) as filer_name,
                (
                    SELECT pp.parsed_data->>'statement_covers_period_from'
                    FROM datasette_ca460_page_parsed pp
                    JOIN datasette_ca460_pages p ON pp.page_id = p.id
                    WHERE p.document_id = d.id
                      AND pp.page_type IN ('cover-page-part-1', 'summary-page')
                    LIMIT 1
                ) as period_from,
                (
                    SELECT pp.parsed_data->>'statement_covers_period_through'
                    FROM datasette_ca460_page_parsed pp
                    JOIN datasette_ca460_pages p ON pp.page_id = p.id
                    WHERE p.document_id = d.id
                      AND pp.page_type IN ('cover-page-part-1', 'summary-page')
                    LIMIT 1
                ) as period_through,
                (
                    SELECT COUNT(DISTINCT ptp.page_id)
                    FROM datasette_ca460_pages p
                    JOIN datasette_ca460_page_type_predictions ptp ON p.id = ptp.page_id
                    WHERE p.document_id = d.id
                ) as pages_classified,
                (
                    SELECT COUNT(DISTINCT pp.page_id)
                    FROM datasette_ca460_pages p
                    JOIN datasette_ca460_page_parsed pp ON p.id = pp.page_id
                    WHERE p.document_id = d.id
                ) as pages_parsed,
                (
                    SELECT COUNT(DISTINCT pp.model)
                    FROM datasette_ca460_pages p
                    JOIN datasette_ca460_page_parsed pp ON p.id = pp.page_id
                    WHERE p.document_id = d.id
                ) as model_count
            FROM datasette_ca460_documents d
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
            "SELECT id, source, page_count, data FROM datasette_ca460_documents WHERE id = ?",
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
                (p.image IS NOT NULL OR p.image_url IS NOT NULL) as has_image,
                ptp.model as classification_model,
                ptp.predicted_page_type
            FROM datasette_ca460_pages p
            LEFT JOIN datasette_ca460_page_type_predictions ptp ON p.id = ptp.page_id
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
            FROM datasette_ca460_page_parsed pp
            JOIN datasette_ca460_pages p ON pp.page_id = p.id
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

        # Check if PDF file exists (uploads) or if DC source (has PDF URL)
        cursor = conn.execute(
            "SELECT filename FROM datasette_ca460_document_files WHERE document_id = ?",
            (document_id,)
        )
        pdf_row = cursor.fetchone()
        has_pdf = pdf_row is not None or doc_row[1] == "documentcloud"

        return {
            "document": {
                "id": doc_row[0],
                "source": doc_row[1],
                "page_count": doc_row[2],
                "title": doc_data.get("title", f"Document {doc_row[0]}"),
                "has_pdf": has_pdf,
                "pdf_filename": pdf_row[0] if pdf_row else None,
            },
            "pages": pages,
            "models": models,
            "_doc_data": doc_data,
            "_source_type": doc_row[1],
        }

    try:
        data = await db.execute_fn(_get_data)
    except Exception as e:
        return Response.json({"error": str(e)}, status=500)

    if data is None:
        return Response.json({"error": "Document not found"}, status=404)

    # Add source-specific fields
    from .sources import UploadSource, DocumentCloudSource
    doc_data = data.pop("_doc_data")
    source_type = data.pop("_source_type")
    source = DocumentCloudSource() if source_type == "documentcloud" else UploadSource()

    data["document"]["embed_url"] = source.embed_url(doc_data)
    for page in data["pages"]:
        page["thumbnail_url"] = source.thumbnail_url(doc_data, page["page_number"])

    return Response.json(data)


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/document/(?P<document_id>\d+)/page/(?P<page_number>\d+)/image$")
@check_permission()
async def ca460_api_page_image(request, datasette, database: str, document_id: str, page_number: str):
    """Serve a page image as PNG, or redirect to CDN for DocumentCloud docs."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.html("Not found", status=404)

    source = await get_source_for_document(db, int(document_id))
    data, content_type = await source.get_image_response_for_page(
        db, int(document_id), int(page_number), datasette=datasette
    )

    if data is None:
        return Response.html("Not found", status=404)

    if content_type is None:
        # data is a URL — redirect
        return Response.redirect(data, status=302)

    return Response(
        body=data,
        content_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )



@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/document/(?P<document_id>\d+)/pdf$")
@check_permission()
async def ca460_api_document_pdf(request, datasette, database: str, document_id: str):
    """Serve the original PDF file, or redirect to DC-hosted PDF."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.html("Not found", status=404)

    source = await get_source_for_document(db, int(document_id))
    data, filename = await source.get_pdf_response(db, int(document_id), datasette=datasette)

    if data is None:
        return Response.html("Not found", status=404)

    if filename is None:
        # data is a URL — redirect
        return Response.redirect(data, status=302)

    return Response(
        body=data,
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
            "SELECT status, error, started_at, completed_at FROM datasette_ca460_sync_jobs WHERE id = ?",
            (sync_job_id,)
        )
        job = cursor.fetchone()

        if not job:
            return None

        # Get events
        cursor = conn.execute(
            "SELECT event_type, message, created_at FROM datasette_ca460_sync_events WHERE sync_job_id = ? ORDER BY id",
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



    # Create sync job
    sync_job_id = str(uuid.uuid4())

    def _create_job(conn):
        conn.execute(
            "INSERT INTO datasette_ca460_sync_jobs (id, project_id, page_type_model, parser_model) VALUES (?, ?, ?, ?)",
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
            params.parser_model,
            actor=request.actor,
        )
    )

    return Response.json(SyncOutput(
        sync_job_id=sync_job_id,
        project_id=params.project_id,
        page_type_model=params.page_type_model,
        parser_model=params.parser_model
    ).model_dump())


class ProcessDocumentParams(BaseModel):
    file_id: Optional[str] = None
    document_id: Optional[int] = None
    page_type_model: str
    parser_model: str

class ProcessDocumentOutput(BaseModel):
    sync_job_id: str
    document_id: int

@router.POST(r"^/(?P<database>[^/]+)/-/ca460/api/process$", output=ProcessDocumentOutput)
@check_permission()
async def ca460_api_process(request, datasette, database: str, params: Annotated[ProcessDocumentParams, Body()]):
    """Start processing a document.

    Accepts either:
    - file_id: a datasette-files ID (df-{ULID}) for a new PDF upload
    - document_id: an existing document to re-process
    """
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    if params.file_id:
        if not is_files_available():
            return Response.json(
                {"error": "PDF upload is not available. Install datasette-ca460[files] to enable it."},
                status=501,
            )
        # New upload: read PDF from datasette-files, extract pages, store images as blobs
        try:
            document_id = await process_uploaded_file(
                datasette, db, params.file_id
            )
        except Exception as e:
            return Response.json({"error": str(e)}, status=400)
    elif params.document_id:
        document_id = params.document_id
    else:
        return Response.json(
            {"error": "Either file_id or document_id is required"}, status=400
        )

    sync_job_id = str(uuid.uuid4())

    def _create_job(conn):
        conn.execute(
            "INSERT INTO datasette_ca460_sync_jobs (id, page_type_model, parser_model) VALUES (?, ?, ?)",
            (sync_job_id, params.page_type_model, params.parser_model)
        )
        conn.commit()

    await db.execute_write_fn(_create_job)

    asyncio.create_task(
        run_process_document_in_background(
            datasette,
            database,
            sync_job_id,
            document_id,
            params.page_type_model,
            params.parser_model,
            actor=request.actor,
        )
    )

    return Response.json(ProcessDocumentOutput(
        sync_job_id=sync_job_id,
        document_id=document_id,
    ).model_dump())


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/sync/(?P<sync_job_id>[^/]+)/tasks$")
@check_permission()
async def ca460_api_task_progress(request, datasette, database: str, sync_job_id: str):
    """Get task-level progress for a sync job."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    progress = await get_task_progress(db, sync_job_id)
    return Response.json({"sync_job_id": sync_job_id, "tasks": progress})


class ResumeParams(BaseModel):
    sync_job_id: str

class ResumeOutput(BaseModel):
    sync_job_id: str
    reset_count: int

@router.POST(r"^/(?P<database>[^/]+)/-/ca460/api/resume$", output=ResumeOutput)
@check_permission()
async def ca460_api_resume(request, datasette, database: str, params: Annotated[ResumeParams, Body()]):
    """Resume a stalled sync job by resetting stale tasks and re-running workers."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    # Get the job's models
    def _get_job(conn):
        cursor = conn.execute(
            "SELECT page_type_model, parser_model, status FROM datasette_ca460_sync_jobs WHERE id = ?",
            (params.sync_job_id,)
        )
        return cursor.fetchone()

    job = await db.execute_write_fn(_get_job)
    if not job:
        return Response.json({"error": "Sync job not found"}, status=404)

    page_type_model, parser_model, status = job

    # Reset stale running tasks
    reset_count = await reset_stale_tasks(db, params.sync_job_id)

    # Mark job as running again if it was stuck
    if status != "running":
        def _reopen(conn):
            conn.execute(
                "UPDATE datasette_ca460_sync_jobs SET status = 'running', completed_at = NULL, error = NULL WHERE id = ?",
                (params.sync_job_id,)
            )
            conn.commit()
        await db.execute_write_fn(_reopen)

    # Restart workers in background
    asyncio.create_task(
        run_resume_in_background(
            datasette,
            database,
            params.sync_job_id,
            parser_model,
            actor=request.actor,
        )
    )

    return Response.json(ResumeOutput(
        sync_job_id=params.sync_job_id,
        reset_count=reset_count,
    ).model_dump())


# ---------------------------------------------------------------------------
# DocumentCloud browsing / import endpoints
# ---------------------------------------------------------------------------

def _get_dc_token(datasette) -> str | None:
    config = datasette.plugin_config("datasette-ca460") or {}
    return config.get("documentcloud_token")


class DcConfigOutput(BaseModel):
    authenticated: bool

@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/dc/config$", output=DcConfigOutput)
@check_permission()
async def ca460_api_dc_config(request, datasette, database: str):
    """Return DocumentCloud integration config for the frontend."""
    token = _get_dc_token(datasette)
    return Response.json(DcConfigOutput(authenticated=token is not None).model_dump())


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/dc/search$")
@check_permission()
async def ca460_api_dc_search(request, datasette, database: str):
    """Proxy search to DocumentCloud API."""
    q = request.args.get("q", "")
    page = int(request.args.get("page", "1"))
    per_page = int(request.args.get("per_page", "25"))
    ordering = request.args.get("ordering", "-created_at")

    token = _get_dc_token(datasette)
    async with DocumentCloudClient(token=token) as client:
        result = await client.search(q, page=page, per_page=per_page, ordering=ordering)

    return Response.json(result)


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/dc/document/(?P<dc_id>\d+)$")
@check_permission()
async def ca460_api_dc_document(request, datasette, database: str, dc_id: str):
    """Return single document metadata from DocumentCloud."""
    token = _get_dc_token(datasette)
    async with DocumentCloudClient(token=token) as client:
        result = await client.get_document(int(dc_id))
    return Response.json(result)


@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/dc/project/(?P<project_id>\d+)$")
@check_permission()
async def ca460_api_dc_project(request, datasette, database: str, project_id: str):
    """Return project metadata + paginated document list."""
    page = int(request.args.get("page", "1"))
    per_page = int(request.args.get("per_page", "25"))

    token = _get_dc_token(datasette)
    async with DocumentCloudClient(token=token) as client:
        project = await client.get_project(int(project_id))
        docs = await client.list_project_documents(int(project_id), page=page, per_page=per_page)

    return Response.json({"project": project, "documents": docs})


class ResolveUrlRequest(BaseModel):
    url: str

class ResolveUrlOutput(BaseModel):
    type: str
    id: int

@router.POST(r"^/(?P<database>[^/]+)/-/ca460/api/dc/resolve-url$", output=ResolveUrlOutput)
@check_permission()
async def ca460_api_dc_resolve_url(request, datasette, database: str, body: Annotated[ResolveUrlRequest, Body()]):
    """Parse a DocumentCloud URL into type + ID."""
    parsed = parse_documentcloud_url(body.url)
    if parsed is None:
        return Response.json({"error": "Unrecognised DocumentCloud URL"}, status=400)
    return Response.json(parsed)


class DcImportRequest(BaseModel):
    document_ids: list[int]
    page_type_model: str
    parser_model: str

class DcImportOutput(BaseModel):
    sync_job_id: str

@router.POST(r"^/(?P<database>[^/]+)/-/ca460/api/dc/import$", output=DcImportOutput)
@check_permission()
async def ca460_api_dc_import(request, datasette, database: str, body: Annotated[DcImportRequest, Body()]):
    """Import selected DocumentCloud documents."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)



    sync_job_id = str(uuid.uuid4())

    def _create_job(conn):
        conn.execute(
            "INSERT INTO datasette_ca460_sync_jobs (id, page_type_model, parser_model) VALUES (?, ?, ?)",
            (sync_job_id, body.page_type_model, body.parser_model)
        )
        conn.commit()
    await db.execute_write_fn(_create_job)

    token = _get_dc_token(datasette)
    asyncio.create_task(
        run_sync_documents_in_background(
            datasette,
            database,
            sync_job_id,
            body.document_ids,
            body.page_type_model,
            body.parser_model,
            token=token,
            actor=request.actor,
        )
    )

    return Response.json(DcImportOutput(sync_job_id=sync_job_id).model_dump())


# ---------------------------------------------------------------------------
# Third-party ingest endpoint
#
# One-shot entry point for external services (e.g. a webhook or scheduled job
# holding a datasette-auth-tokens bearer token with the datasette-ca460-ingest
# permission). POST a DocumentCloud URL; ca460 resolves it, creates a sync
# job, and starts parsing in the background using the default models
# configured for each ca460 purpose in datasette-llm.
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    url: str
    page_type_model: Optional[str] = None
    parser_model: Optional[str] = None

class IngestOutput(BaseModel):
    sync_job_id: str
    document_ids: list[int]


async def _default_model_id(ds_llm, purpose: str, actor: Optional[dict]) -> Optional[str]:
    models = await ds_llm.models(purpose=purpose, actor=actor)
    return models[0].model_id if models else None


@router.POST(r"^/(?P<database>[^/]+)/-/ca460/api/ingest$", output=IngestOutput)
@check_permission(INGEST_PERMISSION)
async def ca460_api_ingest(request, datasette, database: str, body: Annotated[IngestRequest, Body()]):
    """Ingest a DocumentCloud document URL and kick off parsing in the background."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    parsed = parse_documentcloud_url(body.url)
    if parsed is None:
        return Response.json({"error": "Unrecognised DocumentCloud URL"}, status=400)
    if parsed["type"] != "document":
        return Response.json(
            {"error": f"Only document URLs are supported, got {parsed['type']}"},
            status=400,
        )

    document_ids = [parsed["id"]]

    ds_llm = LLM(datasette)
    page_type_model = body.page_type_model or await _default_model_id(
        ds_llm, "ca460-classify", request.actor
    )
    parser_model = body.parser_model or await _default_model_id(
        ds_llm, "ca460-parse", request.actor
    )
    if not page_type_model or not parser_model:
        return Response.json(
            {"error": "No default model available for one or both ca460 purposes"},
            status=500,
        )

    sync_job_id = str(uuid.uuid4())

    def _create_job(conn):
        conn.execute(
            "INSERT INTO datasette_ca460_sync_jobs (id, page_type_model, parser_model) VALUES (?, ?, ?)",
            (sync_job_id, page_type_model, parser_model),
        )
        conn.commit()
    await db.execute_write_fn(_create_job)

    token = _get_dc_token(datasette)
    asyncio.create_task(
        run_sync_documents_in_background(
            datasette,
            database,
            sync_job_id,
            document_ids,
            page_type_model,
            parser_model,
            token=token,
            actor=request.actor,
        )
    )

    return Response.json(
        IngestOutput(sync_job_id=sync_job_id, document_ids=document_ids).model_dump()
    )
