from __future__ import annotations

import uuid
from dataclasses import dataclass

from .config import EffectiveConfig
from .errors import StorageError


@dataclass(frozen=True)
class VectorItem:
    vector_id: str
    source_id: str
    chunk_id: str
    workspace: str
    source_path: str
    chunk_index: int
    page_number: int | None
    text: str
    embedding: list[float]
    provider: str
    embedding_model: str
    dimensions: int


@dataclass(frozen=True)
class SearchHit:
    vector_id: str
    score: float | None
    text: str
    source_path: str
    chunk_index: int
    page_number: int | None


class BaseVectorStore:
    name: str

    def ensure_namespace(self, workspace: str, dimensions: int) -> str:
        raise NotImplementedError

    def upsert(self, namespace: str, items: list[VectorItem]) -> None:
        raise NotImplementedError

    def delete(self, namespace: str, vector_ids: list[str]) -> None:
        raise NotImplementedError

    def search(self, namespace: str, query_embedding: list[float], top_k: int) -> list[SearchHit]:
        raise NotImplementedError

    def reset(self, namespace: str) -> None:
        raise NotImplementedError

    def doctor(self) -> tuple[bool, str]:
        raise NotImplementedError


class PgvectorStore(BaseVectorStore):
    name = "pgvector"

    def __init__(self, config: EffectiveConfig):
        self.dsn = str(config.get("postgres_dsn"))

    def _connect(self):
        import psycopg

        return psycopg.connect(self.dsn, connect_timeout=3)

    def ensure_namespace(self, workspace: str, dimensions: int) -> str:
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_chunks (
                  id TEXT PRIMARY KEY,
                  workspace TEXT NOT NULL,
                  source_id TEXT NOT NULL,
                  chunk_id TEXT NOT NULL,
                  source_path TEXT NOT NULL,
                  chunk_index INTEGER NOT NULL,
                  page_number INTEGER,
                  content TEXT NOT NULL,
                  embedding vector NOT NULL,
                  provider TEXT NOT NULL,
                  embedding_model TEXT NOT NULL,
                  dimensions INTEGER NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_chunks_workspace ON rag_chunks(workspace)")
        return workspace

    def upsert(self, namespace: str, items: list[VectorItem]) -> None:
        if not items:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                for item in items:
                    cur.execute(
                        """
                        INSERT INTO rag_chunks
                        (id, workspace, source_id, chunk_id, source_path, chunk_index, page_number,
                         content, embedding, provider, embedding_model, dimensions)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                          content = EXCLUDED.content,
                          embedding = EXCLUDED.embedding,
                          provider = EXCLUDED.provider,
                          embedding_model = EXCLUDED.embedding_model,
                          dimensions = EXCLUDED.dimensions
                        """,
                        (
                            item.vector_id,
                            namespace,
                            item.source_id,
                            item.chunk_id,
                            item.source_path,
                            item.chunk_index,
                            item.page_number,
                            item.text,
                            vector_literal(item.embedding),
                            item.provider,
                            item.embedding_model,
                            item.dimensions,
                        ),
                    )

    def delete(self, namespace: str, vector_ids: list[str]) -> None:
        if not vector_ids:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rag_chunks WHERE workspace = %s AND id = ANY(%s)", (namespace, vector_ids))

    def search(self, namespace: str, query_embedding: list[float], top_k: int) -> list[SearchHit]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, source_path, chunk_index, page_number, content,
                       1 - (embedding <=> %s::vector) AS score
                FROM rag_chunks
                WHERE workspace = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (vector_literal(query_embedding), namespace, vector_literal(query_embedding), top_k),
            ).fetchall()
        return [
            SearchHit(
                vector_id=row[0],
                source_path=row[1],
                chunk_index=row[2],
                page_number=row[3],
                text=row[4],
                score=float(row[5]) if row[5] is not None else None,
            )
            for row in rows
        ]

    def reset(self, namespace: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM rag_chunks WHERE workspace = %s", (namespace,))

    def doctor(self) -> tuple[bool, str]:
        try:
            with self._connect() as conn:
                ext = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone()
                if not ext:
                    return False, "Postgres is reachable but pgvector extension is not installed."
            return True, "Postgres/pgvector reachable."
        except Exception as exc:
            return False, f"Postgres check failed: {exc}"


class QdrantStore(BaseVectorStore):
    name = "qdrant"

    def __init__(self, config: EffectiveConfig):
        from qdrant_client import QdrantClient

        self.url = str(config.get("qdrant_url"))
        self.client = QdrantClient(url=self.url, timeout=3)

    def ensure_namespace(self, workspace: str, dimensions: int) -> str:
        from qdrant_client.models import Distance, VectorParams

        name = f"rag_{workspace}".replace("-", "_")
        collections = self.client.get_collections().collections
        if not any(collection.name == name for collection in collections):
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
            )
        return name

    def upsert(self, namespace: str, items: list[VectorItem]) -> None:
        if not items:
            return
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=item.vector_id,
                vector=item.embedding,
                payload={
                    "source_id": item.source_id,
                    "chunk_id": item.chunk_id,
                    "workspace": item.workspace,
                    "source_path": item.source_path,
                    "chunk_index": item.chunk_index,
                    "page_number": item.page_number,
                    "text": item.text,
                    "provider": item.provider,
                    "embedding_model": item.embedding_model,
                    "dimensions": item.dimensions,
                },
            )
            for item in items
        ]
        self.client.upsert(collection_name=namespace, points=points)

    def delete(self, namespace: str, vector_ids: list[str]) -> None:
        if not vector_ids:
            return
        from qdrant_client.models import PointIdsList

        self.client.delete(collection_name=namespace, points_selector=PointIdsList(points=vector_ids))

    def search(self, namespace: str, query_embedding: list[float], top_k: int) -> list[SearchHit]:
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=namespace,
                query=query_embedding,
                limit=top_k,
                with_payload=True,
            )
            rows = response.points
        else:  # qdrant-client versions before the universal query API.
            rows = self.client.search(collection_name=namespace, query_vector=query_embedding, limit=top_k)
        hits: list[SearchHit] = []
        for row in rows:
            payload = row.payload or {}
            hits.append(
                SearchHit(
                    vector_id=str(row.id),
                    score=float(row.score) if row.score is not None else None,
                    text=str(payload.get("text", "")),
                    source_path=str(payload.get("source_path", "")),
                    chunk_index=int(payload.get("chunk_index", 0)),
                    page_number=payload.get("page_number"),
                )
            )
        return hits

    def reset(self, namespace: str) -> None:
        try:
            self.client.delete_collection(collection_name=namespace)
        except Exception as exc:
            raise StorageError(f"Qdrant reset failed: {exc}") from exc

    def doctor(self) -> tuple[bool, str]:
        try:
            self.client.get_collections()
            return True, "Qdrant reachable."
        except Exception as exc:
            return False, f"Qdrant check failed: {exc}"


def store_from_config(config: EffectiveConfig) -> BaseVectorStore:
    if config.store == "pgvector":
        return PgvectorStore(config)
    if config.store == "qdrant":
        return QdrantStore(config)
    raise StorageError(f"Unsupported store: {config.store}")


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in vector) + "]"


def new_vector_id() -> str:
    return str(uuid.uuid4())
