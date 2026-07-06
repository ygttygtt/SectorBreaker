import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import gsap from "gsap";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Database,
  Download,
  ExternalLink,
  FileText,
  Filter,
  Loader2,
  Network,
  Play,
  Search,
  Settings,
  Sparkles,
  X,
} from "lucide-react";

import "./styles.css";
import { ToastContainer, useToast } from "./components/Toast";
import { ConfigPanel } from "./components/ConfigPanel";
import { Logo } from "./components/Logo";
import { LogStream } from "./components/LogStream";
import { WorkflowEditor, type NodeStatus } from "./components/WorkflowEditor";
import { api } from "./api/client";
import { useRunEvents } from "./hooks/useRunEvents";
import type {
  Artifact,
  ChatResponse,
  Evidence,
  ExportManifest,
  Project,
  RunEvent,
  RunSnapshot,
  SupervisorPlan,
  WorkflowDefinition,
  WorkflowNode,
} from "./api/client";

type AppPhase = "landing" | "researching" | "reviewing" | "result";

const sourcePolicies = [
  { value: "reliable_first", label: "可靠优先", desc: "先查公开可靠源，不足再补开放网络。" },
  { value: "open_web", label: "开放网络", desc: "覆盖更广，噪音更高，关键结论会评级。" },
  { value: "reliable_only", label: "严格可靠", desc: "只允许政府、公告、公开数据库等可靠来源。" },
  { value: "user_materials_only", label: "仅用户材料", desc: "只整理你给的资料，不主动开放搜索。" },
];

const eventNodeMap: Record<string, string> = {
  scope: "scope",
  initialize_state: "initialize_state",
  external_materials: "external_materials",
  agent_decide: "agent_decide",
  tool_execution: "tool_execution",
  state_update: "state_update",
  artifact_writing: "artifact_writing",
  human_feedback: "human_feedback",
  supervisor_plan: "supervisor_plan",
  source_strategy: "source_strategy",
  source_collection: "source_collection",
  evidence: "source_collection",
  claim_extractor: "claim_extractor",
  counterevidence: "counterevidence",
  evidence_ledger: "evidence_ledger",
  artifact_review: "artifact_review",
  quality_review: "artifact_review",
  talent_source_intake: "talent_source_intake",
  jd_signal_extraction: "claim_extractor",
  skill_normalization: "skill_normalization",
  source_coverage: "source_coverage",
  talent_synthesis: "talent_synthesis",
  market_agent: "market_agent",
  player_agent: "player_agent",
  transaction_agent: "transaction_agent",
  synthesis: "synthesis",
  knowledge_map: "business_database",
  qa_critic: "qa_critic",
  obsidian_export: "export",
  export: "export",
};

export function nodeIdForEvent(event: Pick<RunEvent, "gate" | "step" | "agent">) {
  return eventNodeMap[event.gate] ?? event.step ?? event.gate ?? event.agent?.toLowerCase().replace(/\s+/g, "_");
}

function nodeIdForDefinition(
  event: Pick<RunEvent, "gate" | "step" | "agent">,
  definition: WorkflowDefinition | null,
) {
  const nodeId = nodeIdForEvent(event);
  if (!definition || definition.nodes.some((node) => node.id === nodeId)) return nodeId;
  const aliases: Record<string, string> = {
    obsidian_export: "export",
  };
  const fallback = aliases[event.gate] ?? aliases[nodeId ?? ""];
  if (fallback && definition.nodes.some((node) => node.id === fallback)) return fallback;
  return nodeId;
}

function extractPlan(events: RunEvent[]): SupervisorPlan | null {
  const event = [...events].reverse().find((item) => item.gate === "supervisor_plan" && item.data);
  return (event?.data as unknown as SupervisorPlan) ?? null;
}

function extractQa(events: RunEvent[]) {
  return [...events].reverse().find((item) => item.gate === "qa_critic" && item.data)?.data ?? null;
}

type QaPayload = {
  passed?: boolean;
  blocking_issues?: string[];
  retry_tasks?: string[];
  user_action_needed?: string[];
  can_continue_with_warning?: boolean;
};

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function asQaPayload(value: unknown): QaPayload | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return {
    passed: typeof record.passed === "boolean" ? record.passed : undefined,
    blocking_issues: asStringList(record.blocking_issues),
    retry_tasks: asStringList(record.retry_tasks),
    user_action_needed: asStringList(record.user_action_needed),
    can_continue_with_warning: typeof record.can_continue_with_warning === "boolean" ? record.can_continue_with_warning : undefined,
  };
}

function labelForQuality(value?: string) {
  if (value === "high") return "高可信";
  if (value === "medium") return "中可信";
  if (value === "low") return "低可信";
  return "未知";
}

function labelForVerification(value?: string) {
  if (value === "verified") return "已验证";
  if (value === "partially_verified") return "部分验证";
  if (value === "conflicting") return "有冲突";
  return "未验证";
}

function cleanDisplaySnippet(value?: string, fallback = "该来源未提供摘要，需打开来源复核。") {
  const raw = (value || "").trim();
  if (!raw) return fallback;
  const cleaned = raw
    .replace(/!\[[^\]]*]\([^)]+\)/g, "")
    .replace(/\[([^\]]+)]\([^)]+\)/g, "$1")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[#*`|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const noisePatterns = [
    /skip to content/i,
    /sign in/i,
    /navigation menu/i,
    /search code, repositories/i,
    /you signed in with another tab/i,
    /reload to refresh your session/i,
    /dismiss alert/i,
  ];
  const sentences = cleaned
    .split(/(?<=[。.!?])\s+|\s{2,}/)
    .map((item) => item.trim())
    .filter((item) => item && !noisePatterns.some((pattern) => pattern.test(item)));
  const readable = sentences.join(" ").trim() || fallback;
  return readable.length > 360 ? `${readable.slice(0, 359).trim()}…` : readable;
}

function formatEventTime(timestamp: number) {
  const millis = timestamp > 1_000_000_000_000 ? timestamp : timestamp * 1000;
  return new Date(millis).toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export type AgentBriefCard = {
  id: string;
  label: string;
  summary: string;
  detail?: string;
  tone: "thinking" | "action" | "result" | "state" | "writing" | "warning";
  timestamp: number;
};

function stripKernelPrefix(message: string, prefix: string) {
  return message.startsWith(prefix) ? message.slice(prefix.length).trim() : message.trim();
}

function compactMessage(message: string, maxLength = 260) {
  const normalized = message.replace(/\s+/g, " ").trim();
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1).trim()}…` : normalized;
}

export function countEvidenceSignals(events: RunEvent[]) {
  const stateUpdateTotal = events.reduce((total, event) => {
    const match = event.message.match(/sources\+(\d+)/i);
    return total + (match ? Number(match[1]) : 0);
  }, 0);
  if (stateUpdateTotal > 0) return stateUpdateTotal;

  const collectedEvents = events.filter((event) => event.event_type === "evidence_collected").length;
  if (collectedEvents > 0) return collectedEvents;

  return events.reduce((total, event) => {
    const match = event.message.match(/采纳\s*(\d+)\s*条/);
    return total + (match ? Number(match[1]) : 0);
  }, 0);
}

export function buildAgentBriefCards(events: RunEvent[], limit = 8): AgentBriefCard[] {
  const cards: AgentBriefCard[] = [];
  let latestWritingIndex = -1;

  events.forEach((event, index) => {
    const raw = event.message || "";
    let card: AgentBriefCard | null = null;

    if (raw.startsWith("Thought Summary:")) {
      card = {
        id: `${event.timestamp}-${index}-thought`,
        label: "Agent 判断",
        summary: compactMessage(stripKernelPrefix(raw, "Thought Summary:")),
        tone: "thinking",
        timestamp: event.timestamp,
      };
    } else if (raw.startsWith("Action:")) {
      const summary = stripKernelPrefix(raw, "Action:");
      const [tool, reason] = summary.split(/\s+-\s+(.+)/);
      card = {
        id: `${event.timestamp}-${index}-action`,
        label: "准备行动",
        summary: compactMessage(tool ? `调用 ${tool.trim()}` : summary),
        detail: reason ? compactMessage(reason, 220) : undefined,
        tone: "action",
        timestamp: event.timestamp,
      };
    } else if (raw.startsWith("Observation:") || raw.startsWith("Action Observation:")) {
      card = {
        id: `${event.timestamp}-${index}-observation`,
        label: "工具结果",
        summary: compactMessage(stripKernelPrefix(stripKernelPrefix(raw, "Observation:"), "Action Observation:")),
        tone: "result",
        timestamp: event.timestamp,
      };
    } else if (raw.startsWith("State Update:")) {
      card = {
        id: `${event.timestamp}-${index}-state`,
        label: "状态更新",
        summary: compactMessage(stripKernelPrefix(raw, "State Update:")),
        tone: "state",
        timestamp: event.timestamp,
      };
    } else if (event.gate === "artifact_writing" || event.agent === "V2 Artifact Writer") {
      card = {
        id: `${event.timestamp}-${index}-writing`,
        label: raw.includes("已写作") ? "写作完成" : "正在写作",
        summary: compactMessage(raw),
        tone: event.severity === "error" ? "warning" : "writing",
        timestamp: event.timestamp,
      };
      if (!raw.includes("已写作") && latestWritingIndex >= 0) {
        cards[latestWritingIndex] = card;
        return;
      }
      if (!raw.includes("已写作")) latestWritingIndex = cards.length;
    } else if (event.severity === "error" || event.event_type === "node_blocked") {
      card = {
        id: `${event.timestamp}-${index}-warning`,
        label: "需要处理",
        summary: compactMessage(raw),
        tone: "warning",
        timestamp: event.timestamp,
      };
    }

    if (card) cards.push(card);
  });

  return cards.slice(-limit);
}

function isKnowledgeCard(artifact: Artifact) {
  return artifact.schema_version === "v1-card"
    || artifact.schema_version === "talent-v1-card"
    || artifact.content_path.startsWith("concepts/")
    || artifact.content_path.startsWith("architectures/")
    || artifact.content_path.startsWith("tools/")
    || artifact.content_path.startsWith("questions/")
    || artifact.content_path.startsWith("skills/")
    || artifact.content_path.startsWith("roles/")
    || artifact.content_path.startsWith("companies/");
}

type ProjectMode = "domain_knowledge" | "talent_demand";

const MODE_CONFIG: Record<ProjectMode, {
  eyebrow: string;
  title: string;
  subtitle: string;
  modeTitle: string;
  modeDescription: string;
  fieldLabel: string;
  placeholder: string;
  cta: string;
  reportToggle: string;
  reportHelp: string;
}> = {
  domain_knowledge: {
    eyebrow: "SectorBreaker 个人版",
    title: "把陌生领域，整理成可继续生长的知识库。",
    subtitle: "粘贴外部 AI 报告、接入开放搜索，系统会先建证据账本，再生成 Obsidian-ready 的领域认知系统。",
    modeTitle: "领域建库",
    modeDescription: "个人学习与入局陌生领域：术语、趋势、工具、学习路线、待验证问题。",
    fieldLabel: "研究领域",
    placeholder: "例如：高考教育线上培训、编程教育、AI Agent 工具",
    cta: "开始构建知识库",
    reportToggle: "可选：粘贴 Gemini / Kimi / Qwen / DeepSeek 报告",
    reportHelp: "支持 Markdown / TXT / Word / PDF。系统会把它拆成低可信线索，再结合搜索证据生成知识库。",
  },
  talent_demand: {
    eyebrow: "TalentScope 企业版延伸",
    title: "把岗位样本和招聘材料，沉淀成人才需求情报。",
    subtitle: "面向 HR、课程团队、招聘研究和就业分析：从 JD、Boss 样本、外部报告和搜索补充中抽取岗位画像与技能矩阵。",
    modeTitle: "人才需求情报台",
    modeDescription: "企业侧垂直场景：岗位画像、技能频次、经验薪资信号、能力模型、作品集要求。",
    fieldLabel: "目标岗位 / 能力方向",
    placeholder: "例如：大模型应用开发工程师、AI Agent 工程师",
    cta: "开始生成人才需求情报",
    reportToggle: "可选：上传外部招聘/行业调研报告",
    reportHelp: "支持 Markdown / TXT / Word / PDF。外部 AI DeepSearch 报告会作为已有研究材料进入证据账本。",
  },
};

type BossCollectionSettings = {
  enabled: boolean;
  city: string;
  limit: number;
};

type SourceCoverageMatrix = {
  total_evidence?: number;
  uploaded_jd_count?: number;
  uploaded_report_count?: number;
  boss_job_count?: number;
  search_result_count?: number;
  extracted_page_count?: number;
  occupation_standard_count?: number;
  salary_signal_count?: number;
  experience_signal_count?: number;
  skill_signal_count?: number;
  weak_or_unverified_count?: number;
  gaps?: string[];
};

function asSourceCoverageMatrix(value: unknown): SourceCoverageMatrix | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  if ("source_coverage" in record) return asSourceCoverageMatrix(record.source_coverage);
  if (!("total_evidence" in record) && !("skill_signal_count" in record)) return null;
  return record as SourceCoverageMatrix;
}

function extractSourceCoverage(events: RunEvent[], artifacts: Artifact[]): SourceCoverageMatrix | null {
  const eventCoverage = [...events].reverse()
    .map((event) => asSourceCoverageMatrix(event.data))
    .find(Boolean);
  if (eventCoverage) return eventCoverage;
  const overview = artifacts.find((artifact) => artifact.content_path === "00-岗位需求总览.md" && artifact.content);
  const match = overview?.content?.match(/```json source_coverage\s*([\s\S]*?)```/);
  if (!match) return null;
  try {
    return asSourceCoverageMatrix(JSON.parse(match[1])) ?? null;
  } catch {
    return null;
  }
}

function gapLabel(value: string) {
  if (value === "low_sample") return "样本数量偏低";
  if (value === "no_salary_signal") return "缺少薪资信号";
  if (value === "no_experience_signal") return "缺少经验信号";
  if (value === "search_only_evidence") return "主要依赖搜索摘要";
  return value;
}

function resultQualityMetrics(
  artifacts: Artifact[],
  evidence: Evidence[],
  events: RunEvent[],
  exportManifest: ExportManifest | null,
) {
  const cardArtifacts = artifacts.filter(isKnowledgeCard);
  const mainArtifacts = artifacts.filter((artifact) => !isKnowledgeCard(artifact));
  return {
    evidenceCount: evidence.length,
    mainDocumentCount: mainArtifacts.length,
    knowledgeCardCount: cardArtifacts.length,
    reviewEventCount: events.filter((event) => event.gate === "artifact_review").length,
    unresolvedQuestionCount: cardArtifacts.filter((artifact) => artifact.content_path.startsWith("questions/")).length,
    exportFileCount: exportManifest?.artifact_paths.length ?? 0,
  };
}

function QAReportPanel({ qa }: { qa: QaPayload }) {
  const blocking = qa.blocking_issues ?? [];
  const retry = qa.retry_tasks ?? [];
  const userActions = qa.user_action_needed ?? [];
  return (
    <div className="qa-report-panel">
      {blocking.length > 0 && (
        <div>
          <h4>阻塞项</h4>
          <ul>{blocking.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}
      {retry.length > 0 && (
        <div>
          <h4>重试任务</h4>
          <ul>{retry.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}
      {userActions.length > 0 && (
        <div>
          <h4>需要你补充</h4>
          <ul>{userActions.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}
      {qa.can_continue_with_warning && <p className="qa-warning-note">可降级继续，但相关结论会保留为待验证。</p>}
    </div>
  );
}

function deriveStatuses(events: RunEvent[], definition: WorkflowDefinition | null = null): Record<string, NodeStatus> {
  const statuses: Record<string, NodeStatus> = {};
  for (const event of events) {
    const nodeId = nodeIdForDefinition(event, definition);
    if (!nodeId) continue;
    if (event.event_type === "node_started" || event.event_type === "node_progress") statuses[nodeId] = "running";
    if (event.event_type === "node_completed") statuses[nodeId] = "completed";
    if (event.event_type === "node_skipped") statuses[nodeId] = "skipped";
    if (event.event_type === "node_degraded") statuses[nodeId] = "degraded";
    if (event.event_type === "node_blocked") statuses[nodeId] = "blocked";
    if (event.event_type === "node_failed" || event.event_type === "error") statuses[nodeId] = "failed";
    if (event.event_type === "human_input_required" || event.event_type === "waiting_for_human") statuses[nodeId] = "waiting_for_user";
  }
  return statuses;
}

function formatElapsed(startedAt: number | null) {
  if (!startedAt) return "00:00";
  const total = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const min = String(Math.floor(total / 60)).padStart(2, "0");
  const sec = String(total % 60).padStart(2, "0");
  return `${min}:${sec}`;
}

function LandingView({
  onStart,
  onOpenSettings,
  isLoading,
  llmConfigured,
  searchConfigured,
  searchProviders,
  extractionProviders,
}: {
  onStart: (
    domain: string,
    sourcePolicy: string,
    assistantBrief: string,
    autoRun?: boolean,
    assistantBriefFile?: File | null,
    projectMode?: ProjectMode,
    jdText?: string,
    jdFile?: File | null,
    bossSettings?: BossCollectionSettings,
  ) => void;
  onOpenSettings: () => void;
  isLoading: boolean;
  llmConfigured: boolean;
  searchConfigured: boolean;
  searchProviders: string[];
  extractionProviders: string[];
}) {
  const [domain, setDomain] = useState("");
  const [projectMode, setProjectMode] = useState<ProjectMode>("domain_knowledge");
  const [sourcePolicy, setSourcePolicy] = useState("reliable_first");
  const [jdText, setJdText] = useState("");
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [bossEnabled, setBossEnabled] = useState(false);
  const [bossCity, setBossCity] = useState("北京");
  const [bossLimit, setBossLimit] = useState(8);
  const [assistantBrief, setAssistantBrief] = useState("");
  const [assistantBriefFile, setAssistantBriefFile] = useState<File | null>(null);
  const [showBrief, setShowBrief] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const ctx = gsap.context(() => {
      gsap.from(".landing-panel", { y: 18, autoAlpha: 0, duration: 0.45, stagger: 0.08, ease: "power2.out" });
    }, containerRef);
    return () => ctx.revert();
  }, []);

  function submit() {
    if (!domain.trim()) return;
    onStart(
      domain.trim(),
      sourcePolicy,
      assistantBrief.trim(),
      true,
      assistantBriefFile,
      projectMode,
      jdText.trim(),
      jdFile,
      { enabled: bossEnabled, city: bossCity.trim(), limit: bossLimit },
    );
  }
  const mode = MODE_CONFIG[projectMode];

  return (
    <div ref={containerRef} className={`landing-pro landing-pro--${projectMode === "talent_demand" ? "enterprise" : "personal"}`}>
      <section className="landing-panel landing-panel--main">
        <div className="landing-brand">
          <Logo size={44} />
          <div>
            <h1>{projectMode === "talent_demand" ? "TalentScope" : "SectorBreaker"}</h1>
            <p>{mode.eyebrow}</p>
          </div>
        </div>
        <div className="landing-copy">
          <h2>{mode.title}</h2>
          <p>{mode.subtitle}</p>
        </div>
        {!llmConfigured && (
          <button className="landing-warning" onClick={onOpenSettings} type="button">
            <Settings size={16} />
            LLM 未配置，点击设置 API 密钥
          </button>
        )}
        {!searchConfigured && (
          <button className="landing-warning" onClick={onOpenSettings} type="button">
            <AlertTriangle size={16} />
            搜索未配置，点击接入可靠信源和搜索 Key
          </button>
        )}
        {searchConfigured && (
          <div className="provider-status-card">
            <div className="provider-status-item">
              <strong>搜索 Provider</strong>
              <span>{searchProviders.join(", ") || "unknown"}</span>
            </div>
            <div className="provider-status-item">
              <strong>抽取 Provider</strong>
              <span>{extractionProviders.join(", ") || "unknown"}</span>
            </div>
          </div>
        )}
        <div className="mode-switch" role="group" aria-label="项目模式">
          <button
            className={projectMode === "domain_knowledge" ? "mode-card mode-card--active" : "mode-card"}
            type="button"
            onClick={() => setProjectMode("domain_knowledge")}
          >
            <strong>个人版 · 领域建库</strong>
            <span>{MODE_CONFIG.domain_knowledge.modeDescription}</span>
          </button>
          <button
            className={projectMode === "talent_demand" ? "mode-card mode-card--active" : "mode-card"}
            type="button"
            onClick={() => setProjectMode("talent_demand")}
          >
            <strong>企业版 · {MODE_CONFIG.talent_demand.modeTitle}</strong>
            <span>{MODE_CONFIG.talent_demand.modeDescription}</span>
          </button>
        </div>
        <label className="field-label" htmlFor="domain">{mode.fieldLabel}</label>
        <div className="landing-input-wrap">
          <Search size={18} className="landing-input-icon" />
          <input
            id="domain"
            className="landing-input"
            value={domain}
            onChange={(event) => setDomain(event.target.value)}
            placeholder={mode.placeholder}
            autoFocus
          />
        </div>
        {projectMode === "talent_demand" && (
          <div className="talent-input-panel">
            <div className="panel-title">
              <FileText size={16} />
              <span>人才需求材料</span>
            </div>
            <p>优先上传或粘贴真实 JD / 岗位说明 / 外部调研报告；搜索只作为补充，不默认抓取登录型招聘网站。</p>
            <textarea
              className="assistant-brief-input"
              value={jdText}
              onChange={(event) => setJdText(event.target.value)}
              placeholder="可粘贴一段或多段 JD：岗位、公司、地点、薪资、经验、职责、技能要求……"
              rows={6}
            />
            <label className="file-upload-card">
              <strong>上传 JD / 岗位材料</strong>
              <span>支持 `.md` / `.txt` / `.docx` / `.pdf`，会作为 user_upload 信源进入 Evidence Ledger。</span>
              <input
                type="file"
                aria-label="上传 JD 或岗位材料文件"
                accept=".md,.markdown,.txt,.docx,.pdf,text/markdown,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={(event) => setJdFile(event.target.files?.[0] ?? null)}
              />
              {jdFile && <em>{jdFile.name}</em>}
            </label>
            <div className="boss-source-panel">
              <label className="toggle-chip boss-source-toggle">
                <input
                  type="checkbox"
                  checked={bossEnabled}
                  onChange={(event) => setBossEnabled(event.target.checked)}
                />
                <span>启用 Boss 直聘职位样本采集</span>
              </label>
              <p>企业版专用。未安装本地 Boss CLI 时会在运行日志中降级提示，不影响上传 JD / 外部报告流程。</p>
              <div className="boss-source-grid">
                <label>
                  <span>城市</span>
                  <input
                    value={bossCity}
                    onChange={(event) => setBossCity(event.target.value)}
                    placeholder="例如：北京、上海、深圳"
                    disabled={!bossEnabled}
                  />
                </label>
                <label>
                  <span>样本数</span>
                  <input
                    type="number"
                    min={1}
                    max={30}
                    value={bossLimit}
                    onChange={(event) => setBossLimit(Number(event.target.value) || 8)}
                    disabled={!bossEnabled}
                  />
                </label>
              </div>
            </div>
          </div>
        )}
        <div className="source-policy-grid">
          {sourcePolicies.map((item) => (
            <button
              key={item.value}
              className={`source-policy-card ${sourcePolicy === item.value ? "source-policy-card--active" : ""}`}
              onClick={() => setSourcePolicy(item.value)}
              type="button"
            >
              <strong>{item.label}</strong>
              <span>{item.desc}</span>
            </button>
          ))}
        </div>
        <button className="brief-toggle" type="button" onClick={() => setShowBrief((value) => !value)}>
          <Sparkles size={15} />
          {showBrief ? "收起外部 AI 报告" : mode.reportToggle}
        </button>
        {showBrief && (
          <div className="upload-stack">
            <textarea
              className="assistant-brief-input"
              value={assistantBrief}
              onChange={(event) => setAssistantBrief(event.target.value)}
              placeholder={mode.reportHelp}
              rows={7}
            />
            <label className="file-upload-card">
              <strong>上传外部 AI 报告</strong>
              <span>支持 `.md` / `.txt` / `.docx` / `.pdf`。会先入库，再参与研究与验证流程。</span>
              <input
                type="file"
                aria-label="上传外部 AI 报告文件"
                accept=".md,.markdown,.txt,.docx,.pdf,text/markdown,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={(event) => setAssistantBriefFile(event.target.files?.[0] ?? null)}
              />
              {assistantBriefFile && <em>{assistantBriefFile.name}</em>}
            </label>
          </div>
        )}
        <div className="landing-actions">
          <button className="primary" disabled={!domain.trim() || isLoading || !llmConfigured} onClick={() => submit()} type="button">
            {isLoading ? <Loader2 size={16} className="spinner" /> : <Play size={16} />}
            {mode.cta}
          </button>
          <button className="secondary" onClick={onOpenSettings} type="button">
            <Settings size={16} />
            LLM 设置
          </button>
        </div>
      </section>
      <aside className="landing-panel landing-panel--flow">
        <div className="panel-title">
          <Network size={16} />
          <span>{projectMode === "talent_demand" ? "企业情报运行图" : "领域建库运行图"}</span>
        </div>
        <WorkflowEditor isCompact showControls={false} fillHeight variant={projectMode} />
      </aside>
    </div>
  );
}

function ResearchView({
  project,
  runId,
  events,
  snapshot,
  activeAgent,
  activeMessage,
  workflowDefinition,
  onWorkflowDefinition,
  isConnected,
  onBack,
  onViewPartialResult,
  searchConfigured,
}: {
  project: Project;
  runId: string;
  events: RunEvent[];
  snapshot: RunSnapshot | null;
  activeAgent: string | null;
  activeMessage: string | null;
  workflowDefinition: WorkflowDefinition | null;
  onWorkflowDefinition: (definition: WorkflowDefinition) => void;
  isConnected: boolean;
  onBack: () => void;
  onViewPartialResult: () => void;
  searchConfigured: boolean;
}) {
  const [selectedNode, setSelectedNode] = useState<WorkflowNode | null>(null);
  const [isLogOpen, setIsLogOpen] = useState(false);
  const [startedAt] = useState(Date.now());
  const [elapsed, setElapsed] = useState("00:00");
  const statuses = useMemo(() => deriveStatuses(events, workflowDefinition), [events, workflowDefinition]);
  const latest = events[events.length - 1];
  const initialNodeId = project.project_mode === "domain_knowledge" ? "initialize_state" : "scope";
  const activeNodeId = latest ? nodeIdForDefinition(latest, workflowDefinition) : initialNodeId;
  const evidenceEvents = countEvidenceSignals(events);
  const agentBriefCards = useMemo(() => buildAgentBriefCards(events), [events]);
  const qaReport = asQaPayload(extractQa(events));
  const snapshotProgress = snapshot?.progress.total
    ? Math.min(100, (snapshot.progress.current / snapshot.progress.total) * 100)
    : null;

  useEffect(() => {
    if (!runId) return;
    api.getRunWorkflowDefinition(runId).then(onWorkflowDefinition).catch(() => {});
  }, [onWorkflowDefinition, runId, events.length]);

  useEffect(() => {
    const timer = window.setInterval(() => setElapsed(formatElapsed(startedAt)), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  return (
    <div className="workbench">
      <header className="workbench-topbar">
        <div className="topbar-brand">
          <Logo size={24} animate={false} />
          <strong>SectorBreaker</strong>
        </div>
        <div className="topbar-project">
          <span>{project.domain}</span>
          <b>{sourcePolicies.find((p) => p.value === project.source_policy)?.label ?? project.source_policy}</b>
        </div>
        <div className="topbar-status">
          <span className={`run-pill ${isConnected ? "run-pill--live" : ""}`}>
            {isConnected ? <Loader2 size={13} className="spinner" /> : <Clock3 size={13} />}
            {isConnected ? "实时连接" : "等待事件"}
          </span>
          <span className="run-time">{elapsed}</span>
          <button className="secondary btn-sm" onClick={onBack} type="button">
            <ArrowLeft size={14} />
            新研究
          </button>
        </div>
      </header>
      <div className={`workbench-grid ${isLogOpen ? "workbench-grid--log-open" : "workbench-grid--log-collapsed"}`}>
        <aside className="workbench-left">
          <div className="panel-title">
            <Network size={15} />
            <span>运行图</span>
          </div>
          <WorkflowEditor
            definition={workflowDefinition}
            activeNodeId={activeNodeId}
            nodeStatuses={statuses}
            onNodeClick={setSelectedNode}
            showMinimap
            fillHeight
          />
        </aside>
        <main className="workbench-center">
          <section className="agent-focus-card">
            <div className="agent-focus-head">
              <span>{activeAgent ?? snapshot?.current_stage ?? "Agent Kernel"}</span>
              {snapshot?.status === "failed" || latest?.severity === "error" ? <AlertTriangle size={18} /> : <Loader2 size={18} className={isConnected ? "spinner" : ""} />}
            </div>
            <p>{activeMessage ?? latest?.message ?? "正在构建可导出的知识系统。"}</p>
            {snapshot && <p className="inline-note">运行状态：{snapshot.status}，产物 {snapshot.artifact_summary.length} 个。</p>}
            {snapshot?.status === "failed" && (
              <div className="run-recovery-card">
                <strong>运行中断，但当前进度已保留</strong>
                <span>你可以先查看已生成内容，或回到首页重新运行。若已有产物，也可以在结果页尝试导出已有结果。</span>
                <div>
                  <button className="primary btn-sm" onClick={onViewPartialResult} type="button">查看已生成内容</button>
                  <button className="secondary btn-sm" onClick={onBack} type="button">重新运行</button>
                </div>
              </div>
            )}
            {snapshot?.errors.map((item) => (
              <p className="inline-warning" key={`${item.timestamp}-${item.message}`}>{item.message}</p>
            ))}
            {!searchConfigured && (
              <p className="inline-warning">搜索未配置：系统不会主动联网搜索，关键事实覆盖会受限。</p>
            )}
            {snapshotProgress !== null ? (
              <div className="progress-line">
                <span style={{ width: `${snapshotProgress}%` }} />
              </div>
            ) : latest?.progress_total ? (
              <div className="progress-line">
                <span style={{ width: `${Math.min(100, ((latest.progress_current ?? 0) / latest.progress_total) * 100)}%` }} />
              </div>
            ) : (
              <div className="heartbeat-line" />
            )}
          </section>
          <AgentLiveBrief cards={agentBriefCards} latest={latest} />
          <section className="metrics-strip">
            <div>
              <strong>{events.length}</strong>
              <span>事件</span>
            </div>
            <div>
              <strong>{evidenceEvents}</strong>
              <span>证据事件</span>
            </div>
            <div>
              <strong>{Object.values(statuses).filter((value) => value === "completed").length}</strong>
              <span>完成节点</span>
            </div>
            <div>
              <strong>{Object.values(statuses).filter((value) => value === "blocked").length}</strong>
              <span>阻塞</span>
            </div>
          </section>
          {selectedNode && (
            <section className="node-detail-card">
              <button className="node-detail-close" onClick={() => setSelectedNode(null)} type="button">
                <X size={15} />
              </button>
              <h3>{selectedNode.label}</h3>
              <p>{selectedNode.reason || "该节点用于呈现真实后台执行状态。"}</p>
              <dl>
                <dt>类型</dt><dd>{selectedNode.node_type}</dd>
                <dt>分组</dt><dd>{selectedNode.group}</dd>
                <dt>Agent</dt><dd>{selectedNode.agent_id ?? "-"}</dd>
              </dl>
            </section>
          )}
          {qaReport && (
            <section className="qa-warning-card">
              <AlertTriangle size={18} />
              <div>
                <strong>质量门提示</strong>
                <QAReportPanel qa={qaReport} />
              </div>
            </section>
          )}
        </main>
        {isLogOpen ? (
          <aside className="workbench-right">
            <div className="panel-title panel-title--split">
              <span>
                <FileText size={15} />
                <span>完整运行日志</span>
              </span>
              <button className="ghost-chip" onClick={() => setIsLogOpen(false)} type="button">收起</button>
            </div>
            <LogStream events={events} />
          </aside>
        ) : (
          <button className="log-drawer-tab" onClick={() => setIsLogOpen(true)} type="button">
            <FileText size={15} />
            展开日志
          </button>
        )}
      </div>
    </div>
  );
}

function AgentLiveBrief({ cards, latest }: { cards: AgentBriefCard[]; latest?: RunEvent }) {
  const headline = cards[cards.length - 1];

  return (
    <section className="agent-live-panel">
      <div className="agent-live-head">
        <div>
          <span className="eyebrow">实时汇报</span>
          <h2>{headline ? headline.label : "等待 Agent 行动"}</h2>
        </div>
        <span className="agent-live-time">{latest ? formatEventTime(latest.timestamp) : "--:--:--"}</span>
      </div>
      {cards.length === 0 ? (
        <div className="agent-live-empty">
          <Sparkles size={18} />
          <span>Agent 启动后，这里会用简短卡片说明它为什么行动、调用了什么工具、拿到了什么结果。</span>
        </div>
      ) : (
        <div className="agent-brief-list">
          {cards.map((card) => (
            <article className={`agent-brief-card agent-brief-card--${card.tone}`} key={card.id}>
              <div className="agent-brief-meta">
                <span>{card.label}</span>
                <time>{formatEventTime(card.timestamp)}</time>
              </div>
              <p>{card.summary}</p>
              {card.detail && <small>{card.detail}</small>}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function ReviewView({
  project,
  runId,
  completedGate,
  events,
  artifacts,
  evidence,
  onContinue,
  onSkip,
}: {
  project: Project;
  runId: string;
  completedGate: string;
  events: RunEvent[];
  artifacts: Artifact[];
  evidence: Evidence[];
  onContinue: (guidance?: string, evidenceData?: string, assistantBrief?: string) => void;
  onSkip: () => void;
}) {
  const [guidance, setGuidance] = useState("");
  const [evidenceData, setEvidenceData] = useState("");
  const [assistantBrief, setAssistantBrief] = useState("");
  const [userMaterialFile, setUserMaterialFile] = useState<File | null>(null);
  const [assistantBriefFile, setAssistantBriefFile] = useState<File | null>(null);
  const plan = extractPlan(events);
  const qaReport = asQaPayload(extractQa(events));
  const isPlanReview = completedGate === "supervisor_plan";
  const isQaBlocked = Boolean(qaReport);

  return (
    <div className="review-pro">
      <header className="review-pro-header">
        <div>
          <Logo size={24} animate={false} />
          <strong>{isPlanReview ? "确认主管计划" : isQaBlocked ? "质量门需要处理" : "阶段审阅"}</strong>
        </div>
        <span>{project.domain}</span>
      </header>
      <main className="review-pro-grid">
        <section className="review-pro-main">
          {plan && (
            <div className="plan-card">
              <h2>{plan.intent_summary}</h2>
              <p className="muted">{plan.source_policy_reason}</p>
              <div className="plan-section">
                <h3>启用 Agent</h3>
                <div className="agent-chip-grid">
                  {plan.selected_agents.map((agent) => (
                    <div className="agent-chip" key={agent.agent_id}>
                      <strong>{agent.display_name}</strong>
                      <span>{agent.reason}</span>
                      <em>{agent.run_mode} / {agent.verification_level}</em>
                    </div>
                  ))}
                </div>
              </div>
              <div className="plan-section">
                <h3>跳过 Agent</h3>
                <ul className="compact-list">
                  {plan.skipped_agents.map((agent) => <li key={agent.agent_id}>{agent.display_name}：{agent.reason}</li>)}
                </ul>
              </div>
              <div className="plan-section">
                <h3>重点验证</h3>
                <ul className="compact-list">
                  {plan.verification_plan.counterevidence_triggers.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            </div>
          )}
          {qaReport && (
            <div className="qa-block-card">
              <AlertTriangle size={20} />
              <div>
                <h2>QA 阻塞</h2>
                <QAReportPanel qa={qaReport} />
              </div>
            </div>
          )}
          {!plan && !qaReport && (
            <div className="plan-card">
              <h2>阶段完成</h2>
              <p>已生成 {artifacts.length} 个产物，收集 {evidence.length} 条证据。</p>
            </div>
          )}
        </section>
        <aside className="review-pro-side">
          <label>研究方向补充</label>
          <textarea value={guidance} onChange={(e) => setGuidance(e.target.value)} rows={4} placeholder="只需要补方向、边界、偏好；资料查证仍由系统负责。" />
          <label>用户材料</label>
          <textarea value={evidenceData} onChange={(e) => setEvidenceData(e.target.value)} rows={5} placeholder="可粘贴你已有的笔记、链接、报告摘要。" />
          <label className="file-upload-card">
            <strong>上传用户材料</strong>
            <span>支持 `.md` / `.txt` / `.docx` / `.pdf`。恢复运行前会先上传到项目 documents。</span>
            <input
              type="file"
              aria-label="上传用户材料文件"
              accept=".md,.markdown,.txt,.docx,.pdf,text/markdown,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(event) => setUserMaterialFile(event.target.files?.[0] ?? null)}
            />
            {userMaterialFile && <em>{userMaterialFile.name}</em>}
          </label>
          {isPlanReview && (
            <>
              <label>外部 AI 报告（可选）</label>
              <textarea value={assistantBrief} onChange={(e) => setAssistantBrief(e.target.value)} rows={7} placeholder="Markdown / txt。仅作为线索，不能单独支撑事实。" />
              <label className="file-upload-card">
                <strong>上传外部 AI 报告</strong>
                <span>支持 `.md` / `.txt` / `.docx` / `.pdf`。会作为低可信线索进入后续验证。</span>
                <input
                  type="file"
                  aria-label="上传阶段外部 AI 报告文件"
                  accept=".md,.markdown,.txt,.docx,.pdf,text/markdown,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  onChange={(event) => setAssistantBriefFile(event.target.files?.[0] ?? null)}
                />
                {assistantBriefFile && <em>{assistantBriefFile.name}</em>}
              </label>
            </>
          )}
          <div className="review-actions">
            <button className="secondary" onClick={onSkip} type="button">跳过补充</button>
            <button
              className="primary"
              onClick={async () => {
                if (userMaterialFile) {
                  await api.uploadDocument(project.id, { channel: "user_upload", file: userMaterialFile });
                }
                if (assistantBriefFile) {
                  await api.uploadDocument(project.id, { channel: "assistant_brief", file: assistantBriefFile });
                }
                onContinue(guidance, evidenceData, assistantBrief);
              }}
              type="button"
            >
              <CheckCircle2 size={16} />
              确认并继续
            </button>
          </div>
        </aside>
      </main>
    </div>
  );
}

function ResultView({
  project,
  artifacts,
  evidence,
  events,
  chat,
  setChat,
  exportManifest,
  setExportManifest,
  onNewResearch,
  toastError,
  toastSuccess,
}: {
  project: Project;
  artifacts: Artifact[];
  evidence: Evidence[];
  events: RunEvent[];
  chat: ChatResponse | null;
  setChat: (c: ChatResponse | null) => void;
  exportManifest: ExportManifest | null;
  setExportManifest: (m: ExportManifest | null) => void;
  onNewResearch: () => void;
  toastError: (msg: string) => void;
  toastSuccess: (msg: string) => void;
}) {
  const [question, setQuestion] = useState("");
  const [isExporting, setIsExporting] = useState(false);
  const [qualityFilter, setQualityFilter] = useState("all");
  const [verificationFilter, setVerificationFilter] = useState("all");
  const [attentionOnly, setAttentionOnly] = useState(false);

  const filteredEvidence = useMemo(() => {
    return evidence.filter((item) => {
      if (qualityFilter !== "all" && (item.source_quality ?? "unknown") !== qualityFilter) {
        return false;
      }
      if (verificationFilter !== "all" && (item.verification_status ?? "unverified") !== verificationFilter) {
        return false;
      }
      if (attentionOnly && !item.needs_counterevidence && item.verification_status !== "conflicting") {
        return false;
      }
      return true;
    });
  }, [attentionOnly, evidence, qualityFilter, verificationFilter]);
  const traceEvents = useMemo(() => events.filter((event) => event.message).slice(-14), [events]);
  const qualityMetrics = useMemo(
    () => resultQualityMetrics(artifacts, evidence, events, exportManifest),
    [artifacts, evidence, events, exportManifest],
  );
  const sourceCoverage = useMemo(() => extractSourceCoverage(events, artifacts), [artifacts, events]);

  async function askQuestion() {
    if (!question.trim()) return;
    try {
      setChat(await api.askQuestion(project.id, question));
    } catch (err) {
      toastError(err instanceof Error ? err.message : "问答请求失败");
    }
  }

  async function exportProject() {
    setIsExporting(true);
    try {
      const manifest = await api.exportProject(project.id);
      setExportManifest(manifest);
      toastSuccess("导出成功");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "导出失败");
    } finally {
      setIsExporting(false);
    }
  }

  async function openExportFolder() {
    if (!exportManifest?.export_dir) {
      toastError("导出目录不存在，请先导出一次");
      return;
    }
    try {
      await api.openExportFolder(exportManifest.export_dir);
      toastSuccess("已打开导出文件夹");
    } catch (err) {
      toastError(err instanceof Error ? err.message : "打开文件夹失败");
    }
  }

  return (
    <div className="result-pro">
      <header className="workbench-topbar">
        <div className="topbar-brand"><Logo size={24} animate={false} /><strong>SectorBreaker</strong></div>
        <div className="topbar-project">
          <span>{project.domain}</span>
          <b>{project.project_mode === "talent_demand" ? "人才需求情报完成" : "研究完成"}</b>
        </div>
        <button className="secondary btn-sm" onClick={onNewResearch} type="button"><Play size={14} />新研究</button>
      </header>
      <main className="result-pro-grid">
        <section className="result-card result-card--wide result-card--trace">
          <h3><Clock3 size={16} />运行轨迹</h3>
          {traceEvents.length > 0 ? (
            <ol className="result-run-trace">
              {traceEvents.map((event, index) => (
                <li key={`${event.timestamp}-${event.gate}-${index}`}>
                  <span>{formatEventTime(event.timestamp)}</span>
                  <strong>{event.agent ?? event.gate}</strong>
                  <p>{event.message}</p>
                </li>
              ))}
            </ol>
          ) : (
            <p className="result-empty">暂无运行事件。后续运行会在这里保留每一步轨迹。</p>
          )}
        </section>
        <section className="result-card result-card--wide">
          <h3><Sparkles size={16} />结果质量摘要</h3>
          <div className="quality-grid">
            <div><strong>{qualityMetrics.evidenceCount}</strong><span>证据</span></div>
            <div><strong>{qualityMetrics.mainDocumentCount}</strong><span>主文档</span></div>
            <div><strong>{qualityMetrics.knowledgeCardCount}</strong><span>知识卡片</span></div>
            <div><strong>{qualityMetrics.reviewEventCount}</strong><span>审查补写事件</span></div>
            <div><strong>{qualityMetrics.unresolvedQuestionCount}</strong><span>待验证问题</span></div>
            <div><strong>{qualityMetrics.exportFileCount || "未导出"}</strong><span>导出文件</span></div>
          </div>
          {!exportManifest && <p className="result-empty">点击导出生成 Obsidian Vault，导出后会写入 README、证据账本、主文档和知识卡片。</p>}
        </section>
        {sourceCoverage && (
          <section className="result-card result-card--wide source-coverage-card">
            <h3><Database size={16} />信源覆盖矩阵</h3>
            <div className="quality-grid source-coverage-grid">
              <div><strong>{sourceCoverage.total_evidence ?? 0}</strong><span>总证据</span></div>
              <div><strong>{sourceCoverage.uploaded_jd_count ?? 0}</strong><span>上传 JD</span></div>
              <div><strong>{sourceCoverage.uploaded_report_count ?? 0}</strong><span>外部报告</span></div>
              <div><strong>{sourceCoverage.boss_job_count ?? 0}</strong><span>Boss 样本</span></div>
              <div><strong>{sourceCoverage.search_result_count ?? 0}</strong><span>搜索来源</span></div>
              <div><strong>{sourceCoverage.skill_signal_count ?? 0}</strong><span>技能信号</span></div>
              <div><strong>{sourceCoverage.salary_signal_count ?? 0}</strong><span>薪资信号</span></div>
              <div><strong>{sourceCoverage.experience_signal_count ?? 0}</strong><span>经验信号</span></div>
              <div><strong>{sourceCoverage.weak_or_unverified_count ?? 0}</strong><span>弱/未验证</span></div>
            </div>
            {sourceCoverage.gaps && sourceCoverage.gaps.length > 0 && (
              <div className="coverage-gap-list">
                {sourceCoverage.gaps.map((gap) => <span key={gap}>{gapLabel(gap)}</span>)}
              </div>
            )}
          </section>
        )}
        <section className="result-card">
          <h3><FileText size={16} />产物</h3>
          <ul className="result-artifact-list">
            {artifacts.map((item) => <li key={item.id}><span>{item.title}</span><em>{item.content_path}</em></li>)}
          </ul>
        </section>
        <section className="result-card">
          <h3><Database size={16} />证据账本</h3>
          <div className="evidence-toolbar">
            <div className="evidence-toolbar-title">
              <Filter size={14} />
              <span>{filteredEvidence.length} / {evidence.length} 条证据</span>
            </div>
            <div className="evidence-filter-row">
              <select aria-label="证据质量筛选" value={qualityFilter} onChange={(e) => setQualityFilter(e.target.value)}>
                <option value="all">全部质量</option>
                <option value="high">高可信</option>
                <option value="medium">中可信</option>
                <option value="low">低可信</option>
                <option value="unknown">未知</option>
              </select>
              <select aria-label="证据验证状态筛选" value={verificationFilter} onChange={(e) => setVerificationFilter(e.target.value)}>
                <option value="all">全部状态</option>
                <option value="verified">已验证</option>
                <option value="partially_verified">部分验证</option>
                <option value="unverified">未验证</option>
                <option value="conflicting">有冲突</option>
              </select>
              <label className="toggle-chip">
                <input
                  type="checkbox"
                  checked={attentionOnly}
                  onChange={(e) => setAttentionOnly(e.target.checked)}
                />
                <span>仅看风险项</span>
              </label>
            </div>
          </div>
          <ul className="result-evidence-list">
            {filteredEvidence.map((item) => (
              <li key={item.id}>
                <div className="evidence-head">
                  <strong>{item.source_title}</strong>
                  {item.source_url && (
                    <a className="evidence-link" href={item.source_url} target="_blank" rel="noreferrer">
                      <ExternalLink size={13} />
                      来源
                    </a>
                  )}
                </div>
                <div className="evidence-chip-row">
                  <span className={`evidence-chip evidence-chip--quality-${item.source_quality ?? "unknown"}`}>
                    {labelForQuality(item.source_quality)}
                  </span>
                  <span className={`evidence-chip evidence-chip--status-${item.verification_status ?? "unverified"}`}>
                    {labelForVerification(item.verification_status)}
                  </span>
                  {item.source_type && <span className="evidence-chip">{item.source_type}</span>}
                  {item.needs_counterevidence && <span className="evidence-chip evidence-chip--attention">待反证</span>}
                </div>
                <p>{cleanDisplaySnippet(item.snippet, item.source_title)}</p>
                {(item.bias_risk || item.collected_by) && (
                  <span>
                    {item.bias_risk ?? item.collected_by}
                  </span>
                )}
              </li>
            ))}
          </ul>
          {filteredEvidence.length === 0 && <p className="result-empty">当前筛选条件下没有证据。</p>}
        </section>
        <section className="result-card result-card--wide">
          <h3><Search size={16} />项目问答</h3>
          <div className="result-chat-row">
            <input value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => e.key === "Enter" && askQuestion()} placeholder="基于证据账本继续追问" />
            <button className="primary btn-sm" onClick={askQuestion} disabled={!question.trim()} type="button">询问</button>
            <button className="secondary btn-sm" onClick={exportProject} disabled={isExporting} type="button">
              {isExporting ? <Loader2 size={14} className="spinner" /> : <Download size={14} />}
              导出
            </button>
            {exportManifest?.export_dir && (
              <button className="secondary btn-sm" onClick={openExportFolder} type="button">
                <ExternalLink size={14} />
                打开文件夹
              </button>
            )}
          </div>
          {chat && (
            <div className="chat-answer">
              <p>{chat.answer}</p>
              <span>引用：{chat.citations.join(", ") || "无"}</span>
              {chat.citation_details && chat.citation_details.length > 0 && (
                <ul className="rag-citation-list">
                  {chat.citation_details.map((item) => (
                    <li key={item.source_id}>
                      <strong>{item.title}</strong>
                      <em>{item.source_type} · {item.source_id}</em>
                      <p>{cleanDisplaySnippet(item.snippet)}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {exportManifest && (
            <div className="chat-answer export-path-card">
              <p>已导出 {exportManifest.artifact_paths.length} 个文件。</p>
              {exportManifest.export_dir && <span>目录：{exportManifest.export_dir}</span>}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export function App() {
  const { toasts, removeToast, success, error } = useToast();
  const [phase, setPhase] = useState<AppPhase>("landing");
  const [project, setProject] = useState<Project | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [workflowDefinition, setWorkflowDefinition] = useState<WorkflowDefinition | null>(null);
  const [runSnapshot, setRunSnapshot] = useState<RunSnapshot | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [chat, setChat] = useState<ChatResponse | null>(null);
  const [exportManifest, setExportManifest] = useState<ExportManifest | null>(null);
  const [showConfig, setShowConfig] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [activeMessage, setActiveMessage] = useState<string | null>(null);
  const [reviewingGate, setReviewingGate] = useState<string | null>(null);
  const [llmConfigured, setLlmConfigured] = useState(true);
  const [searchConfigured, setSearchConfigured] = useState(true);
  const [searchProviders, setSearchProviders] = useState<string[]>([]);
  const [extractionProviders, setExtractionProviders] = useState<string[]>([]);

  const refreshRuntimeStatus = useCallback(async () => {
    try {
      const cfg = await api.getLLMConfig();
      setLlmConfigured(cfg.configured);
    } catch {
      setLlmConfigured(false);
    }

    try {
      const cfg = await api.getSearchConfig();
      setSearchConfigured(cfg.configured);
      setSearchProviders(cfg.providers || []);
      setExtractionProviders(cfg.extraction_providers || []);
    } catch {
      setSearchConfigured(false);
      setSearchProviders([]);
      setExtractionProviders([]);
    }
  }, []);

  useEffect(() => {
    void refreshRuntimeStatus();
  }, [refreshRuntimeStatus]);

  const onEvent = useCallback((event: RunEvent) => {
    setActiveAgent(event.agent ?? null);
    setActiveMessage(event.message);
  }, []);

  const onComplete = useCallback(async () => {
    if (!project || !runId) return;
    try {
      const snapshot = await api.getRunSnapshot(runId);
      const [artifactData, evidenceData] = await Promise.all([api.listArtifacts(project.id), api.listEvidence(project.id)]);
      setRunSnapshot(snapshot);
      setArtifacts(artifactData);
      setEvidence(evidenceData);
      if (snapshot.status === "completed") {
        setReviewingGate(null);
        setPhase("result");
      } else if (snapshot.status === "failed") {
        setPhase("researching");
        error(snapshot.errors[0]?.message ?? "运行失败");
      } else {
        setReviewingGate(snapshot.current_stage || "export");
        setPhase("reviewing");
      }
    } catch {
      error("获取研究结果失败");
    }
  }, [error, project, runId]);

  const { events, isConnected, reset: resetEvents } = useRunEvents({ runId, onEvent, onComplete, onError: error });
  const effectiveEvents = runSnapshot?.events.length ? runSnapshot.events : events;

  useEffect(() => {
    if (!runId || phase !== "researching" || runSnapshot?.status === "failed") return;
    const activeRunId = runId;
    let disposed = false;
    async function refreshSnapshot() {
      try {
        const snapshot = await api.getRunSnapshot(activeRunId);
        if (disposed) return;
        setRunSnapshot(snapshot);
        if (snapshot.status === "completed") {
          const [artifactData, evidenceData] = await Promise.all([
            api.listArtifacts(snapshot.project_id),
            api.listEvidence(snapshot.project_id),
          ]);
          if (disposed) return;
          setArtifacts(artifactData);
          setEvidence(evidenceData);
          setPhase("result");
        } else if (snapshot.status === "failed") {
          error(snapshot.errors[0]?.message ?? "运行失败");
        }
      } catch {
        // Snapshot polling is a recovery path; SSE can continue driving live events.
      }
    }
    void refreshSnapshot();
    const timer = window.setInterval(refreshSnapshot, 2500);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [error, phase, runId, runSnapshot?.status]);

  useEffect(() => {
    const waiting = effectiveEvents.find((event) => event.event_type === "waiting_for_human" || event.event_type === "human_input_required");
    if (waiting && phase === "researching") {
      setReviewingGate(waiting.gate);
      setPhase("reviewing");
    }
  }, [effectiveEvents, phase]);

  async function startResearch(
    domain: string,
    sourcePolicy: string,
    assistantBrief: string,
    autoRun = true,
    assistantBriefFile: File | null = null,
    projectMode: ProjectMode = "domain_knowledge",
    jdText = "",
    jdFile: File | null = null,
    bossSettings: BossCollectionSettings = { enabled: false, city: "", limit: 8 },
  ) {
    setIsLoading(true);
    try {
      const proj = await api.createProject({
        title: domain,
        domain,
        market_scope: "mixed",
        depth: "quick",
        source_policy: sourcePolicy,
        project_mode: projectMode,
      });
      setProject(proj);
      setRunSnapshot(null);
      if (projectMode === "talent_demand" && jdText) {
        await api.createDocument(proj.id, {
          channel: "user_upload",
          file_name: "pasted-jd.md",
          mime_type: "text/markdown",
          content: jdText,
        });
      }
      if (projectMode === "talent_demand" && jdFile) {
        await api.uploadDocument(proj.id, { channel: "user_upload", file: jdFile });
      }
      if (projectMode === "talent_demand") {
        await api.updateJobSourceConfig({
          enabled: bossSettings.enabled,
          provider: bossSettings.enabled ? "boss_agent_cli" : "disabled",
          boss_keyword: domain,
          boss_city: bossSettings.city || null,
          boss_limit: bossSettings.limit,
          boss_agent_cli_command: "boss",
          boss_agent_cli_timeout_seconds: 45,
        });
      }
      if (assistantBrief) {
        await api.createDocument(proj.id, {
          channel: "assistant_brief",
          file_name: "assistant-brief.md",
          mime_type: "text/markdown",
          content: assistantBrief,
        });
      }
      if (assistantBriefFile) {
        await api.uploadDocument(proj.id, { channel: "assistant_brief", file: assistantBriefFile });
      }
      const run = await api.startRun(proj.id, autoRun);
      setRunId(run.id);
      setPhase("researching");
      if (assistantBrief && !autoRun) {
        // The user can still edit it on the plan confirmation screen; keep this UX non-blocking.
        success("外部报告已准备，可在计划确认页再次确认。");
      }
    } catch (err) {
      error(err instanceof Error ? err.message : "启动研究失败");
    } finally {
      setIsLoading(false);
    }
  }

  function resetToLanding() {
    setPhase("landing");
    setProject(null);
    setRunId(null);
    setWorkflowDefinition(null);
    setRunSnapshot(null);
    setArtifacts([]);
    setEvidence([]);
    setChat(null);
    setExportManifest(null);
    setReviewingGate(null);
    resetEvents();
  }

  async function handleReviewContinue(guidance?: string, evidenceData?: string, assistantBrief?: string) {
    if (!runId) return;
    if (reviewingGate === "export") {
      setPhase("result");
      success("研究完成");
      return;
    }
    try {
      await api.resumeRun(runId, {
        guidance: guidance || undefined,
        evidence_data: evidenceData || undefined,
        assistant_brief: assistantBrief || undefined,
        plan_confirmed: true,
      });
      setPhase("researching");
      setReviewingGate(null);
      success("已继续研究");
    } catch (err) {
      error(err instanceof Error ? err.message : "恢复研究失败");
    }
  }

  async function handleReviewSkip() {
    if (reviewingGate === "export") {
      setPhase("result");
      return;
    }
    await handleReviewContinue();
  }

  return (
    <main className="shell">
      <ToastContainer toasts={toasts} onRemove={removeToast} />
      <ConfigPanel
        isOpen={showConfig}
        onClose={() => setShowConfig(false)}
        onSuccess={success}
        onError={error}
        onConfigChanged={refreshRuntimeStatus}
      />
      {phase === "landing" && (
        <LandingView
          onStart={startResearch}
          onOpenSettings={() => setShowConfig(true)}
          isLoading={isLoading}
          llmConfigured={llmConfigured}
          searchConfigured={searchConfigured}
          searchProviders={searchProviders}
          extractionProviders={extractionProviders}
        />
      )}
      {phase === "researching" && project && (
        <ResearchView
          project={project}
          runId={runId ?? ""}
          events={effectiveEvents}
          snapshot={runSnapshot}
          activeAgent={activeAgent}
          activeMessage={activeMessage}
          workflowDefinition={workflowDefinition}
          onWorkflowDefinition={setWorkflowDefinition}
          isConnected={isConnected}
          onBack={resetToLanding}
          onViewPartialResult={() => setPhase("result")}
          searchConfigured={searchConfigured}
        />
      )}
      {phase === "reviewing" && project && runId && (
        <ReviewView
          project={project}
          runId={runId}
          completedGate={reviewingGate ?? "export"}
          events={effectiveEvents}
          artifacts={artifacts}
          evidence={evidence}
          onContinue={handleReviewContinue}
          onSkip={handleReviewSkip}
        />
      )}
      {phase === "result" && project && (
        <ResultView
          project={project}
          artifacts={artifacts}
          evidence={evidence}
          events={effectiveEvents}
          chat={chat}
          setChat={setChat}
          exportManifest={exportManifest}
          setExportManifest={setExportManifest}
          onNewResearch={resetToLanding}
          toastError={error}
          toastSuccess={success}
        />
      )}
    </main>
  );
}
