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

export interface RunProgress {
  current: number;
  total: number;
}

export interface RunArtifactSummary {
  id: string;
  title: string;
  content_path: string;
  artifact_type: string;
}

export interface RunSnapshot {
  run_id: string;
  project_id: string;
  status: "idle" | "collecting" | "structuring" | "exporting" | "completed" | "failed";
  current_stage: string;
  progress: RunProgress;
  events: RunEvent[];
  errors: RunEvent[];
  artifact_summary: RunArtifactSummary[];
  updated_at: string;
}

export interface Artifact {
  id: string;
  title: string;
  content_path: string;
  artifact_type?: string;
  content?: string;
  schema_version?: string;
}

export interface Evidence {
  id: string;
  source_title: string;
  snippet: string;
  source_url?: string;
  confidence?: number;
  source_type?: string;
  source_channel?: string;
  source_policy?: string;
  source_quality?: string;
  claim_strength?: string;
  bias_risk?: string;
  collected_by?: string;
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

export interface SearchConfigStatus {
  configured: boolean;
  provider?: string;
  providers?: string[];
  requested_provider_mode?: string;
  extraction_provider?: string;
  extraction_providers?: string[];
  requested_extraction_provider?: string;
  missing_configuration?: string[];
  diagnostics?: string[];
  status_message?: string;
}

export interface SearchTestResult {
  success: boolean;
  message: string;
  source_policy: string;
  providers: string[];
  effective_allowed_domains: string[];
  effective_blocked_domains: string[];
  result_count: number;
  results: Array<{
    title: string;
    url: string;
    snippet: string;
    published_date?: string;
    provider_metadata?: Record<string, unknown>;
  }>;
  extracted_page?: {
    url: string;
    canonical_url?: string;
    title?: string;
    domain?: string;
    extraction_provider?: string;
    raw_text_preview?: string;
  } | null;
  source_assessment?: {
    source_type?: string;
    source_quality?: string;
    is_original_source?: boolean;
    is_marketing_like?: boolean;
    domain?: string;
    recommended_verification_status?: string;
    reliability_notes?: string;
  } | null;
}

export interface SearchRuntimeConfig {
  search_provider_mode: string;
  tavily_api_key?: string;
  tavily_endpoint?: string;
  serper_api_key?: string;
  serper_endpoint?: string;
  brave_api_key?: string;
  brave_endpoint?: string;
  exa_api_key?: string;
  exa_endpoint?: string;
  content_extraction_provider: string;
  firecrawl_api_key?: string;
  firecrawl_endpoint?: string;
  jina_reader_endpoint_prefix?: string;
}

export interface ProjectDocument {
  id: string;
  project_id: string;
  channel: string;
  file_name?: string;
  mime_type?: string;
  content: string;
  word_count: number;
  char_count: number;
  segment_count: number;
  citation_count: number;
  created_at: string;
}

export interface SourceConnectorStatus {
  key: string;
  display_name: string;
  connector_type: string;
  source_type: string;
  trust_level: string;
  domains: string[];
  required_env_keys: string[];
  configured: boolean;
  setup_url?: string | null;
  can_support_facts: boolean;
  requires_manual_review: boolean;
  notes: string;
}

export interface SourcePackStatus {
  name: string;
  display_name: string;
  market_scopes: string[];
  reliable_domains: string[];
  blocked_domains: string[];
  connectors: SourceConnectorStatus[];
}

export interface SourceRegistryStatus {
  packs: SourcePackStatus[];
  configured_connector_count: number;
  recommended_next_action: string;
}

export interface DocumentSegment {
  id: string;
  document_id: string;
  order_index: number;
  text: string;
  heading?: string;
  char_count: number;
  citation_refs: string[];
}

export interface DocumentCitation {
  id: string;
  document_id: string;
  raw_reference: string;
  source_title?: string;
  source_url?: string;
  referenced_segment_ids: string[];
}

export interface EvidencePreview {
  id: string;
  project_id: string;
  source_title: string;
  source_url?: string;
  source_type?: string;
  source_channel: string;
  source_policy?: string;
  raw_excerpt?: string;
  snippet: string;
  summary?: string;
  source_quality: string;
  claim_strength: string;
  bias_risk?: string;
  needs_counterevidence: boolean;
  collected_by?: string;
  confidence: number;
  verification_status: string;
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

  getRunSnapshot(runId: string) {
    return requestJson<RunSnapshot>(`/api/runs/${runId}/snapshot`);
  },

  getActiveRun(projectId: string) {
    return requestJson<RunResponse | null>(`/api/projects/${projectId}/active-run`);
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

  getSearchConfig() {
    return requestJson<SearchConfigStatus>("/api/config/search");
  },

  updateSearchConfig(data: SearchRuntimeConfig) {
    return requestJson<{ success: boolean; message: string; configured: boolean }>("/api/config/search", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  testSearchConnection(data: {
    query: string;
    url_to_extract?: string;
    market_scope?: string;
    source_policy?: string;
    max_results?: number;
    auto_extract_first_result?: boolean;
    allowed_domains?: string[];
    blocked_domains?: string[];
  }) {
    return requestJson<SearchTestResult>("/api/config/search/test", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  getSourceRegistryStatus() {
    return requestJson<SourceRegistryStatus>("/api/config/sources");
  },

  createDocument(projectId: string, data: { channel: string; content: string; file_name?: string; mime_type?: string }) {
    return requestJson<ProjectDocument>(`/api/projects/${projectId}/documents`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async uploadDocument(projectId: string, data: { channel: string; file: File }) {
    const formData = new FormData();
    formData.append("channel", data.channel);
    formData.append("file", data.file);
    const response = await fetch(`/api/projects/${projectId}/documents/upload`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "请求失败" }));
      throw new Error(error.detail || `API 请求失败: ${response.status}`);
    }
    return response.json() as Promise<ProjectDocument>;
  },

  listDocuments(projectId: string) {
    return requestJson<ProjectDocument[]>(`/api/projects/${projectId}/documents`);
  },

  getDocument(documentId: string) {
    return requestJson<ProjectDocument>(`/api/documents/${documentId}`);
  },

  listDocumentSegments(documentId: string) {
    return requestJson<DocumentSegment[]>(`/api/documents/${documentId}/segments`);
  },

  listDocumentCitations(documentId: string) {
    return requestJson<DocumentCitation[]>(`/api/documents/${documentId}/citations`);
  },

  getDocumentEvidencePreview(documentId: string) {
    return requestJson<EvidencePreview[]>(`/api/documents/${documentId}/evidence-preview`);
  },

  ingestDocumentEvidence(documentId: string) {
    return requestJson<{ document_id: string; created_count: number; evidence: EvidencePreview[] }>(
      `/api/documents/${documentId}/ingest-evidence`,
      { method: "POST" },
    );
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
