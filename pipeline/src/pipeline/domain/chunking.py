"""Splits long markdown text into coherent chunks that fit a local model's context
window. Pure, deterministic, no tokenizer dependency — heading-aware first, with a
paragraph-boundary (then hard char-length) fallback for oversized sections."""

from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)

DEFAULT_MAX_CHARS = 4000


def chunk_markdown(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    for section in _split_by_heading(text):
        if len(section) <= max_chars:
            chunks.append(section)
        else:
            chunks.extend(_split_by_paragraph(section, max_chars))
    return chunks


def _split_by_heading(text: str) -> list[str]:
    starts = [m.start() for m in _HEADING_RE.finditer(text)]
    if not starts:
        return [text]

    sections = []
    if starts[0] != 0:
        sections.append(text[: starts[0]].strip())
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        section = text[start:end].strip()
        if section:
            sections.append(section)
    return [s for s in sections if s]


def _split_by_paragraph(section: str, max_chars: int) -> list[str]:
    paragraphs = [p for p in section.split("\n\n") if p.strip()]
    grouped: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars and current:
            grouped.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        grouped.append(current)

    final: list[str] = []
    for chunk in grouped:
        if len(chunk) <= max_chars:
            final.append(chunk)
        else:
            final.extend(chunk[i : i + max_chars] for i in range(0, len(chunk), max_chars))
    return final
