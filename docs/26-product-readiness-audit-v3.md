# Product Readiness Audit V3

审计对象：当前 `main`（`d6995db`）及其生产 API/UI 路径。

结论先行：当前项目是“可运行的 V3 知识库工作台原型”，还不是可以对外承诺“信源接入真实、研究结果可靠”的产品。设置页里确实存在若干已经接到 Provider 的能力，但也存在几个会让用户误判能力边界的断点。

## 严重问题

### P0-1 生产 Agent 没有执行正文抽取

`ContentExtractionProvider` 只在 `/api/config/search/test` 和 CLI smoke 中调用。生产入口 `run_v2_agent_kernel_pipeline` 创建的 `KernelRuntimeContext` 没有正文抽取 Provider，`search_web` 只把搜索结果的 title/snippet 写入 Evidence。

影响：配置 Firecrawl/Jina 后，Agent 研究仍只使用搜索摘要；“搜索 + 抽取”在设置页可见，但生产知识产物没有消费正文。

验收要求：一次真实 Agent run 的 Evidence 必须出现 `extraction_provider`、正文 `raw_excerpt`，并且本地检索能够命中正文而不是只有 snippet。

### P0-2 启发式来源评估会把域名高可信误当成事实 verified

`HeuristicSourceVerificationProvider` 根据 source pack 域名即可将 `recommended_verification_status` 设为 `verified`。域名只能说明来源类别/可信度，不能证明某一条 claim 已被核验。

影响：设置 `reliable_only` 后，用户可能看到“verified”而误以为事实已经完成 corroboration；这违背 evidence-first 和反证要求。

验收要求：启发式 Provider 最多返回 `partially_verified`；只有独立 corroboration/counterevidence 流程才能将 claim/evidence 提升为 `verified`。

### P0-3 真实验收脚本仍检查已退休的 V1 产物

`run_real_search_acceptance.py` 要求 `00-领域总览.md`、`01-入门路线.md` 等 V1 固定文件，而 V3 的 Agent Kernel 已改为自适应 artifact 路径。该脚本不能作为当前产品的真实可用性门禁。

验收要求：脚本改为检查 V3 active artifacts、Evidence、`.sectorbreaker/` 状态包、导出 manifest，以及至少一个正文抽取字段。

## P1 问题

- 搜索配置页保存时把空 API key 直接覆盖持久化 key；用户只改 provider mode 就可能清空原有配置。
- `delegate_specialists` 会并发调用 LLM，但 Specialist 的 `recommended_tool_calls` 只回传给 Master，未在 Specialist 自己的预算内执行；这是真实的“动态委派 + typed result”，不是完整的嵌套多 Agent ReAct。
- source registry 中的官方 API、商业 API、库适配器多数仍是目录项或 roadmap；当前只能通过 SearchProvider 的域名过滤使用，不能宣称已经拥有对应 API connector。
- `/api/config/search/test` 对 `user_materials_only` 没有硬阻断，测试入口可能绕过项目运行时的联网策略。
- HTTP/Firecrawl/Jina 抽取链路尚未统一做 SSRF/private-network URL 防护。

## P2 问题

- Firecrawl map/crawl/batch 没有接入 Agent 工具；当前只实现搜索和单 URL 抽取。
- SearXNG、Crawl4AI、Crawlee、Apify 仍是调研结论，不是生产 Provider。
- 没有真实 Provider 的可重复 contract test matrix 和带成本/延迟/失败率的运行指标。

## 已被证明为真实的能力

- Tavily、Serper、Brave、Exa、Firecrawl SearchProvider 有真实 HTTP 实现；`multi` 会并发请求并公平合并。
- HTTP、Firecrawl、Jina Reader 有真实正文抽取实现，但在本审计时尚未接入生产 Agent 搜索工具。
- SQLite evidence/artifact/revision/ChangeSet、active-only export、local FastEmbed Hybrid RAG、版本隔离检查均有自动化测试。
- Master Agent、四类 typed Specialist、角色 allowlist、禁止 Specialist 直接 apply ChangeSet 的边界是真实存在的。

## 修复顺序

1. 先修 P0-1、P0-2、P0-3，并分别提交。
2. 修复搜索密钥保存和 user-materials-only 测试策略，提交。
3. 修复 Specialist 预算/结果晋升或明确收缩 UI 宣称，提交。
4. 增加真实 Provider contract matrix、V3 acceptance 和 SSRF 防护。

本报告不把“接口存在”“设置项存在”“单元测试使用 fake provider”当作真实接入证据。
