"""Pluggable resume parsing. The default implementation is keyword based and dependency free."""

from __future__ import annotations

import html
import logging
import re
import zipfile
import zlib
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<![\w])(\+?\d[\d\s().\-]{8,18}\d)(?![\w])")
_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_PDF_TJ_RE = re.compile(rb"\(((?:\\.|[^\\()])*)\)\s*Tj")
_PDF_TJ_ARRAY_RE = re.compile(rb"\[((?:\\.|[^\]])*)\]\s*TJ")
_PDF_STR_RE = re.compile(rb"\(((?:\\.|[^\\()])*)\)")
_PRINTABLE_RE = re.compile(rb"[\x20-\x7e\n\r\t]{4,}")
_MAX_DECOMPRESSED = 20 * 1024 * 1024


class ResumeParser(Protocol):
    """Contract for resume parsers: swap by changing ``get_parser``."""

    def parse(self, path: str | Path, skill_names: list[str]) -> dict[str, Any]:
        """Return {"skills": [...master names...], "email": str|None, "phone": str|None}."""
        ...


def _unescape_pdf(raw: bytes) -> str:
    out = re.sub(rb"\\([nrtbf])", lambda m: {b"n": b"\n", b"r": b"\r", b"t": b"\t"}.get(m.group(1), b" "), raw)
    out = re.sub(rb"\\([()\\])", rb"\1", out)
    return out.decode("latin-1", errors="replace")


def _pdf_text(data: bytes) -> str:
    """Best-effort text from a PDF: scan (decompressed) streams for Tj/TJ text operators."""
    chunks: list[bytes] = [data]
    for match in _STREAM_RE.finditer(data):
        body = match.group(1)
        try:
            decompressor = zlib.decompressobj()
            chunks.append(decompressor.decompress(body, _MAX_DECOMPRESSED))
        except zlib.error:
            continue
    parts: list[str] = []
    for chunk in chunks:
        for m in _PDF_TJ_RE.finditer(chunk):
            parts.append(_unescape_pdf(m.group(1)))
        for m in _PDF_TJ_ARRAY_RE.finditer(chunk):
            parts.append("".join(_unescape_pdf(s) for s in _PDF_STR_RE.findall(m.group(1))))
    text = "\n".join(parts)
    return text if text.strip() else data.decode("latin-1", errors="replace")


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
    xml = re.sub(r"</w:p>|<w:br\s*/>|<w:tab\s*/>", "\n", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def _doc_text(data: bytes) -> str:
    """Legacy .doc: pull printable ASCII and UTF-16LE runs out of the binary."""
    runs = [m.group(0).decode("ascii", errors="ignore") for m in _PRINTABLE_RE.finditer(data)]
    wide = re.compile(rb"(?:[\x20-\x7e]\x00){4,}")
    runs.extend(m.group(0).decode("utf-16le", errors="ignore") for m in wide.finditer(data))
    return "\n".join(runs)


def extract_text(path: str | Path) -> str:
    """Extract text from txt/pdf/docx/doc, falling back to a raw byte decode."""
    p = Path(path)
    data = p.read_bytes()
    suffix = p.suffix.lower()
    text = ""
    try:
        if suffix == ".docx" or (data[:2] == b"PK" and suffix != ".pdf"):
            text = _docx_text(p)
        elif suffix == ".pdf" or data[:4] == b"%PDF":
            text = _pdf_text(data)
        elif suffix == ".doc" and data[:4] == b"\xd0\xcf\x11\xe0":
            text = _doc_text(data)
    except (zipfile.BadZipFile, KeyError, zlib.error, OSError) as exc:
        logger.info("Structured text extraction failed for %s: %s", p.name, exc)
        text = ""
    if not text.strip():
        text = data.decode("utf-8", errors="replace")
    return text


def _skill_pattern(name: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9+#])" + re.escape(name.strip()) + r"(?![A-Za-z0-9+#])", re.IGNORECASE)


class KeywordResumeParser:
    """Matches master skill names (word-boundary, case-insensitive) and contact details."""

    def parse(self, path: str | Path, skill_names: list[str]) -> dict[str, Any]:
        text = extract_text(path)
        skills: list[str] = []
        seen: set[str] = set()
        for name in skill_names:
            key = name.strip().casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            if _skill_pattern(name).search(text):
                skills.append(name)
        email_match = _EMAIL_RE.search(text)
        phone: str | None = None
        for m in _PHONE_RE.finditer(text):
            digits = re.sub(r"\D", "", m.group(1))
            if 10 <= len(digits) <= 15:
                phone = ("+" if m.group(1).startswith("+") else "") + digits
                break
        return {"skills": skills, "email": email_match.group(0).lower() if email_match else None, "phone": phone}


_parser: ResumeParser = KeywordResumeParser()


def get_parser() -> ResumeParser:
    """Return the active parser (override ``_parser`` / this function to plug another in)."""
    return _parser
