# Inngest Ingest Observability

## Objective

Add an optional Inngest-powered ingestion mode that gives deep local observability into long-running RAG document ingestion without replacing the existing synchronous CLI ingest path.

The primary user is a developer learning RAG who wants to see each ingest step, retry, wait, and failure clearly while using free-tier AI APIs such as Gemini. The intended outcome is a local development workflow where large document ingestion can run as a durable, observable background workflow through the Inngest Dev Server UI.

## Requirements

### Scope

- Keep the existing `rag ingest <path>` command working as the simple synchronous ingest path.
- Add an optional Inngest-based ingest mode for local development and learning.
- Use Inngest for orchestration, durable steps, retries, waits, and observability.
- Use Inngest locally first. Do not require Inngest Cloud for the MVP.
- Use the Inngest Dev Server UI for observability instead of building a custom dashboard.

### Commands

- Add a command to start the local RAG Inngest app server, for example `rag ingest-server`.
- Add a command to submit an ingest job to Inngest, for example `rag ingest-async <path>`.
- Add a command or README instructions to start the Inngest Dev Server.
- `rag ingest-async <path>` must use the active workspace by default.
- `rag ingest-async <path>` must accept `--workspace <name>` to override the active workspace.
- `rag ingest-async <path>` must accept relevant ingest options supported by the synchronous path, including provider, store, chunk size, chunk overlap, force, and no-interactive mode.
- The CLI must print the local Inngest Dev Server URL after submitting a job when possible.

### Local Inngest App

- Add a FastAPI app that serves the Inngest endpoint at a predictable path such as `/api/inngest`.
- The FastAPI app must be started locally by the project, not hosted externally.
- The app must load the same `.env`, config, metadata, provider, document loader, chunking, and vector store code used by the synchronous CLI path.
- The app must not duplicate the RAG ingestion business logic unless the code is explicitly factored into reusable step functions.
- The local app must work on Windows and WSL/Linux.

### Inngest Workflow

- Define an Inngest function triggered by an ingest event such as `rag/ingest.requested`.
- The ingest event payload must include:
  - workspace
  - path
  - provider
  - store
  - embedding model
  - generation model
  - chunk size
  - chunk overlap
  - force flag
  - request timestamp
- The workflow must expose observable steps for:
  - validating workspace and config
  - discovering files
  - loading each file
  - extracting text
  - chunking text
  - skipping unchanged files by hash
  - embedding chunks
  - waiting and retrying provider rate limits
  - storing vectors
  - updating SQLite metadata
  - producing a final ingest summary
- Long documents must be observable at least at file-level and embedding-chunk-level granularity.
- The workflow must continue processing unrelated files when one file fails.
- The workflow must record added, updated, skipped, unsupported, and failed file counts.

### Gemini Free-Tier Behavior

- Gemini embedding steps must respect provider retry-delay guidance when present.
- Gemini embedding steps must wait and retry the current chunk instead of restarting the whole document.
- Gemini embedding retries and delay settings must use the same config keys as synchronous ingest.
- Rate-limit waits must be visible in the Inngest Dev Server run timeline.

### Observability

- The Inngest Dev Server UI must show:
  - ingest job start and completion
  - each major ingest step
  - file currently being processed
  - chunk count per file
  - current embedding chunk
  - retry attempts
  - provider-request wait durations
  - failed files and failure messages
  - final ingest summary
- The terminal must still print enough information to tell the user where to open the Inngest UI and whether event submission succeeded.
- Do not log API keys, document full text, embeddings, or other secrets in Inngest events or step logs.
- Logs may include source file paths, chunk indexes, counts, provider name, model name, store name, and error summaries.

### Docker And Local Development

- Add Inngest Dev Server support to Docker Compose or document an equivalent local command.
- If Docker Compose is used, expose the Inngest Dev Server UI on `http://localhost:8288`.
- The local RAG Inngest app server and Inngest Dev Server must be able to communicate in Windows and WSL/Linux development.
- `rag doctor` must check the optional Inngest setup when Inngest dependencies or config are present, or provide a separate Inngest doctor command.
- `.env.example` must document optional local Inngest development environment variables, including `INNGEST_DEV`, `INNGEST_EVENT_KEY`, and `INNGEST_SIGNING_KEY`.
- The local app may provide safe local defaults for missing or invalid local Inngest development keys, but valid user-provided `INNGEST_SIGNING_KEY` values must be respected.

### Documentation

- Update the README with a beginner-friendly Inngest section explaining:
  - what Inngest does
  - why it helps long-running ingest
  - when to use `rag ingest` versus `rag ingest-async`
  - how to start the RAG Inngest app server
  - how to start the Inngest Dev Server
  - how to submit an ingest job
  - how to open and read the Dev Server UI
  - how Gemini rate-limit waits appear
- Document that Inngest Cloud is out of scope for the local MVP.

### Tests

- Add tests for event payload construction.
- Add tests for reusable ingest step helpers where practical.
- Add tests that confirm secrets are not included in event payloads or public logs.
- Keep existing synchronous ingest tests passing.

## Constraints

- Do not remove or weaken the existing synchronous `rag ingest` path.
- Do not require a paid Inngest account or Inngest Cloud for the MVP.
- Use Python-compatible Inngest tooling.
- Use FastAPI only for the local Inngest endpoint; do not add a custom web dashboard in this feature.
- Keep the RAG core reusable between sync CLI ingest and async Inngest ingest.
- Keep `.env` loading behavior consistent with the existing app.
- Do not store API keys in SQLite, vector stores, Inngest events, logs, or config files.
- Keep the implementation local-development friendly for Windows PowerShell and WSL/Linux.

## Edge Cases

- If the Inngest Dev Server is not running, `rag ingest-async` must fail with a helpful message or explain how to start it.
- If the local FastAPI/Inngest app server is not running, the Inngest Dev Server must not silently appear healthy; docs and doctor checks must explain the missing app endpoint.
- If an ingest event is missing required fields, the Inngest function must fail clearly before touching documents or vector stores.
- If the active workspace is missing, async ingest must behave like sync ingest: prompt in interactive mode or fail in `--no-interactive` mode.
- If a file is unchanged and `force` is false, the workflow must skip it visibly.
- If a PDF is corrupt or unreadable, the workflow must mark that file failed and continue other files.
- If Gemini returns a retry delay, the workflow must wait and retry the current chunk while showing the wait in the Dev Server timeline.
- If provider quota is exhausted beyond retry limits, the workflow must fail the current file with a clear message and preserve progress for completed files.
- If vector storage fails for one file, the workflow must not mark that file as successfully ingested.
- If the user runs sync and async ingestion concurrently for the same workspace and files, the system must avoid corrupting metadata; if safe concurrency is not implemented, it must document that concurrent ingestion into the same workspace is unsupported.

## Assumptions

- The first Inngest implementation is local-only.
- The existing synchronous ingestion code may be refactored into reusable helpers if needed.
- The initial async workflow may process files sequentially to keep free-tier API usage predictable.
- The Inngest Dev Server UI is sufficient for the first observability dashboard.
- A future version may add Inngest Cloud deployment, production workers, richer metrics, or custom dashboards.

## Out of Scope

- Inngest Cloud deployment.
- User accounts or hosted multi-user operation.
- Custom dashboard UI outside Inngest Dev Server.
- Distributed workers.
- Parallel multi-file ingestion unless it can be done without violating free-tier API constraints.
- Replacing the existing synchronous CLI ingest path.
- Full production observability stack such as OpenTelemetry, Prometheus, or Grafana.

## Definition of Done

- A developer can run the existing `rag ingest <path>` command exactly as before.
- A developer can start a local RAG Inngest app server.
- A developer can start the local Inngest Dev Server and open its UI.
- A developer can submit an async ingest job from the CLI.
- The Inngest Dev Server shows the ingest run with observable file, chunking, embedding, wait/retry, storage, and summary steps.
- Gemini rate-limit retry waits are visible and do not require manual restart while retry attempts remain.
- Failed files are visible and do not prevent unrelated files from being processed.
- API keys and full document text are not exposed in Inngest event payloads or logs.
- README instructions work for local Windows and WSL/Linux development.
- Relevant tests pass, and existing sync-ingest tests still pass.
