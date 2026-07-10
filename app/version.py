"""Application version utilities."""

import tomllib
from functools import lru_cache
from pathlib import Path


@lru_cache
def get_version() -> str:
    """Return the project version from pyproject.toml."""
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        return tomllib.load(f)["project"]["version"]
