---
name: current-progress-and-handoff
description: SectorBreaker 当前进度、剩余任务、可分发任务、强把控任务和项目记忆同步方式
metadata:
  type: project
---

接手 SectorBreaker 前必须先读：

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/10-current-status-and-handoff.md`
4. 与任务相关的 `docs/0x-*.md`

当前状态：

- Runnable V1 重构已开始落地：`auto_run=true` 现在走简化 V1 主路径，新增后端 `RunSnapshot`、最近 run 恢复接口、七个稳定知识产物、`_sources/evidence-ledger.md` 导出布局，以及真实验收脚本的 LLM/Search/Artifact/Export 检查。前端主按钮现在默认走 V1 `auto_run=true` 知识库构建路径，不再把首页主流程带入旧的 Supervisor Plan 确认页。当前自动化回归通过；真实 API 验收已在本地用已配置的 OpenAI-compatible LLM 和 Tavily 跑通。
- V1 第一版本地闭环已真实跑通：本地 runtime config 使用 Tavily + Mimo/OpenAI-compatible LLM，前端 `/api` 默认代理指向当前后端 `127.0.0.1:8030`；UI 输入 `Agent开发` 后可完成真实 run，结果页显示运行轨迹、`5 / 5 条证据`、7 个 Obsidian V1 artifacts，无白屏、无横向溢出、无 GitHub navigation/XLS/Instagram 噪音。
- V1.1 已收缩为“学习型领域建库”：主路径暂不做竞品收入结构和内容生态，先构建结构化 `DomainKnowledgeBase`（总览、概念、主流架构、工具、趋势、学习路径、待验证问题），再渲染 7 个 Obsidian artifacts，避免继续输出一行模板文档。
- V1.1 已修复中文复合主题过滤误杀：`大模型开发就业` 这类主题不再要求完整短语命中；大模型就业/应用开发主题有专属 fallback，覆盖 RAG、Agent、模型 API、Python/后端、作品集和岗位验证问题。
- V1.1 已改为逐文档 LLM 写作：构建 `DomainKnowledgeBase` 后，`Document Writer` 会对 7 个 Obsidian artifact 分别调用 LLM 写完整 Markdown，并发出 `document_writing` 进度事件；短/空输出才回退到 deterministic renderer。
- V1.1 已新增证据充足度检查和生成心跳：可用证据少于 8 条时会补充一轮开放搜索并去重，仍不足时发 warning；Knowledge Builder / Document Writer 的长 LLM 调用会定期发 `node_progress`，避免 UI 长时间无反馈。
- V1.2 已新增富 Obsidian 输出：每篇主文档后有 bounded `Artifact Reviewer`，目标是发现“不够详实”的部分并最多补写一次；同时从 `DomainKnowledgeBase` 生成 `concepts/`、`architectures/`、`tools/`、`questions/` 知识卡片，主文档 fallback 使用可落地的 `[[双向链接]]`。
- V1.2 展示冲刺计划已写入 `docs/superpowers/plans/2026-07-03-v1-2-demo-readiness.md`，作为 2026-07-04 录制前的执行指南：收口当前富 Obsidian 基线、补前端进度可视化、结果质量面板、Obsidian README 首页和失败兜底，不扩展到完整 RAG / 多搜索 UI / 内容生态。
- V1.2 展示冲刺的前端/导出收口已完成：`artifact_review` 可映射到可见流程节点，结果页有质量摘要，失败运行有查看部分结果/重新运行兜底，V1 导出 README 已升级为 Obsidian Vault 首页。
- V1.3 `Talent Demand Intelligence Agent` 已作为可运行新模式接入。`project_mode` 默认 `domain_knowledge`，保持 V1.2 领域建库；`talent_demand` 会进入新的人才需求 pipeline。
- V1.3 人才需求后端已实现真实非空壳能力：上传 JD/user material 与外部 AI 报告优先入库，搜索 provider 作为补充；保守抽取岗位/公司/地点/薪资/经验/职责/技能/工具/层级；归一化 LLM/大模型、RAG、Agent、LangChain、LangGraph、Python、FastAPI、向量数据库等技能别名；生成 Source Coverage Matrix；导出人才需求 Obsidian vault。
- V1.3 前端已接入模式选择、JD 文本/文件上传、外部报告上传、多 provider 搜索设置可见性（Tavily/Serper/Brave/Exa）、Source Coverage 结果面板，并做了一轮整体工作台视觉重做。旧 `领域建库` 仍是默认入口。
- V1.4 已新增企业版 Boss/job-source 增强：`JobSourceProvider`、`BossAgentCliProvider`、`/api/config/job-source`、`boss_job_intake`、`boss_job` evidence channel、Source Coverage 的 `boss_job_count`、前端企业版 Boss 采集面板。默认关闭，只影响 `talent_demand`。
- V1.4 已新增项目级 RAG 问答：`/api/projects/{project_id}/chat` 检索 evidence、上传文档、document segments、artifacts，并返回 `citation_details`；有 LLM 时基于引用回答，无 LLM 时返回确定性引用摘要。
- V1.5 已修复个人版 `高考教育线上培训` 这类中文复合主题 0 证据和模板污染问题：通用中文主题使用中文调研搜索词，过滤器接受 `高考` / `在线教育` / `培训` 等有意义局部命中；非 Agent fallback 改为领域中性 `待补证草稿`，Agent 和大模型就业主题保留专属 fallback。
- V1.5 已让 LLM 降级可见：结构化建库或逐文档写作失败/过短时会发 `node_degraded` 事件，不再静默回落模板。
- V1.5 已新增 0 证据硬中断：初搜和补搜后仍没有可用 evidence 时，V1 run 会在 `source_collection` 发 `node_blocked`，run 进入 failed，不再生成 artifacts。
- V1.5 已支持外部报告 / JD / 用户材料上传 `.docx` 和 `.pdf`：DOCX 用 WordprocessingML 解析，PDF 优先 `pypdf`，无法提取文本时明确报错。
- V1.5 已增强导出体验：manifest 带绝对 `export_dir`，新增受限的 `/api/exports/open-folder` 打开本地导出目录。
- V1.5 前端已区分个人版 `SectorBreaker 领域建库` 与企业版 `TalentScope 人才需求情报台`，包含不同文案、主题、输入引导、Word/PDF 上传提示和分支式流程图预览。
- 已新增 `docs/16-master-agent-research-core.md`，正式记录主管节点 / Master Agent 的架构要求：必须智能、有判断能力、可通过 provider/service 调用工具、具备运行期状态和结构化记忆，并能决定流程继续、补搜、询问用户、降级或中断。上传的外部 AI 调研报告必须作为一等外部信源进入其上下文；硬编码证据条数不能作为主要充分性判断。
- V1.6 已实现个人版 `domain_knowledge` 的第一版 bounded Master Agent 调研循环：运行期 `RunWorkingMemory` 记录目标、上传材料、搜索尝试、工具结果、覆盖报告和决策；外部 AI 报告/用户材料/引用会先转为 V1 evidence；`SearchPlan` / `SearchIntent` 驱动多意图搜索；`CoverageReport` 按概念、现状、趋势、政策/风险、案例/玩家、用户需求、信源质量判断；`MasterAgentDecision` 决定继续、补搜、降级或中断。0 证据硬中断，薄证据只能以 degraded 继续，不再显示“充分”。
- V1.6 前后端运行图已对齐真实 gate：个人版 workflow-definition 和前端 event mapping 使用 `master_agent`、`external_report_intake`、`source_collection`、`evidence_ledger`、`coverage_evaluation`、`knowledge_structuring`、`document_writing`、`artifact_review`、`export`。
- 已新增 `docs/17-agent-state-memory-architecture.md` 和 `docs/superpowers/plans/2026-07-06-agent-state-memory-react-rebuild.md`，正式记录下一阶段核心：知识库设计、状态设计、Agent 记忆设计、上下文筛选、外部 DeepSearch 报告内化、动态 L0-L5 实战认知 Schema、子 Agent ReAct、可选安全冰山/风险探测、人类反馈后重新打开图。
- V2 foundation 旧路径仍保留为 legacy 测试路径：`backend/app/v2_pipeline.py` 不再是个人版生产 auto-run 入口，后续不要把它接回主流程。
- 重要排障记忆：旧 `uvicorn` 进程和 Vite 代理端口不一致会造成“后端配置好了但 UI 仍显示未配置/像没修”的假象。验收前先确认只有一个目标后端，当前默认是 `uvicorn backend.app.api.app:app --port 8030`，并在 `vite.config.ts` 或 `VITE_API_PROXY_TARGET` 变更后重启 Vite。
- V2 Agent Kernel 失败处理已有 partial-write 回归保护：如果前一篇文档写作成功、后一篇写作失败，run 必须 failed，且不能把前序半成品 artifact 持久化到仓库。
- 根目录 `.obsidian/` 是默认 Obsidian Vault 配置模板，包含用户常用插件/设置/工作区。Markdown 导出必须把它复制到每个生成的知识库目录；它不是 evidence，也不是 Agent artifact。
- 文档与协作规范已建立。
- 核心 schema、provider interfaces、provider factory、SQLite migration/repository 已建立。
- 已新增 `source_policy`、`SupervisorPlan`、`AgentTask`、`AgentSelectionDecision`、`AgentSelectionSignal`、`EvidenceClaim`、`QAReport`、workflow definition schemas。
- Evidence Ledger 已扩展 source channel/source quality/claim strength/bias risk/counterevidence 等字段。
- OpenAI 兼容 LLM provider 已实现，可通过 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 启用。
- Tavily search provider 可通过 `TAVILY_API_KEY` 启用。
- 后端现已支持 Tavily / Serper / Brave / Exa 多搜索 provider；V1 前端设置页暂时只暴露 Tavily，避免第一版 onboarding 混乱。
- 已补充搜索配置状态接口；当前前端会在搜索未配置时明确提醒，不再静默降级。
- 前端保存 Tavily runtime 配置后会立即刷新首页搜索状态，不再需要手动刷新页面才能消除“搜索未配置”提示。
- 已新增 `docs/14-search-and-report-ingestion-design.md`，作为多 provider 搜索、外部 AI 报告上传、引用来源验证、交叉验证扩展的正式设计入口。
- 已支持 Serper + Tavily 多搜索 provider 聚合基础。
- 已支持文档上传、切段、引用提取、来源启发式验证、evidence preview、引用证据入库。
- 已打通“文档证据自动进入 workflow”这条链路：已入库 citation evidence 会在 run start/resume 自动作为 seed evidence 注入；`assistant_brief` 文档会自动并入低可信报告输入；普通用户文档会作为 supplemental evidence 注入。
- repository 侧 `add_evidence` 现为幂等写入，避免重复 ingest / resume / 完成持久化时因相同 evidence_id 失败。
- 已打通第一版自动反证回路：`needs_counterevidence` 的线索会生成 verification tasks，并复用现有 search provider 产出新的验证证据（支持/冲突线索）。
- 已补上 `ContentExtractionProvider` 底座，并接入自动反证链路：验证搜索结果可做 `url -> 正文抽取 -> 来源复评 -> evidence 回写`。
- `ContentExtractionProvider` 已支持环境变量切换：默认本地 HTTP fallback，可直接切换到 Firecrawl 或 Jina Reader-style extractor。
- 已新增 `.env.example` 和 `/api/config/search/test`，现在可以在不开项目 run 的情况下直接验证“搜索 + 抽取”链路是否接通。
- 前端 `LLM 设置` 面板现已接入 `测试搜索链路`，配置好 key 后可直接在 UI 验证搜索/抽取连通性。
- landing 页现已直接显示当前启用的搜索 provider 和正文抽取 provider，真实 API 是否生效在主界面即可确认。
- 已新增 `run_search_smoke_test.py`，并增强 `/api/config/search/test`：默认自动抽取首条结果并返回来源评估，真实 API 接入后的验收路径更完整。
- 已补统一 `.env` 自动加载：FastAPI app 与 smoke test 脚本都会读取仓库根目录 `.env`，`.env.example -> .env` 的本地接入路径现已真正生效。
- 已新增 `docs/15-real-search-provider-onboarding.md`，把真实 provider 接入验收拆成 UI、API、CLI、真实 run 四步，后续可直接按清单联调。
- 已新增 `run_real_search_acceptance.py`，可一键串起 `/api/config/search`、`/api/config/search/test`、真实 project run、evidence 入库检查，减少手工联调成本。
- 已新增 `generate_search_env_template.py`，可直接输出最小 `.env` 模板片段，方便真实 provider 快速接入。
- landing / review 现已支持 `.md` / `.txt` 文件上传，assistant brief 与 user material 会通过真实 documents API 入库后再进入研究流程。
- LangGraph workflow 已升级为 Scope → Supervisor Plan → Source Strategy → Source Intake → Claim Extractor → Counterevidence → Evidence Ledger → Market → Player → Transaction → Synthesis → Knowledge Map → QA → Export/RAG Indexer。
- 默认非 auto_run 会在 `supervisor_plan` 暂停，等待用户确认计划。
- 外部 AI 报告只支持手动 md/txt/粘贴输入，作为 `assistant_brief` 低可信线索。
- Markdown/Obsidian 导出器已跑通。
- FastAPI API 已跑通项目 create/list/detail、run、evidence、artifacts、export、chat。
- React/Vite 工作台已重构：信源模式选择、可选 assistant brief、真实 workflow graph、纵向布局、活动节点居中、节点状态、事件流、运行时长、Supervisor Plan review、QA 阻塞视图、证据/产物/问答/导出。
- Vite 已代理 `/api` 到 `http://127.0.0.1:8000`。

强把控任务：

- 剩余业务 Agent 专用 Pydantic 输出 schema。
- 按 `docs/14-search-and-report-ingestion-design.md` 推进多搜索 provider、报告上传/切段、引用来源验证、可靠信源包、真实 Counterevidence 搜索。
- 下一优先级建议放在：把 `needs_counterevidence` 自动转成 verification tasks，并接回搜索 provider 做二次验证/找反例。
- 下一优先级建议放在：增强 verification task query planning、把验证结果和原 claim/evidence 建立更明确的双向链接、补内容抽取层。
- 下一优先级建议放在：接 Firecrawl/Jina 这类更强 extractor、增强 verification task query planning、把验证结果和原 claim/evidence 建立更明确的双向链接。
- 下一优先级建议放在：增强 extractor 失败控制与域名路由、优化 verification task query planning、把验证结果和原 claim/evidence 建立更明确的双向链接。
- 下一优先级建议放在：把 search test 接到前端配置面板、增强 extractor 失败控制与域名路由、优化 verification task query planning、把验证结果和原 claim/evidence 建立更明确的双向链接。
- 下一优先级建议放在：增强 extractor 失败控制与域名路由、优化 verification task query planning、把验证结果和原 claim/evidence 建立更明确的双向链接。
- 下一大版本优先级应转向 `docs/16-master-agent-research-core.md`：结构化 run memory、外部报告进入 V1 主上下文、Master Agent 生成工具/搜索计划、LLM CoverageReport 取代硬编码证据条数、bounded ReAct/search loop、运行图与真实节点对齐。
- Master Agent 后续优先级：V1.6 bounded loop 已落地，下一步应补 full `ask_user` 人在回路中断、更强来源验证、RAG/vector 检索进入主管上下文、更多工具路由，而不是继续写死搜索 heuristic。
- 状态/记忆后续优先级：先定义 `SectorBreakerState`、`KnowledgeSchema`、`ContextPack`、`TaskMemory`、`AgentDecision` 等 Pydantic 契约，再做 ContextPackBuilder 和外部报告 internalizer，最后迁移到 LangGraph StateGraph 与 specialist ReAct loops。
- V2 后续优先级：Pydantic 契约、ContextPackBuilder、ReportInternalizer、ReAct runner、specialist contracts、冰山风险 Agent、V2 graph skeleton 和真实个人版 auto-run V2 pipeline 已实现并测试；下一步要持久化 V2 state、让 specialist loop 使用更强 LLM/tool policy、接 human feedback reopening、深化 source verification/RAG。
- V2 Agent Kernel 已接入个人版生产 auto-run：`backend/app/agent_kernel/pipeline.py` 初始化 `SectorBreakerState`、内化上传报告/用户材料、让 LLM policy 从 State 和 Tools 中选择下一步、执行工具、应用 StateDelta，并只持久化 completed artifacts。运行事件可见 Thought Summary / Action / Observation / State Update / Decision。`write_layer_document` 会重试 3 次；仍失败或过薄则 run failed / `artifact_writing_failed`，不保存模板假产物。
- QA Critic artifact prose unsupported-claim 检测与 retry 建议。
- LangGraph interrupt/resume 与 checkpoint 策略。
- Agent contract/schema 变更。

适合分发任务：

- 前端可编辑项目表单与 API client 抽取。
- artifact detail viewer 与 evidence filters。
- 产物页面细化。
- Markdown 导出样式。
- 示例 fixture。
- 文档补充和验收样例。

验证基线：

- `python -m pytest -q`：23 passed，1 个 FastAPI TestClient/Starlette deprecation warning。
- 当前本轮已验证：`python -m pytest tests/unit/test_sqlite_repository.py tests/api/test_app.py -q` => 16 passed，1 warning。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_counterevidence_provider.py tests/unit/test_workflow_counterevidence.py tests/unit/test_provider_factory.py tests/unit/test_source_verification_provider.py tests/api/test_app.py -q` => 20 passed，1 warning；`python -m pytest tests/unit/test_markdown_exporter.py -q` => 1 passed。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_content_extraction_provider.py tests/unit/test_counterevidence_provider.py tests/unit/test_workflow_counterevidence.py tests/unit/test_provider_contracts.py tests/api/test_app.py -q` => 17 passed，1 warning；`python -m pytest tests/unit/test_markdown_exporter.py tests/unit/test_provider_factory.py tests/unit/test_source_verification_provider.py -q` => 8 passed。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_content_extraction_provider.py tests/unit/test_provider_factory.py tests/unit/test_workflow_counterevidence.py -q` => 13 passed；`python -m pytest tests/api/test_app.py tests/unit/test_source_verification_provider.py tests/unit/test_counterevidence_provider.py tests/unit/test_markdown_exporter.py -q` => 15 passed，1 warning。
- 当前本轮已新增验证：`python -m pytest tests/api/test_app.py tests/unit/test_provider_factory.py tests/unit/test_content_extraction_provider.py -q` => 25 passed，1 warning；`python -m pytest tests/unit/test_workflow_counterevidence.py tests/unit/test_counterevidence_provider.py tests/unit/test_source_verification_provider.py tests/unit/test_markdown_exporter.py -q` => 5 passed。
- 当前本轮已新增验证：`cd frontend && npm test -- --run` => 5 passed；`python -m pytest tests/api/test_app.py tests/unit/test_provider_factory.py tests/unit/test_content_extraction_provider.py -q` => 25 passed，1 warning。
- 当前本轮已新增验证：`cd frontend && npm test -- --run` => 6 passed；`python -m pytest tests/api/test_app.py -q` => 13 passed，1 warning。
- 当前本轮已新增验证：`python -m pytest tests/api/test_app.py -q` => 13 passed，1 warning；`cd frontend && npm test -- --run` => 6 passed。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_env_loader.py tests/api/test_app.py -q` => 15 passed，1 warning；`cd frontend && npm test -- --run` => 6 passed。
- 当前本轮已新增验证：`cd frontend && npm test -- --run` => 7 passed；`python -m pytest tests/api/test_app.py -q` => 13 passed，1 warning。
- 当前本轮已新增验证：`cd frontend && npm test -- --run` => 14 passed；`cd frontend && npm run build` => 通过。
- 当前本轮已新增验证：`python run_real_search_acceptance.py` => 通过，包含 LLM config、Tavily live search、project run completed、5 条 search-channel evidence、7 个 V1 artifacts、Obsidian export manifest。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_v1_pipeline.py -q` => 6 passed；真实默认策略 API run（`Agent开发`）=> completed，4 条 search evidence，7 个 artifacts；真实 UI run（`Agent开发`）=> completed，运行轨迹可见，`5 / 5 条证据`，无白屏/横向溢出/明显导航噪音。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_v1_pipeline.py -q` => 8 passed；`python -m pytest tests/api/test_app.py::test_api_v1_run_creates_knowledge_system_artifacts tests/unit/test_real_search_acceptance_script.py -q` => 6 passed，1 warning。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_v1_pipeline.py -q` => 10 passed；真实搜索诊断显示 `大模型开发就业 岗位 技能要求 职业路径 2026` Tavily 原始返回 8 条结果，之前 0 evidence 是 V1 过滤误杀。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_v1_pipeline.py -q` => 11 passed；`cd frontend && npm test -- --run App.test.tsx` => 16 passed。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_talent_demand_pipeline.py tests/unit/test_talent_demand_models.py tests/unit/test_talent_demand_extraction.py tests/unit/test_talent_demand_skills.py tests/unit/test_talent_demand_source_coverage.py tests/unit/test_talent_demand_export.py tests/api/test_app.py::test_api_talent_demand_run_uses_uploaded_jd_and_creates_talent_artifacts tests/api/test_app.py::test_api_runs_research_and_exports_markdown tests/api/test_app.py::test_api_accepts_talent_demand_project_mode -q` => 16 passed，1 warning；`cd frontend && npm test -- --run App.test.tsx` => 17 passed；`cd frontend && npm run build` => 通过，仅 Vite chunk-size warning。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_job_source_provider.py tests/unit/test_project_retriever.py tests/unit/test_talent_demand_pipeline.py tests/unit/test_talent_demand_source_coverage.py tests/api/test_app.py::test_api_talent_demand_run_uses_uploaded_jd_and_creates_talent_artifacts tests/api/test_app.py::test_api_chat_uses_project_retrieval tests/api/test_app.py::test_api_talent_demand_run_uses_boss_job_source_when_enabled -q` => 13 passed，1 warning；`cd frontend && npm test -- --run App.test.tsx` => 17 passed；`cd frontend && npm run build` => 通过，仅 Vite chunk-size warning。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_v1_pipeline.py -q` => 15 passed；上传/导出 API 子集 => 6 passed，1 warning；`cd frontend && npm test -- --run App.test.tsx` => 17 passed；`cd frontend && npm run build` => 通过，仅 Vite chunk-size warning。
- 当前本轮已新增验证：`python -m pytest tests/unit/test_v1_pipeline.py -q` => 16 passed；`python -m pytest tests/api/test_app.py::test_api_exposes_workflow_definition_and_source_policy -q` => 1 passed，1 warning；`cd frontend && npm test -- --run App.test.tsx` => 17 passed；`cd frontend && npm run build` => 通过，仅 Vite chunk-size warning。
- 当前本轮已新增验证：V2 Agent Kernel `python -m pytest tests/unit/test_agent_kernel_models.py tests/unit/test_agent_kernel_tools.py tests/unit/test_agent_kernel_runtime.py tests/api/test_app.py::test_api_runs_research_and_exports_markdown tests/api/test_app.py::test_api_agent_kernel_writer_failure_marks_run_failed_without_artifacts tests/api/test_app.py::test_api_agent_kernel_uploaded_report_reaches_writer_context -q` => 7 passed，1 warning；`cd frontend && npm test -- --run App.test.tsx` => 17 passed；真实 LLM 最小探针使用本地 runtime config 的 `mimo-v2.5-pro`，结构化 JSON 和 plain text 均通过。
- 当前本轮已新增验证：`python -m pytest tests/api/test_app.py::test_api_agent_kernel_failed_run_does_not_persist_partial_artifacts tests/unit/test_markdown_exporter.py::test_markdown_exporter_copies_default_obsidian_config -q` => 2 passed，1 warning。
- `cd frontend && npm test -- --run`：3 passed。
- `cd frontend && npm run build`：通过。

记忆同步：

- 状态变化更新 `docs/10-current-status-and-handoff.md`。
- 跨工具接手信息变化更新 `docs/11-tooling-handoff.md`。
- Claude Code 记忆变化更新 `.claude/memory/MEMORY.md` 和对应 memory 文件。
- 跨工具接手记忆变化更新 `.claude/memory/tooling-handoff.md`。
- 协作规则变化更新 `AGENTS.md`。
- Claude 入口说明变化更新 `CLAUDE.md`。
- 提交后同时推送 `origin main` 和 `gitee main`。
