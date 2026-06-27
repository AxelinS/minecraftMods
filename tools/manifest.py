"""
manifest.py
-----------
Generates ``manifest.json`` and computes the diff between the previous and
current manifests.

Responsibilities:
  - Build a new manifest document from a :class:`~scanner.ScanResult`.
  - Load and compare with the previous ``manifest.json``.
  - Detect added, modified, deleted, and renamed files.
  - Persist the new manifest to disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from logger import get_logger
from scanner import FileEntry, ScanResult

log = get_logger()

MANIFEST_FILENAME = "manifest.json"


# ---------------------------------------------------------------------------
# Diff data structures
# ---------------------------------------------------------------------------

@dataclass
class ManifestDiff:
    """The result of comparing two manifest snapshots.

    Attributes
    ----------
    added:
        Files present in the new manifest but absent in the old one.
    modified:
        Files whose ``sha256`` changed between the two manifests.
    deleted:
        Files present in the old manifest but absent in the new one.
    renamed:
        Pairs ``(old_path, new_path)`` where the SHA-256 is identical
        but the path changed (heuristic rename detection).
    unchanged:
        Files that are bitwise identical and at the same path.
    """

    added: List[FileEntry]
    modified: List[FileEntry]
    deleted: List[FileEntry]
    renamed: List[tuple[str, str]]     # (old_path, new_path)
    unchanged: List[FileEntry]

    @property
    def has_changes(self) -> bool:
        """Return ``True`` if any add/modify/delete/rename was detected."""
        return bool(self.added or self.modified or self.deleted or self.renamed)

    def summary_lines(self) -> List[str]:
        """Return a list of human-readable summary lines."""
        lines: List[str] = []
        if self.added:
            lines.append("Archivos nuevos:")
            for e in self.added:
                lines.append(f"  + {e.path}")
        if self.modified:
            lines.append("Archivos modificados:")
            for e in self.modified:
                lines.append(f"  * {e.path}")
        if self.deleted:
            lines.append("Archivos eliminados:")
            for e in self.deleted:
                lines.append(f"  - {e.path}")
        if self.renamed:
            lines.append("Archivos renombrados:")
            for old, new in self.renamed:
                lines.append(f"  ~ {old} → {new}")
        if not self.has_changes:
            lines.append("Sin cambios detectados.")
        return lines


# ---------------------------------------------------------------------------
# Manifest document
# ---------------------------------------------------------------------------

@dataclass
class ManifestDocument:
    """In-memory representation of a ``manifest.json`` file."""

    version: str
    generated_at: str
    files: List[FileEntry]

    def to_dict(self) -> dict:
        """Serialise to a plain dictionary for JSON output."""
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "files": [e.to_dict() for e in self.files],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ManifestDocument":
        """Deserialise a manifest loaded from JSON.

        Unknown keys in file entries are silently ignored.
        """
        files = [
            FileEntry(
                path=f["path"],
                filename=f["filename"],
                size=f["size"],
                sha256=f["sha256"],
                modified=f["modified"],
                type=f["type"],
                url=f["url"],
            )
            for f in data.get("files", [])
        ]
        return cls(
            version=data.get("version", "0.0.0"),
            generated_at=data.get("generated_at", ""),
            files=files,
        )


# ---------------------------------------------------------------------------
# Core manifest manager
# ---------------------------------------------------------------------------

class ManifestManager:
    """Creates, loads, diffs, and saves ``manifest.json``.

    Parameters
    ----------
    project_root:
        Directory that contains (or will contain) ``manifest.json``.
    """

    def __init__(self, project_root: Path) -> None:
        self._path = project_root / MANIFEST_FILENAME

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        """Absolute path to ``manifest.json``."""
        return self._path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_previous(self) -> Optional[ManifestDocument]:
        """Load the existing ``manifest.json``, or return ``None`` if absent/invalid."""
        if not self._path.exists():
            log.info("No previous manifest.json found. This will be treated as a fresh scan.")
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            doc = ManifestDocument.from_dict(data)
            log.info(f"Loaded previous manifest (version {doc.version}, {len(doc.files)} files)")
            return doc
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            log.warning(f"Could not parse previous manifest: {exc}. Treating as fresh scan.")
            return None

    def build(self, version: str, scan_result: ScanResult) -> ManifestDocument:
        """Create a new :class:`ManifestDocument` from a scan result.

        Parameters
        ----------
        version:
            The new version string (e.g. ``"1.3.5"``).
        scan_result:
            Output of :class:`~scanner.Scanner`.

        Returns
        -------
        ManifestDocument
            A new document whose files list is already sorted alphabetically.
        """
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return ManifestDocument(
            version=version,
            generated_at=generated_at,
            files=sorted(scan_result.entries, key=lambda e: e.path.lower()),
        )

    def diff(
        self,
        previous: Optional[ManifestDocument],
        current: ManifestDocument,
    ) -> ManifestDiff:
        """Compare *previous* and *current* manifests.

        Uses SHA-256 as the canonical identity of a file's contents.
        Rename detection: if a hash from the old manifest appears at a *different*
        path in the new manifest (and the old path is absent), it is classified
        as a rename rather than a delete + add pair.

        Parameters
        ----------
        previous:
            The old manifest, or ``None`` if no baseline exists.
        current:
            The newly built manifest.

        Returns
        -------
        ManifestDiff
        """
        if previous is None:
            # Every file is new
            return ManifestDiff(
                added=list(current.files),
                modified=[],
                deleted=[],
                renamed=[],
                unchanged=[],
            )

        old_by_path: Dict[str, FileEntry] = {e.path: e for e in previous.files}
        new_by_path: Dict[str, FileEntry] = {e.path: e for e in current.files}

        # Build reverse hash maps for rename detection
        old_hash_to_path: Dict[str, str] = {e.sha256: e.path for e in previous.files}
        new_hash_to_path: Dict[str, str] = {e.sha256: e.path for e in current.files}

        added: List[FileEntry] = []
        modified: List[FileEntry] = []
        deleted: List[FileEntry] = []
        renamed: List[tuple[str, str]] = []
        unchanged: List[FileEntry] = []

        # Detect added and modified
        for path, entry in new_by_path.items():
            if path not in old_by_path:
                # Check if this hash existed elsewhere (rename)
                if entry.sha256 in old_hash_to_path:
                    old_path = old_hash_to_path[entry.sha256]
                    if old_path not in new_by_path:
                        renamed.append((old_path, path))
                    else:
                        added.append(entry)
                else:
                    added.append(entry)
            else:
                old_entry = old_by_path[path]
                if old_entry.sha256 != entry.sha256:
                    modified.append(entry)
                else:
                    unchanged.append(entry)

        # Collect renamed old paths so we can exclude them from deleted
        renamed_old_paths = {r[0] for r in renamed}

        # Detect deleted
        for path, entry in old_by_path.items():
            if path not in new_by_path and path not in renamed_old_paths:
                deleted.append(entry)

        return ManifestDiff(
            added=added,
            modified=modified,
            deleted=deleted,
            renamed=renamed,
            unchanged=unchanged,
        )

    def save(self, document: ManifestDocument) -> None:
        """Serialise and write *document* to ``manifest.json``.

        Parameters
        ----------
        document:
            The manifest to persist.
        """
        self._path.write_text(
            json.dumps(document.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        log.info(
            f"manifest.json saved: version={document.version}, "
            f"files={len(document.files)}"
        )

    def export(self, destination: Path, document: ManifestDocument) -> None:
        """Write *document* to an arbitrary *destination* path (export copy).

        Parameters
        ----------
        destination:
            Target file path (will be created or overwritten).
        document:
            The manifest to export.
        """
        destination.write_text(
            json.dumps(document.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        log.info(f"manifest.json exported to: {destination}")
