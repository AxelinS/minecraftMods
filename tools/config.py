"""
config.py
---------
Persistent application configuration backed by a JSON file.
Follows the Single-Responsibility Principle: only manages config I/O.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


CONFIG_PATH = Path(__file__).parent / "config.json"


@dataclass
class AppConfig:
    """All user-facing preferences that are persisted between sessions."""

    last_project_path: Optional[str] = None
    last_increment_type: str = "patch"          # patch | minor | major
    window_width: int = 1100
    window_height: int = 750
    theme: str = "dark"                          # dark | light | system

    # ---------------------------------------------------------------------------
    # Serialisation helpers
    # ---------------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Convert to a plain dictionary suitable for JSON serialisation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """Build an :class:`AppConfig` from a raw dictionary, ignoring unknown keys."""
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


class ConfigManager:
    """Loads and saves :class:`AppConfig` to/from ``config.json``.

    Usage::

        cm = ConfigManager()
        cm.config.last_project_path = "/some/path"
        cm.save()
    """

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self._path = path
        self.config: AppConfig = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist the current configuration to disk."""
        self._path.write_text(
            json.dumps(self.config.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def reload(self) -> None:
        """Re-read the configuration from disk, discarding any unsaved changes."""
        self.config = self._load()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> AppConfig:
        if not self._path.exists():
            return AppConfig()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return AppConfig.from_dict(raw)
        except (json.JSONDecodeError, TypeError):
            # Corrupted config — start fresh
            return AppConfig()
