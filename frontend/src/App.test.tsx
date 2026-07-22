import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

// Use vi.hoisted so variables are available in vi.mock factories
const {
  mockEventsState,
  mockGetLLMConfig,
  mockCreateProject,
  mockStartRun,
  mockGetRun,
  mockGetRunSnapshot,
  mockGetActiveRun,
  mockGetSearchConfig,
  mockUpdateSearchConfig,
  mockTestSearchConnection,
  mockResumeRun,
  mockRecoverRun,
  mockCreateDocument,
  mockUploadDocument,
  mockListArtifacts,
  mockListEvidence,
  mockAskQuestion,
  mockGrowKnowledge,
  mockExportProject,
  mockOpenExportFolder,
  mockGetWorkflow,
  mockGetSourceRegistryStatus,
  mockListLLMPresets,
  mockUpsertLLMPreset,
  mockApplyLLMPreset,
  mockDeleteLLMPreset,
  mockGetVaultStatus,
  mockImportVault,
  mockAuditVault,
  mockGetKnowledgeHealth,
  mockListMaintenanceBacklog,
  mockStartMaintenanceRun,
  mockListChangeSets,
  mockProposeChangeSet,
  mockApproveChangeSet,
  mockApplyChangeSet,
  mockRollbackChangeSet,
  mockGetRetrievalStatus,
  mockReindexProject,
} = vi.hoisted(() => ({
  mockEventsState: { current: [] as Array<Record<string, unknown>> },
  mockGetLLMConfig: vi.fn().mockResolvedValue({ configured: true, base_url: "http://test", model: "test" }),
  mockListLLMPresets: vi.fn().mockResolvedValue({
    presets: [
      {
        id: "deepseek-official",
        name: "DeepSeek 官方",
        base_url: "https://api.deepseek.com/v1",
        model: "deepseek-chat",
        max_tokens: 4096,
        has_api_key: false,
        is_builtin: true,
        notes: "official",
      },
      {
        id: "sensenova-v4-flash",
        name: "商汤 V4 Flash",
        base_url: "https://token.sensenova.cn/v1",
        model: "deepseek-v4-flash",
        max_tokens: 4096,
        has_api_key: true,
        is_builtin: true,
        notes: "sense",
      },
    ],
  }),
  mockUpsertLLMPreset: vi.fn().mockResolvedValue({ success: true, preset: { id: "custom-fast", name: "Custom Fast", has_api_key: true } }),
  mockApplyLLMPreset: vi.fn().mockResolvedValue({ success: true, message: "applied" }),
  mockDeleteLLMPreset: vi.fn().mockResolvedValue({ success: true }),
  mockGetSourceRegistryStatus: vi.fn().mockResolvedValue({
    packs: [
      {
        name: "company_china_pack",
        display_name: "中国企业与披露信源",
        market_scopes: ["china", "mixed"],
        reliable_domains: ["cninfo.com.cn", "sse.com.cn", "szse.cn", "gsxt.gov.cn"],
        blocked_domains: ["medium.com", "substack.com"],
        connectors: [
          {
            key: "cninfo_public",
            display_name: "巨潮资讯公开披露",
            connector_type: "search_domain_pack",
            source_type: "company_disclosure",
            trust_level: "high",
            domains: ["cninfo.com.cn"],
            required_env_keys: [],
            configured: false,
            execution_status: "available_via_domain_filter",
            can_support_facts: true,
            requires_manual_review: false,
            notes: "通过搜索 provider 发现公开披露 URL。",
          },
          {
            key: "qcc_openapi",
            display_name: "企查查开放平台",
            connector_type: "commercial_api",
            source_type: "public_database",
            trust_level: "high",
            domains: ["openapi.qcc.com"],
            required_env_keys: ["QCC_API_KEY"],
            configured: false,
            setup_url: "https://openapi.qcc.com/dataApi",
            can_support_facts: true,
            requires_manual_review: false,
            notes: "付费商业 API，MVP 可不配置。",
          },
        ],
      },
    ],
    configured_connector_count: 0,
    recommended_next_action: "先配置 Tavily、Serper、Brave 或 Exa 任意一个搜索 Key，再用可靠信源自检验证域名约束。",
  }),
  mockGetSearchConfig: vi.fn().mockResolvedValue({
    configured: true,
    provider: "tavily",
    providers: ["tavily"],
    requested_provider_mode: "auto",
    extraction_provider: "firecrawl",
    extraction_providers: ["firecrawl"],
    requested_extraction_provider: "firecrawl",
    configured_api_keys: ["tavily", "firecrawl"],
    missing_configuration: [],
    diagnostics: [],
    status_message: "搜索已就绪：tavily；抽取使用 firecrawl。",
    provider_onboarding: [
      {
        key: "tavily",
        display_name: "Tavily",
        capability: "search",
        signup_url: "https://app.tavily.com/home",
        pricing_url: "https://docs.tavily.com/documentation/api-credits",
        requires_api_key: true,
        free_tier_summary: "官方当前提供每月免费 credits。",
        configured: true,
        selected: true,
      },
      {
        key: "firecrawl",
        display_name: "Firecrawl",
        capability: "search_and_extraction",
        signup_url: "https://www.firecrawl.dev/app/api-keys",
        pricing_url: "https://www.firecrawl.dev/pricing",
        requires_api_key: true,
        free_tier_summary: "搜索和抓取都会消耗额度。",
        configured: true,
        selected: true,
      },
    ],
  }),
  mockTestSearchConnection: vi.fn().mockResolvedValue({
    success: true,
    message: "搜索/抽取链路可用",
    source_policy: "reliable_only",
    providers: ["tavily"],
    effective_allowed_domains: ["sec.gov", "investor.example.com"],
    effective_blocked_domains: ["medium.com"],
    result_count: 1,
    results: [{ title: "Official market report", url: "https://example.org/report", snippet: "Official statistics." }],
    extracted_page: {
      title: "Official Market Report",
      domain: "example.org",
      extraction_provider: "firecrawl",
      raw_text_preview: "Official market report body content.",
    },
  }),
  mockUpdateSearchConfig: vi.fn().mockResolvedValue({
    success: true,
    message: "搜索配置已更新",
    configured: true,
  }),
  mockResumeRun: vi.fn().mockResolvedValue({ status: "resumed", run_id: "run-1" }),
  mockRecoverRun: vi.fn().mockResolvedValue({ status: "recovery_started", run_id: "run-child", resumed_from_run_id: "run-1" }),
  mockCreateDocument: vi.fn().mockResolvedValue({
    id: "doc-text-1",
    project_id: "project-1",
    channel: "user_upload",
    file_name: "pasted-jd.md",
    mime_type: "text/markdown",
    content: "# jd",
    word_count: 1,
    char_count: 4,
    segment_count: 1,
    citation_count: 0,
    created_at: new Date().toISOString(),
  }),
  mockUploadDocument: vi.fn().mockResolvedValue({
    id: "doc-1",
    project_id: "project-1",
    channel: "assistant_brief",
    file_name: "brief.md",
    mime_type: "text/markdown",
    content: "# brief",
    word_count: 1,
    char_count: 7,
    segment_count: 1,
    citation_count: 0,
    created_at: new Date().toISOString(),
  }),
  mockCreateProject: vi.fn().mockResolvedValue({
    id: "project-1", title: "AI Agent 工具", domain: "AI Agent 工具",
    market_scope: "mixed", depth: "quick", source_policy: "reliable_first", project_mode: "domain_knowledge", status: "draft",
  }),
  mockStartRun: vi.fn().mockResolvedValue({
    id: "run-1", project_id: "project-1", status: "running",
    current_gate: "scope", created_at: new Date().toISOString(), completed_at: null,
  }),
  mockGetRun: vi.fn().mockResolvedValue({
    id: "run-1", project_id: "project-1", status: "waiting_for_human",
    current_gate: "scope", created_at: new Date().toISOString(), completed_at: null,
  }),
  mockGetRunSnapshot: vi.fn().mockResolvedValue({
    run_id: "run-1",
    project_id: "project-1",
    status: "completed",
    current_stage: "completed",
    progress: { current: 3, total: 3 },
    events: [],
    errors: [],
    artifact_summary: [
      { id: "A1", title: "领域总览", content_path: "00-领域总览.md", artifact_type: "domain_overview" },
    ],
    updated_at: new Date().toISOString(),
  }),
  mockGetActiveRun: vi.fn().mockResolvedValue(null),
  mockListArtifacts: vi.fn().mockResolvedValue([
    { id: "ART-RESEARCH-FRAME", title: "研究框架", content_path: "00-研究框架/research-frame.md" },
  ]),
  mockListEvidence: vi.fn().mockResolvedValue([
    {
      id: "EV-USER-SCOPE",
      source_title: "用户输入范围",
      snippet: "用户希望研究 AI Agent 工具",
      source_quality: "high",
      verification_status: "verified",
      source_type: "government",
      source_url: "https://example.org/source",
      needs_counterevidence: false,
    },
    {
      id: "EV-WEAK-001",
      source_title: "营销博客",
      snippet: "预计市场规模达到100亿元。",
      source_quality: "low",
      verification_status: "unverified",
      source_type: "media",
      needs_counterevidence: true,
      bias_risk: "marketing_like=true; signals=cta_language",
    },
  ]),
  mockAskQuestion: vi.fn().mockResolvedValue({ answer: "建议先看研究框架。", citations: ["EV-USER-SCOPE"] }),
  mockGrowKnowledge: vi.fn().mockResolvedValue({ answer: "建议先看研究框架。", citations: ["EV-USER-SCOPE"] }),
  mockExportProject: vi.fn().mockResolvedValue({
    export_version: "1", project_id: "project-1",
    artifact_paths: ["00-研究框架/research-frame.md"], evidence_ids: ["EV-USER-SCOPE"],
    export_dir: "E:\\QianFengStudy\\PythonProject\\SectorBreaker\\exports\\demo",
  }),
  mockOpenExportFolder: vi.fn().mockResolvedValue({ success: true, export_dir: "E:\\QianFengStudy\\PythonProject\\SectorBreaker\\exports\\demo" }),
  mockGetWorkflow: vi.fn().mockResolvedValue({ schema_version: "1", nodes: [], edges: [] }),
  mockGetVaultStatus: vi.fn().mockResolvedValue({
    project_id: "project-1",
    latest_import: null,
    active_note_count: 1,
    notes: [],
  }),
  mockImportVault: vi.fn().mockResolvedValue({
    id: "VI-1", project_id: "project-1", source_path: "D:\\Vault", note_count: 2, total_bytes: 100,
    snapshot_hash: "abc123", imported_paths: ["index.md"], skipped_paths: [], created_at: new Date().toISOString(),
  }),
  mockAuditVault: vi.fn().mockResolvedValue({
    id: "KHR-1", project_id: "project-1", vault_import_id: "VI-1", snapshot_hash: "abc123",
    metrics: { active_notes: 2, findings: 1, broken_links: 1 }, findings: [], generated_at: new Date().toISOString(),
  }),
  mockGetKnowledgeHealth: vi.fn().mockRejectedValue(new Error("not audited")),
  mockListMaintenanceBacklog: vi.fn().mockResolvedValue([]),
  mockStartMaintenanceRun: vi.fn().mockResolvedValue({
    run_id: "run-maintenance-1", status: "started", resumed_from_checkpoint: true, task_ids: [], execution_mode: "plan_only",
  }),
  mockListChangeSets: vi.fn().mockResolvedValue([]),
  mockProposeChangeSet: vi.fn(),
  mockApproveChangeSet: vi.fn(),
  mockApplyChangeSet: vi.fn(),
  mockRollbackChangeSet: vi.fn(),
  mockGetRetrievalStatus: vi.fn().mockResolvedValue({
    effective_mode: "hybrid",
    embedding_provider: "fastembed",
    embedding_model: "BAAI/bge-small-zh-v1.5",
    dimension: 512,
    index_count: 1,
    lexical_candidates: 0,
    vector_candidates: 0,
    last_error: null,
  }),
  mockReindexProject: vi.fn().mockResolvedValue({
    project_id: "project-1",
    source_chunks: 1,
    embedded_chunks: 1,
    unchanged_chunks: 0,
    deleted_chunks: 0,
    index_count: 1,
    embedding_provider: "fastembed",
    embedding_model: "BAAI/bge-small-zh-v1.5",
    dimension: 512,
  }),
}));

let onCompleteRef: (() => Promise<void> | void) | null = null;

vi.mock("./hooks/useRunEvents", () => ({
  useRunEvents: ({ onComplete }: { onComplete?: () => Promise<void> | void }) => {
    onCompleteRef = onComplete ?? null;
    return { events: mockEventsState.current, isConnected: false, reset: () => {} };
  },
}));

vi.mock("./api/client", () => ({
  api: {
    createProject: mockCreateProject,
    startRun: mockStartRun,
    getRun: mockGetRun,
    getRunSnapshot: mockGetRunSnapshot,
    getActiveRun: mockGetActiveRun,
    getRunWorkflowDefinition: mockGetWorkflow,
    getProjectWorkflowDefinition: mockGetWorkflow,
    getLLMConfig: mockGetLLMConfig,
    listLLMPresets: mockListLLMPresets,
    upsertLLMPreset: mockUpsertLLMPreset,
    applyLLMPreset: mockApplyLLMPreset,
    deleteLLMPreset: mockDeleteLLMPreset,
    getSearchConfig: mockGetSearchConfig,
    updateSearchConfig: mockUpdateSearchConfig,
    testSearchConnection: mockTestSearchConnection,
    getSourceRegistryStatus: mockGetSourceRegistryStatus,
    createDocument: mockCreateDocument,
    uploadDocument: mockUploadDocument,
    listArtifacts: mockListArtifacts,
    listEvidence: mockListEvidence,
    askQuestion: mockAskQuestion,
    growKnowledge: mockGrowKnowledge,
    exportProject: mockExportProject,
    openExportFolder: mockOpenExportFolder,
    updateLLMConfig: vi.fn().mockResolvedValue({ success: true }),
    testLLMConnection: vi.fn().mockResolvedValue({ success: true, message: "OK" }),
    addUserInput: vi.fn().mockResolvedValue({ status: "ok", input_id: "ui-1" }),
    resumeRun: mockResumeRun,
    recoverRun: mockRecoverRun,
    getVaultStatus: mockGetVaultStatus,
    importVault: mockImportVault,
    auditVault: mockAuditVault,
    getKnowledgeHealth: mockGetKnowledgeHealth,
    listMaintenanceBacklog: mockListMaintenanceBacklog,
    startMaintenanceRun: mockStartMaintenanceRun,
    listChangeSets: mockListChangeSets,
    proposeChangeSet: mockProposeChangeSet,
    approveChangeSet: mockApproveChangeSet,
    applyChangeSet: mockApplyChangeSet,
    rollbackChangeSet: mockRollbackChangeSet,
    getRetrievalStatus: mockGetRetrievalStatus,
    reindexProject: mockReindexProject,
  },
}));

import { App, buildAgentBriefCards, countEvidenceSignals, nodeIdForEvent } from "./App";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  onCompleteRef = null;
  mockEventsState.current = [];
});

test("maps personal Agent Kernel events to visible workflow graph nodes", () => {
  expect(nodeIdForEvent({ gate: "initialize_state", step: null, agent: "V3 Agent Kernel" })).toBe("initialize_state");
  expect(nodeIdForEvent({ gate: "external_materials", step: null, agent: "V3 Report Internalizer" })).toBe("external_materials");
  expect(nodeIdForEvent({ gate: "agent_decide", step: null, agent: "V3 Master Agent" })).toBe("agent_decide");
  expect(nodeIdForEvent({ gate: "tool_execution", step: null, agent: "V3 Tool Executor" })).toBe("tool_execution");
  expect(nodeIdForEvent({ gate: "state_update", step: null, agent: "V3 State Reducer" })).toBe("state_update");
  expect(nodeIdForEvent({ gate: "artifact_writing", step: null, agent: "V3 Artifact Writer" })).toBe("artifact_writing");
  expect(nodeIdForEvent({ gate: "artifact_review", step: null, agent: "Artifact Reviewer" })).toBe("artifact_review");
  expect(nodeIdForEvent({ gate: "export", step: null, agent: "V3 Master Agent" })).toBe("export");
});

test("counts V3 Agent Kernel source updates as evidence signals", () => {
  expect(countEvidenceSignals([
    {
      event_type: "node_progress",
      gate: "state_update",
      step: null,
      agent: "V3 State Reducer",
      message: "State Update: sources+8, claims+8, questions+0, artifacts+0",
      data: null,
      severity: "info",
      timestamp: Date.now(),
    },
    {
      event_type: "node_progress",
      gate: "tool_execution",
      step: null,
      agent: "search_web",
      message: "Observation: 搜索「API中转站」返回 8 条，采纳 8 条，去重/过滤 0 条。",
      data: null,
      severity: "info",
      timestamp: Date.now(),
    },
  ])).toBe(8);
});

test("builds user-facing Agent brief cards from kernel trace events", () => {
  const cards = buildAgentBriefCards([
    {
      event_type: "node_progress",
      gate: "agent_decide",
      step: null,
      agent: "V3 Master Agent",
      message: "Thought Summary: 当前 State 完全空白，需要先做基础搜索。",
      data: null,
      severity: "info",
      timestamp: Date.now(),
    },
    {
      event_type: "node_progress",
      gate: "tool_execution",
      step: null,
      agent: "V3 Tool Executor",
      message: "Action: search_web - 为 L1 建立定义和需求基础。",
      data: null,
      severity: "info",
      timestamp: Date.now(),
    },
    {
      event_type: "node_progress",
      gate: "tool_execution",
      step: null,
      agent: "search_web",
      message: "Observation: 搜索「API中转站 是什么」返回 8 条，采纳 8 条，去重/过滤 0 条。",
      data: null,
      severity: "info",
      timestamp: Date.now(),
    },
  ]);

  expect(cards.map((card) => card.label)).toEqual(["Agent 判断", "准备行动", "工具结果"]);
  expect(cards[1].summary).toContain("search_web");
  expect(cards[2].summary).toContain("采纳 8 条");
});

test("renders the landing page with search input", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "SectorBreaker" })).toBeInTheDocument();
  expect(screen.getByPlaceholderText(/AI Agent 工具/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /开始构建知识库/ })).toBeInTheDocument();
  expect(screen.getByText("可靠优先")).toBeInTheDocument();
});

test("shows configured search and extraction providers on landing page", async () => {
  render(<App />);

  expect(await screen.findByText("搜索 Provider")).toBeInTheDocument();
  expect(screen.getByText("tavily")).toBeInTheDocument();
  expect(screen.getByText("抽取 Provider")).toBeInTheDocument();
  expect(screen.getByText("firecrawl")).toBeInTheDocument();
});

test("shows explicit warning when search is not configured", async () => {
  mockGetSearchConfig.mockResolvedValueOnce({
    configured: false,
    provider: undefined,
    providers: [],
    requested_provider_mode: "auto",
    extraction_provider: undefined,
    extraction_providers: [],
    requested_extraction_provider: "http",
    missing_configuration: ["tavily_api_key", "serper_api_key"],
    diagnostics: ["至少需要配置 Tavily 或 Serper 的一个 API Key，开放网络搜索才会启用。"],
    status_message: "搜索未配置：请至少填写 Tavily 或 Serper 的一个 API Key。",
  });

  render(<App />);

  expect(await screen.findByText(/搜索未配置/)).toBeInTheDocument();
});

test("startRun is called when button is clicked", async () => {
  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  fireEvent.click(await screen.findByLabelText("中国企业与披露信源"));
  fireEvent.click(screen.getByRole("button", { name: "仅限所选" }));
  await waitFor(() => expect(screen.getByRole("button", { name: /开始构建知识库/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始构建知识库/ }));
  await waitFor(() => expect(mockStartRun).toHaveBeenCalled());
  expect(mockCreateProject).toHaveBeenCalledWith(expect.objectContaining({
    project_mode: "domain_knowledge",
    source_preferences: {
      source_pack_ids: ["company_china_pack"],
      custom_allowed_domains: [],
      blocked_domains: [],
      enforcement: "require",
    },
  }));
  expect(mockStartRun).toHaveBeenCalledWith("project-1", true);
  expect(mockResumeRun).not.toHaveBeenCalled();
});

test("adopts an existing Vault without requiring an Agent bootstrap run", async () => {
  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "RAG 知识库" } });
  fireEvent.change(screen.getByLabelText("已有 Obsidian / Markdown Vault（可选）"), {
    target: { value: "D:\\Knowledge\\RAG" },
  });
  fireEvent.click(screen.getByRole("button", { name: "接管现有 Vault" }));

  await waitFor(() => expect(mockCreateProject).toHaveBeenCalled());
  expect(mockImportVault).toHaveBeenCalledWith("project-1", { source_path: "D:\\Knowledge\\RAG" });
  expect(mockAuditVault).toHaveBeenCalledWith("project-1");
  expect(mockStartRun).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.getByText("知识库自治管理")).toBeInTheDocument());
});

test("onComplete fetches artifacts and transitions to result when snapshot completed", async () => {
  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /开始构建知识库/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始构建知识库/ }));
  await waitFor(() => expect(onCompleteRef).toBeTruthy());

  // Trigger onComplete
  await onCompleteRef!();

  await waitFor(() => expect(mockGetRunSnapshot).toHaveBeenCalled());
  expect(mockListArtifacts).toHaveBeenCalled();
  expect(mockListEvidence).toHaveBeenCalled();
  expect(await screen.findByText("证据账本")).toBeInTheDocument();
});

test("completed project exposes the V3 knowledge management control plane", async () => {
  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /开始构建知识库/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始构建知识库/ }));
  await waitFor(() => expect(onCompleteRef).toBeTruthy());
  await onCompleteRef!();

  expect(await screen.findByRole("heading", { name: "知识库自治管理" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("本地 Vault 路径"), { target: { value: "D:\\Vault" } });
  fireEvent.click(screen.getByRole("button", { name: "导入并审计" }));

  await waitFor(() => expect(mockImportVault).toHaveBeenCalledWith("project-1", { source_path: "D:\\Vault" }));
  expect(mockAuditVault).toHaveBeenCalledWith("project-1");
});

test("shows hybrid retrieval provenance on the answer and each citation", async () => {
  mockGrowKnowledge.mockResolvedValueOnce({
    answer: "内部资料可通过混合检索召回。",
    citations: ["EV-LEX", "DOC-VEC", "ART-HYBRID"],
    citation_details: [
      {
        source_id: "EV-LEX",
        source_type: "evidence",
        title: "关键词证据",
        snippet: "关键词召回内容",
        score: 0.02,
        retrieval_mode: "lexical",
        lexical_rank: 1,
      },
      {
        source_id: "DOC-VEC",
        source_type: "document_segment",
        title: "语义文档",
        snippet: "向量召回内容",
        score: 0.02,
        retrieval_mode: "vector",
        vector_rank: 1,
        embedding_model: "BAAI/bge-small-zh-v1.5",
      },
      {
        source_id: "ART-HYBRID",
        source_type: "vault_note",
        title: "融合笔记",
        snippet: "融合召回内容",
        score: 0.03,
        retrieval_mode: "hybrid",
        lexical_rank: 2,
        vector_rank: 2,
        embedding_model: "BAAI/bge-small-zh-v1.5",
      },
    ],
    retrieval_mode: "hybrid",
    embedding_model: "BAAI/bge-small-zh-v1.5",
    retrieval_diagnostics: {
      effective_mode: "hybrid",
      embedding_provider: "fastembed",
      embedding_model: "BAAI/bge-small-zh-v1.5",
      dimension: 512,
      index_count: 3,
      lexical_candidates: 2,
      vector_candidates: 2,
      last_error: null,
    },
    artifact_id: "FOLLOWUP-1",
    artifact_path: "followups/hybrid-rag.md",
    updated_artifact_count: 2,
  });

  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /开始构建知识库/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始构建知识库/ }));
  await waitFor(() => expect(onCompleteRef).toBeTruthy());
  await onCompleteRef!();

  fireEvent.change(await screen.findByPlaceholderText("基于证据账本继续追问"), { target: { value: "如何检索内部资料？" } });
  fireEvent.click(screen.getByRole("button", { name: "追问并补库" }));

  expect(await screen.findByText("向量召回")).toBeInTheDocument();
  expect(screen.getByText("关键词召回")).toBeInTheDocument();
  expect(screen.getAllByText("混合召回").length).toBeGreaterThanOrEqual(2);
  expect(screen.getAllByText("BAAI/bge-small-zh-v1.5").length).toBeGreaterThanOrEqual(1);
});

test("failed snapshot renders visible error instead of blank screen", async () => {
  mockGetRunSnapshot.mockResolvedValueOnce({
    run_id: "run-1",
    project_id: "project-1",
    status: "failed",
    current_stage: "knowledge_structuring",
    progress: { current: 2, total: 3 },
    events: [],
    errors: [{
      event_type: "error",
      gate: "knowledge_structuring",
      step: null,
      agent: null,
      message: "LLM 调用失败",
      data: null,
      progress_current: null,
      progress_total: null,
      severity: "error",
      timestamp: Date.now(),
    }],
    artifact_summary: [],
    updated_at: new Date().toISOString(),
  });

  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /开始构建知识库/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始构建知识库/ }));
  await waitFor(() => expect(onCompleteRef).toBeTruthy());
  await onCompleteRef!();

  expect((await screen.findAllByText("LLM 调用失败")).length).toBeGreaterThan(0);
  expect(screen.getByText(/运行状态：failed/)).toBeInTheDocument();
  expect(screen.getByText("运行失败")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "查看已生成内容" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "查看已生成内容" }));
  expect(await screen.findByText("证据账本")).toBeInTheDocument();
});

test("interrupted snapshot offers real checkpoint recovery", async () => {
  mockGetRunSnapshot.mockResolvedValueOnce({
    run_id: "run-1",
    project_id: "project-1",
    status: "interrupted",
    current_stage: "agent_decide",
    terminal_reason: "lease_expired",
    can_recover: true,
    progress: { current: 1, total: 3 },
    events: [],
    errors: [],
    artifact_summary: [],
    updated_at: new Date().toISOString(),
  });

  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /开始构建知识库/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始构建知识库/ }));
  await waitFor(() => expect(onCompleteRef).toBeTruthy());
  await onCompleteRef!();

  expect(await screen.findByText("运行已中断，可从检查点恢复")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "恢复运行" }));
  await waitFor(() => expect(mockRecoverRun).toHaveBeenCalledWith("run-1"));
});

test("config panel can test search connectivity", async () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: /LLM 设置/ }));

  expect(await screen.findByText(/搜索链路自检/)).toBeInTheDocument();
  expect(screen.getByText(/当前搜索 provider: tavily \/ 抽取 provider: firecrawl/)).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: /申请 \/ 获取 Key/ }).some((link) => link.getAttribute("href") === "https://app.tavily.com/home")).toBe(true);
  expect(screen.getAllByRole("link", { name: /额度与价格/ }).length).toBeGreaterThan(0);

  fireEvent.change(screen.getByLabelText("测试信源策略"), { target: { value: "reliable_only" } });
  fireEvent.change(screen.getByLabelText("允许域名（可选）"), { target: { value: "sec.gov, investor.example.com" } });
  fireEvent.change(screen.getByLabelText("排除域名（可选）"), { target: { value: "medium.com" } });
  fireEvent.click(screen.getByRole("button", { name: /测试搜索链路/ }));

  await waitFor(() => expect(mockTestSearchConnection).toHaveBeenCalled());
  expect(mockTestSearchConnection).toHaveBeenCalledWith(expect.objectContaining({
    source_policy: "reliable_only",
    allowed_domains: ["sec.gov", "investor.example.com"],
    blocked_domains: ["medium.com"],
  }));
  expect(await screen.findByText(/搜索\/抽取链路可用/)).toBeInTheDocument();
  expect(screen.getByText(/Source policy: reliable_only/)).toBeInTheDocument();
  expect(screen.getByText(/Allowed domains: sec.gov, investor.example.com/)).toBeInTheDocument();
  expect(screen.getByText(/Blocked domains: medium.com/)).toBeInTheDocument();
  expect(screen.getByText(/Official Market Report/)).toBeInTheDocument();
});

test("config panel can apply and save local llm presets", async () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: /LLM 设置/ }));

  expect(await screen.findByText(/LLM 预设/)).toBeInTheDocument();
  expect(screen.getAllByText(/DeepSeek 官方/).length).toBeGreaterThan(0);

  fireEvent.change(screen.getByLabelText("选择预设"), { target: { value: "sensenova-v4-flash" } });
  fireEvent.change(screen.getByLabelText("API Key *"), { target: { value: "sk-local-only" } });
  fireEvent.click(screen.getByRole("button", { name: /应用预设/ }));

  await waitFor(() => expect(mockApplyLLMPreset).toHaveBeenCalledWith("sensenova-v4-flash", { api_key: "sk-local-only" }));

  fireEvent.change(screen.getByLabelText("预设名称"), { target: { value: "Custom Fast" } });
  fireEvent.change(screen.getByLabelText("Base URL *"), { target: { value: "https://api.custom.test/v1" } });
  fireEvent.change(screen.getByLabelText("Model *"), { target: { value: "custom-fast" } });
  fireEvent.click(screen.getByRole("button", { name: /保存为预设/ }));

  await waitFor(() => expect(mockUpsertLLMPreset).toHaveBeenCalledWith(expect.stringMatching(/^custom-fast/), expect.objectContaining({
    name: "Custom Fast",
    base_url: "https://api.custom.test/v1",
    api_key: "sk-local-only",
    model: "custom-fast",
    max_tokens: 4096,
  })));
});

test("config panel can save search runtime config", async () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: /LLM 设置/ }));
  expect(await screen.findByText(/搜索与抽取配置/)).toBeInTheDocument();
  expect(await screen.findByText(/仅域名过滤发现，无直连适配器/)).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText(/Tavily API Key/), { target: { value: "tvly-test-key" } });
  fireEvent.click(screen.getByRole("button", { name: /保存搜索配置/ }));

  await waitFor(() => expect(mockUpdateSearchConfig).toHaveBeenCalled());
  expect(mockUpdateSearchConfig).toHaveBeenCalledWith(expect.objectContaining({
    search_provider_mode: "auto",
    tavily_api_key: "tvly-test-key",
    serper_api_key: undefined,
    brave_api_key: undefined,
    exa_api_key: undefined,
  }));
});

test("saving Tavily config refreshes landing search status without manual reload", async () => {
  mockGetSearchConfig
    .mockResolvedValueOnce({
      configured: false,
      providers: [],
      requested_provider_mode: "tavily",
      extraction_providers: ["http"],
      requested_extraction_provider: "http",
      missing_configuration: ["tavily_api_key"],
      diagnostics: ["请填写 Tavily API Key。"],
      status_message: "搜索未配置：请填写 Tavily API Key。",
    })
    .mockResolvedValueOnce({
      configured: false,
      providers: [],
      requested_provider_mode: "tavily",
      extraction_providers: ["http"],
      requested_extraction_provider: "http",
      missing_configuration: ["tavily_api_key"],
      diagnostics: ["请填写 Tavily API Key。"],
      status_message: "搜索未配置：请填写 Tavily API Key。",
    })
    .mockResolvedValueOnce({
      configured: true,
      provider: "tavily",
      providers: ["tavily"],
      requested_provider_mode: "tavily",
      extraction_provider: "http",
      extraction_providers: ["http"],
      requested_extraction_provider: "http",
      missing_configuration: [],
      diagnostics: [],
      status_message: "搜索已就绪：tavily。",
    });

  render(<App />);
  expect(await screen.findByRole("button", { name: /搜索未配置/ })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /搜索未配置/ }));
  expect(await screen.findByText(/搜索与抽取配置/)).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText(/Tavily API Key/), { target: { value: "tvly-test-key" } });
  fireEvent.click(screen.getByRole("button", { name: /保存搜索配置/ }));

  await waitFor(() => expect(mockUpdateSearchConfig).toHaveBeenCalled());
  await waitFor(() => expect(screen.queryByRole("button", { name: /搜索未配置/ })).not.toBeInTheDocument());
  expect(await screen.findByText("搜索 Provider")).toBeInTheDocument();
  expect(screen.getByText("tavily")).toBeInTheDocument();
});

test("uploads assistant brief file before starting research", async () => {
  render(<App />);

  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  fireEvent.click(screen.getByRole("button", { name: /可选：粘贴 Gemini/ }));

  const file = new File(["# brief"], "brief.md", { type: "text/markdown" });
  const fileInput = screen.getByLabelText("上传外部 AI 报告文件");
  fireEvent.change(fileInput, { target: { files: [file] } });

  fireEvent.click(screen.getByRole("button", { name: /开始构建知识库/ }));

  await waitFor(() => expect(mockUploadDocument).toHaveBeenCalled());
  expect(mockStartRun).toHaveBeenCalled();
});

test("renders QA report as readable action lists", async () => {
  mockEventsState.current = [
    {
      event_type: "node_blocked",
      gate: "qa_critic",
      step: null,
      agent: "QA Critic",
      message: "质量门发现问题",
      severity: "error",
      timestamp: Date.now(),
      data: {
        passed: false,
        blocking_issues: ["产物包含缺少强证据支撑的事实主张: ART-MARKET-OVERVIEW"],
        retry_tasks: ["补充可靠来源并重新生成相关产物，或把这些主张降级为待验证问题。"],
        user_action_needed: ["如果你手头有可靠报告或公开来源，可上传补充。"],
        can_continue_with_warning: false,
      },
    },
  ];
  mockGetRun.mockResolvedValueOnce({
    id: "run-1",
    project_id: "project-1",
    status: "waiting_for_human",
    current_gate: "qa_critic",
    created_at: new Date().toISOString(),
    completed_at: null,
  });
  mockGetRunSnapshot.mockResolvedValueOnce({
    run_id: "run-1",
    project_id: "project-1",
    status: "waiting_for_human",
    current_stage: "qa_critic",
    progress: { current: 2, total: 3 },
    events: mockEventsState.current,
    errors: [],
    artifact_summary: [],
    can_resume: true,
    updated_at: new Date().toISOString(),
  });

  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /开始构建知识库/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始构建知识库/ }));
  await waitFor(() => expect(onCompleteRef).toBeTruthy());
  await onCompleteRef!();

  expect(await screen.findByText("QA 阻塞")).toBeInTheDocument();
  expect(screen.getByText("阻塞项")).toBeInTheDocument();
  expect(screen.getByText(/ART-MARKET-OVERVIEW/)).toBeInTheDocument();
  expect(screen.getByText("重试任务")).toBeInTheDocument();
  expect(screen.getByText("需要你补充")).toBeInTheDocument();
});

test("filters evidence ledger in result view", async () => {
  mockGetRun.mockResolvedValueOnce({
    id: "run-1",
    project_id: "project-1",
    status: "completed",
    current_gate: "export",
    created_at: new Date().toISOString(),
    completed_at: new Date().toISOString(),
  });

  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /开始构建知识库/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始构建知识库/ }));
  await waitFor(() => expect(onCompleteRef).toBeTruthy());
  await onCompleteRef!();

  expect(await screen.findByText("证据账本")).toBeInTheDocument();
  expect(screen.getByText("用户输入范围")).toBeInTheDocument();
  expect(screen.getByText("营销博客")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("证据质量筛选"), { target: { value: "low" } });
  expect(screen.queryByText("用户输入范围")).not.toBeInTheDocument();
  expect(screen.getByText("营销博客")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("证据质量筛选"), { target: { value: "all" } });
  fireEvent.click(screen.getByText("仅看风险项"));
  expect(screen.queryByText("用户输入范围")).not.toBeInTheDocument();
  expect(screen.getByText("营销博客")).toBeInTheDocument();
});

test("completed result shows run trace and cleans long evidence snippets", async () => {
  mockGetRunSnapshot.mockResolvedValueOnce({
    run_id: "run-1",
    project_id: "project-1",
    status: "completed",
    current_stage: "completed",
    progress: { current: 3, total: 3 },
    events: [
      {
        event_type: "node_started",
        gate: "source_collection",
        step: null,
        agent: null,
        message: "开始收集 V1 领域资料",
        data: null,
        progress_current: 1,
        progress_total: 3,
        severity: "info",
        timestamp: Date.now(),
      },
      {
        event_type: "node_completed",
        gate: "knowledge_structuring",
        step: null,
        agent: null,
        message: "V1 知识系统生成完成",
        data: null,
        progress_current: 2,
        progress_total: 3,
        severity: "info",
        timestamp: Date.now(),
      },
      {
        event_type: "node_progress",
        gate: "artifact_review",
        step: null,
        agent: "Artifact Reviewer",
        message: "正在审查详实度：领域总览",
        data: null,
        progress_current: 1,
        progress_total: 7,
        severity: "info",
        timestamp: Date.now(),
      },
    ],
    errors: [],
    artifact_summary: [
      { id: "A1", title: "领域总览", content_path: "00-领域总览.md", artifact_type: "domain_overview" },
    ],
    updated_at: new Date().toISOString(),
  });
  mockListArtifacts.mockResolvedValueOnce([
    { id: "A1", title: "领域总览", content_path: "00-领域总览.md", artifact_type: "domain_overview", schema_version: "v1" },
    { id: "C1", title: "RAG", content_path: "concepts/RAG.md", artifact_type: "core_concepts", schema_version: "v1-card" },
    { id: "Q1", title: "待验证问题 1", content_path: "questions/待验证问题 1.md", artifact_type: "unresolved_questions", schema_version: "v1-card" },
  ]);
  mockListEvidence.mockResolvedValueOnce([
    {
      id: "EV-LONG",
      source_title: "VoltAgent/awesome-openclaw-skills - GitHub",
      source_url: "https://github.com/VoltAgent/awesome-openclaw-skills",
      source_quality: "unknown",
      verification_status: "partially_verified",
      source_type: "web",
      needs_counterevidence: true,
      snippet:
        "[Skip to content](https://github.com/VoltAgent/awesome-openclaw-skills#start-of-content). " +
        "[Sign in](https://github.com/login). Navigation Menu. Search code, repositories, users, issues, pull requests. " +
        "Agent development frameworks compare LangGraph, CrewAI, OpenAI Agents SDK, evaluation, tool calling, memory, orchestration, deployment, and production safety patterns. " +
        "This practical repository is useful as a lead but needs verification. ".repeat(12),
    },
  ]);

  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "Agent开发" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /开始构建知识库/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始构建知识库/ }));
  await waitFor(() => expect(onCompleteRef).toBeTruthy());
  await onCompleteRef!();

  expect(await screen.findByText("运行轨迹")).toBeInTheDocument();
  expect(screen.getByText("V1 知识系统生成完成")).toBeInTheDocument();
  expect(screen.getByText("结果质量摘要")).toBeInTheDocument();
  expect(screen.getByText("知识卡片")).toBeInTheDocument();
  expect(screen.getByText("审查补写事件")).toBeInTheDocument();
  expect(screen.getByText("待验证问题")).toBeInTheDocument();
  expect(screen.getByText(/点击导出生成 Obsidian Vault/)).toBeInTheDocument();
  expect(screen.queryByText(/Skip to content/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Navigation Menu/)).not.toBeInTheDocument();
  expect(screen.getByText(/Agent development frameworks compare LangGraph/)).toBeInTheDocument();
});

test("config panel shows reliable source onboarding and key requirements", async () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: /LLM 设置/ }));

  expect(await screen.findByText("可靠信源接入")).toBeInTheDocument();
  expect(screen.getAllByText("中国企业与披露信源").length).toBeGreaterThan(0);
  expect(screen.getByText("巨潮资讯公开披露")).toBeInTheDocument();
  expect(screen.getByText("企查查开放平台")).toBeInTheDocument();
  expect(screen.getByText(/需要 QCC_API_KEY/)).toBeInTheDocument();
  expect(screen.getByText(/先配置 Tavily/)).toBeInTheDocument();
});

test("landing search warning opens settings when search key is missing", async () => {
  mockGetSearchConfig.mockResolvedValueOnce({
    configured: false,
    providers: [],
    requested_provider_mode: "auto",
    extraction_providers: ["http"],
    requested_extraction_provider: "http",
    missing_configuration: ["tavily_api_key"],
    diagnostics: ["至少需要配置 Tavily、Serper、Brave、Exa 或 Firecrawl 之一的 API Key，开放网络搜索才会启用。"],
    status_message: "搜索未配置：请至少填写 Tavily、Serper、Brave、Exa 或 Firecrawl 之一的 API Key。",
  });

  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: /搜索未配置/ }));

  expect(await screen.findByText("可靠信源接入")).toBeInTheDocument();
});
