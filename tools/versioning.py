"""
versioning.py
-------------
Manages the ``version.json`` file and provides semantic-version increments.

version.json schema::

    {"version": "1.3.4"}

Increment types:
  - **patch**: 1.3.4 → 1.3.5
  - **minor**: 1.3.4 → 1.4.0
  - **major**: 1.3.4 → 2.0.0
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Tuple

from logger import get_logger

log = get_logger()

VERSION_FILENAME = "version.json"
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class VersionError(Exception):
    """Raised when ``version.json`` is missing or contains an invalid value."""


class VersionManager:
    """Reads, validates, increments, and writes ``version.json``.

    Parameters
    ----------
    project_root:
        Directory that contains (or will contain) ``version.json``.
    """

    def __init__(self, project_root: Path) -> None:
        self._path = project_root / VERSION_FILENAME

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        """Absolute path to ``version.json``."""
        return self._path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self) -> str:
        """Read and return the current version string (e.g. ``"1.3.4"``).

        Raises
        ------
        VersionError
            If the file does not exist or the version string is invalid.
        """
        if not self._path.exists():
            raise VersionError(
                f"version.json not found at {self._path}. "
                "Create it with content: {\"version\": \"1.0.0\"}"
            )
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise VersionError(f"version.json is not valid JSON: {exc}") from exc

        version = data.get("version")
        if not isinstance(version, str) or not _VERSION_RE.match(version):
            raise VersionError(
                f"version.json must contain a MAJOR.MINOR.PATCH string, got: {version!r}"
            )
        return version

    def write(self, version: str) -> None:
        """Validate and persist *version* to ``version.json``.

        Parameters
        ----------
        version:
            A ``MAJOR.MINOR.PATCH`` string to write.

        Raises
        ------
        VersionError
            If the version string format is invalid.
        """
        if not _VERSION_RE.match(version):
            raise VersionError(
                f"Invalid version format: {version!r}. Expected MAJOR.MINOR.PATCH"
            )
        self._path.write_text(
            json.dumps({"version": version}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        log.info(f"version.json updated → {version}")

    def increment(self, increment_type: str) -> Tuple[str, str]:
        """Compute and persist the next version.

        Parameters
        ----------
        increment_type:
            One of ``"patch"``, ``"minor"``, or ``"major"`` (case-insensitive).

        Returns
        -------
        Tuple[str, str]
            ``(old_version, new_version)`` strings.

        Raises
        ------
        VersionError
            If the current version cannot be read or the type is unknown.
        ValueError
            If *increment_type* is not a recognised increment keyword.
        """
        old = self.read()
        new = _bump(old, increment_type.lower())
        self.write(new)
        log.info(f"Version bumped ({increment_type}): {old} → {new}")
        return old, new


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse(version: str) -> Tuple[int, int, int]:
    major, minor, patch = map(int, version.split("."))
    return major, minor, patch


def _bump(version: str, increment_type: str) -> str:
    """Return the bumped version string without writing to disk."""
    major, minor, patch = _parse(version)
    if increment_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if increment_type == "minor":
        return f"{major}.{minor + 1}.0"
    if increment_type == "major":
        return f"{major + 1}.0.0"
    raise ValueError(
        f"Unknown increment type: {increment_type!r}. "
        "Expected 'patch', 'minor', or 'major'."
    )
