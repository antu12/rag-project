from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .errors import WorkspaceError
from .paths import SQLITE_PATH, ensure_runtime_dirs


WORKSPACE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")


@dataclass(frozen=True)
class Workspace:
    id: int
    name: str
    created_at: str


@dataclass(frozen=True)
class SourceRecord:
    id: str
    workspace: str
    source_path: str
    file_type: str
    file_hash: str
    chunk_count: int
    provider: str
    embedding_model: str
    generation_model: str
    store: str
    dimensions: int
    ingested_at: str


@dataclass(frozen=True)
class ChunkRecord:
    id: str
    source_id: str
    workspace: str
    source_path: str
    chunk_index: int
    page_number: int | None
    text: str
    vector_id: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MetadataStore:
    def __init__(self, path: Path = SQLITE_PATH):
        self.path = path
        ensure_runtime_dirs()
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.migrate()

    def close(self) -> None:
        self.conn.close()

    def migrate(self) -> None:
        self.conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workspaces (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS namespaces (
              workspace TEXT NOT NULL,
              store TEXT NOT NULL,
              provider TEXT NOT NULL,
              embedding_model TEXT NOT NULL,
              dimensions INTEGER NOT NULL,
              namespace TEXT NOT NULL,
              PRIMARY KEY (workspace, store)
            );
            CREATE TABLE IF NOT EXISTS sources (
              id TEXT PRIMARY KEY,
              workspace TEXT NOT NULL,
              source_path TEXT NOT NULL,
              file_type TEXT NOT NULL,
              file_hash TEXT NOT NULL,
              chunk_count INTEGER NOT NULL,
              provider TEXT NOT NULL,
              embedding_model TEXT NOT NULL,
              generation_model TEXT NOT NULL,
              store TEXT NOT NULL,
              dimensions INTEGER NOT NULL,
              ingested_at TEXT NOT NULL,
              UNIQUE (workspace, source_path)
            );
            CREATE TABLE IF NOT EXISTS chunks (
              id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL,
              workspace TEXT NOT NULL,
              source_path TEXT NOT NULL,
              chunk_index INTEGER NOT NULL,
              page_number INTEGER,
              text TEXT NOT NULL,
              vector_id TEXT NOT NULL,
              FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
            );
            """
        )
        self.conn.commit()

    def create_workspace(self, name: str) -> Workspace:
        safe_name = normalize_workspace_name(name)
        try:
            self.conn.execute(
                "INSERT INTO workspaces (name, created_at) VALUES (?, ?)",
                (safe_name, now_iso()),
            )
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            raise WorkspaceError(f"Workspace already exists: {safe_name}") from exc
        return self.get_workspace(safe_name)

    def get_workspace(self, name: str) -> Workspace:
        row = self.conn.execute("SELECT * FROM workspaces WHERE name = ?", (name,)).fetchone()
        if not row:
            raise WorkspaceError(f"Workspace not found: {name}")
        return Workspace(id=row["id"], name=row["name"], created_at=row["created_at"])

    def list_workspaces(self) -> list[Workspace]:
        rows = self.conn.execute("SELECT * FROM workspaces ORDER BY name").fetchall()
        return [Workspace(id=row["id"], name=row["name"], created_at=row["created_at"]) for row in rows]

    def set_active_workspace(self, name: str) -> None:
        workspace = self.get_workspace(name)
        self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_workspace', ?)",
            (workspace.name,),
        )
        self.conn.commit()

    def active_workspace(self) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = 'active_workspace'").fetchone()
        return str(row["value"]) if row else None

    def resolve_workspace(self, requested: str | None, no_interactive: bool = False) -> str:
        if requested:
            return self.get_workspace(requested).name
        active = self.active_workspace()
        if active:
            return self.get_workspace(active).name
        workspaces = self.list_workspaces()
        if not workspaces:
            raise WorkspaceError("No workspace exists. Run 'rag workspace create <name>' first.")
        if no_interactive:
            raise WorkspaceError("No active workspace. Run 'rag workspace use <name>' or pass --workspace.")
        return workspaces[0].name

    def set_namespace(
        self, workspace: str, store: str, provider: str, embedding_model: str, dimensions: int, namespace: str
    ) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO namespaces
            (workspace, store, provider, embedding_model, dimensions, namespace)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (workspace, store, provider, embedding_model, dimensions, namespace),
        )
        self.conn.commit()

    def namespace(self, workspace: str, store: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM namespaces WHERE workspace = ? AND store = ?", (workspace, store)
        ).fetchone()

    def assert_dimensions(self, workspace: str, store: str, embedding_model: str, dimensions: int) -> None:
        row = self.namespace(workspace, store)
        if not row:
            return
        if int(row["dimensions"]) != dimensions or row["embedding_model"] != embedding_model:
            raise WorkspaceError(
                "Embedding model/dimension mismatch. Re-ingest the workspace or use "
                f"{row['embedding_model']} with {row['dimensions']} dimensions."
            )

    def find_source(self, workspace: str, source_path: str) -> SourceRecord | None:
        row = self.conn.execute(
            "SELECT * FROM sources WHERE workspace = ? AND source_path = ?", (workspace, source_path)
        ).fetchone()
        return source_from_row(row) if row else None

    def delete_source(self, source_id: str) -> list[str]:
        rows = self.conn.execute("SELECT vector_id FROM chunks WHERE source_id = ?", (source_id,)).fetchall()
        vector_ids = [str(row["vector_id"]) for row in rows]
        self.conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        self.conn.commit()
        return vector_ids

    def upsert_source(self, source: SourceRecord, chunks: Iterable[ChunkRecord]) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO sources
                (id, workspace, source_path, file_type, file_hash, chunk_count, provider,
                 embedding_model, generation_model, store, dimensions, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.id,
                    source.workspace,
                    source.source_path,
                    source.file_type,
                    source.file_hash,
                    source.chunk_count,
                    source.provider,
                    source.embedding_model,
                    source.generation_model,
                    source.store,
                    source.dimensions,
                    source.ingested_at,
                ),
            )
            self.conn.executemany(
                """
                INSERT OR REPLACE INTO chunks
                (id, source_id, workspace, source_path, chunk_index, page_number, text, vector_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.id,
                        chunk.source_id,
                        chunk.workspace,
                        chunk.source_path,
                        chunk.chunk_index,
                        chunk.page_number,
                        chunk.text,
                        chunk.vector_id,
                    )
                    for chunk in chunks
                ],
            )

    def list_sources(self, workspace: str, store: str | None = None) -> list[SourceRecord]:
        if store:
            rows = self.conn.execute(
                "SELECT * FROM sources WHERE workspace = ? AND store = ? ORDER BY source_path",
                (workspace, store),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM sources WHERE workspace = ? ORDER BY source_path", (workspace,)
            ).fetchall()
        return [source_from_row(row) for row in rows]

    def chunks_by_ids(self, vector_ids: list[str]) -> dict[str, ChunkRecord]:
        if not vector_ids:
            return {}
        placeholders = ",".join("?" for _ in vector_ids)
        rows = self.conn.execute(
            f"SELECT * FROM chunks WHERE vector_id IN ({placeholders})", vector_ids
        ).fetchall()
        return {str(row["vector_id"]): chunk_from_row(row) for row in rows}

    def reset_workspace_store(self, workspace: str, store: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT c.vector_id
            FROM chunks c
            JOIN sources s ON c.source_id = s.id
            WHERE s.workspace = ? AND s.store = ?
            """,
            (workspace, store),
        ).fetchall()
        vector_ids = [str(row["vector_id"]) for row in rows]
        self.conn.execute("DELETE FROM sources WHERE workspace = ? AND store = ?", (workspace, store))
        self.conn.execute("DELETE FROM namespaces WHERE workspace = ? AND store = ?", (workspace, store))
        self.conn.commit()
        return vector_ids


def normalize_workspace_name(name: str) -> str:
    normalized = name.strip()
    if not WORKSPACE_RE.match(normalized):
        raise WorkspaceError(
            "Workspace names must start with a letter or number and contain only letters, numbers, dashes, or underscores."
        )
    return normalized


def source_from_row(row: sqlite3.Row) -> SourceRecord:
    return SourceRecord(
        id=row["id"],
        workspace=row["workspace"],
        source_path=row["source_path"],
        file_type=row["file_type"],
        file_hash=row["file_hash"],
        chunk_count=int(row["chunk_count"]),
        provider=row["provider"],
        embedding_model=row["embedding_model"],
        generation_model=row["generation_model"],
        store=row["store"],
        dimensions=int(row["dimensions"]),
        ingested_at=row["ingested_at"],
    )


def chunk_from_row(row: sqlite3.Row) -> ChunkRecord:
    return ChunkRecord(
        id=row["id"],
        source_id=row["source_id"],
        workspace=row["workspace"],
        source_path=row["source_path"],
        chunk_index=int(row["chunk_index"]),
        page_number=row["page_number"],
        text=row["text"],
        vector_id=row["vector_id"],
    )
