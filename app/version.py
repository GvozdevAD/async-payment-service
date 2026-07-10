"""Application version utilities."""

import tomllib
from functools import lru_cache
from pathlib import Path


@lru_cache
def get_version() -> str:
    """Return the project version from pyproject.toml.

    Returns:
        Semantic version string, or 0.0.0 if pyproject.toml is missing.
    """
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if not pyproject_path.is_file():
        return "0.0.0"
    with pyproject_path.open("rb") as f:
        return tomllib.load(f)["project"]["version"]
