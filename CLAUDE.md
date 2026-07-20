# CLAUDE.md

SectorBreaker V3 是本地优先的多智能体知识库自治管理系统。生产入口只有 `backend.app.agent_kernel.run_v2_agent_kernel_pipeline`；函数名暂时保留兼容性，State 与知识控制面已升级到 V3。

## 必读顺序

1. `AGENTS.md`
2. 本文件
3. `docs/00-project-brief.md`
4. `docs/01-architecture.md`
5. `docs/02-agent-contracts.md`
6. `docs/10-current-status-and-handoff.md`
7. `docs/11-tooling-handoff.md`
8. `docs/19-agent-kernel-debugging-retrospective.md`
9. `docs/20-version-isolation-and-cutover-rules.md`
10. `docs/21-living-knowledge-base-roadmap.md`
11. `docs/23-autonomous-knowledge-management-v3.md`
12. `docs/24-local-hybrid-rag.md`
13. `.claude/memory/MEMORY.md`

## 当前架构原则

- Master Agent 通过 State、Tools、Observation 和 StateDelta 决策，不运行固定角色流水线。
- Specialist 是动态、任务级委派，只返回 typed result 或 ChangeSet suggestion，不能应用修改。
- Vault 源目录只读；系统管理 SQLite 中的不可变 Artifact revisions，并导出 managed vault。
- 已有笔记更新必须经过 ChangeSet、base hash、审批与 apply。
- factual change 必须携带 evidence ids；检索和导出只读取 active revisions。
- 外部服务只能通过 provider interfaces 调用。
- 当前检索是统一的本地 Hybrid RAG：FastEmbed 真向量、增量 SQLite 索引、lexical/vector RRF 和显式降级状态。
- 企业人才、Boss/job-source 与旧 graph workflow 已退休，不能恢复到生产 imports。

## 验收

```powershell
python -m pytest -q
python tools/check_version_isolation.py
cd frontend
npm test -- --run
npm run build
```

涉及知识生命周期的变更还应完成 import -> audit -> ChangeSet -> approve -> apply -> export -> rollback 验收。

## Git

提交信息使用中文。提交到 `main` 后，网络和认证允许时同时推送：

```powershell
git push origin main
git push gitee main
```
