import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

// Use vi.hoisted so variables are available in vi.mock factories
const {
  mockEventsState,
  mockGetLLMConfig,
  mockCreateProject,
  mockStartRun,
  mockGetRun,
  mockGetSearchConfig,
  mockUpdateSearchConfig,
  mockTestSearchConnection,
  mockUploadDocument,
  mockListArtifacts,
  mockListEvidence,
  mockAskQuestion,
  mockExportProject,
  mockGetWorkflow,
  mockGetSourceRegistryStatus,
} = vi.hoisted(() => ({
  mockEventsState: { current: [] as Array<Record<string, unknown>> },
  mockGetLLMConfig: vi.fn().mockResolvedValue({ configured: true, base_url: "http://test", model: "test" }),
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
            configured: true,
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
    configured_connector_count: 1,
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
    missing_configuration: [],
    diagnostics: [],
    status_message: "搜索已就绪：tavily；抽取使用 firecrawl。",
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
    market_scope: "mixed", depth: "quick", source_policy: "reliable_first", status: "draft",
  }),
  mockStartRun: vi.fn().mockResolvedValue({
    id: "run-1", project_id: "project-1", status: "running",
    current_gate: "scope", created_at: new Date().toISOString(), completed_at: null,
  }),
  mockGetRun: vi.fn().mockResolvedValue({
    id: "run-1", project_id: "project-1", status: "waiting_for_human",
    current_gate: "scope", created_at: new Date().toISOString(), completed_at: null,
  }),
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
  mockExportProject: vi.fn().mockResolvedValue({
    export_version: "1", project_id: "project-1",
    artifact_paths: ["00-研究框架/research-frame.md"], evidence_ids: ["EV-USER-SCOPE"],
  }),
  mockGetWorkflow: vi.fn().mockResolvedValue({ schema_version: "1", nodes: [], edges: [] }),
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
    getRunWorkflowDefinition: mockGetWorkflow,
    getProjectWorkflowDefinition: mockGetWorkflow,
    getLLMConfig: mockGetLLMConfig,
    getSearchConfig: mockGetSearchConfig,
    updateSearchConfig: mockUpdateSearchConfig,
    testSearchConnection: mockTestSearchConnection,
    getSourceRegistryStatus: mockGetSourceRegistryStatus,
    uploadDocument: mockUploadDocument,
    listArtifacts: mockListArtifacts,
    listEvidence: mockListEvidence,
    askQuestion: mockAskQuestion,
    exportProject: mockExportProject,
    updateLLMConfig: vi.fn().mockResolvedValue({ success: true }),
    testLLMConnection: vi.fn().mockResolvedValue({ success: true, message: "OK" }),
    addUserInput: vi.fn().mockResolvedValue({ status: "ok", input_id: "ui-1" }),
    resumeRun: vi.fn().mockResolvedValue({ status: "resumed", run_id: "run-1" }),
  },
}));

import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  onCompleteRef = null;
  mockEventsState.current = [];
});

test("renders the landing page with search input", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "SectorBreaker" })).toBeInTheDocument();
  expect(screen.getByPlaceholderText(/AI Agent 工具/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /生成计划/ })).toBeInTheDocument();
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
  await waitFor(() => expect(screen.getByRole("button", { name: /生成计划/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /生成计划/ }));
  await waitFor(() => expect(mockStartRun).toHaveBeenCalled());
});

test("onComplete fetches artifacts and transitions to reviewing", async () => {
  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /生成计划/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /生成计划/ }));
  await waitFor(() => expect(onCompleteRef).toBeTruthy());

  // Trigger onComplete
  await onCompleteRef!();

  // Should call getRun, listArtifacts, listEvidence
  await waitFor(() => expect(mockGetRun).toHaveBeenCalled());
  expect(mockListArtifacts).toHaveBeenCalled();
  expect(mockListEvidence).toHaveBeenCalled();
});

test("config panel can test search connectivity", async () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: /LLM 设置/ }));

  expect(await screen.findByText(/搜索链路自检/)).toBeInTheDocument();
  expect(screen.getByText(/当前搜索 provider: tavily \/ 抽取 provider: firecrawl/)).toBeInTheDocument();

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

test("config panel can save search runtime config", async () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: /LLM 设置/ }));
  expect(await screen.findByText(/搜索与抽取配置/)).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("搜索 Provider 模式"), { target: { value: "multi" } });
  fireEvent.change(screen.getByLabelText("Tavily API Key"), { target: { value: "tvly-test-key" } });
  fireEvent.change(screen.getByLabelText("Brave API Key"), { target: { value: "brave-test-key" } });
  fireEvent.click(screen.getByRole("button", { name: /保存搜索配置/ }));

  await waitFor(() => expect(mockUpdateSearchConfig).toHaveBeenCalled());
});

test("config panel can save exa search runtime config", async () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: /LLM 设置/ }));
  expect(await screen.findByText(/搜索与抽取配置/)).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("搜索 Provider 模式"), { target: { value: "exa" } });
  fireEvent.change(screen.getByLabelText("Exa API Key"), { target: { value: "exa-test-key" } });
  fireEvent.click(screen.getByRole("button", { name: /保存搜索配置/ }));

  await waitFor(() => expect(mockUpdateSearchConfig).toHaveBeenCalled());
  expect(mockUpdateSearchConfig).toHaveBeenCalledWith(expect.objectContaining({
    search_provider_mode: "exa",
    exa_api_key: "exa-test-key",
    exa_endpoint: "https://api.exa.ai/search",
  }));
});

test("uploads assistant brief file before starting research", async () => {
  render(<App />);

  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  fireEvent.click(screen.getByRole("button", { name: /可选：粘贴 Gemini/ }));

  const file = new File(["# brief"], "brief.md", { type: "text/markdown" });
  const fileInput = screen.getByLabelText("上传外部 AI 报告文件");
  fireEvent.change(fileInput, { target: { files: [file] } });

  fireEvent.click(screen.getByRole("button", { name: /生成计划/ }));

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

  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /生成计划/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /生成计划/ }));
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
  await waitFor(() => expect(screen.getByRole("button", { name: /生成计划/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /生成计划/ }));
  await waitFor(() => expect(onCompleteRef).toBeTruthy());
  await onCompleteRef!();

  fireEvent.click(await screen.findByRole("button", { name: "跳过补充" }));

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

test("config panel shows reliable source onboarding and key requirements", async () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: /LLM 设置/ }));

  expect(await screen.findByText("可靠信源接入")).toBeInTheDocument();
  expect(screen.getByText("中国企业与披露信源")).toBeInTheDocument();
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
    diagnostics: ["至少需要配置 Tavily、Serper、Brave、Exa 四者之一的 API Key，开放网络搜索才会启用。"],
    status_message: "搜索未配置：请至少填写 Tavily、Serper、Brave、Exa 四者之一的 API Key。",
  });

  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: /搜索未配置/ }));

  expect(await screen.findByText("可靠信源接入")).toBeInTheDocument();
});
