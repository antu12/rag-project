from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .chunking import chunk_pages
from .config import EffectiveConfig
from .documents import discover_supported, load_document
from .errors import IngestError, WorkspaceError
from .metadata import ChunkRecord, MetadataStore, SourceRecord, now_iso
from .providers import BaseProvider, provider_from_config
from .stores import SearchHit, VectorItem, new_vector_id, store_from_config


@dataclass(frozen=True)
class IngestSummary:
    added: int
    updated: int
    skipped: int
    unsupported: int
    failed: int
    messages: list[str]


def ingest_path(
    path: Path,
    workspace: str,
    config: EffectiveConfig,
    metadata: MetadataStore,
    force: bool = False,
    progress: Callable[[str], None] | None = None,
    root: Path | None = None,
) -> IngestSummary:
    if not path.exists():
        raise IngestError(f"Path does not exist: {path}")

    provider = provider_from_config(config)
    store = store_from_config(config)
    supported, skipped_files = discover_supported(path)
    if not supported:
        return IngestSummary(0, 0, 0, len(skipped_files), 0, ["No supported files were found."])

    added = updated = skipped = failed = 0
    messages = [f"Unsupported: {item.path} ({item.reason})" for item in skipped_files]
    root = root or (path if path.is_dir() else path.parent)

    for file_path in supported:
        try:
            if progress:
                progress(f"Loading {file_path}")
            document = load_document(file_path, root)
            existing = metadata.find_source(workspace, document.relative_path)
            if existing and existing.file_hash == document.file_hash and not force:
                if progress:
                    progress(f"Skipping unchanged file {document.relative_path}")
                skipped += 1
                continue

            if progress:
                progress(f"Chunking {document.relative_path}")
            chunks = chunk_pages(
                document.pages,
                int(config.get("chunk_size")),
                int(config.get("chunk_overlap")),
            )
            if not chunks:
                skipped += 1
                messages.append(f"Skipped empty text: {document.relative_path}")
                continue

            if progress:
                progress(f"Embedding {len(chunks)} chunks from {document.relative_path}")
            embeddings = provider.embed_texts([chunk.text for chunk in chunks], progress=progress)
            dimensions = len(embeddings[0]) if embeddings else provider.expected_dimensions()
            if not dimensions:
                raise IngestError("Could not determine embedding dimensions.")
            metadata.assert_dimensions(workspace, config.store, provider.embedding_model, dimensions)
            namespace = store.ensure_namespace(workspace, dimensions)
            metadata.set_namespace(
                workspace,
                config.store,
                config.provider,
                provider.embedding_model,
                dimensions,
                namespace,
            )

            if existing:
                old_vectors = metadata.delete_source(existing.id)
                store.delete(namespace, old_vectors)
                updated += 1
            else:
                added += 1

            source_id = f"{workspace}:{document.relative_path}:{document.file_hash[:16]}"
            vector_items: list[VectorItem] = []
            chunk_records: list[ChunkRecord] = []
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunk_id = f"{source_id}:{index}"
                vector_id = new_vector_id()
                vector_items.append(
                    VectorItem(
                        vector_id=vector_id,
                        source_id=source_id,
                        chunk_id=chunk_id,
                        workspace=workspace,
                        source_path=document.relative_path,
                        chunk_index=index,
                        page_number=chunk.page_number,
                        text=chunk.text,
                        embedding=embedding,
                        provider=config.provider,
                        embedding_model=provider.embedding_model,
                        dimensions=dimensions,
                    )
                )
                chunk_records.append(
                    ChunkRecord(
                        id=chunk_id,
                        source_id=source_id,
                        workspace=workspace,
                        source_path=document.relative_path,
                        chunk_index=index,
                        page_number=chunk.page_number,
                        text=chunk.text,
                        vector_id=vector_id,
                    )
                )

            if progress:
                progress(f"Storing {len(vector_items)} vectors for {document.relative_path}")
            store.upsert(namespace, vector_items)
            metadata.upsert_source(
                SourceRecord(
                    id=source_id,
                    workspace=workspace,
                    source_path=document.relative_path,
                    file_type=document.file_type,
                    file_hash=document.file_hash,
                    chunk_count=len(chunk_records),
                    provider=config.provider,
                    embedding_model=provider.embedding_model,
                    generation_model=provider.generation_model,
                    store=config.store,
                    dimensions=dimensions,
                    ingested_at=now_iso(),
                ),
                chunk_records,
            )
        except Exception as exc:
            failed += 1
            messages.append(f"Failed: {file_path} ({exc})")

    return IngestSummary(added, updated, skipped, len(skipped_files), failed, messages)


def retrieve(
    query: str,
    workspace: str,
    config: EffectiveConfig,
    metadata: MetadataStore,
    provider: BaseProvider | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[SearchHit]:
    namespace_row = metadata.namespace(workspace, config.store)
    if not namespace_row:
        raise WorkspaceError("No documents are indexed for this workspace/store yet.")
    provider = provider or provider_from_config(config)
    if progress:
        progress(f"Embedding query with {config.provider} model {provider.embedding_model}.")
    query_embedding = provider.embed_texts([query], progress=progress)[0]
    dimensions = len(query_embedding)
    metadata.assert_dimensions(workspace, config.store, provider.embedding_model, dimensions)
    store = store_from_config(config)
    if progress:
        progress(f"Searching {config.store} for top {config.get('top_k')} chunks.")
    return store.search(str(namespace_row["namespace"]), query_embedding, int(config.get("top_k")))


def build_context(hits: list[SearchHit]) -> str:
    blocks = []
    for index, hit in enumerate(hits, start=1):
        cite = citation_for(hit)
        blocks.append(f"[{index}] {cite}\n{hit.text}")
    return "\n\n".join(blocks)


def citation_for(hit: SearchHit) -> str:
    if hit.page_number:
        return f"{hit.source_path} page {hit.page_number}"
    return f"{hit.source_path} chunk {hit.chunk_index}"


def ask_question(
    question: str,
    workspace: str,
    config: EffectiveConfig,
    metadata: MetadataStore,
    progress: Callable[[str], None] | None = None,
) -> tuple[str, list[SearchHit], dict[str, int] | None, str]:
    provider = provider_from_config(config)
    hits = retrieve(question, workspace, config, metadata, provider=provider, progress=progress)
    if not hits:
        return "No relevant context was found in the indexed documents.", [], None, ""
    if progress:
        progress(f"Building prompt context from {len(hits)} retrieved chunks.")
    context = build_context(hits)
    result = provider.generate(question, context, progress=progress)
    return result.text, hits, result.token_usage, context


def load_eval_file(path: Path) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Eval file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        import yaml

        data = yaml.safe_load(text)
    tests = data.get("tests") if isinstance(data, dict) else None
    if not isinstance(tests, list):
        raise ValueError("Eval file must contain a top-level 'tests' list.")
    for index, item in enumerate(tests, start=1):
        if not isinstance(item, dict) or not item.get("question") or not item.get("expected_sources"):
            raise ValueError(f"Eval test {index} must include question and expected_sources.")
    return tests


def source_matched(actual: str, expected: str) -> bool:
    return actual == expected or actual.endswith(expected)
