import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("renders the research workbench first", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "SectorBreaker" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "破壁工作台" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "阶段关口" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "证据与产物" })).toBeInTheDocument();
  expect(screen.getByText("下一步：接入真实 LLM 与检索任务")).toBeInTheDocument();
});

test("starts a research run through the api", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/projects") {
      return new Response(
        JSON.stringify({
          id: "project-1",
          title: "AI Agent Tools",
          domain: "AI Agent 工具",
          market_scope: "mixed",
          depth: "quick"
        }),
        { status: 200 }
      );
    }
    if (url === "/api/projects/project-1/runs") {
      return new Response(
        JSON.stringify({
          current_gate: "export",
          artifacts: [
            {
              id: "ART-RESEARCH-FRAME",
              title: "研究框架",
              content_path: "00-研究框架/research-frame.md"
            }
          ]
        }),
        { status: 200 }
      );
    }
    if (url === "/api/projects/project-1/evidence") {
      return new Response(
        JSON.stringify([
          {
            id: "EV-USER-SCOPE",
            source_title: "用户输入范围",
            snippet: "用户希望研究 AI Agent 工具"
          }
        ]),
        { status: 200 }
      );
    }
    return new Response("{}", { status: 200 });
  });

  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "启动研究" }));

  await waitFor(() => expect(screen.getByText("ART-RESEARCH-FRAME")).toBeInTheDocument());
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/projects",
    expect.objectContaining({ method: "POST" })
  );
});

test("asks a project question after a run", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/projects") {
      return new Response(
        JSON.stringify({
          id: "project-1",
          title: "AI Agent Tools",
          domain: "AI Agent 工具",
          market_scope: "mixed",
          depth: "quick"
        }),
        { status: 200 }
      );
    }
    if (url === "/api/projects/project-1/runs") {
      return new Response(JSON.stringify({ current_gate: "export", artifacts: [] }), { status: 200 });
    }
    if (url === "/api/projects/project-1/evidence") {
      return new Response(JSON.stringify([]), { status: 200 });
    }
    if (url === "/api/projects/project-1/chat") {
      return new Response(
        JSON.stringify({
          answer: "建议先看研究框架。",
          citations: ["EV-USER-SCOPE"]
        }),
        { status: 200 }
      );
    }
    return new Response("{}", { status: 200 });
  });

  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "启动研究" }));
  await waitFor(() => expect(screen.getByText("运行完成")).toBeInTheDocument());

  fireEvent.change(screen.getByLabelText("项目问题"), { target: { value: "应该先学什么" } });
  fireEvent.click(screen.getByRole("button", { name: "询问" }));

  await waitFor(() => expect(screen.getByText("建议先看研究框架。")).toBeInTheDocument());
  expect(screen.getByText("引用：EV-USER-SCOPE")).toBeInTheDocument();
});

test("exports the current project", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/projects") {
      return new Response(
        JSON.stringify({
          id: "project-1",
          title: "AI Agent Tools",
          domain: "AI Agent 工具",
          market_scope: "mixed",
          depth: "quick"
        }),
        { status: 200 }
      );
    }
    if (url === "/api/projects/project-1/runs") {
      return new Response(JSON.stringify({ current_gate: "export", artifacts: [] }), { status: 200 });
    }
    if (url === "/api/projects/project-1/evidence") {
      return new Response(JSON.stringify([]), { status: 200 });
    }
    if (url === "/api/projects/project-1/exports") {
      return new Response(
        JSON.stringify({
          export_version: "1",
          project_id: "project-1",
          artifact_paths: ["00-研究框架/research-frame.md"],
          evidence_ids: ["EV-USER-SCOPE"]
        }),
        { status: 200 }
      );
    }
    return new Response("{}", { status: 200 });
  });

  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "启动研究" }));
  await waitFor(() => expect(screen.getByText("运行完成")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "导出知识库" }));

  await waitFor(() => expect(screen.getByText("已导出 1 个文件")).toBeInTheDocument());
});
