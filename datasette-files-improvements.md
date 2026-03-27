# Proposal: datasette-files API improvements for plugin authors

## Context

datasette-ca460 uses datasette-files for PDF upload/selection in the browser. After a user picks a PDF, the server needs to:

1. **Read the PDF bytes** from datasette-files to extract page images
2. **Get file metadata** (filename, content type) for the uploaded file

These are server-side operations performed by plugin code running inside the same Datasette process. There is no browser or actor involved — it's plugin-to-plugin communication.

## The problem

datasette-files only exposes an HTTP API. There is no public Python API for reading files or metadata. This forces plugin authors into hacks:

### Hack 1: Using `datasette.client` (broken)

```python
resp = await datasette.client.get(f"/-/files/{file_id}/download")
```

This fails because `datasette.client` requests have no actor, and datasette-files requires `files-browse` permission on every download. The request gets a 403 Forbidden.

Even if the permission issue were solved, `datasette.client` has other problems: the download endpoint returns a streaming ASGI response (`_StreamingFileResponse`) that the test client may not handle correctly, and for storage backends with signed URLs it returns a redirect that `datasette.client` won't follow.

### Hack 2: Reaching into private internals (fragile)

```python
from datasette_files import _sources

# Query the internal database to find the file's storage path and source
db = datasette.get_internal_database()
row = (await db.execute(
    """SELECT f.path, s.slug as source_slug
    FROM datasette_files f
    JOIN datasette_files_sources s ON f.source_id = s.id
    WHERE f.id = ?""",
    [file_id],
)).first()

storage = _sources[row["source_slug"]]
content = await storage.read_file(row["path"])
```

This works but depends on:
- The private `_sources` dict (underscore-prefixed, not part of public API)
- Knowledge of the internal database schema (`datasette_files`, `datasette_files_sources`)
- The `Storage.read_file()` method signature not changing

### Hack 3: Bypassing datasette-files entirely

For the file picker UI, we load `datasette-file-picker.js` at runtime via a script tag injection because:
- It's a plain JS module exported as `openFilePicker()`, not a web component
- Vite's dev server intercepts `import()` calls even with `@vite-ignore`
- The JS lives on the Datasette origin, not the Vite dev server

```javascript
// Have to use new Function to dodge Vite's import analysis
const url = new URL(
  '/-/static-plugins/datasette_files/datasette-file-picker.js',
  window.location.origin
).href;
const mod = await (new Function('u', 'return import(u)'))(url);
```

## Proposed improvements

### 1. Public Python API for file access

Add a public, documented Python API for server-side file operations:

```python
from datasette_files import get_file, read_file

# Get metadata
file_meta = await get_file(datasette, "df-01arwx4snjdjnv69420s4qdebc")
# Returns: {"id": "df-...", "filename": "upload.pdf", "content_type": "application/pdf", "size": 12345, ...}

# Read content
content_bytes = await read_file(datasette, "df-01arwx4snjdjnv69420s4qdebc")
# Returns: bytes
```

These functions would:
- Skip permission checks (server-side code is trusted)
- Handle the storage backend lookup internally
- Be the stable public interface, insulating callers from schema/registry changes

### 2. `<datasette-file-picker>` as a proper web component

The current `datasette-file-picker.js` exports an `openFilePicker()` function that opens a dialog. This is hard to integrate with component frameworks (Svelte, React, etc.) because:

- It's imperative (`await openFilePicker({column: "..."})`) rather than declarative
- It can't be embedded inline in a form — it always opens a modal
- Loading it from another origin (Vite dev server) requires hacks

A `<datasette-file-picker>` custom element would be easier to use:

```html
<datasette-file-picker source="my-source" accept=".pdf"></datasette-file-picker>
```

With events:
- `select` — fires when a file is picked, with `detail: {id, filename, content_type, size}`
- `upload` — fires when an upload completes

This would be declarative, embeddable, and framework-agnostic.

### 3. Extra JS URLs hook for custom pages

datasette-files loads its JS (`datasette-file-cell.js`) via `extra_js_urls` but only on `table`, `row`, and `database` views. Plugin authors using datasette-files components on custom routes get nothing.

Options:
- Load picker/upload JS on all pages (small cost, big convenience)
- Provide a helper function plugins can call in their templates: `{{ datasette_files_picker_js() }}`
- Or document a recommended pattern for dynamic loading

### 4. Permission-free internal client

More generally, Datasette could benefit from a way to make internal client requests that bypass permission checks:

```python
resp = await datasette.client.get(
    f"/-/files/{file_id}/download",
    _bypass_permissions=True,  # or _actor={"id": "root"}
)
```

This would solve the problem not just for datasette-files but for any plugin-to-plugin HTTP communication via `datasette.client`.

### 5. Configurable default permissions per plugin

datasette-files defaults to denying all access. Every deployment needs explicit permission configuration. For development and simple setups, it would help to have a way to set sensible defaults:

```yaml
plugins:
  datasette-files:
    sources:
      uploads:
        storage: filesystem
        config:
          root: ./uploads
    # Default permissions for all sources
    default_permissions:
      files-browse: true
      files-upload: true
```

## Priority

From the perspective of datasette-ca460 (and likely other plugins that build on datasette-files):

1. **Public Python read API** — highest impact, unblocks server-side file processing without hacks
2. **Web component** — improves DX for frontend integration
3. **Permission-free internal client** — solves the root cause across all plugins
4. **Default permissions** — reduces configuration friction
5. **Extra JS on all pages** — nice to have
