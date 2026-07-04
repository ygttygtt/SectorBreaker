"""Document parsing utilities for uploaded reports and notes."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from backend.app.schemas.documents import DocumentCitation, DocumentSegment

_URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")
_PDF_TEXT_OPERATOR_RE = re.compile(rb"\((?:\\.|[^\\)])*\)\s*Tj|\[((?:.|\n)*?)\]\s*TJ")
_PDF_STRING_RE = re.compile(rb"\((?:\\.|[^\\)])*\)")


def extract_uploaded_document_text(file_name: str | None, mime_type: str | None, raw_bytes: bytes) -> str:
    """Extract text from supported uploaded document formats."""

    suffix = Path(file_name or "").suffix.lower()
    normalized_mime = (mime_type or "").lower()
    if suffix in {".txt", ".md", ".markdown"} or normalized_mime in {"text/plain", "text/markdown"}:
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("document must be utf-8 text") from exc
    if suffix == ".docx" or normalized_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx_text(raw_bytes)
    if suffix == ".pdf" or normalized_mime == "application/pdf":
        return _extract_pdf_text(raw_bytes)
    raise ValueError("unsupported document type")


def _extract_docx_text(raw_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            document_xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ValueError("invalid docx document") from exc

    root = ElementTree.fromstring(document_xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    content = "\n\n".join(paragraphs).strip()
    if not content:
        raise ValueError("docx document contains no extractable text")
    return content


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]

        reader = PdfReader(io.BytesIO(raw_bytes))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        content = "\n\n".join(page for page in pages if page).strip()
        if content:
            return content
    except Exception:
        pass

    content = _extract_basic_pdf_literal_text(raw_bytes)
    if content:
        return content
    raise ValueError("pdf document contains no extractable text; install pypdf or upload docx/txt")


def _extract_basic_pdf_literal_text(raw_bytes: bytes) -> str:
    chunks: list[str] = []
    for match in _PDF_TEXT_OPERATOR_RE.finditer(raw_bytes):
        operator = match.group(0)
        for raw_string in _PDF_STRING_RE.findall(operator):
            text = _decode_pdf_literal_string(raw_string[1:-1])
            if text:
                chunks.append(text)
    content = " ".join(chunks)
    content = re.sub(r"\s+", " ", content).strip()
    return content if len(content) >= 20 else ""


def _decode_pdf_literal_string(value: bytes) -> str:
    value = (
        value.replace(rb"\(", b"(")
        .replace(rb"\)", b")")
        .replace(rb"\\", b"\\")
        .replace(rb"\n", b"\n")
        .replace(rb"\r", b"\r")
        .replace(rb"\t", b"\t")
    )
    for encoding in ("utf-16-be", "utf-8", "latin-1"):
        try:
            text = value.decode(encoding)
        except UnicodeDecodeError:
            continue
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", text).strip()
        if cleaned:
            return cleaned
    return ""


def split_document_segments(document_id: str, content: str) -> list[DocumentSegment]:
    normalized = content.replace("\r\n", "\n").strip()
    if not normalized:
        return [
            DocumentSegment(
                id=f"{document_id}-seg-001",
                document_id=document_id,
                order_index=1,
                text="",
                char_count=0,
                citation_refs=[],
            )
        ]

    chunks = re.split(r"\n\s*\n+", normalized)
    segments: list[DocumentSegment] = []
    for index, chunk in enumerate(chunks, start=1):
        lines = [line.rstrip() for line in chunk.splitlines()]
        heading = None
        if lines and lines[0].lstrip().startswith("#"):
            heading = lines[0].lstrip("# ").strip() or None
        citation_refs = _URL_PATTERN.findall(chunk)
        segments.append(
            DocumentSegment(
                id=f"{document_id}-seg-{index:03d}",
                document_id=document_id,
                order_index=index,
                heading=heading,
                text=chunk.strip(),
                char_count=len(chunk.strip()),
                citation_refs=citation_refs,
            )
        )
    return segments


def extract_document_citations(document_id: str, segments: list[DocumentSegment]) -> list[DocumentCitation]:
    citation_map: dict[str, list[str]] = {}
    for segment in segments:
        for url in segment.citation_refs:
            citation_map.setdefault(url, []).append(segment.id)

    citations: list[DocumentCitation] = []
    for index, (url, segment_ids) in enumerate(citation_map.items(), start=1):
        citations.append(
            DocumentCitation(
                id=f"{document_id}-cit-{index:03d}",
                document_id=document_id,
                raw_reference=url,
                source_url=url,
                referenced_segment_ids=segment_ids,
            )
        )
    return citations
