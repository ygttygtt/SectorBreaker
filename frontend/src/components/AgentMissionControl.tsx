import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Clock3, ExternalLink, Network, Radio, ShieldCheck } from "lucide-react";

import { api } from "../api/client";
import type { AgentManifest, AgentMission, AgentWorkOrder, Evidence } from "../api/client";

export function AgentMissionControl({
  runId,
  projectId,
  eventCount,
}: {
  runId: string;
  projectId: string;
  eventCount: number;
}) {
  const [mission, setMission] = useState<AgentMission | null>(null);
  const [registry, setRegistry] = useState<AgentManifest[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [changeStatus, setChangeStatus] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);

  useEffect(() => {
    if (!runId || !projectId) return;
    let disposed = false;
    async function refresh() {
      try {
        const [nextMission, nextRegistry, nextEvidence] = await Promise.all([
          api.getAgentMission(runId),
          api.getAgentRegistry(projectId),
          api.listEvidence(projectId),
        ]);
        if (disposed) return;
        setMission(nextMission);
        setRegistry(nextRegistry);
        setEvidence(nextEvidence);
        setSelectedTaskId((current) => current ?? nextMission.work_orders[0]?.id ?? null);
        if (nextMission.change_set_id) {
          const changeSets = await api.listChangeSets(projectId);
          if (!disposed) setChangeStatus(changeSets.find((item) => item.id === nextMission.change_set_id)?.status ?? null);
        }
      } catch {
        // A normal Agent Kernel run has no live challenge mission.
      }
    }
    void refresh();
    const timer = window.setInterval(() => {
      if (!mission || ["planned", "running"].includes(mission.status)) void refresh();
    }, 1800);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [eventCount, mission?.status, projectId, refreshNonce, runId]);

  async function approve() {
    if (!mission?.change_set_id) return;
    setPublishing(true);
    try {
      const result = await api.approveChangeSet(projectId, mission.change_set_id);
      setChangeStatus(result.status);
      setRefreshNonce((value) => value + 1);
    } finally {
      setPublishing(false);
    }
  }

  async function apply() {
    if (!mission?.change_set_id) return;
    setPublishing(true);
    try {
      const result = await api.applyChangeSet(projectId, mission.change_set_id);
      setChangeStatus(result.status);
      setRefreshNonce((value) => value + 1);
    } finally {
      setPublishing(false);
    }
  }

  const selectedTask = mission?.work_orders.find((item) => item.id === selectedTaskId) ?? null;
  const manifest = registry.find((item) => item.agent_id === selectedTask?.assigned_agent_id) ?? null;
  const deliverable = mission?.deliverables.find((item) => item.task_id === selectedTask?.id) ?? null;
  const settlement = mission?.settlements.find((item) => item.task_id === selectedTask?.id) ?? null;
  const referencedEvidence = useMemo(() => {
    const ids = new Set(deliverable?.evidence_ids ?? mission?.deliverables.flatMap((item) => item.evidence_ids) ?? []);
    return evidence.filter((item) => ids.has(item.id));
  }, [deliverable?.evidence_ids, evidence, mission?.deliverables]);

  if (!mission) return null;

  const layers = graphLayers(mission.work_orders);
  const editorDeliverable = mission.deliverables.find((item) => item.draft_markdown);

  return (
    <section className="mission-control" aria-label="Multi-Agent Mission Control">
      <div className="mission-control-head">
        <div>
          <span className="eyebrow">Mission Control · 真实任务合同</span>
          <h2>{mission.domain}</h2>
          <p>{mission.objective}</p>
        </div>
        <span className={`mission-status mission-status--${mission.status}`}><Radio size={13} />{mission.status}</span>
      </div>

      <div className="mission-control-grid">
        <div className="mission-graph-panel">
          <div className="mission-panel-title"><Network size={15} /><strong>Mission Graph</strong><span>{mission.work_orders.length} WorkOrders</span></div>
          <div className="mission-dag">
            {layers.map((layer, layerIndex) => (
              <div className="mission-dag-layer" key={layerIndex}>
                {layer.map((task) => (
                  <button
                    className={`mission-task mission-task--${task.status} ${selectedTaskId === task.id ? "is-selected" : ""}`}
                    key={task.id}
                    onClick={() => setSelectedTaskId(task.id)}
                    type="button"
                  >
                    <span>{task.task_type}</span>
                    <strong>{task.research_angle || task.objective}</strong>
                    <small>{task.assigned_agent_id || "等待派单"}</small>
                    {task.depends_on.length > 0 && <em>依赖 {task.depends_on.join(" · ")}</em>}
                  </button>
                ))}
                {layerIndex < layers.length - 1 && <span className="mission-layer-arrow">→</span>}
              </div>
            ))}
          </div>
        </div>

        <aside className="mission-agent-panel">
          <div className="mission-panel-title"><ShieldCheck size={15} /><strong>Agent Detail</strong></div>
          {selectedTask ? <>
            <h3>{manifest?.display_name ?? selectedTask.assigned_agent_id ?? "尚未派单"}</h3>
            <div className="agent-transport-row">
              <span className={`transport-badge transport-badge--${manifest?.transport ?? "local"}`}>
                {manifest?.transport === "a2a" ? "A2A 1.0" : "LOCAL"}
              </span>
              <span>{selectedTask.status}</span>
              <span><Clock3 size={12} />尝试 {selectedTask.attempts}</span>
            </div>
            <p>{selectedTask.objective}</p>
            <dl className="mission-agent-facts">
              <dt>能力</dt><dd>{manifest?.capabilities.join(" · ") || selectedTask.required_capabilities.join(" · ")}</dd>
              <dt>工具</dt><dd>{manifest?.tool_allowlist.join(" · ") || "—"}</dd>
              <dt>验收</dt><dd>{selectedTask.acceptance_criteria.join("；")}</dd>
            </dl>
            {selectedTask.assignment_trace.length > 0 && <div className="assignment-trace">
              <strong>可解释派单</strong>
              {selectedTask.assignment_trace.map((bid) => <div key={bid.agent_id} className={!bid.eligible ? "is-excluded" : ""}>
                <span>{bid.agent_id}</span><b>{bid.eligible ? bid.score.toFixed(3) : "排除"}</b>
                <small>{bid.exclusion_reasons.join("；") || bid.rationale}</small>
              </div>)}
            </div>}
            {settlement && <div className="settlement-card">
              <CheckCircle2 size={15} />
              <div><strong>任务结算 · {settlement.accepted ? "accepted" : "rejected"}</strong><span>质量 {settlement.quality_score.toFixed(2)} · Evidence +{settlement.evidence_gain} · 返工 {settlement.rework_count}</span></div>
            </div>}
          </> : <p>选择一个 WorkOrder 查看身份、权限、派单评分与结算。</p>}
        </aside>
      </div>

      <div className="mission-deliverable-panel">
        <div className="mission-panel-title"><CheckCircle2 size={15} /><strong>Evidence & Deliverable</strong><span>{referencedEvidence.length} 条真实来源</span></div>
        <div className="mission-evidence-list">
          {referencedEvidence.slice(0, 6).map((item) => <a key={item.id} href={item.source_url} target="_blank" rel="noreferrer">
            <span>{item.id}</span><strong>{item.source_title}</strong><em>{item.verification_status || "unverified"}</em><ExternalLink size={12} />
          </a>)}
        </div>
        {deliverable?.claim_checks.map((check) => <article className={`claim-check claim-check--${check.status}`} key={check.claim}>
          <strong>{check.status}</strong><p>{check.claim}</p><small>{check.reason}</small>
        </article>)}
        {editorDeliverable?.draft_markdown && <details className="starter-note-preview" open={mission.status === "waiting_for_review"}>
          <summary>Starter Note 提案 · {editorDeliverable.proposed_path}</summary>
          <pre>{editorDeliverable.draft_markdown}</pre>
        </details>}
        {mission.change_set_id && <div className="mission-approval-note">
          <p>ChangeSet {mission.change_set_id} · {changeStatus || "proposed"}。Agent 无直接写入权；发布权由规则与人工审批持有。</p>
          <div>
            <button className="secondary btn-sm" disabled={publishing || changeStatus !== "proposed"} onClick={() => void approve()} type="button">Approve</button>
            <button className="primary btn-sm" disabled={publishing || changeStatus !== "approved"} onClick={() => void apply()} type="button">Apply to Vault</button>
          </div>
        </div>}
      </div>
    </section>
  );
}

function graphLayers(tasks: AgentWorkOrder[]) {
  const level = new Map<string, number>();
  const byId = new Map(tasks.map((item) => [item.id, item]));
  function taskLevel(task: AgentWorkOrder): number {
    const cached = level.get(task.id);
    if (cached !== undefined) return cached;
    const value = task.depends_on.length === 0
      ? 0
      : 1 + Math.max(...task.depends_on.map((id) => taskLevel(byId.get(id)!)));
    level.set(task.id, value);
    return value;
  }
  tasks.forEach(taskLevel);
  const max = Math.max(...level.values());
  return Array.from({ length: max + 1 }, (_, index) => tasks.filter((task) => level.get(task.id) === index));
}
