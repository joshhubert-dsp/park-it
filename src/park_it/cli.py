import importlib.resources
from pathlib import Path

import typer
from google_auth_oauthlib.flow import InstalledAppFlow
from pydantic import FilePath

from park_it.app.build_app import DEFAULT_GOOGLE_TOKEN_FILE
from park_it.services.email.gmailer import REDIRECT_PORT, SCOPES

app = typer.Typer(
    no_args_is_help=True,
    help="A park-it command line interface is provided with a few conveniences.",
    context_settings={"help_option_names": ["-h", "--help"]},
)

EXAMPLE_ROOT = Path(str(importlib.resources.files("park_it"))) / "example"


@app.command()
def serve_example(port: int = typer.Argument(8000, help="localhost port to serve on.")):
    """Builds and serves a non-functional static example site template on `localhost:PORT` for viewing purposes. Note that the embedded calendar view won't work since it's serving the page template directly (you'll see a bit of jinja syntax that the app uses to serve it), but you'll get a decent idea anyway."""
    import contextlib

    from mkdocs.commands.serve import serve

    with contextlib.chdir(EXAMPLE_ROOT):
        serve(
            config_file="mkdocs.yml",
            open_in_browser=True,
            dev_addr=f"localhost:{port}",
        )


@app.command()
def init(
    project_root: Path | None = typer.Argument(
        None,
        help="Root path of your project to initialize. If not passed, uses the current working directory. ",
    ),
):
    """Initializes a new park-it project with the necessary directories and files, copied directly from the `example` dir."""
    if not project_root:
        project_root = Path.cwd()

    for file_or_dir in EXAMPLE_ROOT.rglob("*"):
        relative = file_or_dir.relative_to(EXAMPLE_ROOT)

        if file_or_dir.is_file():
            dest = project_root / relative
            if not dest.exists():
                try:
                    dest.write_text(file_or_dir.read_text("utf-8"), "utf-8")
                except UnicodeDecodeError:  # not text, probably an image, don't need it
                    pass
            elif file_or_dir.name == ".gitignore":
                # append to an existing gitignore
                with open(dest, "a", encoding="utf-8") as f:
                    f.write("\n" + file_or_dir.read_text("utf-8"))

        elif file_or_dir.is_dir():
            if file_or_dir.name == "__pycache__":
                continue
            (project_root / relative).mkdir(parents=True, exist_ok=True)


@app.command()
def oauth(
    secret_read_path: FilePath = typer.Argument(
        help="Path to your downloaded Google App client secret file."
    ),
    token_write_path: FilePath | None = typer.Argument(
        None,
        help="Path to write the generated token file to. If not passed, writes `auth-token.json` to the same directory as the client secret file.",
    ),
    port: int = typer.Option(REDIRECT_PORT, help="localhost port to serve on."),
):
    """
    Run the Google OAuth Installed App flow with your downloaded client secret file, to generate a long-lived refresh token file for use by the app.
    """
    flow = InstalledAppFlow.from_client_secrets_file(secret_read_path, SCOPES)
    creds = flow.run_local_server(port=port, open_browser=True)
    assert creds is not None
    if token_write_path is None:
        token_write_path = secret_read_path.parent / DEFAULT_GOOGLE_TOKEN_FILE
    token_write_path.write_text(creds.to_json(), "utf8")


if __name__ == "__main__":
    app()
