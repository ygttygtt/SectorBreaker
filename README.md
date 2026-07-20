# SectorBreaker

**本地优先的多智能体知识库自治管理系统。**

SectorBreaker 不再以“一次性快速了解一个领域”为终点。它可以创建或接管一个 Markdown/Obsidian Vault，持续发现知识缺口、研究和验证信息、提出可审计修改，并通过版本、Diff、审批和回滚控制知识库演化。

## 当前可用能力

- 导入现有 Markdown/Obsidian Vault，不修改源目录。
- 确定性检查断链、孤立笔记、重复标题、缺失 front matter、缺失证据元数据和未解决标记。
- 将问题持久化为维护 Backlog，重复审计不会重复创建任务。
- Master Agent 按 State 和目标自主选择检索、搜索、委派 Specialist、写作或等待用户。
- 动态 Specialist 角色：`vault_auditor`、`researcher`、`verifier`、`knowledge_editor`。
- Specialist 只有角色级工具白名单，不能直接应用修改。
- 对已有笔记的修改生成 ChangeSet、base hash 和 unified diff；显式审批后才能应用。
- Artifact 使用不可变 revision、content hash、supersedes/superseded_by 和 active 状态。
- active-only 检索和导出；支持冲突检测与逐字节内容回滚。
- 前端提供 Vault 导入、健康报告、Backlog、维护运行、Diff、批准、应用和回滚工作台。
- 导出为可直接打开的 Obsidian Vault，并保存 `.sectorbreaker/` 控制面状态。

## 当前 RAG 实现

当前版本已经实现真实的本地 Hybrid RAG。项目问答和 Agent 共用同一个检索服务：

- SQLite FTS 检索 evidence；
- `BAAI/bge-small-zh-v1.5` 通过 FastEmbed 在本地生成 query/document embeddings；
- evidence、document segments 和 active artifacts 按 content hash 增量写入 SQLite 向量索引；
- lexical 与 vector 候选通过 RRF 融合，不混加不可比较的原始分数；
- citation 返回 lexical/vector rank、相似度、模型、路径、hash 和验证状态；
- superseded revisions 会从活动索引清除；未变化内容不会重复向量化。

Embedding runtime 或模型不可用时，API 和前端会明确显示 `lexical_degraded`，不会把关键词检索伪装成语义检索。首次使用会把模型下载到 `~/.cache/sectorbreaker/fastembed`；之后离线从本地缓存加载。

## 核心闭环

```text
Vault 导入
  -> 健康审计
  -> 维护 Backlog
  -> Master Agent / Specialist 研究与验证
  -> ChangeSet + Diff
  -> 审批应用
  -> active revision 导出
  -> 回滚
```

## Quick Start

```powershell
conda activate sectorbreaker
pip install -e ".[dev]"

cd frontend
npm install
cd ..

python -m uvicorn backend.app.api.app:app --port 8030 --reload
```

新终端：

```powershell
cd frontend
npm run dev
```

打开 `http://127.0.0.1:5173/`。LLM 和搜索 Provider 可在页面设置中配置；不配置搜索时，Vault 导入、审计、ChangeSet、导出和回滚仍可本地运行。

## Provider

- LLM：任何 OpenAI-compatible endpoint。
- Search：Tavily、Serper、Brave、Exa，支持单一或聚合模式。
- Extraction：本地 HTTP fallback、Firecrawl 或 Jina Reader。
- Embedding：FastEmbed 本地模型，默认 `BAAI/bge-small-zh-v1.5`。
- `user_materials_only` 会在运行时硬阻断联网搜索。

环境变量示例见 `.env.example`。搜索链可单独验证：

```powershell
python run_search_smoke_test.py
python tools/smoke_local_hybrid_rag.py
```

## 验证

```powershell
python -m pytest -q
python tools/check_version_isolation.py

cd frontend
npm test -- --run
npm run build
```

## 关键文档

- `docs/00-project-brief.md`
- `docs/01-architecture.md`
- `docs/02-agent-contracts.md`
- `docs/05-api-contract.md`
- `docs/06-export-spec.md`
- `docs/10-current-status-and-handoff.md`
- `docs/20-version-isolation-and-cutover-rules.md`
- `docs/23-autonomous-knowledge-management-v3.md`
- `docs/24-local-hybrid-rag.md`

## 已退休能力

企业人才需求、TalentScope、Boss/job-source 和旧固定 workflow 已从生产代码、API、前端和测试中删除。历史数据库通过 migration 归档和清理相关数据，生产路径不能再导入这些模块。

## Later

- 增量后台监控和定时刷新；
- 与用户源 Vault 的双向同步；
- move/delete 的更强审批和恢复语义；
- 多用户与云端部署。
