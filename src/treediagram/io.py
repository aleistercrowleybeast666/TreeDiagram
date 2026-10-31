"""Bounded declarative JSON and atomic output, shared by CLI and GUI."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

MAX_BYTES = 32 * 1024 * 1024


def Json_Digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _Pairs_Read(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def Json_Decode(raw: bytes):
    if len(raw) > MAX_BYTES:
        raise ValueError("file exceeds 32 MiB")
    # Check nesting before invoking the recursive JSON decoder, ignoring string contents.
    depth, quoted, escaped = 0, False, False
    for char in raw.decode("utf-8-sig"):
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 32:
                raise ValueError("JSON nesting exceeds 32")
        elif char in "]}":
            depth -= 1
    def invalid(value):
        raise ValueError(f"non-finite JSON number: {value}")
    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_Pairs_Read,
                       parse_constant=invalid)
    pending = [value]
    count = 0
    while pending:
        item = pending.pop()
        count += 1
        if count > 4000000:
            raise ValueError("JSON node limit exceeded")
        if isinstance(item, dict):
            if len(item) > 4096:
                raise ValueError("JSON object member limit exceeded")
            pending.extend(item.values())
        elif isinstance(item, list):
            if len(item) > 600001:
                raise ValueError("JSON array limit exceeded")
            pending.extend(item)
        elif type(item) is float and not math.isfinite(item):
            raise ValueError("JSON contains nonfinite/overflow number")
    return value


def Json_Read(path: Path):
    with path.open("rb") as stream:
        return Json_Decode(stream.read(MAX_BYTES + 1))


def Json_Write(path: Path, value) -> None:
    raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()
    Json_Decode(raw)
    if path.is_symlink():
        raise ValueError("refusing to replace symlink")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
