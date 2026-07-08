from __future__ import annotations

from dataclasses import dataclass

from .errors import ConfigError


@dataclass(frozen=True)
class TextChunk:
    text: str
    page_number: int | None


def chunk_pages(pages: list[tuple[str, int | None]], chunk_size: int, chunk_overlap: int) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ConfigError("chunk_size must be positive.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ConfigError("chunk_overlap must be smaller than chunk_size.")

    chunks: list[TextChunk] = []
    for text, page_number in pages:
        cleaned = " ".join(text.split())
        if not cleaned:
            continue
        start = 0
        while start < len(cleaned):
            end = min(start + chunk_size, len(cleaned))
            chunk_text = cleaned[start:end].strip()
            if chunk_text:
                chunks.append(TextChunk(text=chunk_text, page_number=page_number))
            if end == len(cleaned):
                break
            start = max(end - chunk_overlap, start + 1)
    return chunks
