from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .paths import CONFIG_PATH, PROJECT_DIR, ensure_runtime_dirs


DEFAULTS: dict[str, Any] = {
    "provider": "openai",
    "store": "pgvector",
    "chunk_size": 1000,
    "chunk_overlap": 150,
    "top_k": 5,
    "postgres_dsn": "postgresql://rag:rag@localhost:5432/rag",
    "qdrant_url": "http://localhost:6333",
    "openai_embedding_model": "text-embedding-3-small",
    "openai_generation_model": "gpt-4o-mini",
    "gemini_embedding_model": "gemini-embedding-2",
    "gemini_generation_model": "gemini-3.5-flash",
    "request_timeout_seconds": 60,
    "request_retries": 3,
    "gemini_embedding_retries": 20,
    "gemini_embedding_delay_seconds": 0.7,
}

ENV_KEYS = {
    "provider": "RAG_PROVIDER",
    "store": "RAG_STORE",
    "chunk_size": "RAG_CHUNK_SIZE",
    "chunk_overlap": "RAG_CHUNK_OVERLAP",
    "top_k": "RAG_TOP_K",
    "postgres_dsn": "RAG_POSTGRES_DSN",
    "qdrant_url": "RAG_QDRANT_URL",
    "openai_embedding_model": "RAG_OPENAI_EMBEDDING_MODEL",
    "openai_generation_model": "RAG_OPENAI_GENERATION_MODEL",
    "gemini_embedding_model": "RAG_GEMINI_EMBEDDING_MODEL",
    "gemini_generation_model": "RAG_GEMINI_GENERATION_MODEL",
    "request_timeout_seconds": "RAG_REQUEST_TIMEOUT_SECONDS",
    "request_retries": "RAG_REQUEST_RETRIES",
    "gemini_embedding_retries": "RAG_GEMINI_EMBEDDING_RETRIES",
    "gemini_embedding_delay_seconds": "RAG_GEMINI_EMBEDDING_DELAY_SECONDS",
}

INT_KEYS = {
    "chunk_size",
    "chunk_overlap",
    "top_k",
    "request_timeout_seconds",
    "request_retries",
    "gemini_embedding_retries",
}
FLOAT_KEYS = {"gemini_embedding_delay_seconds"}
ALLOWED_KEYS = set(DEFAULTS)


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or PROJECT_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class EffectiveConfig:
    values: dict[str, Any]

    def get(self, key: str) -> Any:
        return self.values[key]

    @property
    def provider(self) -> str:
        return str(self.get("provider"))

    @property
    def store(self) -> str:
        return str(self.get("store"))

    @property
    def embedding_model(self) -> str:
        return str(self.get(f"{self.provider}_embedding_model"))

    @property
    def generation_model(self) -> str:
        return str(self.get(f"{self.provider}_generation_model"))


def load_local_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ConfigError("Local config must be a JSON object.")
    return data


def save_local_config(data: dict[str, Any], path: Path = CONFIG_PATH) -> None:
    ensure_runtime_dirs()
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def coerce_value(key: str, value: Any) -> Any:
    if key in INT_KEYS:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Configuration key '{key}' must be an integer.") from exc
    if key in FLOAT_KEYS:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Configuration key '{key}' must be a number.") from exc
    return str(value) if value is not None else value


def effective_config(overrides: dict[str, Any] | None = None) -> EffectiveConfig:
    load_dotenv()
    local = load_local_config()
    values = dict(DEFAULTS)
    for key, value in local.items():
        if key in ALLOWED_KEYS:
            values[key] = coerce_value(key, value)
    for key, env_key in ENV_KEYS.items():
        if env_key in os.environ and os.environ[env_key] != "":
            values[key] = coerce_value(key, os.environ[env_key])
    for key, value in (overrides or {}).items():
        if value is not None:
            if key not in ALLOWED_KEYS:
                raise ConfigError(f"Unknown configuration key: {key}")
            values[key] = coerce_value(key, value)
    validate(values)
    return EffectiveConfig(values)


def validate(values: dict[str, Any]) -> None:
    if values["provider"] not in {"openai", "gemini"}:
        raise ConfigError("Provider must be 'openai' or 'gemini'.")
    if values["store"] not in {"pgvector", "qdrant"}:
        raise ConfigError("Store must be 'pgvector' or 'qdrant'.")
    if values["chunk_size"] <= 0:
        raise ConfigError("chunk_size must be positive.")
    if values["chunk_overlap"] < 0:
        raise ConfigError("chunk_overlap cannot be negative.")
    if values["chunk_overlap"] >= values["chunk_size"]:
        raise ConfigError("chunk_overlap must be smaller than chunk_size.")
    if values["top_k"] <= 0:
        raise ConfigError("top_k must be a positive integer.")
    if values["gemini_embedding_retries"] <= 0:
        raise ConfigError("gemini_embedding_retries must be a positive integer.")
    if values["gemini_embedding_delay_seconds"] < 0:
        raise ConfigError("gemini_embedding_delay_seconds cannot be negative.")


def set_config_value(key: str, value: str) -> None:
    if key not in ALLOWED_KEYS:
        raise ConfigError(f"Unknown configuration key: {key}")
    if "key" in key.lower() or "secret" in key.lower() or "token" in key.lower():
        raise ConfigError("Secrets must be stored in environment variables, not local config.")
    local = load_local_config()
    local[key] = coerce_value(key, value)
    validate({**DEFAULTS, **local})
    save_local_config(local)


def redacted_config(values: dict[str, Any]) -> dict[str, Any]:
    redacted = {}
    for key, value in values.items():
        value_text = str(value)
        if any(marker in key.lower() for marker in ("key", "secret", "token", "password")) or (
            "dsn" in key.lower() and "@" in value_text
        ):
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted
