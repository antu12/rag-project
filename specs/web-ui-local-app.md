# Local RAG Web Application

## Objective

Build a local, single-user Web application that exposes the complete useful capability of the existing RAG CLI through an approachable, observable interface. A developer learning RAG must be able to configure providers, manage isolated workspaces, upload and ingest documents, inspect every pipeline stage, search retrieved chunks, ask grounded questions with citations, browse independent question history, run retrieval evaluations, inspect sources, reset data, and diagnose local services without returning to the CLI for ordinary use.

The Web application must make the RAG pipeline visible rather than hiding it. Every long-running operation must identify its current stage, status, timing, progress, waits, retries, result, and actionable failure. The existing CLI must remain supported and both interfaces must reuse the same backend business logic and metadata.

## Product Principles

- Optimize for one developer learning and debugging RAG locally.
- Present the actual application as the first screen; do not create a marketing landing page.
- Keep the interface quiet, operational, information-dense, and easy to scan.
- Show what the system is doing, which provider/model/store it is using, and why an operation failed.
- Preserve workspace isolation everywhere and keep the active workspace visible.
- Keep provider secrets on the backend and never return stored secret values to the browser.
- Keep the CLI and Web UI behavior consistent by sharing application services instead of invoking CLI commands or duplicating logic.
- Design backend contracts so authentication, multi-user ownership, conversation memory, and deployment can be added later without pretending they exist now.

## Users And Access

- Support one trusted local user in the first version.
- Do not require login, accounts, roles, permissions, or user registration.
- Bind the production-like local server to `127.0.0.1` by default.
- Treat remote/LAN exposure, authentication, authorization, and multi-user isolation as future work.
- Display a warning when the API is configured to bind to a non-loopback interface because secret-setting and destructive endpoints are unauthenticated in this version.

## Technology And Architecture

### Frontend

- Build the frontend with React, TypeScript, and Vite.
- Use React Router for page routing.
- Use TanStack Query for server state, request lifecycle, cache invalidation, and mutations.
- Use Tailwind CSS for styling and a small set of reusable local UI primitives.
- Use Lucide icons for familiar actions and provide tooltips for icon-only or unfamiliar controls.
- Keep generated frontend files under a dedicated directory such as `web/`.
- Do not introduce a second frontend framework or a component system that obscures basic application behavior.

### Backend

- Extend the existing FastAPI application into the local Web API while preserving the Inngest endpoint.
- Place HTTP transport, request validation, serialization, and streaming concerns outside the core RAG modules.
- Refactor reusable application services where needed so the CLI, Web API, and Inngest functions call the same operations.
- Do not execute shell commands or call the Typer CLI from API handlers.
- Use Pydantic request and response models and publish an OpenAPI schema.
- Version application endpoints under `/api/v1`; keep the Inngest protocol endpoint at `/api/inngest`.
- Serve the built frontend from FastAPI for a simple local production-like command, while retaining separate Vite and FastAPI development servers with documented CORS configuration.

### Runtime Data

- Continue using SQLite for local metadata and extend its schema with migrations for uploads, jobs, job events, chat sessions, chat turns, and eval runs.
- Continue using pgvector and Qdrant through the existing storage interface.
- Store managed uploads under `.rag/uploads/<workspace>/` using server-generated safe names and retain the original display filename in metadata.
- Keep `.rag/`, uploaded files, job logs, chat history, and other runtime data ignored by git.
- Do not store embeddings twice merely to support the UI.

### Live Updates

- Use Server-Sent Events for live job and operation events in the first version.
- Persist job state and events before broadcasting them so page refreshes and temporary SSE disconnects do not lose history.
- Support reconnection using a last-event identifier or an equivalent cursor.
- Fall back to bounded polling when SSE is unavailable.
- Define a stable event envelope containing event ID, job ID, timestamp, stage, status, message, progress fields, retry/wait details, and safe structured metadata.

## Information Architecture

Use a persistent application shell with:

- A compact sidebar containing Overview, Documents, Search, Chat, Evaluations, Activity, Settings, and System Health.
- A persistent workspace selector near the top of the shell.
- A header area for the current page title, relevant primary action, provider/store indicator, and service-health warning.
- A responsive mobile navigation pattern that preserves access to all sections.
- No cards nested inside cards and no decorative dashboard sections that reduce information density.

The application must provide these routes:

- `/` or `/overview`
- `/documents`
- `/documents/:sourceId`
- `/search`
- `/chat`
- `/chat/:sessionId`
- `/evaluations`
- `/evaluations/:runId`
- `/activity`
- `/activity/:jobId`
- `/settings`
- `/health`

## Core User Flows

### First Run

1. Load application/bootstrap status.
2. If no workspace exists, present workspace creation as the primary task.
3. Show provider key presence and storage health without blocking navigation.
4. Guide the user to Settings when the selected provider lacks a key.
5. Guide the user to System Health when the selected store is unavailable.
6. Provide exact Windows PowerShell and Linux/WSL commands for dependencies that must be started externally.

### Workspace Selection

1. Select an existing workspace from the persistent selector or create one in place.
2. Make the selected workspace the same active workspace used by the CLI.
3. Invalidate workspace-scoped frontend queries after switching.
4. Never show documents, jobs, history, evals, or search results from another workspace as though they belong to the newly selected workspace.

### Upload And Ingest

1. Open Documents and drag files onto the upload area or use a file picker.
2. Validate supported type, count, per-file size, total request size, duplicate names, and empty files before ingestion.
3. Copy accepted files into the selected workspace's managed upload directory.
4. Show the selected files and allow removal before submission.
5. Choose synchronous or Inngest execution with a segmented control.
6. Review provider, embedding model, generation model, store, chunk size, overlap, force behavior, Gemini pacing, and retry settings.
7. Submit an ingestion job and navigate to its activity detail.
8. Show every stage and file outcome while the job runs.
9. Refresh source and workspace summaries after completion or partial completion.

### Search

1. Enter an independent query and choose top-k.
2. Embed the query and search the active workspace/store without generation.
3. Show live stages for validation, query embedding, dimension validation, and vector search.
4. Display ranked chunks with score, source, page/chunk citation, preview, provider/model/store details, and expandable full text.
5. Allow opening the corresponding source detail and copying a citation.

### Ask

1. Create or open a local chat session used for browsing history.
2. Submit a question as an independent RAG query; previous turns must not be included in retrieval or generation context.
3. Show stages for validation, query embedding, vector search, prompt-context construction, and generation.
4. Render the grounded answer, citations, timing, selected settings, and token usage when available.
5. Allow inspection of retrieved chunks and a redacted prompt preview in a collapsible debug panel.
6. Persist the question, answer, citations, retrieved hit metadata, settings snapshot, timings, usage, and errors.
7. Allow renaming and deleting a local history session with confirmation.

### Evaluation

1. Import an existing JSON or YAML eval file or create/edit a suite using structured fields.
2. Validate the complete suite before starting a run.
3. Select provider, embedding model, store, top-k, and workspace settings for the run.
4. Run retrieval-focused cases and stream case-level status.
5. Show expected sources, retrieved sources, pass/fail, scores, durations, and aggregate accuracy.
6. Persist immutable run settings and results so old runs remain interpretable after configuration changes.
7. Compare at least two runs side by side by aggregate result and per-case source matching.
8. Do not add LLM answer grading in this version.

### Reset

1. Start reset from workspace settings or Documents.
2. Clearly identify the workspace and vector store affected.
3. Require typing the workspace name or an equivalently deliberate confirmation.
4. Delete vectors, chunks, and source metadata only for that workspace/store.
5. Separately offer deletion of managed upload copies; do not silently conflate source deletion with file deletion.
6. Preserve other workspaces and chat/eval history unless the confirmation explicitly includes them.

## Screen Requirements

### Overview

- Show the active workspace, selected provider/models, selected vector store, and compact service status.
- Show source count, chunk count, most recent ingestion, recent question count, recent eval score, and active/failed jobs.
- Provide direct actions for Upload Documents, Ask a Question, Search Chunks, and Run Evaluation.
- Show recent activity in a compact table or timeline.
- Provide purposeful empty states that direct the user to the next valid action.

### Workspaces

- Provide workspace creation from the selector and a dedicated management dialog or section.
- List name, created time, source/chunk counts by store, latest activity, and active status.
- Validate names using the existing workspace naming rules and explain invalid characters inline.
- Support selecting a workspace and resetting its store data.
- Do not add workspace deletion until semantics for managed files, history, jobs, and both vector stores are implemented atomically and covered by a separate destructive confirmation flow.

### Documents

- Provide drag-and-drop and file-picker upload for `.pdf`, `.md`, and `.txt`.
- Support multi-file uploads and preserve readable original names and relative directory information when the browser supplies it.
- List indexed sources with path, type, short hash, chunk count, provider, embedding model, generation model, dimensions, store, and ingestion time.
- Provide filtering by file type, provider, store, and ingest state, plus text search and sortable columns.
- Provide a source detail view showing metadata and paginated chunks with page number, chunk index, and text.
- Support re-ingesting selected managed files with current or overridden settings.
- Support removing one source from its vector store and metadata with confirmation while separately choosing whether to delete the managed file.
- Mark files that exist in managed storage but are not indexed, and indexed records whose managed file is missing.

### Ingestion Setup

- Use a focused drawer or dialog rather than a separate marketing-like page.
- Use a segmented control for Synchronous and Inngest modes and explain the practical difference succinctly.
- Use selects for provider and vector store, editable model selects/inputs, numeric fields for chunk size/overlap/retries, and a numeric input for Gemini delay.
- Validate overlap smaller than chunk size, positive counts, supported provider/store combinations, key presence, and store health before submission.
- Show the expected number of files and make clear that exact chunk count is known only after extraction/chunking.
- Provide a force re-ingest checkbox with a clear consequence.

### Activity And Job Detail

- List jobs across operation types with workspace, type, execution mode, status, progress, started time, duration, and summary.
- Support statuses `queued`, `validating`, `running`, `waiting`, `retrying`, `succeeded`, `partially_succeeded`, `failed`, and `cancelled` where cancellation is actually supported.
- Show a stable timeline for upload validation, discovery, file hashing, loading, text extraction, chunking, unchanged-file checks, embedding, rate-limit waits, retries, namespace validation, vector storage, metadata update, and final summary.
- Show per-file status and embedding progress as current/total chunks.
- Show wait duration, retry attempt/limit, provider operation, and safe provider error summary.
- Distinguish a still-running operation from a disconnected browser or unavailable event stream.
- Keep completed and failed job details browsable after restart.
- Link Inngest-mode jobs to the local Inngest Dev Server run when a stable URL/run identifier is available.
- Never log API keys, authorization headers, embeddings, complete prompts, or full document text.

### Search Playground

- Keep the query input and top-k control stable while results load.
- Show an explicit progress timeline and elapsed time.
- Present ranked results for comparison rather than decorative cards.
- Provide score, citation, text preview/full text, source metadata, and vector identifier in debug mode.
- Handle no indexed sources, no results, dimension mismatch, missing provider key, provider quota, and unavailable store with tailored actions.
- Keep recent search history for the current browser session only unless a later spec adds persisted search history.

### Chat And History

- Provide a chat-like reading experience with a session list and a main conversation pane.
- Persist sessions and turns in SQLite for later browsing.
- Treat each question independently and label the behavior in session metadata/help, not as repeated instructional text in the main interface.
- Do not send prior messages to the embedding or generation provider.
- Show citations adjacent to the answer and allow a citation to open its retrieved chunk/source detail.
- Show an insufficient-context result as a normal grounded outcome, not a generic failure.
- Provide debug details for retrieved chunks, scores, provider/models/store, top-k, timing, token usage when available, and redacted prompt preview.
- Prevent duplicate submission while a question is running, but permit navigating away and returning to its persisted operation.
- Preserve failed turns with their safe error and retry action.
- Reserve data-model extension points for future parent-turn relationships, conversation context policy, summaries, and memory records without implementing them.

### Evaluations

- Provide suite list/import/create/edit/delete and run history.
- Represent each case with question, one or more expected source paths, and optional expected-answer notes.
- Validate malformed YAML/JSON, duplicate/empty cases, missing sources, and invalid expected source arrays.
- Show per-case retrieval results and aggregate score with settings snapshot.
- Support comparison of runs that differ by provider, embedding model, chunk settings recorded on indexed data, top-k, or store.
- Warn when a comparison is not meaningful because runs used different workspaces or document sets.
- Export a run result as JSON.

### Settings

- Group settings into Provider, Models, Retrieval, Chunking, Storage, Retry/Timeout, and Inngest sections.
- Show effective values and their source: built-in default, local config, `.env`, or shell environment.
- Allow editing supported non-secret local config values using the same validation as the CLI.
- Allow write-only entry/replacement/removal of `OPENAI_API_KEY`, `GOOGLE_API_KEY`, and `GEMINI_API_KEY` in the project-local `.env`.
- Return only key presence, source, and an optional non-sensitive fingerprint such as last four characters when explicitly judged safe; never return the complete value.
- Mask key inputs, never prefill them, disable browser autocomplete where practical, and clear them after submission.
- Update `.env` without deleting unrelated entries or comments, use an atomic replacement, and preserve shell-environment precedence.
- Explain when a newly written `.env` key is shadowed by a shell variable.
- Warn before model/store changes that are incompatible with an existing workspace namespace.
- Provide restore-to-default behavior only for local config overrides, not shell or `.env` values.

### System Health

- Provide Web equivalents of `rag doctor` and `rag inngest-doctor`.
- Check SQLite readiness, effective configuration, required Python packages, selected and optional provider key presence, Postgres connectivity, pgvector extension, Qdrant connectivity, FastAPI status, Inngest endpoint sync, and Inngest Dev Server reachability.
- Distinguish required failures from optional/inactive-service warnings.
- Show check time, duration, status, safe details, and exact remediation.
- Provide platform-specific Windows PowerShell and Linux/WSL commands for starting Docker Compose, activating/installing the project, and starting the app server.
- Do not start, stop, restart, or control Docker, Inngest, or host processes from the browser in this version.

## API Requirements

Implement explicit request/response contracts for at least these endpoint groups. Exact minor route names may change during implementation if the OpenAPI contract remains coherent and the spec is updated in the same change.

### Bootstrap And Health

- `GET /api/v1/bootstrap`: application version, active workspace, effective non-secret configuration, key-presence summary, feature flags, and compact health summary.
- `GET /api/v1/health`: lightweight API liveness.
- `POST /api/v1/doctor`: complete on-demand health checks.
- `POST /api/v1/inngest/doctor`: optional Inngest checks.

### Workspaces

- `GET /api/v1/workspaces`
- `POST /api/v1/workspaces`
- `PUT /api/v1/workspaces/{name}/active`
- `POST /api/v1/workspaces/{name}/reset`
- Return workspace summaries without requiring one API call per row.

### Configuration And Secrets

- `GET /api/v1/config`: effective redacted config, editable local overrides, value sources, and constraints.
- `PATCH /api/v1/config`: validated non-secret local overrides.
- `DELETE /api/v1/config/{key}`: remove a local override.
- `GET /api/v1/secrets/status`: provider key presence and source only.
- `PUT /api/v1/secrets/{provider}`: write-only set/replace operation.
- `DELETE /api/v1/secrets/{provider}`: remove only the project-local `.env` key and report if a shell key remains active.

### Uploads And Sources

- `POST /api/v1/workspaces/{workspace}/uploads`: multipart managed upload with per-file results.
- `GET /api/v1/workspaces/{workspace}/uploads`
- `DELETE /api/v1/workspaces/{workspace}/uploads/{uploadId}`
- `GET /api/v1/workspaces/{workspace}/sources`
- `GET /api/v1/workspaces/{workspace}/sources/{sourceId}`
- `GET /api/v1/workspaces/{workspace}/sources/{sourceId}/chunks` with pagination.
- `DELETE /api/v1/workspaces/{workspace}/sources/{sourceId}` with explicit vector/metadata and managed-file options.

### Operations And Jobs

- `POST /api/v1/workspaces/{workspace}/ingestions`: submit managed upload IDs and settings snapshot with execution mode.
- `GET /api/v1/jobs` with workspace/type/status filters and pagination.
- `GET /api/v1/jobs/{jobId}`
- `GET /api/v1/jobs/{jobId}/events`
- `GET /api/v1/jobs/{jobId}/stream`: SSE stream.
- `POST /api/v1/jobs/{jobId}/cancel` only when the implementation can safely cancel at a documented boundary; otherwise omit the endpoint and do not show a fake cancel control.
- Both synchronous and Inngest ingestion must create the same local job/event representation. Synchronous means execution by the local API process; Inngest means durable execution through Inngest.

### Search And Chat

- `POST /api/v1/workspaces/{workspace}/search`: independent retrieval request with settings overrides.
- `GET /api/v1/chat/sessions`
- `POST /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{sessionId}`
- `PATCH /api/v1/chat/sessions/{sessionId}`
- `DELETE /api/v1/chat/sessions/{sessionId}`
- `POST /api/v1/chat/sessions/{sessionId}/turns`: independent RAG question.
- Long-running search/ask responses must either use the common job stream or a clearly documented operation-event stream and must remain recoverable after navigation.

### Evaluations

- `GET /api/v1/eval/suites`
- `POST /api/v1/eval/suites`
- `GET/PATCH/DELETE /api/v1/eval/suites/{suiteId}`
- `POST /api/v1/eval/suites/import`
- `POST /api/v1/eval/runs`
- `GET /api/v1/eval/runs`
- `GET /api/v1/eval/runs/{runId}`
- `GET /api/v1/eval/runs/{runId}/export`

## Job And Event Model

Persist at least:

- Job ID, operation type, workspace, execution mode, status, created/started/completed timestamps, progress current/total, configuration snapshot, result summary, safe error, and optional Inngest identifiers.
- Event ID, job ID, sequence, timestamp, stage code, human-readable message, status, file/upload/source identifiers, chunk current/total, retry attempt/limit, wait seconds, duration, and safe metadata.
- Per-file outcome for ingestion: added, updated, skipped, unsupported, or failed.

Requirements:

- Use machine-stable stage/status codes and separate display labels.
- Enforce monotonically increasing event sequence per job.
- Make terminal job states immutable except for explicitly recorded recovery/migration behavior.
- Mark interrupted synchronous jobs as failed/interrupted after an API restart; do not leave them running forever.
- Reconcile Inngest job status after API restart when possible.
- Bound retained event volume by coalescing overly frequent progress events while retaining retries, waits, failures, stage transitions, and final summaries.

## Data Integrity And Concurrency

- Scope every data query and mutation by explicit workspace on the backend; do not trust frontend filtering for isolation.
- Keep the active workspace as convenience state, but include workspace explicitly in resource URLs and persisted records.
- Serialize or lock ingestion/reset/source-removal operations that target the same workspace/store/source to avoid metadata/vector corruption.
- Reject or queue conflicting synchronous and Inngest jobs with an actionable explanation.
- Use database transactions for metadata mutations and define compensation behavior when vector storage succeeds but metadata storage fails, or vice versa.
- Preserve completed files when another file in the same ingestion job fails.
- Continue using file hashes for idempotency across CLI and Web ingestion.
- Prevent path traversal, absolute upload paths, unsafe filenames, symlink escapes, and cross-workspace file access.
- Use server-generated IDs in filesystem paths and preserve original names only as metadata/display text.
- Define upload and API body limits through configurable backend settings with documented defaults.

## Validation And Error Contract

- Return a consistent JSON error shape with code, message, field errors where relevant, retryability, suggested action, and correlation/job ID.
- Map expected configuration, workspace, provider, quota, dimension, storage, validation, and not-found failures to suitable non-500 HTTP statuses.
- Do not expose Python tracebacks, SQL, secrets, complete prompts, embeddings, or provider authorization details to the browser.
- Preserve a safe provider name, operation, status/code, retry delay, and error summary for debugging.
- Show field validation inline and operation failures in the relevant job/turn/result, not only as transient toast messages.
- Use toast notifications only for brief confirmations or background status changes.

## Secret And Local Security Requirements

- Never include API keys in frontend bundles, API reads, logs, SSE events, Inngest payloads, job metadata, chat records, eval results, or error responses.
- Accept secret writes only over the local API and reject them when remote access is enabled unless a future authenticated mode explicitly permits it.
- Preserve `.env` gitignore protection and verify it in automated tests.
- Redact DSN passwords and secret-like values in configuration and health responses.
- Do not render untrusted Markdown as raw HTML; sanitize supported Markdown output.
- Treat document text, filenames, model output, and provider errors as untrusted display content.
- Configure development CORS narrowly for the known Vite origin; do not use wildcard origins with secret or destructive endpoints.
- Add CSRF/origin protection appropriate to the same-origin local deployment, particularly for secret and destructive mutations.

## Accessibility And Responsive Behavior

- Meet WCAG 2.1 AA expectations for color contrast, keyboard operation, focus visibility, labels, landmarks, dialogs, form errors, and status announcements.
- Do not use color as the only job-status indicator.
- Make upload, workspace switching, search, chat, settings, dialogs, tables, and debug disclosures usable by keyboard.
- Announce meaningful asynchronous status changes through an appropriately throttled live region.
- Respect reduced-motion preferences and avoid decorative motion.
- Keep layouts usable from 360px mobile width through wide desktop screens.
- Convert wide tables to deliberate compact rows or horizontal scrolling on small screens without clipping actions or labels.
- Ensure long filenames, hashes, model names, errors, citations, and unbroken text wrap or truncate with accessible full-value disclosure.

## Performance Requirements

- Render the application shell and cached bootstrap state without waiting for full doctor checks.
- Paginate sources, chunks, jobs, chat sessions, turns, eval suites, and eval runs where lists may grow.
- Avoid returning chunk text in source-list responses; fetch it on source detail/pagination.
- Avoid polling every page independently; centralize live job state and invalidate only affected queries.
- Keep upload, job, and provider timeouts distinct.
- Stream progress frequently enough to show useful movement without creating one persisted event for every low-value log line.
- Preserve UI responsiveness while uploads, ingestion, evals, searches, and asks are running.

## Configuration Defaults

- Reuse existing CLI defaults and precedence: request override, shell environment, `.env`, local config, built-in default.
- Show effective values rather than silently displaying editable local values as though they are active.
- Use existing provider/model/store/chunk/top-k/retry validation.
- Add documented backend defaults for upload limits, pagination, job retention, and allowed origins during implementation, and update this spec in the same change.

## Testing And Verification

### Backend

- Add unit tests for API schemas, error mapping, config source reporting, atomic `.env` secret updates, redaction, upload path safety, workspace scoping, job transitions, and SSE event serialization.
- Add integration tests for workspace creation/activation, managed upload, source/chunk listing, sync ingestion, search, ask persistence, eval runs, reset, and health endpoints using provider/store fakes where external calls are unnecessary.
- Add contract tests proving API requests call shared application services and do not invoke the CLI.
- Add concurrency tests for conflicting ingest/reset/source-delete operations.
- Add migration tests for existing `.rag/metadata.sqlite3` databases.
- Keep all existing CLI tests passing.

### Frontend

- Add component tests for forms, validation, status displays, citations, empty/error/loading states, secret inputs, and destructive confirmations.
- Add API mocking tests for quota waits, retries, partial ingestion, SSE disconnect/reconnect, missing services, and dimension mismatch.
- Add end-to-end tests for first run, workspace switching, upload/ingest, source inspection, search, ask/history, eval, settings, health, and reset.
- Verify keyboard navigation and automated accessibility checks on every primary route.

### Real-Service Acceptance

- Verify pgvector and Qdrant paths against Dockerized services.
- Verify at least one OpenAI and one Gemini request when credentials/quota are available; keep automated CI independent from paid API calls.
- Verify a real synchronous ingestion timeline.
- Verify a real Inngest ingestion in the Dev Server UI, including file/chunk progress and a simulated or real retry/wait.
- Verify browser behavior at desktop and mobile viewports using screenshots and interaction tests.
- Verify Windows PowerShell and WSL/Linux setup instructions.

## Documentation And Developer Experience

- Add beginner-friendly Web UI setup for Windows PowerShell and WSL/Linux.
- Provide development commands for backend and frontend and one local production-like start command.
- Document required Node and Python versions, dependency installation, Docker startup, Inngest startup, URLs, and troubleshooting.
- Document the distinction between synchronous local-process ingestion and durable Inngest ingestion.
- Explain managed upload storage and how reset/source deletion affects indexed data versus copied files.
- Explain that chat sessions are persisted for browsing but every question is independent.
- Explain secret handling and the risks of non-loopback binding without authentication.
- Keep CLI documentation and workflows intact.

## Constraints

- Preserve the Python CLI and its commands.
- Use React, TypeScript, Vite, FastAPI, TanStack Query, React Router, Tailwind CSS, and Lucide icons for this milestone.
- Continue using raw OpenAI and Gemini SDKs; do not add LangChain or LlamaIndex.
- Continue supporting both pgvector and Qdrant.
- Continue supporting `.pdf`, `.md`, and `.txt` only.
- Keep Inngest optional and local; do not require Inngest Cloud.
- Do not require paid infrastructure beyond any provider API usage chosen by the user.
- Run on Windows PowerShell and WSL/Linux.
- Keep the UI local-first and single-user.
- Do not add a custom replacement for the Inngest Dev Server dashboard.

## Edge Cases

- No workspaces exist, or the active workspace was removed/corrupted.
- Workspace changes while a request is in flight.
- Duplicate workspace name or unsafe workspace characters.
- Empty upload, unsupported extension, MIME/extension disagreement, zero-byte file, corrupt PDF, duplicate filename, very long filename, oversized file, request too large, interrupted upload, or insufficient disk space.
- Same file uploaded twice with identical content, different filename with identical content, or same filename with changed content.
- Managed upload exists without an index record, or index metadata exists after the managed file was removed externally.
- Missing selected-provider key, both Gemini key aliases set, invalid/revoked key, quota exhaustion, retry delay, timeout, malformed provider response, or generation returning empty text.
- Selected vector store is unavailable, namespace is absent, embedding dimensions/models mismatch, vector write partially fails, or metadata commit fails.
- No documents indexed, no retrieval hits, insufficient context, stale citation target, or source removed after a historical answer.
- SSE connection drops, duplicate/replayed event, out-of-order event, browser refresh, API restart during sync work, Inngest unavailable, or Inngest app endpoint unsynced.
- One file fails while other files succeed.
- Reset, source deletion, sync ingest, and Inngest ingest conflict for the same workspace/store.
- Eval suite is invalid, expected source no longer exists, run is interrupted, or compared runs use incompatible document sets.
- `.env` is missing, malformed, read-only, updated concurrently, or shell environment shadows a newly written key.
- Long model names, filenames, document text, answers, provider errors, and citations do not fit normal UI containers.
- Browser back/forward navigation and direct links to missing/deleted resources.
- User opens multiple tabs and changes active workspace or configuration in another tab.

## Out Of Scope

- Authentication, user accounts, roles, permissions, and multi-user deployment.
- Conversation-aware retrieval, prior-turn prompt context, query rewriting from history, summaries, long-term memory, and memory controls.
- Local embedding models.
- New document loaders such as `.docx`, spreadsheets, HTML, OCR, image, audio, or video.
- Hybrid lexical/vector search, reranking, query expansion, and agent tools.
- LLM-based answer grading.
- Inngest Cloud, cloud deployment, distributed workers, and production process orchestration.
- Starting or stopping Docker, Inngest, or other host processes from the Web UI.
- Custom observability dashboard replacing Inngest Dev Server.
- Editing original document contents.
- Workspace sharing, export/import, backup, and restore.

## Future Plan

### Conversation Continuity And Memory

A later spec must add conversation-aware behavior as a backend capability, not merely concatenate browser messages. It must define:

- Session context policy and user controls for independent versus contextual questions.
- Follow-up query rewriting and visibility into the rewritten retrieval query.
- Token budgeting, context-window limits, turn selection, and conversation summarization.
- Citation correctness when an answer depends on earlier turns.
- Persistent memory types, scope, extraction, editing, deletion, expiry, and workspace isolation.
- Protection against stale, contradictory, or poisoned memory.
- Eval coverage comparing independent and contextual retrieval.
- Data migrations from the independent-turn history created by this version.

### Other Future Milestones

- Authentication and multi-user ownership.
- Additional document loaders.
- Hybrid search, reranking, and query rewriting.
- Local embedding providers.
- Cloud deployment and production observability.

## Definition Of Done

- A new local user can follow the README on Windows PowerShell or WSL/Linux and open the usable Web application.
- The application starts on the real product interface, handles first-run empty state, and requires no authentication locally.
- The user can create and switch between at least two workspaces, and every screen/API operation remains correctly isolated.
- The user can securely set or replace OpenAI and Gemini keys through write-only UI handling without any endpoint returning them.
- The user can inspect and edit effective non-secret configuration with correct source/precedence reporting.
- The user can upload managed `.pdf`, `.md`, and `.txt` copies, validate them, and ingest them using either synchronous or Inngest mode.
- Both ingestion modes show persisted, live, recoverable status for validation, hashing, loading, extraction, chunking, embedding chunks, waits, retries, storage, metadata, per-file outcomes, and final summary.
- A real Inngest run appears in the local Dev Server with the detailed observability required by the Inngest spec.
- The user can list sources, inspect metadata and paginated chunks, re-ingest a file, remove a source, and deliberately choose whether to delete its managed copy.
- The user can run search and inspect ranked chunks, scores, citations, metadata, progress, and errors without generation.
- The user can ask independent grounded questions, receive citations, inspect debug retrieval/context data, and browse persisted sessions and turns after restart.
- Prior turns are demonstrably not sent as retrieval or generation context.
- The user can create/import an eval suite, run it, inspect case and aggregate results, compare runs, and export results.
- The user can inspect persistent activity/job history and recover status after refresh or SSE reconnection.
- The user can run complete health checks and receive actionable Windows and Linux/WSL remediation without the UI controlling host services.
- The user can reset one workspace/store without affecting another, with deliberate confirmation and explicit managed-file handling.
- API keys, embeddings, full document text, complete prompts, and secret values do not appear in unsafe events, logs, configuration reads, or browser payloads.
- The UI is keyboard usable, passes automated accessibility checks on primary routes, and works without overlap or clipped controls at mobile and desktop viewports.
- Existing CLI behavior and tests remain intact; backend, frontend, integration, migration, concurrency, accessibility, and end-to-end tests described above pass.
- The OpenAPI contract, README, `.env.example`, Docker instructions, and all related specs accurately describe the delivered behavior.
