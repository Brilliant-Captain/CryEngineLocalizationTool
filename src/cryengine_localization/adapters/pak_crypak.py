"""CryEngine encrypted PAK repacking through the bundled libcrypak backend."""

from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class CryPakRepackError(RuntimeError):
    """A CryPak could not be rebuilt."""


@dataclass(frozen=True)
class CryPakRepackResult:
    source_pak: Path
    source_zip: Path
    output_pak: Path
    backend: Path
    output_sha256: str
    output_size: int


def _absolute(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _default_backend() -> Path:
    candidates = []
    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        candidates.append(Path(bundle_root) / "resources" / "bin" / "cry-pak-repack.dll")
    candidates.extend(
        (
            Path(__file__).resolve().parents[3] / "resources" / "bin" / "cry-pak-repack.dll",
            Path.cwd() / "resources" / "bin" / "cry-pak-repack.dll",
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return _absolute(candidate)
    return _absolute(candidates[0])


def resolve_repack_backend(value: str | Path | None = None) -> Path:
    """Resolve an explicit or bundled CryPak repack DLL."""

    candidate = _absolute(value) if value else _default_backend()
    if not candidate.is_file():
        raise FileNotFoundError(
            f"CryPak repack backend not found: {candidate}; pass --backend or install resources/bin/cry-pak-repack.dll"
        )
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_backend(path: Path):
    try:
        library = ctypes.CDLL(str(path))
    except OSError as exc:
        raise CryPakRepackError(f"failed to load CryPak backend: {path}: {exc}") from exc
    function = library.pak_repack
    function.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_short,
    ]
    function.restype = ctypes.c_int
    return function


def repack_crypak(
    source_pak: str | Path,
    source_zip: str | Path,
    output_pak: str | Path,
    *,
    public_key: str | Path,
    backend: str | Path | None = None,
) -> CryPakRepackResult:
    """Rebuild an encrypted CryPak using the source pak's encryption header.

    ``source_zip`` must be a standard ZIP containing the complete desired
    member set. The native backend accepts narrow paths, so all inputs are
    staged under an ASCII temporary directory before it is called.
    """

    source = _absolute(source_pak)
    desired = _absolute(source_zip)
    output = _absolute(output_pak)
    key = _absolute(public_key)
    dll = resolve_repack_backend(backend)
    for path in (source, desired, key):
        if not path.is_file():
            raise FileNotFoundError(path)
    if source == output or desired == output or key == output:
        raise ValueError("source, zip, key and output paths must differ")
    output.parent.mkdir(parents=True, exist_ok=True)

    function = _load_backend(dll)
    with tempfile.TemporaryDirectory(prefix="cry_pak_repack_") as temporary_dir:
        temporary = Path(temporary_dir)
        staged_source = temporary / "source.pak"
        staged_zip = temporary / "desired.zip"
        staged_key = temporary / "public.der"
        staged_output = temporary / "output.pak"
        shutil.copyfile(source, staged_source)
        shutil.copyfile(desired, staged_zip)
        shutil.copyfile(key, staged_key)
        key_bytes = staged_key.read_bytes()
        key_buffer = (ctypes.c_ubyte * len(key_bytes)).from_buffer_copy(key_bytes)
        try:
            code = function(
                os.fsencode(staged_source),
                os.fsencode(staged_zip),
                os.fsencode(staged_output),
                key_buffer,
                len(key_bytes),
            )
        except OSError as exc:
            raise CryPakRepackError(f"CryPak backend call failed: {exc}") from exc
        if code != 0:
            raise CryPakRepackError(f"CryPak backend returned error code {code}")
        if not staged_output.is_file() or staged_output.stat().st_size < 22:
            raise CryPakRepackError("CryPak backend produced no output")
        raw_head = staged_output.read_bytes()[:4]
        if raw_head == b"PK\x03\x04":
            raise CryPakRepackError("backend produced a standard ZIP, not an encrypted CryPak")
        temporary_output = output.with_suffix(output.suffix + ".partial")
        shutil.copyfile(staged_output, temporary_output)
        os.replace(temporary_output, output)

    return CryPakRepackResult(
        source_pak=source,
        source_zip=desired,
        output_pak=output,
        backend=dll,
        output_sha256=_sha256(output),
        output_size=output.stat().st_size,
    )
