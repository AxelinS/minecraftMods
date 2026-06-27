"""
scanner.py
----------
Recursively scans the ``pack/`` directory and builds a list of
:class:`FileEntry` objects.

Responsibilities:
  - Walk the directory tree respecting :class:`~utils.IgnoreFilter`.
  - Collect metadata: size, modification time, MIME-like type.
  - Delegate hash computation to :class:`~hashing.HashWorker`.
  - Report progress via the application logger.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from hashing import HashWorker
from logger import get_logger
from utils import IgnoreFilter

log = get_logger()

PACK_DIR_NAME = "pack"


@dataclass
class FileEntry:
    """Metadata record for a single file inside the ``pack/`` directory.

    All paths are stored relative to the ``pack/`` directory root so the
    manifest is portable across machines.
    """

    path: str          # e.g. "mods/create.jar"
    filename: str      # e.g. "create.jar"
    size: int          # bytes
    sha256: str        # lowercase hex digest
    modified: str      # UTC ISO-8601, e.g. "2026-06-25T18:00:20Z"
    type: str          # file extension without dot, lower-cased, e.g. "jar"
    url: str           # relative download URL, e.g. "pack/mods/create.jar"

    def to_dict(self) -> dict:
        """Serialise to a plain dictionary for JSON output."""
        return {
            "path": self.path,
            "filename": self.filename,
            "size": self.size,
            "sha256": self.sha256,
            "modified": self.modified,
            "type": self.type,
            "url": self.url,
        }


@dataclass
class ScanResult:
    """Aggregated output produced by :class:`Scanner`."""

    entries: List[FileEntry]
    total_files: int
    total_size: int       # bytes
    elapsed_seconds: float

    @property
    def pack_dir(self) -> Optional[str]:
        """Unused here; kept for future use."""
        return None


class Scanner:
    """Scans a modpack project and returns a :class:`ScanResult`.

    Parameters
    ----------
    project_root:
        Absolute path to the root of the modpack project (contains ``pack/``).
    max_workers:
        Thread-pool size for hash computation. ``None`` = auto.
    """

    def __init__(
        self,
        project_root: Path,
        max_workers: Optional[int] = None,
    ) -> None:
        self._root = project_root
        self._pack_dir = project_root / PACK_DIR_NAME
        self._max_workers = max_workers

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Raise :class:`ValueError` if pre-conditions for scanning are not met."""
        if not self._pack_dir.exists():
            raise ValueError(
                f"The 'pack' directory does not exist at: {self._pack_dir}"
            )
        if not self._pack_dir.is_dir():
            raise ValueError(
                f"'pack' path exists but is not a directory: {self._pack_dir}"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> ScanResult:
        """Run a full scan and return a :class:`ScanResult`.

        The method:
        1. Collects all file paths while applying the ignore filter.
        2. Reads stat metadata (size, mtime) for each file.
        3. Computes SHA-256 hashes in parallel.
        4. Assembles and sorts :class:`FileEntry` objects.

        Returns
        -------
        ScanResult
            Contains all file entries sorted alphabetically by path.
        """
        self.validate()

        start = time.perf_counter()
        ignore_filter = IgnoreFilter(self._root)

        log.info(f"Scanning pack directory: {self._pack_dir}")
        raw_paths = self._collect_paths(ignore_filter)
        log.info(f"Found {len(raw_paths)} files. Computing hashes…")

        worker = HashWorker(max_workers=self._max_workers)
        hashes = worker.compute_all(raw_paths)

        entries: List[FileEntry] = []
        total_size = 0

        for abs_path in raw_paths:
            if abs_path not in hashes:
                # Hashing failed for this file; skip it
                continue
            stat = abs_path.stat()
            rel = abs_path.relative_to(self._pack_dir)
            path_str = rel.as_posix()
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            entry = FileEntry(
                path=path_str,
                filename=abs_path.name,
                size=stat.st_size,
                sha256=hashes[abs_path],
                modified=modified,
                type=abs_path.suffix.lstrip(".").lower() or "unknown",
                url=f"pack/{path_str}",
            )
            entries.append(entry)
            total_size += stat.st_size

        # Stable alphabetical order by relative path
        entries.sort(key=lambda e: e.path.lower())

        elapsed = time.perf_counter() - start
        log.info(
            f"Scan complete: {len(entries)} files, "
            f"{total_size:,} bytes, {elapsed:.2f}s"
        )

        return ScanResult(
            entries=entries,
            total_files=len(entries),
            total_size=total_size,
            elapsed_seconds=elapsed,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_paths(self, ignore_filter: IgnoreFilter) -> List[Path]:
        """Walk the pack directory and return a list of non-ignored file paths."""
        collected: List[Path] = []
        for item in sorted(self._pack_dir.rglob("*")):
            if not item.is_file():
                continue
            if ignore_filter.is_ignored(item, self._pack_dir):
                log.debug(f"Ignored: {item.relative_to(self._pack_dir)}")
                continue
            collected.append(item)
        return collected
