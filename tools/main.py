"""
main.py
-------
Application entry point.

Usage::

    cd modpack/tools
    python main.py

Requirements::

    pip install customtkinter

Python 3.11+ is required.
"""

from __future__ import annotations

import sys

# Guard: Python version check
if sys.version_info < (3, 11):
    sys.exit("Modpack Manager requires Python 3.11 or newer.")

from config import ConfigManager
from gui import App


def main() -> None:
    """Bootstrap the application."""
    config_manager = ConfigManager()
    app = App(config_manager)
    app.mainloop()


if __name__ == "__main__":
    main()
