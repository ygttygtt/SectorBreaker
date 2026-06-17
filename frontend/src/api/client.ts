/**
 * Type-safe API client for SectorBreaker backend.
 */

export interface Project {
  id: string;
  title: string;
  domain: string;
  market_scope: string;
  depth: string;
  source_policy?: string;
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
  progress_current?: number | null;
  progress_total?: number | null;
  severity?: string;
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
  source_type?: string;
  source_channel?: string;
  source_quality?: string;
  verification_status?: string;
  needs_counterevidence?: boolean;
}

export interface AgentTask {
  agent_id: string;
  display_name: string;
  role: string;
  reason: string;
  run_mode: string;
  execution_group: string;
  depends_on: string[];
  source_scope: string[];
  output_contract: string;
  verification_level: string;
  fallback: string;
}

export interface SupervisorPlan {
  intent_summary: string;
  source_policy: string;
  source_policy_reason: string;
  selected_agents: AgentTask[];
  skipped_agents: { agent_id: string; display_name: string; reason: string }[];
  verification_plan: {
    key_claim_types: string[];
    counterevidence_triggers: string[];
    downgraded_source_types: string[];
    notes?: string;
  };
  human_review_points: string[];
  success_criteria: string[];
  assumptions: string[];
  risks: string[];
}

export interface WorkflowNode {
  id: string;
  label: string;
  node_type: string;
  agent_id?: string | null;
  group: string;
  status: string;
  reason?: string | null;
  details: Record<string, unknown>;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  label?: string | null;
}

export interface WorkflowDefinition {
  schema_version: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
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
  createProject(data: { title: string; domain: string; market_scope: string; depth: string; source_policy: string }) {
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

  getRunWorkflowDefinition(runId: string) {
    return requestJson<WorkflowDefinition>(`/api/runs/${runId}/workflow-definition`);
  },

  getProjectWorkflowDefinition(projectId: string) {
    return requestJson<WorkflowDefinition>(`/api/projects/${projectId}/workflow-definition`);
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
  resumeRun(runId: string, data: { guidance?: string; evidence_data?: string; assistant_brief?: string; plan_confirmed?: boolean }) {
    return requestJson<{ status: string; run_id: string }>(`/api/runs/${runId}/resume`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },
};
