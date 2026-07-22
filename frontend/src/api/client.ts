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
  project_mode?: "domain_knowledge";
  status: string;
}

export interface CreateProjectPayload {
  title: string;
  domain: string;
  market_scope: string;
  depth: string;
  source_policy: string;
  project_mode?: "domain_knowledge";
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
  citation_details?: ChatCitationDetail[];
  retrieval_mode: RetrievalMode;
  embedding_model?: string | null;
  retrieval_diagnostics: RetrievalDiagnostics;
  artifact_id?: string | null;
  artifact_path?: string | null;
  updated_artifact_count?: number;
}

export interface FollowUpResponse extends ChatResponse {
  artifact_id?: string | null;
  artifact_path?: string | null;
  updated_artifact_count?: number;
}

export interface ChatCitationDetail {
  source_id: string;
  parent_id?: string | null;
  source_type: string;
  title: string;
  snippet: string;
  score: number;
  url?: string | null;
  relative_path?: string | null;
  content_hash?: string | null;
  verification_status?: string | null;
  retrieval_mode: "lexical" | "vector" | "hybrid";
  lexical_rank?: number | null;
  vector_rank?: number | null;
  lexical_score?: number | null;
  vector_score?: number | null;
  embedding_model?: string | null;
}

export type RetrievalMode = "hybrid" | "hybrid_pending" | "lexical" | "lexical_degraded";

export interface RetrievalDiagnostics {
  effective_mode: RetrievalMode;
  embedding_configured: boolean;
  embedding_available: boolean;
  embedding_loaded: boolean;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  dimension?: number | null;
  index_count: number;
  lexical_candidates: number;
  vector_candidates: number;
  last_error?: string | null;
}

export interface VectorReindexResult {
  project_id: string;
  source_chunks: number;
  embedded_chunks: number;
  unchanged_chunks: number;
  deleted_chunks: number;
  index_count: number;
  embedding_provider: string;
  embedding_model: string;
  dimension?: number | null;
}

export interface ExportManifest {
  export_version?: string;
  project_id?: string;
  generated_at?: string;
  artifact_paths: string[];
  evidence_ids: string[];
  export_dir?: string | null;
}

export interface LLMConfigStatus {
  configured: boolean;
  base_url?: string;
  model?: string;
  max_tokens?: number | null;
}

export interface LLMPreset {
  id: string;
  name: string;
  base_url: string;
  model: string;
  max_tokens: number;
  notes?: string | null;
  has_api_key: boolean;
  is_builtin: boolean;
}

export interface LLMPresetPayload {
  name: string;
  base_url: string;
  api_key?: string | null;
  model: string;
  max_tokens: number;
  notes?: string | null;
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
  configured_api_keys?: string[];
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
  firecrawl_search_endpoint?: string;
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
  execution_status: string;
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

export interface VaultImportRequest {
  source_path: string;
  max_files?: number;
  max_total_bytes?: number;
}

export interface VaultImportRecord {
  id: string;
  project_id: string;
  source_path: string;
  note_count: number;
  total_bytes: number;
  snapshot_hash: string;
  imported_paths: string[];
  skipped_paths: string[];
  created_at: string;
}

export interface VaultNoteSummary {
  artifact_id: string;
  relative_path: string;
  title: string;
  revision: number;
  content_hash: string;
  wikilinks: string[];
  tags: string[];
}

export interface VaultStatus {
  project_id: string;
  latest_import: VaultImportRecord | null;
  active_note_count: number;
  notes: VaultNoteSummary[];
}

export type HealthFindingType =
  | "broken_link"
  | "orphan_note"
  | "duplicate_title"
  | "missing_frontmatter"
  | "missing_evidence_metadata"
  | "unresolved_marker";

export interface HealthFinding {
  id: string;
  finding_type: HealthFindingType;
  severity: "info" | "warning" | "blocking";
  target_paths: string[];
  explanation: string;
  suggested_action: string;
  detector: string;
  auto_fixable: boolean;
}

export interface KnowledgeHealthReport {
  id: string;
  project_id: string;
  vault_import_id: string | null;
  snapshot_hash: string;
  metrics: Record<string, number>;
  findings: HealthFinding[];
  generated_at: string;
}

export type MaintenanceTaskStatus = "open" | "planned" | "running" | "blocked" | "done" | "dismissed";

export interface MaintenanceTask {
  id: string;
  project_id: string;
  fingerprint: string;
  finding_ids: string[];
  task_type: string;
  objective: string;
  target_paths: string[];
  priority: number;
  status: MaintenanceTaskStatus;
  assigned_specialist: string | null;
  required_evidence_types: string[];
  approval_required: boolean;
  change_set_id: string | null;
  created_at: string;
  updated_at: string;
}

export type ChangeSetStatus = "proposed" | "approved" | "applied" | "conflicted" | "rolled_back" | "denied";

export interface ChangeOperation {
  operation: "create" | "update";
  path: string;
  base_hash: string;
  before_content: string;
  after_content: string;
  unified_diff: string;
  factual_change: boolean;
}

export interface ChangeSet {
  id: string;
  project_id: string;
  task_id: string | null;
  status: ChangeSetStatus;
  summary: string;
  evidence_ids: string[];
  operations: ChangeOperation[];
  created_by_agent: string;
  created_at: string;
  approved_at: string | null;
  applied_at: string | null;
  rolled_back_at: string | null;
  applied_artifact_ids: string[];
  rollback_artifact_ids: string[];
  error: string | null;
}

export interface ChangeSetProposalPayload {
  task_id?: string | null;
  summary: string;
  path: string;
  after_content: string;
  evidence_ids?: string[];
  factual_change?: boolean;
}

export interface MaintenanceRunPayload {
  objective?: string;
  task_ids?: string[];
  execution_mode?: "plan_only" | "apply_safe" | "require_review";
  autonomy_policy?: Record<string, unknown>;
}

export interface MaintenanceRunResponse {
  run_id: string;
  status: string;
  resumed_from_checkpoint: boolean;
  task_ids: string[];
  execution_mode: string;
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
  createProject(data: CreateProjectPayload) {
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

  getRunTrace(runId: string) {
    return requestJson<{
      run_id: string;
      project_id: string;
      status: string;
      event_count: number;
      events: RunEvent[];
    }>(`/api/runs/${runId}/trace`);
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

  // Knowledge-base control plane
  importVault(projectId: string, data: VaultImportRequest) {
    return requestJson<VaultImportRecord>(`/api/projects/${projectId}/vault/import`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  getVaultStatus(projectId: string) {
    return requestJson<VaultStatus>(`/api/projects/${projectId}/vault`);
  },

  auditVault(projectId: string) {
    return requestJson<KnowledgeHealthReport>(`/api/projects/${projectId}/audits`, { method: "POST" });
  },

  getKnowledgeHealth(projectId: string) {
    return requestJson<KnowledgeHealthReport>(`/api/projects/${projectId}/health`);
  },

  listMaintenanceBacklog(projectId: string) {
    return requestJson<MaintenanceTask[]>(`/api/projects/${projectId}/maintenance-backlog`);
  },

  startMaintenanceRun(projectId: string, data: MaintenanceRunPayload) {
    return requestJson<MaintenanceRunResponse>(`/api/projects/${projectId}/maintenance-runs`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  listChangeSets(projectId: string) {
    return requestJson<ChangeSet[]>(`/api/projects/${projectId}/change-sets`);
  },

  proposeChangeSet(projectId: string, data: ChangeSetProposalPayload) {
    return requestJson<ChangeSet>(`/api/projects/${projectId}/change-sets`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  approveChangeSet(projectId: string, changeSetId: string) {
    return requestJson<ChangeSet>(`/api/projects/${projectId}/change-sets/${changeSetId}/approve`, { method: "POST" });
  },

  applyChangeSet(projectId: string, changeSetId: string) {
    return requestJson<ChangeSet>(`/api/projects/${projectId}/change-sets/${changeSetId}/apply`, { method: "POST" });
  },

  rollbackChangeSet(projectId: string, changeSetId: string) {
    return requestJson<ChangeSet>(`/api/projects/${projectId}/change-sets/${changeSetId}/rollback`, { method: "POST" });
  },

  getRetrievalStatus(projectId?: string) {
    const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
    return requestJson<RetrievalDiagnostics>(`/api/config/retrieval${params}`);
  },

  reindexProject(projectId: string) {
    return requestJson<VectorReindexResult>(`/api/projects/${projectId}/retrieval/reindex`, { method: "POST" });
  },

  // Chat
  askQuestion(projectId: string, question: string) {
    return requestJson<ChatResponse>(`/api/projects/${projectId}/chat`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
  },

  growKnowledge(projectId: string, question: string) {
    return requestJson<FollowUpResponse>(`/api/projects/${projectId}/follow-up`, {
      method: "POST",
      body: JSON.stringify({ question }),
    });
  },

  // Export
  exportProject(projectId: string) {
    return requestJson<ExportManifest>(`/api/projects/${projectId}/exports`, { method: "POST" });
  },

  openExportFolder(exportDir: string) {
    return requestJson<{ success: boolean; export_dir: string }>("/api/exports/open-folder", {
      method: "POST",
      body: JSON.stringify({ export_dir: exportDir }),
    });
  },

  // LLM Config
  getLLMConfig() {
    return requestJson<LLMConfigStatus>("/api/config/llm");
  },

  getSearchConfig() {
    return requestJson<SearchConfigStatus>("/api/config/search");
  },

  updateSearchConfig(data: SearchRuntimeConfig) {
    return requestJson<{ success: boolean; message: string; configured: boolean; configured_api_keys: string[] }>("/api/config/search", {
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

  listLLMPresets() {
    return requestJson<{ presets: LLMPreset[] }>("/api/config/llm/presets");
  },

  upsertLLMPreset(presetId: string, data: LLMPresetPayload) {
    return requestJson<{ success: boolean; preset: LLMPreset }>(`/api/config/llm/presets/${encodeURIComponent(presetId)}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  applyLLMPreset(presetId: string, data?: { api_key?: string | null }) {
    return requestJson<{ success: boolean; message: string; preset: LLMPreset }>(`/api/config/llm/presets/${encodeURIComponent(presetId)}/apply`, {
      method: "POST",
      body: JSON.stringify(data ?? {}),
    });
  },

  deleteLLMPreset(presetId: string) {
    return requestJson<{ success: boolean; message?: string }>(`/api/config/llm/presets/${encodeURIComponent(presetId)}`, {
      method: "DELETE",
    });
  },

  updateLLMConfig(data: { base_url: string; api_key: string; model: string; max_tokens?: number }) {
    return requestJson<{ success: boolean; message: string }>("/api/config/llm", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  testLLMConnection(data: { base_url: string; api_key: string; model: string; max_tokens?: number }) {
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
