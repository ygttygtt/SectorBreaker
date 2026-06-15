import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "./App";

test("renders the research workbench first", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "SectorBreaker" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "破壁工作台" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "阶段关口" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "证据与产物" })).toBeInTheDocument();
  expect(screen.getByText("下一步：接入真实 LLM 与检索任务")).toBeInTheDocument();
});
