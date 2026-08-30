# Changelog

## 0.3.2

- Fixed repository discovery in the GitHub Actions release job.
- Made release uploads safe to repeat when an existing tag is rebuilt.
- Removed internal execution artifacts from the public documentation set.

## 0.3.1

- Fixed Windows release builds by creating and using the project virtual environment in CI.

## 0.3.0

- Added a generic JSON project profile shared by GUI and CLI.
- Added profile-backed CSV export, Dry-run, build, install, rollback, and PAK operations.
- Added a complete Tkinter workbench for translation, fonts, PAK inspection, and guarded installation.
- Added built-in `zh-CN` and `en-US` GUI resources with external locale overrides.
- Added bundled fontTools coverage and subset operations, with optional custom Python override.
- Added full-font and subset-font documentation and a console PyInstaller entry point.
- Added public contribution, security, release, and GUI operation guides.
