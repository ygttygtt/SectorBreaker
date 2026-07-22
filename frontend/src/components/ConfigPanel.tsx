import { useState, useEffect } from "react";
import { Settings, Eye, EyeOff, Loader2, CheckCircle2, XCircle, Search, Globe, ShieldCheck, Plus, Save, Trash2, KeyRound, ExternalLink } from "lucide-react";
import { api, type LLMConfigStatus, type LLMPreset, type SearchConfigStatus, type SearchTestResult, type SourceRegistryStatus } from "../api/client";

interface ConfigPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (message: string) => void;
  onError: (message: string) => void;
  onConfigChanged?: () => void;
}

export function ConfigPanel({ isOpen, onClose, onSuccess, onError, onConfigChanged }: ConfigPanelProps) {
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [maxTokens, setMaxTokens] = useState(4096);
  const [presetName, setPresetName] = useState("");
  const [presetNotes, setPresetNotes] = useState("");
  const [selectedPresetId, setSelectedPresetId] = useState("");
  const [llmPresets, setLlmPresets] = useState<LLMPreset[]>([]);
  const [showApiKey, setShowApiKey] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isSavingPreset, setIsSavingPreset] = useState(false);
  const [isApplyingPreset, setIsApplyingPreset] = useState(false);
  const [isDeletingPreset, setIsDeletingPreset] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [configStatus, setConfigStatus] = useState<LLMConfigStatus | null>(null);
  const [savedConfig, setSavedConfig] = useState({
    baseUrl: "",
    model: "",
    maxTokens: 4096,
    selectedPresetId: "",
  });
  const [searchStatus, setSearchStatus] = useState<SearchConfigStatus | null>(null);
  const [searchQuery, setSearchQuery] = useState("AI agent market map");
  const [extractUrl, setExtractUrl] = useState("https://example.com");
  const [searchSourcePolicy, setSearchSourcePolicy] = useState("open_web");
  const [allowedDomainsText, setAllowedDomainsText] = useState("");
  const [blockedDomainsText, setBlockedDomainsText] = useState("");
  const [isTestingSearch, setIsTestingSearch] = useState(false);
  const [searchTestResult, setSearchTestResult] = useState<SearchTestResult | null>(null);
  const [isSavingSearch, setIsSavingSearch] = useState(false);
  const [searchProviderMode, setSearchProviderMode] = useState("tavily");
  const [tavilyApiKey, setTavilyApiKey] = useState("");
  const [serperApiKey, setSerperApiKey] = useState("");
  const [braveApiKey, setBraveApiKey] = useState("");
  const [exaApiKey, setExaApiKey] = useState("");
  const [contentExtractionProvider, setContentExtractionProvider] = useState("http");
  const [firecrawlApiKey, setFirecrawlApiKey] = useState("");
  const [jinaReaderEndpointPrefix, setJinaReaderEndpointPrefix] = useState("https://r.jina.ai/http://");
  const [sourceRegistryStatus, setSourceRegistryStatus] = useState<SourceRegistryStatus | null>(null);
  const [sourceRegistryError, setSourceRegistryError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      fetchConfigStatus();
      fetchLlmPresets();
      fetchSearchStatus();
      fetchSourceRegistryStatus();
    }
  }, [isOpen]);

  const selectedPreset = llmPresets.find((item) => item.id === selectedPresetId);
  const formMatchesSelectedPreset = Boolean(
    selectedPreset
      && baseUrl === selectedPreset.base_url
      && model === selectedPreset.model
      && Number(maxTokens) === Number(selectedPreset.max_tokens || 4096),
  );
  const canUseStoredPresetKey = Boolean(selectedPreset?.has_api_key && formMatchesSelectedPreset);
  const hasUsableApiKey = Boolean(apiKey.trim()) || canUseStoredPresetKey;
  const llmConfigDirty = Boolean(
    apiKey.trim()
      || baseUrl !== savedConfig.baseUrl
      || model !== savedConfig.model
      || Number(maxTokens) !== Number(savedConfig.maxTokens)
      || selectedPresetId !== savedConfig.selectedPresetId,
  );

  function snapshotConfig(status: LLMConfigStatus, presetId = selectedPresetId) {
    const nextSnapshot = {
      baseUrl: status.base_url || "",
      model: status.model || "",
      maxTokens: status.max_tokens || 4096,
      selectedPresetId: presetId,
    };
    setSavedConfig(nextSnapshot);
    return nextSnapshot;
  }

  function handleClose() {
    if (llmConfigDirty && !window.confirm("当前 LLM 配置有未保存改动，确定关闭吗？")) {
      return;
    }
    onClose();
  }

  async function fetchConfigStatus() {
    try {
      const status = await api.getLLMConfig();
      setConfigStatus(status);
      if (status.configured) {
        setBaseUrl(status.base_url || "");
        setModel(status.model || "");
        setMaxTokens(status.max_tokens || 4096);
      }
      snapshotConfig(status);
    } catch (err) {
      console.error("Failed to fetch config status:", err);
    }
  }

  async function fetchLlmPresets() {
    try {
      const result = await api.listLLMPresets();
      setLlmPresets(result.presets);
      if (!selectedPresetId && result.presets.length > 0) {
        setSelectedPresetId(result.presets[0].id);
      }
    } catch (err) {
      console.error("Failed to fetch LLM presets:", err);
    }
  }

  function applyPresetToForm(presetId: string) {
    setSelectedPresetId(presetId);
    const preset = llmPresets.find((item) => item.id === presetId);
    if (!preset) {
      setPresetName("");
      setPresetNotes("");
      setBaseUrl("");
      setApiKey("");
      setModel("");
      setMaxTokens(4096);
      return;
    }
    setPresetName(preset.name);
    setBaseUrl(preset.base_url || "");
    setModel(preset.model || "");
    setMaxTokens(preset.max_tokens || 4096);
    setPresetNotes(preset.notes || "");
    setApiKey("");
  }

  function presetIdFromName(name: string) {
    const slug = name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return slug || `preset-${Date.now()}`;
  }

  async function fetchSearchStatus() {
    try {
      const status = await api.getSearchConfig();
      setSearchStatus(status);
      if (status.requested_provider_mode) {
        setSearchProviderMode(status.requested_provider_mode);
      }
      if (status.extraction_provider) {
        setContentExtractionProvider(status.extraction_provider);
      }
    } catch (err) {
      console.error("Failed to fetch search status:", err);
    }
  }

  function hasStoredSearchKey(provider: string) {
    return Boolean(searchStatus?.configured_api_keys?.includes(provider));
  }

  function connectorStatusLabel(status: string) {
    const labels: Record<string, string> = {
      ready: "直连接口已配置",
      available_via_domain_filter: "仅域名过滤发现，无直连适配器",
      needs_search_provider: "需先配置通用搜索",
      needs_configuration: "实现存在，尚缺配置",
      available_not_selected: "适配器可用，但当前未选择",
      configured_but_unwired: "已有配置，但生产未接线",
      manual_review: "仅人工复核",
      planned: "尚未实现",
    };
    return labels[status] || status;
  }

  async function fetchSourceRegistryStatus() {
    try {
      setSourceRegistryError(null);
      setSourceRegistryStatus(await api.getSourceRegistryStatus());
    } catch (err) {
      setSourceRegistryError(err instanceof Error ? err.message : "可靠信源状态读取失败");
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
      const result = await api.testLLMConnection({ base_url: baseUrl, api_key: apiKey, model, max_tokens: maxTokens });
      setTestResult(result);
    } catch (err) {
      setTestResult({ success: false, message: "请求失败，请检查网络连接" });
    } finally {
      setIsTesting(false);
    }
  }

  async function handleSave() {
    if (!baseUrl || !model || !apiKey.trim()) {
      onError("请填写 Base URL、Model 和 API Key；如果要使用已保存 Key 的预设，请点击应用预设。");
      return;
    }

    setIsSaving(true);

    try {
      await api.updateLLMConfig({ base_url: baseUrl, api_key: apiKey, model, max_tokens: maxTokens });
      onSuccess("LLM 配置已保存");
      setConfigStatus({ configured: true, base_url: baseUrl, model, max_tokens: maxTokens });
      snapshotConfig({ configured: true, base_url: baseUrl, model, max_tokens: maxTokens }, selectedPresetId);
      setApiKey("");
      setTestResult({ success: true, message: `当前生效模型：${model}` });
      onConfigChanged?.();
    } catch (err) {
      onError(err instanceof Error ? err.message : "请求失败，请检查网络连接");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleApplyPreset() {
    if (!selectedPresetId) {
      onError("请先选择一个预设");
      return;
    }
    setIsApplyingPreset(true);
    try {
      const result = await api.applyLLMPreset(selectedPresetId, { api_key: apiKey || undefined });
      const appliedPreset = result.preset || selectedPreset || {
        id: selectedPresetId,
        name: presetName || model || "LLM 预设",
        base_url: baseUrl,
        model,
        max_tokens: maxTokens,
      };
      await fetchConfigStatus();
      await fetchLlmPresets();
      if (!apiKey.trim()) {
        setApiKey("");
      }
      setConfigStatus({ configured: true, base_url: appliedPreset.base_url, model: appliedPreset.model, max_tokens: appliedPreset.max_tokens });
      snapshotConfig(
        { configured: true, base_url: appliedPreset.base_url, model: appliedPreset.model, max_tokens: appliedPreset.max_tokens },
        appliedPreset.id,
      );
      onConfigChanged?.();
      onSuccess(result.message || `LLM 预设已应用：${appliedPreset.name}`);
      setTestResult({ success: true, message: `当前生效模型：${appliedPreset.model}` });
    } catch (err) {
      onError(err instanceof Error ? err.message : "应用预设失败，请确认 Base URL、API Key 和模型名已填写");
    } finally {
      setIsApplyingPreset(false);
    }
  }

  async function handleSavePreset() {
    const name = presetName.trim() || model.trim() || "自定义预设";
    const presetId = selectedPresetId && !llmPresets.find((item) => item.id === selectedPresetId)?.is_builtin
      ? selectedPresetId
      : presetIdFromName(name);
    if (!baseUrl || !model) {
      onError("请至少填写 Base URL 和 Model 后再保存预设");
      return;
    }
    setIsSavingPreset(true);
    try {
      await api.upsertLLMPreset(presetId, {
        name,
        base_url: baseUrl,
        api_key: apiKey || undefined,
        model,
        max_tokens: maxTokens,
        notes: presetNotes || undefined,
      });
      await fetchLlmPresets();
      setSelectedPresetId(presetId);
      setSavedConfig((current) => ({ ...current, selectedPresetId: presetId }));
      onSuccess("LLM 预设已保存到本地");
    } catch (err) {
      onError(err instanceof Error ? err.message : "保存 LLM 预设失败");
    } finally {
      setIsSavingPreset(false);
    }
  }

  function handlePrimarySave() {
    if (canUseStoredPresetKey && !apiKey.trim()) {
      void handleApplyPreset();
      return;
    }
    void handleSave();
  }

  async function handleDeletePreset() {
    const preset = llmPresets.find((item) => item.id === selectedPresetId);
    if (!preset || preset.is_builtin) {
      onError("内置预设不能删除");
      return;
    }
    setIsDeletingPreset(true);
    try {
      await api.deleteLLMPreset(preset.id);
      await fetchLlmPresets();
      setSelectedPresetId("");
      setPresetName("");
      setPresetNotes("");
      onSuccess("LLM 预设已删除");
    } catch (err) {
      onError(err instanceof Error ? err.message : "删除 LLM 预设失败");
    } finally {
      setIsDeletingPreset(false);
    }
  }

  async function handleSearchTest() {
    if (!searchQuery.trim()) {
      onError("请先填写测试查询");
      return;
    }

    setIsTestingSearch(true);
    setSearchTestResult(null);

    try {
      const allowedDomains = allowedDomainsText
        .split(/[\n,]+/)
        .map((item) => item.trim())
        .filter(Boolean);
      const blockedDomains = blockedDomainsText
        .split(/[\n,]+/)
        .map((item) => item.trim())
        .filter(Boolean);
      const result = await api.testSearchConnection({
        query: searchQuery.trim(),
        url_to_extract: extractUrl.trim() || undefined,
        market_scope: "mixed",
        source_policy: searchSourcePolicy,
        max_results: 3,
        allowed_domains: allowedDomains,
        blocked_domains: blockedDomains,
      });
      setSearchTestResult(result);
      if (result.success) {
        onSuccess("搜索链路测试完成");
      }
    } catch (err) {
      setSearchTestResult({
        success: false,
        message: err instanceof Error ? err.message : "搜索链路测试失败",
        source_policy: searchSourcePolicy,
        providers: [],
        effective_allowed_domains: [],
        effective_blocked_domains: [],
        result_count: 0,
        results: [],
        extracted_page: null,
      });
    } finally {
      setIsTestingSearch(false);
    }
  }

  async function handleSaveSearchConfig() {
    setIsSavingSearch(true);
    try {
      const result = await api.updateSearchConfig({
        search_provider_mode: searchProviderMode,
        tavily_api_key: tavilyApiKey || undefined,
        tavily_endpoint: "https://api.tavily.com/search",
        serper_api_key: serperApiKey || undefined,
        serper_endpoint: "https://google.serper.dev/search",
        brave_api_key: braveApiKey || undefined,
        brave_endpoint: "https://api.search.brave.com/res/v1/web/search",
        exa_api_key: exaApiKey || undefined,
        exa_endpoint: "https://api.exa.ai/search",
        firecrawl_search_endpoint: "https://api.firecrawl.dev/v2/search",
        content_extraction_provider: contentExtractionProvider,
        firecrawl_api_key: firecrawlApiKey || undefined,
        firecrawl_endpoint: "https://api.firecrawl.dev/v1/scrape",
        jina_reader_endpoint_prefix: jinaReaderEndpointPrefix || undefined,
      });
      await fetchSearchStatus();
      await fetchSourceRegistryStatus();
      setTavilyApiKey("");
      setSerperApiKey("");
      setBraveApiKey("");
      setExaApiKey("");
      setFirecrawlApiKey("");
      onConfigChanged?.();
      onSuccess(result.message);
    } catch (err) {
      onError(err instanceof Error ? err.message : "搜索配置保存失败");
    } finally {
      setIsSavingSearch(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="modal-overlay">
      <div className="modal-content config-modal">
        <div className="modal-header">
          <div className="modal-title">
            <Settings size={20} />
            <h3>LLM 配置</h3>
          </div>
          <button className="modal-close" onClick={handleClose}>
            &times;
          </button>
        </div>

        <div className="modal-body">
          {configStatus?.configured && (
            <div className="config-status configured">
              <CheckCircle2 size={16} />
              <span>当前生效模型：<strong>{configStatus.model}</strong></span>
            </div>
          )}

          {llmConfigDirty && (
            <div className="config-status unsaved">
              <XCircle size={16} />
              <span>当前表单有未保存改动，保存或应用预设后才会用于新测试。</span>
            </div>
          )}

          <div className="config-section">
            <div className="config-section-title">
              <KeyRound size={16} />
              <span>LLM 预设</span>
            </div>

            <div className="settings-grid">
              <div className="settings-card">
                <div className="form-group">
                  <label htmlFor="llmPresetSelect">选择预设</label>
                  <select
                    id="llmPresetSelect"
                    value={selectedPresetId}
                    onChange={(e) => applyPresetToForm(e.target.value)}
                  >
                    <option value="">新建空白配置</option>
                    {llmPresets.map((preset) => (
                      <option key={preset.id} value={preset.id}>
                        {preset.name}{preset.has_api_key ? "（已保存 Key）" : ""}
                      </option>
                    ))}
                  </select>
                  <span className="form-hint">预设和密钥只保存到本地 runtime config，不会进入 Git。</span>
                </div>

                <div className="preset-list">
                  {llmPresets.map((preset) => (
                    <button
                      className={`preset-chip ${preset.id === selectedPresetId ? "active" : ""}`}
                      key={preset.id}
                      onClick={() => applyPresetToForm(preset.id)}
                      type="button"
                    >
                      <strong>{preset.name}</strong>
                      <span>{preset.model || "未填模型"}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="settings-card">
                <div className="form-group">
                  <label htmlFor="presetName">预设名称</label>
                  <input
                    id="presetName"
                    type="text"
                    value={presetName}
                    onChange={(e) => setPresetName(e.target.value)}
                    placeholder="例如：DeepSeek 官方 / 商汤 V4 Flash / Mimo"
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="presetNotes">备注</label>
                  <input
                    id="presetNotes"
                    type="text"
                    value={presetNotes}
                    onChange={(e) => setPresetNotes(e.target.value)}
                    placeholder="用途、速度、价格或上下文长度"
                  />
                </div>
              </div>
            </div>

            <div className="settings-card">
              <div className="config-section-title">
                <Settings size={16} />
                <span>当前连接</span>
              </div>

              <div className="settings-grid compact">
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

                <div className="form-group">
                  <label htmlFor="maxTokens">Max Tokens</label>
                  <input
                    id="maxTokens"
                    type="number"
                    min={512}
                    max={32768}
                    value={maxTokens}
                    onChange={(e) => setMaxTokens(Number(e.target.value || 4096))}
                  />
                  <span className="form-hint">默认 4096，可按模型能力调整</span>
                </div>
              </div>

              <div className="form-group">
                <label htmlFor="apiKey">API Key *</label>
                <div className="input-with-toggle">
                  <input
                    id="apiKey"
                    type={showApiKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={canUseStoredPresetKey ? "已保存，可留空继续使用；输入新 Key 会替换" : "sk-..."}
                  />
                  <button
                    className="toggle-password"
                    onClick={() => setShowApiKey(!showApiKey)}
                    type="button"
                    aria-label={showApiKey ? "隐藏 API Key" : "显示 API Key"}
                  >
                    {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                <span className="form-hint">
                  {canUseStoredPresetKey
                    ? "该预设已有本地保存的 Key。出于安全不会回显明文，留空应用会继续使用旧 Key。"
                    : "Key 仅发送到本地后端保存，列表接口不会回传明文。"}
                </span>
              </div>

              <div className="config-action-row">
                <button className="secondary" onClick={handleApplyPreset} disabled={isApplyingPreset || !selectedPresetId} type="button">
                  {isApplyingPreset ? <Loader2 size={16} className="spinner" /> : <CheckCircle2 size={16} />}
                  应用预设
                </button>
                <button className="secondary" onClick={handleSavePreset} disabled={isSavingPreset || !baseUrl || !model} type="button">
                  {isSavingPreset ? <Loader2 size={16} className="spinner" /> : <Save size={16} />}
                  保存为预设
                </button>
                <button className="secondary danger" onClick={handleDeletePreset} disabled={isDeletingPreset || !selectedPresetId || llmPresets.find((item) => item.id === selectedPresetId)?.is_builtin} type="button">
                  {isDeletingPreset ? <Loader2 size={16} className="spinner" /> : <Trash2 size={16} />}
                  删除预设
                </button>
                <button className="secondary" onClick={() => {
                  setSelectedPresetId("");
                  setPresetName("");
                  setPresetNotes("");
                  setBaseUrl("");
                  setApiKey("");
                  setModel("");
                  setMaxTokens(4096);
                }} type="button">
                  <Plus size={16} />
                  新建空白
                </button>
              </div>
            </div>
          </div>

          <div className="config-section">
            <div className="config-section-title">
              <Search size={16} />
              <span>搜索与抽取配置</span>
            </div>

            {searchStatus?.status_message && (
              <div className="config-status configured">
                <CheckCircle2 size={16} />
                <span>{searchStatus.status_message}</span>
              </div>
            )}

            {searchStatus?.diagnostics?.length ? (
              <div className="test-result error">
                <XCircle size={16} />
                <div>
                  {searchStatus.diagnostics.map((item) => (
                    <div key={item}>{item}</div>
                  ))}
                </div>
              </div>
            ) : null}

            {!searchStatus?.configured && !searchStatus?.diagnostics?.length ? (
              <div className="test-result error">
                <XCircle size={16} />
                <span>当前未配置搜索 provider，测试会失败。</span>
              </div>
            ) : searchStatus?.configured ? (
              <div className="config-status configured">
                <CheckCircle2 size={16} />
                <span>
                  当前搜索 provider: {(searchStatus.providers || []).join(", ")}
                  {" / "}
                  抽取 provider: {(searchStatus.extraction_providers || []).join(", ") || "unknown"}
                </span>
              </div>
            ) : null}

            {searchStatus?.missing_configuration?.length ? (
              <div className="form-hint">
                缺少配置：{searchStatus.missing_configuration.join(", ")}
              </div>
            ) : null}

            {searchStatus?.requested_extraction_provider && (
              <div className="form-hint">
                当前请求的搜索 provider: {searchStatus.requested_provider_mode || searchProviderMode}；
                当前请求的抽取 provider: {searchStatus.requested_extraction_provider}
                {searchStatus.extraction_provider ? `，实际使用: ${searchStatus.extraction_provider}` : ""}
              </div>
            )}

            {searchStatus?.provider_onboarding?.length ? (
              <div className="provider-onboarding-grid">
                {searchStatus.provider_onboarding.map((provider) => (
                  <div className="provider-onboarding-row" key={provider.key}>
                    <div>
                      <strong>{provider.display_name}</strong>
                      <span>
                        {provider.selected ? "当前使用" : provider.configured ? "已配置，未选择" : provider.requires_api_key ? "尚未配置" : "本地可用"}
                      </span>
                    </div>
                    <p>{provider.free_tier_summary}</p>
                    <nav aria-label={`${provider.display_name} 申请与价格`}>
                      {provider.signup_url && (
                        <a href={provider.signup_url} target="_blank" rel="noreferrer">
                          申请 / 获取 Key <ExternalLink size={13} />
                        </a>
                      )}
                      {provider.pricing_url && provider.pricing_url !== provider.signup_url && (
                        <a href={provider.pricing_url} target="_blank" rel="noreferrer">
                          额度与价格 <ExternalLink size={13} />
                        </a>
                      )}
                    </nav>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="form-group">
              <label htmlFor="searchProviderMode">搜索 Provider 模式</label>
              <select
                id="searchProviderMode"
                value={searchProviderMode}
                onChange={(e) => setSearchProviderMode(e.target.value)}
              >
                <option value="auto">auto：自动选择可用 provider</option>
                <option value="tavily">tavily：推荐默认</option>
                <option value="serper">serper：Google Search API</option>
                <option value="brave">brave：Brave Search API</option>
                <option value="exa">exa：语义搜索</option>
                <option value="firecrawl">firecrawl：搜索并发现可抓取网页</option>
                <option value="multi">multi：聚合多个 provider</option>
              </select>
              <span className="form-hint">上传材料会优先进入项目知识状态；开放搜索用于补证和发现缺口。</span>
            </div>

            <div className="form-group">
              <label htmlFor="tavilyApiKey">Tavily API Key（推荐）</label>
              <input
                id="tavilyApiKey"
                type="password"
                value={tavilyApiKey}
                onChange={(e) => setTavilyApiKey(e.target.value)}
                placeholder={hasStoredSearchKey("tavily") ? "已保存；留空则保留" : "tvly-..."}
              />
            </div>

            <div className="form-group">
              <label htmlFor="serperApiKey">Serper API Key</label>
              <input
                id="serperApiKey"
                type="password"
                value={serperApiKey}
                onChange={(e) => setSerperApiKey(e.target.value)}
                placeholder={hasStoredSearchKey("serper") ? "已保存；留空则保留" : "serper-..."}
              />
            </div>

            <div className="form-group">
              <label htmlFor="braveApiKey">Brave Search API Key</label>
              <input
                id="braveApiKey"
                type="password"
                value={braveApiKey}
                onChange={(e) => setBraveApiKey(e.target.value)}
                placeholder={hasStoredSearchKey("brave") ? "已保存；留空则保留" : "brave-..."}
              />
            </div>

            <div className="form-group">
              <label htmlFor="exaApiKey">Exa API Key</label>
              <input
                id="exaApiKey"
                type="password"
                value={exaApiKey}
                onChange={(e) => setExaApiKey(e.target.value)}
                placeholder={hasStoredSearchKey("exa") ? "已保存；留空则保留" : "exa-..."}
              />
            </div>

            <div className="form-group">
              <label htmlFor="contentExtractionProvider">抽取 Provider</label>
              <select
                id="contentExtractionProvider"
                value={contentExtractionProvider}
                onChange={(e) => setContentExtractionProvider(e.target.value)}
              >
                <option value="http">http fallback</option>
                <option value="firecrawl">firecrawl</option>
                <option value="jina">jina</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="firecrawlApiKey">Firecrawl API Key（搜索/抽取共用）</label>
              <input
                id="firecrawlApiKey"
                type="password"
                value={firecrawlApiKey}
                onChange={(e) => setFirecrawlApiKey(e.target.value)}
                placeholder={hasStoredSearchKey("firecrawl") ? "已保存；留空则保留" : "fc-..."}
              />
            </div>

            {contentExtractionProvider === "jina" && (
              <div className="form-group">
                <label htmlFor="jinaReaderEndpointPrefix">Jina Reader Endpoint</label>
                <input
                  id="jinaReaderEndpointPrefix"
                  type="text"
                  value={jinaReaderEndpointPrefix}
                  onChange={(e) => setJinaReaderEndpointPrefix(e.target.value)}
                  placeholder="https://r.jina.ai/http://"
                />
              </div>
            )}

            <button className="secondary" onClick={handleSaveSearchConfig} disabled={isSavingSearch} type="button">
              {isSavingSearch ? (
                <>
                  <Loader2 size={16} className="spinner" />
                  保存搜索配置中...
                </>
              ) : (
                "保存搜索配置"
              )}
            </button>

            <div className="config-section-title">
              <ShieldCheck size={16} />
              <span>可靠信源接入</span>
            </div>
            {sourceRegistryStatus && (
              <div className="source-onboarding">
                <div className="source-onboarding-note">
                  {sourceRegistryStatus.recommended_next_action}
                </div>
                {sourceRegistryStatus.packs.map((pack) => (
                  <div className="source-pack-card" key={pack.name}>
                    <div className="source-pack-head">
                      <strong>{pack.display_name}</strong>
                      <span>{pack.market_scopes.join(", ")}</span>
                    </div>
                    <div className="source-domain-line">
                      权威域名：{pack.reliable_domains.slice(0, 6).join(", ") || "none"}
                    </div>
                    {pack.reliable_domains.length > 0 && (
                      <button
                        className="secondary"
                        type="button"
                        onClick={() => {
                          setAllowedDomainsText(pack.reliable_domains.join(", "));
                          setBlockedDomainsText(pack.blocked_domains.join(", "));
                          setSearchSourcePolicy("reliable_only");
                          setSearchQuery(`${pack.display_name} 官方资料`);
                        }}
                      >
                        载入此信源包自检
                      </button>
                    )}
                    <div className="source-connector-grid">
                      {pack.connectors.map((connector) => (
                        <div
                          className={`source-connector-chip ${connector.configured ? "is-ready" : connector.execution_status === "available_via_domain_filter" ? "is-discovery" : "is-missing"}`}
                          key={connector.key}
                        >
                          <strong>{connector.display_name}</strong>
                          <span>{connector.connector_type} · {connectorStatusLabel(connector.execution_status)}</span>
                          <em>
                            {connector.requires_manual_review
                              ? "人工复核"
                              : connector.required_env_keys.length
                                ? `需要 ${connector.required_env_keys.join(", ")}`
                                : "无需 key"}
                          </em>
                          {connector.setup_url && (
                            <a href={connector.setup_url} target="_blank" rel="noreferrer">获取/查看文档</a>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {sourceRegistryError && <div className="test-result error">{sourceRegistryError}</div>}

            <div className="config-section-title">
              <Globe size={16} />
              <span>搜索链路自检</span>
            </div>

            <div className="form-group">
              <label htmlFor="searchQuery">测试查询</label>
              <input
                id="searchQuery"
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="AI agent market map"
              />
              <span className="form-hint">用于验证当前搜索 provider 是否能返回结果</span>
            </div>

            <div className="form-group">
              <label htmlFor="searchSourcePolicy">测试信源策略</label>
              <select
                id="searchSourcePolicy"
                value={searchSourcePolicy}
                onChange={(e) => {
                  const value = e.target.value;
                  setSearchSourcePolicy(value);
                  if (value === "reliable_only" && searchQuery === "AI agent market map") {
                    setSearchQuery("AI agent market disclosure official data");
                  }
                }}
              >
                <option value="open_web">open_web</option>
                <option value="reliable_first">reliable_first</option>
                <option value="reliable_only">reliable_only</option>
                <option value="user_materials_only">user_materials_only</option>
              </select>
              <span className="form-hint">会自动复用 workflow 中对应的域名约束逻辑。</span>
            </div>

            <div className="form-group">
              <label htmlFor="extractUrl">抽取测试 URL（可选）</label>
              <input
                id="extractUrl"
                type="text"
                value={extractUrl}
                onChange={(e) => setExtractUrl(e.target.value)}
                placeholder="https://example.com"
              />
              <span className="form-hint">如果填写，会继续测试正文抽取 provider</span>
            </div>

            <div className="form-group">
              <label htmlFor="allowedDomains">允许域名（可选）</label>
              <textarea
                id="allowedDomains"
                value={allowedDomainsText}
                onChange={(e) => setAllowedDomainsText(e.target.value)}
                rows={2}
                placeholder="sec.gov, investor.example.com"
              />
              <span className="form-hint">逗号或换行分隔。用于验证 reliable-first / reliable-only 风格的域名白名单。</span>
            </div>

            <div className="form-group">
              <label htmlFor="blockedDomains">排除域名（可选）</label>
              <textarea
                id="blockedDomains"
                value={blockedDomainsText}
                onChange={(e) => setBlockedDomainsText(e.target.value)}
                rows={2}
                placeholder="medium.com, substack.com"
              />
              <span className="form-hint">逗号或换行分隔。用于排除营销站、聚合站或噪音来源。</span>
            </div>

            {searchTestResult && (
              <div className={`search-test-card ${searchTestResult.success ? "success" : "error"}`}>
                <div className="search-test-head">
                  {searchTestResult.success ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                  <strong>{searchTestResult.message}</strong>
                </div>
                <p>Source policy: {searchTestResult.source_policy}</p>
                <p>Providers: {searchTestResult.providers.join(", ") || "none"}</p>
                <p>Allowed domains: {searchTestResult.effective_allowed_domains.join(", ") || "none"}</p>
                <p>Blocked domains: {searchTestResult.effective_blocked_domains.join(", ") || "none"}</p>
                <p>结果数: {searchTestResult.result_count}</p>
                {searchTestResult.results[0] && (
                  <div className="search-test-snippet">
                    <strong>{searchTestResult.results[0].title}</strong>
                    <span>{searchTestResult.results[0].url}</span>
                    <p>{searchTestResult.results[0].snippet}</p>
                  </div>
                )}
                {searchTestResult.extracted_page && (
                  <div className="search-test-snippet">
                    <div className="search-test-inline">
                      <Globe size={14} />
                      <strong>{searchTestResult.extracted_page.title || "Extracted Page"}</strong>
                    </div>
                    <span>{searchTestResult.extracted_page.domain} / {searchTestResult.extracted_page.extraction_provider}</span>
                    <p>{searchTestResult.extracted_page.raw_text_preview}</p>
                  </div>
                )}
              </div>
            )}
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
            className="secondary"
            onClick={handleSearchTest}
            disabled={isTestingSearch || !searchQuery.trim()}
          >
            {isTestingSearch ? (
              <>
                <Loader2 size={16} className="spinner" />
                测试搜索中...
              </>
            ) : (
              <>
                <Search size={16} />
                测试搜索链路
              </>
            )}
          </button>
          <button
            className="primary"
            onClick={handlePrimarySave}
            disabled={isSaving || isApplyingPreset || !baseUrl || !model || !hasUsableApiKey}
          >
            {isSaving || isApplyingPreset ? (
              <>
                <Loader2 size={16} className="spinner" />
                {isApplyingPreset ? "应用中..." : "保存中..."}
              </>
            ) : (
              canUseStoredPresetKey && !apiKey.trim() ? "应用并生效" : "保存配置"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
