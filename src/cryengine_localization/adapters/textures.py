"""DDS metadata validation and PAK replacement helpers."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


class TextureFormatError(ValueError):
    """Input is not a supported DDS file."""


class TextureValidationError(ValueError):
    """Replacement metadata is incompatible with the source texture."""


class TextureToolError(RuntimeError):
    """An optional image tool or image decoder failed."""


@dataclass(frozen=True)
class DdsMetadata:
    width: int
    height: int
    mip_count: int
    fourcc: str
    has_alpha: bool
    rgb_bit_count: int
    pitch_or_linear: int


@dataclass(frozen=True)
class RgbaImage:
    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("image dimensions must be positive")
        if len(self.pixels) != self.width * self.height * 4:
            raise ValueError("RGBA pixel buffer has an invalid length")


def parse_dds_header(raw: bytes) -> DdsMetadata:
    if len(raw) < 128 or raw[:4] != b"DDS ":
        raise TextureFormatError("missing DDS magic or header")
    values = struct.unpack_from("<31I", raw, 4)
    if values[0] != 124:
        raise TextureFormatError("invalid DDS header size")
    height, width, pitch, mip_count = values[2], values[3], values[4], values[6] or 1
    pixel_format_size, pixel_flags, fourcc_value, rgb_bits, _r, _g, _b, alpha_mask = values[18:26]
    if pixel_format_size != 32:
        raise TextureFormatError("invalid DDS pixel format size")
    fourcc = fourcc_value.to_bytes(4, "little").decode("latin1")
    has_alpha = alpha_mask != 0 or fourcc in {"DXT3", "DXT5", "BC2 ", "BC3 "}
    return DdsMetadata(width, height, mip_count, fourcc, has_alpha, rgb_bits, pitch)


def _paeth(a: int, b: int, c: int) -> int:
    estimate = a + b - c
    pa, pb, pc = abs(estimate - a), abs(estimate - b), abs(estimate - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _read_png(raw: bytes) -> RgbaImage:
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise TextureFormatError("not a PNG file")
    offset = 8
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    while offset + 12 <= len(raw):
        length = struct.unpack_from(">I", raw, offset)[0]
        kind = raw[offset + 4 : offset + 8]
        payload_start = offset + 8
        payload_end = payload_start + length
        if payload_end + 4 > len(raw):
            raise TextureFormatError("truncated PNG chunk")
        payload = raw[payload_start:payload_end]
        if kind == b"IHDR":
            if len(payload) != 13:
                raise TextureFormatError("invalid PNG IHDR")
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
        offset = payload_end + 4
    if not width or not height or bit_depth != 8 or interlace != 0:
        raise TextureFormatError("only non-interlaced 8-bit PNG is supported")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise TextureFormatError(f"unsupported PNG color type: {color_type}")
    stride = width * channels
    try:
        decoded = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise TextureFormatError("invalid PNG image data") from exc
    if len(decoded) != height * (stride + 1):
        raise TextureFormatError("PNG scanline length mismatch")
    rows: list[bytes] = []
    previous = bytes(stride)
    cursor = 0
    for _ in range(height):
        filter_type = decoded[cursor]
        encoded = decoded[cursor + 1 : cursor + 1 + stride]
        cursor += stride + 1
        row = bytearray(stride)
        for index, value in enumerate(encoded):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                reconstructed = value
            elif filter_type == 1:
                reconstructed = (value + left) & 0xFF
            elif filter_type == 2:
                reconstructed = (value + up) & 0xFF
            elif filter_type == 3:
                reconstructed = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                reconstructed = (value + _paeth(left, up, up_left)) & 0xFF
            else:
                raise TextureFormatError(f"unsupported PNG filter: {filter_type}")
            row[index] = reconstructed
        rows.append(bytes(row))
        previous = bytes(row)
    rgba = bytearray()
    for row in rows:
        if color_type == 6:
            rgba.extend(row)
        elif color_type == 2:
            for index in range(0, len(row), 3):
                rgba.extend((*row[index : index + 3], 255))
        elif color_type == 0:
            for value in row:
                rgba.extend((value, value, value, 255))
        else:  # grayscale + alpha
            for index in range(0, len(row), 2):
                value, alpha = row[index : index + 2]
                rgba.extend((value, value, value, alpha))
    return RgbaImage(width, height, bytes(rgba))


def _read_ppm(raw: bytes) -> RgbaImage:
    if not raw.startswith((b"P6", b"P3", b"P5", b"P2")):
        raise TextureFormatError("not a supported PPM/PGM file")
    cursor = 0

    def token() -> bytes:
        nonlocal cursor
        while cursor < len(raw) and raw[cursor] in b" \t\r\n":
            cursor += 1
        if cursor < len(raw) and raw[cursor] == ord("#"):
            while cursor < len(raw) and raw[cursor] not in b"\r\n":
                cursor += 1
            return token()
        start = cursor
        while cursor < len(raw) and raw[cursor] not in b" \t\r\n#":
            cursor += 1
        if start == cursor:
            raise TextureFormatError("invalid PPM header")
        return raw[start:cursor]

    magic = token()
    try:
        width, height, maximum = int(token()), int(token()), int(token())
    except (ValueError, TextureFormatError) as exc:
        raise TextureFormatError("invalid PPM dimensions") from exc
    if maximum != 255 or width <= 0 or height <= 0:
        raise TextureFormatError("only 8-bit PPM/PGM is supported")
    channels = 3 if magic in (b"P6", b"P3") else 1
    if magic in (b"P6", b"P5"):
        if raw[cursor : cursor + 2] == b"\r\n":
            cursor += 2
        elif cursor < len(raw) and raw[cursor] in b" \t\r\n":
            cursor += 1
        values = raw[cursor : cursor + width * height * channels]
        if len(values) != width * height * channels:
            raise TextureFormatError("truncated PPM pixels")
    else:
        values = bytes(int(token()) for _ in range(width * height * channels))
    rgba = bytearray()
    if channels == 3:
        for index in range(0, len(values), 3):
            rgba.extend((*values[index : index + 3], 255))
    else:
        for value in values:
            rgba.extend((value, value, value, 255))
    return RgbaImage(width, height, bytes(rgba))


def read_image_rgba(path: str | Path) -> RgbaImage:
    """Read PNG/PPM with the standard library, or use Pillow for other formats."""

    image_path = Path(path).expanduser().resolve()
    raw = image_path.read_bytes()
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return _read_png(raw)
    if raw.startswith((b"P6", b"P3", b"P5", b"P2")):
        return _read_ppm(raw)
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            converted = image.convert("RGBA")
            return RgbaImage(converted.width, converted.height, converted.tobytes())
    except (ImportError, OSError, ValueError) as exc:
        raise TextureToolError(
            "unsupported image format; use PNG/PPM or install Pillow for additional formats"
        ) from exc


def _downsample(image: RgbaImage) -> RgbaImage:
    width, height = max(1, image.width // 2), max(1, image.height // 2)
    output = bytearray()
    for y in range(height):
        for x in range(width):
            samples = []
            for dy in (0, 1):
                for dx in (0, 1):
                    sx, sy = min(image.width - 1, x * 2 + dx), min(image.height - 1, y * 2 + dy)
                    start = (sy * image.width + sx) * 4
                    samples.append(image.pixels[start : start + 4])
            output.extend(sum(channel) // len(samples) for channel in zip(*samples))
    return RgbaImage(width, height, bytes(output))


def _block_pixels(image: RgbaImage, left: int, top: int) -> list[tuple[int, int, int, int]]:
    pixels = []
    for y in range(4):
        for x in range(4):
            sx, sy = min(image.width - 1, left + x), min(image.height - 1, top + y)
            start = (sy * image.width + sx) * 4
            pixels.append(tuple(image.pixels[start : start + 4]))
    return pixels


def _rgb565(red: int, green: int, blue: int) -> int:
    return ((red * 31 + 127) // 255 << 11) | ((green * 63 + 127) // 255 << 5) | ((blue * 31 + 127) // 255)


def _expand565(value: int) -> tuple[int, int, int]:
    return (
        ((value >> 11) & 31) * 255 // 31,
        ((value >> 5) & 63) * 255 // 63,
        (value & 31) * 255 // 31,
    )


def _encode_color_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    darkest = min(pixels, key=lambda p: p[0] * 299 + p[1] * 587 + p[2] * 114)
    brightest = max(pixels, key=lambda p: p[0] * 299 + p[1] * 587 + p[2] * 114)
    c0, c1 = _rgb565(*brightest[:3]), _rgb565(*darkest[:3])
    if c0 <= c1:
        high, low = max(c0, c1), min(c0, c1)
        c0, c1 = (high + 1, low) if high < 0xFFFF else (high, max(0, low - 1))
    rgb0, rgb1 = _expand565(c0), _expand565(c1)
    palette = [
        rgb0,
        rgb1,
        tuple((2 * rgb0[i] + rgb1[i]) // 3 for i in range(3)),
        tuple((rgb0[i] + 2 * rgb1[i]) // 3 for i in range(3)),
    ]
    indices = 0
    for index, pixel in enumerate(pixels):
        choice = min(range(4), key=lambda i: sum((pixel[channel] - palette[i][channel]) ** 2 for channel in range(3)))
        indices |= choice << (index * 2)
    return struct.pack("<HHI", c0, c1, indices)


def _encode_alpha_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    alpha0, alpha1 = max(pixel[3] for pixel in pixels), min(pixel[3] for pixel in pixels)
    if alpha0 == alpha1:
        palette = [alpha0, alpha1] + [alpha0] * 6
    else:
        palette = [alpha0, alpha1] + [((7 - index) * alpha0 + index * alpha1) // 7 for index in range(1, 7)]
    indices = 0
    for index, pixel in enumerate(pixels):
        choice = min(range(8), key=lambda i: abs(pixel[3] - palette[i]))
        indices |= choice << (index * 3)
    return bytes((alpha0, alpha1)) + indices.to_bytes(6, "little")


def _encode_level(image: RgbaImage) -> bytes:
    output = bytearray()
    for top in range(0, image.height, 4):
        for left in range(0, image.width, 4):
            pixels = _block_pixels(image, left, top)
            output.extend(_encode_alpha_block(pixels))
            output.extend(_encode_color_block(pixels))
    return bytes(output)


def encode_rgba_to_dds(
    width: int,
    height: int,
    rgba: bytes,
    *,
    mipmaps: bool = True,
    fourcc: str = "DXT5",
) -> bytes:
    """Encode RGBA pixels as deterministic DXT5/BC3 DDS data."""

    image = RgbaImage(width, height, bytes(rgba))
    if fourcc != "DXT5":
        raise TextureFormatError("pure Python encoder currently supports DXT5 only")
    levels = [image]
    if mipmaps:
        while levels[-1].width > 1 or levels[-1].height > 1:
            levels.append(_downsample(levels[-1]))
    encoded_levels = [_encode_level(level) for level in levels]
    header = [0] * 31
    header[0] = 124
    header[1] = 0x81007
    header[2], header[3] = height, width
    header[4] = len(encoded_levels[0])
    header[6] = len(levels)
    header[18], header[19], header[20] = 32, 4, int.from_bytes(b"DXT5", "little")
    header[26] = 0x1000 | (0x8 | 0x400000 if len(levels) > 1 else 0)
    return b"DDS " + struct.pack("<31I", *header) + b"".join(encoded_levels)


def encode_image_file_to_dds(
    image_path: str | Path,
    output_path: str | Path,
    *,
    mipmaps: bool = True,
) -> Path:
    image = read_image_rgba(image_path)
    encoded = encode_rgba_to_dds(image.width, image.height, image.pixels, mipmaps=mipmaps)
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded)
    return destination


def validate_texture_replacement(
    original: bytes, replacement: bytes, *, require_alpha: bool = False
) -> DdsMetadata:
    source = parse_dds_header(original)
    candidate = parse_dds_header(replacement)
    errors: list[str] = []
    if (candidate.width, candidate.height) != (source.width, source.height):
        errors.append("dimension mismatch")
    if candidate.mip_count != source.mip_count:
        errors.append("mip count mismatch")
    if candidate.fourcc != source.fourcc:
        errors.append("compression format mismatch")
    if require_alpha and not candidate.has_alpha:
        errors.append("alpha channel required")
    if errors:
        raise TextureValidationError("; ".join(errors))
    return candidate


def replace_texture_in_pak(
    source_pak: str | Path,
    entry_path: str,
    replacement: bytes | str | Path,
    output_pak: str | Path,
    *,
    require_alpha: bool = False,
) -> Path:
    from zipfile import ZipFile

    from cryengine_localization.adapters.pak import build_pak, normalize_entry_path, scan_pak

    archive = scan_pak(source_pak)
    normalized_requested = normalize_entry_path(entry_path)
    normalized = next((entry.path for entry in archive.entries if entry.path == normalized_requested), None)
    if normalized is None:
        raise KeyError(entry_path)
    replacement_bytes = Path(replacement).read_bytes() if isinstance(replacement, (str, Path)) else bytes(replacement)
    with ZipFile(archive.path, "r") as source:
        payload = {entry.path: source.read(entry.source_name) for entry in archive.entries}
    validate_texture_replacement(payload[normalized], replacement_bytes, require_alpha=require_alpha)
    payload[normalized] = replacement_bytes
    return build_pak(payload, output_pak)
