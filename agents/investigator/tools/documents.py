"""Bounded, read-only document extraction for TXT, Markdown, PDF and DOCX.

Text artifacts are written beneath ToolContext.output_dir. Measurements record
summaries, references, and explicitly declared dictionary entries. No OCR is performed.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from ..contracts import ArtifactRef, Coverage, SourceRef, ToolResult

SUPPORTED = {"txt", "md", "pdf", "docx"}
_DECLARATION = re.compile(r"^(Table|Column)\s*:\s*(.*?)\s*$", re.IGNORECASE)


def _dictionary_evidence(text_parts: list[tuple[str, str, bool]], source_id: str) -> dict:
    """Parse explicit declarations from the same bounded text saved as an artifact."""
    table = column = None
    tables, entries = [], []
    for reference, part, complete in text_parts:
        lines = part.splitlines()
        if not complete and not part.endswith("\n"):
            lines = lines[:-1]
        for number, line in enumerate(lines, 1):
            line = line.strip()
            locator = reference if reference.startswith("line ") else f"{reference}, line {number}"
            citation = {"source_id": source_id, "locator": locator}
            declaration = _DECLARATION.fullmatch(line)
            if declaration:
                kind, value = declaration.groups()
                if value.startswith("`") and value.endswith("`"):
                    value = value[1:-1].strip()
                if kind.lower() == "table":
                    table, column = value, None
                    if table:
                        tables.append({"table": table, "citation": citation})
                else:
                    column = value
            elif table and column:
                code, separator, label = (piece.strip() for piece in line.partition("="))
                if separator and code and label:
                    entries.append({"table": table, "column": column, "code": code, "label": label,
                                    "citation": citation})
    return {"tables": tables, "entries": entries}


def _limit(context: Any, key: str, default: int) -> int:
    limits = getattr(context, "limits", None)
    value = limits.get(key, default) if isinstance(limits, dict) else getattr(limits, key, default)
    if type(value) is not int or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def _source(source: SourceRef, context: Any) -> Path:
    root = Path(context.dataset_root).resolve(strict=True)
    path = Path(context.resolve_source(source)).resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(root) or path != (root / source.relative_path).resolve(strict=True):
        raise PermissionError("Unapproved document source")
    return path


def _output(context: Any, name: str) -> Path:
    if hasattr(context, "artifact_path"):
        return context.artifact_path(name)
    root = Path(context.output_dir).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise PermissionError("Output escapes private directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_pdf(path: Path, max_pages: int, max_chars: int) -> tuple[list[dict], int, list[str]]:
    from pypdf import PdfReader
    reader = PdfReader(str(path), strict=False)
    total = len(reader.pages)
    sections, issues = [], []
    for i in range(min(total, max_pages)):
        if sum(len(x["text"]) for x in sections) >= max_chars:
            break
        try:
            text = reader.pages[i].extract_text() or ""
        except Exception as exc:
            text = ""
            issues.append(f"Page {i+1} extraction failed ({type(exc).__name__}).")
        sections.append({"reference": f"page {i+1}", "text": text})
    return sections, total, issues


def _read_docx(path: Path, max_chars: int) -> tuple[list[dict], int, list[str]]:
    from docx import Document
    doc = Document(str(path))
    sections: list[dict] = []
    current = "body"
    for i, paragraph in enumerate(doc.paragraphs, 1):
        if paragraph.style and paragraph.style.name.lower().startswith("heading") and paragraph.text.strip():
            current = paragraph.text.strip()[:120]
        if paragraph.text.strip():
            sections.append({"reference": f"paragraph {i} ({current})", "text": paragraph.text})
        if sum(len(x["text"]) for x in sections) >= max_chars:
            break
    # Include table text with stable table/row references.
    if sum(len(x["text"]) for x in sections) < max_chars:
        for t, table in enumerate(doc.tables, 1):
            for r, row in enumerate(table.rows, 1):
                sections.append({"reference": f"table {t}, row {r}", "text": " | ".join(cell.text for cell in row.cells)})
                if sum(len(x["text"]) for x in sections) >= max_chars:
                    break
            if sum(len(x["text"]) for x in sections) >= max_chars:
                break
    # DOCX has no reliable physical page count without layout/rendering.
    return sections, len(doc.paragraphs) + sum(len(t.rows) for t in doc.tables), []


def extract_document(source: SourceRef, context: Any) -> ToolResult:
    """Extract text with references and explicit partial/unsupported outcomes."""
    fmt = source.format.lower()
    issues: list[str] = []
    sections: list[dict] = []
    total: int | None = None
    examined = 0
    status = "complete"
    max_chars = _limit(context, "max_text_chars", 2_000_000)
    max_bytes = _limit(context, "max_bytes_read", 512 * 1024 * 1024)
    max_pages = _limit(context, "max_document_pages", 500)
    artifacts = []
    measurements: dict[str, Any] = {"documents": {source.source_id: {"format": fmt, "source_path": source.relative_path}}}
    item = measurements["documents"][source.source_id]
    if fmt not in SUPPORTED:
        status = "unsupported"
        issues.append(f"Unsupported document format: {fmt}.")
    else:
        try:
            path = _source(source, context)
            if path.stat().st_size > max_bytes:
                status = "unsupported"
                issues.append(f"Document exceeds max_bytes_read ({max_bytes}); not opened.")
            elif fmt in {"txt", "md"}:
                data = path.read_bytes()
                text = data.decode("utf-8-sig", errors="strict")
                lines = text.splitlines()
                total = len(lines)
                # Preserve line references and record headings for Markdown.
                length = 0
                for i, line in enumerate(lines, 1):
                    if length >= max_chars:
                        break
                    sections.append({"reference": f"line {i}", "text": line})
                    length += len(line) + 1
                item["headings"] = [{"line": i, "heading": line.lstrip("# ").strip()}
                                    for i, line in enumerate(lines, 1) if fmt == "md" and re.match(r"^#{1,6}\s", line)][:100]
            elif fmt == "pdf":
                sections, total, extra = _read_pdf(path, max_pages, max_chars)
                issues.extend(extra)
            else:
                sections, total, extra = _read_docx(path, max_chars)
                issues.extend(extra)
        except Exception as exc:
            # Do not expose absolute paths, source content, or exception strings.
            status = "failed"
            issues.append(f"Document extraction failed ({type(exc).__name__}).")
    # Ensure strict bound even when a single page/paragraph is huge.
    text_parts = []
    remaining = max_chars
    for section in sections:
        if remaining <= 0:
            break
        if text_parts:
            remaining -= 1  # separator inserted when assembling the artifact
        if remaining <= 0:
            break
        part = section["text"][:remaining]
        text_parts.append((section["reference"], part, len(part) == len(section["text"])))
        remaining -= len(part)
    extracted = "\n".join(part for _, part, _ in text_parts)
    examined = len(text_parts)
    if total is None:
        total = examined
    if status == "complete" and (examined < total or issues):
        status = "partial"
    if examined < total:
        issues.append(f"Only {examined} of {total} document units extracted (resource limit or truncation).")
    if any(not complete for _, _, complete in text_parts):
        issues.append(f"Extracted text limited to {max_chars} characters.")
        if status == "complete":
            status = "partial"
    if status == "complete" and not extracted.strip():
        issues.append("No extractable text; document may be empty or scanned and require OCR.")
        status = "partial"
    if status != "complete" and not issues:
        issues.append("Document extraction incomplete.")
    item.update({"unit": "pages" if fmt == "pdf" else "files" if fmt not in {"txt", "md", "docx"} else "pages",
                 "units_examined": examined, "units_total": total,
                 "character_count": len(extracted), "word_count": len(re.findall(r"\b\w+\b", extracted)),
                 "empty_content": not bool(extracted.strip()), "possible_scanned_document": fmt == "pdf" and not bool(extracted.strip()),
                 "references": [{"reference": ref, "characters": len(txt)} for ref, txt, _ in text_parts[:500]],
                 "role": "unclassified_document", "role_note": "Supporting documentation versus text dataset requires external evidence."})
    if status in {"complete", "partial"}:
        item["dictionary"] = _dictionary_evidence(text_parts, source.source_id)
        name = f"documents/{hashlib.sha256(source.source_id.encode()).hexdigest()[:16]}.txt"
        _output(context, name).write_text(extracted, encoding="utf-8")
        artifacts.append(context.artifact(name, "text/plain") if hasattr(context, "artifact") else
                         ArtifactRef(
                             f"{context.result_id}:text", name, "text/plain"))
        item["text_artifact"] = name
    unit = "pages" if fmt in SUPPORTED else "files"
    coverage = Coverage(mode="none" if examined == 0 else "full" if status == "complete" else "sample",
                        unit=unit, examined=examined, total=total,
                        selection="Document units in source order, bounded by byte/page/character limits; no random sampling",
                        seed=None)
    return ToolResult(result_id=str(context.result_id), component_id=str(context.component_id),
                      status=status, inputs=[source.source_id], method="bounded_document_extraction_v2",
                      parameters={"max_text_chars": max_chars, "max_bytes_read": max_bytes, "max_document_pages": max_pages},
                      coverage=coverage, measurements=measurements, artifacts=artifacts, limitations=issues)
