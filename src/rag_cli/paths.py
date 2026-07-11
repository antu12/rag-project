from pathlib import Path


PROJECT_DIR = Path.cwd()
RAG_DIR = PROJECT_DIR / ".rag"
CONFIG_PATH = RAG_DIR / "config.json"
SQLITE_PATH = RAG_DIR / "metadata.sqlite3"
UPLOADS_DIR = RAG_DIR / "uploads"


def ensure_runtime_dirs() -> None:
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
