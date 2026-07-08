from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import EffectiveConfig


INGEST_EVENT_NAME = "rag/ingest.requested"
INNGEST_APP_ID = "rag-cli"
INNGEST_ENDPOINT_PATH = "/api/inngest"
INNGEST_DEV_SERVER_URL = "http://localhost:8288"
INGEST_APP_SERVER_URL = "http://localhost:8000"
LOCAL_INNGEST_SIGNING_KEY = "signkey-test-00000000000000000000000000000000"


def is_valid_inngest_signing_key(value: str | None) -> bool:
    if not value:
        return False
    for prefix in ("signkey-test-", "signkey-prod-"):
        if value.startswith(prefix):
            suffix = value.removeprefix(prefix)
            try:
                bytes.fromhex(suffix)
            except ValueError:
                return False
            return bool(suffix)
    return False


@dataclass(frozen=True)
class IngestEventPayload:
    workspace: str
    path: str
    provider: str
    store: str
    embedding_model: str
    generation_model: str
    chunk_size: int
    chunk_overlap: int
    force: bool
    requested_at: str

    def to_data(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "path": self.path,
            "provider": self.provider,
            "store": self.store,
            "embedding_model": self.embedding_model,
            "generation_model": self.generation_model,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "force": self.force,
            "requested_at": self.requested_at,
        }


def build_ingest_event_payload(
    path: Path,
    workspace: str,
    config: EffectiveConfig,
    force: bool,
) -> IngestEventPayload:
    return IngestEventPayload(
        workspace=workspace,
        path=str(path).replace("\\", "/"),
        provider=config.provider,
        store=config.store,
        embedding_model=config.embedding_model,
        generation_model=config.generation_model,
        chunk_size=int(config.get("chunk_size")),
        chunk_overlap=int(config.get("chunk_overlap")),
        force=force,
        requested_at=datetime.now(timezone.utc).isoformat(),
    )


def build_ingest_event(payload: IngestEventPayload) -> dict[str, Any]:
    return {
        "name": INGEST_EVENT_NAME,
        "data": payload.to_data(),
    }


build_inngest_event = build_ingest_event


def validate_ingest_event_data(data: dict[str, Any]) -> IngestEventPayload:
    required = [
        "workspace",
        "path",
        "provider",
        "store",
        "embedding_model",
        "generation_model",
        "chunk_size",
        "chunk_overlap",
        "force",
        "requested_at",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"Ingest event missing required fields: {', '.join(missing)}")
    return IngestEventPayload(
        workspace=str(data["workspace"]),
        path=str(data["path"]),
        provider=str(data["provider"]),
        store=str(data["store"]),
        embedding_model=str(data["embedding_model"]),
        generation_model=str(data["generation_model"]),
        chunk_size=int(data["chunk_size"]),
        chunk_overlap=int(data["chunk_overlap"]),
        force=bool(data["force"]),
        requested_at=str(data["requested_at"]),
    )


def assert_secret_safe_event(event: dict[str, Any]) -> None:
    text = repr(event).lower()
    forbidden = ["api_key", "apikey", "secret", "token", "password", "embedding\": ["]
    found = [marker for marker in forbidden if marker in text]
    if found:
        raise ValueError(f"Inngest event contains forbidden secret-like fields: {', '.join(found)}")
