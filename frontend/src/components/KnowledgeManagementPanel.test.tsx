import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getVaultStatus: vi.fn(),
  importVault: vi.fn(),
  auditVault: vi.fn(),
  getKnowledgeHealth: vi.fn(),
  listMaintenanceBacklog: vi.fn(),
  startMaintenanceRun: vi.fn(),
  listChangeSets: vi.fn(),
  proposeChangeSet: vi.fn(),
  approveChangeSet: vi.fn(),
  applyChangeSet: vi.fn(),
  rollbackChangeSet: vi.fn(),
  getRetrievalStatus: vi.fn(),
  reindexProject: vi.fn(),
}));

vi.mock("../api/client", () => ({ api: mocks }));

import { KnowledgeManagementPanel } from "./KnowledgeManagementPanel";

const vaultStatus = {
  project_id: "project-1",
  latest_import: {
    id: "VI-1",
    project_id: "project-1",
    source_path: "D:\\Knowledge\\Vault",
    note_count: 2,
    total_bytes: 1024,
    snapshot_hash: "abcdef1234567890",
    imported_paths: ["index.md", "cards/RAG.md"],
    skipped_paths: [],
    created_at: "2026-07-19T00:00:00Z",
  },
  active_note_count: 2,
  notes: [],
};

const healthReport = {
  id: "KHR-1",
  project_id: "project-1",
  vault_import_id: "VI-1",
  snapshot_hash: "abcdef1234567890",
  metrics: {
    active_notes: 2,
    findings: 2,
    broken_links: 1,
    orphan_notes: 0,
    missing_evidence_metadata: 1,
  },
  findings: [
    {
      id: "HF-1",
      finding_type: "broken_link",
      severity: "warning",
      target_paths: ["index.md"],
      explanation: "wikilink 没有对应的活跃笔记。",
      suggested_action: "修正链接。",
      detector: "deterministic_vault_scanner",
      auto_fixable: false,
    },
  ],
  generated_at: "2026-07-19T00:01:00Z",
};

const retrievalStatus = {
  effective_mode: "hybrid",
  embedding_provider: "fastembed",
  embedding_model: "BAAI/bge-small-zh-v1.5",
  dimension: 512,
  index_count: 18,
  lexical_candidates: 6,
  vector_candidates: 6,
  last_error: null,
};

const task = {
  id: "MT-1",
  project_id: "project-1",
  fingerprint: "fingerprint",
  finding_ids: ["HF-1"],
  task_type: "repair_link",
  objective: "修复 index.md 中的断链",
  target_paths: ["index.md"],
  priority: 2,
  status: "open",
  assigned_specialist: null,
  required_evidence_types: [],
  approval_required: true,
  change_set_id: null,
  created_at: "2026-07-19T00:01:00Z",
  updated_at: "2026-07-19T00:01:00Z",
};

function changeSet(id: string, status: string) {
  return {
    id,
    project_id: "project-1",
    task_id: "MT-1",
    status,
    summary: `${status} RAG 页面`,
    evidence_ids: ["EV-1"],
    operations: [{
      operation: "update",
      path: "cards/RAG.md",
      base_hash: "basehash123456",
      before_content: "# RAG\n旧内容",
      after_content: "# RAG\n新内容",
      unified_diff: "--- cards/RAG.md\n+++ cards/RAG.md\n-旧内容\n+新内容",
      factual_change: true,
    }],
    created_by_agent: "knowledge_editor",
    created_at: "2026-07-19T00:02:00Z",
    approved_at: null,
    applied_at: null,
    rolled_back_at: null,
    applied_artifact_ids: [],
    rollback_artifact_ids: [],
    error: null,
  };
}

function renderPanel() {
  const props = {
    projectId: "project-1",
    onMaintenanceStarted: vi.fn(),
    onArtifactsChanged: vi.fn().mockResolvedValue(undefined),
    onError: vi.fn(),
    onSuccess: vi.fn(),
  };
  render(<KnowledgeManagementPanel {...props} />);
  return props;
}

beforeEach(() => {
  mocks.getVaultStatus.mockResolvedValue(vaultStatus);
  mocks.importVault.mockResolvedValue(vaultStatus.latest_import);
  mocks.auditVault.mockResolvedValue(healthReport);
  mocks.getKnowledgeHealth.mockResolvedValue(healthReport);
  mocks.listMaintenanceBacklog.mockResolvedValue([task]);
  mocks.startMaintenanceRun.mockResolvedValue({
    run_id: "run-maintenance-1",
    status: "started",
    resumed_from_checkpoint: true,
    task_ids: ["MT-1"],
    execution_mode: "plan_only",
  });
  mocks.listChangeSets.mockResolvedValue([
    changeSet("CS-proposed", "proposed"),
    changeSet("CS-approved", "approved"),
    changeSet("CS-applied", "applied"),
  ]);
  mocks.proposeChangeSet.mockResolvedValue(changeSet("CS-new", "proposed"));
  mocks.approveChangeSet.mockResolvedValue(changeSet("CS-proposed", "approved"));
  mocks.applyChangeSet.mockResolvedValue(changeSet("CS-approved", "applied"));
  mocks.rollbackChangeSet.mockResolvedValue(changeSet("CS-applied", "rolled_back"));
  mocks.getRetrievalStatus.mockResolvedValue(retrievalStatus);
  mocks.reindexProject.mockResolvedValue({
    project_id: "project-1",
    source_chunks: 18,
    embedded_chunks: 18,
    unchanged_chunks: 0,
    deleted_chunks: 0,
    index_count: 18,
    embedding_provider: "fastembed",
    embedding_model: "BAAI/bge-small-zh-v1.5",
    dimension: 512,
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.localStorage.clear();
});

test("restores the remembered Vault path for this project", async () => {
  window.localStorage.setItem("sectorbreaker:vault-path:project-1", "D:\\Remembered\\Vault");
  renderPanel();
  expect(await screen.findByDisplayValue("D:\\Remembered\\Vault")).toBeInTheDocument();
  expect(screen.getByText(/源目录只读/)).toBeInTheDocument();
});

test("imports a local Vault and immediately creates a deterministic health report", async () => {
  const props = renderPanel();
  expect(await screen.findByText("修复 index.md 中的断链")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("本地 Vault 路径"), { target: { value: "D:\\Knowledge\\Vault" } });
  fireEvent.click(screen.getByRole("button", { name: "导入并审计" }));

  await waitFor(() => expect(mocks.importVault).toHaveBeenCalledWith("project-1", { source_path: "D:\\Knowledge\\Vault" }));
  expect(mocks.auditVault).toHaveBeenCalledWith("project-1");
  await waitFor(() => expect(props.onArtifactsChanged).toHaveBeenCalled());
  expect(props.onSuccess).toHaveBeenCalledWith(expect.stringContaining("已导入 2 篇 Markdown"));
  expect(screen.getAllByText("断链").length).toBeGreaterThan(0);
});

test("starts a scoped Master Agent maintenance run from selected backlog tasks", async () => {
  const props = renderPanel();
  const taskCheckbox = await screen.findByRole("checkbox", { name: /修复 index.md 中的断链/ });
  fireEvent.click(taskCheckbox);
  fireEvent.change(screen.getByLabelText("维护目标"), { target: { value: "只修复可验证的链接" } });
  fireEvent.change(screen.getByLabelText("维护执行模式"), { target: { value: "require_review" } });
  fireEvent.click(screen.getByRole("button", { name: "交给 Master Agent" }));

  await waitFor(() => expect(mocks.startMaintenanceRun).toHaveBeenCalledWith("project-1", {
    task_ids: ["MT-1"],
    objective: "只修复可验证的链接",
    execution_mode: "require_review",
    autonomy_policy: {},
  }));
  expect(props.onMaintenanceStarted).toHaveBeenCalledWith("run-maintenance-1");
});

test("shows unified diff and exposes approve, apply, and rollback as separate actions", async () => {
  renderPanel();
  fireEvent.click(await screen.findByRole("button", { name: /proposed RAG 页面/ }));
  fireEvent.click(screen.getByRole("button", { name: /approved RAG 页面/ }));
  fireEvent.click(screen.getByRole("button", { name: /applied RAG 页面/ }));

  expect(screen.getAllByLabelText("cards/RAG.md Diff")[0]).toHaveTextContent("+新内容");
  fireEvent.click(screen.getByRole("button", { name: "批准" }));
  await waitFor(() => expect(mocks.approveChangeSet).toHaveBeenCalledWith("project-1", "CS-proposed"));

  fireEvent.click(screen.getByRole("button", { name: "应用新修订" }));
  await waitFor(() => expect(mocks.applyChangeSet).toHaveBeenCalledWith("project-1", "CS-approved"));

  fireEvent.click(screen.getByRole("button", { name: "回滚" }));
  await waitFor(() => expect(mocks.rollbackChangeSet).toHaveBeenCalledWith("project-1", "CS-applied"));
});

test("creates a manual ChangeSet proposal without bypassing approval", async () => {
  renderPanel();
  await screen.findByText("修复 index.md 中的断链");
  fireEvent.click(screen.getByRole("button", { name: "手动提案" }));
  fireEvent.change(screen.getByLabelText("ChangeSet 摘要"), { target: { value: "补充 RAG 定义" } });
  fireEvent.change(screen.getByLabelText("ChangeSet 路径"), { target: { value: "cards/RAG.md" } });
  fireEvent.change(screen.getByLabelText("ChangeSet 完整内容"), { target: { value: "# RAG\n\n新定义" } });
  fireEvent.change(screen.getByLabelText("ChangeSet 证据 ID"), { target: { value: "EV-1, EV-2" } });
  fireEvent.click(screen.getByRole("checkbox", { name: "包含事实性修改（必须提供证据）" }));
  fireEvent.click(screen.getByRole("button", { name: "创建待审批 ChangeSet" }));

  await waitFor(() => expect(mocks.proposeChangeSet).toHaveBeenCalledWith("project-1", expect.objectContaining({
    summary: "补充 RAG 定义",
    path: "cards/RAG.md",
    after_content: "# RAG\n\n新定义",
    evidence_ids: ["EV-1", "EV-2"],
    factual_change: true,
  })));
});

test("shows the honest Hybrid RAG mode, model, and vector index count", async () => {
  renderPanel();

  expect(await screen.findByText("混合语义检索")).toBeInTheDocument();
  expect(screen.getByText("BAAI/bge-small-zh-v1.5")).toBeInTheDocument();
  expect(screen.getByText("18")).toBeInTheDocument();
  expect(mocks.getRetrievalStatus).toHaveBeenCalledWith("project-1");
});

test("rebuilds the local semantic index and refreshes retrieval status", async () => {
  const props = renderPanel();
  fireEvent.click(await screen.findByRole("button", { name: "重建语义索引" }));

  await waitFor(() => expect(mocks.reindexProject).toHaveBeenCalledWith("project-1"));
  expect(mocks.getRetrievalStatus).toHaveBeenCalledTimes(2);
  expect(props.onSuccess).toHaveBeenCalledWith(expect.stringContaining("18 个分块完成向量化"));
});

test("makes semantic degradation visible instead of presenting keyword search as hybrid", async () => {
  mocks.getRetrievalStatus.mockResolvedValueOnce({
    ...retrievalStatus,
    effective_mode: "lexical_degraded",
    index_count: 0,
    last_error: "local embedding model unavailable",
  });
  renderPanel();

  expect(await screen.findByText("关键词降级")).toBeInTheDocument();
  expect(screen.getByText(/local embedding model unavailable/)).toBeInTheDocument();
});

test("retrieval status failure does not hide the rest of the knowledge control plane", async () => {
  mocks.getRetrievalStatus.mockRejectedValueOnce(new Error("retrieval endpoint unavailable"));
  const props = renderPanel();

  expect(await screen.findByText("修复 index.md 中的断链")).toBeInTheDocument();
  expect(screen.getAllByText(/retrieval endpoint unavailable/).length).toBeGreaterThan(0);
  expect(props.onError).not.toHaveBeenCalled();
});
