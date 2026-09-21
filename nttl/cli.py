import typer

from nttl import __version__

app = typer.Typer(add_completion=False, help="Nighttime Timelapse")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"nttl {__version__}")
        raise typer.Exit


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit"
    ),
) -> None:
    pass


def main() -> None:
    app()
