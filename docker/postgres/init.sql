CREATE EXTENSION IF NOT EXISTS vector;

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
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_workspace ON rag_chunks(workspace);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_source_id ON rag_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding ON rag_chunks USING hnsw (embedding vector_cosine_ops);
