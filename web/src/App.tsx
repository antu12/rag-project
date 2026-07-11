import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, BookOpen, Bot, ChevronRight, CircleHelp, Database, FileSearch, Files, FlaskConical, HeartPulse, Home, KeyRound, Menu, MessageSquare, Plus, RefreshCw, Search, Send, Settings, Upload, X } from "lucide-react";
import { Link, NavLink, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, Bootstrap, Hit, Job, JobEvent, Source } from "./api";

const nav = [
  ["/overview", "Overview", Home], ["/documents", "Documents", Files], ["/search", "Search", Search],
  ["/chat", "Chat", MessageSquare], ["/evaluations", "Evaluations", FlaskConical], ["/activity", "Activity", Activity],
  ["/settings", "Settings", Settings], ["/health", "System Health", HeartPulse],
] as const;

type WorkspaceContext = { bootstrap: Bootstrap; workspace: string; refresh: () => void };
let currentContext: WorkspaceContext | null = null;
function useWorkspace() { if (!currentContext) throw new Error("Workspace context is unavailable"); return currentContext; }

export default function App() {
  const queryClient = useQueryClient();
  const bootstrap = useQuery({ queryKey: ["bootstrap"], queryFn: api.bootstrap });
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const refresh = () => { void queryClient.invalidateQueries(); };
  if (bootstrap.isLoading) return <Loading label="Loading RAG Learning Studio" />;
  if (bootstrap.error || !bootstrap.data) return <Fatal error={bootstrap.error} />;
  const workspace = bootstrap.data.active_workspace || bootstrap.data.workspaces[0]?.name || "";
  currentContext = { bootstrap: bootstrap.data, workspace, refresh };
  const activate = async (value: string) => { await api.activateWorkspace(value); refresh(); };
  const create = async (event: FormEvent) => { event.preventDefault(); if (!name.trim()) return; await api.createWorkspace(name.trim()); await activate(name.trim()); setName(""); setCreating(false); };
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><BookOpen size={20} /> RAG Learning Studio</div>
      <nav className="nav" aria-label="Primary navigation">{nav.map(([to, label, Icon]) => <NavLink key={to} to={to}><Icon size={17} />{label}</NavLink>)}</nav>
      <div className="subtle" style={{ marginTop: "auto", color: "#9fb4ad" }}>Local single-user mode<br />API v{bootstrap.data.version}</div>
    </aside>
    <main className="main">
      <nav className="mobile-nav" aria-label="Mobile navigation">{nav.map(([to, label, Icon]) => <NavLink key={to} to={to} title={label}><Icon size={18} /><span className="sr-only">{label}</span></NavLink>)}</nav>
      <header className="topbar">
        <div><div className="subtle">Active workspace</div>{creating ? <form onSubmit={create} className="toolbar" style={{ margin: 0 }}><input autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="workspace-name" aria-label="Workspace name" /><button className="button primary">Create</button><button type="button" className="button icon-button" onClick={() => setCreating(false)} title="Cancel"><X size={16} /></button></form> : <select aria-label="Active workspace" value={workspace} onChange={e => void activate(e.target.value)} disabled={!workspace}><option value="">No workspace</option>{bootstrap.data.workspaces.map(item => <option key={item.name}>{item.name}</option>)}</select>}</div>
        <div className="toolbar" style={{ margin: 0 }}><span className="subtle">{String(bootstrap.data.config.provider)} / {String(bootstrap.data.config.store)}</span><button className="button icon-button" onClick={() => setCreating(true)} title="Create workspace"><Plus size={17} /></button></div>
      </header>
      <div className="content">
        {!workspace ? <FirstRun onCreate={() => setCreating(true)} /> : <Routes>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/documents/:sourceId" element={<SourceDetail />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:sessionId" element={<ChatPage />} />
          <Route path="/evaluations" element={<Evaluations />} />
          <Route path="/evaluations/:runId" element={<ActivityDetail />} />
          <Route path="/activity" element={<ActivityPage />} />
          <Route path="/activity/:jobId" element={<ActivityDetail />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/health" element={<HealthPage />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>}
      </div>
    </main>
  </div>;
}

function Page({ title, description, action, children }: { title: string; description?: string; action?: ReactNode; children: ReactNode }) {
  return <><div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "start" }}><div><h1>{title}</h1>{description && <p className="subtle">{description}</p>}</div>{action}</div>{children}</>;
}

function Overview() {
  const { workspace, bootstrap } = useWorkspace();
  const sources = useQuery({ queryKey: ["sources", workspace], queryFn: () => api.sources(workspace) });
  const jobs = useQuery({ queryKey: ["jobs", workspace], queryFn: () => api.jobs(workspace), refetchInterval: 5000 });
  const sessions = useQuery({ queryKey: ["sessions", workspace], queryFn: () => api.sessions(workspace) });
  const ws = bootstrap.workspaces.find(item => item.name === workspace);
  return <Page title="Overview" description="Your current RAG workspace at a glance.">
    <div className="grid stats">
      <Stat label="Indexed sources" value={ws?.source_count ?? sources.data?.length ?? 0} />
      <Stat label="Stored chunks" value={ws?.chunk_count ?? 0} />
      <Stat label="Question sessions" value={sessions.data?.length ?? 0} />
      <Stat label="Active or failed jobs" value={jobs.data?.filter(j => !["succeeded", "cancelled"].includes(j.status)).length ?? 0} />
    </div>
    <div className="toolbar"><Link className="button primary" to="/documents"><Upload size={16} />Upload documents</Link><Link className="button" to="/chat"><MessageSquare size={16} />Ask a question</Link><Link className="button" to="/search"><Search size={16} />Search chunks</Link><Link className="button" to="/evaluations"><FlaskConical size={16} />Run evaluation</Link></div>
    <section className="panel"><h2>Recent activity</h2>{jobs.isLoading ? <Loading label="Loading activity" compact /> : jobs.data?.length ? <JobTable jobs={jobs.data.slice(0, 8)} /> : <Empty title="No activity yet" detail="Upload a document to see the RAG pipeline in motion." />}</section>
  </Page>;
}

function Documents() {
  const { workspace, refresh } = useWorkspace();
  const queryClient = useQueryClient();
  const sources = useQuery({ queryKey: ["sources", workspace], queryFn: () => api.sources(workspace) });
  const uploads = useQuery({ queryKey: ["uploads", workspace], queryFn: () => api.uploads(workspace) });
  const [files, setFiles] = useState<File[]>([]);
  const [mode, setMode] = useState("synchronous");
  const [force, setForce] = useState(false);
  const [chunkSize, setChunkSize] = useState(1000);
  const [overlap, setOverlap] = useState(150);
  const navigate = useNavigate();
  const uploadMutation = useMutation({ mutationFn: () => api.upload(workspace, files), onSuccess: data => { setFiles([]); void queryClient.invalidateQueries({ queryKey: ["uploads", workspace] }); const ids = data.files.filter(item => item.status === "uploaded").map(item => item.id); if (ids.length) ingestMutation.mutate(ids); } });
  const ingestMutation = useMutation({ mutationFn: (ids: string[]) => api.ingest(workspace, { upload_ids: ids, execution_mode: mode, force, chunk_size: chunkSize, chunk_overlap: overlap }), onSuccess: job => { refresh(); navigate(`/activity/${job.id}`); } });
  const error = uploadMutation.error || ingestMutation.error;
  return <Page title="Documents" description="Upload managed copies, ingest them, and inspect indexed chunks.">
    <div className="grid two-col" style={{ marginTop: 20 }}>
      <section className="panel"><h2>Upload and ingest</h2><label className="dropzone"><Upload size={24} style={{ margin: "0 auto 8px" }} /><strong>Choose PDF, Markdown, or text files</strong><div className="subtle">Files are copied into this workspace.</div><input type="file" multiple accept=".pdf,.md,.txt" style={{ marginTop: 14 }} onChange={e => setFiles(Array.from(e.target.files || []))} /></label>
        {files.length > 0 && <ul>{files.map(file => <li key={file.name}>{file.name} <span className="subtle">({formatBytes(file.size)})</span></li>)}</ul>}
        <div className="toolbar"><div className="field"><label>Execution mode</label><select value={mode} onChange={e => setMode(e.target.value)}><option value="synchronous">Synchronous</option><option value="inngest">Inngest</option></select></div><div className="field"><label>Chunk size</label><input type="number" min={1} value={chunkSize} onChange={e => setChunkSize(Number(e.target.value))} /></div><div className="field"><label>Overlap</label><input type="number" min={0} max={chunkSize - 1} value={overlap} onChange={e => setOverlap(Number(e.target.value))} /></div></div>
        <label><input type="checkbox" style={{ width: "auto", marginRight: 8 }} checked={force} onChange={e => setForce(e.target.checked)} />Force re-ingestion of unchanged files</label>
        {error && <ErrorNotice error={error} />}
        <button className="button primary" style={{ marginTop: 16 }} disabled={!files.length || overlap >= chunkSize || uploadMutation.isPending || ingestMutation.isPending} onClick={() => uploadMutation.mutate()}>{uploadMutation.isPending || ingestMutation.isPending ? "Submitting…" : "Upload and ingest"}</button>
      </section>
      <section className="panel"><h2>Managed uploads</h2>{uploads.data?.length ? <div className="table-wrap"><table><thead><tr><th>Name</th><th>Size</th><th>Added</th></tr></thead><tbody>{uploads.data.map(item => <tr key={item.id}><td>{item.original_name}</td><td>{formatBytes(item.size_bytes)}</td><td>{formatDate(item.created_at)}</td></tr>)}</tbody></table></div> : <Empty title="No managed uploads" detail="Uploaded files remain separate from their vector index records." />}</section>
    </div>
    <section style={{ marginTop: 24 }}><h2>Indexed sources</h2>{sources.isLoading ? <Loading compact label="Loading sources" /> : sources.data?.length ? <SourceTable sources={sources.data} /> : <Empty title="No indexed sources" detail="Upload and ingest a document to begin searching and asking questions." />}</section>
  </Page>;
}

function SourceDetail() {
  const { workspace } = useWorkspace(); const { sourceId = "" } = useParams();
  const source = useQuery({ queryKey: ["source", workspace, sourceId], queryFn: () => fetch(`/api/v1/workspaces/${encodeURIComponent(workspace)}/sources/${encodeURIComponent(sourceId)}`).then(readJson) });
  const chunks = useQuery({ queryKey: ["chunks", workspace, sourceId], queryFn: () => fetch(`/api/v1/workspaces/${encodeURIComponent(workspace)}/sources/${encodeURIComponent(sourceId)}/chunks`).then(readJson) });
  if (source.isLoading) return <Loading label="Loading source" />;
  if (source.error) return <ErrorNotice error={source.error} />;
  return <Page title={source.data.source_path} description={`${source.data.file_type.toUpperCase()} · ${source.data.chunk_count} chunks · ${source.data.embedding_model}`}><div className="panel" style={{ marginTop: 20 }}><div className="subtle">SHA-256</div><code>{source.data.file_hash}</code></div><section style={{ marginTop: 24 }}><h2>Chunks</h2>{chunks.data?.items.map((chunk: any) => <article className="panel" key={chunk.id} style={{ marginBottom: 10 }}><div className="subtle">Chunk {chunk.chunk_index}{chunk.page_number ? ` · Page ${chunk.page_number}` : ""}</div><p style={{ whiteSpace: "pre-wrap" }}>{chunk.text}</p></article>)}</section></Page>;
}

function SearchPage() {
  const { workspace } = useWorkspace(); const [query, setQuery] = useState(""); const [topK, setTopK] = useState(5); const [debug, setDebug] = useState(false);
  const search = useMutation({ mutationFn: () => api.search(workspace, { query, top_k: topK }) });
  return <Page title="Search playground" description="Inspect retrieval before asking a generation model."><form className="toolbar" onSubmit={e => { e.preventDefault(); search.mutate(); }}><div className="field" style={{ flex: 1 }}><label htmlFor="query">Query</label><input id="query" value={query} onChange={e => setQuery(e.target.value)} placeholder="What do the documents say about…" /></div><div className="field" style={{ minWidth: 90 }}><label htmlFor="topk">Top K</label><input id="topk" type="number" min={1} max={100} value={topK} onChange={e => setTopK(Number(e.target.value))} /></div><button className="button primary" disabled={!query.trim() || search.isPending}><Search size={16} />{search.isPending ? "Searching…" : "Search"}</button></form>
    <label><input type="checkbox" style={{ width: "auto", marginRight: 8 }} checked={debug} onChange={e => setDebug(e.target.checked)} />Show full chunk text and vector IDs</label>{search.error && <ErrorNotice error={search.error} />}
    {search.data && <section className="panel" style={{ marginTop: 20 }}><h2>Retrieved chunks</h2><div className="subtle">{search.data.progress.join(" → ")}</div>{search.data.results.length ? search.data.results.map((hit, i) => <HitView key={hit.vector_id} hit={hit} rank={i + 1} debug={debug} />) : <Empty title="No relevant chunks" detail="Try a different query or inspect the indexed sources." />}</section>}
  </Page>;
}

function ChatPage() {
  const { workspace, refresh } = useWorkspace(); const { sessionId } = useParams(); const navigate = useNavigate();
  const sessions = useQuery({ queryKey: ["sessions", workspace], queryFn: () => api.sessions(workspace) });
  const session = useQuery({ queryKey: ["session", workspace, sessionId], queryFn: () => api.session(workspace, sessionId!), enabled: !!sessionId, refetchInterval: 2500 });
  const [question, setQuestion] = useState(""); const [activeJob, setActiveJob] = useState<Job | null>(null);
  const create = useMutation({ mutationFn: () => api.createSession(workspace), onSuccess: item => { refresh(); navigate(`/chat/${item.id}`); } });
  const ask = useMutation({ mutationFn: () => api.ask(sessionId!, question, {}), onSuccess: data => { setQuestion(""); setActiveJob(data.job); void session.refetch(); } });
  useEffect(() => { if (!activeJob || ["succeeded", "failed"].includes(activeJob.status)) return; const timer = setInterval(async () => { const job = await api.job(activeJob.id); setActiveJob(job); if (["succeeded", "failed"].includes(job.status)) void session.refetch(); }, 1000); return () => clearInterval(timer); }, [activeJob?.id, activeJob?.status]);
  return <Page title="Chat" description="History is saved, while every question remains an independent RAG query." action={<button className="button" onClick={() => create.mutate()}><Plus size={16} />New session</button>}><div className="chat-layout" style={{ marginTop: 20 }}><aside className="sessions" aria-label="Chat sessions">{sessions.data?.map(item => <Link className={`session-item ${item.id === sessionId ? "active" : ""}`} to={`/chat/${item.id}`} key={item.id}>{item.title}<div className="subtle">{formatDate(item.updated_at)}</div></Link>)}{!sessions.data?.length && <div className="empty">No saved sessions</div>}</aside><section className="conversation">{!sessionId ? <Empty title="Choose or create a session" detail="Saved sessions let you browse old independent questions." /> : <><div className="messages">{session.data?.turns?.map((turn: any) => <div key={turn.id}><div className="message question">{turn.question}</div><div className="message answer"><strong>Answer</strong>{turn.status === "running" ? <p>Working through retrieval and generation…</p> : turn.error ? <ErrorNotice error={new Error(turn.error.message)} /> : <><div className="markdown-answer"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>{turn.answer || ""}</ReactMarkdown></div>{turn.citations?.length > 0 && <div className="subtle">Sources: {turn.citations.join(" · ")}</div>}<details><summary>Retrieval details</summary>{turn.hits?.map((hit: Hit, i: number) => <HitView key={hit.vector_id} hit={hit} rank={i + 1} debug />)}</details></>}</div></div>)}{activeJob && <JobProgress job={activeJob} />}</div><form className="composer" onSubmit={e => { e.preventDefault(); if (question.trim()) ask.mutate(); }}><textarea aria-label="Question" value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ask a grounded question about this workspace…" /><button className="button primary" disabled={!question.trim() || ask.isPending || activeJob?.status === "running"}><Send size={16} />Ask</button></form></>}</section></div></Page>;
}

function Evaluations() {
  const { workspace, refresh } = useWorkspace(); const navigate = useNavigate(); const suites = useQuery({ queryKey: ["suites", workspace], queryFn: () => api.suites(workspace) });
  const [name, setName] = useState(""); const [question, setQuestion] = useState(""); const [source, setSource] = useState("");
  const create = useMutation({ mutationFn: () => api.createSuite({ workspace, name, cases: [{ question, expected_sources: source.split(",").map(v => v.trim()).filter(Boolean) }] }), onSuccess: () => { setName(""); setQuestion(""); setSource(""); refresh(); } });
  const run = useMutation({ mutationFn: (id: string) => api.runSuite(workspace, id), onSuccess: job => navigate(`/evaluations/${job.id}`) });
  return <Page title="Evaluations" description="Measure whether expected sources appear in retrieved results."><div className="grid two-col" style={{ marginTop: 20 }}><form className="panel" onSubmit={e => { e.preventDefault(); create.mutate(); }}><h2>Create a suite</h2><Field label="Suite name"><input value={name} onChange={e => setName(e.target.value)} /></Field><Field label="Question"><textarea value={question} onChange={e => setQuestion(e.target.value)} /></Field><Field label="Expected source paths (comma separated)"><input value={source} onChange={e => setSource(e.target.value)} /></Field>{create.error && <ErrorNotice error={create.error} />}<button className="button primary" disabled={!name || !question || !source}>Save suite</button></form><section><h2>Saved suites</h2>{suites.data?.length ? suites.data.map(item => <div className="panel" key={item.id} style={{ marginBottom: 10 }}><strong>{item.name}</strong><div className="subtle">{item.cases.length} case(s) · Updated {formatDate(item.updated_at)}</div><button className="button" style={{ marginTop: 12 }} onClick={() => run.mutate(item.id)}><FlaskConical size={16} />Run evaluation</button></div>) : <Empty title="No evaluation suites" detail="Create a retrieval-focused test case to compare RAG settings." />}</section></div></Page>;
}

function ActivityPage() {
  const { workspace } = useWorkspace(); const jobs = useQuery({ queryKey: ["jobs", workspace], queryFn: () => api.jobs(workspace), refetchInterval: 3000 });
  return <Page title="Activity" description="Persistent operations, progress, waits, retries, and outcomes.">{jobs.isLoading ? <Loading label="Loading jobs" /> : jobs.data?.length ? <div style={{ marginTop: 20 }}><JobTable jobs={jobs.data} /></div> : <Empty title="No jobs yet" detail="Ingestion, questions, and evaluations will appear here." />}</Page>;
}

function ActivityDetail() {
  const params = useParams(); const id = params.jobId || params.runId || ""; const job = useQuery({ queryKey: ["job", id], queryFn: () => api.job(id), refetchInterval: query => ["succeeded", "partially_succeeded", "failed", "cancelled", "interrupted"].includes(query.state.data?.status || "") ? false : 1000 });
  if (job.isLoading) return <Loading label="Loading job" />; if (job.error || !job.data) return <ErrorNotice error={job.error} />;
  return <Page title={`${capitalize(job.data.operation)} job`} description={`${job.data.execution_mode} · ${job.data.workspace}`} action={<Status value={job.data.status} />}><JobProgress job={job.data} detailed />{job.data.result && <section className="panel" style={{ marginTop: 18 }}><h2>Result</h2><pre style={{ overflow: "auto", whiteSpace: "pre-wrap" }}>{JSON.stringify(job.data.result, null, 2)}</pre></section>}</Page>;
}

function SettingsPage() {
  const { bootstrap, refresh } = useWorkspace(); const config = useQuery({ queryKey: ["config"], queryFn: api.config });
  const [values, setValues] = useState<Record<string, unknown>>({}); const [provider, setProvider] = useState("openai"); const [secret, setSecret] = useState("");
  const save = useMutation({ mutationFn: () => api.patchConfig(values), onSuccess: () => { setValues({}); refresh(); } }); const saveSecret = useMutation({ mutationFn: () => api.setSecret(provider, secret), onSuccess: () => { setSecret(""); refresh(); } });
  const keys = ["provider", "store", "openai_embedding_model", "openai_generation_model", "gemini_embedding_model", "gemini_generation_model", "chunk_size", "chunk_overlap", "top_k", "request_timeout_seconds", "request_retries", "gemini_embedding_retries", "gemini_embedding_delay_seconds"];
  return <Page title="Settings" description="Effective local configuration and write-only provider credentials."><section className="panel" style={{ marginTop: 20 }}><h2>Provider secrets</h2><div className="toolbar"><div className="field"><label>Provider</label><select value={provider} onChange={e => setProvider(e.target.value)}><option value="openai">OpenAI ({bootstrap.secrets.openai.configured ? "configured" : "missing"})</option><option value="gemini">Gemini ({bootstrap.secrets.gemini.configured ? "configured" : "missing"})</option></select></div><div className="field" style={{ flex: 1 }}><label>New API key</label><input type="password" autoComplete="new-password" value={secret} onChange={e => setSecret(e.target.value)} placeholder="Stored in the project .env; existing values are never returned" /></div><button className="button primary" disabled={!secret || saveSecret.isPending} onClick={() => saveSecret.mutate()}><KeyRound size={16} />Set key</button></div>{saveSecret.error && <ErrorNotice error={saveSecret.error} />}</section>
    <section style={{ marginTop: 24 }}><h2>Application configuration</h2>{config.data && <div className="table-wrap"><table><thead><tr><th>Setting</th><th>Effective value</th><th>Source</th></tr></thead><tbody>{keys.map(key => <tr key={key}><td>{key}</td><td><input value={String(values[key] ?? config.data.effective[key] ?? "")} onChange={e => setValues(v => ({ ...v, [key]: e.target.value }))} /></td><td>{config.data.sources[key]}</td></tr>)}</tbody></table></div>}<div className="toolbar"><button className="button primary" disabled={!Object.keys(values).length || save.isPending} onClick={() => save.mutate()}>Save changed settings</button></div>{save.error && <ErrorNotice error={save.error} />}</section><ResetPanel /></Page>;
}

function ResetPanel() {
  const { workspace, bootstrap, refresh } = useWorkspace(); const [confirmation, setConfirmation] = useState(""); const [deleteUploads, setDeleteUploads] = useState(false); const store = String(bootstrap.config.store);
  const reset = useMutation({ mutationFn: () => api.reset(workspace, store, confirmation, deleteUploads), onSuccess: () => { setConfirmation(""); refresh(); } });
  return <section className="panel" style={{ marginTop: 24, borderColor: "#d9aaaa" }}><h2>Reset workspace store</h2><p className="subtle">Deletes vectors and source metadata for <strong>{workspace}</strong> in <strong>{store}</strong>. Other workspaces are preserved.</p><div className="toolbar"><div className="field"><label>Type {workspace} to confirm</label><input value={confirmation} onChange={e => setConfirmation(e.target.value)} /></div><label><input type="checkbox" style={{ width: "auto", marginRight: 8 }} checked={deleteUploads} onChange={e => setDeleteUploads(e.target.checked)} />Also delete managed copies</label><button className="button danger" disabled={confirmation !== workspace || reset.isPending} onClick={() => reset.mutate()}>Reset workspace</button></div>{reset.error && <ErrorNotice error={reset.error} />}</section>;
}

function HealthPage() {
  const health = useMutation({ mutationFn: api.doctor }); useEffect(() => { health.mutate(); }, []);
  return <Page title="System health" description="Local dependencies and exact remediation without host-control permissions." action={<button className="button" onClick={() => health.mutate()}><RefreshCw size={16} />Run checks</button>}>{health.isPending && <Loading compact label="Running checks" />}{health.error && <ErrorNotice error={health.error} />}{health.data && <><div className={`notice ${health.data.status === "degraded" ? "error" : ""}`}>Overall status: <strong>{health.data.status}</strong> · Completed in {health.data.duration_ms} ms</div><div className="table-wrap"><table><thead><tr><th>Check</th><th>Status</th><th>Details</th><th>Required</th></tr></thead><tbody>{health.data.checks.map((item: any) => <tr key={item.name}><td>{item.name}</td><td><Status value={item.status} /></td><td>{item.details}</td><td>{item.required ? "Yes" : "Optional"}</td></tr>)}</tbody></table></div><section className="panel" style={{ marginTop: 18 }}><h2>Start local services</h2><code>{health.data.commands.windows}</code><p className="subtle">Use the same Docker Compose command in Windows PowerShell or WSL/Linux. The browser does not control Docker.</p></section></>}</Page>;
}

function JobTable({ jobs }: { jobs: Job[] }) { return <div className="table-wrap"><table><thead><tr><th>Operation</th><th>Mode</th><th>Status</th><th>Progress</th><th>Started</th><th></th></tr></thead><tbody>{jobs.map(job => <tr key={job.id}><td>{capitalize(job.operation)}</td><td>{job.execution_mode}</td><td><Status value={job.status} /></td><td>{job.progress_total ? `${job.progress_current}/${job.progress_total}` : "—"}</td><td>{formatDate(job.started_at || job.created_at)}</td><td><Link to={`/activity/${job.id}`} title="Open job"><ChevronRight size={17} /></Link></td></tr>)}</tbody></table></div>; }
function SourceTable({ sources }: { sources: Source[] }) { return <div className="table-wrap"><table><thead><tr><th>Source</th><th>Type</th><th>Chunks</th><th>Provider / model</th><th>Store</th><th>Ingested</th></tr></thead><tbody>{sources.map(source => <tr key={source.id}><td><Link to={`/documents/${encodeURIComponent(source.id)}`}>{source.source_path}</Link><div className="subtle">{source.file_hash.slice(0, 12)}</div></td><td>{source.file_type}</td><td>{source.chunk_count}</td><td>{source.provider}<div className="subtle">{source.embedding_model}</div></td><td>{source.store}</td><td>{formatDate(source.ingested_at)}</td></tr>)}</tbody></table></div>; }
function JobProgress({ job, detailed = false }: { job: Job; detailed?: boolean }) { const events = job.events || []; return <section className="panel" style={{ marginTop: detailed ? 20 : 10 }} aria-live="polite"><div style={{ display: "flex", justifyContent: "space-between" }}><strong>Operation progress</strong><Status value={job.status} /></div>{job.progress_total > 0 && <progress max={job.progress_total} value={job.progress_current} style={{ width: "100%", marginTop: 12 }} />}{detailed && <ul className="timeline">{events.map(event => <li key={event.id}><span><StatusDot value={event.status} /></span><div><strong>{event.stage.replaceAll("_", " ")}</strong><div>{event.message}</div>{event.wait_seconds && <div className="subtle">Waiting {event.wait_seconds}s</div>}</div><time className="subtle">{formatTime(event.created_at)}</time></li>)}</ul>}</section>; }
function HitView({ hit, rank, debug }: { hit: Hit; rank: number; debug: boolean }) { return <article className="hit"><div className="hit-head"><span>{rank}. {hit.citation}</span><span>{hit.score == null ? "No score" : hit.score.toFixed(4)}</span></div><p>{debug ? hit.text : `${hit.text.slice(0, 420)}${hit.text.length > 420 ? "…" : ""}`}</p>{debug && <code className="subtle">{hit.vector_id}</code>}</article>; }
function Stat({ label, value }: { label: string; value: ReactNode }) { return <div className="panel stat"><span className="subtle">{label}</span><strong>{value}</strong></div>; }
function Status({ value }: { value: string }) { return <span className={`status ${value}`}><StatusDot value={value} />{value.replaceAll("_", " ")}</span>; }
function StatusDot({ value }: { value: string }) { return <span className="dot" aria-hidden="true" data-status={value} />; }
function Field({ label, children }: { label: string; children: ReactNode }) { return <label className="field" style={{ marginBottom: 13 }}><span>{label}</span>{children}</label>; }
function Empty({ title, detail }: { title: string; detail: string }) { return <div className="empty"><CircleHelp size={24} style={{ margin: "0 auto 8px" }} /><strong>{title}</strong><div className="subtle">{detail}</div></div>; }
function FirstRun({ onCreate }: { onCreate: () => void }) { return <div className="panel" style={{ maxWidth: 620, margin: "12vh auto" }}><Database size={28} /><h1 style={{ marginTop: 14 }}>Create your first workspace</h1><p>Workspaces isolate documents, chunks, embeddings, history, and evaluations for separate learning tasks.</p><button className="button primary" onClick={onCreate}><Plus size={16} />Create workspace</button></div>; }
function Loading({ label, compact = false }: { label: string; compact?: boolean }) { return <div className={compact ? "subtle" : "empty"} role="status">{label}…</div>; }
function Fatal({ error }: { error: unknown }) { return <main className="empty"><h1>Could not start the application</h1><ErrorNotice error={error} /><p>Confirm the FastAPI server and local metadata directory are available.</p></main>; }
function ErrorNotice({ error }: { error: unknown }) { return <div className="notice error" role="alert">{error instanceof Error ? error.message : String(error || "Unknown error")}</div>; }
async function readJson(response: Response) { const data = await response.json(); if (!response.ok) throw new Error(data?.error?.message || data?.detail || "Request failed"); return data; }
function formatDate(value?: string) { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—"; }
function formatTime(value: string) { return new Intl.DateTimeFormat(undefined, { timeStyle: "medium" }).format(new Date(value)); }
function formatBytes(value: number) { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB`; }
function capitalize(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
