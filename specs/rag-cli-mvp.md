# RAG CLI MVP

## Objective

Build a command-line RAG learning project that lets a single developer create isolated workspaces, ingest local documents, store embeddings in Dockerized vector backends, retrieve relevant chunks, ask grounded questions with citations, and evaluate retrieval quality.

The primary user is a developer learning how RAG works end to end. The project should expose the main RAG stages clearly instead of hiding them behind a framework.

## Requirements

### CLI

- Implement the MVP as a Python CLI package.
- Use Typer for command definitions and interactive prompts.
- Provide these top-level commands:
  - `rag init`
  - `rag config show`
  - `rag config set <key> <value>`
  - `rag doctor`
  - `rag workspace create <name>`
  - `rag workspace list`
  - `rag workspace use <name>`
  - `rag workspace current`
  - `rag ingest <path>`
  - `rag search <query>`
  - `rag ask <question>`
  - `rag sources`
  - `rag eval <eval-file>`
  - `rag reset`
- Commands must use the active workspace by default.
- Commands that operate on workspace data must also accept `--workspace <name>` to override the active workspace.
- Commands must be interactive by default when required information is missing.
- Commands must support `--no-interactive` so scripts can fail fast instead of prompting.
- CLI output should be readable in a terminal and should clearly show success, skipped work, errors, and next steps.
- Long-running commands such as `rag ingest`, `rag search`, `rag ask`, and `rag eval` must print progress messages so the user can tell whether the app is loading files, chunking, embedding, waiting for rate limits, retrying, searching vector storage, building prompt context, generating answers, or storing vectors.
- Commands must return non-zero exit codes for failed operations so the CLI can be used in scripts.

### Configuration

- `rag init` must create required local project directories and example configuration files without storing secrets.
- Provide a checked-in `.env.example` documenting required environment variables.
- Automatically load a project-local `.env` file from the repository root before reading provider API keys or `RAG_*` configuration environment variables.
- Values already set in the shell environment must take precedence over `.env` values.
- The `.env` file must remain ignored by git and must not be committed.
- Support configuration from command options, environment variables, and a local non-secret config file.
- Use this precedence order: command option, shell environment variable, `.env` value, local config file, built-in default.
- `rag config show` must print effective non-secret configuration values and redact anything that looks secret.
- `rag config set <key> <value>` must store non-secret defaults such as provider, store, model names, chunk size, chunk overlap, top-k, and service URLs.
- Configuration must support separate defaults for embedding model and generation model.
- Configuration must support Gemini embedding delay and retry settings so free-tier users can pace embedding requests during ingestion.

### Workspaces

- Support multiple isolated workspaces.
- A workspace must isolate documents, chunks, embeddings, vector collection/table namespace, provider/model metadata, and ingestion history.
- `rag workspace create <name>` must create a workspace with a filesystem-safe identifier.
- `rag workspace list` must show all workspaces and indicate the active workspace.
- `rag workspace use <name>` must set the active workspace.
- If a command needs a workspace and no active workspace exists, it must prompt the user to choose or create one when interactive mode is enabled.
- If a command needs a workspace and no active workspace exists while `--no-interactive` is set, it must fail with a helpful message.

### Providers

- Support both OpenAI and Google Gemini APIs from the MVP.
- Do not reuse Codex credentials or assume API access is available.
- Read OpenAI credentials from `OPENAI_API_KEY`.
- Read Gemini credentials from `GOOGLE_API_KEY` or `GEMINI_API_KEY`.
- Provide provider selection through `--provider openai` and `--provider gemini`.
- Provide model selection through `--embedding-model` and `--generation-model`.
- Store provider and model metadata with ingested chunks so the user can inspect how a workspace was built.
- Use raw provider SDKs directly. Do not use LangChain, LlamaIndex, or other RAG frameworks in the MVP.
- If a required API key is missing, fail before making provider calls and explain which environment variable is required.
- Store embedding vector dimensions with each workspace/store namespace.
- If a user tries to search or ask with an embedding model whose dimensions do not match existing indexed vectors, fail with a helpful message explaining that the workspace must be re-ingested or a matching model must be used.
- Provider calls must use reasonable timeouts and retry transient failures with bounded retries.
- Embedding calls during ingestion should be batched when the provider SDK supports batching.
- Gemini embedding calls must avoid restarting an entire document's embedding batch after a single chunk fails.
- Gemini embedding calls must support configurable pacing between chunk embedding requests to reduce free-tier rate-limit failures.
- Gemini embedding ingestion must behave like a queue: when a chunk hits a provider retry delay, the app should wait and retry that chunk instead of requiring the user to restart ingestion manually.
- Gemini embedding retries must be configurable separately from normal provider retries because large document ingestion can require many rate-limit waits on the free tier.
- Provider retry logic should respect explicit retry-delay guidance from provider errors when available.

### Documents

- Ingest `.pdf`, `.md`, and `.txt` files in the MVP.
- Recursively ingest supported files from a directory path.
- Ingest a single supported file path.
- Preserve relative source paths for files ingested from a directory so citations remain readable.
- Skip unsupported file types and report them in the ingest summary.
- Extract text from PDFs using an open-source Python library.
- Preserve source metadata for each chunk, including workspace, source file path, file hash, file type, chunk index, and page number when available.
- Future document types such as `.docx`, spreadsheets, and other formats are out of scope for the MVP but should be noted in the README as future extensions.

### Chunking

- Split extracted text into overlapping chunks.
- Provide configurable `--chunk-size` and `--chunk-overlap` options for `rag ingest`.
- Use sensible defaults if no chunk options are provided.
- Validate that chunk overlap is smaller than chunk size.
- Avoid producing empty chunks after whitespace cleanup.
- Store chunk text and metadata so citations and debug output can reference the original source.

### Idempotent Ingestion

- Compute a file hash for each ingested file.
- If a file has already been ingested into the workspace with the same hash, skip it by default.
- If a file exists with a new hash, replace that file's previous chunks and vectors for the active workspace.
- Provide `--force` on `rag ingest` to reprocess files even when their hashes are unchanged.
- Provide an ingest summary showing added, updated, skipped, unsupported, and failed files.
- During ingestion, print progress for the current file, chunk count, embedding progress, provider-request waits, retries, and vector storage.

### Storage

- Provide Dockerized storage for:
  - Postgres with pgvector
  - Qdrant
- Include a Docker Compose configuration for the storage services.
- Include database initialization for Postgres so the pgvector extension and required tables/indexes are created.
- Support vector store selection through `--store pgvector` and `--store qdrant`.
- Keep the storage layer behind an internal interface so retrieval and ingestion code can target either backend.
- Use SQLite for local CLI metadata such as active workspace, workspace list, ingestion history, provider/model metadata, and source records.
- Initialize and migrate SQLite metadata schema automatically when commands run.
- Store enough vector identifiers in SQLite to delete or replace a single file's chunks in either backend.
- Do not store API keys in SQLite, Postgres, Qdrant, or project files.
- Do not store API keys in local non-secret config. API keys may be read from the shell environment or a git-ignored `.env` file only.

### Retrieval

- `rag search <query>` must embed the query, retrieve relevant chunks from the selected vector store, and print retrieval results without asking an LLM to generate an answer.
- `rag search` must show source file, chunk index, score when available, and a short text preview.
- `rag search` must print progress before query embedding and vector-store search.
- Support `--top-k` for retrieval count.
- Validate that `--top-k` is a positive integer.
- Support `--debug` to show additional retrieval details where available.

### Question Answering

- `rag ask <question>` must retrieve relevant chunks and send the question plus retrieved context to the selected provider for generation.
- The default `ask` output must include:
  - final answer
  - source citations
  - a clear message when the answer cannot be found in the retrieved context
- The prompt must instruct the model to answer only from retrieved context and to say when the context is insufficient.
- Citations must reference source file and page number when available, otherwise source file and chunk index.
- `rag ask` must support `--top-k`.
- `rag ask` must support `--debug` to show retrieved chunks, scores, provider/model, token usage when available, and prompt preview.
- `rag ask` must print progress before query embedding, vector-store search, prompt-context construction, and answer generation.
- If no relevant chunks are retrieved, `rag ask` must not call the generation model and must explain that no context was found.

### Sources

- `rag sources` must list indexed sources for the selected workspace.
- The source list must include file path, file type, file hash or short hash, chunk count, provider, vector store, and ingestion time.

### Eval

- `rag eval <eval-file>` must run a small retrieval-focused evaluation suite.
- The eval file must be a simple local JSON or YAML file containing test cases with:
  - question
  - expected source file or files
  - optional expected answer notes
- Include an example eval file in the repository.
- For each test case, `rag eval` must run retrieval and report whether expected sources appeared in the top-k results.
- The eval output must include per-case results and an aggregate score.
- Eval must be usable for comparing provider, model, chunking, top-k, and vector store settings.
- Full LLM answer grading is out of scope for the MVP.

### Doctor

- `rag doctor` must check:
  - Python package import readiness where possible
  - Docker service connectivity for Postgres and Qdrant
  - pgvector availability in Postgres
  - Qdrant connectivity
  - presence of provider API keys without printing secret values
  - effective provider/store/model configuration
  - local SQLite metadata database readiness
- `rag doctor` must report actionable fixes for failed checks.

### Reset

- `rag reset` must clear vectors, chunks, and source metadata for the selected workspace and selected store.
- `rag reset` must require confirmation in interactive mode.
- `rag reset --no-interactive` must require an explicit confirmation flag such as `--yes`.
- Resetting one workspace must not delete another workspace's data.

### Project Documentation

- Include a README with:
  - project purpose
  - setup steps
  - dependency installation instructions
  - environment variables
  - Docker Compose startup instructions
  - example commands for OpenAI and Gemini
  - explanation of ingestion, chunking, embeddings, retrieval, generation, citations, and eval
  - troubleshooting notes
  - future extensions

## Constraints

- Use Python for the MVP.
- Provide project packaging through `pyproject.toml`.
- Expose the CLI as `rag` after installation.
- Use raw OpenAI and Gemini SDKs directly.
- Do not use LangChain, LlamaIndex, or similar RAG orchestration frameworks in the MVP.
- Use Docker Compose for Postgres/pgvector and Qdrant.
- Keep provider logic, document loading, chunking, storage, retrieval, generation, eval, and CLI orchestration separated into understandable modules.
- Keep the architecture easy to extend later with a Go service or additional document loaders.
- Do not commit secrets or write secrets into generated config files.
- The project should be runnable locally on Windows PowerShell.
- Keep generated runtime data such as `.rag/`, SQLite files, and local caches out of git.

## Edge Cases

- Missing provider API key must fail with a clear message naming the required environment variable.
- Missing API keys for inactive providers must not fail `rag doctor`; they should be reported as optional unless that provider is selected.
- Missing Docker service must be detected by `rag doctor`.
- Missing active workspace must prompt in interactive mode or fail in `--no-interactive` mode.
- Empty document directories must report that no supported files were found.
- Empty extracted document text must be skipped and reported.
- Unsupported files must be skipped without failing the whole ingest run.
- Corrupt or unreadable PDFs must be reported as failed files without stopping unrelated files from ingesting.
- Re-ingesting unchanged files must skip them based on file hash.
- Re-ingesting changed files must replace old chunks and vectors for that file in the workspace.
- Asking a question before any documents are indexed must fail with a helpful message.
- Search with no matching results must report that no relevant chunks were found.
- Provider API failures must be reported without hiding the underlying provider name and operation.
- Provider rate limits and transient network failures must retry a limited number of times before failing clearly.
- Gemini embedding rate limits must suggest waiting, increasing `gemini_embedding_delay_seconds`, increasing chunk size to reduce chunk count, or retrying later.
- Embedding dimension mismatches must fail before querying vector storage.
- Reset must protect against accidental deletion with confirmation behavior.
- Workspace names must reject unsafe characters or normalize to filesystem-safe identifiers.
- Invalid eval files must report the schema problem and not run partial evals silently.

## Assumptions

- Default chunk size and overlap can be chosen during implementation if they are documented in the README.
- Default model names can be chosen during implementation if they are configurable and documented.
- The eval file may use either JSON or YAML; implementation should choose one simple format first and document it.
- Local CLI metadata may live under a project-local directory such as `.rag/`.
- Exact retry counts and request timeouts can be chosen during implementation if they are documented.

## Out of Scope

- Web UI.
- User accounts, permissions, or hosted multi-user service behavior.
- LangChain, LlamaIndex, or other RAG frameworks.
- `.docx`, spreadsheet, HTML, image, audio, or video ingestion.
- LLM-based answer grading.
- Hybrid search, reranking, query rewriting, conversation memory, and agent tools.
- Cloud deployment.

## Definition of Done

- A developer can install project dependencies, start Dockerized Postgres/pgvector and Qdrant, and run `rag doctor`.
- A developer can run `rag init` and get local directories, example env/config files, and no committed secrets.
- A developer can install the project so the `rag` command is available.
- A developer can create and activate at least two workspaces.
- A developer can ingest `.pdf`, `.md`, and `.txt` files into one workspace without contaminating another workspace.
- Re-running ingest skips unchanged files using file hashes.
- Re-running ingest with `--force` reprocesses files even when hashes are unchanged.
- A developer can run `rag search` and see retrieved chunks with sources and scores.
- A developer can run `rag ask` with OpenAI and receive a grounded answer with citations.
- A developer can run `rag ask` with Gemini and receive a grounded answer with citations.
- A developer receives a clear error when searching with an embedding model that does not match the indexed vector dimensions.
- A developer can run `rag sources` and inspect indexed files and chunk counts.
- A developer can run `rag eval` against a local eval file and see per-case and aggregate retrieval results.
- A developer can reset one workspace without deleting another workspace.
- The README explains the RAG pipeline and includes working examples for both providers and both vector stores.
- Relevant tests or verification scripts cover workspace selection, file hashing behavior, chunking, provider missing-key errors, and storage interface behavior where practical.
