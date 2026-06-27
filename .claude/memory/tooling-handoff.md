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
- 后端：FastAPI + LangGraph + SQLite + provider factory + Supervisor Plan + Evidence Ledger + 可解释选择轨迹
- 前端：Vite + React + TypeScript，可解释研究工作台，真实 workflow graph，纵向布局与活动节点居中
- 前端默认 `/api` 代理到 `http://127.0.0.1:8000`。如果 UI 误报 LLM/搜索未配置，优先排查旧 `uvicorn` 进程和 Vite 是否需要重启。
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

最高风险任务：

- 剩余业务 Agent Pydantic 输出 schema 和 prompt
- 可靠信源包、真实 Counterevidence 搜索、Evidence Curator 可信度/冲突规则
- 多搜索 provider 编排、爬虫/抓取层扩展与 provider routing
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
