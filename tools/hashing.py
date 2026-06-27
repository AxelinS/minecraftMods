"""
hashing.py
----------
SHA-256 computation for individual files and batches.

Key design decisions:
  - Streaming reads (8 KB chunks) to avoid loading large JARs into memory.
  - :class:`HashWorker` uses ``ThreadPoolExecutor`` for parallel batch hashing.
  - The public interface returns results as a ``dict[Path, str]`` for easy lookup.
"""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from logger import get_logger

CHUNK_SIZE = 8 * 1024  # 8 KB

log = get_logger()


def compute_sha256(path: Path) -> str:
    """Compute the SHA-256 digest of a file using streaming reads.

    Parameters
    ----------
    path:
        Absolute path to the file.

    Returns
    -------
    str
        Lowercase hex digest string (64 characters).

    Raises
    ------
    OSError
        If the file cannot be read.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


class HashWorker:
    """Computes SHA-256 hashes for a list of files in parallel.

    Parameters
    ----------
    max_workers:
        Number of threads. ``None`` lets :class:`ThreadPoolExecutor` choose.
    """

    def __init__(self, max_workers: Optional[int] = None) -> None:
        self._max_workers = max_workers

    def compute_all(self, paths: List[Path]) -> Dict[Path, str]:
        """Hash every file in *paths* and return a mapping ``{path: hex_digest}``.

        Failed files are logged and excluded from the result.

        Parameters
        ----------
        paths:
            List of absolute file paths to hash.

        Returns
        -------
        Dict[Path, str]
            Mapping from file path to its SHA-256 hex digest.
        """
        results: Dict[Path, str] = {}
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            future_to_path = {
                executor.submit(compute_sha256, p): p for p in paths
            }
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    results[path] = future.result()
                except Exception as exc:  # noqa: BLE001
                    log.error(f"Failed to hash {path.name}: {exc}")
        return results
