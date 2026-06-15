import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "./App";

test("renders the research workbench first", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "SectorBreaker" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "研究驾驶舱" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "固定关口" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "证据与产物" })).toBeInTheDocument();
});
