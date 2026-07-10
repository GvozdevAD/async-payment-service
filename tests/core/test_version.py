"""Application version tests."""

from pathlib import Path
from unittest.mock import patch

from app.version import get_version


def test_get_version_reads_pyproject() -> None:
    """Version should match pyproject.toml project version."""
    get_version.cache_clear()

    version = get_version()

    assert version == "0.1.0"


def test_get_version_fallback_when_pyproject_missing() -> None:
    """Missing pyproject.toml should return a safe fallback version."""
    get_version.cache_clear()

    with patch.object(Path, "is_file", return_value=False):
        version = get_version()

    assert version == "0.0.0"
