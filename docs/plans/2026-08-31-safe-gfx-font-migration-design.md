# Safe GFX Font Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent runtime crashes caused by FFDec-rebuilt legacy Scaleform GFX files and provide a conservative in-place `DefineFont3` migration path for files that need Chinese glyphs.

**Architecture:** Keep the existing FFDec replacement backend for ordinary GFX files, but add a safety assessment that classifies outputs as safe, caution, or blocked. Add a separate tag-level migration backend that compares an FFDec candidate with the original, replaces only the target `DefineFont3` tag, preserves unrelated SWF tags and container metadata, and refuses to write when the comparison is ambiguous.

**Tech Stack:** Python 3.12, standard library (`struct`, `zlib`, `dataclasses`, `pathlib`), existing FFDec CLI integration, bundled `fontTools` for optional subset generation, pytest fixtures, and the existing `cry-localize` CLI/GUI.

---

## Problem Evidence

The game accepts the translated XML package and several rebuilt GFX files, but crashes when rebuilt `death_screen.gfx` and `1.01/Menus_Startmenu.gfx` are installed. The crash log reports `Pure function call`, a null write access violation, and `GFxMeshCacheReset`. FFDec successfully parses both candidate files and their tag counts match the originals, so the failure is a runtime compatibility issue rather than a basic SWF parse failure.

The two failing files grew from 4,154 to 12,718 bytes and from 469,942 to 666,947 bytes after font replacement. The current tool validates only that FFDec can dump the resulting GFX; it does not prove that the target game's older GFx runtime can load the rebuilt font table and compressed payload. The project requirements already state that arbitrary Scaleform/GFX versions are not guaranteed to be safely rewritten by one external tool.

## Design Decisions

### Safety assessment

Add immutable report models for container kind, decompressed size, tag counts, DefineFont3 count, target slot metadata, and risk reasons. The assessment must be read-only and deterministic. It should flag small legacy files, unusual compression headers, large output growth, multiple font tags, and any candidate where non-font tags differ. Assessment must never silently downgrade a blocked file to a normal replacement.

`font replace` remains backward compatible for files classified safe. For caution and blocked files, the default behavior is to stop before writing and print actionable reasons. An explicit `--allow-risky-rebuild` option preserves the existing escape hatch for advanced users; GUI users receive the same warning and must explicitly opt in.

### Tag-level migration

Implement a minimal SWF tag reader that understands the standard short and long tag headers, identifies tag code 75 (`DefineFont3`), and preserves raw bytes for every non-target tag. For GFX, parse the uncompressed payload directly; for CFX, decompress bytes after the existing header and remember the original container metadata. Build an FFDec candidate in a temporary location, identify the corresponding target DefineFont3 tag by ordinal/slot, and substitute only that raw tag payload into the original tag stream. Recompute the SWF payload length and the tag header length as required, then restore the original GFX/CFX container form.

The migration backend must reject candidates when the number/order of tags differs, when more than the requested font tag changes, when the candidate cannot be mapped unambiguously, or when the resulting payload cannot be parsed again. It should write atomically to a caller-provided output path and never modify the source.

### CLI and GUI integration

Expose a safety report command and a migration mode separately from the existing FFDec replacement command. The CLI should support a dry-run report, explicit opt-in for risky rebuilds, and an output path distinct from the source. The GUI should show risk reasons, the selected backend, and whether the output passed non-font-byte preservation checks.

## Implementation Tasks

### Task 1: Add binary container and SWF tag primitives

**Files:**
- Create: `src/cryengine_localization/adapters/swf.py`
- Test: `tests/unit/test_swf.py`

Implement GFX/CFX decode/encode helpers, SWF header parsing, short/long tag iteration, tag code 75 detection, and deterministic reassembly. Use synthetic fixtures only; no commercial game files belong in the repository.

### Task 2: Add safety assessment models and checks

**Files:**
- Modify: `src/cryengine_localization/adapters/gfxfont.py`
- Test: `tests/unit/test_gfxfont.py`

Add `GfxSafetyReport`, `assess_gfx_safety`, and candidate comparison helpers. Cover safe, caution, blocked, output-growth, compression, and non-font-tag-difference cases.

### Task 3: Add in-place DefineFont3 migration

**Files:**
- Modify: `src/cryengine_localization/adapters/gfxfont.py`
- Test: `tests/unit/test_gfxfont.py`

Implement candidate generation through the existing FFDec command integration, tag-only transplantation, atomic output, and post-write validation. Keep the current `replace_font_slots` behavior unchanged for callers that do not request migration.

### Task 4: Expose CLI controls

**Files:**
- Modify: `src/cryengine_localization/cli/main.py`
- Test: `tests/unit/test_gfxfont.py`, `tests/integration/test_cli.py`

Add safety/migration subcommands or flags, clear exit codes, and machine-readable JSON output for CI and GUI consumers.

### Task 5: Integrate GUI warnings

**Files:**
- Modify: `src/cryengine_localization/gui.py`
- Modify: `src/cryengine_localization/locales/zh-CN.json`
- Modify: `src/cryengine_localization/locales/en-US.json`
- Test: `tests/unit/test_gui.py`, `tests/unit/test_gui_model.py`

Show risk classification, reasons, backend selection, and validation results. Require explicit opt-in before risky FFDec rebuilds.

### Task 6: Verify against local game files without committing them

Use the local release executable and FFDec only from a workstation. Generate candidates in a temporary/work directory for the two failing files, verify that unrelated tags are byte-identical, and install only after manual confirmation. Record the result in a local report outside Git.

## Error Handling

All binary parse failures must be typed and actionable. The tool must distinguish unsupported SWF structures, ambiguous tag mapping, invalid compression, FFDec failure, and post-reassembly validation failure. No final output is created on failure. Existing source files and rollback records remain untouched.

## Success Criteria

- Existing ordinary GFX replacement tests remain green.
- Risky legacy files are blocked by default with explicit reasons.
- Synthetic tag fixtures prove that only a selected DefineFont3 tag changes.
- The two problematic files can produce an in-place candidate, or the tool clearly reports why the structure is unsupported.
- No repository test or release artifact contains commercial game resources, user fonts, FFDec binaries, or user-specific absolute paths.
