
dev *options:
  DATASETTE_CA460_VITE_PATH=http://localhost:5177/ \
  watchexec \
    --stop-signal SIGKILL \
    -e py,html \
    --ignore '*.db' \
    --ignore '*.db-journal' \
    --ignore '*.db-wal' \
    --restart \
    --clear -- \
    just sample {{options}}

dev-frontend:
  npm run dev --prefix frontend -- --port 5177

frontend-build:
  npm run build --prefix frontend

dev-prod *options:
  just sample {{options}}

sample *options:
  DATASETTE_SECRET=abc123 \
    uv run datasette \
      --root \
      tmp.db \
      --plugins-dir example \
      {{options}}


types: 
  uv run python -c 'from datasette_ca460 import router; import json; print(json.dumps(router.openapi_document_json()))' \
    | npx --prefix frontend openapi-typescript > frontend/api.d.ts

