import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import {
  ArrowRight,
  SkipForward,
  FileText,
  Database,
  Loader2,
  UserCheck,
  MessageSquare,
  Package,
} from "lucide-react";
import { GraphFlow, GATES } from "./GraphFlow";
import { api } from "../api/client";
import type { Project, Artifact, Evidence, RunEvent } from "../api/client";

interface ReviewViewProps {
  project: Project;
  runId: string;
  completedGate: string;
  events: RunEvent[];
  artifacts: Artifact[];
  evidence: Evidence[];
  onContinue: (guidance?: string, evidenceData?: string) => void;
  onSkip: () => void;
}

/**
 * ReviewView — shown after a gate completes.
 * Lets the user review AI output and optionally inject supplementary information.
 */
export function ReviewView({
  project,
  runId,
  completedGate,
  events,
  artifacts,
  evidence,
  onContinue,
  onSkip,
}: ReviewViewProps) {
  const [guidance, setGuidance] = useState("");
  const [evidenceData, setEvidenceData] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  // Entrance animation
  useEffect(() => {
    if (!contentRef.current) return;
    const ctx = gsap.context(() => {
      gsap.from(".review-header", { y: -20, opacity: 0, duration: 0.4, ease: "power2.out" });
      gsap.from(".review-gate-info", { y: 20, opacity: 0, duration: 0.5, delay: 0.1, ease: "power2.out" });
      gsap.from(".review-output", { y: 20, opacity: 0, duration: 0.5, delay: 0.2, ease: "power2.out" });
      gsap.from(".review-input", { y: 20, opacity: 0, duration: 0.5, delay: 0.3, ease: "power2.out" });
      gsap.from(".review-actions", { y: 20, opacity: 0, duration: 0.5, delay: 0.4, ease: "power2.out" });
    }, contentRef);
    return () => ctx.revert();
  }, []);

  const gate = GATES.find((g) => g.key === completedGate);
  const gateIdx = GATES.findIndex((g) => g.key === completedGate);
  const nextGate = gateIdx < GATES.length - 1 ? GATES[gateIdx + 1] : null;

  // Filter artifacts and evidence for this gate
  const gateArtifacts = artifacts; // In the future, filter by gate

  // Get gate-specific events (for final review show all events)
  const isFinalReview = completedGate === "export";
  const gateEvents = isFinalReview ? events : events.filter((e) => e.gate === completedGate);

  // Gate-specific guidance hints
  const guidanceHints: Record<string, string> = {
    scope: "你对这个领域有什么已有认知？有什么特别想了解的方向？",
    evidence: "你有自己搜集到的数据或信息吗？可以粘贴在这里。",
    research_frame: "研究框架是否覆盖了你关心的重点？有什么需要调整的？",
    knowledge_map: "行业地图是否准确？你有补充的玩家或渠道信息吗？",
    opportunity: "你看到的机会假设是否靠谱？有补充的验证思路吗？",
    export: "导出前有什么需要修改的吗？",
  };

  // Gate-specific evidence injection hints
  const evidenceHints: Record<string, string> = {
    scope: "你已有的行业资料、报告摘要、笔记等",
    evidence: "你搜集到的市场数据、行业报告、新闻链接等",
    research_frame: "你认为重要的研究问题或学习路径",
    knowledge_map: "你知道的玩家信息、渠道数据、价格区间等",
    opportunity: "你发现的机会线索、用户反馈、竞品动态等",
    export: "",
  };

  async function handleContinue() {
    setIsSubmitting(true);
    try {
      // Submit user inputs if any
      if (guidance.trim() || evidenceData.trim()) {
        if (guidance.trim()) {
          await api.addUserInput(runId, {
            gate: completedGate,
            input_type: "guidance",
            content: guidance.trim(),
          });
        }
        if (evidenceData.trim()) {
          await api.addUserInput(runId, {
            gate: completedGate,
            input_type: "evidence_data",
            content: evidenceData.trim(),
          });
        }
      }
      onContinue(guidance.trim() || undefined, evidenceData.trim() || undefined);
    } catch {
      // Continue anyway
      onContinue();
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div ref={contentRef} className="review">
      <header className="review-header">
        <div className="review-header-left">
          <h1>SectorBreaker</h1>
        </div>
      </header>

      {/* Gate info banner */}
      <div className="review-gate-info">
        <div className="review-gate-badge">
          <UserCheck size={18} />
          <span>{gate?.name ?? completedGate} 完成</span>
        </div>
        {nextGate && (
          <span className="review-next-hint">
            下一步：{nextGate.name}
          </span>
        )}
      </div>

      {/* Flow graph (compact, showing progress) */}
      <GraphFlow currentGate={completedGate} compact />

      {/* Agent output summary */}
      <div className="review-content">
        <section className="review-output">
          <div className="review-section-title">
            <Package size={18} />
            <h3>AI 产出摘要</h3>
          </div>

          {/* Gate events as timeline */}
          {gateEvents.length > 0 ? (
            <div className="review-timeline">
              {gateEvents.map((event, idx) => (
                <div key={idx} className="review-timeline-item">
                  <span className="review-timeline-dot" />
                  <div className="review-timeline-content">
                    <span className="review-timeline-msg">{event.message}</span>
                    {event.agent && <span className="review-timeline-agent">{event.agent}</span>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="review-empty">暂无详细事件记录</p>
          )}

          {/* Artifacts produced */}
          {gateArtifacts.length > 0 && (
            <div className="review-artifacts">
              <h4>生成的产物</h4>
              <ul>
                {gateArtifacts.map((a) => (
                  <li key={a.id}>
                    <FileText size={14} />
                    <span>{a.title || a.id}</span>
                    <span className="review-artifact-path">{a.content_path}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Evidence collected */}
          {evidence.length > 0 && (
            <div className="review-evidence-summary">
              <h4>
                <Database size={14} />
                收集到 {evidence.length} 条证据
              </h4>
            </div>
          )}
        </section>

        {/* User input area */}
        {evidenceHints[completedGate] && (
          <section className="review-input">
            <div className="review-section-title">
              <MessageSquare size={18} />
              <h3>补充信息（可选）</h3>
            </div>

            <div className="review-input-group">
              <label htmlFor="guidance">
                <MessageSquare size={14} />
                研究方向备注
              </label>
              <textarea
                id="guidance"
                value={guidance}
                onChange={(e) => setGuidance(e.target.value)}
                placeholder={guidanceHints[completedGate] ?? "告诉 AI 下一步研究应该偏向什么方向…"}
                rows={3}
              />
              <span className="review-input-hint">
                AI 会在下一步参考你的备注
              </span>
            </div>

            <div className="review-input-group">
              <label htmlFor="evidence-data">
                <Database size={14} />
                已有数据/信息
              </label>
              <textarea
                id="evidence-data"
                value={evidenceData}
                onChange={(e) => setEvidenceData(e.target.value)}
                placeholder={evidenceHints[completedGate]}
                rows={5}
              />
              <span className="review-input-hint">
                粘贴你的数据、表格、报告摘要等，会作为证据注入到 AI 的研究流程中
              </span>
            </div>
          </section>
        )}

        {/* Actions */}
        <div className="review-actions">
          <button className="secondary" onClick={onSkip} type="button">
            <SkipForward size={16} />
            跳过，直接继续
          </button>
          <button
            className="primary"
            onClick={handleContinue}
            disabled={isSubmitting}
            type="button"
          >
            {isSubmitting ? (
              <>
                <Loader2 size={16} className="spinner" />
                提交中…
              </>
            ) : (
              <>
                <ArrowRight size={16} />
                {guidance.trim() || evidenceData.trim() ? "确认并继续" : "继续研究"}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
