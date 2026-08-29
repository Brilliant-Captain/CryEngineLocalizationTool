"""JSON codec with the limited trailing-comma compatibility CryEngine needs."""

from __future__ import annotations

import json
from typing import Any


def _remove_trailing_commas(text: str) -> str:
    output: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "}]":
                index += 1
                continue
        output.append(char)
        index += 1
    return "".join(output)


def parse_json_relaxed(raw: bytes | str) -> Any:
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    return json.loads(_remove_trailing_commas(text))


def dump_json(data: Any) -> bytes:
    """Serialize patched localization data as UTF-8 JSON."""

    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

