import { useEffect, useRef } from "react";
import gsap from "gsap";
import {
  Target,
  Database,
  FileText,
  Map,
  Search,
  Download,
  CheckCircle2,
  Loader2,
  Circle,
  AlertCircle,
  UserCheck,
} from "lucide-react";

export interface GateInfo {
  key: string;
  name: string;
  icon: typeof Target;
  humanReview: boolean;
}

export const GATES: GateInfo[] = [
  { key: "scope", name: "范围确认", icon: Target, humanReview: true },
  { key: "evidence", name: "证据收集", icon: Database, humanReview: false },
  { key: "research_frame", name: "研究框架", icon: FileText, humanReview: true },
  { key: "knowledge_map", name: "知识地图", icon: Map, humanReview: false },
  { key: "opportunity", name: "机会地图", icon: Search, humanReview: true },
  { key: "export", name: "导出", icon: Download, humanReview: false },
];

export type GateStatus = "done" | "current" | "next" | "error";

interface GraphFlowProps {
  currentGate: string;
  gateStatuses?: Record<string, GateStatus>;
  activeAgent?: string | null;
  activeMessage?: string | null;
  onGateClick?: (gateKey: string) => void;
  compact?: boolean;
}

function getGateStatus(gateKey: string, currentGate: string): GateStatus {
  const currentIdx = GATES.findIndex((g) => g.key === currentGate);
  const gateIdx = GATES.findIndex((g) => g.key === gateKey);
  if (currentIdx === -1) return "next";
  if (gateIdx < currentIdx) return "done";
  if (gateIdx === currentIdx) return "current";
  return "next";
}

export function GraphFlow({
  currentGate,
  gateStatuses,
  activeAgent,
  activeMessage,
  onGateClick,
  compact = false,
}: GraphFlowProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Animate gate status changes
  useEffect(() => {
    if (!containerRef.current) return;

    const ctx = gsap.context(() => {
      const currentEl = containerRef.current!.querySelector(".gate--current .gate-indicator");
      if (currentEl) {
        gsap.fromTo(
          currentEl,
          { scale: 0.8 },
          { scale: 1, duration: 0.4, ease: "back.out(1.7)" }
        );
      }
    }, containerRef);

    return () => ctx.revert();
  }, [currentGate]);

  return (
    <div ref={containerRef} className={`graph-flow ${compact ? "graph-flow--compact" : ""}`}>
      {GATES.map((gate, idx) => {
        const status = gateStatuses?.[gate.key] ?? getGateStatus(gate.key, currentGate);
        const Icon = gate.icon;
        const isClickable = status === "done" && onGateClick;

        return (
          <div key={gate.key} className="graph-flow-item">
            {/* Connector line */}
            {idx > 0 && (
              <div className={`graph-flow-connector ${status === "done" || status === "current" ? "graph-flow-connector--active" : ""}`} />
            )}

            {/* Gate node */}
            <button
              className={`gate gate--${status} ${isClickable ? "gate--clickable" : ""}`}
              onClick={isClickable ? () => onGateClick(gate.key) : undefined}
              type="button"
              title={gate.name}
            >
              <div className="gate-indicator">
                {status === "done" ? (
                  <CheckCircle2 size={compact ? 16 : 20} />
                ) : status === "current" ? (
                  <Loader2 size={compact ? 16 : 20} className="spinner" />
                ) : status === "error" ? (
                  <AlertCircle size={compact ? 16 : 20} />
                ) : (
                  <Circle size={compact ? 16 : 20} />
                )}
              </div>

              {!compact && (
                <div className="gate-body">
                  <span className="gate-label">{gate.name}</span>
                  {gate.humanReview && (
                    <span className="gate-badge">
                      <UserCheck size={10} />
                      人工
                    </span>
                  )}
                </div>
              )}
            </button>

            {/* Active agent indicator */}
            {status === "current" && !compact && activeAgent && (
              <div className="gate-agent">
                <span className="gate-agent-name">{activeAgent}</span>
                {activeMessage && <span className="gate-agent-msg">{activeMessage}</span>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
