from datasette import hookimpl

from typing import Optional
from textwrap import dedent
import json
from pathlib import Path
from .routes import router
from pydantic import BaseModel

@hookimpl
def register_routes():
    return router.routes()

@hookimpl
def database_actions(datasette, database):
    return [
        {
            "label": "Sync Form 460 data",
            "href": datasette.urls.database(database) + "/-/ca460/"
        }
    ]

# https://vite.dev/guide/backend-integration.html
class ManifestChunk(BaseModel):
    """Vite manifest chunk."""
    src: Optional[str] = None
    file: str  # The output file name of this chunk / asset
    css: Optional[list[str]] = None  # The list of CSS files imported by this chunk (JS chunks only)
    assets: Optional[list[str]] = None  # The list of asset files imported by this chunk, excluding CSS (JS chunks only)
    isEntry: Optional[bool] = None  # Whether this chunk or asset is an entry point
    name: Optional[str] = None  # The name of this chunk / asset if known
    isDynamicEntry: Optional[bool] = None  # Whether this chunk is a dynamic entry point (JS chunks only)
    imports: Optional[list[str]] = None  # The list of statically imported chunks (JS chunks only)
    dynamicImports: Optional[list[str]] = None  # The list of dynamically imported chunks (JS chunks only)

@hookimpl
def extra_template_vars(datasette, database):
    import os
    vite_path = os.environ.get("DATASETTE_CA460_VITE_PATH")
    if vite_path:
        pass
    else: 
        manifest_raw = json.loads((Path(__file__).parent / "manifest.json").read_text())
        manifest: dict[str, ManifestChunk] = {
            k: ManifestChunk(**v) for k, v in manifest_raw.items()
        }
        
        # from vite docs:
        # Specifically, a backend generating HTML should include the following tags 
        # given a manifest file and an entry point. Note that following this order 
        # is recommended for optimal performance:

        # 1. A <link rel="stylesheet"> tag for each file in 
        #    the entry point chunk's css list (if it exists)
        # 2. Recursively follow all chunks in the entry point's 
        #    imports list and include a <link rel="stylesheet"> 
        #    tag for each CSS file of each imported chunk's css 
        #    list (if it exists).
        # 3. A tag for the file key of the entry point chunk. 
        #    This can be <script type="module"> for JavaScript, 
        #    <link rel="stylesheet"> for CSS.
        # 4. Optionally, <link rel="modulepreload"> tag for 
        #    the file of each imported JavaScript chunk, again 
        #    recursively following the imports starting from 
        #    the entry point chunk.


    async def datasette_ca460_vite_entry(entrypoint):
        # https://vite.dev/guide/backend-integration.html

        if vite_path:
          return dedent(f"""
          
          <script type="module" src="{vite_path}@vite/client"></script>
          <script type="module" src="{vite_path}{entrypoint}"></script>
          
          """
          )
        else:
            chunk  = manifest.get(entrypoint)
            if not chunk:
                raise ValueError(f"Entrypoint {entrypoint} not found in manifest")
            parts = []
            
            # part 1, css files
            for css in chunk.css or []:
                file = str(Path(css).relative_to("static"))
                href = datasette.urls.static_plugins("datasette_ca460", file)
                parts.append(f'<link rel="stylesheet" href="{href}">')
            
            # part 2, import lists's chunks css files
            # TODO

            # part 3, entry point script
            # pop first path part which is always "static/"
            file = str(Path(chunk.file).relative_to("static"))
            src = datasette.urls.static_plugins("datasette_ca460", file)
            parts.append(f'<script type="module" src="{src}"></script>')

            # skip part 4
            return "\n".join(parts)

            
      
    return {"datasette_ca460_vite_entry": datasette_ca460_vite_entry}



