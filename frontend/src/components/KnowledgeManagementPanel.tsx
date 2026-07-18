import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArchiveRestore,
  Bot,
  Check,
  ChevronDown,
  ChevronUp,
  ClipboardCheck,
  FileDiff,
  FolderInput,
  GitPullRequest,
  Loader2,
  Play,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

import { api } from "../api/client";
import type {
  ChangeSet,
  ChangeSetProposalPayload,
  KnowledgeHealthReport,
  MaintenanceRunPayload,
  MaintenanceTask,
  VaultStatus,
} from "../api/client";

interface KnowledgeManagementPanelProps {
  projectId: string;
  onMaintenanceStarted: (runId: string) => void;
  onArtifactsChanged: () => Promise<void> | void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
}

const findingLabels: Record<string, string> = {
  broken_link: "断链",
  orphan_note: "孤立笔记",
  duplicate_title: "重复标题",
  missing_frontmatter: "缺少 Front Matter",
  missing_evidence_metadata: "缺少证据元数据",
  unresolved_marker: "未解决标记",
};

const taskStatusLabels: Record<string, string> = {
  open: "待处理",
  planned: "已规划",
  running: "处理中",
  blocked: "受阻",
  done: "已完成",
  dismissed: "已忽略",
};

const changeStatusLabels: Record<string, string> = {
  proposed: "待审批",
  approved: "已批准",
  applied: "已应用",
  conflicted: "有冲突",
  rolled_back: "已回滚",
  denied: "已拒绝",
};

const metricDefinitions = [
  ["active_notes", "活跃笔记"],
  ["findings", "健康问题"],
  ["broken_links", "断链"],
  ["orphan_notes", "孤立笔记"],
  ["missing_evidence_metadata", "待补证"],
] as const;

function dateLabel(value?: string | null) {
  if (!value) return "尚未生成";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function compactHash(value?: string | null) {
  return value ? value.slice(0, 10) : "—";
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export function KnowledgeManagementPanel({
  projectId,
  onMaintenanceStarted,
  onArtifactsChanged,
  onError,
  onSuccess,
}: KnowledgeManagementPanelProps) {
  const [vaultPath, setVaultPath] = useState("");
  const [vault, setVault] = useState<VaultStatus | null>(null);
  const [health, setHealth] = useState<KnowledgeHealthReport | null>(null);
  const [tasks, setTasks] = useState<MaintenanceTask[]>([]);
  const [changeSets, setChangeSets] = useState<ChangeSet[]>([]);
  const [selectedTaskIds, setSelectedTaskIds] = useState<string[]>([]);
  const [maintenanceObjective, setMaintenanceObjective] = useState("");
  const [executionMode, setExecutionMode] = useState<MaintenanceRunPayload["execution_mode"]>("plan_only");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [expandedChangeSetIds, setExpandedChangeSetIds] = useState<string[]>([]);
  const [showProposal, setShowProposal] = useState(false);
  const [proposal, setProposal] = useState<ChangeSetProposalPayload>({
    summary: "",
    path: "",
    after_content: "",
    evidence_ids: [],
    factual_change: false,
  });
  const [proposalEvidence, setProposalEvidence] = useState("");

  const refreshControlPlane = useCallback(async () => {
    setBusyAction((current) => current ?? "refresh");
    try {
      const [vaultResult, backlogResult, changeSetResult, healthResult] = await Promise.all([
        api.getVaultStatus(projectId),
        api.listMaintenanceBacklog(projectId),
        api.listChangeSets(projectId),
        api.getKnowledgeHealth(projectId).catch(() => null),
      ]);
      setVault(vaultResult);
      setTasks(backlogResult);
      setChangeSets(changeSetResult);
      setHealth(healthResult);
      setSelectedTaskIds((current) => current.filter((id) => backlogResult.some((task) => task.id === id)));
    } catch (error) {
      onError(errorMessage(error, "知识库状态加载失败"));
    } finally {
      setBusyAction((current) => current === "refresh" ? null : current);
    }
  }, [onError, projectId]);

  useEffect(() => {
    void refreshControlPlane();
  }, [refreshControlPlane]);

  const actionableTasks = useMemo(
    () => tasks.filter((task) => ["open", "planned", "blocked"].includes(task.status)),
    [tasks],
  );

  async function importAndAudit() {
    if (!vaultPath.trim()) return;
    setBusyAction("import");
    try {
      const imported = await api.importVault(projectId, { source_path: vaultPath.trim() });
      const report = await api.auditVault(projectId);
      await Promise.all([refreshControlPlane(), onArtifactsChanged()]);
      setHealth(report);
      onSuccess(`已导入 ${imported.note_count} 篇 Markdown，并生成 ${report.findings.length} 项健康发现`);
    } catch (error) {
      onError(errorMessage(error, "Vault 导入失败"));
    } finally {
      setBusyAction(null);
    }
  }

  async function runAudit() {
    setBusyAction("audit");
    try {
      const report = await api.auditVault(projectId);
      setHealth(report);
      await refreshControlPlane();
      onSuccess(`审计完成：发现 ${report.findings.length} 个维护项`);
    } catch (error) {
      onError(errorMessage(error, "知识健康审计失败"));
    } finally {
      setBusyAction(null);
    }
  }

  function toggleTask(taskId: string) {
    setSelectedTaskIds((current) => current.includes(taskId)
      ? current.filter((id) => id !== taskId)
      : [...current, taskId]);
  }

  async function startMaintenance() {
    if (selectedTaskIds.length === 0 && !maintenanceObjective.trim()) return;
    setBusyAction("maintenance");
    try {
      const result = await api.startMaintenanceRun(projectId, {
        task_ids: selectedTaskIds,
        objective: maintenanceObjective.trim(),
        execution_mode: executionMode,
        autonomy_policy: {},
      });
      onSuccess("维护运行已交给 Master Agent");
      onMaintenanceStarted(result.run_id);
    } catch (error) {
      onError(errorMessage(error, "维护运行启动失败"));
      setBusyAction(null);
    }
  }

  async function mutateChangeSet(changeSetId: string, action: "approve" | "apply" | "rollback") {
    setBusyAction(`${action}:${changeSetId}`);
    try {
      const changed = action === "approve"
        ? await api.approveChangeSet(projectId, changeSetId)
        : action === "apply"
          ? await api.applyChangeSet(projectId, changeSetId)
          : await api.rollbackChangeSet(projectId, changeSetId);
      const expectedStatus = action === "approve" ? "approved" : action === "apply" ? "applied" : "rolled_back";
      if (changed.status !== expectedStatus) {
        throw new Error(changed.error || `ChangeSet 状态为 ${changeStatusLabels[changed.status] ?? changed.status}`);
      }
      await Promise.all([refreshControlPlane(), onArtifactsChanged()]);
      onSuccess(action === "approve" ? "ChangeSet 已批准" : action === "apply" ? "ChangeSet 已应用为新修订" : "已创建回滚修订");
    } catch (error) {
      onError(errorMessage(error, action === "approve" ? "审批失败" : action === "apply" ? "应用失败" : "回滚失败"));
    } finally {
      setBusyAction(null);
    }
  }

  async function proposeChange() {
    if (!proposal.summary.trim() || !proposal.path.trim() || !proposal.after_content.trim()) return;
    setBusyAction("propose");
    try {
      const evidenceIds = proposalEvidence.split(/[,\s]+/).map((item) => item.trim()).filter(Boolean);
      await api.proposeChangeSet(projectId, {
        ...proposal,
        task_id: proposal.task_id || undefined,
        summary: proposal.summary.trim(),
        path: proposal.path.trim(),
        after_content: proposal.after_content,
        evidence_ids: evidenceIds,
      });
      setProposal({ summary: "", path: "", after_content: "", evidence_ids: [], factual_change: false });
      setProposalEvidence("");
      setShowProposal(false);
      await refreshControlPlane();
      onSuccess("ChangeSet 草案已创建，应用前仍需审批");
    } catch (error) {
      onError(errorMessage(error, "ChangeSet 创建失败"));
    } finally {
      setBusyAction(null);
    }
  }

  function toggleChangeSet(changeSetId: string) {
    setExpandedChangeSetIds((current) => current.includes(changeSetId)
      ? current.filter((id) => id !== changeSetId)
      : [...current, changeSetId]);
  }

  const isBusy = busyAction !== null;

  return (
    <section className="result-card result-card--wide knowledge-control-plane" aria-labelledby="knowledge-control-title">
      <div className="knowledge-control-heading">
        <div>
          <span className="knowledge-control-eyebrow"><ShieldCheck size={14} />V3 CONTROL PLANE</span>
          <h3 id="knowledge-control-title"><Activity size={17} />知识库自治管理</h3>
          <p>导入、审计、维护、审批和回滚都保留版本与证据链；源 Vault 不会被直接修改。</p>
        </div>
        <button className="secondary btn-sm" onClick={() => void refreshControlPlane()} disabled={isBusy} type="button">
          <RefreshCw size={14} className={busyAction === "refresh" ? "spinner" : ""} />刷新状态
        </button>
      </div>

      <div className="knowledge-control-section vault-import-section">
        <div className="knowledge-section-title">
          <FolderInput size={16} />
          <div><strong>接管本地 Markdown Vault</strong><span>后端读取绝对路径，并建立安全的受管镜像。</span></div>
        </div>
        <div className="vault-import-row">
          <input
            aria-label="本地 Vault 路径"
            value={vaultPath}
            onChange={(event) => setVaultPath(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && void importAndAudit()}
            placeholder="例如 D:\\Knowledge\\MyVault"
          />
          <button className="primary btn-sm" onClick={() => void importAndAudit()} disabled={!vaultPath.trim() || isBusy} type="button">
            {busyAction === "import" ? <Loader2 size={14} className="spinner" /> : <FolderInput size={14} />}
            导入并审计
          </button>
        </div>
        <div className="vault-status-strip">
          <span><b>{vault?.active_note_count ?? 0}</b> 篇活跃笔记</span>
          <span>快照 <code>{compactHash(vault?.latest_import?.snapshot_hash)}</code></span>
          <span>{vault?.latest_import ? `最近导入 ${dateLabel(vault.latest_import.created_at)}` : "当前项目尚未导入外部 Vault"}</span>
        </div>
      </div>

      <div className="knowledge-control-columns">
        <div className="knowledge-control-section health-panel">
          <div className="knowledge-section-title knowledge-section-title--actions">
            <div><ClipboardCheck size={16} /><div><strong>知识健康</strong><span>{dateLabel(health?.generated_at)}</span></div></div>
            <button className="secondary btn-sm" onClick={() => void runAudit()} disabled={isBusy || (vault?.active_note_count ?? 0) === 0} type="button">
              {busyAction === "audit" ? <Loader2 size={13} className="spinner" /> : <ClipboardCheck size={13} />}重新审计
            </button>
          </div>
          <div className="health-metric-grid">
            {metricDefinitions.map(([key, label]) => (
              <div key={key}><strong>{health?.metrics[key] ?? (key === "active_notes" ? vault?.active_note_count ?? 0 : "—")}</strong><span>{label}</span></div>
            ))}
          </div>
          {health?.findings.length ? (
            <ul className="health-finding-list">
              {health.findings.slice(0, 6).map((finding) => (
                <li key={finding.id}>
                  <span className={`status-pill status-pill--${finding.severity}`}>{findingLabels[finding.finding_type] ?? finding.finding_type}</span>
                  <div><strong>{finding.target_paths.join("、") || "Vault"}</strong><p>{finding.explanation}</p></div>
                </li>
              ))}
            </ul>
          ) : <p className="result-empty">导入 Vault 后运行审计，系统会确定性识别断链、孤岛和元数据缺口。</p>}
        </div>

        <div className="knowledge-control-section backlog-panel">
          <div className="knowledge-section-title knowledge-section-title--actions">
            <div><Bot size={16} /><div><strong>维护 Backlog</strong><span>{actionableTasks.length} 项可执行</span></div></div>
            {actionableTasks.length > 0 && (
              <button className="text-button" onClick={() => setSelectedTaskIds(
                selectedTaskIds.length === actionableTasks.length ? [] : actionableTasks.map((task) => task.id),
              )} type="button">
                {selectedTaskIds.length === actionableTasks.length ? "取消全选" : "全选可执行项"}
              </button>
            )}
          </div>
          <div className="maintenance-task-list">
            {tasks.slice(0, 8).map((task) => {
              const selectable = ["open", "planned", "blocked"].includes(task.status);
              return (
                <label key={task.id} className={`maintenance-task ${selectedTaskIds.includes(task.id) ? "is-selected" : ""}`}>
                  <input type="checkbox" checked={selectedTaskIds.includes(task.id)} disabled={!selectable} onChange={() => toggleTask(task.id)} />
                  <span className="maintenance-priority">P{task.priority}</span>
                  <div><strong>{task.objective}</strong><span>{task.target_paths.join("、") || "全局"} · {taskStatusLabels[task.status]}</span></div>
                </label>
              );
            })}
            {tasks.length === 0 && <p className="result-empty">审计后会自动生成去重的维护任务。</p>}
          </div>
          <div className="maintenance-run-form">
            <input aria-label="维护目标" value={maintenanceObjective} onChange={(event) => setMaintenanceObjective(event.target.value)} placeholder="可选：补充本轮维护目标" />
            <select aria-label="维护执行模式" value={executionMode} onChange={(event) => setExecutionMode(event.target.value as MaintenanceRunPayload["execution_mode"])}>
              <option value="plan_only">只规划并生成 ChangeSet</option>
              <option value="require_review">所有修改都需审核</option>
              <option value="apply_safe">仅自动应用安全修改</option>
            </select>
            <button className="primary btn-sm" onClick={() => void startMaintenance()} disabled={isBusy || (selectedTaskIds.length === 0 && !maintenanceObjective.trim())} type="button">
              {busyAction === "maintenance" ? <Loader2 size={14} className="spinner" /> : <Play size={14} />}
              交给 Master Agent
            </button>
          </div>
        </div>
      </div>

      <div className="knowledge-control-section changeset-panel">
        <div className="knowledge-section-title knowledge-section-title--actions">
          <div><FileDiff size={16} /><div><strong>ChangeSet 审批台</strong><span>查看完整 Diff，再批准、应用或回滚修订。</span></div></div>
          <button className="secondary btn-sm" onClick={() => setShowProposal((current) => !current)} type="button">
            <GitPullRequest size={14} />{showProposal ? "收起草案" : "手动提案"}
          </button>
        </div>

        {showProposal && (
          <div className="changeset-proposal-form">
            <input aria-label="ChangeSet 摘要" value={proposal.summary} onChange={(event) => setProposal((current) => ({ ...current, summary: event.target.value }))} placeholder="修改摘要" />
            <input aria-label="ChangeSet 路径" value={proposal.path} onChange={(event) => setProposal((current) => ({ ...current, path: event.target.value }))} placeholder="例如 cards/RAG.md" />
            <select aria-label="关联维护任务" value={proposal.task_id ?? ""} onChange={(event) => setProposal((current) => ({ ...current, task_id: event.target.value || null }))}>
              <option value="">不关联维护任务</option>
              {tasks.map((task) => <option key={task.id} value={task.id}>{task.objective}</option>)}
            </select>
            <textarea aria-label="ChangeSet 完整内容" value={proposal.after_content} onChange={(event) => setProposal((current) => ({ ...current, after_content: event.target.value }))} placeholder="修改后的完整 Markdown 内容" rows={7} />
            <input aria-label="ChangeSet 证据 ID" value={proposalEvidence} onChange={(event) => setProposalEvidence(event.target.value)} placeholder="证据 ID，多个用逗号或空格分隔" />
            <label className="toggle-chip"><input type="checkbox" checked={proposal.factual_change ?? false} onChange={(event) => setProposal((current) => ({ ...current, factual_change: event.target.checked }))} /><span>包含事实性修改（必须提供证据）</span></label>
            <button className="primary btn-sm" onClick={() => void proposeChange()} disabled={isBusy || !proposal.summary.trim() || !proposal.path.trim() || !proposal.after_content.trim()} type="button">
              {busyAction === "propose" ? <Loader2 size={14} className="spinner" /> : <GitPullRequest size={14} />}创建待审批 ChangeSet
            </button>
          </div>
        )}

        <div className="changeset-list">
          {changeSets.map((changeSet) => {
            const expanded = expandedChangeSetIds.includes(changeSet.id);
            return (
              <article className={`changeset-card changeset-card--${changeSet.status}`} key={changeSet.id}>
                <button className="changeset-summary" onClick={() => toggleChangeSet(changeSet.id)} type="button" aria-expanded={expanded}>
                  <span className={`status-pill status-pill--${changeSet.status}`}>{changeStatusLabels[changeSet.status]}</span>
                  <div><strong>{changeSet.summary}</strong><span>{changeSet.operations.length} 项操作 · {changeSet.created_by_agent} · {dateLabel(changeSet.created_at)}</span></div>
                  {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
                {expanded && (
                  <div className="changeset-detail">
                    {changeSet.operations.map((operation, index) => (
                      <div className="changeset-operation" key={`${operation.path}-${index}`}>
                        <div><strong>{operation.operation === "create" ? "新建" : "更新"} · {operation.path}</strong><span>基线 {compactHash(operation.base_hash)}{operation.factual_change ? " · 事实性修改" : ""}</span></div>
                        <pre aria-label={`${operation.path} Diff`}>{operation.unified_diff || "当前记录没有可显示的 unified diff。"}</pre>
                      </div>
                    ))}
                    {changeSet.evidence_ids.length > 0 && <p className="changeset-evidence">证据：{changeSet.evidence_ids.join("、")}</p>}
                    {changeSet.error && <p className="changeset-error">{changeSet.error}</p>}
                    <div className="changeset-actions">
                      {changeSet.status === "proposed" && <button className="secondary btn-sm" onClick={() => void mutateChangeSet(changeSet.id, "approve")} disabled={isBusy} type="button"><Check size={14} />批准</button>}
                      {changeSet.status === "approved" && <button className="primary btn-sm" onClick={() => void mutateChangeSet(changeSet.id, "apply")} disabled={isBusy} type="button"><Check size={14} />应用新修订</button>}
                      {changeSet.status === "applied" && <button className="secondary btn-sm" onClick={() => void mutateChangeSet(changeSet.id, "rollback")} disabled={isBusy} type="button"><ArchiveRestore size={14} />回滚</button>}
                    </div>
                  </div>
                )}
              </article>
            );
          })}
          {changeSets.length === 0 && <p className="result-empty">Master Agent 或手动提案创建的 ChangeSet 会出现在这里；没有审批就不会覆盖现有笔记。</p>}
        </div>
      </div>
    </section>
  );
}
