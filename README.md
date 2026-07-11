# RAG CLI

This project is a beginner-friendly command-line app for learning RAG, or retrieval-augmented generation.

RAG means:

1. Put your documents into the system.
2. Split the documents into smaller chunks.
3. Turn each chunk into an embedding, which is a list of numbers that captures meaning.
4. Store those embeddings in a vector database.
5. When you ask a question, search for the most relevant chunks.
6. Send those chunks to an AI model so it answers from your documents.
7. Show the answer with citations.

This project supports:

- OpenAI and Google Gemini
- `.pdf`, `.md`, and `.txt` documents
- Postgres with pgvector
- Qdrant
- multiple isolated workspaces
- retrieval-only search
- grounded question answering
- simple retrieval evals
- optional Inngest ingest observability

## What You Need

Install these first:

- Python 3.11 or newer
- Docker Desktop
- a Google Gemini API key if you want Gemini
- an OpenAI API key if you want OpenAI

You do not get free OpenAI or Gemini API access from Codex. Codex can help build this project, but this app needs your own provider API key.

## Gemini Models

As of July 5, 2026, Google’s Gemini API docs list these useful models for this project:

- `gemini-3.5-flash`: current stable Gemini 3 generation model. Use this as the default Gemini answer model.
- `gemini-3.1-pro`: preview model for harder reasoning and complex tasks.
- `gemini-3-flash`: preview fast model.
- `gemini-3.1-flash-lite`: stable low-cost model.
- `gemini-embedding-2`: latest embedding model for semantic search and RAG.
- `gemini-embedding-001`: earlier embedding model that is still useful for RAG.

For this project, start with:

```text
generation model: gemini-3.5-flash
embedding model:  gemini-embedding-2
```

Important: if you change embedding models after ingesting documents, you usually need to re-ingest. Vector dimensions can change between embedding models, and the app will stop you with a clear error instead of mixing incompatible vectors.

Official docs:

- [Gemini API models](https://ai.google.dev/gemini-api/docs/models)
- [Gemini embeddings](https://ai.google.dev/gemini-api/docs/embeddings)

## Supported Operating Systems

The app is designed to run on both Windows and Linux.

The code is cross-platform because it uses:

- Python `pathlib` for file paths
- Docker Compose for Postgres and Qdrant
- SQLite for local metadata
- environment variables for secrets

The examples below show both Windows PowerShell and Linux/macOS shell commands.

## Setup From Scratch

### Windows PowerShell

Open PowerShell in this project folder:

```powershell
cd "C:\Users\arsha\OneDrive\Documents\RAG Agent"
```

Create a Python virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the project:

```powershell
pip install -e ".[dev]"
```

Start the databases:

```powershell
docker compose up -d
```

Initialize local RAG files:

```powershell
rag init
```

Run a health check:

```powershell
rag doctor
```

`rag doctor` checks your API keys, Docker services, local config, Python packages, and metadata database.

Secrets can live in a project-local `.env` file. The app automatically loads `.env` from the project root, so you do not need to export keys every time if they are already saved there.

### Linux Or macOS

Open a terminal in the project folder:

```bash
cd "/path/to/RAG Agent"
```

Create a Python virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install the project:

```bash
pip install -e ".[dev]"
```

Start the databases:

```bash
docker compose up -d
```

Initialize local RAG files:

```bash
rag init
```

Run a health check:

```bash
rag doctor
```

## Set Up Gemini

Get a Gemini API key from Google AI Studio:

[Get a Gemini API key](https://aistudio.google.com/app/apikey)

Recommended: add it to `.env` in the project root:

```text
GOOGLE_API_KEY=your-gemini-api-key
```

Alternative: set it in PowerShell for the current terminal session:

```powershell
$env:GOOGLE_API_KEY="your-gemini-api-key"
```

Alternative: set it in Linux/macOS for the current terminal session:

```bash
export GOOGLE_API_KEY="your-gemini-api-key"
```

You can also use:

```powershell
$env:GEMINI_API_KEY="your-gemini-api-key"
```

Or on Linux/macOS:

```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

Tell the app to use Gemini by default:

```powershell
rag config set provider gemini
rag config set gemini_generation_model gemini-3.5-flash
rag config set gemini_embedding_model gemini-embedding-2
rag config set gemini_embedding_retries 20
rag config set gemini_embedding_delay_seconds 0.7
```

Check the config:

```powershell
rag config show
```

Then run:

```powershell
rag doctor
```

If Gemini is configured correctly, the Gemini API key check should pass.

## Set Up OpenAI

Recommended: add it to `.env` in the project root:

```text
OPENAI_API_KEY=your-openai-api-key
```

Alternative: set your OpenAI API key in PowerShell for the current terminal session:

```powershell
$env:OPENAI_API_KEY="your-openai-api-key"
```

Linux/macOS:

```bash
export OPENAI_API_KEY="your-openai-api-key"
```

Tell the app to use OpenAI:

```powershell
rag config set provider openai
rag config set openai_generation_model gpt-4o-mini
rag config set openai_embedding_model text-embedding-3-small
```

Run:

```powershell
rag doctor
```

## Choose a Vector Store

This project supports two vector stores.

Use Postgres with pgvector:

```powershell
rag config set store pgvector
```

Use Qdrant:

```powershell
rag config set store qdrant
```

For learning, try both. Postgres teaches you a production-style relational database with vector search. Qdrant teaches you a purpose-built vector database.

## Workspaces

A workspace is a separate document collection.

Use workspaces when you want to keep different tasks separate, for example:

- `research-notes`
- `company-docs`
- `course-material`
- `personal-pdfs`

Create a workspace:

```powershell
rag workspace create research-notes
```

Make it active:

```powershell
rag workspace use research-notes
```

See all workspaces:

```powershell
rag workspace list
```

See the active workspace:

```powershell
rag workspace current
```

Most commands use the active workspace automatically. You can override it:

```powershell
rag ask "What is this about?" --workspace company-docs
```

## Add Documents

Create a folder for documents:

```powershell
mkdir data\raw
```

Put `.pdf`, `.md`, or `.txt` files inside `data\raw`.

Then ingest them:

```powershell
rag ingest .\data\raw
```

What ingest does:

1. Finds supported files.
2. Extracts text.
3. Splits text into chunks.
4. Embeds each chunk using OpenAI or Gemini.
5. Stores vectors in pgvector or Qdrant.
6. Stores source metadata locally in SQLite.

During ingest, the CLI prints progress messages like:

```text
... Loading data/raw/example.pdf
... Chunking example.pdf
... Embedding 42 chunks from example.pdf
... Embedding chunk 1/42 with Gemini.
... Waiting 1.2s before next Gemini embedding request.
... embedding chunk 8/42 hit a retryable error; waiting 52.0s before retry 2/30.
... Storing 42 vectors for example.pdf
```

If it says it is waiting, it is not stuck. It is respecting provider rate limits.

Ingest with Gemini and Qdrant explicitly:

```powershell
rag ingest .\data\raw --provider gemini --store qdrant
```

Ingest with custom chunk settings:

```powershell
rag ingest .\data\raw --chunk-size 800 --chunk-overlap 120
```

If you are using Gemini's free tier and ingesting PDFs, prefer larger chunks so the app makes fewer embedding requests:

```powershell
rag ingest .\data\raw --chunk-size 3000 --chunk-overlap 300
```

Gemini free-tier embedding quota can be tight for large PDFs. The app waits between Gemini embedding calls by default. You can slow it down further:

```powershell
rag config set gemini_embedding_delay_seconds 1.2
```

The app also treats Gemini embedding as a queue. If Gemini returns a retry delay, such as "retry in 52s", the app waits and retries that same chunk instead of making you restart the whole ingest. For large PDFs on the free tier, you can raise the chunk retry budget:

```powershell
rag config set gemini_embedding_retries 30
```

Reprocess files even if they have not changed:

```powershell
rag ingest .\data\raw --force
```

By default, repeated ingestion skips unchanged files using file hashes.

## Search Before Asking

Search only retrieves chunks. It does not call the answer model.

```powershell
rag search "vector databases"
```

Use this when debugging retrieval. If search results are poor, `ask` will probably be poor too.

Show more results:

```powershell
rag search "vector databases" --top-k 10
```

Show more detail:

```powershell
rag search "vector databases" --debug
```

## Ask Questions

Ask a question:

```powershell
rag ask "What do my documents say about chunking?"
```

The app will:

1. Embed your question.
2. Retrieve relevant chunks.
3. Send those chunks to the generation model.
4. Print an answer.
5. Print citations.

During `ask`, the CLI prints progress messages like:

```text
... Embedding query with gemini model gemini-embedding-2.
... Searching pgvector for top 5 chunks.
... Building prompt context from 5 retrieved chunks.
... Generating answer with Gemini model gemini-3.5-flash.
```

If it is slow, it is usually waiting on the provider for query embedding or answer generation. If Gemini returns a rate-limit retry delay, the CLI prints the wait before retrying.

Ask with Gemini:

```powershell
rag ask "Summarize the indexed documents" --provider gemini
```

Ask with Gemini and Qdrant:

```powershell
rag ask "Summarize the indexed documents" --provider gemini --store qdrant
```

Show debug information:

```powershell
rag ask "What are the main points?" --debug
```

Debug output includes retrieved chunks, scores, model names, token usage when available, and a prompt preview.

## See Indexed Sources

List files indexed in the active workspace:

```powershell
rag sources
```

This shows file path, type, short hash, chunk count, provider, store, and ingestion time.

## Eval Retrieval

Eval checks whether search finds the sources you expected.

Example eval file:

```yaml
tests:
  - question: "What is this document about?"
    expected_sources:
      - "example.md"
```

Run:

```powershell
rag eval .\examples\eval.sample.yaml
```

This does not grade generated answers. It only checks retrieval quality.

## Optional Inngest Ingest Observability

Use this when you want to watch a long ingest job as a background workflow instead of relying only on terminal output.

Inngest helps because it shows each run, step, retry, wait, and failure in a local Dev Server UI. This is especially useful with Gemini free-tier rate limits because waits and retries are visible instead of looking like the app is stuck.

This project uses Inngest locally only for the first version. Inngest Cloud is not required.

Optional local Inngest values can live in `.env`:

```text
INNGEST_DEV=1
INNGEST_EVENT_KEY=local
INNGEST_SIGNING_KEY=signkey-test-00000000000000000000000000000000
```

These are not OpenAI or Gemini API keys. They are only used for the local Inngest Dev Server handshake. If `INNGEST_SIGNING_KEY` is missing or invalid during local dev, the app falls back to the local test key shown above. If you provide a valid `signkey-test-<hex>` or `signkey-prod-<hex>` value, the app uses yours.

Use normal sync ingest when you want the simplest path:

```bash
rag ingest ./data/raw
```

Use async Inngest ingest when you want deeper observability:

```bash
rag ingest-async ./data/raw
```

### Start The RAG Inngest App Server

Open terminal 1:

```bash
rag ingest-server
```

This starts the local FastAPI app and serves the Inngest endpoint at:

```text
http://localhost:8000/api/inngest
```

### Start The Inngest Dev Server

Open terminal 2 and use Docker Compose:

```bash
docker compose up -d inngest
```

Then open:

```text
http://localhost:8288
```

Alternative if you have the Inngest CLI installed:

```bash
inngest dev -u http://localhost:8000/api/inngest
```

### Check Inngest Setup

```bash
rag inngest-doctor
```

It checks:

- the local RAG Inngest app endpoint
- the local Inngest Dev Server

### Submit An Async Ingest Job

Open terminal 3:

```bash
rag ingest-async ./data/raw --chunk-size 3000 --chunk-overlap 300
```

The event payload includes workspace, path, provider, store, model names, chunk settings, force flag, and timestamp. It does not include API keys, full document text, or embeddings.

In the Inngest UI, look for the `rag-ingest-requested` function. You should see steps for validation, discovery, each file ingest, retries/waits, storage, and final summary. If Gemini asks the app to wait because of quota, that wait appears in the run logs/timeline.

Avoid running sync and async ingestion against the same workspace and same files at the same time. The first local version processes async files sequentially to keep free-tier API usage predictable.

## Reset a Workspace

Clear vectors and source metadata for the active workspace and active store:

```powershell
rag reset
```

For scripts:

```powershell
rag reset --no-interactive --yes
```

Resetting one workspace does not delete another workspace.

## Common Problems

Missing Gemini key:

```text
missing; set GOOGLE_API_KEY or GEMINI_API_KEY
```

Fix:

```powershell
$env:GOOGLE_API_KEY="your-gemini-api-key"
```

Docker services are not running:

```text
run docker compose up -d and retry
```

Fix:

```powershell
docker compose up -d
```

No documents indexed:

```text
No documents are indexed for this workspace/store yet.
```

Fix:

```powershell
rag ingest .\data\raw
```

`rag ask` feels stuck:

```text
... Embedding query with gemini model gemini-embedding-2.
```

This means the app is waiting on the embedding provider before it can search your documents. On Gemini free tier, this can wait if embedding quota is temporarily exhausted.

```text
... Generating answer with Gemini model gemini-3.5-flash.
```

This means retrieval already finished and the generation model is writing the final answer. Try a lower `--top-k` if the prompt context is too large:

```powershell
rag ask "What is the chapter 1 summary?" --top-k 3 --debug
```

Embedding dimension mismatch:

```text
Embedding model/dimension mismatch.
```

Fix:

```powershell
rag reset
rag ingest .\data\raw
```

Gemini quota or `RESOURCE_EXHAUSTED` during ingest:

```text
Quota exceeded for metric: embed_content_free_tier_requests
```

Fixes:

```powershell
rag config set gemini_embedding_retries 30
rag config set gemini_embedding_delay_seconds 1.2
rag ingest .\data\raw --chunk-size 3000 --chunk-overlap 300
```

If the quota message includes a retry delay, the app will wait and retry automatically while it still has retry attempts left. This is normal on the free tier and does not mean the project is broken.

## Beginner Mental Model

Think of the app as three layers:

1. Documents: your PDFs, Markdown files, and text files.
2. Retrieval: embeddings plus vector database search.
3. Answering: Gemini or OpenAI writes an answer using retrieved chunks.

When something goes wrong, debug in that order:

1. Did `rag sources` show your files?
2. Did `rag search "your topic"` find useful chunks?
3. Did `rag ask "your question" --debug` send useful context to the model?

## Local Web Application

The React Web application provides the same learning workflow through a browser: workspaces, managed document uploads, synchronous or Inngest ingestion, detailed activity, source/chunk inspection, retrieval search, grounded questions with citations, saved independent question history, evaluation suites, settings, and system health.

The first version is local and single-user. It has no authentication, so the server binds to `127.0.0.1` by default. Do not expose it to a public network.

### Install Web Dependencies

Install the Python project as described above, then install and build the frontend:

```powershell
cd web
npm install
npm run build
cd ..
```

The same commands work in WSL/Linux. Node.js 20 or newer is recommended.

### Start The Web Application

Start the selected vector database first:

```powershell
docker compose up -d
```

Then activate the Python virtual environment and run:

```powershell
rag web
```

Open `http://127.0.0.1:8000`. The production frontend bundle is served by FastAPI. The same server also exposes the versioned API under `/api/v1`, OpenAPI documentation at `/docs`, and the Inngest endpoint at `/api/inngest`.

For frontend development, use two terminals:

```powershell
# Terminal 1, repository root
rag web --reload

# Terminal 2
cd web
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` requests to FastAPI.

### Managed Uploads And Ingestion Modes

Browser uploads are copied into `.rag/uploads/<workspace>/`. Indexed vectors and source metadata are separate from those managed copies. Source deletion and workspace reset therefore ask separately whether managed files should also be deleted.

- **Synchronous** ingestion runs inside the local FastAPI process. Restarting that process interrupts the job.
- **Inngest** ingestion submits durable work to the local Inngest Dev Server. Start the Inngest service with Docker Compose and open `http://localhost:8288` for its detailed run timeline.

Both modes create local activity records. Progress remains available after a page refresh. Avoid running conflicting ingestion and reset operations against the same workspace and store.

### Provider Keys In The Web UI

Settings accepts OpenAI and Gemini keys as write-only values and stores them in the git-ignored project `.env`. Existing key values are never returned to the browser. Shell environment variables still take precedence over `.env` values.

### Chat History

Chat sessions and turns are saved locally for browsing, but every question is an independent RAG query. Earlier turns are not added to retrieval or generation context. Conversation-aware retrieval and memory are planned as a later backend milestone.

### Web Troubleshooting

- If the page does not load, run `npm run build` in `web/` and restart `rag web`.
- If upload works but ingestion fails, open System Health and verify the selected provider key and vector store.
- If Inngest submission fails, start both `rag web` and the `inngest` Docker Compose service.
- Upload defaults are 25 files per request and 25 MiB per file. Override them with `RAG_WEB_MAX_UPLOAD_FILES` and `RAG_WEB_MAX_UPLOAD_BYTES`.

## Future Extensions

Later versions can add:

- `.docx`
- spreadsheets
- HTML
- image OCR
- hybrid search
- reranking
- query rewriting
- conversation memory
- web UI
- cloud deployment
- optional LangChain or LlamaIndex versions after the raw SDK pipeline is understood
