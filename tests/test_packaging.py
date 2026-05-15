"""
Packaging integrity tests for the carlijoy.compat collection.

Verifies that the installed package contains a valid galaxy.yml with a
Galaxy-compatible version that matches the Python package version.
These tests run without Docker and are always collected (no mark needed).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from packaging.version import Version

if TYPE_CHECKING:
    import pytest

import ansible_collections.carlijoy.compat._version as _col_ver


def _collection_dir() -> Path:
    """Return the installed collection root directory."""
    return Path(_col_ver.__file__).parent


class TestGalaxyYml:
    """galaxy.yml presence, structure, and version consistency."""

    def test_galaxy_yml(self, subtests: pytest.Subtests) -> None:
        """galaxy.yml exists, is valid YAML, has a strict semver version, and matches package."""
        collection_dir = _collection_dir()

        with subtests.test("file exists"):
            galaxy_file = collection_dir / "galaxy.yml"
            assert galaxy_file.is_file(), f"galaxy.yml not found at {galaxy_file}"

        with subtests.test("valid yaml"):
            data = yaml.safe_load((collection_dir / "galaxy.yml").read_text())
            assert isinstance(data, dict)

        with subtests.test("strict semver"):
            data = yaml.safe_load((collection_dir / "galaxy.yml").read_text())
            v = Version(data["version"])
            assert (
                v.pre is None and v.post is None and v.dev is None and v.local is None
            ), f"galaxy.yml version {data['version']!r} is not strict X.Y.Z semver"

        with subtests.test("matches package version"):
            data = yaml.safe_load((collection_dir / "galaxy.yml").read_text())
            galaxy = Version(data["version"])
            package = Version(_col_ver.__version__)
            assert (galaxy.major, galaxy.minor, galaxy.micro) == (
                package.major,
                package.minor,
                package.micro,
            ), f"galaxy.yml {data['version']!r} does not match package {_col_ver.__version__!r}"
