"""
logger.py
---------
Thread-safe, in-process event log that the GUI can subscribe to.

Design:
  - LogDispatcher holds a list of listener callbacks.
  - Any module calls ``get_logger().info(...)`` / ``.warning(...)`` / ``.error(...)``.
  - The GUI registers a callback that appends lines to a scrolled text widget.
  - A global singleton is exposed via :func:`get_logger`.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, List


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LogRecord:
    """A single log entry."""

    __slots__ = ("level", "message", "timestamp")

    def __init__(self, level: LogLevel, message: str) -> None:
        self.level = level
        self.message = message
        self.timestamp: str = datetime.now(timezone.utc).strftime("%H:%M:%S")

    def __str__(self) -> str:  # noqa: D105
        return f"[{self.timestamp}] [{self.level.value}] {self.message}"


ListenerFn = Callable[[LogRecord], None]


class LogDispatcher:
    """Central hub that forwards :class:`LogRecord` objects to registered listeners.

    Thread-safe: listeners are invoked from whichever thread calls :pymeth:`log`.
    The GUI should schedule GUI updates via ``widget.after(0, ...)`` inside its
    listener to stay on the main thread.
    """

    def __init__(self) -> None:
        self._listeners: List[ListenerFn] = []
        self._lock = threading.Lock()

    def add_listener(self, fn: ListenerFn) -> None:
        """Register a new listener callback."""
        with self._lock:
            self._listeners.append(fn)

    def remove_listener(self, fn: ListenerFn) -> None:
        """Unregister a previously added listener."""
        with self._lock:
            try:
                self._listeners.remove(fn)
            except ValueError:
                pass

    def log(self, level: LogLevel, message: str) -> None:
        """Emit a log record to all registered listeners."""
        record = LogRecord(level, message)
        with self._lock:
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(record)
            except Exception:  # noqa: BLE001
                pass  # Never let a listener crash the application

    # Convenience wrappers -----------------------------------------------

    def debug(self, message: str) -> None:
        """Emit a DEBUG-level log record."""
        self.log(LogLevel.DEBUG, message)

    def info(self, message: str) -> None:
        """Emit an INFO-level log record."""
        self.log(LogLevel.INFO, message)

    def warning(self, message: str) -> None:
        """Emit a WARNING-level log record."""
        self.log(LogLevel.WARNING, message)

    def error(self, message: str) -> None:
        """Emit an ERROR-level log record."""
        self.log(LogLevel.ERROR, message)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_dispatcher = LogDispatcher()


def get_logger() -> LogDispatcher:
    """Return the application-wide :class:`LogDispatcher` singleton."""
    return _dispatcher
