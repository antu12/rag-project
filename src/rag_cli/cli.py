from __future__ import annotations

from pathlib import Path
from typing import Optional
import importlib.util
import json
import os
import urllib.error
import urllib.request

import typer
from rich.console import Console
from rich.table import Table

from .config import effective_config, redacted_config, save_local_config, set_config_value
from .errors import RagError
from .inngest_payloads import (
    INGEST_APP_SERVER_URL,
    INNGEST_DEV_SERVER_URL,
    INNGEST_ENDPOINT_PATH,
    assert_secret_safe_event,
    build_ingest_event,
    build_ingest_event_payload,
)
from .metadata import MetadataStore
from .operations import ask_question, citation_for, ingest_path, load_eval_file, retrieve, source_matched
from .paths import CONFIG_PATH, RAG_DIR, ensure_runtime_dirs
from .stores import store_from_config


app = typer.Typer(help="Command-line RAG learning project.")
workspace_app = typer.Typer(help="Manage isolated RAG workspaces.")
config_app = typer.Typer(help="Manage non-secret local configuration.")
app.add_typer(workspace_app, name="workspace")
app.add_typer(config_app, name="config")
console = Console()


def fail(exc: Exception) -> None:
    console.print(f"[red]Error:[/red] {exc}")
    raise typer.Exit(code=1)


def common_overrides(
    provider: str | None = None,
    store: str | None = None,
    embedding_model: str | None = None,
    generation_model: str | None = None,
    top_k: int | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> dict:
    overrides = {
        "provider": provider,
        "store": store,
        "top_k": top_k,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
    }
    if provider and embedding_model:
        overrides[f"{provider}_embedding_model"] = embedding_model
    if provider and generation_model:
        overrides[f"{provider}_generation_model"] = generation_model
    if not provider and embedding_model:
        overrides["openai_embedding_model"] = embedding_model
        overrides["gemini_embedding_model"] = embedding_model
    if not provider and generation_model:
        overrides["openai_generation_model"] = generation_model
        overrides["gemini_generation_model"] = generation_model
    return {key: value for key, value in overrides.items() if value is not None}


def metadata() -> MetadataStore:
    return MetadataStore()


def resolve_workspace(db: MetadataStore, requested: str | None, no_interactive: bool) -> str:
    if requested or no_interactive:
        return db.resolve_workspace(requested, no_interactive=no_interactive)
    active = db.active_workspace()
    if active:
        return db.get_workspace(active).name
    workspaces = db.list_workspaces()
    if not workspaces:
        raise RagError("No workspace exists. Run 'rag workspace create <name>' first.")
    choices = [workspace.name for workspace in workspaces]
    console.print("No active workspace is set.")
    for index, name in enumerate(choices, start=1):
        console.print(f"{index}. {name}")
    selected = typer.prompt("Choose a workspace number or name")
    if selected.isdigit() and 1 <= int(selected) <= len(choices):
        return choices[int(selected) - 1]
    return db.get_workspace(selected).name


@app.command()
def init() -> None:
    """Create local runtime directories and example config."""
    try:
        ensure_runtime_dirs()
        if not CONFIG_PATH.exists():
            save_local_config({})
        console.print(f"Initialized {RAG_DIR}")
        console.print("Use .env.example for environment variable names. Do not store secrets in config.")
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@config_app.command("show")
def config_show() -> None:
    try:
        cfg = effective_config()
        table = Table(title="Effective Configuration")
        table.add_column("Key")
        table.add_column("Value")
        for key, value in redacted_config(cfg.values).items():
            table.add_row(key, str(value))
        console.print(table)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    try:
        set_config_value(key, value)
        console.print(f"Saved {key}.")
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@workspace_app.command("create")
def workspace_create(name: str) -> None:
    try:
        db = metadata()
        workspace = db.create_workspace(name)
        if not db.active_workspace():
            db.set_active_workspace(workspace.name)
        console.print(f"Created workspace: {workspace.name}")
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@workspace_app.command("list")
def workspace_list() -> None:
    try:
        db = metadata()
        active = db.active_workspace()
        table = Table(title="Workspaces")
        table.add_column("Active")
        table.add_column("Name")
        table.add_column("Created")
        for workspace in db.list_workspaces():
            table.add_row("*" if workspace.name == active else "", workspace.name, workspace.created_at)
        console.print(table)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@workspace_app.command("use")
def workspace_use(name: str) -> None:
    try:
        db = metadata()
        db.set_active_workspace(name)
        console.print(f"Active workspace: {name}")
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@workspace_app.command("current")
def workspace_current() -> None:
    try:
        active = metadata().active_workspace()
        if not active:
            raise RagError("No active workspace.")
        console.print(active)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@app.command()
def ingest(
    path: Path,
    provider: Optional[str] = typer.Option(None),
    store: Optional[str] = typer.Option(None),
    workspace: Optional[str] = typer.Option(None),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
    generation_model: Optional[str] = typer.Option(None, "--generation-model"),
    chunk_size: Optional[int] = typer.Option(None, "--chunk-size"),
    chunk_overlap: Optional[int] = typer.Option(None, "--chunk-overlap"),
    force: bool = typer.Option(False, "--force"),
    no_interactive: bool = typer.Option(False, "--no-interactive"),
) -> None:
    try:
        cfg = effective_config(common_overrides(provider, store, embedding_model, generation_model, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
        db = metadata()
        ws = resolve_workspace(db, workspace, no_interactive)
        summary = ingest_path(path, ws, cfg, db, force=force, progress=lambda message: console.print(f"[cyan]...[/cyan] {message}"))
        console.print(
            f"Added: {summary.added} Updated: {summary.updated} Skipped: {summary.skipped} "
            f"Unsupported: {summary.unsupported} Failed: {summary.failed}"
        )
        for message in summary.messages:
            console.print(message)
        if summary.failed:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@app.command("ingest-server")
def ingest_server(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Start the local FastAPI app that serves the Inngest endpoint."""
    try:
        console.print(f"Starting RAG Inngest app server at http://{host}:{port}{INNGEST_ENDPOINT_PATH}")
        console.print(f"Open Inngest Dev Server at {INNGEST_DEV_SERVER_URL} after it is running.")
        import uvicorn

        uvicorn.run("rag_cli.inngest_app:app", host=host, port=port, reload=reload)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@app.command("ingest-async")
def ingest_async(
    path: Path,
    provider: Optional[str] = typer.Option(None),
    store: Optional[str] = typer.Option(None),
    workspace: Optional[str] = typer.Option(None),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
    generation_model: Optional[str] = typer.Option(None, "--generation-model"),
    chunk_size: Optional[int] = typer.Option(None, "--chunk-size"),
    chunk_overlap: Optional[int] = typer.Option(None, "--chunk-overlap"),
    force: bool = typer.Option(False, "--force"),
    no_interactive: bool = typer.Option(False, "--no-interactive"),
    dev_server_url: str = typer.Option(INNGEST_DEV_SERVER_URL, "--dev-server-url"),
    event_key: str = typer.Option("local", "--event-key"),
) -> None:
    """Submit an ingest job to the local Inngest Dev Server."""
    try:
        if not path.exists():
            raise RagError(f"Path does not exist: {path}")
        cfg = effective_config(
            common_overrides(
                provider,
                store,
                embedding_model,
                generation_model,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        )
        db = metadata()
        ws = resolve_workspace(db, workspace, no_interactive)
        payload = build_ingest_event_payload(path, ws, cfg, force)
        event = build_ingest_event(payload)
        assert_secret_safe_event(event)
        _post_inngest_event(dev_server_url, event_key, event)
        console.print(f"Submitted async ingest job for workspace '{ws}'.")
        console.print(f"Inngest Dev Server UI: {dev_server_url}")
        console.print(f"RAG Inngest app endpoint should be running at {INGEST_APP_SERVER_URL}{INNGEST_ENDPOINT_PATH}")
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@app.command("inngest-doctor")
def inngest_doctor(
    app_server_url: str = typer.Option(INGEST_APP_SERVER_URL, "--app-server-url"),
    dev_server_url: str = typer.Option(INNGEST_DEV_SERVER_URL, "--dev-server-url"),
) -> None:
    """Check optional local Inngest setup."""
    try:
        table = Table(title="Inngest Doctor")
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Details")
        failed = False
        for name, url in [
            ("RAG Inngest app endpoint", f"{app_server_url}{INNGEST_ENDPOINT_PATH}"),
            ("Inngest Dev Server", dev_server_url),
        ]:
            ok, details = _http_check(url)
            failed = failed or not ok
            table.add_row(name, "ok" if ok else "fail", details)
        console.print(table)
        if failed:
            console.print("Start the app server with: rag ingest-server")
            console.print("Start the Inngest Dev Server with Docker or: inngest dev -u http://localhost:8000/api/inngest")
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@app.command()
def search(
    query: str,
    provider: Optional[str] = typer.Option(None),
    store: Optional[str] = typer.Option(None),
    workspace: Optional[str] = typer.Option(None),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
    top_k: Optional[int] = typer.Option(None, "--top-k"),
    debug: bool = typer.Option(False, "--debug"),
    no_interactive: bool = typer.Option(False, "--no-interactive"),
) -> None:
    try:
        cfg = effective_config(common_overrides(provider, store, embedding_model, top_k=top_k))
        db = metadata()
        ws = resolve_workspace(db, workspace, no_interactive)
        hits = retrieve(query, ws, cfg, db, progress=lambda message: console.print(f"[cyan]...[/cyan] {message}"))
        if not hits:
            console.print("No relevant chunks were found.")
            return
        print_hits(hits, debug=debug)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@app.command()
def ask(
    question: str,
    provider: Optional[str] = typer.Option(None),
    store: Optional[str] = typer.Option(None),
    workspace: Optional[str] = typer.Option(None),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
    generation_model: Optional[str] = typer.Option(None, "--generation-model"),
    top_k: Optional[int] = typer.Option(None, "--top-k"),
    debug: bool = typer.Option(False, "--debug"),
    no_interactive: bool = typer.Option(False, "--no-interactive"),
) -> None:
    try:
        cfg = effective_config(common_overrides(provider, store, embedding_model, generation_model, top_k=top_k))
        db = metadata()
        ws = resolve_workspace(db, workspace, no_interactive)
        answer, hits, usage, context = ask_question(
            question,
            ws,
            cfg,
            db,
            progress=lambda message: console.print(f"[cyan]...[/cyan] {message}"),
        )
        console.print("[bold]Answer[/bold]")
        console.print(answer)
        if hits:
            console.print("\n[bold]Sources[/bold]")
            for index, hit in enumerate(hits, start=1):
                console.print(f"[{index}] {citation_for(hit)}")
        if debug:
            console.print("\n[bold]Debug[/bold]")
            console.print(f"provider={cfg.provider} store={cfg.store} embedding_model={cfg.embedding_model} generation_model={cfg.generation_model}")
            if usage:
                console.print(f"token_usage={usage}")
            console.print("Prompt context preview:")
            console.print(context[:2000])
            print_hits(hits, debug=True)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@app.command()
def sources(
    store: Optional[str] = typer.Option(None),
    workspace: Optional[str] = typer.Option(None),
    no_interactive: bool = typer.Option(False, "--no-interactive"),
) -> None:
    try:
        cfg = effective_config(common_overrides(store=store))
        db = metadata()
        ws = resolve_workspace(db, workspace, no_interactive)
        rows = db.list_sources(ws, cfg.store)
        table = Table(title=f"Sources: {ws}/{cfg.store}")
        for column in ["Path", "Type", "Hash", "Chunks", "Provider", "Store", "Ingested"]:
            table.add_column(column)
        for row in rows:
            table.add_row(
                row.source_path,
                row.file_type,
                row.file_hash[:12],
                str(row.chunk_count),
                f"{row.provider}/{row.embedding_model}",
                row.store,
                row.ingested_at,
            )
        console.print(table)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@app.command("eval")
def eval_command(
    eval_file: Path,
    provider: Optional[str] = typer.Option(None),
    store: Optional[str] = typer.Option(None),
    workspace: Optional[str] = typer.Option(None),
    embedding_model: Optional[str] = typer.Option(None, "--embedding-model"),
    top_k: Optional[int] = typer.Option(None, "--top-k"),
    no_interactive: bool = typer.Option(False, "--no-interactive"),
) -> None:
    try:
        cfg = effective_config(common_overrides(provider, store, embedding_model, top_k=top_k))
        tests = load_eval_file(eval_file)
        db = metadata()
        ws = resolve_workspace(db, workspace, no_interactive)
        passed = 0
        table = Table(title="Retrieval Eval")
        table.add_column("Question")
        table.add_column("Expected")
        table.add_column("Found")
        table.add_column("Result")
        for item in tests:
            hits = retrieve(
                str(item["question"]),
                ws,
                cfg,
                db,
                progress=lambda message: console.print(f"[cyan]...[/cyan] {message}"),
            )
            expected_sources = [str(source) for source in item["expected_sources"]]
            found_paths = [hit.source_path for hit in hits]
            ok = all(any(source_matched(found, expected) for found in found_paths) for expected in expected_sources)
            passed += 1 if ok else 0
            table.add_row(str(item["question"]), ", ".join(expected_sources), ", ".join(found_paths), "pass" if ok else "fail")
        console.print(table)
        console.print(f"Score: {passed}/{len(tests)}")
        if passed != len(tests):
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@app.command()
def reset(
    store: Optional[str] = typer.Option(None),
    workspace: Optional[str] = typer.Option(None),
    yes: bool = typer.Option(False, "--yes"),
    no_interactive: bool = typer.Option(False, "--no-interactive"),
) -> None:
    try:
        cfg = effective_config(common_overrides(store=store))
        db = metadata()
        ws = resolve_workspace(db, workspace, no_interactive)
        if no_interactive and not yes:
            raise RagError("reset --no-interactive requires --yes.")
        if not yes and not typer.confirm(f"Reset workspace '{ws}' for store '{cfg.store}'?"):
            console.print("Reset cancelled.")
            return
        namespace_row = db.namespace(ws, cfg.store)
        if namespace_row:
            store_client = store_from_config(cfg)
            store_client.reset(str(namespace_row["namespace"]))
        vector_ids = db.reset_workspace_store(ws, cfg.store)
        console.print(f"Reset {ws}/{cfg.store}. Removed {len(vector_ids)} vectors from metadata.")
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


@app.command()
def doctor() -> None:
    try:
        cfg = effective_config()
        db = metadata()
        checks: list[tuple[str, bool, str]] = []
        checks.append(("SQLite metadata", True, f"ready at {db.path}"))
        checks.append(("Config", True, f"provider={cfg.provider} store={cfg.store} embedding_model={cfg.embedding_model} generation_model={cfg.generation_model}"))
        for module in ["typer", "rich", "openai", "google.genai", "pypdf", "psycopg", "qdrant_client"]:
            checks.append((f"package:{module}", importlib.util.find_spec(module) is not None, "installed" if importlib.util.find_spec(module) else "missing; run pip install -e ."))
        openai_key = bool(os.getenv("OPENAI_API_KEY"))
        checks.append(
            (
                "OpenAI API key",
                openai_key or cfg.provider != "openai",
                "configured"
                if openai_key
                else "missing; set OPENAI_API_KEY"
                if cfg.provider == "openai"
                else "not configured; only needed when provider=openai",
            )
        )
        gemini_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        checks.append(
            (
                "Gemini API key",
                bool(gemini_key) or cfg.provider != "gemini",
                "configured"
                if gemini_key
                else "missing; set GOOGLE_API_KEY or GEMINI_API_KEY"
                if cfg.provider == "gemini"
                else "not configured; only needed when provider=gemini",
            )
        )
        for store_name in ("pgvector", "qdrant"):
            store_cfg = effective_config({"store": store_name})
            ok, message = store_from_config(store_cfg).doctor()
            if not ok and store_name in {"pgvector", "qdrant"}:
                message = f"{message}; run docker compose up -d and retry"
            checks.append((store_name, ok, message))
        table = Table(title="Doctor")
        table.add_column("Check")
        table.add_column("Status")
        table.add_column("Details")
        failed = False
        for name, ok, message in checks:
            failed = failed or not ok
            table.add_row(name, "ok" if ok else "fail", message)
        console.print(table)
        if failed:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)


def print_hits(hits, debug: bool = False) -> None:
    table = Table(title="Search Results")
    table.add_column("#")
    table.add_column("Source")
    table.add_column("Score")
    table.add_column("Preview")
    for index, hit in enumerate(hits, start=1):
        preview = hit.text if debug else hit.text[:240]
        table.add_row(str(index), citation_for(hit), "" if hit.score is None else f"{hit.score:.4f}", preview)
    console.print(table)


def _post_inngest_event(dev_server_url: str, event_key: str, event: dict) -> None:
    url = f"{dev_server_url.rstrip('/')}/e/{event_key}"
    body = json.dumps(event).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status >= 300:
                raise RagError(f"Inngest Dev Server returned HTTP {response.status}.")
    except urllib.error.URLError as exc:
        raise RagError(
            "Could not submit event to the Inngest Dev Server. "
            "Start it with 'inngest dev -u http://localhost:8000/api/inngest' "
            "or use the Docker Compose Inngest service."
        ) from exc


def _http_check(url: str) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status < 500, f"HTTP {response.status}"
    except Exception as exc:
        return False, str(exc)


if __name__ == "__main__":
    app()
