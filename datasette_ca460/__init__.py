from datasette import hookimpl
from datasette.permissions import Action
from datasette_vite import vite_entry
import os

# Import routes module to trigger route registration on the shared router
from . import routes
from .router import router, CA460_ACCESS_NAME
from .cli import ca460_cli

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
            "label": "Sync Form 460 data",
            "href": datasette.urls.database(database) + "/-/ca460/",
        }
    ]
