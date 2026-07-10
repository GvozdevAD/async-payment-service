"""Application version tests."""

import tomllib
from pathlib import Path
from unittest.mock import patch

from app.version import get_version

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _expected_version() -> str:
    """Return the project version declared in pyproject.toml."""
    with _PYPROJECT.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_get_version_reads_pyproject() -> None:
    """Version should match pyproject.toml project version."""
    get_version.cache_clear()

    version = get_version()

    assert version == _expected_version()


def test_get_version_fallback_when_pyproject_missing() -> None:
    """Missing pyproject.toml should return a safe fallback version."""
    get_version.cache_clear()

    with patch.object(Path, "is_file", return_value=False):
        version = get_version()

    assert version == "0.0.0"
