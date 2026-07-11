export type Workspace = { name: string; created_at: string; active: boolean; source_count: number; chunk_count: number; last_ingested_at?: string };
export type Bootstrap = { version: string; active_workspace: string | null; workspaces: Workspace[]; config: Record<string, unknown>; secrets: Record<string, { configured: boolean; source: string; aliases: string[] }>; features: Record<string, boolean> };
export type JobEvent = { id: number; sequence: number; created_at: string; stage: string; status: string; message: string; current?: number; total?: number; retry_attempt?: number; retry_limit?: number; wait_seconds?: number; metadata?: Record<string, unknown> };
export type Job = { id: string; workspace: string; operation: string; execution_mode: string; status: string; created_at: string; started_at?: string; completed_at?: string; progress_current: number; progress_total: number; config: Record<string, unknown>; result?: Record<string, unknown>; error?: { message: string }; events?: JobEvent[] };
export type Source = { id: string; workspace: string; source_path: string; file_type: string; file_hash: string; chunk_count: number; provider: string; embedding_model: string; generation_model: string; store: string; dimensions: number; ingested_at: string };
export type Hit = { vector_id: string; score?: number; text: string; source_path: string; chunk_index: number; page_number?: number; citation: string };

const API = "/api/v1";

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...init, headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data?.error?.message || data?.detail || `Request failed (${response.status})`);
  return data as T;
}

export const api = {
  bootstrap: () => request<Bootstrap>("/bootstrap"),
  createWorkspace: (name: string) => request<Workspace>("/workspaces", { method: "POST", body: JSON.stringify({ name }) }),
  activateWorkspace: (name: string) => request(`/workspaces/${encodeURIComponent(name)}/active`, { method: "PUT" }),
  sources: (workspace: string) => request<Source[]>(`/workspaces/${encodeURIComponent(workspace)}/sources`),
  uploads: (workspace: string) => request<any[]>(`/workspaces/${encodeURIComponent(workspace)}/uploads`),
  upload: (workspace: string, files: File[]) => { const form = new FormData(); files.forEach(file => form.append("files", file)); return request<{ files: any[] }>(`/workspaces/${encodeURIComponent(workspace)}/uploads`, { method: "POST", body: form }); },
  ingest: (workspace: string, body: Record<string, unknown>) => request<Job>(`/workspaces/${encodeURIComponent(workspace)}/ingestions`, { method: "POST", body: JSON.stringify(body) }),
  jobs: (workspace?: string) => request<Job[]>(`/jobs${workspace ? `?workspace=${encodeURIComponent(workspace)}` : ""}`),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  search: (workspace: string, body: Record<string, unknown>) => request<{ progress: string[]; results: Hit[]; config: Record<string, unknown> }>(`/workspaces/${encodeURIComponent(workspace)}/search`, { method: "POST", body: JSON.stringify(body) }),
  sessions: (workspace: string) => request<any[]>(`/chat/sessions?workspace=${encodeURIComponent(workspace)}`),
  session: (workspace: string, id: string) => request<any>(`/chat/sessions/${id}?workspace=${encodeURIComponent(workspace)}`),
  createSession: (workspace: string, title = "New session") => request<any>("/chat/sessions", { method: "POST", body: JSON.stringify({ workspace, title }) }),
  ask: (sessionId: string, question: string, config: Record<string, unknown>) => request<{ turn: any; job: Job }>(`/chat/sessions/${sessionId}/turns`, { method: "POST", body: JSON.stringify({ question, ...config }) }),
  suites: (workspace: string) => request<any[]>(`/eval/suites?workspace=${encodeURIComponent(workspace)}`),
  createSuite: (body: Record<string, unknown>) => request<any>("/eval/suites", { method: "POST", body: JSON.stringify(body) }),
  runSuite: (workspace: string, id: string) => request<Job>(`/eval/suites/${id}/run?workspace=${encodeURIComponent(workspace)}`, { method: "POST", body: JSON.stringify(null) }),
  config: () => request<any>("/config"),
  patchConfig: (values: Record<string, unknown>) => request<any>("/config", { method: "PATCH", body: JSON.stringify({ values }) }),
  setSecret: (provider: string, value: string) => request<any>(`/secrets/${provider}`, { method: "PUT", body: JSON.stringify({ value }) }),
  doctor: () => request<any>("/doctor", { method: "POST" }),
  reset: (workspace: string, store: string, confirmation: string, deleteUploads: boolean) => request<any>(`/workspaces/${encodeURIComponent(workspace)}/reset`, { method: "POST", body: JSON.stringify({ store, confirmation, delete_uploads: deleteUploads }) }),
};
