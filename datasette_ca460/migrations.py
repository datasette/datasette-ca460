from sqlite_utils import Database
from sqlite_migrate import Migrations

migrations = Migrations("datasette-ca460")


@migrations()
def m001_initial(db: Database):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS datasette_ca460_sync_jobs(
            id TEXT PRIMARY KEY,
            project_id INTEGER,
            page_type_model TEXT,
            parser_model TEXT,
            status TEXT DEFAULT 'running',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS datasette_ca460_sync_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_job_id TEXT REFERENCES datasette_ca460_sync_jobs(id),
            event_type TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS datasette_ca460_documents(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL DEFAULT 'upload',
            page_count INTEGER,
            data JSONB
        );

        CREATE TABLE IF NOT EXISTS datasette_ca460_document_files(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER REFERENCES datasette_ca460_documents(id) UNIQUE,
            filename TEXT,
            file_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS datasette_ca460_pages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER REFERENCES datasette_ca460_documents(id),
            page_number INTEGER,
            image BLOB,
            image_url TEXT
        );

        CREATE TABLE IF NOT EXISTS datasette_ca460_page_type_predictions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER REFERENCES datasette_ca460_pages(id),
            model TEXT,
            predicted_page_type TEXT,
            model_usage JSON,
            timing JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS datasette_ca460_page_parsed(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER REFERENCES datasette_ca460_pages(id),
            page_type TEXT,
            model TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model_usage JSON,
            timing JSON,
            parsed_data JSON
        );

        CREATE TABLE IF NOT EXISTS datasette_ca460_page_images(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id INTEGER REFERENCES datasette_ca460_pages(id) UNIQUE,
            image BLOB NOT NULL
        );

        CREATE TABLE IF NOT EXISTS datasette_ca460_page_tasks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_job_id TEXT REFERENCES datasette_ca460_sync_jobs(id),
            document_id INTEGER REFERENCES datasette_ca460_documents(id),
            page_id INTEGER REFERENCES datasette_ca460_pages(id),
            page_number INTEGER,
            task_type TEXT NOT NULL,
            page_type TEXT,
            model TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        );
    """)
