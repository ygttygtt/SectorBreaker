# Reliable Source Connector Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reliable-source registry and an end-to-end onboarding path so users can see which source packs are active, which API keys are needed, and whether reliable-source search/extraction is actually working before a research run starts.

**Architecture:** Keep external services behind provider interfaces. Treat reliable sources as governance metadata and connector descriptors, not as another generic search provider. The backend owns source-pack policy, connector status, and evidence classification; the frontend owns configuration visibility, key-entry guidance, and self-test actions.

**Tech Stack:** Python, FastAPI, Pydantic/dataclasses, pytest, React, TypeScript, Vitest, Testing Library.

---

## Scope Boundaries

This plan does implement:

- a `SourceRegistry` around built-in source packs;
- first built-in packs for China company/disclosure sources and technical frontier sources;
- backend status output that tells the frontend which connectors are usable, key-gated, search-domain-only, or manual-review-only;
- frontend configuration/onboarding UI for reliable sources;
- tests proving the user is not trapped in an invisible "missing API key" state.

This plan does not implement:

- scraping login-gated or CAPTCHA-protected platforms;
- real paid API calls to QCC, Tianyancha, CNINFO Data Service, or Tushare;
- a full custom crawler;
- database schema changes;
- export schema changes.

## Source Intake Rules

Use this order when adding or classifying a source:

1. `official_api`: GitHub, arXiv, Semantic Scholar, Stack Exchange, HN APIs, SEC, or other documented official APIs.
2. `commercial_api`: QCC, Tianyancha, CNINFO Data Service, licensed exchange/data feeds.
3. `library_adapter`: AKShare/Tushare-style adapters, always with provenance and lower authority than original disclosures.
4. `search_domain_pack`: authoritative public domains discovered through Tavily/Serper/Brave/Exa.
5. `extraction_fallback`: Firecrawl/Jina/HTTP/Apify fetches text from already-discovered public URLs.
6. `manual_review`: high-trust but hard-to-automate sources such as GSXT claims that may involve CAPTCHA or legal/process constraints.

## Files

Backend:

- Modify: `backend/app/providers/source_packs.py`
- Modify: `backend/app/providers/source_verification.py`
- Modify: `backend/app/providers/counterevidence.py`
- Modify: `backend/app/providers/factory.py`
- Modify: `backend/app/graph/workflow.py`
- Modify: `backend/app/api/app.py`
- Modify: `backend/app/providers/__init__.py`

Frontend:

- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/ConfigPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`

Tests and docs:

- Create: `tests/unit/test_source_registry.py`
- Modify: `tests/unit/test_source_verification_provider.py`
- Modify: `tests/unit/test_counterevidence_provider.py`
- Modify: `tests/unit/test_provider_factory.py`
- Modify: `tests/api/test_app.py`
- Modify: `docs/04-provider-interfaces.md`
- Modify: `docs/14-search-and-report-ingestion-design.md`
- Modify: `docs/15-real-search-provider-onboarding.md`
- Modify after implementation: `docs/10-current-status-and-handoff.md`
- Modify after implementation: `docs/11-tooling-handoff.md`

---

### Task 1: Source Registry Contract

**Files:**
- Modify: `backend/app/providers/source_packs.py`
- Create: `tests/unit/test_source_registry.py`

- [ ] **Step 1: Write failing registry tests**

Add tests proving the new registry can list source packs, report connector metadata, preserve existing reliable-domain behavior, and mark manual/commercial connectors separately.

```python
from backend.app.providers.source_packs import (
    SourceConnectorType,
    build_default_source_registry,
)


def test_registry_lists_china_company_pack_connectors() -> None:
    registry = build_default_source_registry()

    pack = registry.get_pack("company_china_pack")

    assert pack is not None
    connector_keys = {connector.key for connector in pack.connectors}
    assert {"cninfo_public", "sse_disclosure", "szse_disclosure", "gsxt_manual", "qcc_openapi", "tianyancha_openapi"}.issubset(connector_keys)
    assert registry.reliable_domains_for_market("china")
    assert "cninfo.com.cn" in registry.reliable_domains_for_market("china")


def test_registry_marks_manual_and_commercial_connectors() -> None:
    registry = build_default_source_registry()

    connectors = {connector.key: connector for connector in registry.connectors_for_market("china")}

    assert connectors["gsxt_manual"].connector_type == SourceConnectorType.MANUAL_REVIEW
    assert connectors["gsxt_manual"].requires_manual_review is True
    assert connectors["qcc_openapi"].connector_type == SourceConnectorType.COMMERCIAL_API
    assert connectors["qcc_openapi"].required_env_keys == ("QCC_API_KEY",)


def test_registry_lists_tech_frontier_official_apis() -> None:
    registry = build_default_source_registry()

    connectors = {connector.key: connector for connector in registry.connectors_for_pack("tech_frontier_pack")}

    assert connectors["github_api"].connector_type == SourceConnectorType.OFFICIAL_API
    assert connectors["github_api"].required_env_keys == ("GITHUB_TOKEN",)
    assert connectors["arxiv_api"].required_env_keys == ()
    assert connectors["stack_exchange_api"].setup_url == "https://api.stackexchange.com/docs"
```

- [ ] **Step 2: Run the tests and confirm RED**

Run:

```bash
python -m pytest tests/unit/test_source_registry.py -q
```

Expected: fail because `SourceConnectorType`, `build_default_source_registry`, and registry methods do not exist yet.

- [ ] **Step 3: Implement the registry**

Add these data structures while keeping the existing wrapper functions working:

```python
from dataclasses import dataclass, field
from enum import StrEnum


class SourceConnectorType(StrEnum):
    OFFICIAL_API = "official_api"
    COMMERCIAL_API = "commercial_api"
    LIBRARY_ADAPTER = "library_adapter"
    SEARCH_DOMAIN_PACK = "search_domain_pack"
    EXTRACTION_FALLBACK = "extraction_fallback"
    MANUAL_REVIEW = "manual_review"


@dataclass(frozen=True)
class SourceConnector:
    key: str
    display_name: str
    connector_type: SourceConnectorType
    source_type: SourceType
    trust_level: str
    domains: tuple[str, ...] = ()
    required_env_keys: tuple[str, ...] = ()
    setup_url: str | None = None
    can_support_facts: bool = True
    requires_manual_review: bool = False
    notes: str = ""


@dataclass(frozen=True)
class SourcePack:
    name: str
    display_name: str
    market_scopes: tuple[str, ...]
    reliable_rules: tuple[ReliableSourceRule, ...]
    connectors: tuple[SourceConnector, ...] = ()
    blocked_domains: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceRegistry:
    packs: tuple[SourcePack, ...] = field(default_factory=tuple)

    def get_pack(self, name: str) -> SourcePack | None:
        return next((pack for pack in self.packs if pack.name == name), None)

    def packs_for_market(self, market_scope: str | None) -> tuple[SourcePack, ...]:
        scope = market_scope or MarketScope.MIXED.value
        return tuple(pack for pack in self.packs if scope in pack.market_scopes)

    def connectors_for_pack(self, pack_name: str) -> tuple[SourceConnector, ...]:
        pack = self.get_pack(pack_name)
        return pack.connectors if pack else ()

    def connectors_for_market(self, market_scope: str | None) -> tuple[SourceConnector, ...]:
        connectors: list[SourceConnector] = []
        for pack in self.packs_for_market(market_scope):
            connectors.extend(pack.connectors)
        return tuple(connectors)

    def reliable_domains_for_market(self, market_scope: str | None) -> list[str]:
        domains: list[str] = []
        for pack in self.packs_for_market(market_scope):
            domains.extend(rule.domain for rule in pack.reliable_rules)
        return list(dict.fromkeys(domains))

    def blocked_domains_for_market(self, market_scope: str | None) -> list[str]:
        domains: list[str] = []
        for pack in self.packs_for_market(market_scope):
            domains.extend(pack.blocked_domains)
        return list(dict.fromkeys(domains))

    def match_reliable_rule(self, domain: str | None) -> ReliableSourceRule | None:
        if not domain:
            return None
        for pack in self.packs:
            for rule in pack.reliable_rules:
                if domain_matches(domain, rule.domain):
                    return rule
        return None
```

Add built-in connector descriptors for:

- `cninfo_public`, `sse_disclosure`, `szse_disclosure`, `bse_disclosure`, `gsxt_manual`, `qcc_openapi`, `tianyancha_openapi`, `akshare_adapter`, `tushare_api`;
- `github_api`, `arxiv_api`, `semantic_scholar_api`, `stack_exchange_api`, `hn_algolia_api`, `hn_firebase_api`, `papers_with_code`, `firecrawl_extraction`, `jina_reader_extraction`.

Keep these existing functions as wrappers:

```python
DEFAULT_SOURCE_REGISTRY = build_default_source_registry()


def packs_for_market(market_scope: str | None) -> tuple[SourcePack, ...]:
    return DEFAULT_SOURCE_REGISTRY.packs_for_market(market_scope)


def reliable_domains_for_market(market_scope: str | None) -> list[str]:
    return DEFAULT_SOURCE_REGISTRY.reliable_domains_for_market(market_scope)


def blocked_domains_for_market(market_scope: str | None) -> list[str]:
    return DEFAULT_SOURCE_REGISTRY.blocked_domains_for_market(market_scope)


def match_reliable_rule(domain: str | None) -> ReliableSourceRule | None:
    return DEFAULT_SOURCE_REGISTRY.match_reliable_rule(domain)
```

- [ ] **Step 4: Run source registry tests and existing verification tests**

Run:

```bash
python -m pytest tests/unit/test_source_registry.py tests/unit/test_source_verification_provider.py tests/unit/test_counterevidence_provider.py -q
```

Expected: all pass.

---

### Task 2: Registry-Backed Verification And Counterevidence

**Files:**
- Modify: `backend/app/providers/source_verification.py`
- Modify: `backend/app/providers/counterevidence.py`
- Modify: `backend/app/providers/factory.py`
- Modify: `backend/app/providers/__init__.py`
- Modify: `backend/app/graph/workflow.py`
- Modify: `tests/unit/test_source_verification_provider.py`
- Modify: `tests/unit/test_counterevidence_provider.py`
- Modify: `tests/unit/test_provider_factory.py`

- [ ] **Step 1: Write failing dependency-injection tests**

Add tests proving providers accept a custom registry:

```python
from backend.app.providers.source_packs import (
    ReliableSourceRule,
    SourcePack,
    SourceRegistry,
)
from backend.app.providers.source_verification import HeuristicSourceVerificationProvider
from backend.app.providers.counterevidence import HeuristicCounterevidenceProvider
from backend.app.schemas import SourcePolicy, SourceType


def test_source_verifier_uses_injected_registry() -> None:
    registry = SourceRegistry(packs=(
        SourcePack(
            name="custom_pack",
            display_name="Custom Pack",
            market_scopes=("custom",),
            reliable_rules=(ReliableSourceRule("trusted.example", SourceType.PUBLIC_DATABASE, "custom_public_database"),),
        ),
    ))
    provider = HeuristicSourceVerificationProvider(source_registry=registry)

    result = asyncio.run(provider.assess_source(
        url="https://trusted.example/data",
        title="Custom data",
        snippet="Official custom source.",
        extracted_text=None,
        source_policy=SourcePolicy.RELIABLE_ONLY.value,
    ))

    assert result.source_quality == "high"
    assert "custom_public_database" in (result.reliability_notes or "")


def test_counterevidence_provider_uses_injected_registry_domains() -> None:
    registry = SourceRegistry(packs=(
        SourcePack(
            name="custom_pack",
            display_name="Custom Pack",
            market_scopes=("custom",),
            reliable_rules=(ReliableSourceRule("trusted.example", SourceType.PUBLIC_DATABASE, "custom_public_database"),),
        ),
    ))
    provider = HeuristicCounterevidenceProvider(source_registry=registry)

    tasks = asyncio.run(provider.build_verification_tasks("CL-1", "增长很快", "custom"))

    assert "trusted.example" in (tasks[0].preferred_domains or [])
```

- [ ] **Step 2: Run and confirm RED**

Run:

```bash
python -m pytest tests/unit/test_source_verification_provider.py tests/unit/test_counterevidence_provider.py -q
```

Expected: fail because constructors do not accept `source_registry`.

- [ ] **Step 3: Implement provider injection**

Use constructor defaults:

```python
class HeuristicSourceVerificationProvider:
    def __init__(self, source_registry: SourceRegistry | None = None) -> None:
        self.source_registry = source_registry or DEFAULT_SOURCE_REGISTRY
```

```python
class HeuristicCounterevidenceProvider:
    def __init__(self, source_registry: SourceRegistry | None = None) -> None:
        self.source_registry = source_registry or DEFAULT_SOURCE_REGISTRY
```

Replace direct calls to module wrapper functions inside those classes with the injected registry.

- [ ] **Step 4: Add factory builder**

In `factory.py`:

```python
from backend.app.providers.source_packs import SourceRegistry, build_default_source_registry
from backend.app.providers.source_verification import HeuristicSourceVerificationProvider


def build_source_registry() -> SourceRegistry:
    return build_default_source_registry()


def build_source_verification_provider(
    source_registry: SourceRegistry | None = None,
) -> HeuristicSourceVerificationProvider:
    return HeuristicSourceVerificationProvider(source_registry=source_registry or build_source_registry())
```

Add a factory test:

```python
def test_provider_factory_builds_source_registry_and_verifier() -> None:
    registry = build_source_registry()
    verifier = build_source_verification_provider(source_registry=registry)

    assert registry.reliable_domains_for_market("china")
    assert verifier.source_registry is registry
```

- [ ] **Step 5: Share the registry in workflow**

In `workflow.py`, create one registry and use it for verifier/counterevidence:

```python
source_registry = build_source_registry()
source_verifier = HeuristicSourceVerificationProvider(source_registry=source_registry)
counterevidence_provider = HeuristicCounterevidenceProvider(source_registry=source_registry)
```

Keep `search_constraints_for_policy()` behavior unchanged for now by preserving wrapper functions in `source_packs.py`.

- [ ] **Step 6: Run provider tests**

Run:

```bash
python -m pytest tests/unit/test_source_registry.py tests/unit/test_source_verification_provider.py tests/unit/test_counterevidence_provider.py tests/unit/test_provider_factory.py -q
```

Expected: all pass.

---

### Task 3: Backend Source Connector Status API

**Files:**
- Modify: `backend/app/api/app.py`
- Modify: `tests/api/test_app.py`
- Modify: `frontend/src/api/client.ts` in Task 4

- [ ] **Step 1: Write failing API status test**

Add a test that fails until the source registry endpoint exists:

```python
def test_api_exposes_source_registry_status(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=_default_fake_llm(),
        )
    )

    response = client.get("/api/config/sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["packs"]
    pack_names = {pack["name"] for pack in payload["packs"]}
    assert {"company_china_pack", "tech_frontier_pack"}.issubset(pack_names)
    connectors = {
        connector["key"]: connector
        for pack in payload["packs"]
        for connector in pack["connectors"]
    }
    assert connectors["qcc_openapi"]["connector_type"] == "commercial_api"
    assert connectors["qcc_openapi"]["configured"] is False
    assert connectors["gsxt_manual"]["requires_manual_review"] is True
    assert connectors["github_api"]["required_env_keys"] == ["GITHUB_TOKEN"]
```

- [ ] **Step 2: Run and confirm RED**

Run:

```bash
python -m pytest tests/api/test_app.py::test_api_exposes_source_registry_status -q
```

Expected: fail with 404.

- [ ] **Step 3: Add response models**

In `app.py`:

```python
class SourceConnectorStatus(BaseModel):
    key: str
    display_name: str
    connector_type: str
    source_type: str
    trust_level: str
    domains: list[str] = Field(default_factory=list)
    required_env_keys: list[str] = Field(default_factory=list)
    configured: bool = False
    setup_url: str | None = None
    can_support_facts: bool = True
    requires_manual_review: bool = False
    notes: str = ""


class SourcePackStatus(BaseModel):
    name: str
    display_name: str
    market_scopes: list[str]
    reliable_domains: list[str]
    blocked_domains: list[str]
    connectors: list[SourceConnectorStatus] = Field(default_factory=list)


class SourceRegistryStatus(BaseModel):
    packs: list[SourcePackStatus] = Field(default_factory=list)
    configured_connector_count: int = 0
    recommended_next_action: str = ""
```

- [ ] **Step 4: Implement `GET /api/config/sources`**

Rules:

- `configured` is true only when all `required_env_keys` are present in `os.environ` or runtime config has an equivalent key already supported by the app.
- `search_domain_pack`, `manual_review`, and no-key official APIs can be shown as available without making them look like paid API connectors.
- no secret values are returned.

Implementation sketch:

```python
def _connector_configured(connector: SourceConnector, active_search_config: SearchConfig) -> bool:
    runtime_key_presence = {
        "TAVILY_API_KEY": bool(active_search_config.tavily_api_key),
        "SERPER_API_KEY": bool(active_search_config.serper_api_key),
        "BRAVE_API_KEY": bool(active_search_config.brave_api_key),
        "EXA_API_KEY": bool(active_search_config.exa_api_key),
        "FIRECRAWL_API_KEY": bool(active_search_config.firecrawl_api_key),
    }
    if not connector.required_env_keys:
        return True
    return all(runtime_key_presence.get(key, bool(os.getenv(key))) for key in connector.required_env_keys)
```

Endpoint:

```python
@app.get("/api/config/sources")
def get_source_registry_status():
    packs = []
    configured_count = 0
    for pack in source_registry.packs:
        connectors = []
        for connector in pack.connectors:
            configured = _connector_configured(connector, active_search_config)
            configured_count += int(configured)
            connectors.append(SourceConnectorStatus(
                key=connector.key,
                display_name=connector.display_name,
                connector_type=connector.connector_type.value,
                source_type=connector.source_type.value,
                trust_level=connector.trust_level,
                domains=list(connector.domains),
                required_env_keys=list(connector.required_env_keys),
                configured=configured,
                setup_url=connector.setup_url,
                can_support_facts=connector.can_support_facts,
                requires_manual_review=connector.requires_manual_review,
                notes=connector.notes,
            ))
        packs.append(SourcePackStatus(
            name=pack.name,
            display_name=pack.display_name,
            market_scopes=list(pack.market_scopes),
            reliable_domains=[rule.domain for rule in pack.reliable_rules],
            blocked_domains=list(pack.blocked_domains),
            connectors=connectors,
        ))
    return SourceRegistryStatus(
        packs=packs,
        configured_connector_count=configured_count,
        recommended_next_action=(
            "先配置 Tavily、Serper、Brave 或 Exa 任意一个搜索 Key，再用可靠信源自检验证域名约束。"
            if active_search_provider is None
            else "搜索已可用；可继续验证 reliable_only 策略下的权威域名结果。"
        ),
    ).model_dump(mode="json")
```

- [ ] **Step 5: Run API tests**

Run:

```bash
python -m pytest tests/api/test_app.py::test_api_exposes_source_registry_status tests/api/test_app.py::test_api_exposes_search_config_status tests/api/test_app.py::test_api_updates_search_runtime_config -q
```

Expected: all pass.

---

### Task 4: Frontend API Client Types

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Add TypeScript models**

Add:

```ts
export interface SourceConnectorStatus {
  key: string;
  display_name: string;
  connector_type: string;
  source_type: string;
  trust_level: string;
  domains: string[];
  required_env_keys: string[];
  configured: boolean;
  setup_url?: string | null;
  can_support_facts: boolean;
  requires_manual_review: boolean;
  notes: string;
}

export interface SourcePackStatus {
  name: string;
  display_name: string;
  market_scopes: string[];
  reliable_domains: string[];
  blocked_domains: string[];
  connectors: SourceConnectorStatus[];
}

export interface SourceRegistryStatus {
  packs: SourcePackStatus[];
  configured_connector_count: number;
  recommended_next_action: string;
}
```

- [ ] **Step 2: Add client method**

```ts
getSourceRegistryStatus() {
  return requestJson<SourceRegistryStatus>("/api/config/sources");
},
```

- [ ] **Step 3: No separate test yet**

Frontend behavior tests are added in Task 6 so the client method is exercised through the real panel.

---

### Task 5: Frontend Source Onboarding UI

**Files:**
- Modify: `frontend/src/components/ConfigPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add source registry state to `ConfigPanel`**

```ts
const [sourceRegistryStatus, setSourceRegistryStatus] = useState<SourceRegistryStatus | null>(null);
const [sourceRegistryError, setSourceRegistryError] = useState<string | null>(null);

async function fetchSourceRegistryStatus() {
  try {
    setSourceRegistryError(null);
    setSourceRegistryStatus(await api.getSourceRegistryStatus());
  } catch (err) {
    setSourceRegistryError(err instanceof Error ? err.message : "可靠信源状态读取失败");
  }
}
```

Call it when the panel opens and after saving search config:

```ts
if (isOpen) {
  fetchConfigStatus();
  fetchSearchStatus();
  fetchSourceRegistryStatus();
}
```

```ts
await fetchSearchStatus();
await fetchSourceRegistryStatus();
```

- [ ] **Step 2: Add a reliable-source section**

Add it after "搜索与抽取配置" status and before raw key inputs:

```tsx
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
```

User-facing copy must make these points clear:

- "搜索 Key" unlocks domain-pack discovery.
- QCC/Tianyancha/CNINFO Data Service are paid/commercial connectors and are not required for the first MVP.
- GSXT is high-trust but manual-review/CAPTCHA-risk, not a crawler target.
- Jina/Firecrawl are extraction fallback, not fact sources.

- [ ] **Step 3: Add no-key recovery path on landing**

In `App.tsx`, when `searchConfigured` is false, change the warning to include a button-like action that opens settings:

```tsx
{!searchConfigured && (
  <button className="landing-warning" onClick={onOpenSettings} type="button">
    <AlertTriangle size={16} />
    搜索未配置，点击接入可靠信源和搜索 Key
  </button>
)}
```

Keep the product runnable without search, but make the degradation explicit.

- [ ] **Step 4: Add minimal CSS**

Use existing restrained design tokens:

```css
.source-onboarding { display: grid; gap: 10px; }
.source-onboarding-note { padding: 9px 10px; border: 1px solid var(--soft-line); border-radius: 7px; color: #344054; background: #f8fafc; font-size: 13px; }
.source-pack-card { display: grid; gap: 8px; padding: 10px 12px; border: 1px solid var(--soft-line); border-radius: 7px; background: #fff; }
.source-pack-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.source-pack-head strong { font-size: 13px; }
.source-pack-head span, .source-domain-line { color: var(--muted); font-size: 12px; }
.source-connector-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.source-connector-chip { display: grid; gap: 3px; padding: 8px; border-radius: 6px; border: 1px solid var(--soft-line); font-size: 12px; }
.source-connector-chip.is-ready { background: #f0fdfa; border-color: rgba(16, 185, 129, .35); }
.source-connector-chip.is-missing { background: #fff8f8; border-color: rgba(239, 68, 68, .25); }
.source-connector-chip strong, .source-connector-chip span, .source-connector-chip em { overflow-wrap: anywhere; }
.source-connector-chip em { color: var(--muted); font-style: normal; }
.source-connector-chip a { color: var(--green); font-weight: 700; text-decoration: none; }
@media (max-width: 760px) { .source-connector-grid { grid-template-columns: 1fr; } }
```

- [ ] **Step 5: Build once for TypeScript/CSS errors**

Run:

```bash
cd frontend
npm run build
```

Expected: build passes.

---

### Task 6: Frontend Tests For No-Key Onboarding

**Files:**
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Extend API mock**

Add:

```ts
const mockGetSourceRegistryStatus = vi.fn().mockResolvedValue({
  packs: [
    {
      name: "company_china_pack",
      display_name: "中国企业与披露信源",
      market_scopes: ["china", "mixed"],
      reliable_domains: ["cninfo.com.cn", "sse.com.cn", "szse.cn", "gsxt.gov.cn"],
      blocked_domains: ["medium.com", "substack.com"],
      connectors: [
        {
          key: "cninfo_public",
          display_name: "巨潮资讯公开披露",
          connector_type: "search_domain_pack",
          source_type: "company_disclosure",
          trust_level: "high",
          domains: ["cninfo.com.cn"],
          required_env_keys: [],
          configured: true,
          can_support_facts: true,
          requires_manual_review: false,
          notes: "通过搜索 provider 发现公开披露 URL。",
        },
        {
          key: "qcc_openapi",
          display_name: "企查查开放平台",
          connector_type: "commercial_api",
          source_type: "public_database",
          trust_level: "high",
          domains: ["openapi.qcc.com"],
          required_env_keys: ["QCC_API_KEY"],
          configured: false,
          setup_url: "https://openapi.qcc.com/dataApi",
          can_support_facts: true,
          requires_manual_review: false,
          notes: "付费商业 API，MVP 可不配置。",
        },
      ],
    },
  ],
  configured_connector_count: 1,
  recommended_next_action: "先配置 Tavily、Serper、Brave 或 Exa 任意一个搜索 Key，再用可靠信源自检验证域名约束。",
});
```

Expose it in the mocked `api` object:

```ts
getSourceRegistryStatus: mockGetSourceRegistryStatus,
```

- [ ] **Step 2: Add test for visible onboarding**

```ts
test("config panel shows reliable source onboarding and key requirements", async () => {
  render(<App />);

  fireEvent.click(screen.getByRole("button", { name: /LLM 设置/ }));

  expect(await screen.findByText("可靠信源接入")).toBeInTheDocument();
  expect(screen.getByText("中国企业与披露信源")).toBeInTheDocument();
  expect(screen.getByText("巨潮资讯公开披露")).toBeInTheDocument();
  expect(screen.getByText("企查查开放平台")).toBeInTheDocument();
  expect(screen.getByText(/需要 QCC_API_KEY/)).toBeInTheDocument();
  expect(screen.getByText(/先配置 Tavily/)).toBeInTheDocument();
});
```

- [ ] **Step 3: Add test for no-key landing recovery**

```ts
test("landing search warning opens settings when search key is missing", async () => {
  mockGetSearchConfig.mockResolvedValueOnce({
    configured: false,
    providers: [],
    requested_provider_mode: "auto",
    extraction_providers: ["http"],
    requested_extraction_provider: "http",
    missing_configuration: ["tavily_api_key"],
    diagnostics: ["至少需要配置 Tavily、Serper、Brave、Exa 四者之一的 API Key，开放网络搜索才会启用。"],
    status_message: "搜索未配置：请至少填写 Tavily、Serper、Brave、Exa 四者之一的 API Key。",
  });

  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: /搜索未配置/ }));

  expect(await screen.findByText("可靠信源接入")).toBeInTheDocument();
});
```

- [ ] **Step 4: Run frontend tests**

Run:

```bash
cd frontend
npm test -- --run
```

Expected: all tests pass.

---

### Task 7: Search Self-Test Uses Source Pack Defaults

**Files:**
- Modify: `backend/app/api/app.py`
- Modify: `frontend/src/components/ConfigPanel.tsx`
- Modify: `tests/api/test_app.py`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Add API assertion for source-pack constraints**

Extend existing `/api/config/search/test` tests so `reliable_only` with `market_scope=china` returns source-pack-derived domains:

```python
assert "cninfo.com.cn" in response.json()["effective_allowed_domains"]
assert "sse.com.cn" in response.json()["effective_allowed_domains"]
assert "szse.cn" in response.json()["effective_allowed_domains"]
```

- [ ] **Step 2: Add frontend default test values**

In `ConfigPanel`, when source policy changes to `reliable_only`, set a clear default query if the field is still the generic default:

```ts
onChange={(e) => {
  const value = e.target.value;
  setSearchSourcePolicy(value);
  if (value === "reliable_only" && searchQuery === "AI agent market map") {
    setSearchQuery("AI agent market disclosure official data");
  }
}}
```

Do not auto-fill fake API keys.

- [ ] **Step 3: Keep manual domain override**

The user can still fill `allowed_domains`; if they do, API behavior remains:

```python
effective_allowed_domains = payload.allowed_domains or policy_allowed_domains
```

- [ ] **Step 4: Run focused API and frontend tests**

Run:

```bash
python -m pytest tests/api/test_app.py::test_api_search_test_applies_source_policy_constraints -q
cd frontend
npm test -- --run
```

Expected: pass.

---

### Task 8: Documentation And User-Facing Onboarding

**Files:**
- Modify: `docs/04-provider-interfaces.md`
- Modify: `docs/14-search-and-report-ingestion-design.md`
- Modify: `docs/15-real-search-provider-onboarding.md`
- Modify after implementation: `docs/10-current-status-and-handoff.md`
- Modify after implementation: `docs/11-tooling-handoff.md`

- [ ] **Step 1: Document `SourceRegistry`**

Add to `docs/04-provider-interfaces.md`:

```markdown
## SourceRegistry

`SourceRegistry` is local evidence-governance metadata, not a search provider.
It declares source packs, connector types, reliable domains, blocked domains,
API-key requirements, and manual-review boundaries.

Connector types:

- `official_api`
- `commercial_api`
- `library_adapter`
- `search_domain_pack`
- `extraction_fallback`
- `manual_review`
```

- [ ] **Step 2: Update ingestion design**

Add that source packs feed:

- search domain constraints;
- source assessment;
- counterevidence preferred domains;
- frontend onboarding and status display.

- [ ] **Step 3: Update real onboarding doc**

Add the short user path:

```markdown
1. Open `LLM 设置`.
2. Read `可靠信源接入`.
3. For the first MVP, fill one search key: Tavily, Serper, Brave, or Exa.
4. Leave QCC/Tianyancha/CNINFO Data Service empty unless you have paid credentials.
5. Use `http` or `jina` extraction first.
6. Click `测试搜索链路` with `reliable_only`.
7. Confirm `Allowed domains` includes official/disclosure domains and `结果数 > 0`.
```

- [ ] **Step 4: Update handoff docs after verification**

Record:

- source registry implemented;
- frontend now exposes reliable-source onboarding;
- commercial connectors are metadata only until credentials/paid APIs are added;
- remaining work: real commercial connector providers.

---

### Task 9: Verification

**Files:**
- No new files unless failures require fixes.

- [ ] **Step 1: Backend focused tests**

Run:

```bash
python -m pytest tests/unit/test_source_registry.py tests/unit/test_source_verification_provider.py tests/unit/test_counterevidence_provider.py tests/unit/test_provider_factory.py -q
```

Expected: pass.

- [ ] **Step 2: API focused tests**

Run:

```bash
python -m pytest tests/api/test_app.py::test_api_exposes_source_registry_status tests/api/test_app.py::test_api_exposes_search_config_status tests/api/test_app.py::test_api_search_test_applies_source_policy_constraints tests/api/test_app.py::test_api_updates_search_runtime_config -q
```

Expected: pass.

- [ ] **Step 3: Graph reliability tests**

Run:

```bash
python -m pytest tests/graph/test_research_workflow.py tests/unit/test_workflow_counterevidence.py -q
```

Expected: pass.

- [ ] **Step 4: Frontend tests and build**

Run:

```bash
cd frontend
npm test -- --run
npm run build
npm audit --audit-level=high
```

Expected: tests pass, build passes, audit reports 0 high vulnerabilities.

- [ ] **Step 5: Diff and secret check**

Run:

```bash
git diff --check
git diff --stat
rg -n "sk-[A-Za-z0-9]|tvly-[A-Za-z0-9]|QCC_API_KEY=.*\\S|TIANYANCHA_API_KEY=.*\\S|GITHUB_TOKEN=.*\\S" .
```

Expected:

- no whitespace errors;
- diff only touches planned files;
- no real API secrets committed.

---

### Task 10: Manual Run Path

**Files:**
- No edits.

- [ ] **Step 1: Start backend**

Run:

```bash
uvicorn backend.app.api.app:app --host 127.0.0.1 --port 8000 --reload
```

- [ ] **Step 2: Start frontend**

Run:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 3000
```

- [ ] **Step 3: Verify UI onboarding**

Open:

```text
http://127.0.0.1:3000
```

Check:

- landing page shows clickable search/key warning when search is unconfigured;
- clicking it opens `LLM 设置`;
- `可靠信源接入` lists China company/disclosure and tech frontier packs;
- QCC/Tianyancha show as paid/commercial and not required for MVP;
- GSXT shows as manual-review, not crawler;
- entering one search key enables search status;
- `测试搜索链路` shows effective allowed/blocked domains and first result.

- [ ] **Step 4: Real-key smoke path**

If at least one real search key is available:

```bash
python run_search_smoke_test.py
```

Expected:

- `result_count > 0`;
- `first_result_source_quality` is printed;
- reliable-only with China market shows official/disclosure domains in the request path.

---

## Commit

After all verification passes:

```bash
git add backend frontend tests docs
git commit -m "完善可靠信源接入计划与前端配置闭环"
git push origin main && git push gitee main
```

If this plan is implemented through multiple commits, use Chinese commit messages and push both remotes after the final verified commit on `main`.
