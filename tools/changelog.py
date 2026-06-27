"""
changelog.py
------------
Generates and maintains ``CHANGELOG.md``.

Each call to :meth:`ChangelogManager.append_entry` prepends a new
version block at the top of the file, preserving older entries below.

Changelog block format::

    # Version X.Y.Z

    **Fecha:** 2026-06-26

    ## Added
    - pack/mods/newmod.jar

    ## Updated
    - pack/mods/create.jar

    ## Removed
    - pack/mods/oldmod.jar

    ## Notes
    <admin notes>

    ---
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from logger import get_logger
from manifest import ManifestDiff

log = get_logger()

CHANGELOG_FILENAME = "CHANGELOG.md"


class ChangelogEntry:
    """Represents a single version entry in the changelog.

    Parameters
    ----------
    version:
        Version string, e.g. ``"1.3.5"``.
    diff:
        The :class:`~manifest.ManifestDiff` for this version.
    notes:
        Optional free-text notes provided by the administrator.
    date:
        UTC date string (``YYYY-MM-DD``). Defaults to today.
    """

    def __init__(
        self,
        version: str,
        diff: ManifestDiff,
        notes: str = "",
        date: Optional[str] = None,
    ) -> None:
        self.version = version
        self.diff = diff
        self.notes = notes.strip()
        self.date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def render(self) -> str:
        """Return the Markdown block for this entry."""
        lines: List[str] = [
            f"# Version {self.version}",
            "",
            f"**Fecha:** {self.date}",
            "",
        ]

        if self.diff.added:
            lines.append("## Added")
            for e in self.diff.added:
                lines.append(f"- {e.path}")
            lines.append("")

        if self.diff.modified:
            lines.append("## Updated")
            for e in self.diff.modified:
                lines.append(f"- {e.path}")
            lines.append("")

        if self.diff.deleted:
            lines.append("## Removed")
            for e in self.diff.deleted:
                lines.append(f"- {e.path}")
            lines.append("")

        if self.diff.renamed:
            lines.append("## Renamed")
            for old, new in self.diff.renamed:
                lines.append(f"- {old} → {new}")
            lines.append("")

        if not self.diff.has_changes:
            lines.append("_No changes detected._")
            lines.append("")

        if self.notes:
            lines.append("## Notes")
            lines.append("")
            lines.append(self.notes)
            lines.append("")

        lines.append("---")
        lines.append("")

        return "\n".join(lines)


class ChangelogManager:
    """Manages ``CHANGELOG.md`` for the modpack project.

    Parameters
    ----------
    project_root:
        Directory that contains (or will contain) ``CHANGELOG.md``.
    """

    def __init__(self, project_root: Path) -> None:
        self._path = project_root / CHANGELOG_FILENAME

    @property
    def path(self) -> Path:
        """Absolute path to ``CHANGELOG.md``."""
        return self._path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append_entry(self, entry: ChangelogEntry) -> None:
        """Prepend *entry* at the top of ``CHANGELOG.md``.

        Creates the file if it does not exist yet.
        Preserves all previous content below the new entry.

        Parameters
        ----------
        entry:
            The changelog entry to prepend.
        """
        new_block = entry.render()

        if self._path.exists():
            previous = self._path.read_text(encoding="utf-8")
        else:
            previous = ""

        content = new_block + previous
        self._path.write_text(content, encoding="utf-8")
        log.info(f"CHANGELOG.md updated for version {entry.version}")

    def read(self) -> str:
        """Return the full text of ``CHANGELOG.md``, or an empty string."""
        if not self._path.exists():
            return ""
        return self._path.read_text(encoding="utf-8")

    def export(self, destination: Path) -> None:
        """Copy the changelog to *destination*.

        Parameters
        ----------
        destination:
            Target file path (will be created or overwritten).
        """
        content = self.read()
        destination.write_text(content, encoding="utf-8")
        log.info(f"CHANGELOG.md exported to: {destination}")

    def export_summary_txt(
        self,
        destination: Path,
        version: str,
        diff: ManifestDiff,
    ) -> None:
        """Write a plain-text change summary to *destination*.

        Parameters
        ----------
        destination:
            Target ``.txt`` file path.
        version:
            The new version string.
        diff:
            The manifest diff to summarise.
        """
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            f"Modpack Update Summary",
            f"======================",
            f"Nueva versión : {version}",
            f"Generado      : {date}",
            f"",
        ]
        lines.extend(diff.summary_lines())
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.info(f"Summary TXT exported to: {destination}")
