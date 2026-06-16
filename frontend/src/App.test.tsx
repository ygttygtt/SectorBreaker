import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

// Mock useRunEvents to avoid EventSource issues in jsdom
vi.mock("./hooks/useRunEvents", () => ({
  useRunEvents: () => ({ events: [], isConnected: false, reset: () => {} }),
}));

import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const projectMock = {
  id: "project-1",
  title: "AI Agent 工具",
  domain: "AI Agent 工具",
  market_scope: "mixed",
  depth: "quick",
  status: "draft",
};

const runMock = {
  id: "run-1",
  project_id: "project-1",
  status: "completed",
  current_gate: "export",
  current_step: null,
  created_at: new Date().toISOString(),
  completed_at: new Date().toISOString(),
};

const artifactsMock = [
  { id: "ART-RESEARCH-FRAME", title: "研究框架", content_path: "00-研究框架/research-frame.md" },
];

const evidenceMock = [
  { id: "EV-USER-SCOPE", source_title: "用户输入范围", snippet: "用户希望研究 AI Agent 工具" },
];

function mockFetch(responses: Record<string, unknown> = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/projects" && !responses[url]) {
      return new Response(JSON.stringify(projectMock), { status: 200 });
    }
    if (url === "/api/projects/project-1/runs") {
      return new Response(JSON.stringify(runMock), { status: 200 });
    }
    if (url === "/api/projects/project-1/artifacts") {
      return new Response(JSON.stringify(artifactsMock), { status: 200 });
    }
    if (url === "/api/projects/project-1/evidence") {
      return new Response(JSON.stringify(evidenceMock), { status: 200 });
    }
    if (responses[url]) {
      return new Response(JSON.stringify(responses[url]), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
}

async function startResearch(domain = "AI Agent 工具") {
  const input = screen.getByPlaceholderText(/AI Agent 工具/);
  fireEvent.change(input, { target: { value: domain } });
  fireEvent.click(screen.getByRole("button", { name: /开始破壁/ }));
  // Wait for review phase
  await waitFor(() => expect(screen.getByText(/完成/)).toBeInTheDocument());
  // Click "跳过，直接继续" to go to result
  fireEvent.click(screen.getByRole("button", { name: /跳过/ }));
  await waitFor(() => expect(screen.getByText("研究完成")).toBeInTheDocument());
}

test("renders the landing page with search input", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "SectorBreaker" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "你想了解什么领域？" })).toBeInTheDocument();
  expect(screen.getByPlaceholderText(/AI Agent 工具/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /开始破壁/ })).toBeInTheDocument();
  expect(screen.getByText("范围确认")).toBeInTheDocument();
  expect(screen.getByText("导出")).toBeInTheDocument();
});

test("starts a research run, reviews, and shows result", async () => {
  mockFetch();

  render(<App />);

  await startResearch();

  expect(screen.getAllByText("研究框架").length).toBeGreaterThanOrEqual(1);
});

test("asks a project question after research completes", async () => {
  mockFetch({
    "/api/projects/project-1/chat": {
      answer: "建议先看研究框架。",
      citations: ["EV-USER-SCOPE"],
    },
  });

  render(<App />);

  await startResearch();

  fireEvent.change(screen.getByLabelText("项目问题"), { target: { value: "应该先学什么" } });
  fireEvent.click(screen.getByRole("button", { name: "询问" }));

  await waitFor(() => expect(screen.getByText("建议先看研究框架。")).toBeInTheDocument());
  expect(screen.getByText("引用：EV-USER-SCOPE")).toBeInTheDocument();
});

test("exports the current project", async () => {
  mockFetch({
    "/api/projects/project-1/exports": {
      export_version: "1",
      project_id: "project-1",
      artifact_paths: ["00-研究框架/research-frame.md"],
      evidence_ids: ["EV-USER-SCOPE"],
    },
  });

  render(<App />);

  await startResearch();

  fireEvent.click(screen.getByRole("button", { name: /导出知识库/ }));

  await waitFor(() => expect(screen.getByText("已导出 1 个文件")).toBeInTheDocument());
});
