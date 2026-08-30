"""PyInstaller entry point for the console CLI executable."""

from __future__ import annotations

from cryengine_localization.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
