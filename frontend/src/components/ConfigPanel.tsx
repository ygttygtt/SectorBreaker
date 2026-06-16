import { useState, useEffect } from "react";
import { Settings, Eye, EyeOff, Loader2, CheckCircle2, XCircle } from "lucide-react";

interface ConfigPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (message: string) => void;
  onError: (message: string) => void;
}

interface LLMConfigStatus {
  configured: boolean;
  base_url?: string;
  model?: string;
}

export function ConfigPanel({ isOpen, onClose, onSuccess, onError }: ConfigPanelProps) {
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [configStatus, setConfigStatus] = useState<LLMConfigStatus | null>(null);

  useEffect(() => {
    if (isOpen) {
      fetchConfigStatus();
    }
  }, [isOpen]);

  async function fetchConfigStatus() {
    try {
      const response = await fetch("/api/config/llm");
      if (response.ok) {
        const status = await response.json();
        setConfigStatus(status);
        if (status.configured) {
          setBaseUrl(status.base_url || "");
          setModel(status.model || "");
        }
      }
    } catch (err) {
      console.error("Failed to fetch config status:", err);
    }
  }

  async function handleTest() {
    if (!baseUrl || !apiKey || !model) {
      onError("请填写所有必填字段");
      return;
    }

    setIsTesting(true);
    setTestResult(null);

    try {
      const response = await fetch("/api/config/llm/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, model }),
      });

      const result = await response.json();
      setTestResult(result);
    } catch (err) {
      setTestResult({ success: false, message: "请求失败，请检查网络连接" });
    } finally {
      setIsTesting(false);
    }
  }

  async function handleSave() {
    if (!baseUrl || !apiKey || !model) {
      onError("请填写所有必填字段");
      return;
    }

    setIsSaving(true);

    try {
      const response = await fetch("/api/config/llm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, model }),
      });

      if (response.ok) {
        onSuccess("LLM 配置已保存");
        onClose();
      } else {
        const error = await response.json();
        onError(error.detail || "保存失败");
      }
    } catch (err) {
      onError("请求失败，请检查网络连接");
    } finally {
      setIsSaving(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-header">
          <div className="modal-title">
            <Settings size={20} />
            <h3>LLM 配置</h3>
          </div>
          <button className="modal-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="modal-body">
          {configStatus?.configured && (
            <div className="config-status configured">
              <CheckCircle2 size={16} />
              <span>当前已配置: {configStatus.model}</span>
            </div>
          )}

          <div className="form-group">
            <label htmlFor="baseUrl">Base URL *</label>
            <input
              id="baseUrl"
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
            />
            <span className="form-hint">OpenAI 兼容的 API 地址</span>
          </div>

          <div className="form-group">
            <label htmlFor="apiKey">API Key *</label>
            <div className="input-with-toggle">
              <input
                id="apiKey"
                type={showApiKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
              />
              <button
                className="toggle-password"
                onClick={() => setShowApiKey(!showApiKey)}
                type="button"
              >
                {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <span className="form-hint">API 密钥（不会保存到前端）</span>
          </div>

          <div className="form-group">
            <label htmlFor="model">Model *</label>
            <input
              id="model"
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="gpt-4o-mini"
            />
            <span className="form-hint">模型名称</span>
          </div>

          {testResult && (
            <div className={`test-result ${testResult.success ? "success" : "error"}`}>
              {testResult.success ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
              <span>{testResult.message}</span>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button
            className="secondary"
            onClick={handleTest}
            disabled={isTesting || !baseUrl || !apiKey || !model}
          >
            {isTesting ? (
              <>
                <Loader2 size={16} className="spinner" />
                测试中...
              </>
            ) : (
              "测试连接"
            )}
          </button>
          <button
            className="primary"
            onClick={handleSave}
            disabled={isSaving || !baseUrl || !apiKey || !model}
          >
            {isSaving ? (
              <>
                <Loader2 size={16} className="spinner" />
                保存中...
              </>
            ) : (
              "保存配置"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}