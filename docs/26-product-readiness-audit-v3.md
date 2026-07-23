# Product Readiness Audit V3

审计对象：`d6995db` 之后的生产 API/UI 路径，并由“用户可用性审计”和“架构反方审判”两条独立检查交叉验证。

结论先行：当前项目是“可运行的 V3 知识库工作台原型”，还不是可以对外承诺“可恢复、信源接入真实、研究结果可靠”的产品。设置页里确实存在若干已经接到 Provider 的能力，但也存在会让用户误判能力边界或直接卡死流程的断点。

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

### P0-4 人在回路的“继续研究”是断路

前端真实调用 `POST /api/runs/{run_id}/resume`，后端却没有该路由。Kernel 可以进入 `waiting_for_human`，SSE 也声称等待 resume，但 `/inputs` 只是写入 `user_inputs` 表；生产代码没有读取或消费这些输入。

影响：Agent 一旦执行 `ask_user`，或需要用户审查后继续，按钮会收到 404；即使输入已保存，也不会进入后续 State。该能力不是“不够成熟”，而是当前不可用。

验收要求：定义 typed resume payload；只允许恢复 waiting run；把用户反馈持久化并注入恢复后的 Agent State/ContextPack；通过真实 UI client -> API -> Kernel consumption 测试。

### P0-5 专用信源包没有成为项目或 Agent 的持久约束

设置页的“载入此信源包自检”只会改写自检表单中的 query/domains/policy，不保存到项目。生产 Agent 只有在 LLM 主动生成 `preferred_domains` 时才会使用域名过滤。因此专用网站能通过一次自检，并不表示后续研究会主动使用它。

影响：用户选择、查看或测试专用信源包后，真实 run 仍可能完全不访问这些站点。

验收要求：项目保存 typed source preferences/source-pack ids；Agent ContextPack 明确携带并强制应用这些约束；运行事件和 Evidence 记录最终使用的 domain policy。

## P1 问题

- 搜索配置页保存时把空 API key 直接覆盖持久化 key；用户只改 provider mode 就可能清空原有配置。
- `delegate_specialists` 会并发调用 LLM，但 Specialist 的 `recommended_tool_calls` 只回传给 Master，未在 Specialist 自己的预算内执行；这是真实的“动态委派 + typed result”，不是完整的嵌套多 Agent ReAct。
- source registry 中的官方 API、商业 API、库适配器多数仍是目录项或 roadmap；当前只能通过 SearchProvider 的域名过滤使用，不能宣称已经拥有对应 API connector。
- `/api/config/search/test` 对 `user_materials_only` 没有硬阻断，测试入口可能绕过项目运行时的联网策略。
- HTTP/Firecrawl/Jina 抽取链路尚未统一做 SSRF/private-network URL 防护。
- `finish` 只要求 State 中存在任意 artifact；已有历史产物的 maintenance/continuation run 可以在本轮零新产物、零 ChangeSet、任务未推进时被标记 completed。
- checkpoint 和 artifact checkpoint 的持久化异常被静默吞掉；运行可能报告 completed，但重启后没有可恢复状态。
- 当前 SQLite 中存在 7 个从 2026-07-06/07 起仍为 `running` 的历史 run。启动过程没有 stale-run reconciliation，SSE 超时结束也不更新状态，前端会长期把孤儿运行当作仍在执行。
- Master 可以直接提交任意 `verification_status`；verified claim 的门禁只检查 evidence id 非空，不检查 Evidence 是否存在、正文是否抽取、是否有独立佐证或反证。
- artifact review 主要检查长度、标题和 `EV-` 字样，不能证明引用真实存在或支持正文结论。

## P2 问题

- Firecrawl map/crawl/batch 没有接入 Agent 工具；当前只实现搜索和单 URL 抽取。
- SearXNG、Crawl4AI、Crawlee、Apify 仍是调研结论，不是生产 Provider。
- 没有真实 Provider 的可重复 contract test matrix 和带成本/延迟/失败率的运行指标。
- Serper/Brave 对多个域名直接拼接多个 `site:` 条件，可能被搜索端按 AND 解释而返回空结果；需要按 Provider 语义分批或显式 OR。
- runtime config 以明文 JSON 保存 API key，缺少原子写入、文件权限收紧和损坏恢复策略。

## 已被证明为真实的能力

- Tavily、Serper、Brave、Exa、Firecrawl SearchProvider 有真实 HTTP 实现；`multi` 会并发请求并公平合并。
- HTTP、Firecrawl、Jina Reader 有真实正文抽取实现，但在本审计时尚未接入生产 Agent 搜索工具。
- SQLite evidence/artifact/revision/ChangeSet、active-only export、local FastEmbed Hybrid RAG、版本隔离检查均有自动化测试。
- Master Agent、四类 typed Specialist、角色 allowlist、禁止 Specialist 直接 apply ChangeSet 的边界是真实存在的。

## 当前机器上的真实配置

- Tavily 已配置并真实返回结果；HTTP extraction 自检真实成功。
- Firecrawl、Serper、Brave、Exa 当前均未配置，因此不能在这台机器上宣称可用。
- 自检链路的 source quality 仍是 `unknown/unverified`，且自检结果不等于 Agent 生产链路已经消费抽取正文。

## 修复顺序

1. 修复人在回路 resume，并验证用户反馈被 Agent 消费。
2. 把正文抽取/来源评估接入生产 Agent，并禁止启发式 verified。
3. 让专用信源偏好成为项目级 typed policy，而非一次性自检状态。
4. 修复搜索密钥保存、user-materials-only 自检策略和 connector 状态文案。
5. 收紧完成条件、Evidence/ChangeSet/review 门禁和 stale-run 恢复语义。
6. 重写 V3 真实验收，随后再推进 Specialist 独立预算工具循环和 SSRF 防护。

本报告不把“接口存在”“设置项存在”“单元测试使用 fake provider”当作真实接入证据。

## 本轮已修复

- P0-1：正文抽取 Provider 已进入生产 Agent `search_web`，Evidence 保存正文、Provider、元数据和抽取时间；前三个 URL 有单条失败隔离。
- P0-2：启发式来源评估最高为 `partially_verified`，并新增本地域名策略后置过滤。
- P0-4：新增 typed `/api/runs/{run_id}/resume`；只恢复 waiting run，反馈会进入 State/ContextPack，assistant brief 会作为低可信文档内化。
- 搜索配置：空白字段不再清除已存 Key；状态只返回非敏感的 Provider key-presence；`user_materials_only`、零结果和不可读抽取不再显示成功。
- 信源目录：domain pack 改为 `available_via_domain_filter`，不再计作已配置直连；未选中的抽取适配器也不再显示 ready。
- 假完成/恢复：历史 artifact 不再满足本轮 finish；artifact 和 final checkpoint 写入失败会使 run 失败，不再静默报告 completed。
- 人审闭环：Agent 创建的 ChangeSet 记录 `origin_run_id`，应用后的 revision 保留该归属；V3 真实验收可 approve/apply 后恢复同一 run。

这些修复同时有 fake Provider 回归测试和下述真实 Tavily + HTTP extraction 生产验收。

- 项目级 source pack/custom domain policy 已持久化，`prefer` fallback 和
  `require` hard allowlist 会进入 Agent State、运行诊断和 Evidence provenance。
- 搜索预算按真实 Provider fan-out 计费，抽取另有硬预算；同 run 恢复不会
  重置消费计数，聚合失败会保守扣除已保留额度。
- URL 抽取已拒绝私网/保留地址并逐跳校验 HTTP redirect；runtime config
  使用原子替换、备份恢复和尽力 owner-only 权限。
- stale run 已有 owner lease、heartbeat、`interrupted`/orphaned 区分和
  lineage child recovery；waiting 事件、snapshot、SSE 和前端恢复按钮已接通。
- ChangeSet apply 与 artifact review 已按项目解析 Evidence；伪造或跨项目
  `EV-*` 无法通过。LLM 提交的 verified claim 若找不到项目 Evidence 会被降级。
- follow-up 已按完整规范化问题幂等，重复追问不再重复建页；artifact 只保存
  真实项目 Evidence id，`updated_artifact_count` 只表示本次变更。

## 真实验收结果（2026-07-22）

使用本机实际配置 `deepseek-v4-flash + Tavily + HTTP extraction` 完成 V3 生产路径验收：

- 项目：`project-63a8ed6dcd05454ab28cc0443a4e765b`；run：`run-5c098a859db94c29a9181dc02ec1d471`。
- 42 条 search-channel Evidence；生产 Evidence 中存在可读 `raw_excerpt`、`extraction_provider=http_content` 和抽取时间/元数据。
- 4 个 active V3 artifacts，均有 substantial content、V3 schema 和 evidence ids；无 V1/fallback marker。
- Agent 生成 ChangeSet 后进入 `waiting_for_human`；验收完成 approve -> apply -> 同 run `/resume` -> completed。
- 导出目录：`exports/v3真实搜索抽取验收-闭环-20260722`；包含全部 `.sectorbreaker/*.json`、manifest 和 active artifact ids。
- 真实运行约 10 分钟，期间一次 `propose_change_set` 因空 `after_content` 失败，Agent 后续自我修正并完成。这证明容错存在，也说明决策延迟和无效工具调用仍需优化。

验收通过不等于所有审计项关闭。仍未完成的主要产品缺口是：claim-level
语义支持/反证门禁、Specialist 独立工具循环、至少一个
真实垂直站点 direct connector，以及 Firecrawl map/crawl 的受控契约。

## 本轮整体体验修复（2026-07-23）

- 首屏明确区分“创建新知识库”和“接管现有 Vault”，并在开始前展示 LLM、搜索、正文抽取、本地语义检索四项准备度及缺失配置的结果影响。
- `RunSnapshot` 新增 typed `budget` 遥测；研究页以真实事件时间线为主视图，展示阶段、耗时、事件、Provider/抽取/写作预算和最新错误。静态能力图改为可展开参考；中断、失败、未配置搜索均提供对应恢复或设置动作，并诚实说明当前没有即时取消接口。
- 结果页增加质量判定和单一下一步建议，补充已验证证据与风险证据计数；知识库控制面支持记忆 Vault 路径、显示源目录只读边界、导出/打开受管 Vault，并在导入快照变化时提示审阅。
- ChangeSet 审查摘要现在显示受影响路径、证据门、版本基线和文件数，冲突错误附带恢复动作；专用信源包明确是域名过滤发现，不冒充直连 API。
- `ConfigPanel`、`KnowledgeManagementPanel` 和 ReactFlow `WorkflowEditor` 改为异步 chunk。首屏主 chunk 从约 639 kB 降至约 332 kB（gzip 约 109 kB）；其余能力按需加载。

这轮修复聚焦控制面和用户可见性，没有改变 Agent Kernel 的决策骨架、证据门或 Vault 写入边界。
