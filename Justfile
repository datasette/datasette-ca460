# Type generation
types-routes:
  uv run python -c 'from datasette_ca460.router import router; import json; print(json.dumps(router.openapi_document_json()))' \
    | npx --prefix frontend openapi-typescript > frontend/api.d.ts

types:
  just types-routes

types-watch:
  watchexec \
    -e py \
    --clear -- \
      just types

DEV_PORT := "5177"

# Frontend building
frontend *flags:
    npm run build --prefix frontend {{flags}}

frontend-dev *flags:
    npm run dev --prefix frontend -- --port {{DEV_PORT}} {{flags}}

# Formatting
format-frontend *flags:
    npm run format --prefix frontend {{flags}}

format-frontend-check *flags:
    npm run format:check --prefix frontend {{flags}}

lint *flags:
    uv run ruff check {{flags}}

format-backend *flags:
    uv run ruff format {{flags}}

format-backend-check *flags:
    uv run ruff format --check {{flags}}

format:
    just format-backend
    just format-frontend

format-check:
    just format-backend-check
    just format-frontend-check

# Type checking
check-frontend:
    npm run check --prefix frontend

check-backend:
    uvx ty check

check:
    just check-backend
    just check-frontend

# Development servers
dev *flags:
    mkdir -p example/fs
    DATASETTE_SECRET=abc123 uv run \
      --with datasette-debug-gotham \
      --with datasette-sidebar \
      datasette \
        -s permissions.datasette-ca460-access.id "*" \
        -s permissions.datasette-sidebar-access.id "*" \
        -s plugins.datasette-llm.purposes.ca460-classify.models '["gemini/gemini-3-flash-preview"]' \
        -s plugins.datasette-llm.purposes.ca460-parse.models '["gemini/gemini-3-flash-preview"]' \
        --plugins-dir example \
        {{flags}}

dev-tmp:
  DATASETTE_SECRET=abc123 uv run \
      --no-project \
      --with-editable . \
      --with 'datasette>1a' \
      --with datasette-debug-gotham \
      --with datasette-sidebar \
      --with "datasette-auth-tokens==0.4a12" \
      datasette \
        -s permissions.datasette-ca460-access.id "*" \
        -s permissions.datasette-ca460-ingest.id "*" \
        -s permissions.datasette-sidebar-access.id "*" \
        -s permissions.auth-tokens-create.id clark \
        -s plugins.datasette-auth-tokens.manage_tokens true \
        --plugins-dir example \
        -p 3039 x.db --internal internalx.db --create

test *flags:
    uv run --extra files pytest tests/ {{flags}}

dev-with-hmr *flags:
    DATASETTE_CA460_VITE_PATH=http://localhost:{{DEV_PORT}}/ \
    watchexec \
      --stop-signal SIGKILL \
      -e py,html \
      --ignore '*.db' \
      --ignore '*.db-journal' \
      --ignore '*.db-wal' \
      --restart \
      --clear -- \
      just dev {{flags}}
