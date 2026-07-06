---
name: tooling-handoff
description: SectorBreaker 跨工具接手入口，适用于 Cursor、Windsurf、Gemini、Claude Code、Codex 等后续开发工具
metadata:
  type: project
---

后续任何工具或 Agent 接手时，不要依赖原始聊天记录。以仓库文档为准。

必读顺序：

1. `AGENTS.md`
2. `README.md`
3. `docs/10-current-status-and-handoff.md`
4. `docs/11-tooling-handoff.md`
5. 当前任务相关的 `docs/0x-*.md`

当前基线：

- conda 环境：`sectorbreaker`
- Runnable V1 重构已部分落地：`auto_run=true` 走简化 V1 主路径，前端主按钮现在默认进入 V1 知识库构建，不再把默认用户路径带到旧 Supervisor Plan 确认页。前端开始消费后端 `RunSnapshot`，导出布局改为稳定 Obsidian V1 文件集。真实验收已在本地用已配置的 OpenAI-compatible LLM 和 Tavily 跑通。
- V1 第一版真实 UI 闭环已跑通：本地 runtime config 使用 Tavily + Mimo/OpenAI-compatible LLM；`http://127.0.0.1:5173` 输入 `Agent开发` 可跑到完成，结果页有运行轨迹、`5 / 5 条证据`、7 个 artifacts，无白屏、无横向溢出、无 GitHub navigation/XLS/Instagram 噪音。
- V1.1 当前主线是学习型领域建库，不做竞品收入结构和内容生态。后端先构建 `DomainKnowledgeBase`，再导出概念、架构、工具、趋势、学习路线和待验证问题，避免一行模板文档。
- V1.1 已修复中文复合主题过滤误杀，并为大模型就业/应用开发主题提供专属 fallback 内容。
- V1.1 已改为逐文档 LLM 写作：构建 `DomainKnowledgeBase` 后，后端会让 LLM 分别写 7 个 Obsidian Markdown artifact，并发出 `document_writing` 进度事件，前端据此更新流程状态。
- V1.1 已新增证据充足度检查和 LLM 生成心跳：少于 8 条可用证据时补搜一轮并去重，仍不足会 warning；长时间建库/写作时持续发 progress 事件。
- V1.2 已新增富 Obsidian 输出：主文档写作后运行 bounded `Artifact Reviewer`，偏向扩写详实度而不是删短；导出会额外生成 `concepts/`、`architectures/`、`tools/`、`questions/` 知识卡片，并改进 YAML front matter 以适配 Obsidian Properties。
- V1.2 展示冲刺计划已写入 `docs/superpowers/plans/2026-07-03-v1-2-demo-readiness.md`。下一步按该计划完成前端进度可视化、结果质量面板、导出 README 首页和 demo-safe failure/restore，不要在录制前扩展 full RAG、多搜索 UI 或内容生态抓取。
- V1.2 展示冲刺的前端/导出收口已完成：结果页质量摘要、失败恢复块、`artifact_review` 流程映射和 V1 Obsidian Vault README 首页都已落地。后续真实录屏验收交给用户本地跑 Tavily/Mimo。
- V1.3 `Talent Demand Intelligence Agent` 已可运行。`project_mode="domain_knowledge"` 仍走默认 V1.2 领域建库；`project_mode="talent_demand"` 走新人才需求 pipeline。
- V1.3 已实现上传 JD/user material、外部 AI 报告、搜索补充、JD 信号抽取、技能归一化、Source Coverage Matrix、人才需求 Obsidian vault 和前端 Source Coverage 面板。后续不要把这个当成纯计划或 UI 壳子。
- V1.4 已实现企业版 Boss/job-source 增强：本地 Boss-compatible CLI 通过 `JobSourceProvider` 接入，采集结果写入 `boss_job` evidence channel。该能力默认关闭，只在 `talent_demand` 启用，不影响个人版。
- V1.4 已实现项目级 RAG 问答：chat 检索项目 evidence、documents、segments、artifacts，并返回 `citation_details`。
- V1.5 已修复个人版中文复合主题 0 证据和模板污染问题：通用中文主题使用中文调研搜索词，过滤器接受有意义局部命中，非 Agent fallback 是领域中性 `待补证草稿`，LLM fallback 会发 degraded 事件。
- V1.5 已新增 0 证据硬中断：初搜和补搜后仍没有可用 evidence 时，V1 run 会在 `source_collection` 发 `node_blocked`，run 进入 failed，不再生成 artifacts。
- V1.5 已支持 `.docx` / `.pdf` 上传外部报告、JD 和用户材料；DOCX 用 WordprocessingML 解析，PDF 优先 `pypdf`，提取失败会明确报错。
- V1.5 已增强导出体验：manifest 带 `export_dir`，并新增受限 `/api/exports/open-folder` 打开本地导出目录。
- V1.5 前端已区分个人版 `SectorBreaker 领域建库` 和企业版 `TalentScope 人才需求情报台`，包括不同文案、主题、输入引导和分支式流程图预览。
- 已新增 `docs/16-master-agent-research-core.md`，正式记录主管节点 / Master Agent 要求：必须智能、有判断能力、可通过 provider/service 调用工具、具备运行期状态和结构化记忆，并能决定继续、补搜、询问用户、降级或中断。上传的外部 AI 调研报告必须作为一等外部信源进入其上下文；硬编码证据条数不能作为主要充分性判断。
- V1.6 已实现个人版 bounded Master Agent loop：`RunWorkingMemory`、外部报告/材料/引用证据入库、Master 多意图搜索计划、`SearchProvider` 工具调用诊断、`CoverageReport` 覆盖判断、`MasterAgentDecision` 继续/补搜/降级/中断。0 证据会阻塞，薄证据会 degraded，不再被标记为充分。
- V1.6 个人版 workflow-definition 和前端流程图已对齐真实事件节点：`master_agent`、`external_report_intake`、`source_collection`、`evidence_ledger`、`coverage_evaluation`、`knowledge_structuring`、`document_writing`、`artifact_review`、`export`。
- 已新增 `docs/17-agent-state-memory-architecture.md` 和 `docs/superpowers/plans/2026-07-06-agent-state-memory-react-rebuild.md`。下一阶段主线是状态/记忆/知识架构：`SectorBreakerState`、动态 L0-L5 Schema、ContextPack 过滤、外部报告内化、specialist ReAct loops、安全冰山/风险探测、人类反馈 reopening。
- V2 Agent Kernel 已接入个人版生产 auto-run：`backend/app/agent_kernel/pipeline.py` 初始化 `SectorBreakerState`、内化上传报告/用户材料、让 LLM policy 从 State 和 Tools 中选择下一步、执行工具、应用 StateDelta，并只持久化 completed artifacts。旧 V1/V2 workflow 已移动到 `backend/app/legacy/`，生产代码不得 import。`write_layer_document` 使用普通文本 LLM completion 写 Markdown，不再把正文当 JSON 解析；失败会重试 3 次，仍失败或输出过薄时 run failed / `artifact_writing_failed`，不会导出模板假产物。
- Agent Kernel 验收必须包含真实 Mimo + Tavily 端到端运行和导出 Markdown 检查；fake/unit test 不能单独作为用户可测结论。
- 当前真实 Agent Kernel 验收：项目 `api中转站-v2-agent-kernel验收5`，导出目录 `E:\QianFengStudy\PythonProject\SectorBreaker\exports\api中转站-v2-agent-kernel验收5`。导出包含 5 篇 V2 Markdown（约 17KB-22KB），使用 `schema_version: "v2-agent-kernel"` 和 `EV-KERNEL-*`，无旧 V1/fallback 标记。
- V2 长调试失败复盘已写入 `docs/19-agent-kernel-debugging-retrospective.md`。后续工具接手 Agent Kernel 任务时必须先读：它记录了旧 workflow 泄漏、伪 Agent 命名、Markdown 走 JSON 解析、模板兜底掩盖失败、前端图与后端执行漂移、fake/unit test 误判可用等失败链路，以及真实导出验收门槛。
- V2 Agent Kernel 的失败语义包含 partial-write 场景：如果前一篇文档已生成、后一篇写作失败，失败 run 不能持久化任何半成品 artifact。
- 根目录 `.obsidian/` 是默认 Obsidian Vault 配置模板，导出器会复制到每个生成的知识库目录；它不是 generated artifact 或 evidence。
- 前端设置页已展示 Tavily / Serper / Brave / Exa provider mode；Tavily 仍是推荐默认。人才需求模式明确不默认抓取登录型招聘网站。
- 后端：FastAPI + LangGraph + SQLite + provider factory + Supervisor Plan + Evidence Ledger + 可解释选择轨迹
- 前端：Vite + React + TypeScript，可解释研究工作台，真实 workflow graph，纵向布局与活动节点居中
- 前端默认 `/api` 代理到 `http://127.0.0.1:8030`。如果 UI 误报 LLM/搜索未配置，优先排查旧 `uvicorn` 进程和 Vite 是否需要重启。
- 当前会显式展示“搜索未配置”提示，避免把无联网检索误当成正常研究能力
- 后端搜索 provider 已扩展为 Tavily / Serper / Brave / Exa；V1 前端配置面板暂时只暴露 Tavily
- 保存 Tavily runtime 配置后，前端会立即刷新 landing 页搜索状态，不需要手动刷新
- `docs/14-search-and-report-ingestion-design.md` 是下一阶段搜索、报告上传、来源验证、交叉验证扩展的统一施工入口
- 真实运行链路里，上传/导入的文档已经不再停留在独立接口：citation evidence 可自动注入 workflow，assistant brief 文档会自动进入低可信报告流
- evidence 持久化已做幂等，重复 ingest/resume 不会因同 ID 证据报错
- 低可信/营销线索现在也不只是被标记：workflow 会自动创建 verification tasks，并通过已配置 search provider 拉回补充验证证据
- 验证搜索结果现在还能经过 `ContentExtractionProvider` 做正文抽取和来源复评，workflow 已经不是 snippet-only
- extractor provider 现在支持环境变量切换：默认 `http` fallback，也可切 `firecrawl` 或 `jina`
- 配完 `.env.example` 后，可直接调用 `/api/config/search/test` 验证搜索与抽取链，不必先创建项目运行
- 前端配置面板也已接入同样的搜索链路测试能力，配完 key 后可直接在 UI 点击验证
- landing 页也会显示当前 search/extraction provider，能快速确认真实 API 是否已启用
- 现在还有 CLI 验收入口 `python run_search_smoke_test.py`，API/UI smoke test 也会自动抽首条结果并返回来源评估
- 现在还有 `docs/15-real-search-provider-onboarding.md` 作为真实 key 联调清单，后续工具接手时可直接按该顺序验收
- 现在还有 `python run_real_search_acceptance.py` 作为端到端验收脚本，适合在真实 key 配好后直接验证 evidence 是否真正入库
- 现在还有 `python generate_search_env_template.py` 作为最小配置模板生成器，适合先快速产出 `.env` 片段
- FastAPI app 与 smoke-test script 都自动读取仓库根目录 `.env`
- 前端 landing/review 已支持 `.md` / `.txt` 上传 assistant brief 与 user material
- 测试基线：Python 23 passed；前端 14 passed；前端 build passed
- 最新真实验收：`python run_real_search_acceptance.py` passed，包含 LLM、Tavily 搜索、完整 project run、evidence 写入、V1 artifacts 和 Obsidian export。
- 最新 UI 验收：真实 `Agent开发` run completed，运行轨迹可见，证据账本 `5 / 5`，7 个 Obsidian V1 artifacts，布局不溢出。
- 最新自动化验收：V1 pipeline 单测 8 passed；V1 artifact API/acceptance script focused tests 6 passed。
- 最新自动化验收：V1 pipeline 单测 10 passed；`大模型开发就业` 搜索诊断确认 Tavily 有结果，需避免过滤误杀。
- 最新自动化验收：V1 pipeline 单测 11 passed；`frontend App.test.tsx` 16 passed。
- 最新自动化验收：V1.4 focused backend 13 passed，1 warning；`frontend App.test.tsx` 17 passed；`frontend npm run build` passed，仅 Vite chunk-size warning。
- 最新自动化验收：V1.5 pipeline 单测 15 passed；上传/导出 API 子集 6 passed，1 warning；`frontend App.test.tsx` 17 passed；`frontend npm run build` passed，仅 Vite chunk-size warning。
- 最新自动化验收：V1.6 pipeline 单测 16 passed；workflow-definition API 单测 1 passed，1 warning；`frontend App.test.tsx` 17 passed；`frontend npm run build` passed，仅 Vite chunk-size warning。
- 最新自动化验收：V2 Agent Kernel 7 passed，1 warning；frontend App 17 passed；真实 LLM 最小探针使用 `mimo-v2.5-pro`，结构化 JSON 与 plain text 均通过。
- 最新自动化验收：export/failure regression 2 passed，1 warning，覆盖 partial artifact 不落库和导出复制 `.obsidian/`。
- 最新真实验收：`api中转站-v2-agent-kernel验收5` 导出 5 篇 V2 Markdown，文件大小约 17KB-22KB，抽查内容为非模板正文，且没有旧 V1/fallback 标记。
- 最新切换收口验证：provider/kernel/API/export/planner 编译通过；focused Python suite 4 passed；frontend App suite 18 passed；生产 legacy import 扫描无匹配；验收导出只命中 5 个 `schema_version: "v2-agent-kernel"`，无旧 V1/fallback 标记。

最高风险任务：

- 剩余业务 Agent Pydantic 输出 schema 和 prompt
- 可靠信源包、真实 Counterevidence 搜索、Evidence Curator 可信度/冲突规则
- 多搜索 provider 编排、爬虫/抓取层扩展与 provider routing
- Master Agent Research Core 后续：V1.6 bounded loop 已落地；V2 durable state/memory models、ContextPackBuilder、外部报告 internalizer、bounded ReAct runner、specialist contracts、冰山风险 Agent、graph skeleton 和真实个人版 auto-run V2 pipeline 已落地；剩余重点是持久化 V2 state、让 specialist loop 使用更强 LLM/tool policy、full `ask_user` 人在回路中断、更强来源验证、RAG/vector 检索进入主管上下文和更严格 artifact claim audit
- 报告文件上传、引用来源提取、营销来源识别与验证链路
- `needs_counterevidence` 到 verification task / 搜索回路 还未自动打通，是下一核心缺口
- 下一核心缺口已从“是否自动打通”变成“如何把 verification task 做得更准、并补正文抽取与证据链接”
- 下一核心缺口进一步收敛为：接更强 extractor provider、优化 verification query planning、补充原 claim 与验证证据的强链接关系
- 下一核心缺口进一步收敛为：优化 extractor 失败控制与 domain routing、优化 verification query planning、补充原 claim 与验证证据的强链接关系
- Claim Extractor / Counterevidence 已进入真实执行链路，但后续仍可继续细化子 Agent 输出 schema
- Market / Player / Transaction / Synthesis 已进入真实执行链路，但仍可继续增强并行与独立 schema
- QA Critic artifact prose unsupported-claim 检测
- LangGraph interrupt/resume/checkpoint
- public schema / graph state / export format / provider interface 变更

适合分发任务：

- artifact detail viewer
- evidence filters
- export 样式优化
- deterministic fixtures / golden export tests

记忆同步时同时更新：

- `docs/10-current-status-and-handoff.md`
- `docs/11-tooling-handoff.md`
- `.claude/memory/current-progress-and-handoff.md`
- `.claude/memory/tooling-handoff.md`
- 必要时更新 `README.md`、`AGENTS.md`、`CLAUDE.md`
