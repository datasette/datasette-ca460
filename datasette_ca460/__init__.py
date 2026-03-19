from datasette import hookimpl
from datasette.permissions import Action
from datasette_vite import vite_entry
import os

# Import routes module to trigger route registration on the shared router
from . import routes
from .router import router, CA460_ACCESS_NAME
from .cli import ca460_cli

try:
    from datasette_sidebar.hookspecs import SidebarApp
    _has_sidebar = True
except ImportError:
    _has_sidebar = False

_ = routes


@hookimpl
def register_routes():
    return router.routes()


@hookimpl
def extra_template_vars(datasette):
    entry = vite_entry(
        datasette=datasette,
        plugin_package="datasette_ca460",
        vite_dev_path=os.environ.get("DATASETTE_CA460_VITE_PATH"),
    )
    return {"datasette_ca460_vite_entry": entry}


@hookimpl
def register_actions(datasette):
    return [
        Action(
            name=CA460_ACCESS_NAME,
            description="Can access CA 460 features",
        ),
    ]


@hookimpl
def register_commands(cli):
    cli.add_command(ca460_cli)


@hookimpl
def database_actions(datasette, database):
    return [
        {
            "label": "Form 460 data",
            "href": datasette.urls.database(database) + "/-/ca460/",
        }
    ]


if _has_sidebar:

    @hookimpl
    def datasette_sidebar_apps(datasette):
        def href(db):
            if db:
                return f"/{db}/-/ca460"
            # If only one database, link directly to it
            databases = [name for name in datasette.databases if name != "_internal"]
            if len(databases) == 1:
                return f"/{databases[0]}/-/ca460"
            return None

        return [
            SidebarApp(
                label="CA Form 460",
                description="Campaign finance filings",
                href=href,
                icon='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
                color="#0066cc",
            ),
        ]
