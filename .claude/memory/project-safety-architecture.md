---
name: project-safety-architecture
description: SectorBreaker 文档优先与安全协作架构，适配 Claude Code 和多 Agent 接力开发
metadata:
  type: project
---

SectorBreaker 必须优先维护协作规范和架构护栏，再进入业务功能开发。

## 必读文件

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/00-project-brief.md`
4. `docs/01-architecture.md`
5. `docs/02-agent-contracts.md`

## 核心原则

- 文档先行：接口、schema、Agent 合约、测试标准先写清楚。
- 结构化输出：Agent 间传递 Pydantic/JSON schema，不靠散文解析。
- 证据优先：关键研究结论必须关联来源、可信度、验证状态。
- Provider 隔离：LLM、搜索、检索、导出都必须走抽象接口。
- 固定关口：Supervisor 可动态派活，但不能绕过研究框架、证据、知识地图、机会地图、导出等质量门。

