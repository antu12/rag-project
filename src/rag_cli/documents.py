from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt"}


@dataclass(frozen=True)
class LoadedDocument:
    path: Path
    relative_path: str
    file_type: str
    file_hash: str
    pages: list[tuple[str, int | None]]


@dataclass(frozen=True)
class SkippedFile:
    path: Path
    reason: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_supported(path: Path) -> tuple[list[Path], list[SkippedFile]]:
    if path.is_file():
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            return [path], []
        return [], [SkippedFile(path, "unsupported file type")]

    supported: list[Path] = []
    skipped: list[SkippedFile] = []
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        if item.suffix.lower() in SUPPORTED_EXTENSIONS:
            supported.append(item)
        else:
            skipped.append(SkippedFile(item, "unsupported file type"))
    return supported, skipped


def load_document(path: Path, root: Path) -> LoadedDocument:
    suffix = path.suffix.lower()
    file_hash = file_sha256(path)
    relative_path = str(path.relative_to(root)) if path != root and root.is_dir() else path.name

    if suffix in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        pages = [(text, None)]
    elif suffix == ".pdf":
        pages = load_pdf(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    return LoadedDocument(
        path=path,
        relative_path=relative_path.replace("\\", "/"),
        file_type=suffix.lstrip("."),
        file_hash=file_hash,
        pages=pages,
    )


def load_pdf(path: Path) -> list[tuple[str, int | None]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[tuple[str, int | None]] = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append((page.extract_text() or "", index))
    return pages
