"""CryEngine encrypted PAK decryption orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from cryengine_localization.adapters.pak import PakError, extract_pak, scan_pak


class PakDecryptError(RuntimeError):
    """A PAK could not be copied, decrypted or validated."""


RSA_PUBLIC_KEY_LENGTH = 140
_RSA_DER_PREFIX = bytes.fromhex("30 81 89 02 81 81 00")
_RSA_DER_SUFFIX = bytes.fromhex("02 03 01 00 01")


@dataclass(frozen=True)
class PublicKeyDiscovery:
    module_path: str
    offset: int
    key_path: str
    key_sha256: str


def discover_public_key(
    game_root: str | Path,
    *,
    output_key: str | Path | None = None,
) -> PublicKeyDiscovery:
    """Find a CryEngine RSA PKCS#1 public key embedded in game modules."""

    root = _absolute(game_root)
    if not root.is_dir():
        raise NotADirectoryError(root)
    candidates: list[tuple[Path, int, bytes]] = []
    modules = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.casefold() in {".dll", ".exe"}
        ),
        key=lambda path: path.absolute().as_posix().casefold(),
    )
    for module in modules:
        try:
            raw = module.read_bytes()
        except OSError:
            continue
        start = 0
        while True:
            offset = raw.find(_RSA_DER_PREFIX, start)
            if offset < 0:
                break
            end = offset + RSA_PUBLIC_KEY_LENGTH
            if end <= len(raw):
                candidate = raw[offset:end]
                if candidate.endswith(_RSA_DER_SUFFIX):
                    candidates.append((module, offset, candidate))
            start = offset + 1

    unique: dict[bytes, tuple[Path, int]] = {}
    for module, offset, candidate in candidates:
        unique.setdefault(candidate, (module, offset))
    if not unique:
        raise PakDecryptError("no embedded CryEngine RSA public key found")
    if len(unique) > 1:
        details = ", ".join(
            f"{module}:{offset}" for module, offset in unique.values()
        )
        raise PakDecryptError(f"multiple embedded RSA public keys found: {details}")

    key_bytes, (module, offset) = next(iter(unique.items()))
    if output_key is None:
        key_path = Path.cwd() / ".cryengine-public.der"
    else:
        key_path = _absolute(output_key)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key_bytes)
    return PublicKeyDiscovery(
        module_path=str(module),
        offset=offset,
        key_path=str(key_path),
        key_sha256=hashlib.sha256(key_bytes).hexdigest(),
    )


def resolve_decryptor(value: str | Path | None = None) -> Path:
    """Resolve an explicit, environment-provided, or bundled decryptor."""

    candidates: list[Path] = []
    if value:
        candidates.append(_absolute(value))
    configured = os.environ.get("CRYENGINE_PAK_DECRYPTOR")
    if configured:
        candidates.append(_absolute(configured))
    candidates.extend(
        (
            Path(sys.executable).resolve().parent / "resources" / "bin" / "cry-pak-decrypt.exe",
            Path(__file__).resolve().parents[3] / "resources" / "bin" / "cry-pak-decrypt.exe",
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "no CryEngine PAK decryptor found; pass --decryptor or set CRYENGINE_PAK_DECRYPTOR"
    )


def resolve_public_key(value: str | Path | None = None) -> Path | None:
    """Resolve an explicit or environment-provided key."""

    if value:
        candidate = _absolute(value)
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate
    configured = os.environ.get("CRYENGINE_PAK_PUBLIC_KEY")
    if configured:
        candidate = _absolute(configured)
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate
    return None


@dataclass(frozen=True)
class PakDecryptResult:
    input_path: str
    output_path: str
    mode: str
    status: str
    encrypted: bool
    entry_count: int = 0
    extracted_count: int = 0
    input_sha256: str = ""
    output_sha256: str = ""
    error: str = ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute(path: str | Path) -> Path:
    return Path(path).expanduser().absolute()


def _temporary_output(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".partial", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(name)
    temporary.unlink(missing_ok=True)
    return temporary


def _run_helper(
    decryptor: Path,
    source: Path,
    key: Path,
    temporary: Path,
    *,
    timeout: float,
) -> None:
    command = [str(decryptor), "decrypt", str(source), str(key), str(temporary)]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except OSError as exc:
        raise PakDecryptError(f"failed to start decryptor: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PakDecryptError(f"decryptor timed out after {timeout:g}s") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise PakDecryptError(f"decryptor exited with code {completed.returncode}{suffix}")
    if not temporary.is_file() or temporary.stat().st_size == 0:
        raise PakDecryptError("decryptor produced no output")


def decrypt_pak(
    input_pak: str | Path,
    output_pak: str | Path,
    *,
    decryptor: str | Path,
    public_key: str | Path,
    overwrite: bool = False,
    timeout: float = 300.0,
) -> PakDecryptResult:
    """Copy or decrypt one PAK and validate the resulting archive."""

    source = _absolute(input_pak)
    destination = _absolute(output_pak)
    helper = _absolute(decryptor)
    key = _absolute(public_key)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not helper.is_file():
        raise FileNotFoundError(helper)
    if not key.is_file():
        raise FileNotFoundError(key)
    if source == destination:
        raise ValueError("output path must differ from input path")
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)

    input_hash = _sha256(source)
    encrypted = False
    entry_count = 0
    try:
        archive = scan_pak(source)
    except (PakError, OSError, ValueError):
        encrypted = True
    else:
        entry_count = len(archive.entries)

    temporary = _temporary_output(destination)
    try:
        if encrypted:
            _run_helper(helper, source, key, temporary, timeout=timeout)
        else:
            shutil.copyfile(source, temporary)
        validated = scan_pak(temporary)
        entry_count = len(validated.entries)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return PakDecryptResult(
        input_path=str(source),
        output_path=str(destination),
        mode="pak",
        status="decrypted" if encrypted else "copied",
        encrypted=encrypted,
        entry_count=entry_count,
        input_sha256=input_hash,
        output_sha256=_sha256(destination),
    )


def decrypt_pak_tree(
    input_root: str | Path,
    output_root: str | Path,
    *,
    decryptor: str | Path,
    public_key: str | Path,
    mode: str = "pak",
    overwrite: bool = False,
    timeout: float = 300.0,
    report_path: str | Path | None = None,
) -> tuple[tuple[PakDecryptResult, ...], Path | None]:
    """Process every PAK below input_root while preserving relative paths."""

    if mode not in {"pak", "extract"}:
        raise ValueError("mode must be 'pak' or 'extract'")
    source_root = _absolute(input_root)
    destination_root = _absolute(output_root)
    if not source_root.is_dir():
        raise NotADirectoryError(source_root)
    destination_root.mkdir(parents=True, exist_ok=True)

    results: list[PakDecryptResult] = []
    pak_paths = sorted(
        source_root.rglob("*.pak"),
        key=lambda item: item.absolute().as_posix().casefold(),
    )
    for source in pak_paths:
        relative = source.absolute().relative_to(source_root.absolute())
        if mode == "pak":
            destination = destination_root / relative
            try:
                results.append(
                    decrypt_pak(
                        source,
                        destination,
                        decryptor=decryptor,
                        public_key=public_key,
                        overwrite=overwrite,
                        timeout=timeout,
                    )
                )
            except Exception as exc:
                results.append(
                    PakDecryptResult(
                        input_path=str(source),
                        output_path=str(destination),
                        mode="pak",
                        status="failed",
                        encrypted=False,
                        input_sha256=_sha256(source),
                        error=str(exc),
                    )
                )
            continue

        temporary = _temporary_output(destination_root / relative)
        temporary.unlink(missing_ok=True)
        extract_root = destination_root / relative.parent / relative.stem
        try:
            single = decrypt_pak(
                source,
                temporary,
                decryptor=decryptor,
                public_key=public_key,
                overwrite=True,
                timeout=timeout,
            )
            written = extract_pak(temporary, extract_root, overwrite=overwrite)
            results.append(
                PakDecryptResult(
                    input_path=single.input_path,
                    output_path=str(extract_root),
                    mode="extract",
                    status=single.status,
                    encrypted=single.encrypted,
                    entry_count=single.entry_count,
                    extracted_count=len(written),
                    input_sha256=single.input_sha256,
                    output_sha256=single.output_sha256,
                )
            )
        except Exception as exc:
            results.append(
                PakDecryptResult(
                    input_path=str(source),
                    output_path=str(extract_root),
                    mode="extract",
                    status="failed",
                    encrypted=False,
                    input_sha256=_sha256(source),
                    error=str(exc),
                )
            )
        finally:
            temporary.unlink(missing_ok=True)

    report = None
    if report_path is not None:
        report = _absolute(report_path)
        report.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "input_root": str(source_root),
            "output_root": str(destination_root),
            "mode": mode,
            "total": len(results),
            "succeeded": sum(item.status != "failed" for item in results),
            "failed": sum(item.status == "failed" for item in results),
            "results": [asdict(item) for item in results],
        }
        report.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return tuple(results), report
