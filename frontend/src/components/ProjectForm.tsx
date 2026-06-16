import { useState } from "react";
import { FileText, Loader2 } from "lucide-react";

export interface ProjectConfig {
  domain: string;
  market_scope: string;
  depth: string;
  notes?: string;
}

interface ProjectFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (config: ProjectConfig) => void;
  isLoading?: boolean;
}

const marketScopes = [
  { value: "china", label: "中国市场" },
  { value: "global", label: "全球市场" },
  { value: "mixed", label: "混合市场" },
];

const depths = [
  { value: "quick", label: "快速了解（1-2小时）" },
  { value: "standard", label: "标准研究（半天）" },
  { value: "deep", label: "深入分析（1天+）" },
];

export function ProjectForm({ isOpen, onClose, onSubmit, isLoading }: ProjectFormProps) {
  const [domain, setDomain] = useState("");
  const [marketScope, setMarketScope] = useState("mixed");
  const [depth, setDepth] = useState("quick");
  const [notes, setNotes] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!domain.trim()) {
      return;
    }
    onSubmit({ domain: domain.trim(), market_scope: marketScope, depth, notes: notes.trim() || undefined });
  }

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div className="modal-title">
            <FileText size={20} />
            <h3>新建研究项目</h3>
          </div>
          <button className="modal-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-group">
              <label htmlFor="domain">研究领域 *</label>
              <input
                id="domain"
                type="text"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="例如：AI Agent 工具、本地生活服务、跨境电商"
                required
              />
              <span className="form-hint">输入你想了解的行业或领域</span>
            </div>

            <div className="form-group">
              <label htmlFor="marketScope">市场范围</label>
              <select
                id="marketScope"
                value={marketScope}
                onChange={(e) => setMarketScope(e.target.value)}
              >
                {marketScopes.map((scope) => (
                  <option key={scope.value} value={scope.value}>
                    {scope.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="depth">研究深度</label>
              <select
                id="depth"
                value={depth}
                onChange={(e) => setDepth(e.target.value)}
              >
                {depths.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="notes">备注（可选）</label>
              <textarea
                id="notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="添加你特别想了解的方向、已有的认知、关注的重点等"
                rows={3}
              />
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="secondary" onClick={onClose}>
              取消
            </button>
            <button type="submit" className="primary" disabled={!domain.trim() || isLoading}>
              {isLoading ? (
                <>
                  <Loader2 size={16} className="spinner" />
                  启动中...
                </>
              ) : (
                "启动研究"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}