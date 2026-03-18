import click

from .add import ca460_add
from .serve import ca460_serve


@click.group(name="ca460")
def ca460_cli():
    "Process California Form 460 campaign finance filings"


ca460_cli.add_command(ca460_add)
ca460_cli.add_command(ca460_serve)
