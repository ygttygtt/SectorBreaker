/**
 * Type-safe API client for SectorBreaker backend.
 */

export interface Project {
  id: string;
  title: string;
  domain: string;
  market_scope: string;
  depth: string;
  status: string;
}

export interface RunResponse {
  id: string;
  project_id: string;
  status: string;
  current_gate: string | null;
  current_step: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface RunEvent {
  event_type: string;
  gate: string;
  step: string | null;
  agent: string | null;
  message: string;
  data: Record<string, unknown> | null;
  timestamp: number;
}

export interface Artifact {
  id: string;
  title: string;
  content_path: string;
  artifact_type?: string;
  content?: string;
}

export interface Evidence {
  id: string;
  source_title: string;
  snippet: string;
  source_url?: string;
  confidence?: number;
}

export interface ChatResponse {
  answer: string;
  citations: string[];
}

export interface ExportManifest {
  artifact_paths: string[];
  evidence_ids: string[];
}

export interface LLMConfigStatus {
  configured: boolean;
  base_url?: string;
  model?: string;
}

export interface LLMTestResult {
  success: boolean;
  message: string;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "请求失败" }));
    throw new Error(error.detail || `API 请求失败: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  // Projects
  createProject(data: { title: string; domain: string; market_scope: string; depth: string }) {
    return requestJson<Project>("/api/projects", { method: "POST", body: JSON.stringify(data) });
  },

  getProject(projectId: string) {
    return requestJson<Project>(`/api/projects/${projectId}`);
  },

  listProjects() {
    return requestJson<Project[]>("/api/projects");
  },

  // Runs
  startRun(projectId: string, autoRun: boolean = false) {
    const params = autoRun ? "?auto_run=true" : "";
    return requestJson<RunResponse>(`/api/projects/${projectId}/runs${params}`, { method: "POST" });
  },

  getRun(runId: string) {
    return requestJson<RunResponse>(`/api/runs/${runId}`);
  },

  // Evidence & Artifacts
  listEvidence(projectId: string) {
    return requestJson<Evidence[]>(`/api/projects/${projectId}/evidence`);
  },

  listArtifacts(projectId: string) {
    return requestJson<Artifact[]>(`/api/projects/${projectId}/artifacts`);
  },

  // Chat
  askQuestion(projectId: string, question: string) {
    return requestJson<ChatResponse>(`/api/projects/${projectId}/chat`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
  },

  // Export
  exportProject(projectId: string) {
    return requestJson<ExportManifest>(`/api/projects/${projectId}/exports`, { method: "POST" });
  },

  // LLM Config
  getLLMConfig() {
    return requestJson<LLMConfigStatus>("/api/config/llm");
  },

  updateLLMConfig(data: { base_url: string; api_key: string; model: string }) {
    return requestJson<{ success: boolean; message: string }>("/api/config/llm", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  testLLMConnection(data: { base_url: string; api_key: string; model: string }) {
    return requestJson<LLMTestResult>("/api/config/llm/test", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  // User Inputs
  addUserInput(runId: string, data: { gate: string; input_type: string; content: string }) {
    return requestJson<{ status: string; input_id: string }>(`/api/runs/${runId}/inputs`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  // Resume after human review
  resumeRun(runId: string, data: { guidance?: string; evidence_data?: string }) {
    return requestJson<{ status: string; run_id: string }>(`/api/runs/${runId}/resume`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
};
