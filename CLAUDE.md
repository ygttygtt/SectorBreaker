# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SectorBreaker（领域破壁）是一款基于 LangGraph 与多智能体协同的数字化行业研究与情报分析系统。通过反向拆解产业链、竞品及内容生态，帮助用户在 1 小时内将碎片化信息编织为可无缝导入 Obsidian 的全域商业认知地图。

核心方法论分五步：
1. **建数据库** — 行业市场、玩家、交易单位的结构化数据
2. **反向拆解** — 竞品商业结构、收入模型、转化路径、信任资产
3. **内容生态** — 批量分析内容账号、高频选题、内容分类
4. **知识地图** — 多层级行业地图 + Obsidian 知识卡片
5. **情报系统** — 持续监控、周报生成、机会追踪

## Tech Stack

- **LangGraph** — 多智能体编排框架
- **Python** — 主语言
- **FastAPI** — 后端 API
- **Vite + React + TypeScript** — Web 工作台
- **SQLite** — 本地结构化状态与 FTS 检索
- **Obsidian** — 知识库输出格式（Markdown）

## Collaboration Bootstrap

Claude Code and other coding agents must read `AGENTS.md` first, then this file, then the relevant document under `docs/`.

The project is documentation-first. Before implementing business features, update or verify:

- `docs/01-architecture.md` for workflow or graph changes
- `docs/02-agent-contracts.md` for Agent behavior changes
- `docs/03-state-and-storage.md` for state/database/file changes
- `docs/04-provider-interfaces.md` for external service integration changes
- `docs/05-api-contract.md` for backend API changes
- `docs/06-export-spec.md` for Markdown/Obsidian output changes
- `docs/07-testing-strategy.md` for test coverage expectations

Core guardrail: all cross-agent outputs must be structured and evidence-linked. Do not let graph nodes exchange important data only as prose.

## Current Progress Handoff

Before continuing feature work, read `docs/10-current-status-and-handoff.md` and `docs/11-tooling-handoff.md`.

That document records:

- what has already been implemented;
- what remains unfinished;
- which tasks are safe to delegate;
- which architecture-sensitive tasks need stronger review;
- how to sync project memory after progress changes.

Claude Code should also read `.claude/memory/MEMORY.md` before making changes.

## Git: Dual Remote Push

提交日志统一使用中文。

本项目同时推送到 GitHub 和 Gitee，**每次 commit 后必须两边都推**：

```bash
git push origin main && git push gitee main
```

| Remote | 平台 | 地址 |
|--------|------|------|
| `origin` | GitHub | `git@github.com:ygttygtt/SectorBreaker.git` |
| `gitee` | Gitee | `git@gitee.com:ygttygtt/sector-breaker.git` |
