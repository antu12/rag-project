from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI

from .config import effective_config
from .documents import discover_supported
from .inngest_payloads import (
    INGEST_EVENT_NAME,
    INNGEST_APP_ID,
    IngestEventPayload,
    LOCAL_INNGEST_SIGNING_KEY,
    assert_secret_safe_event,
    is_valid_inngest_signing_key,
    validate_ingest_event_data,
)
from .metadata import MetadataStore
from .operations import IngestSummary, ingest_path


logger = logging.getLogger("rag_cli.inngest")
app = FastAPI(title="RAG CLI Inngest App")
os.environ.setdefault("INNGEST_DEV", "1")
os.environ.setdefault("INNGEST_EVENT_KEY", "local")
if not is_valid_inngest_signing_key(os.environ.get("INNGEST_SIGNING_KEY")):
    os.environ["INNGEST_SIGNING_KEY"] = LOCAL_INNGEST_SIGNING_KEY


def _load_inngest():
    import inngest
    import inngest.fast_api

    return inngest


inngest = _load_inngest()
inngest_client = inngest.Inngest(app_id=INNGEST_APP_ID, logger=logger)


@inngest_client.create_function(
    fn_id="rag-ingest-requested",
    trigger=inngest.TriggerEvent(event=INGEST_EVENT_NAME),
)
async def rag_ingest_requested(ctx: Any) -> dict[str, Any]:
    event = {"name": ctx.event.name, "data": ctx.event.data}
    assert_secret_safe_event(event)
    payload = validate_ingest_event_data(ctx.event.data)

    await _step_run(ctx, "validate workspace and config", lambda: _validate_payload(payload))
    discovered = await _step_run(ctx, "discover files", lambda: _discover(payload))

    totals = IngestSummary(0, 0, 0, int(discovered["unsupported"]), 0, list(discovered["messages"]))
    root = Path(payload.path) if Path(payload.path).is_dir() else Path(payload.path).parent
    for file_name in discovered["files"]:
        file_path = Path(file_name)
        result = await _step_run(ctx, f"ingest file: {file_path.name}", lambda file_path=file_path: _ingest_one(payload, file_path, root, ctx))
        totals = IngestSummary(
            totals.added + int(result["added"]),
            totals.updated + int(result["updated"]),
            totals.skipped + int(result["skipped"]),
            totals.unsupported,
            totals.failed + int(result["failed"]),
            totals.messages + list(result["messages"]),
        )

    summary = {
        "added": totals.added,
        "updated": totals.updated,
        "skipped": totals.skipped,
        "unsupported": totals.unsupported,
        "failed": totals.failed,
        "messages": totals.messages,
    }
    await _step_run(ctx, "final ingest summary", lambda: summary)
    return summary


async def _step_run(ctx: Any, name: str, fn: Callable[[], Any]) -> Any:
    result = ctx.step.run(name, fn)
    if hasattr(result, "__await__"):
        return await result
    return result


def _validate_payload(payload: IngestEventPayload) -> dict[str, Any]:
    overrides = {
        "provider": payload.provider,
        "store": payload.store,
        "chunk_size": payload.chunk_size,
        "chunk_overlap": payload.chunk_overlap,
        f"{payload.provider}_embedding_model": payload.embedding_model,
        f"{payload.provider}_generation_model": payload.generation_model,
    }
    cfg = effective_config(overrides)
    db = MetadataStore()
    db.get_workspace(payload.workspace)
    db.close()
    return {
        "workspace": payload.workspace,
        "provider": cfg.provider,
        "store": cfg.store,
        "embedding_model": cfg.embedding_model,
        "generation_model": cfg.generation_model,
    }


def _discover(payload: IngestEventPayload) -> dict[str, Any]:
    path = Path(payload.path)
    supported, skipped = discover_supported(path)
    return {
        "files": [str(item) for item in supported],
        "unsupported": len(skipped),
        "messages": [f"Unsupported: {item.path} ({item.reason})" for item in skipped],
    }


def _ingest_one(payload: IngestEventPayload, file_path: Path, root: Path, ctx: Any) -> dict[str, Any]:
    overrides = {
        "provider": payload.provider,
        "store": payload.store,
        "chunk_size": payload.chunk_size,
        "chunk_overlap": payload.chunk_overlap,
        f"{payload.provider}_embedding_model": payload.embedding_model,
        f"{payload.provider}_generation_model": payload.generation_model,
    }
    cfg = effective_config(overrides)
    db = MetadataStore()

    def progress(message: str) -> None:
        ctx.logger.info(message)

    summary = ingest_path(
        file_path,
        payload.workspace,
        cfg,
        db,
        force=payload.force,
        progress=progress,
        root=root,
    )
    db.close()
    return {
        "added": summary.added,
        "updated": summary.updated,
        "skipped": summary.skipped,
        "unsupported": summary.unsupported,
        "failed": summary.failed,
        "messages": summary.messages,
    }


inngest.fast_api.serve(app, inngest_client, [rag_ingest_requested])
