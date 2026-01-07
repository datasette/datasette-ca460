dev *options:
  DATASETTE_SECRET=abc123 \
    uv run datasette \
      --root \
      tmp.db \
      --plugins-dir example \
      {{options}}