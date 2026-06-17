import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

// Use vi.hoisted so variables are available in vi.mock factories
const { mockGetLLMConfig, mockCreateProject, mockStartRun, mockGetRun,
        mockListArtifacts, mockListEvidence, mockAskQuestion, mockExportProject, mockGetWorkflow } = vi.hoisted(() => ({
  mockGetLLMConfig: vi.fn().mockResolvedValue({ configured: true, base_url: "http://test", model: "test" }),
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
    { id: "EV-USER-SCOPE", source_title: "用户输入范围", snippet: "用户希望研究 AI Agent 工具" },
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
    return { events: [], isConnected: false, reset: () => {} };
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
});

test("renders the landing page with search input", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "SectorBreaker" })).toBeInTheDocument();
  expect(screen.getByPlaceholderText(/AI Agent 工具/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /生成计划/ })).toBeInTheDocument();
  expect(screen.getByText("可靠优先")).toBeInTheDocument();
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
