"""Encoding/format detection and streaming readers/writers.

Text is processed in blocks that end at line breaks, so files of any size are
handled with bounded memory. Line endings and the original encoding (including a
byte order mark) are preserved. JSON is processed token-wise: only the contents of
string tokens are changed; whitespace, numbers and structure stay byte-identical.
"""
from __future__ import annotations

import codecs
import io
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

BLOCK_CHARS = 1 << 20
MAX_CARRY_CHARS = 8 * BLOCK_CHARS
SAMPLE_BYTES = 1 << 20

JSON_EXTENSIONS = {".json", ".jsonl", ".ndjson", ".geojson"}

_BOMS = [
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
]


class FormatError(Exception):
    """The file cannot be processed in the selected format/encoding."""


@dataclass(frozen=True)
class FileEncoding:
    codec: str
    bom: bytes = b""

    @property
    def label(self) -> str:
        return self.codec + ("+BOM" if self.bom else "")


def detect_encoding(path: Path) -> FileEncoding:
    with open(path, "rb") as fh:
        sample = fh.read(SAMPLE_BYTES)
    for bom, codec in _BOMS:
        if sample.startswith(bom):
            return FileEncoding(codec, bom)
    if b"\x00" in sample:
        even = sample[0::2].count(0)
        odd = sample[1::2].count(0)
        half = max(len(sample) // 2, 1)
        if odd > half * 0.3 and even < half * 0.05:
            return FileEncoding("utf-16-le")
        if even > half * 0.3 and odd < half * 0.05:
            return FileEncoding("utf-16-be")
        raise FormatError("Datei enthält Nullbytes und ist vermutlich binär.")
    try:
        codecs.getincrementaldecoder("utf-8")().decode(sample, final=len(sample) < SAMPLE_BYTES)
        return FileEncoding("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        sample.decode("cp1252")
        return FileEncoding("cp1252")
    except UnicodeDecodeError:
        return FileEncoding("latin-1")


def parse_encoding(name: str) -> FileEncoding:
    """Explicit user choice, e.g. 'utf-8', 'cp1252', 'utf-16-le+BOM'."""
    codec, _, suffix = name.partition("+")
    codecs.lookup(codec)
    bom = b""
    if suffix.upper() == "BOM":
        bom = {"utf-8": codecs.BOM_UTF8, "utf-16-le": codecs.BOM_UTF16_LE,
               "utf-16-be": codecs.BOM_UTF16_BE}.get(codec.lower(), b"")
    return FileEncoding(codec, bom)


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0e-\x1a\x1c-\x1f\x7f]")


def detect_format(path: Path, encoding: FileEncoding) -> str:
    """Return 'jsonl', 'json' or 'text'; raise FormatError for binary content."""
    with open_text(path, encoding) as fh:
        sample = fh.read(64 * 1024)
    if sample and len(_CONTROL.findall(sample)) > len(sample) * 0.01:
        raise FormatError("Datei enthält viele Steuerzeichen und ist vermutlich binär.")
    stripped = sample.lstrip()
    first_line = stripped.split("\n", 1)[0].strip()
    if first_line.startswith("{") and first_line.endswith("}"):
        try:
            json.loads(first_line)
            return "jsonl"
        except ValueError:
            pass
    if Path(path).suffix.lower() in JSON_EXTENSIONS and stripped[:1] in ("{", "["):
        return "json"
    return "text"


def open_text(path: Path, encoding: FileEncoding) -> io.TextIOWrapper:
    raw = open(path, "rb")  # noqa: SIM115 - owned by the returned wrapper
    if encoding.bom and raw.read(len(encoding.bom)) != encoding.bom:
        raw.seek(0)
    return io.TextIOWrapper(raw, encoding=encoding.codec, errors="strict", newline="")


def create_text(path: Path, encoding: FileEncoding) -> io.TextIOWrapper:
    raw = open(path, "xb")  # noqa: SIM115 - owned by the returned wrapper
    raw.write(encoding.bom)
    return io.TextIOWrapper(raw, encoding=encoding.codec, errors="strict", newline="")


def iter_blocks(stream: io.TextIOBase, block_chars: int = BLOCK_CHARS) -> Iterator[str]:
    """Yield blocks ending at a line break; overlong lines are split at whitespace."""
    carry = ""
    while True:
        try:
            chunk = stream.read(block_chars)
        except UnicodeDecodeError as exc:
            raise FormatError(f"Zeichenkodierung passt nicht: {exc.reason}.") from exc
        if not chunk:
            if carry:
                yield carry
            return
        data = carry + chunk
        cut = data.rfind("\n") + 1
        if cut == 0:
            cut = max(data.rfind(" "), data.rfind("\t")) + 1
            if cut == 0:
                if len(data) < MAX_CARRY_CHARS:
                    carry = data
                    continue
                cut = len(data)
        yield data[:cut]
        carry = data[cut:]


# --- JSON ---------------------------------------------------------------------

# callback(decoded_string, is_key, is_secret_value) -> replacement or None (unchanged)
StringCallback = Callable[[str, bool, bool], "str | None"]

_STRUCTURE = re.compile(r"[{}\[\],:]")


class JsonStringRewriter:
    """Streams JSON (single document or JSON Lines) and rewrites string tokens."""

    def __init__(self, callback: StringCallback, secret_keys: re.Pattern[str]):
        self.callback = callback
        self.secret_keys = secret_keys
        self._stack: list[str] = []
        self._expect_key = False
        self._last_key: str | None = None
        self._in_string = False
        self._parts: list[str] = []

    def feed(self, chunk: str) -> str:
        out: list[str] = []
        i = 0
        n = len(chunk)
        while i < n:
            if not self._in_string:
                j = chunk.find('"', i)
                segment = chunk[i:] if j == -1 else chunk[i:j]
                self._track_structure(segment)
                out.append(segment)
                if j == -1:
                    break
                self._in_string = True
                self._parts = []
                i = j + 1
            else:
                j = chunk.find('"', i)
                if j == -1:
                    self._parts.append(chunk[i:])
                    break
                self._parts.append(chunk[i:j])
                if _trailing_backslashes(self._parts) % 2 == 1:
                    self._parts.append('"')
                    i = j + 1
                    continue
                self._in_string = False
                out.append(self._finish_string("".join(self._parts)))
                i = j + 1
        return "".join(out)

    def close(self) -> None:
        if self._in_string:
            raise FormatError("JSON endet innerhalb einer Zeichenkette.")

    def _track_structure(self, segment: str) -> None:
        for match in _STRUCTURE.finditer(segment):
            char = match.group()
            if char == "{":
                self._stack.append("o")
                self._expect_key = True
            elif char == "[":
                self._stack.append("a")
                self._expect_key = False
            elif char in "}]":
                if self._stack:
                    self._stack.pop()
                self._expect_key = False
                self._last_key = None
            elif char == ",":
                self._expect_key = bool(self._stack) and self._stack[-1] == "o"
                self._last_key = None
            else:  # ":"
                self._expect_key = False

    def _finish_string(self, raw: str) -> str:
        try:
            value = json.loads('"' + raw + '"')
        except ValueError as exc:
            raise FormatError(f"Ungültige JSON-Zeichenkette: {exc}.") from exc
        in_object = bool(self._stack) and self._stack[-1] == "o"
        is_key = self._expect_key and in_object
        is_secret = (not is_key and in_object and self._last_key is not None
                     and bool(self.secret_keys.search(self._last_key)))
        if is_key:
            self._last_key = value
            self._expect_key = False
        new = self.callback(value, is_key, is_secret)
        if new is None or new == value:
            return '"' + raw + '"'
        return json.dumps(new, ensure_ascii="\\u" in raw)


def _trailing_backslashes(parts: list[str]) -> int:
    count = 0
    for part in reversed(parts):
        stripped = part.rstrip("\\")
        count += len(part) - len(stripped)
        if stripped:
            break
    return count
