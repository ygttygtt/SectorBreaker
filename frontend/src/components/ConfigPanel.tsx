import { useState, useEffect } from "react";
import { Settings, Eye, EyeOff, Loader2, CheckCircle2, XCircle, Search, Globe, ShieldCheck } from "lucide-react";
import { api, type SearchConfigStatus, type SearchTestResult, type SourceRegistryStatus } from "../api/client";

interface ConfigPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (message: string) => void;
  onError: (message: string) => void;
}

export function ConfigPanel({ isOpen, onClose, onSuccess, onError }: ConfigPanelProps) {
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [configStatus, setConfigStatus] = useState<{ configured: boolean; base_url?: string; model?: string } | null>(null);
  const [searchStatus, setSearchStatus] = useState<SearchConfigStatus | null>(null);
  const [searchQuery, setSearchQuery] = useState("AI agent market map");
  const [extractUrl, setExtractUrl] = useState("https://example.com");
  const [searchSourcePolicy, setSearchSourcePolicy] = useState("open_web");
  const [allowedDomainsText, setAllowedDomainsText] = useState("");
  const [blockedDomainsText, setBlockedDomainsText] = useState("");
  const [isTestingSearch, setIsTestingSearch] = useState(false);
  const [searchTestResult, setSearchTestResult] = useState<SearchTestResult | null>(null);
  const [isSavingSearch, setIsSavingSearch] = useState(false);
  const [tavilyApiKey, setTavilyApiKey] = useState("");
  const [serperApiKey, setSerperApiKey] = useState("");
  const [braveApiKey, setBraveApiKey] = useState("");
  const [exaApiKey, setExaApiKey] = useState("");
  const [searchProviderMode, setSearchProviderMode] = useState("auto");
  const [contentExtractionProvider, setContentExtractionProvider] = useState("http");
  const [firecrawlApiKey, setFirecrawlApiKey] = useState("");
  const [jinaReaderEndpointPrefix, setJinaReaderEndpointPrefix] = useState("https://r.jina.ai/http://");
  const [sourceRegistryStatus, setSourceRegistryStatus] = useState<SourceRegistryStatus | null>(null);
  const [sourceRegistryError, setSourceRegistryError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      fetchConfigStatus();
      fetchSearchStatus();
      fetchSourceRegistryStatus();
    }
  }, [isOpen]);

  async function fetchConfigStatus() {
    try {
      const status = await api.getLLMConfig();
      setConfigStatus(status);
      if (status.configured) {
        setBaseUrl(status.base_url || "");
        setModel(status.model || "");
      }
    } catch (err) {
      console.error("Failed to fetch config status:", err);
    }
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
        content_extraction_provider: contentExtractionProvider,
        firecrawl_api_key: firecrawlApiKey || undefined,
        firecrawl_endpoint: "https://api.firecrawl.dev/v1/scrape",
        jina_reader_endpoint_prefix: jinaReaderEndpointPrefix || undefined,
      });
      await fetchSearchStatus();
      await fetchSourceRegistryStatus();
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

          <div className="config-section">
            <div className="config-section-title">
              <Settings size={16} />
              <span>LLM 配置</span>
            </div>

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
                当前请求的搜索模式: {searchStatus.requested_provider_mode || "auto"}；
                当前请求的抽取 provider: {searchStatus.requested_extraction_provider}
                {searchStatus.extraction_provider ? `，实际使用: ${searchStatus.extraction_provider}` : ""}
              </div>
            )}

            <div className="form-group">
              <label htmlFor="searchProviderMode">搜索 Provider 模式</label>
              <select
                id="searchProviderMode"
                value={searchProviderMode}
                onChange={(e) => setSearchProviderMode(e.target.value)}
              >
                <option value="auto">auto（自动：单个直连，多 key 聚合）</option>
                <option value="multi">multi（强制聚合）</option>
                <option value="tavily">tavily</option>
                <option value="serper">serper</option>
                <option value="brave">brave</option>
                <option value="exa">exa</option>
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="tavilyApiKey">Tavily API Key</label>
              <input
                id="tavilyApiKey"
                type="password"
                value={tavilyApiKey}
                onChange={(e) => setTavilyApiKey(e.target.value)}
                placeholder="tvly-..."
              />
            </div>

            <div className="form-group">
              <label htmlFor="serperApiKey">Serper API Key</label>
              <input
                id="serperApiKey"
                type="password"
                value={serperApiKey}
                onChange={(e) => setSerperApiKey(e.target.value)}
                placeholder="serper key"
              />
            </div>

            <div className="form-group">
              <label htmlFor="braveApiKey">Brave API Key</label>
              <input
                id="braveApiKey"
                type="password"
                value={braveApiKey}
                onChange={(e) => setBraveApiKey(e.target.value)}
                placeholder="brave key"
              />
            </div>

            <div className="form-group">
              <label htmlFor="exaApiKey">Exa API Key</label>
              <input
                id="exaApiKey"
                type="password"
                value={exaApiKey}
                onChange={(e) => setExaApiKey(e.target.value)}
                placeholder="exa key"
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

            {contentExtractionProvider === "firecrawl" && (
              <div className="form-group">
                <label htmlFor="firecrawlApiKey">Firecrawl API Key</label>
                <input
                  id="firecrawlApiKey"
                  type="password"
                  value={firecrawlApiKey}
                  onChange={(e) => setFirecrawlApiKey(e.target.value)}
                  placeholder="fc-..."
                />
              </div>
            )}

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
                    <div className="source-connector-grid">
                      {pack.connectors.map((connector) => (
                        <div className={`source-connector-chip ${connector.configured ? "is-ready" : "is-missing"}`} key={connector.key}>
                          <strong>{connector.display_name}</strong>
                          <span>{connector.connector_type}</span>
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
