import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

// Use vi.hoisted so variables are available in vi.mock factories
const { mockGetLLMConfig, mockCreateProject, mockStartRun, mockListArtifacts, mockListEvidence,
        mockAskQuestion, mockExportProject, mockResumeRun } = vi.hoisted(() => ({
  mockGetLLMConfig: vi.fn().mockResolvedValue({ configured: true, base_url: "http://test", model: "test" }),
  mockCreateProject: vi.fn().mockResolvedValue({
    id: "project-1", title: "AI Agent 工具", domain: "AI Agent 工具",
    market_scope: "mixed", depth: "quick", status: "draft",
  }),
  mockStartRun: vi.fn().mockResolvedValue({
    id: "run-1", project_id: "project-1", status: "running",
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
  mockResumeRun: vi.fn().mockResolvedValue({ status: "resumed", run_id: "run-1" }),
}));

let onCompleteCallback: (() => void) | null = null;

vi.mock("./hooks/useRunEvents", () => ({
  useRunEvents: ({ onComplete }: { onComplete?: () => void }) => {
    // Store the latest onComplete
    if (onComplete) onCompleteCallback = onComplete;
    return { events: [], isConnected: false, reset: () => {} };
  },
}));

vi.mock("./api/client", () => ({
  api: {
    createProject: mockCreateProject,
    startRun: mockStartRun,
    getLLMConfig: mockGetLLMConfig,
    listArtifacts: mockListArtifacts,
    listEvidence: mockListEvidence,
    askQuestion: mockAskQuestion,
    exportProject: mockExportProject,
    updateLLMConfig: vi.fn().mockResolvedValue({ success: true }),
    testLLMConnection: vi.fn().mockResolvedValue({ success: true, message: "OK" }),
    addUserInput: vi.fn().mockResolvedValue({ status: "ok", input_id: "ui-1" }),
    resumeRun: mockResumeRun,
  },
}));

import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  onCompleteCallback = null;
});

test("renders the landing page with search input", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "SectorBreaker" })).toBeInTheDocument();
  expect(screen.getByPlaceholderText(/AI Agent 工具/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /开始破壁/ })).toBeInTheDocument();
  expect(screen.getByText("范围确认")).toBeInTheDocument();
  expect(screen.getByText("导出")).toBeInTheDocument();
});

test("completes research flow and shows result", async () => {
  render(<App />);

  // Type domain first (button is disabled when domain is empty)
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });

  // Wait for button to be enabled (LLM config loaded)
  await waitFor(() => expect(screen.getByRole("button", { name: /开始破壁/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始破壁/ }));

  // Wait for startRun to be called
  await waitFor(() => expect(mockStartRun).toHaveBeenCalled());

  // Trigger onComplete manually (simulating SSE [DONE])
  await waitFor(() => expect(onCompleteCallback).toBeTruthy());
  onCompleteCallback!();

  // Should transition to reviewing
  await waitFor(() => expect(screen.getByText(/完成/)).toBeInTheDocument());

  // Click skip to go to result
  fireEvent.click(screen.getByRole("button", { name: /跳过/ }));
  await waitFor(() => expect(screen.getByText("研究完成")).toBeInTheDocument());
});

test("asks a project question", async () => {
  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /开始破壁/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始破壁/ }));
  await waitFor(() => expect(onCompleteCallback).toBeTruthy());
  onCompleteCallback!();
  await waitFor(() => expect(screen.getByText(/完成/)).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: /跳过/ }));
  await waitFor(() => expect(screen.getByText("研究完成")).toBeInTheDocument());

  fireEvent.change(screen.getByLabelText("项目问题"), { target: { value: "应该先学什么" } });
  fireEvent.click(screen.getByRole("button", { name: "询问" }));
  await waitFor(() => expect(screen.getByText("建议先看研究框架。")).toBeInTheDocument());
  expect(screen.getByText("引用：EV-USER-SCOPE")).toBeInTheDocument();
});

test("exports the project", async () => {
  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/AI Agent 工具/), { target: { value: "AI Agent 工具" } });
  await waitFor(() => expect(screen.getByRole("button", { name: /开始破壁/ })).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: /开始破壁/ }));
  await waitFor(() => expect(onCompleteCallback).toBeTruthy());
  onCompleteCallback!();
  await waitFor(() => expect(screen.getByText(/完成/)).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: /跳过/ }));
  await waitFor(() => expect(screen.getByText("研究完成")).toBeInTheDocument());

  fireEvent.click(screen.getByRole("button", { name: /导出知识库/ }));
  await waitFor(() => expect(screen.getByText("已导出 1 个文件")).toBeInTheDocument());
});
