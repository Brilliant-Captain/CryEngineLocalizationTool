from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

from cryengine_localization.adapters.pak_crypak import repack_crypak


ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PAK = Path(r"C:\Fixtures\ExampleGame\Localization\english_xml.pak")
PUBLIC_KEY = Path(r"C:\Fixtures\ExampleGame\cryengine-public.der")
SOURCE_ZIP = Path(r"C:\Fixtures\ExampleGame\english-original-decrypted.zip")
BACKEND = ROOT / "resources" / "bin" / "cry-pak-repack.dll"
DECRYPTOR = ROOT / "resources" / "bin" / "cry-pak-decrypt.exe"


@pytest.mark.skipif(
    not all(path.is_file() for path in (SAMPLE_PAK, PUBLIC_KEY, SOURCE_ZIP, BACKEND, DECRYPTOR)),
    reason="local CryPak fixtures unavailable",
)
def test_repack_crypak_roundtrip_preserves_members(tmp_path: Path) -> None:
    output = tmp_path / "roundtrip.pak"
    result = repack_crypak(SAMPLE_PAK, SOURCE_ZIP, output, public_key=PUBLIC_KEY, backend=BACKEND)
    assert result.output_pak == output.resolve()
    assert output.read_bytes()[:4] != b"PK\x03\x04"
    decoded = tmp_path / "decoded.zip"
    completed = subprocess.run([str(DECRYPTOR), "decrypt", str(output), str(PUBLIC_KEY), str(decoded)], check=False)
    assert completed.returncode == 0
    with zipfile.ZipFile(SOURCE_ZIP) as expected, zipfile.ZipFile(decoded) as actual:
        assert sorted(expected.namelist()) == sorted(actual.namelist())
        for name in expected.namelist():
            assert expected.read(name) == actual.read(name)


def test_repack_rejects_same_output_path(tmp_path: Path) -> None:
    source = tmp_path / "source.pak"
    source.write_bytes(b"x")
    with pytest.raises(ValueError, match="must differ"):
        repack_crypak(source, source, source, public_key=source, backend=source)
