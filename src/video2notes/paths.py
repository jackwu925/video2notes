import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def project_root() -> Path:
    """Return the repository root used for relative runtime artifacts."""
    env_root = os.getenv("VIDEO2NOTES_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    source_path = Path(__file__).expanduser().resolve()
    for parent in source_path.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src" / "video2notes").exists():
            return parent

    return Path.cwd().resolve()


def user_path(path: str | Path) -> Path:
    """Return a user-expanded path without converting relative paths to absolute paths."""
    return Path(path).expanduser()


def display_path(path: str | Path) -> str:
    """Format project paths as relative paths whenever possible."""
    raw_path = user_path(path)
    if not raw_path.is_absolute():
        return raw_path.as_posix()

    roots = (project_root(), Path.cwd().resolve())
    for root in roots:
        try:
            return raw_path.relative_to(root).as_posix()
        except ValueError:
            continue
    return raw_path.as_posix()


def sanitize_project_paths(text: str) -> str:
    """Hide local checkout paths in UI-facing text such as logs and errors."""
    sanitized = text
    roots = {project_root(), Path.cwd().resolve()}
    for root in roots:
        root_text = root.as_posix()
        sanitized = sanitized.replace(root_text + "/", "")
        sanitized = sanitized.replace(root_text, ".")
    return sanitized

