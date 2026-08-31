# Changelog

## 0.6.1

- Changed batch dry-run output to a bounded summary with ready, empty, and failed counts plus at most 100 failure details.
- Added separate batch translation-only and font-only build commands and GUI actions, while retaining the combined build action.
- Added localized UI strings and external-locale fallback guidance for the new batch controls.

## 0.6.0

- Added full-game batch resource discovery with small active translation CSVs, report-only resource shards, and scan summaries.
- Added source-archive provenance, War of Rights English-overlay filtering, and safe reuse of prior human translations with backups and reports.
- Added profile, CLI, and GUI batch scan, preview, build, and translation-reuse workflows.
- Added batch GFX/CFX font discovery and one-font replacement overlays; files without embedded DefineFont3 slots are reported and skipped safely.
- Added compatibility for legacy localization JSON files with missing separators between adjacent object records.

## 0.4.0

- Added SpreadsheetML XML catalog extraction and translation-cell writeback.
- Added safe reads for legacy CryEngine PAKs whose local headers use backslashes.
- Added Scaleform `GFX` container font scanning alongside compressed `CFX` files.
- Added low-confidence discovery for localization-only CryEngine resource sets.
- Added best-effort engine version discovery from `.cryproject` and `CrySystem.dll` metadata.
- Moved `original_hash` to the final CSV column so source and translation text stay adjacent.

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
- Added legacy GFX safety assessment and tag-level DefineFont3 migration to avoid unsafe full-file FFDec rebuilds.
- Added full-font and subset-font documentation and a console PyInstaller entry point.
- Added public contribution, security, release, and GUI operation guides.
