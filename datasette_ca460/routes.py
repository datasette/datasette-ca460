from pathlib import Path
from typing import Optional
from datasette_llm_accountant import LlmWrapper
from datasette import Response
from datasette_plugin_router import Router
from pydantic import BaseModel
import json
from .sync import run_sync_in_background
import asyncio
import uuid

router = Router()

async def render_vite_entry(datasette, entrypoint: str) -> str:
    return await datasette.render_template(
        "ca460_vite_entry.html",
        {
            "entry_name": entrypoint,
        }
    )

@router.GET(r"^/(?P<database>[^/]+)/-/ca460$")
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
        await render_vite_entry(datasette, "src/index_view.ts")
    )
    
@router.GET(r"^/(?P<database>[^/]+)/-/ca460/sync$")
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
        await render_vite_entry(datasette, "src/sync_view.ts")
    )


# TODO permissions check
@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/models$")
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
    page_count: int
    title: Optional[str]
    model_count: int

class DocumentListResponse(BaseModel):
    documents: list[DocumentListItem]

# TODO permissions check
@router.GET(r"^/(?P<database>[^/]+)/-/ca460/api/documents$", output=DocumentListResponse)
async def ca460_api_documents(request, datasette):
    """API endpoint to get list of documents with parsed data."""
    database_name = request.url_vars["database"]

    try:
        db = datasette.get_database(database_name)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    def _get_documents(conn):
        # Get documents that have been parsed by at least one model
        cursor = conn.execute("""
            SELECT DISTINCT 
                d.id,
                d.page_count,
                d.data->>'title' as title,
                (
                    SELECT COUNT(DISTINCT pp.model)
                    FROM pages p
                    JOIN page_parsed pp ON p.id = pp.page_id
                    WHERE p.document_id = d.id
                ) as model_count
            FROM documents d
            JOIN pages p ON d.id = p.document_id
            JOIN page_parsed pp ON p.id = pp.page_id
            ORDER BY d.id DESC
        """)
        rows = cursor.fetchall()
        return [
            {
                "id": row[0],
                "page_count": row[1],
                "title": row[2],
                "model_count": row[3],
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
async def ca460_api_document_parsed(request, datasette, database: str, document_id: str):
    """API endpoint to get all parsed data for a document, grouped by model."""
    try:
        db = datasette.get_database(database)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    def _get_parsed_data(conn):
        # Get document info
        cursor = conn.execute(
            "SELECT id, page_count, data FROM documents WHERE id = ?",
            (document_id,)
        )
        doc_row = cursor.fetchone()
        if not doc_row:
            return None

        doc_data = json.loads(doc_row[2]) if doc_row[2] else {}

        # Get all parsed data for this document, grouped by model
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

        # Group by model
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

        return {
            "document": {
                "id": doc_row[0],
                "page_count": doc_row[1],
                "title": doc_data.get("title", f"Document {doc_row[0]}"),
            },
            "models": models,
        }

    try:
        data = await db.execute_fn(_get_parsed_data)
    except Exception as e:
        return Response.json({"error": str(e)}, status=500)

    if data is None:
        return Response.json({"error": "Document not found"}, status=404)

    return Response.json(data)



@router.GET(r"^/(?P<database>[^/]+)/-/ca460/sync/(?P<sync_job_id>[^/]+)/events$")
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

SCHEMA = (Path(__file__).parent / "schema.sql").read_text()

@router.POST(r"^/(?P<database>[^/]+)/-/ca460/api/sync$")
async def ca460_api_sync(request, datasette):
    """API endpoint to start a sync job."""
    database_name = request.url_vars["database"]

    if request.method != "POST":
        return Response.json({"error": "Method not allowed"}, status=405)

    try:
        db = datasette.get_database(database_name)
    except KeyError:
        return Response.json({"error": "Database not found"}, status=404)

    # Parse JSON body
    try:
        body = await request.post_body()
        data = json.loads(body)
    except Exception:
        return Response.json({"error": "Invalid JSON body"}, status=400)

    project_id = data.get("project_id")
    page_type_model = data.get("page_type_model", "llama-server")
    parser_model = data.get("parser_model", "gemini-3-flash-preview")

    if not project_id:
        return Response.json({"error": "Please provide a DocumentCloud project ID"}, status=400)

    try:
        project_id = int(project_id)
    except ValueError:
        return Response.json({"error": "Project ID must be a number"}, status=400)

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

    return Response.json({
        "sync_job_id": sync_job_id,
        "project_id": project_id,
        "page_type_model": page_type_model,
        "parser_model": parser_model,
    })

