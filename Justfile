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
    DATASETTE_SECRET=abc123 uv run \
      --with datasette-debug-gotham \
      datasette \
        --root \
        -s permissions.ca460_access.id "*" \
        -p 8007 \
        tmp.db \
        --plugins-dir example \
        {{flags}}

test *flags:
    uv run pytest tests/ {{flags}}

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
