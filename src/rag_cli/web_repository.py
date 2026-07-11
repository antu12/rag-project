from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from .metadata import now_iso
from .paths import SQLITE_PATH, ensure_runtime_dirs


TERMINAL_JOB_STATUSES = {"succeeded", "partially_succeeded", "failed", "cancelled", "interrupted"}


class WebRepository:
    def __init__(self, path: Path = SQLITE_PATH):
        ensure_runtime_dirs()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.migrate()

    def close(self) -> None:
        self.conn.close()

    def migrate(self) -> None:
        self.conn.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS web_uploads (
              id TEXT PRIMARY KEY, workspace TEXT NOT NULL, original_name TEXT NOT NULL,
              stored_path TEXT NOT NULL, file_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
              file_hash TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS web_jobs (
              id TEXT PRIMARY KEY, workspace TEXT NOT NULL, operation TEXT NOT NULL,
              execution_mode TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
              started_at TEXT, completed_at TEXT, progress_current INTEGER NOT NULL DEFAULT 0,
              progress_total INTEGER NOT NULL DEFAULT 0, config_json TEXT NOT NULL,
              result_json TEXT, error_json TEXT, inngest_run_id TEXT
            );
            CREATE TABLE IF NOT EXISTS web_job_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, sequence INTEGER NOT NULL,
              created_at TEXT NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL,
              message TEXT NOT NULL, current INTEGER, total INTEGER, retry_attempt INTEGER,
              retry_limit INTEGER, wait_seconds REAL, metadata_json TEXT NOT NULL DEFAULT '{}',
              UNIQUE(job_id, sequence), FOREIGN KEY(job_id) REFERENCES web_jobs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS web_chat_sessions (
              id TEXT PRIMARY KEY, workspace TEXT NOT NULL, title TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS web_chat_turns (
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, question TEXT NOT NULL,
              answer TEXT, status TEXT NOT NULL, citations_json TEXT NOT NULL DEFAULT '[]',
              hits_json TEXT NOT NULL DEFAULT '[]', config_json TEXT NOT NULL DEFAULT '{}',
              usage_json TEXT, error_json TEXT, created_at TEXT NOT NULL, completed_at TEXT,
              FOREIGN KEY(session_id) REFERENCES web_chat_sessions(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS web_eval_suites (
              id TEXT PRIMARY KEY, workspace TEXT NOT NULL, name TEXT NOT NULL,
              cases_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS web_eval_runs (
              id TEXT PRIMARY KEY, suite_id TEXT NOT NULL, workspace TEXT NOT NULL,
              status TEXT NOT NULL, config_json TEXT NOT NULL, results_json TEXT,
              score REAL, created_at TEXT NOT NULL, completed_at TEXT,
              FOREIGN KEY(suite_id) REFERENCES web_eval_suites(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_web_jobs_workspace ON web_jobs(workspace, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_web_events_job ON web_job_events(job_id, sequence);
            CREATE INDEX IF NOT EXISTS idx_web_chat_workspace ON web_chat_sessions(workspace, updated_at DESC);
            """
        )
        self.conn.commit()

    def mark_abandoned_local_jobs_interrupted(self) -> None:
        self.conn.execute(
            "UPDATE web_jobs SET status='interrupted', completed_at=? WHERE execution_mode='synchronous' AND status NOT IN ('succeeded','partially_succeeded','failed','cancelled','interrupted')",
            (now_iso(),),
        )
        self.conn.commit()

    def add_upload(self, workspace: str, original_name: str, stored_path: str, file_type: str, size: int, file_hash: str) -> dict[str, Any]:
        upload_id = str(uuid.uuid4())
        created = now_iso()
        self.conn.execute(
            "INSERT INTO web_uploads VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (upload_id, workspace, original_name, stored_path, file_type, size, file_hash, created),
        )
        self.conn.commit()
        return self.get_upload(workspace, upload_id)

    def get_upload(self, workspace: str, upload_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM web_uploads WHERE workspace=? AND id=?", (workspace, upload_id)).fetchone()
        if not row:
            raise KeyError("Managed upload not found.")
        return dict(row)

    def list_uploads(self, workspace: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.conn.execute("SELECT * FROM web_uploads WHERE workspace=? ORDER BY created_at DESC", (workspace,))]

    def delete_upload(self, workspace: str, upload_id: str) -> dict[str, Any]:
        item = self.get_upload(workspace, upload_id)
        self.conn.execute("DELETE FROM web_uploads WHERE workspace=? AND id=?", (workspace, upload_id))
        self.conn.commit()
        return item

    def create_job(self, workspace: str, operation: str, mode: str, config: dict[str, Any]) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO web_jobs (id,workspace,operation,execution_mode,status,created_at,config_json) VALUES (?,?,?,?,?,?,?)",
            (job_id, workspace, operation, mode, "queued", now_iso(), json.dumps(config)),
        )
        self.conn.commit()
        self.add_event(job_id, "queued", "queued", "Job queued.")
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM web_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise KeyError("Job not found.")
        return _decode_row(row, {"config_json": "config", "result_json": "result", "error_json": "error"})

    def list_jobs(self, workspace: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if workspace:
            rows = self.conn.execute("SELECT * FROM web_jobs WHERE workspace=? ORDER BY created_at DESC LIMIT ?", (workspace, limit))
        else:
            rows = self.conn.execute("SELECT * FROM web_jobs ORDER BY created_at DESC LIMIT ?", (limit,))
        return [_decode_row(row, {"config_json": "config", "result_json": "result", "error_json": "error"}) for row in rows]

    def update_job(self, job_id: str, status: str, *, current: int | None = None, total: int | None = None, result: Any = None, error: Any = None) -> None:
        existing = self.get_job(job_id)
        if existing["status"] in TERMINAL_JOB_STATUSES:
            return
        started = existing["started_at"] or (now_iso() if status not in {"queued"} else None)
        completed = now_iso() if status in TERMINAL_JOB_STATUSES else None
        self.conn.execute(
            "UPDATE web_jobs SET status=?,started_at=?,completed_at=?,progress_current=COALESCE(?,progress_current),progress_total=COALESCE(?,progress_total),result_json=COALESCE(?,result_json),error_json=COALESCE(?,error_json) WHERE id=?",
            (status, started, completed, current, total, json.dumps(result) if result is not None else None, json.dumps(error) if error is not None else None, job_id),
        )
        self.conn.commit()

    def add_event(self, job_id: str, stage: str, status: str, message: str, *, current: int | None = None, total: int | None = None, retry_attempt: int | None = None, retry_limit: int | None = None, wait_seconds: float | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        row = self.conn.execute("SELECT COALESCE(MAX(sequence),0)+1 AS seq FROM web_job_events WHERE job_id=?", (job_id,)).fetchone()
        sequence = int(row["seq"])
        self.conn.execute(
            "INSERT INTO web_job_events (job_id,sequence,created_at,stage,status,message,current,total,retry_attempt,retry_limit,wait_seconds,metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, sequence, now_iso(), stage, status, message, current, total, retry_attempt, retry_limit, wait_seconds, json.dumps(metadata or {})),
        )
        self.conn.commit()
        return self.list_events(job_id, sequence - 1)[0]

    def list_events(self, job_id: str, after: int = 0) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM web_job_events WHERE job_id=? AND sequence>? ORDER BY sequence", (job_id, after))
        return [_decode_row(row, {"metadata_json": "metadata"}) for row in rows]

    def create_session(self, workspace: str, title: str = "New session") -> dict[str, Any]:
        session_id, created = str(uuid.uuid4()), now_iso()
        self.conn.execute("INSERT INTO web_chat_sessions VALUES (?,?,?,?,?)", (session_id, workspace, title, created, created))
        self.conn.commit()
        return self.get_session(session_id, workspace)

    def get_session(self, session_id: str, workspace: str | None = None) -> dict[str, Any]:
        query, args = "SELECT * FROM web_chat_sessions WHERE id=?", [session_id]
        if workspace:
            query, args = query + " AND workspace=?", [session_id, workspace]
        row = self.conn.execute(query, args).fetchone()
        if not row:
            raise KeyError("Chat session not found.")
        data = dict(row)
        data["turns"] = self.list_turns(session_id)
        return data

    def list_sessions(self, workspace: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM web_chat_sessions WHERE workspace=? ORDER BY updated_at DESC", (workspace,))
        return [dict(row) for row in rows]

    def rename_session(self, workspace: str, session_id: str, title: str) -> dict[str, Any]:
        self.get_session(session_id, workspace)
        self.conn.execute("UPDATE web_chat_sessions SET title=?,updated_at=? WHERE id=?", (title, now_iso(), session_id))
        self.conn.commit()
        return self.get_session(session_id, workspace)

    def delete_session(self, workspace: str, session_id: str) -> None:
        self.get_session(session_id, workspace)
        self.conn.execute("DELETE FROM web_chat_sessions WHERE id=?", (session_id,))
        self.conn.commit()

    def create_turn(self, session_id: str, question: str, config: dict[str, Any]) -> dict[str, Any]:
        turn_id = str(uuid.uuid4())
        self.conn.execute("INSERT INTO web_chat_turns (id,session_id,question,status,config_json,created_at) VALUES (?,?,?,?,?,?)", (turn_id, session_id, question, "running", json.dumps(config), now_iso()))
        self.conn.execute("UPDATE web_chat_sessions SET updated_at=? WHERE id=?", (now_iso(), session_id))
        self.conn.commit()
        return self.get_turn(turn_id)

    def finish_turn(self, turn_id: str, *, answer: str | None = None, citations: list[Any] | None = None, hits: list[Any] | None = None, usage: Any = None, error: Any = None) -> dict[str, Any]:
        status = "failed" if error else "succeeded"
        self.conn.execute("UPDATE web_chat_turns SET answer=?,status=?,citations_json=?,hits_json=?,usage_json=?,error_json=?,completed_at=? WHERE id=?", (answer, status, json.dumps(citations or []), json.dumps(hits or []), json.dumps(usage) if usage else None, json.dumps(error) if error else None, now_iso(), turn_id))
        self.conn.commit()
        return self.get_turn(turn_id)

    def get_turn(self, turn_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM web_chat_turns WHERE id=?", (turn_id,)).fetchone()
        if not row:
            raise KeyError("Chat turn not found.")
        return _decode_row(row, {"citations_json": "citations", "hits_json": "hits", "config_json": "config", "usage_json": "usage", "error_json": "error"})

    def list_turns(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM web_chat_turns WHERE session_id=? ORDER BY created_at", (session_id,))
        return [_decode_row(row, {"citations_json": "citations", "hits_json": "hits", "config_json": "config", "usage_json": "usage", "error_json": "error"}) for row in rows]

    def save_suite(self, workspace: str, name: str, cases: list[dict[str, Any]], suite_id: str | None = None) -> dict[str, Any]:
        now, suite_id = now_iso(), suite_id or str(uuid.uuid4())
        existing = self.conn.execute("SELECT created_at FROM web_eval_suites WHERE id=? AND workspace=?", (suite_id, workspace)).fetchone()
        created = existing["created_at"] if existing else now
        self.conn.execute("INSERT OR REPLACE INTO web_eval_suites VALUES (?,?,?,?,?,?)", (suite_id, workspace, name, json.dumps(cases), created, now))
        self.conn.commit()
        return self.get_suite(workspace, suite_id)

    def get_suite(self, workspace: str, suite_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM web_eval_suites WHERE workspace=? AND id=?", (workspace, suite_id)).fetchone()
        if not row:
            raise KeyError("Evaluation suite not found.")
        return _decode_row(row, {"cases_json": "cases"})

    def list_suites(self, workspace: str) -> list[dict[str, Any]]:
        return [_decode_row(row, {"cases_json": "cases"}) for row in self.conn.execute("SELECT * FROM web_eval_suites WHERE workspace=? ORDER BY updated_at DESC", (workspace,))]

    def delete_suite(self, workspace: str, suite_id: str) -> None:
        self.get_suite(workspace, suite_id)
        self.conn.execute("DELETE FROM web_eval_suites WHERE id=?", (suite_id,))
        self.conn.commit()


def _decode_row(row: sqlite3.Row, mappings: dict[str, str]) -> dict[str, Any]:
    data = dict(row)
    for source, target in mappings.items():
        value = data.pop(source, None)
        data[target] = json.loads(value) if value else None
    return data
