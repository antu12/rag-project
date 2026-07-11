from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import shutil
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterator, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .config import ALLOWED_KEYS, ENV_KEYS, effective_config, load_dotenv, load_local_config, redacted_config, set_config_value
from .documents import SUPPORTED_EXTENSIONS
from .errors import RagError
from .inngest_payloads import INNGEST_DEV_SERVER_URL, build_ingest_event, build_ingest_event_payload
from .metadata import MetadataStore, normalize_workspace_name
from .operations import ask_question, citation_for, ingest_path, retrieve, source_matched
from .paths import PROJECT_DIR, RAG_DIR, UPLOADS_DIR, ensure_runtime_dirs
from .stores import store_from_config
from .web_repository import TERMINAL_JOB_STATUSES, WebRepository


API_PREFIX = "/api/v1"
MAX_UPLOAD_BYTES = int(os.getenv("RAG_WEB_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_UPLOAD_FILES = int(os.getenv("RAG_WEB_MAX_UPLOAD_FILES", "25"))
WEB_DIST = PROJECT_DIR / "web" / "dist"
SECRET_KEYS = {"openai": ["OPENAI_API_KEY"], "gemini": ["GOOGLE_API_KEY", "GEMINI_API_KEY"]}


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=63)


class ConfigPatch(BaseModel):
    values: dict[str, Any]


class SecretWrite(BaseModel):
    value: str = Field(min_length=1)
    alias: str | None = None


class IngestRequest(BaseModel):
    upload_ids: list[str] = Field(min_length=1)
    execution_mode: Literal["synchronous", "inngest"] = "synchronous"
    provider: Literal["openai", "gemini"] | None = None
    store: Literal["pgvector", "qdrant"] | None = None
    embedding_model: str | None = None
    generation_model: str | None = None
    chunk_size: int | None = Field(None, gt=0)
    chunk_overlap: int | None = Field(None, ge=0)
    force: bool = False

    @field_validator("chunk_overlap")
    @classmethod
    def overlap_is_valid(cls, value: int | None, info):
        size = info.data.get("chunk_size")
        if value is not None and size is not None and value >= size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return value


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000)
    provider: Literal["openai", "gemini"] | None = None
    store: Literal["pgvector", "qdrant"] | None = None
    embedding_model: str | None = None
    top_k: int | None = Field(None, gt=0, le=100)


class SessionCreate(BaseModel):
    workspace: str
    title: str = Field(default="New session", min_length=1, max_length=120)


class SessionPatch(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class TurnCreate(BaseModel):
    question: str = Field(min_length=1, max_length=20_000)
    provider: Literal["openai", "gemini"] | None = None
    store: Literal["pgvector", "qdrant"] | None = None
    embedding_model: str | None = None
    generation_model: str | None = None
    top_k: int | None = Field(None, gt=0, le=100)


class SuiteWrite(BaseModel):
    workspace: str
    name: str = Field(min_length=1, max_length=120)
    cases: list[dict[str, Any]] = Field(min_length=1)


class ResetRequest(BaseModel):
    store: Literal["pgvector", "qdrant"]
    confirmation: str
    delete_uploads: bool = False


def create_web_app() -> FastAPI:
    ensure_runtime_dirs()
    startup_repo = WebRepository()
    startup_repo.mark_abandoned_local_jobs_interrupted()
    startup_repo.close()
    api = FastAPI(title="RAG Learning Studio API", version="0.2.0")
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    register_error_handlers(api)
    register_routes(api)
    from .inngest_app import inngest, inngest_client, rag_ingest_requested

    inngest.fast_api.serve(api, inngest_client, [rag_ingest_requested])
    if WEB_DIST.exists():
        assets = WEB_DIST / "assets"
        if assets.exists():
            api.mount("/assets", StaticFiles(directory=assets), name="web-assets")

        @api.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            target = WEB_DIST / path
            if path and target.is_file():
                return FileResponse(target)
            return FileResponse(WEB_DIST / "index.html")
    return api


def register_error_handlers(api: FastAPI) -> None:
    @api.exception_handler(KeyError)
    def key_error(_: Request, exc: KeyError):
        return error_response(404, "not_found", str(exc).strip("'"))

    @api.exception_handler(RagError)
    def rag_error(_: Request, exc: RagError):
        return error_response(422, "rag_error", str(exc))

    @api.exception_handler(Exception)
    def unexpected(_: Request, exc: Exception):
        return error_response(500, "internal_error", "The local API encountered an unexpected error.", detail=str(exc))


def error_response(status: int, code: str, message: str, *, detail: str | None = None, action: str | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "retryable": status >= 500}}
    if detail and os.getenv("RAG_WEB_DEBUG") == "1":
        body["error"]["detail"] = detail
    if action:
        body["error"]["suggested_action"] = action
    return JSONResponse(status_code=status, content=body)


def register_routes(api: FastAPI) -> None:
    @api.get(f"{API_PREFIX}/health")
    def health():
        return {"status": "ok", "version": api.version}

    @api.get(f"{API_PREFIX}/bootstrap")
    def bootstrap():
        metadata = MetadataStore()
        try:
            workspaces = workspace_summaries(metadata)
            active = metadata.active_workspace()
        finally:
            metadata.close()
        cfg = effective_config()
        return {
            "version": api.version,
            "active_workspace": active,
            "workspaces": workspaces,
            "config": redacted_config(cfg.values),
            "secrets": secret_status(),
            "features": {"inngest": True, "conversation_memory": False, "authentication": False},
        }

    @api.get(f"{API_PREFIX}/workspaces")
    def workspaces():
        db = MetadataStore()
        try:
            return workspace_summaries(db)
        finally:
            db.close()

    @api.post(f"{API_PREFIX}/workspaces", status_code=201)
    def create_workspace(body: WorkspaceCreate):
        db = MetadataStore()
        try:
            workspace = db.create_workspace(body.name)
            if not db.active_workspace():
                db.set_active_workspace(workspace.name)
            return workspace.__dict__
        finally:
            db.close()

    @api.put(f"{API_PREFIX}/workspaces/{{workspace}}/active")
    def activate_workspace(workspace: str):
        db = MetadataStore()
        try:
            db.set_active_workspace(workspace)
            return {"active_workspace": workspace}
        finally:
            db.close()

    @api.post(f"{API_PREFIX}/workspaces/{{workspace}}/reset")
    def reset_workspace(workspace: str, body: ResetRequest):
        if body.confirmation != workspace:
            raise HTTPException(422, "Confirmation must exactly match the workspace name.")
        db = MetadataStore()
        try:
            db.get_workspace(workspace)
            cfg = effective_config({"store": body.store})
            namespace = db.namespace(workspace, body.store)
            if namespace:
                store_from_config(cfg).reset(str(namespace["namespace"]))
            db.reset_workspace_store(workspace, body.store)
        finally:
            db.close()
        deleted_uploads = 0
        if body.delete_uploads:
            repo = WebRepository()
            try:
                for item in repo.list_uploads(workspace):
                    safe_unlink(Path(item["stored_path"]), workspace)
                    repo.delete_upload(workspace, item["id"])
                    deleted_uploads += 1
            finally:
                repo.close()
        return {"workspace": workspace, "store": body.store, "deleted_uploads": deleted_uploads}

    @api.get(f"{API_PREFIX}/config")
    def get_config():
        cfg = effective_config()
        local = load_local_config()
        sources = config_sources()
        return {"effective": redacted_config(cfg.values), "local_overrides": redacted_config(local), "sources": sources, "editable_keys": sorted(ALLOWED_KEYS)}

    @api.patch(f"{API_PREFIX}/config")
    def patch_config(body: ConfigPatch):
        unknown = set(body.values) - ALLOWED_KEYS
        if unknown:
            raise HTTPException(422, f"Unknown configuration keys: {', '.join(sorted(unknown))}")
        for key, value in body.values.items():
            set_config_value(key, str(value))
        return get_config()

    @api.delete(f"{API_PREFIX}/config/{{key}}")
    def delete_config(key: str):
        if key not in ALLOWED_KEYS:
            raise HTTPException(404, "Unknown configuration key.")
        local = load_local_config()
        local.pop(key, None)
        from .config import save_local_config
        save_local_config(local)
        return get_config()

    @api.get(f"{API_PREFIX}/secrets/status")
    def get_secret_status():
        return secret_status()

    @api.put(f"{API_PREFIX}/secrets/{{provider}}")
    def put_secret(provider: str, body: SecretWrite, request: Request):
        require_local_request(request)
        key = secret_key_for(provider, body.alias)
        update_dotenv({key: body.value})
        os.environ[key] = body.value
        return secret_status()

    @api.delete(f"{API_PREFIX}/secrets/{{provider}}")
    def delete_secret(provider: str, request: Request, alias: str | None = None):
        require_local_request(request)
        key = secret_key_for(provider, alias)
        update_dotenv({key: None})
        os.environ.pop(key, None)
        return secret_status()

    @api.post(f"{API_PREFIX}/workspaces/{{workspace}}/uploads", status_code=201)
    async def upload_files(workspace: str, files: list[UploadFile] = File(...)):
        if len(files) > MAX_UPLOAD_FILES:
            raise HTTPException(413, f"At most {MAX_UPLOAD_FILES} files may be uploaded at once.")
        db = MetadataStore()
        try:
            db.get_workspace(workspace)
        finally:
            db.close()
        repo = WebRepository()
        results = []
        try:
            target_dir = (UPLOADS_DIR / normalize_workspace_name(workspace)).resolve()
            target_dir.mkdir(parents=True, exist_ok=True)
            for upload in files:
                original = Path(upload.filename or "").name
                suffix = Path(original).suffix.lower()
                if suffix not in SUPPORTED_EXTENSIONS:
                    results.append({"name": original, "status": "unsupported", "reason": f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"})
                    continue
                content = await upload.read(MAX_UPLOAD_BYTES + 1)
                if not content:
                    results.append({"name": original, "status": "failed", "reason": "File is empty."})
                    continue
                if len(content) > MAX_UPLOAD_BYTES:
                    results.append({"name": original, "status": "failed", "reason": f"File exceeds {MAX_UPLOAD_BYTES} bytes."})
                    continue
                digest = hashlib.sha256(content).hexdigest()
                stored = target_dir / f"{digest[:16]}-{_safe_filename(original)}"
                if not stored.exists():
                    stored.write_bytes(content)
                item = repo.add_upload(workspace, original, str(stored), suffix.lstrip("."), len(content), digest)
                item["status"] = "uploaded"
                results.append(item)
        finally:
            repo.close()
        return {"files": results}

    @api.get(f"{API_PREFIX}/workspaces/{{workspace}}/uploads")
    def list_uploads(workspace: str):
        repo = WebRepository()
        try:
            return repo.list_uploads(workspace)
        finally:
            repo.close()

    @api.delete(f"{API_PREFIX}/workspaces/{{workspace}}/uploads/{{upload_id}}")
    def delete_upload(workspace: str, upload_id: str):
        repo = WebRepository()
        try:
            item = repo.delete_upload(workspace, upload_id)
            safe_unlink(Path(item["stored_path"]), workspace)
            return {"deleted": upload_id}
        finally:
            repo.close()

    @api.get(f"{API_PREFIX}/workspaces/{{workspace}}/sources")
    def list_sources(workspace: str, store: str | None = None):
        db = MetadataStore()
        try:
            db.get_workspace(workspace)
            return [source.__dict__ for source in db.list_sources(workspace, store)]
        finally:
            db.close()

    @api.get(f"{API_PREFIX}/workspaces/{{workspace}}/sources/{{source_id}}")
    def source_detail(workspace: str, source_id: str):
        db = MetadataStore()
        try:
            source = next((item for item in db.list_sources(workspace) if item.id == source_id), None)
            if not source:
                raise KeyError("Source not found.")
            return source.__dict__
        finally:
            db.close()

    @api.get(f"{API_PREFIX}/workspaces/{{workspace}}/sources/{{source_id}}/chunks")
    def source_chunks(workspace: str, source_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
        repo = WebRepository()
        try:
            rows = repo.conn.execute("SELECT id,source_path,chunk_index,page_number,text,vector_id FROM chunks WHERE workspace=? AND source_id=? ORDER BY chunk_index LIMIT ? OFFSET ?", (workspace, source_id, limit, offset)).fetchall()
            total = repo.conn.execute("SELECT COUNT(*) AS n FROM chunks WHERE workspace=? AND source_id=?", (workspace, source_id)).fetchone()["n"]
            return {"items": [dict(row) for row in rows], "total": total, "offset": offset, "limit": limit}
        finally:
            repo.close()

    @api.delete(f"{API_PREFIX}/workspaces/{{workspace}}/sources/{{source_id}}")
    def delete_source(workspace: str, source_id: str, delete_file: bool = False):
        db = MetadataStore()
        repo = WebRepository()
        try:
            source = next((item for item in db.list_sources(workspace) if item.id == source_id), None)
            if not source:
                raise KeyError("Source not found.")
            namespace = db.namespace(workspace, source.store)
            vector_ids = db.delete_source(source_id)
            if namespace:
                store_from_config(effective_config({"store": source.store})).delete(str(namespace["namespace"]), vector_ids)
            deleted_file = False
            if delete_file:
                for item in repo.list_uploads(workspace):
                    if Path(item["stored_path"]).name.endswith(Path(source.source_path).name):
                        safe_unlink(Path(item["stored_path"]), workspace)
                        repo.delete_upload(workspace, item["id"])
                        deleted_file = True
            return {"deleted": source_id, "deleted_file": deleted_file}
        finally:
            db.close()
            repo.close()

    @api.post(f"{API_PREFIX}/workspaces/{{workspace}}/ingestions", status_code=202)
    def start_ingestion(workspace: str, body: IngestRequest):
        overrides = request_overrides(body)
        cfg = effective_config(overrides)
        repo = WebRepository()
        try:
            uploads = [repo.get_upload(workspace, item) for item in body.upload_ids]
            job = repo.create_job(workspace, "ingestion", body.execution_mode, {**cfg.values, "force": body.force, "upload_ids": body.upload_ids})
        finally:
            repo.close()
        target = run_sync_ingestion if body.execution_mode == "synchronous" else submit_inngest_ingestion
        threading.Thread(target=target, args=(job["id"], workspace, uploads, cfg.values, body.force), daemon=True).start()
        return job

    @api.get(f"{API_PREFIX}/jobs")
    def jobs(workspace: str | None = None, limit: int = Query(100, ge=1, le=500)):
        repo = WebRepository()
        try:
            return repo.list_jobs(workspace, limit)
        finally:
            repo.close()

    @api.get(f"{API_PREFIX}/jobs/{{job_id}}")
    def job(job_id: str):
        repo = WebRepository()
        try:
            result = repo.get_job(job_id)
            result["events"] = repo.list_events(job_id)
            return result
        finally:
            repo.close()

    @api.get(f"{API_PREFIX}/jobs/{{job_id}}/events")
    def job_events(job_id: str, after: int = Query(0, ge=0)):
        repo = WebRepository()
        try:
            repo.get_job(job_id)
            return repo.list_events(job_id, after)
        finally:
            repo.close()

    @api.get(f"{API_PREFIX}/jobs/{{job_id}}/stream")
    def job_stream(job_id: str, request: Request, after: int = Query(0, ge=0)):
        last_header = request.headers.get("last-event-id")
        cursor = int(last_header) if last_header and last_header.isdigit() else after
        return StreamingResponse(stream_events(job_id, cursor), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @api.post(f"{API_PREFIX}/workspaces/{{workspace}}/search")
    def search(workspace: str, body: SearchRequest):
        cfg = effective_config(request_overrides(body))
        messages: list[str] = []
        db = MetadataStore()
        try:
            hits = retrieve(body.query, workspace, cfg, db, progress=messages.append)
            return {"query": body.query, "progress": messages, "results": [hit_dict(hit) for hit in hits], "config": redacted_config(cfg.values)}
        finally:
            db.close()

    @api.get(f"{API_PREFIX}/chat/sessions")
    def sessions(workspace: str):
        repo = WebRepository()
        try:
            return repo.list_sessions(workspace)
        finally:
            repo.close()

    @api.post(f"{API_PREFIX}/chat/sessions", status_code=201)
    def create_session(body: SessionCreate):
        repo = WebRepository()
        try:
            return repo.create_session(body.workspace, body.title)
        finally:
            repo.close()

    @api.get(f"{API_PREFIX}/chat/sessions/{{session_id}}")
    def session(session_id: str, workspace: str):
        repo = WebRepository()
        try:
            return repo.get_session(session_id, workspace)
        finally:
            repo.close()

    @api.patch(f"{API_PREFIX}/chat/sessions/{{session_id}}")
    def rename_session(session_id: str, workspace: str, body: SessionPatch):
        repo = WebRepository()
        try:
            return repo.rename_session(workspace, session_id, body.title)
        finally:
            repo.close()

    @api.delete(f"{API_PREFIX}/chat/sessions/{{session_id}}")
    def delete_session(session_id: str, workspace: str):
        repo = WebRepository()
        try:
            repo.delete_session(workspace, session_id)
            return {"deleted": session_id}
        finally:
            repo.close()

    @api.post(f"{API_PREFIX}/chat/sessions/{{session_id}}/turns", status_code=202)
    def create_turn(session_id: str, body: TurnCreate):
        repo = WebRepository()
        try:
            session_data = repo.get_session(session_id)
            cfg = effective_config(request_overrides(body))
            turn = repo.create_turn(session_id, body.question, cfg.values)
            job = repo.create_job(session_data["workspace"], "ask", "synchronous", {**cfg.values, "turn_id": turn["id"]})
        finally:
            repo.close()
        threading.Thread(target=run_ask, args=(job["id"], turn["id"], session_data["workspace"], body.question, cfg.values), daemon=True).start()
        return {"turn": turn, "job": job}

    @api.get(f"{API_PREFIX}/eval/suites")
    def suites(workspace: str):
        repo = WebRepository()
        try:
            return repo.list_suites(workspace)
        finally:
            repo.close()

    @api.post(f"{API_PREFIX}/eval/suites", status_code=201)
    def save_suite(body: SuiteWrite):
        validate_cases(body.cases)
        repo = WebRepository()
        try:
            return repo.save_suite(body.workspace, body.name, body.cases)
        finally:
            repo.close()

    @api.delete(f"{API_PREFIX}/eval/suites/{{suite_id}}")
    def remove_suite(suite_id: str, workspace: str):
        repo = WebRepository()
        try:
            repo.delete_suite(workspace, suite_id)
            return {"deleted": suite_id}
        finally:
            repo.close()

    @api.post(f"{API_PREFIX}/eval/suites/{{suite_id}}/run", status_code=202)
    def run_suite(suite_id: str, workspace: str, body: SearchRequest | None = None):
        repo = WebRepository()
        try:
            suite = repo.get_suite(workspace, suite_id)
            cfg = effective_config(request_overrides(body) if body else {})
            job = repo.create_job(workspace, "evaluation", "synchronous", {**cfg.values, "suite_id": suite_id})
        finally:
            repo.close()
        threading.Thread(target=run_evaluation, args=(job["id"], workspace, suite, cfg.values), daemon=True).start()
        return job

    @api.post(f"{API_PREFIX}/doctor")
    def doctor():
        return run_doctor_checks()


def workspace_summaries(db: MetadataStore) -> list[dict[str, Any]]:
    active = db.active_workspace()
    result = []
    for workspace in db.list_workspaces():
        sources = db.list_sources(workspace.name)
        result.append({**workspace.__dict__, "active": workspace.name == active, "source_count": len(sources), "chunk_count": sum(item.chunk_count for item in sources), "last_ingested_at": max((item.ingested_at for item in sources), default=None)})
    return result


def request_overrides(body: Any) -> dict[str, Any]:
    if body is None:
        return {}
    data = body.model_dump(exclude_none=True)
    overrides = {key: data[key] for key in ("provider", "store", "top_k", "chunk_size", "chunk_overlap") if key in data}
    provider = data.get("provider") or effective_config(overrides).provider
    if data.get("embedding_model"):
        overrides[f"{provider}_embedding_model"] = data["embedding_model"]
    if data.get("generation_model"):
        overrides[f"{provider}_generation_model"] = data["generation_model"]
    return overrides


def run_sync_ingestion(job_id: str, workspace: str, uploads: list[dict[str, Any]], values: dict[str, Any], force: bool) -> None:
    repo, metadata = WebRepository(), MetadataStore()
    totals = {"added": 0, "updated": 0, "skipped": 0, "unsupported": 0, "failed": 0, "messages": []}
    try:
        repo.update_job(job_id, "running", current=0, total=len(uploads))
        repo.add_event(job_id, "validation", "running", "Validated workspace, configuration, and managed uploads.", current=0, total=len(uploads))
        cfg = effective_config(values)
        for index, upload in enumerate(uploads, 1):
            repo.add_event(job_id, "file", "running", f"Processing {upload['original_name']}", current=index - 1, total=len(uploads), metadata={"upload_id": upload["id"], "filename": upload["original_name"]})

            def progress(message: str) -> None:
                stage, status, extra = parse_progress(message)
                event_current = extra.pop("current", index - 1)
                event_total = extra.pop("total", len(uploads))
                repo.add_event(
                    job_id,
                    stage,
                    status,
                    message,
                    current=event_current,
                    total=event_total,
                    **extra,
                )

            summary = ingest_path(Path(upload["stored_path"]), workspace, cfg, metadata, force=force, progress=progress, root=Path(upload["stored_path"]).parent)
            for key in ("added", "updated", "skipped", "unsupported", "failed"):
                totals[key] += getattr(summary, key)
            totals["messages"].extend(summary.messages)
            repo.update_job(job_id, "running", current=index, total=len(uploads))
        status = "succeeded" if totals["failed"] == 0 else ("partially_succeeded" if totals["added"] + totals["updated"] + totals["skipped"] else "failed")
        repo.add_event(job_id, "summary", status, f"Ingestion finished: {totals['added']} added, {totals['updated']} updated, {totals['skipped']} skipped, {totals['failed']} failed.", current=len(uploads), total=len(uploads))
        repo.update_job(job_id, status, current=len(uploads), total=len(uploads), result=totals)
    except Exception as exc:
        repo.add_event(job_id, "failure", "failed", safe_error(exc))
        repo.update_job(job_id, "failed", error={"message": safe_error(exc), "retryable": True})
    finally:
        metadata.close()
        repo.close()


def submit_inngest_ingestion(job_id: str, workspace: str, uploads: list[dict[str, Any]], values: dict[str, Any], force: bool) -> None:
    repo = WebRepository()
    try:
        cfg = effective_config(values)
        repo.update_job(job_id, "running", current=0, total=len(uploads))
        repo.add_event(job_id, "inngest_submission", "running", "Submitting managed files to the local Inngest Dev Server.", total=len(uploads))
        for index, upload in enumerate(uploads, 1):
            event = build_ingest_event(build_ingest_event_payload(Path(upload["stored_path"]), workspace, cfg, force))
            event["data"]["web_job_id"] = job_id
            request = urllib.request.Request(f"{INNGEST_DEV_SERVER_URL}/e/local", data=json.dumps(event).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status >= 300:
                    raise RuntimeError(f"Inngest returned HTTP {response.status}")
            repo.add_event(job_id, "inngest_submission", "succeeded", f"Submitted {upload['original_name']} to Inngest.", current=index, total=len(uploads))
        repo.add_event(job_id, "inngest_tracking", "waiting", "Events submitted. Waiting for durable Inngest runs to complete.", current=len(uploads), total=len(uploads))
        repo.update_job(job_id, "waiting", current=len(uploads), total=len(uploads), result={"submitted": len(uploads), "dev_server_url": INNGEST_DEV_SERVER_URL})
    except Exception as exc:
        repo.add_event(job_id, "inngest_submission", "failed", safe_error(exc))
        repo.update_job(job_id, "failed", error={"message": safe_error(exc), "retryable": True})
    finally:
        repo.close()


def run_ask(job_id: str, turn_id: str, workspace: str, question: str, values: dict[str, Any]) -> None:
    repo, metadata = WebRepository(), MetadataStore()
    try:
        cfg = effective_config(values)
        repo.update_job(job_id, "running")

        def progress(message: str) -> None:
            stage, status, extra = parse_progress(message)
            repo.add_event(job_id, stage, status, message, **extra)

        answer, hits, usage, _context = ask_question(question, workspace, cfg, metadata, progress=progress)
        citations = [citation_for(hit) for hit in hits]
        hit_data = [hit_dict(hit) for hit in hits]
        repo.finish_turn(turn_id, answer=answer, citations=citations, hits=hit_data, usage=usage)
        repo.add_event(job_id, "answer", "succeeded", "Grounded answer completed.")
        repo.update_job(job_id, "succeeded", result={"turn_id": turn_id, "citations": citations, "usage": usage})
    except Exception as exc:
        error = {"message": safe_error(exc), "retryable": True}
        repo.finish_turn(turn_id, error=error)
        repo.add_event(job_id, "failure", "failed", error["message"])
        repo.update_job(job_id, "failed", error=error)
    finally:
        metadata.close()
        repo.close()


def run_evaluation(job_id: str, workspace: str, suite: dict[str, Any], values: dict[str, Any]) -> None:
    repo, metadata = WebRepository(), MetadataStore()
    results = []
    try:
        cfg = effective_config(values)
        cases = suite["cases"]
        repo.update_job(job_id, "running", current=0, total=len(cases))
        for index, case in enumerate(cases, 1):
            repo.add_event(job_id, "evaluation_case", "running", f"Retrieving case {index}/{len(cases)}.", current=index - 1, total=len(cases))
            hits = retrieve(case["question"], workspace, cfg, metadata)
            actual = [hit.source_path for hit in hits]
            expected = case["expected_sources"]
            passed = all(any(source_matched(item, wanted) for item in actual) for wanted in expected)
            results.append({"question": case["question"], "expected_sources": expected, "retrieved_sources": actual, "passed": passed, "hits": [hit_dict(hit) for hit in hits]})
            repo.update_job(job_id, "running", current=index, total=len(cases))
        score = sum(1 for item in results if item["passed"]) / len(results)
        result = {"suite_id": suite["id"], "score": score, "passed": sum(1 for item in results if item["passed"]), "total": len(results), "cases": results}
        repo.add_event(job_id, "summary", "succeeded", f"Evaluation completed with {score:.0%} retrieval accuracy.", current=len(results), total=len(results))
        repo.update_job(job_id, "succeeded", result=result)
    except Exception as exc:
        repo.add_event(job_id, "failure", "failed", safe_error(exc))
        repo.update_job(job_id, "failed", error={"message": safe_error(exc), "retryable": True})
    finally:
        metadata.close()
        repo.close()


def stream_events(job_id: str, after: int) -> Iterator[str]:
    cursor = after
    idle = 0
    while idle < 120:
        repo = WebRepository()
        try:
            job = repo.get_job(job_id)
            events = repo.list_events(job_id, cursor)
        finally:
            repo.close()
        if events:
            idle = 0
            for event in events:
                cursor = event["sequence"]
                yield f"id: {cursor}\nevent: job-event\ndata: {json.dumps(event)}\n\n"
        else:
            idle += 1
            yield ": keep-alive\n\n"
        if job["status"] in TERMINAL_JOB_STATUSES and not events:
            break
        time.sleep(0.5)


def parse_progress(message: str) -> tuple[str, str, dict[str, Any]]:
    lower = message.lower()
    stage = "progress"
    for marker, name in (("loading", "loading"), ("chunking", "chunking"), ("embedding", "embedding"), ("waiting", "provider_wait"), ("retry", "provider_retry"), ("storing", "vector_storage"), ("skipping", "hash_check"), ("generating", "generation"), ("searching", "vector_search"), ("building prompt", "prompt_context")):
        if marker in lower:
            stage = name
            break
    status = "retrying" if "retry " in lower or "retryable" in lower else ("waiting" if "waiting " in lower else "running")
    extra: dict[str, Any] = {}
    chunk = re.search(r"chunk (\d+)/(\d+)", lower)
    if chunk:
        extra.update(current=int(chunk.group(1)), total=int(chunk.group(2)))
    wait = re.search(r"waiting ([0-9.]+)s", lower)
    if wait:
        extra["wait_seconds"] = float(wait.group(1))
    retry = re.search(r"retry (\d+)/(\d+)", lower)
    if retry:
        extra.update(retry_attempt=int(retry.group(1)), retry_limit=int(retry.group(2)))
    return stage, status, extra


def run_doctor_checks() -> dict[str, Any]:
    checks = []
    started = time.perf_counter()
    db = MetadataStore()
    try:
        checks.append({"name": "SQLite metadata", "status": "ok", "details": f"Ready at {db.path}", "required": True})
    finally:
        db.close()
    cfg = effective_config()
    for provider, status in secret_status().items():
        required = provider == cfg.provider
        checks.append({"name": f"{provider.title()} API key", "status": "ok" if status["configured"] else ("fail" if required else "warning"), "details": status["source"] if status["configured"] else "Not configured", "required": required})
    for store_name in ("pgvector", "qdrant"):
        try:
            ok, details = store_from_config(effective_config({"store": store_name})).doctor()
        except Exception as exc:
            ok, details = False, safe_error(exc)
        checks.append({"name": store_name, "status": "ok" if ok else ("fail" if store_name == cfg.store else "warning"), "details": details, "required": store_name == cfg.store})
    return {"status": "ok" if not any(item["status"] == "fail" for item in checks) else "degraded", "duration_ms": round((time.perf_counter() - started) * 1000), "checks": checks, "commands": {"windows": "docker compose up -d", "linux_wsl": "docker compose up -d"}}


def config_sources() -> dict[str, str]:
    local = load_local_config()
    sources = {}
    for key in ALLOWED_KEYS:
        env_key = ENV_KEYS.get(key)
        if env_key and env_key in os.environ and os.environ[env_key] != "":
            sources[key] = "shell-or-dotenv"
        elif key in local:
            sources[key] = "local-config"
        else:
            sources[key] = "built-in-default"
    return sources


def secret_status() -> dict[str, Any]:
    load_dotenv()
    return {
        provider: {"configured": any(bool(os.getenv(key)) for key in keys), "source": "environment-or-dotenv" if any(bool(os.getenv(key)) for key in keys) else "missing", "aliases": [key for key in keys if os.getenv(key)]}
        for provider, keys in SECRET_KEYS.items()
    }


def secret_key_for(provider: str, alias: str | None) -> str:
    if provider not in SECRET_KEYS:
        raise HTTPException(404, "Unknown provider.")
    if alias:
        if alias not in SECRET_KEYS[provider]:
            raise HTTPException(422, "Unsupported secret alias.")
        return alias
    return SECRET_KEYS[provider][0]


def update_dotenv(changes: dict[str, str | None]) -> None:
    env_path = PROJECT_DIR / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    remaining = dict(changes)
    output = []
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in remaining:
                value = remaining.pop(key)
                if value is not None:
                    output.append(f"{key}={value}")
                continue
        output.append(line)
    for key, value in remaining.items():
        if value is not None:
            output.append(f"{key}={value}")
    temporary = env_path.with_suffix(".env.tmp")
    temporary.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    temporary.replace(env_path)


def require_local_request(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(403, "Secret changes are allowed only from the local machine.")


def validate_cases(cases: list[dict[str, Any]]) -> None:
    for index, case in enumerate(cases, 1):
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise HTTPException(422, f"Evaluation case {index} requires a question.")
        expected = case.get("expected_sources")
        if not isinstance(expected, list) or not expected or not all(isinstance(item, str) and item for item in expected):
            raise HTTPException(422, f"Evaluation case {index} requires expected_sources.")


def hit_dict(hit: Any) -> dict[str, Any]:
    return {"vector_id": hit.vector_id, "score": hit.score, "text": hit.text, "source_path": hit.source_path, "chunk_index": hit.chunk_index, "page_number": hit.page_number, "citation": citation_for(hit)}


def safe_error(exc: Exception) -> str:
    text = str(exc)
    text = re.sub(r"(?i)(api[_-]?key|authorization|token|password)\s*[=:]\s*\S+", r"\1=<redacted>", text)
    return text[:1000]


def safe_unlink(path: Path, workspace: str) -> None:
    root = (UPLOADS_DIR / normalize_workspace_name(workspace)).resolve()
    resolved = path.resolve()
    if root not in resolved.parents:
        raise HTTPException(400, "Managed upload path escaped its workspace.")
    resolved.unlink(missing_ok=True)


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name).strip(".-")
    return cleaned[:120] or "document"


app = create_web_app()
