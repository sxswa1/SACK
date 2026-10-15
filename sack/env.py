"""Load repository-local runtime settings before other SACK modules import."""

from pathlib import Path

from dotenv import load_dotenv


def load_project_env(path: str | Path | None = None) -> bool:
    """Load the project .env without overriding the process environment.

    Resolve the default from this source file, rather than the current working
    directory, so scripts and the CLI use the same configuration.
    """
    env_path = Path(path) if path is not None else Path(__file__).resolve().parent.parent / ".env"
    return load_dotenv(dotenv_path=env_path, override=False, encoding="utf-8")
