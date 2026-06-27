"""
utils.py
--------
Shared utilities: ignore-pattern matching, human-readable formatting,
and other cross-cutting helpers.

The ignore system supports two sources of patterns:
  1. A hard-coded default set of temporary/system files.
  2. An optional ``.manifestignore`` file in the project root with
     gitignore-style syntax (``#`` comments, ``*`` wildcards, directory
     patterns ending with ``/``).
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import List, Set


# ---------------------------------------------------------------------------
# Default patterns that are always ignored
# ---------------------------------------------------------------------------

DEFAULT_IGNORE_PATTERNS: List[str] = [
    # System / editor artefacts
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "ehthumbs.db",
    # Temp / backup files
    "*.tmp",
    "*.bak",
    "*.old",
    "*.log",
    "*.swp",
    "*~",
    # Python
    "__pycache__",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    # VCS / IDE
    ".git",
    ".gitignore",
    ".idea",
    ".vscode",
    # Build artefacts
    "*.class",
    "node_modules",
]


class IgnoreFilter:
    """Decides whether a given path should be excluded from the scan.

    Parameters
    ----------
    project_root:
        Root directory of the modpack project (contains ``.manifestignore``).
    extra_patterns:
        Additional fnmatch patterns to ignore beyond the defaults.
    """

    def __init__(
        self,
        project_root: Path,
        extra_patterns: List[str] | None = None,
    ) -> None:
        self._patterns: List[str] = list(DEFAULT_IGNORE_PATTERNS)
        if extra_patterns:
            self._patterns.extend(extra_patterns)
        self._load_manifestignore(project_root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_ignored(self, path: Path, relative_to: Path) -> bool:
        """Return ``True`` if *path* should be excluded.

        Parameters
        ----------
        path:
            Absolute path to the file or directory.
        relative_to:
            The base directory used to compute the relative path for matching.
        """
        rel = path.relative_to(relative_to)
        parts = rel.parts  # e.g. ("mods", "create.jar")

        for pattern in self._patterns:
            # Match against each path component individually …
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
            # … and against the full relative path string.
            if fnmatch.fnmatch(str(rel), pattern):
                return True
            # Directory pattern ending with "/"
            if pattern.endswith("/"):
                dir_pattern = pattern.rstrip("/")
                for part in parts[:-1]:  # only directory segments
                    if fnmatch.fnmatch(part, dir_pattern):
                        return True
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_manifestignore(self, root: Path) -> None:
        """Parse ``.manifestignore`` and append patterns to the list."""
        ignore_file = root / ".manifestignore"
        if not ignore_file.exists():
            return
        for raw_line in ignore_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#"):
                self._patterns.append(line)


# ---------------------------------------------------------------------------
# Human-readable formatting helpers
# ---------------------------------------------------------------------------

def format_size(size_bytes: int) -> str:
    """Return a human-readable file size string.

    Examples::

        >>> format_size(1024)
        '1.00 KB'
        >>> format_size(1_048_576)
        '1.00 MB'
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.2f} PB"


def format_duration(seconds: float) -> str:
    """Return a human-readable elapsed-time string (e.g. ``"2.34 s"``).

    Examples::

        >>> format_duration(0.005)
        '5.00 ms'
        >>> format_duration(65)
        '1m 5s'
    """
    if seconds < 1:
        return f"{seconds * 1000:.2f} ms"
    if seconds < 60:
        return f"{seconds:.2f} s"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs}s"
