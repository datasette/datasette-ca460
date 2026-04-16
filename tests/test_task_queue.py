"""Tests for the SQLite-backed task queue in sync.py."""

import json
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from datasette.app import Datasette
from sqlite_utils import Database as SqliteUtilsDatabase

from datasette_ca460.migrations import migrations
from datasette_ca460.sync import (
    claim_task,
    complete_task,
    create_classify_tasks,
    create_parse_task_for_page,
    fail_task,
    get_job_summary,
    get_task_progress,
    log_event,
    reset_stale_tasks,
    STALE_TASK_TIMEOUT_MINUTES,
)


@pytest_asyncio.fixture
async def ds():
    """Create a Datasette instance with schema applied and a sample document with pages."""
    datasette = Datasette(memory=True)
    db = datasette.get_database("_memory")

    def _setup(conn):
        migrations.apply(SqliteUtilsDatabase(conn))
        # Create a sync job
        conn.execute(
            "INSERT INTO datasette_ca460_sync_jobs(id, status) VALUES ('job-1', 'running')"
        )
        # Create a document with 3 pages
        conn.execute(
            "INSERT INTO datasette_ca460_documents(id, source, page_count, data) VALUES (1, 'upload', 3, '{}')"
        )
        for i in range(1, 4):
            conn.execute(
                "INSERT INTO datasette_ca460_pages(document_id, page_number, image) VALUES (1, ?, ?)",
                (i, b"fake-image"),
            )
        conn.commit()

    await db.execute_write_fn(_setup)
    return datasette, db


# ---------------------------------------------------------------------------
# log_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_event(ds):
    _, db = ds
    await log_event(db, "job-1", "info", "hello world")

    def _check(conn):
        row = conn.execute(
            "SELECT sync_job_id, event_type, message FROM datasette_ca460_sync_events"
        ).fetchone()
        return row

    row = await db.execute_write_fn(_check)
    assert tuple(row) == ("job-1", "info", "hello world")


@pytest.mark.asyncio
async def test_log_event_multiple(ds):
    _, db = ds
    await log_event(db, "job-1", "info", "first")
    await log_event(db, "job-1", "error", "second")

    def _check(conn):
        return conn.execute("SELECT COUNT(*) FROM datasette_ca460_sync_events").fetchone()[0]

    assert await db.execute_write_fn(_check) == 2


# ---------------------------------------------------------------------------
# create_classify_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_classify_tasks(ds):
    _, db = ds
    count = await create_classify_tasks(db, "job-1", 1, "gemini-1.5-flash")
    assert count == 3  # 3 pages

    def _check(conn):
        rows = conn.execute(
            "SELECT page_number, task_type, model, status FROM datasette_ca460_page_tasks ORDER BY page_number"
        ).fetchall()
        return rows

    rows = await db.execute_write_fn(_check)
    assert len(rows) == 3
    assert all(r[1] == "classify" for r in rows)
    assert all(r[2] == "gemini-1.5-flash" for r in rows)
    assert all(r[3] == "pending" for r in rows)


@pytest.mark.asyncio
async def test_create_classify_tasks_skips_existing_predictions(ds):
    _, db = ds

    # Pre-insert a prediction for page 1
    def _predict(conn):
        page_id = conn.execute(
            "SELECT id FROM datasette_ca460_pages WHERE page_number = 1"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO datasette_ca460_page_type_predictions(page_id, model, predicted_page_type) VALUES (?, ?, ?)",
            (page_id, "gemini-1.5-flash", "cover-page"),
        )
        conn.commit()

    await db.execute_write_fn(_predict)

    count = await create_classify_tasks(db, "job-1", 1, "gemini-1.5-flash")
    assert count == 3  # returns total page count

    def _check(conn):
        return conn.execute("SELECT COUNT(*) FROM datasette_ca460_page_tasks").fetchone()[0]

    assert await db.execute_write_fn(_check) == 2  # only 2 tasks created


@pytest.mark.asyncio
async def test_create_classify_tasks_idempotent(ds):
    _, db = ds
    await create_classify_tasks(db, "job-1", 1, "gemini-1.5-flash")
    await create_classify_tasks(db, "job-1", 1, "gemini-1.5-flash")

    def _check(conn):
        return conn.execute("SELECT COUNT(*) FROM datasette_ca460_page_tasks").fetchone()[0]

    assert await db.execute_write_fn(_check) == 3  # no duplicates


# ---------------------------------------------------------------------------
# claim_task / complete_task / fail_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_task(ds):
    _, db = ds
    await create_classify_tasks(db, "job-1", 1, "model-x")

    task = await claim_task(db, "job-1")
    assert task is not None
    assert task["task_type"] == "classify"
    assert task["model"] == "model-x"
    assert task["document_id"] == 1

    # The claimed task should now be "running"
    def _check(conn):
        return conn.execute(
            "SELECT status FROM datasette_ca460_page_tasks WHERE id = ?", (task["id"],)
        ).fetchone()[0]

    assert await db.execute_write_fn(_check) == "running"


@pytest.mark.asyncio
async def test_claim_task_returns_none_when_empty(ds):
    _, db = ds
    task = await claim_task(db, "job-1")
    assert task is None


@pytest.mark.asyncio
async def test_claim_task_prefers_classify(ds):
    _, db = ds

    # Create one parse task and one classify task
    def _setup(conn):
        page_id = conn.execute("SELECT id FROM datasette_ca460_pages WHERE page_number = 1").fetchone()[0]
        conn.execute(
            """INSERT INTO datasette_ca460_page_tasks
            (sync_job_id, document_id, page_id, page_number, task_type, model, status)
            VALUES ('job-1', 1, ?, 1, 'parse', 'model-x', 'pending')""",
            (page_id,),
        )
        page_id2 = conn.execute("SELECT id FROM datasette_ca460_pages WHERE page_number = 2").fetchone()[0]
        conn.execute(
            """INSERT INTO datasette_ca460_page_tasks
            (sync_job_id, document_id, page_id, page_number, task_type, model, status)
            VALUES ('job-1', 1, ?, 2, 'classify', 'model-x', 'pending')""",
            (page_id2,),
        )
        conn.commit()

    await db.execute_write_fn(_setup)

    task = await claim_task(db, "job-1", preferred_type="classify")
    assert task["task_type"] == "classify"


@pytest.mark.asyncio
async def test_claim_task_falls_back_to_other_type(ds):
    _, db = ds

    def _setup(conn):
        page_id = conn.execute("SELECT id FROM datasette_ca460_pages WHERE page_number = 1").fetchone()[0]
        conn.execute(
            """INSERT INTO datasette_ca460_page_tasks
            (sync_job_id, document_id, page_id, page_number, task_type, model, status)
            VALUES ('job-1', 1, ?, 1, 'parse', 'model-x', 'pending')""",
            (page_id,),
        )
        conn.commit()

    await db.execute_write_fn(_setup)

    # Prefer classify, but only parse is available
    task = await claim_task(db, "job-1", preferred_type="classify")
    assert task["task_type"] == "parse"


@pytest.mark.asyncio
async def test_complete_task(ds):
    _, db = ds
    await create_classify_tasks(db, "job-1", 1, "model-x")
    task = await claim_task(db, "job-1")
    await complete_task(db, task["id"])

    def _check(conn):
        row = conn.execute(
            "SELECT status, completed_at FROM datasette_ca460_page_tasks WHERE id = ?",
            (task["id"],),
        ).fetchone()
        return row

    row = await db.execute_write_fn(_check)
    assert row[0] == "completed"
    assert row[1] is not None


@pytest.mark.asyncio
async def test_fail_task(ds):
    _, db = ds
    await create_classify_tasks(db, "job-1", 1, "model-x")
    task = await claim_task(db, "job-1")
    await fail_task(db, task["id"], "rate limit exceeded")

    def _check(conn):
        row = conn.execute(
            "SELECT status, error FROM datasette_ca460_page_tasks WHERE id = ?",
            (task["id"],),
        ).fetchone()
        return row

    row = await db.execute_write_fn(_check)
    assert row[0] == "failed"
    assert row[1] == "rate limit exceeded"


# ---------------------------------------------------------------------------
# reset_stale_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_stale_tasks(ds):
    _, db = ds
    await create_classify_tasks(db, "job-1", 1, "model-x")

    # Claim a task, then backdate its started_at to make it stale
    task = await claim_task(db, "job-1")

    def _make_stale(conn):
        stale_time = (datetime.now() - timedelta(minutes=STALE_TASK_TIMEOUT_MINUTES + 1)).isoformat()
        conn.execute(
            "UPDATE datasette_ca460_page_tasks SET started_at = ? WHERE id = ?",
            (stale_time, task["id"]),
        )
        conn.commit()

    await db.execute_write_fn(_make_stale)

    count = await reset_stale_tasks(db, "job-1")
    assert count == 1

    def _check(conn):
        return conn.execute(
            "SELECT status, started_at FROM datasette_ca460_page_tasks WHERE id = ?",
            (task["id"],),
        ).fetchone()

    row = await db.execute_write_fn(_check)
    assert row[0] == "pending"
    assert row[1] is None


@pytest.mark.asyncio
async def test_reset_stale_tasks_ignores_recent(ds):
    _, db = ds
    await create_classify_tasks(db, "job-1", 1, "model-x")
    await claim_task(db, "job-1")  # just started, not stale

    count = await reset_stale_tasks(db, "job-1")
    assert count == 0


# ---------------------------------------------------------------------------
# create_parse_task_for_page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_parse_task(ds):
    _, db = ds

    def _get_page(conn):
        return conn.execute("SELECT id FROM datasette_ca460_pages WHERE page_number = 1").fetchone()[0]

    page_id = await db.execute_write_fn(_get_page)

    await create_parse_task_for_page(
        db, "job-1", 1, page_id, 1, "schedule-a", "gemini-pro"
    )

    def _check(conn):
        row = conn.execute(
            "SELECT task_type, page_type, model, status FROM datasette_ca460_page_tasks WHERE page_id = ?",
            (page_id,),
        ).fetchone()
        return row

    row = await db.execute_write_fn(_check)
    assert tuple(row) == ("parse", "schedule-a", "gemini-pro", "pending")


@pytest.mark.asyncio
async def test_create_parse_task_skips_unknown(ds):
    _, db = ds

    def _get_page(conn):
        return conn.execute("SELECT id FROM datasette_ca460_pages WHERE page_number = 1").fetchone()[0]

    page_id = await db.execute_write_fn(_get_page)

    await create_parse_task_for_page(
        db, "job-1", 1, page_id, 1, "unknown", "gemini-pro"
    )

    def _check(conn):
        return conn.execute("SELECT COUNT(*) FROM datasette_ca460_page_tasks").fetchone()[0]

    assert await db.execute_write_fn(_check) == 0


@pytest.mark.asyncio
async def test_create_parse_task_idempotent(ds):
    _, db = ds

    def _get_page(conn):
        return conn.execute("SELECT id FROM datasette_ca460_pages WHERE page_number = 1").fetchone()[0]

    page_id = await db.execute_write_fn(_get_page)

    await create_parse_task_for_page(db, "job-1", 1, page_id, 1, "schedule-a", "gemini-pro")
    await create_parse_task_for_page(db, "job-1", 1, page_id, 1, "schedule-a", "gemini-pro")

    def _check(conn):
        return conn.execute("SELECT COUNT(*) FROM datasette_ca460_page_tasks").fetchone()[0]

    assert await db.execute_write_fn(_check) == 1


# ---------------------------------------------------------------------------
# get_task_progress / get_job_summary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_task_progress(ds):
    _, db = ds
    await create_classify_tasks(db, "job-1", 1, "model-x")

    # Claim and complete one, fail another
    task1 = await claim_task(db, "job-1")
    await complete_task(db, task1["id"])
    task2 = await claim_task(db, "job-1")
    await fail_task(db, task2["id"], "oops")

    progress = await get_task_progress(db, "job-1")
    assert progress["classify"]["completed"] == 1
    assert progress["classify"]["failed"] == 1
    assert progress["classify"]["pending"] == 1


@pytest.mark.asyncio
async def test_get_task_progress_empty(ds):
    _, db = ds
    progress = await get_task_progress(db, "job-1")
    assert progress == {}


@pytest.mark.asyncio
async def test_get_job_summary(ds):
    _, db = ds
    await create_classify_tasks(db, "job-1", 1, "model-x")

    task1 = await claim_task(db, "job-1")
    await complete_task(db, task1["id"])
    task2 = await claim_task(db, "job-1")
    await complete_task(db, task2["id"])
    task3 = await claim_task(db, "job-1")
    await fail_task(db, task3["id"], "error")

    summary = await get_job_summary(db, "job-1")
    assert "2 classified" in summary
    assert "0 parsed" in summary
    assert "1 errors" in summary
