# Agent Kernel V3：失败恢复 + 叙述人性化 + 思考日志 + 配置确认感 + 并行补卡

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复"辅助卡片失败杀掉整轮 run"的致命 bug，让已写成的真实文档不再丢失并可从断点恢复；把 Agent 面向用户的叙述改成人话；把完整思考轨迹留存为可导出日志并生成 Agent 自述报告；给 LLM 配置面板加保存确认感；让互不依赖的辅助卡片并行生成。

**Architecture:**
- **失败恢复**：writer 只在内容通过 `_usable_markdown` 校验后才落盘，所以 `context.artifacts` 里从无模板空壳。因此把「失败即丢弃全部产物」改成「持久化所有已写成的真实产物 + run 标记 `completed`（有失败时附警告事件）」，并让失败 run 也留下可恢复 checkpoint。辅助卡片（`write_explainer_card`/`write_vault_index`）失败降级为可跳过，不再阻断整轮。
- **叙述人性化**：给 `AgentDecision` 增加 `user_notice` 字段，让 LLM 在输出决策的同一次调用里**实时生成**一句面向用户的自然语言通知（"我在补充关于 X 的资料，因为……"），prompt 立规矩禁止内部术语。事件流对用户只呈现一种"进展"卡片；原始 `thought_summary`/工具名/`reason` 等降级为可折叠调试细节。绝不用代码硬编码 `if tool_name == ...` 事后翻译。
- **思考日志**：run 的完整 trace（已在 `trace_summary.json`）新增一个 `GET /api/runs/{run_id}/trace` 导出接口 + 前端下载按钮；再加一个 `generate_run_narrative` 工具，让 Agent 在 run 收尾时用第一人称复盘"我是怎么调研这个领域的"。
- **配置确认感**：前端 ConfigPanel 加"当前生效模型"高亮、未保存改动提醒、选预设时把已存 Key 回填占位符、去掉丑陋滚动条。
- **并行补卡**：主 Agent 主循环仍串行（把控全局），但当它决定"批量补 N 张解释卡"时，用一个 `write_explainer_cards_batch` 工具并发生成，互不依赖。

**Tech Stack:** Python / Pydantic v2 / FastAPI / asyncio / SQLite / React + TypeScript / pytest

---

## 排查结论（写计划的事实依据，执行前必读）

对失败 run `exports/情趣成人用品/` 的 `.sectorbreaker/trace_summary.json`（120 事件）与 `agent_state.json` 的解析结论：

| 事实 | 数据 |
|------|------|
| 证据搜集 | `evidence_count: 99` |
| 最终产物 | `artifact_count: 0`（`artifact_manifest.json` 为空数组）|
| 主文档写作 | `write_layer_document` 调用 6 次，trace event #5~#101 多为 `error=None`（**写成功了多篇**）|
| 致命点 | event #115：`write_explainer_card` 报 `missing title or focus`（LLM 调用时没填 `title`/`focus` 参数）|
| 连锁反应 | event #117：runtime 把这个**解释卡参数缺失**当致命错误 → `BLOCKED` 整轮 |
| 产物丢失原因 | `pipeline.py` 中 `raise RuntimeError` 在 `repository.add_artifact()` **之前**执行 |

**根因（与"99 条证据撑爆上下文"无关）：**

1. `runtime.py` 的 `_handle_observation` 把 `write_explainer_card`/`write_vault_index` 失败和主文档失败同等处理（同一个 `{"write_layer_document", "write_explainer_card", "write_vault_index"}` 判断），一张可选卡片参数缺失就 `FAILED` 整轮。
2. `pipeline.py` 在 run 非 COMPLETED 时 `raise`，而持久化 `for artifact in runtime_context.artifacts: repository.add_artifact(artifact)` 在 `raise` 之后，导致已写成的真实产物全部丢弃。
3. `write_explainer_card` 对 `missing title or focus` 直接返回 `success=False`，没有从 `focus`/State 兜底补 `title`。

**关键约束（来自用户决策）：**「防假产物」铁律的本意是"不存模板空壳"。当前 writer 只在 `_usable_markdown` 通过后才 append 到 `context.artifacts`，所以结构上已经不含空壳。因此可以安全地保留所有已写成的真实产物，同时仍然不写任何模板。

---

## 文件地图

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| 修改 | `backend/app/agent_kernel/runtime.py` | 卡片失败降级为可跳过；主文档失败也保留已写成产物 |
| 修改 | `backend/app/agent_kernel/pipeline.py` | 失败时先持久化真实产物再决定状态；失败 run 也存 checkpoint |
| 修改 | `backend/app/agent_kernel/tools/artifacts.py` | `write_explainer_card` 参数兜底；新增批量并发补卡工具 |
| 修改 | `backend/app/agent_kernel/models.py` | `AgentDecision` 增加 `user_notice` 字段（LLM 实时生成的人话通知）；`KernelRunResult` 增加 `partial_success`/`failed_writes` |
| 修改 | `backend/app/agents/prompts/tool_decision.md` | 要求 LLM 输出 `user_notice`，立禁术语规矩 |
| 修改 | `backend/app/agent_kernel/models.py` | `KernelRunResult` 增加 `partial_success` / `failed_writes` 字段 |
| 修改 | `backend/app/agent_kernel/tools/__init__.py` | 注册批量补卡工具与自述报告工具 |
| 新建 | `backend/app/agent_kernel/tools/narrative.py` | `generate_run_narrative` 工具：第一人称调研复盘 |
| 修改 | `backend/app/api/app.py` | 新增 `GET /api/runs/{run_id}/trace` 导出接口 |
| 修改 | `frontend/src/App.tsx` | 事件流统一为"通知"卡片；调试日志折叠；trace 下载按钮 |
| 修改 | `frontend/src/components/ConfigPanel.tsx` | 保存确认感、未保存提醒、Key 占位回填、去滚动条 |
| 修改 | `frontend/src/api/client.ts` | 增加 `downloadRunTrace` 客户端方法 |
| 修改 | `frontend/src/styles.css` | 配置弹窗滚动条美化 |
| 新建 | `tests/unit/test_kernel_partial_success.py` | 卡片失败不杀 run + 主文档失败保留产物 |
| 修改 | `tests/unit/test_agent_kernel_models.py` | `AgentDecision.user_notice` 字段测试 |
| 新建 | `tests/unit/test_explainer_card_fallback.py` | 卡片参数兜底 |
| 新建 | `tests/unit/test_run_narrative.py` | 自述报告工具 |
| 新建 | `tests/api/test_run_trace_export.py` | trace 导出接口 |

---

## Task 1：修复致命 bug — 卡片失败不杀 run + 已写成产物不丢失（P0）

**这是最高优先级：它同时解决问题 3（写作失败）和你对"状态保留/恢复"的核心诉求。**

**Files:**
- 修改：`backend/app/agent_kernel/runtime.py`
- 修改：`backend/app/agent_kernel/pipeline.py`
- 修改：`backend/app/agent_kernel/models.py`
- 修改：`backend/app/agent_kernel/tools/artifacts.py`（卡片参数兜底）
- 新建：`tests/unit/test_kernel_partial_success.py`
- 修改：`tests/api/test_app.py`（更新旧 partial-write 断言）

---

- [ ] **Step 1.1：给 `KernelRunResult` 增加部分成功字段**

在 `backend/app/agent_kernel/models.py` 的 `KernelRunResult` 里增加两个字段：

```python
class KernelRunResult(BaseModel):
    status: KernelRunStatus
    state_version: str
    trace: list[KernelTraceEvent] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    stop_reason: str = ""
    iterations: int = 0
    failed_writes: list[str] = Field(default_factory=list)   # 失败的写作标题/工具，用于警告
    partial_success: bool = False                            # 有产物但也有失败时为 True
```

- [ ] **Step 1.2：写失败测试 — 卡片失败不应杀 run**

新建 `tests/unit/test_kernel_partial_success.py`：

```python
"""Regression tests: optional card failure must not kill a run with real artifacts."""
from __future__ import annotations

import asyncio

from backend.app.agent_kernel.models import (
    AgentActionType,
    AgentDecision,
    KernelObservation,
    KernelRunStatus,
    KernelStateDelta,
    ToolCall,
    ToolSpec,
)
from backend.app.agent_kernel.runtime import AgentKernelRuntime
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext, ToolRegistry
from backend.app.agent_state.models import SectorBreakerState
from backend.app.schemas import Artifact, ArtifactType, ResearchProject
from backend.app.schemas import MarketScope, ResearchDepth, SourcePolicy, ProjectMode
from datetime import UTC, datetime


def _project() -> ResearchProject:
    return ResearchProject(
        id="proj-001", title="T", domain="d",
        market_scope=MarketScope.MIXED, depth=ResearchDepth.QUICK,
        source_policy=SourcePolicy.RELIABLE_FIRST, project_mode=ProjectMode.DOMAIN_KNOWLEDGE,
        status="draft", created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )


class _Repo:
    def list_evidence(self, project_id): return []
    def list_documents(self, project_id): return []
    def list_artifacts(self, project_id): return []


def _make_real_artifact() -> Artifact:
    return Artifact(
        id="ART-KERNEL-L1-real001", project_id="proj-001",
        artifact_type=ArtifactType.DOMAIN_OVERVIEW, title="L1",
        content_path="docs/01-l1.md", content="# L1\n\n## S\n\n" + "x" * 800,
        schema_version="v2-agent-kernel", created_at=datetime.now(UTC),
    )


def test_card_failure_does_not_kill_run_with_real_artifacts() -> None:
    # Policy: 第 1 步已经有一篇真实主文档，第 2 步调失败的卡片，第 3 步 finish
    class Policy:
        def __init__(self): self.i = 0
        async def decide(self, **kwargs):
            self.i += 1
            if self.i == 1:
                return AgentDecision(
                    thought_summary="写卡片（会失败）",
                    action_type=AgentActionType.WRITE_ARTIFACT,
                    tool_call=ToolCall(tool_name="write_explainer_card", args={}, reason="缺参数"),
                )
            return AgentDecision(
                thought_summary="完成", action_type=AgentActionType.FINISH, stop_reason="done",
            )

    async def failing_card(tool_call, context):
        return KernelObservation(
            tool_name="write_explainer_card", success=False,
            summary="解释卡写作失败：缺少 title 或 focus。", error="missing title or focus",
        )

    registry = ToolRegistry()
    registry.register(ToolSpec(name="write_explainer_card", description="c"), failing_card)

    context = KernelRuntimeContext(
        project=_project(), repository=_Repo(), state=SectorBreakerState.initialize(
            project_id="proj-001", domain="d", user_goal="g"),
        search_provider=None, llm_provider=None, emit_event=lambda e: asyncio.sleep(0),
    )
    # 预置一篇已写成的真实主文档
    context.artifacts = [_make_real_artifact()]

    result = asyncio.run(AgentKernelRuntime(policy=Policy(), registry=registry).run(context))

    # 卡片失败不应让整轮 FAILED/BLOCKED；应该继续到 finish 并 COMPLETED
    assert result.status == KernelRunStatus.COMPLETED
    assert "ART-KERNEL-L1-real001" in result.artifact_ids
    assert result.failed_writes  # 记录了卡片失败
```

- [ ] **Step 1.3：跑测试，确认失败**

Run: `python -m pytest tests/unit/test_kernel_partial_success.py -v`
Expected: FAIL（当前卡片失败会 return FAILED/BLOCKED，status 不等于 COMPLETED）

- [ ] **Step 1.4：修改 `runtime.py` — 区分"致命写作失败"与"可跳过写作失败"**

打开 `backend/app/agent_kernel/runtime.py`，找到 `_handle_observation` 里这段（约 216 行）：

```python
        if observation.tool_name in {"write_layer_document", "write_explainer_card", "write_vault_index"} and not observation.success:
            failed = KernelTraceEvent(
                kind=TraceEventKind.BLOCKED,
                message="Blocked: LLM 写作失败，已停止运行，未导出模板或假产物。",
                data=observation.model_dump(mode="json"),
            )
            trace.append(failed)
            await self._emit(
                context,
                failed,
                gate="artifact_writing",
                agent="V2 Artifact Writer",
                severity="error",
            )
            return consecutive_failed_tools, self._result(
                KernelRunStatus.FAILED,
                context,
                trace,
                iteration,
                "artifact_writing_failed",
            )
```

替换为（辅助卡片/索引失败只记录、跳过；主文档失败也不再立即杀 run，而是记录后交由主循环决定）：

```python
        OPTIONAL_WRITERS = {"write_explainer_card", "write_vault_index"}
        MAIN_WRITERS = {"write_layer_document", "revise_layer_document"}
        if observation.tool_name in (OPTIONAL_WRITERS | MAIN_WRITERS) and not observation.success:
            self._failed_writes.append(observation.summary or observation.tool_name)
            severity = "warning" if observation.tool_name in OPTIONAL_WRITERS else "error"
            note = (
                "可选卡片/索引写作失败，已跳过，不影响主文档和整轮产物。"
                if observation.tool_name in OPTIONAL_WRITERS
                else "主文档写作失败，已记录；已写成的其它文档仍会保留。"
            )
            skip_event = KernelTraceEvent(
                kind=TraceEventKind.WARNING,
                message="Observation: " + note,
                data=observation.model_dump(mode="json"),
            )
            trace.append(skip_event)
            await self._emit(context, skip_event, gate="artifact_writing", agent="V2 Artifact Writer", severity=severity)
            # 不再 return FAILED/BLOCKED —— 交回主循环，让 Agent 决定重试/换层/finish
            consecutive_failed_tools = consecutive_failed_tools + 1
            if consecutive_failed_tools >= self.config.max_consecutive_failed_tools:
                return consecutive_failed_tools, self._result(
                    KernelRunStatus.MAX_ITERATIONS if context.artifacts else KernelRunStatus.FAILED,
                    context, trace, iteration,
                    "连续写作失败过多，已停止；已写成的产物会保留。",
                )
            return consecutive_failed_tools, None
```

在 `AgentKernelRuntime.__init__` 里初始化 `self._failed_writes`：

```python
    def __init__(self, *, policy, registry, config=None) -> None:
        self.policy = policy
        self.registry = registry
        self.config = config or KernelLoopConfig()
        self._failed_writes: list[str] = []
```

在 `run()` 方法开头（`trace = []` 那行附近）重置：

```python
        self._failed_writes = []
```

- [ ] **Step 1.5：修改 `_result` — 把 failed_writes/partial_success 带进结果**

在 `runtime.py` 的 `_result` 静态方法改为实例方法（因为要读 `self._failed_writes`），或直接在构造 `KernelRunResult` 处补字段。将 `_result` 改为：

```python
    def _result(
        self,
        status: KernelRunStatus,
        context: KernelRuntimeContext,
        trace: list[KernelTraceEvent],
        iterations: int,
        reason: str,
    ) -> KernelRunResult:
        return KernelRunResult(
            status=status,
            state_version=context.state.state_version,
            trace=trace,
            artifact_ids=[artifact.id for artifact in context.artifacts],
            stop_reason=reason,
            iterations=iterations,
            failed_writes=list(self._failed_writes),
            partial_success=bool(context.artifacts and self._failed_writes),
        )
```

注意：`_result` 原本是 `@staticmethod`，去掉该装饰器，并把所有 `self._result(...)` 调用保持不变（原来就是 `self._result`）；确认文件内没有以 `AgentKernelRuntime._result(` 形式的静态调用。

- [ ] **Step 1.6：跑测试，确认通过**

Run: `python -m pytest tests/unit/test_kernel_partial_success.py -v`
Expected: PASS

- [ ] **Step 1.7：修改 `pipeline.py` — 失败也先持久化真实产物**

打开 `backend/app/agent_kernel/pipeline.py`，找到结尾这段：

```python
    if result.status != KernelRunStatus.COMPLETED:
        raise RuntimeError("V2 Agent Kernel did not complete: " + result.status.value + " / " + result.stop_reason)
    for artifact in runtime_context.artifacts:
        repository.add_artifact(artifact)
    return runtime_context.artifacts
```

替换为（先持久化所有已写成的真实产物，再根据是否有产物决定成功/失败）：

```python
    # 先持久化所有已写成的真实产物（writer 只在通过 _usable_markdown 校验后才 append，
    # 因此 runtime_context.artifacts 中不含模板空壳；保留它们不违反"防假产物"）。
    for artifact in runtime_context.artifacts:
        repository.add_artifact(artifact)

    if runtime_context.artifacts:
        # 有真实产物即视为可用（可能是部分成功）。失败的写作以警告形式告知用户。
        if result.failed_writes:
            await emit_event(RunEvent(
                event_type="node_degraded",
                gate="artifact_writing",
                agent="V2 Agent Kernel",
                message=(
                    "本轮已生成 " + str(len(runtime_context.artifacts)) + " 篇文档；"
                    + str(len(result.failed_writes)) + " 项写作未成功，可在下一轮继续补全。"
                ),
                severity="warning",
                data={"failed_writes": result.failed_writes},
            ))
        return runtime_context.artifacts

    # 完全没有产物才算失败。此时 checkpoint 已保存，可从证据+State 恢复重跑。
    raise RuntimeError("V2 Agent Kernel produced no artifacts: " + result.status.value + " / " + result.stop_reason)
```

（`run_end` checkpoint 的保存已在 `runtime.run()` 之后、这段之前完成，失败 run 同样会留下 checkpoint，无需改动。）

- [ ] **Step 1.8：更新旧回归测试的断言**

打开 `tests/api/test_app.py`，找到 `test_api_agent_kernel_failed_run_does_not_persist_partial_artifacts`（约 428 行）。该测试原本断言"先成功一篇再失败一篇 → 产物为空"。现在语义变了：先成功的那篇**应该保留**。改断言为：

```python
def test_api_agent_kernel_failed_run_keeps_completed_artifacts(tmp_path: Path) -> None:
    llm = _partial_then_failing_kernel_writer_llm()
    client = TestClient(
        create_app(
            database_path=tmp_path / "sectorbreaker.sqlite3",
            export_root=tmp_path / "exports",
            llm_provider=llm,
        )
    )
    project = client.post(
        "/api/projects",
        json={"title": "API中转站", "domain": "API中转站", "market_scope": "mixed", "depth": "quick"},
    ).json()

    run_response = client.post(f"/api/projects/{project['id']}/runs", params={"auto_run": "true"})
    run_result = _wait_for_run(client, run_response.json()["id"])

    # 第一篇真实文档已写成 → 应保留；run 不再因第二篇失败而丢弃全部产物
    artifacts = client.get(f"/api/projects/{project['id']}/artifacts").json()
    assert len(artifacts) == 1
    assert artifacts[0]["title"] == "L1 本源与需求"
```

同时确认 `test_api_agent_kernel_writer_failure_marks_run_failed_without_artifacts`（第一篇就失败、没有任何产物）仍应 `status == "failed"` 且 `artifacts == []` —— 这条测试语义不变，保留。

- [ ] **Step 1.9：卡片参数兜底 — `write_explainer_card` 缺 title 时从 focus 补**

打开 `backend/app/agent_kernel/tools/artifacts.py`，找到 `write_explainer_card` 里这段：

```python
    title = str(tool_call.args.get("title") or "").strip()
    focus = str(tool_call.args.get("focus") or title).strip()
    writing_goal = str(tool_call.args.get("writing_goal") or "").strip()
    if not title or not focus:
        return KernelObservation(
            tool_name="write_explainer_card",
            success=False,
            summary="解释卡写作失败：缺少 title 或 focus。",
            error="missing title or focus",
        )
```

替换为（title 缺失时从 focus 兜底，focus 缺失时从 title 兜底，二者皆空才失败）：

```python
    title = str(tool_call.args.get("title") or "").strip()
    focus = str(tool_call.args.get("focus") or "").strip()
    writing_goal = str(tool_call.args.get("writing_goal") or "").strip()
    if not title and focus:
        title = focus[:60]
    if not focus and title:
        focus = title
    if not title and not focus:
        return KernelObservation(
            tool_name="write_explainer_card",
            success=False,
            summary="解释卡跳过：未提供 title 或 focus，无法确定卡片主题。",
            error="missing title and focus",
        )
```

- [ ] **Step 1.10：跑全量相关回归**

Run: `python -m pytest tests/unit/test_kernel_partial_success.py tests/unit/test_agent_kernel_runtime.py tests/unit/test_agent_kernel_tools.py tests/api/test_app.py::test_api_agent_kernel_failed_run_keeps_completed_artifacts tests/api/test_app.py::test_api_agent_kernel_writer_failure_marks_run_failed_without_artifacts -v`
Expected: 全部 PASS

- [ ] **Step 1.11：提交**

```bash
git add backend/app/agent_kernel/runtime.py backend/app/agent_kernel/pipeline.py backend/app/agent_kernel/models.py backend/app/agent_kernel/tools/artifacts.py tests/unit/test_kernel_partial_success.py tests/api/test_app.py
git commit -m "fix: 卡片失败不再杀整轮 run，已写成的真实文档保留并可从断点恢复"
```

---

## Task 2：Agent 叙述人性化 — LLM 决策时同步产出"一句人话通知"

**问题 2 的核心：** 现在给用户看的原文是
> `调用 revise_layer_document：L1已标记ready_to_write且partial_material_ready=True，不应继续无目标搜索。修订版可以记录知识框架和缺口，解放cognitive cycle进入L2。`

**根因（排查结论）：** `runtime.py` 给用户看的 Action 文案是 `f"Action: {tool_call.tool_name} - {tool_call.reason}"`，而 `reason` 是 **LLM 自己生成的**——上面那句 jargon 就是 LLM 写进 `reason` 的。问题不在"没翻译"，而在于 **prompt 从没要求 LLM 讲人话**，且 `AgentDecision` 里没有一个专门面向用户的字段。

**正确设计（不要硬编码枚举）：** Agent 在决策时本来就知道自己"为什么这么做"。所以让 LLM 在输出 `AgentDecision` 的**同一次调用**里，顺带生成一句面向用户的自然语言通知 `user_notice`——就像 Claude Code 在动手前先说一句"我要先读 package.json 确认依赖版本"。这句话**实时随决策产出**，覆盖任意工具（包括未来新增的），零 `if tool_name == ...` 枚举。prompt 里立规矩：`user_notice` 面向不懂技术的用户，禁止出现 `L1`/`ready_to_write`/`coverage_score` 等内部术语。

> **反面教材（不要这样做）：** 写一个 `narrate_action(tool_name, args, reason)` 函数，用一长串 `if tool_name == "search_web": return "我在搜索…"` 把每个工具的话术写死。这既无法覆盖新工具、又把叙述质量锁死在预设模板里、还每加一个工具就要回来改代码。叙述必须由掌握实时上下文的 LLM 生成，不是由代码事后拼。

**同类问题一并修正：** 前端 `App.tsx` 的 `summarizeStateUpdate` 把 `sources+N` 硬编码翻译成"新增 N 个来源"，`buildAgentBriefCards` 用 `startsWith("Thought Summary:")` 等前缀把事件硬分成"Agent 判断/准备行动/状态更新/下一步决策"四五个类别——这正是你说的"分类太多"。有了 `user_notice` 后，这些降级为纯 fallback（仅在旧数据无 `user_notice` 时启用）。

**Files:**
- 修改：`backend/app/agent_kernel/models.py`（`AgentDecision` 增加 `user_notice` 字段）
- 修改：`backend/app/agents/prompts/tool_decision.md`（要求 LLM 生成 `user_notice`，立禁术语规矩）
- 修改：`backend/app/agent_kernel/runtime.py`（用 `decision.user_notice` 作为面向用户的事件文案）
- 修改：`frontend/src/App.tsx`（优先展示 `user_notice`，统一为单一"进展"卡片，旧分类降级为 fallback）
- 修改：`tests/unit/test_agent_kernel_models.py`（`AgentDecision` 默认值兼容）

---

- [ ] **Step 2.1：给 `AgentDecision` 增加 `user_notice` 字段**

打开 `backend/app/agent_kernel/models.py`，在 `AgentDecision` 里加一个字段（放在 `thought_summary` 之后）：

```python
class AgentDecision(BaseModel):
    thought_summary: str
    user_notice: str = ""      # ← 面向用户的一句人话通知，由 LLM 在决策时同步生成
    action_type: AgentActionType
    tool_call: ToolCall | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    state_delta: KernelStateDelta | None = None
    expected_observation: str = ""
    stop_reason: str = ""
    current_goal: str = ""
    plan_steps: list[str] = Field(default_factory=list)
    progress_check: str = ""
```

`user_notice` 与 `thought_summary` 的分工：
- `thought_summary`：给会读技术细节的人看的审计摘要，可以提到覆盖度、证据状态等。
- `user_notice`：给完全不懂技术的普通用户看的一句话，说清"我现在在做什么、为什么"，禁止任何内部术语。默认空字符串保证向后兼容（旧数据/未生成时不报错）。

- [ ] **Step 2.2：写失败测试 — user_notice 字段存在且可选**

打开 `tests/unit/test_agent_kernel_models.py`，在末尾追加：

```python
def test_agent_decision_accepts_user_notice() -> None:
    from backend.app.agent_kernel.models import AgentDecision, AgentActionType, ToolCall
    decision = AgentDecision(
        thought_summary="L1 coverage_score 足够，准备写作。",
        user_notice="我已经收集够资料了，现在开始撰写这个领域的入门介绍。",
        action_type=AgentActionType.WRITE_ARTIFACT,
        tool_call=ToolCall(tool_name="write_layer_document", args={"title": "本源与边界"}, reason="x"),
    )
    assert decision.user_notice.startswith("我")


def test_agent_decision_user_notice_defaults_empty() -> None:
    from backend.app.agent_kernel.models import AgentDecision, AgentActionType
    decision = AgentDecision(
        thought_summary="finish",
        action_type=AgentActionType.FINISH,
        stop_reason="done",
    )
    assert decision.user_notice == ""   # 向后兼容：旧调用不填也不报错
```

- [ ] **Step 2.3：跑测试确认失败**

Run: `python -m pytest tests/unit/test_agent_kernel_models.py -v -k user_notice`
Expected: 若字段未加会 FAIL；加完 Step 2.1 后应 PASS（先跑确认字段行为）

- [ ] **Step 2.4：在 `tool_decision.md` 要求 LLM 生成 `user_notice`（立禁术语规矩）**

打开 `backend/app/agents/prompts/tool_decision.md`。

(a) 在 `## Required Output` 的 JSON 示例里，`thought_summary` 下面加一行 `user_notice`：

```json
{
  "thought_summary": "用户可见的简短推理摘要，说明当前理解、为什么选择此 action，不暴露隐藏 chain-of-thought。",
  "user_notice": "我现在要联网查一下这个领域的商业模式和定价，因为前面的资料还没讲清楚它们靠什么赚钱。",
  "action_type": "call_tool",
```

（第二个 `tool_calls` 示例的 JSON 也同样加一行 `user_notice`，写一句对应那个动作的人话，例如："我先看看目前收集的资料够不够，再决定要不要补搜。"）

(b) 把现有的 `## Thought Summary Rules` 小节改名为 `## User-Facing Narration Rules`，并在其后追加对 `user_notice` 的硬性要求：

```markdown
## User-Facing Narration Rules

每个决策必须同时产出两段面向不同读者的文字：

### thought_summary（给能读技术细节的人）
- 你现在理解的任务状态、为什么这个动作是下一步、期望观察到什么、有无证据/覆盖/安全风险。
- 不输出隐藏 chain-of-thought、逐步内心推导或长篇自我辩论。

### user_notice（给完全不懂技术的普通用户，这是产品主界面唯一展示给用户的一句话）
- 用第一人称、口语化，一句话讲清"我现在在做什么、为什么做"。就像一个研究员在旁边轻声解说。
- 参考风格（Claude Code 动手前先说一句）：
  - "我先去查一下这个行业主要有哪些玩家。"
  - "资料里对它怎么赚钱说得不清楚，我再补搜一下商业模式。"
  - "入门资料够了，我现在开始写这个领域的第一篇介绍。"
  - "有个词可能新手看不懂，我单独写一张卡片解释它。"
- 严禁出现任何内部术语或参数名：不要写 `L1`/`L2`、`ready_to_write`、`coverage_score`、`partial_material_ready`、`cognitive cycle`、`state_delta`、`layer_id`、`=True/=False`。
- 不要提"层级""schema""字段""标记为"这类实现概念。用户不知道我们后台分了几层。
- 如果动作是内部整理（如更新记忆、评估覆盖度），也要翻译成用户能懂的话，例如"我把刚查到的信息整理一下"。
- 长度控制在一句话（建议 40 字以内）。
```

- [ ] **Step 2.5：runtime 用 `decision.user_notice` 作为面向用户的事件文案**

打开 `backend/app/agent_kernel/runtime.py`。

(a) 找到 `run()` 里构造并 emit `thought` 事件的地方（约 49 行）。当前它 emit 的 message 是 `f"Thought Summary: {decision.thought_summary}"`。改为优先用 `user_notice`（回退到 thought_summary），并把原始结构化信息放进 data：

```python
            user_text = (decision.user_notice or "").strip() or decision.thought_summary
            thought = KernelTraceEvent(
                kind=TraceEventKind.THOUGHT,
                message=user_text,                       # 面向用户：一句人话
                data={
                    **decision.model_dump(mode="json"),  # 原始 thought_summary/current_goal 等留作调试细节
                    "user_notice": decision.user_notice,
                },
            )
            trace.append(thought)
            await self._emit(context, thought, gate="agent_decide", agent="V2 Master Agent")
```

(b) 找到构造 `action_event` 的地方（约 105 行）。当前 message 是 `f"Action: {tool_call.tool_name} - {tool_call.reason}"`——`reason` 正是 jargon 来源。改为：面向用户的 message 用 `decision.user_notice`，把 `tool_name`/`reason` 降级进 data：

```python
                action_event = KernelTraceEvent(
                    kind=TraceEventKind.ACTION,
                    message=(decision.user_notice or "").strip() or f"{tool_call.tool_name}",
                    data={
                        **tool_call.model_dump(mode="json"),   # tool_name/reason/args 作为调试细节
                        "current_goal": decision.current_goal,
                        "plan_steps": decision.plan_steps,
                        "progress_check": decision.progress_check,
                        "user_notice": decision.user_notice,
                    },
                )
```

注意：不要再把 `tool_call.reason` 拼进面向用户的 message。`reason` 只保留在 `data` 里供调试日志查看。

- [ ] **Step 2.6：编译检查**

Run: `python -m py_compile backend/app/agent_kernel/models.py backend/app/agent_kernel/runtime.py`
Expected: 无输出

- [ ] **Step 2.7：前端 — 事件流统一为单一"进展"通知，旧分类降级为 fallback**

打开 `frontend/src/App.tsx`，找到 `buildAgentBriefCards`（约 283 行）。在 `events.forEach((event, index) => {` 内部、`let card ...` 之后，加一个**最高优先分支**：只要事件带 `data.user_notice`（或 message 本身已是人话），就统一成一张"进展"卡片，原始 message/结构化字段折叠进 detail：

```typescript
  events.forEach((event, index) => {
    const raw = event.message || "";
    let card: AgentBriefCard | null = null;

    // 最高优先：LLM 决策时同步生成的面向用户通知
    const data = (event.data || {}) as Record<string, unknown>;
    const userNotice = typeof data.user_notice === "string" ? data.user_notice.trim() : "";
    if (userNotice) {
      const debugDetail = [
        typeof data.reason === "string" ? `原因: ${data.reason}` : "",
        typeof data.current_goal === "string" ? `目标: ${data.current_goal}` : "",
        raw && raw !== userNotice ? `原始: ${raw}` : "",
      ].filter(Boolean).join("\n");
      cards.push({
        id: `${event.timestamp}-${index}-notice`,
        label: "进展",
        summary: userNotice,
        detail: debugDetail || undefined,   // 术语/结构化信息只在展开的调试细节里
        tone: event.severity === "error" ? "warning" : raw.startsWith("Observation:") ? "result" : "action",
        importance: "primary",
        timestamp: event.timestamp,
      });
      return;
    }

    // ↓ 以下旧的 startsWith("Thought Summary:")/"Action:"/"State Update:" 分类逻辑
    //   仅作为 fallback 保留（用于没有 user_notice 的历史事件），不再是主路径。
    if (raw.startsWith("Thought Summary:")) {
```

（保留原有所有 `if (raw.startsWith(...))` 分支不动，它们现在只在没有 `user_notice` 时兜底。）

- [ ] **Step 2.8：前端构建 + 已有测试回归**

Run: `cd frontend && npm run build && npm test -- --run App.test.tsx`
Expected: 全部 PASS（`buildAgentBriefCards` 的旧测试仍走 fallback 分支，不受影响）

- [ ] **Step 2.9：提交**

```bash
git add backend/app/agent_kernel/models.py backend/app/agents/prompts/tool_decision.md backend/app/agent_kernel/runtime.py frontend/src/App.tsx tests/unit/test_agent_kernel_models.py
git commit -m "feat: Agent 决策时同步产出面向用户的 user_notice，禁术语，前端统一为单一进展通知"
```

---

## Task 3：思考日志留存 + Agent 自述报告

**问题 4 的核心：** 完整的思考轨迹（已存在 `trace_summary.json`）是调优的金矿——正是它让我们 3 步定位了这次的失败真凶。但现在只能翻导出目录里的 JSON，不能在 UI 直接拿到；也没有"Agent 用人话讲讲它怎么调研的"的复盘。同时用户担心"99 条搜索结果是否都用得上"——自述报告正好能暴露证据利用率。

**Files:**
- 修改：`backend/app/api/app.py`（新增 `GET /api/runs/{run_id}/trace` 导出接口）
- 新建：`backend/app/agent_kernel/tools/narrative.py`（`generate_run_narrative` 工具）
- 修改：`backend/app/agent_kernel/tools/__init__.py`（注册工具）
- 修改：`frontend/src/api/client.ts`（`downloadRunTrace` 方法）
- 修改：`frontend/src/App.tsx`（trace 下载按钮）
- 新建：`tests/unit/test_run_narrative.py`
- 新建：`tests/api/test_run_trace_export.py`

---

- [ ] **Step 3.1：写 trace 导出接口的失败测试**

新建 `tests/api/test_run_trace_export.py`：

```python
"""Tests for GET /api/runs/{run_id}/trace export endpoint."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.schemas import RunEvent


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(
        database_path=tmp_path / "sb.sqlite3",
        export_root=tmp_path / "exports",
    ))


def test_trace_export_returns_all_run_events(tmp_path: Path) -> None:
    client = _client(tmp_path)
    project = client.post("/api/projects", json={
        "title": "T", "domain": "d", "market_scope": "mixed", "depth": "quick",
    }).json()
    run = client.post(f"/api/projects/{project['id']}/runs").json()

    resp = client.get(f"/api/runs/{run['id']}/trace")
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body
    assert "events" in body
    assert isinstance(body["events"], list)


def test_trace_export_404_for_unknown_run(tmp_path: Path) -> None:
    client = _client(tmp_path)
    resp = client.get("/api/runs/nonexistent/trace")
    assert resp.status_code == 404
```

- [ ] **Step 3.2：跑测试确认失败**

Run: `python -m pytest tests/api/test_run_trace_export.py -v`
Expected: FAIL（接口不存在，返回 404 但 `test_trace_export_returns_all_run_events` 也 404）

- [ ] **Step 3.3：实现 trace 导出接口**

打开 `backend/app/api/app.py`，找到 `@app.get("/api/runs/{run_id}/events")`（约 1010 行），在它前面新增：

```python
    @app.get("/api/runs/{run_id}/trace")
    def export_run_trace(run_id: str):
        """Export the full run trace (all events) for debugging and tuning analysis."""
        try:
            run = repository.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc
        events = repository.list_run_events(run_id)
        return {
            "run_id": run_id,
            "project_id": run.project_id,
            "status": run.status.value,
            "event_count": len(events),
            "events": [event.model_dump(mode="json") for event in events],
        }
```

- [ ] **Step 3.4：跑测试确认通过**

Run: `python -m pytest tests/api/test_run_trace_export.py -v`
Expected: PASS（2 passed）

- [ ] **Step 3.5：写自述报告工具的失败测试**

新建 `tests/unit/test_run_narrative.py`：

```python
"""Tests for the generate_run_narrative tool (first-person research recap)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.app.agent_kernel.models import ToolCall
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.narrative import generate_run_narrative
from backend.app.agent_state.models import SectorBreakerState
from backend.app.providers.fakes import FakeLLMProvider
from backend.app.schemas import (
    Artifact, ArtifactType, ResearchProject,
    MarketScope, ResearchDepth, SourcePolicy, ProjectMode,
)


def _project() -> ResearchProject:
    return ResearchProject(
        id="proj-001", title="T", domain="情趣用品",
        market_scope=MarketScope.MIXED, depth=ResearchDepth.QUICK,
        source_policy=SourcePolicy.RELIABLE_FIRST, project_mode=ProjectMode.DOMAIN_KNOWLEDGE,
        status="draft", created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )


def _context(llm) -> KernelRuntimeContext:
    state = SectorBreakerState.initialize(project_id="proj-001", domain="情趣用品", user_goal="建库")
    state.evidence_refs = [f"EV-{i}" for i in range(99)]
    ctx = KernelRuntimeContext(
        project=_project(), repository=None, state=state,
        search_provider=None, llm_provider=llm, emit_event=lambda e: asyncio.sleep(0),
    )
    ctx.artifacts = [
        Artifact(id="ART-KERNEL-L1-a", project_id="proj-001", artifact_type=ArtifactType.DOMAIN_OVERVIEW,
                 title="本源与边界", content_path="docs/01.md", content="x" * 800,
                 schema_version="v2-agent-kernel", created_at=datetime.now(UTC)),
    ]
    return ctx


def test_generate_run_narrative_creates_first_person_report() -> None:
    narrative_text = (
        "# 我是怎么调研情趣用品这个领域的\n\n"
        "## 起点\n\n我先搞清楚这个领域是什么。\n\n"
        "## 搜索与发现\n\n我一共搜索了 99 条资料，发现监管信息不足，于是又补搜了政策。\n\n"
        "## 我的判断\n\n我认为已经覆盖了核心层。"
    )
    llm = FakeLLMProvider(response=narrative_text)
    ctx = _context(llm)
    tool_call = ToolCall(tool_name="generate_run_narrative", args={}, reason="收尾复盘")
    obs = asyncio.run(generate_run_narrative(tool_call, ctx))

    assert obs.success is True
    # 生成了一个 narrative artifact
    narrative_artifacts = [a for a in ctx.artifacts if a.artifact_type == ArtifactType.FOLLOW_UP_NOTE or "调研" in a.title]
    assert narrative_artifacts
    assert obs.artifact_ids


def test_generate_run_narrative_without_llm_fails_gracefully() -> None:
    ctx = _context(llm=None)
    tool_call = ToolCall(tool_name="generate_run_narrative", args={}, reason="test")
    obs = asyncio.run(generate_run_narrative(tool_call, ctx))
    assert obs.success is False
```

- [ ] **Step 3.6：跑测试确认失败**

Run: `python -m pytest tests/unit/test_run_narrative.py -v`
Expected: FAIL（`narrative` 模块不存在）

- [ ] **Step 3.7：实现 `generate_run_narrative` 工具**

新建 `backend/app/agent_kernel/tools/narrative.py`：

```python
"""generate_run_narrative: first-person research recap of how the Agent investigated."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from backend.app.agent_kernel.models import KernelObservation, KernelStateDelta
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.providers.interfaces import ChatMessage
from backend.app.schemas import Artifact, ArtifactType


async def generate_run_narrative(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    """Ask the LLM to write a first-person account of the research process."""
    if context.llm_provider is None:
        return KernelObservation(
            tool_name="generate_run_narrative",
            success=False,
            summary="无法生成调研复盘：未配置 LLM。",
            error="llm provider not configured",
        )

    state = context.state
    evidence_count = len(state.evidence_refs)
    artifact_titles = [a.title for a in context.artifacts]
    claim_count = len(state.shared_knowledge.claims)
    open_qs = [q.question for q in state.shared_knowledge.open_questions if not q.resolved][:12]
    decisions = [d.reason for d in state.decision_log][-20:]

    prompt = (
        "你是这次领域调研的 Agent。请用第一人称、面向普通用户，"
        "讲清楚你是怎么一步步把这个领域搞明白的。像一个人在复盘自己的研究过程，"
        "不要用内部术语（如 layer_id、ready_to_write、coverage_score）。\n\n"
        f"领域：{context.project.domain}\n"
        f"我一共收集了 {evidence_count} 条证据，提炼了 {claim_count} 条要点。\n"
        f"我最终写成的文档：{', '.join(artifact_titles) or '（无）'}\n"
        f"我做过的一些判断（内部记录，供你参考，不要照抄术语）：\n"
        + "\n".join(f"- {d}" for d in decisions) + "\n\n"
        f"我还没完全解决的问题：\n" + "\n".join(f"- {q}" for q in open_qs) + "\n\n"
        "请输出 Markdown，结构建议：\n"
        "## 我想搞清楚什么\n## 我是怎么找资料的\n## 中途遇到的问题和调整\n"
        "## 我最后弄明白了什么\n## 还没解决、值得继续挖的\n\n"
        "特别说明：如果收集的资料很多，请诚实说明哪些用上了、哪些暂时没用上，帮用户判断信息利用情况。"
    )
    try:
        raw = await context.llm_provider.complete([ChatMessage(role="user", content=prompt)])
    except Exception as exc:
        return KernelObservation(
            tool_name="generate_run_narrative",
            success=False,
            summary=f"调研复盘生成失败：{type(exc).__name__}",
            error=str(exc)[:300],
        )
    content = str(raw).strip()
    if len(content) < 200:
        return KernelObservation(
            tool_name="generate_run_narrative",
            success=False,
            summary="调研复盘内容过短，未保存。",
            error="narrative too short",
        )

    artifact = Artifact(
        id=f"ART-KERNEL-NARRATIVE-{uuid4().hex[:8]}",
        project_id=context.project.id,
        artifact_type=ArtifactType.FOLLOW_UP_NOTE,
        title=f"调研复盘：我是怎么研究{context.project.domain}的",
        content_path=f"docs/00-调研复盘.md",
        content=content,
        source_evidence_ids=list(dict.fromkeys(state.evidence_refs)),
        schema_version="v2-agent-kernel",
        created_at=datetime.now(UTC),
    )
    context.artifacts.append(artifact)
    return KernelObservation(
        tool_name="generate_run_narrative",
        success=True,
        summary=f"已生成调研复盘（{len(content)} 字符），讲清楚了本轮研究思路和信息利用情况。",
        data={"artifact": artifact.model_dump(mode="json")},
        state_delta=KernelStateDelta(artifact_ids=[artifact.id]),
        artifact_ids=[artifact.id],
    )
```

- [ ] **Step 3.8：注册工具**

打开 `backend/app/agent_kernel/tools/__init__.py`，先读取现有 `build_default_tool_registry` 结构，然后在注册区加入：

```python
    from backend.app.agent_kernel.models import ToolSpec
    from backend.app.agent_kernel.tool_registry import schema
    from backend.app.agent_kernel.tools.narrative import generate_run_narrative
    registry.register(
        ToolSpec(
            name="generate_run_narrative",
            description="Write a first-person recap of how the Agent researched this domain, including honest notes on which evidence was used.",
            args_schema=schema({"reason": {"type": "string"}}),
        ),
        generate_run_narrative,
    )
```

（具体插入位置：在 `register_artifact_tools(registry)` 调用之后。如果 `__init__.py` 用的是分模块注册函数，就仿照 `register_artifact_tools` 的模式加一行调用。执行时先读该文件确认结构。）

- [ ] **Step 3.9：跑测试确认通过**

Run: `python -m pytest tests/unit/test_run_narrative.py -v`
Expected: PASS（2 passed）

- [ ] **Step 3.10：前端加 trace 下载 + narrative 提示**

打开 `frontend/src/api/client.ts`，在 `api` 对象里（`getRunSnapshot` 附近）加一个方法。该文件统一用内部 `requestJson<T>(path, init?)` 辅助函数发请求，仿照它写：

```typescript
  getRunTrace(runId: string) {
    return requestJson<{
      run_id: string;
      project_id: string;
      status: string;
      event_count: number;
      events: RunEvent[];
    }>(`/api/runs/${runId}/trace`);
  },
```

（`RunEvent` 类型该文件已定义/导入；若未导入，在顶部 import 处补上。下载动作在 App.tsx 里完成，见 Step 3.10。）

打开 `frontend/src/App.tsx`，在运行结果区（有 export/artifact 的地方）加一个"下载思考日志"按钮：

```tsx
<button
  className="secondary"
  type="button"
  onClick={async () => {
    const id = runId || latest?.run_id;
    if (!id) return;
    const data = await api.getRunTrace(id as string);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `run-trace-${id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }}
>
  下载思考日志
</button>
```

（执行时先在 App.tsx 里搜索现有的"导出"或"下载"按钮，把这个按钮放在同一容器里，复用 `runId` 变量名；变量名以文件实际为准。）

- [ ] **Step 3.11：前端构建检查**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 3.12：提交**

```bash
git add backend/app/api/app.py backend/app/agent_kernel/tools/narrative.py backend/app/agent_kernel/tools/__init__.py frontend/src/api/client.ts frontend/src/App.tsx tests/unit/test_run_narrative.py tests/api/test_run_trace_export.py
git commit -m "feat: 思考日志可导出 + Agent 第一人称调研复盘报告"
```

---

## Task 4：配置面板确认感 — 未保存提醒 + 当前模型高亮 + Key 回填 + 去滚动条

**问题 1 的核心：**
- 选了 Mimo 但"保存按钮点不了"，关掉窗口后实际用的不是 Mimo → 缺少"当前生效模型"的明确反馈，也不知道存没存
- 选已保存预设，加载后 base_url 有、但 Key 不显示 → 用户想改 Key 时是黑盒
- 弹窗右侧有丑陋滚动条

**设计原则（用户原话）：** 选预设 = 把预设加载进设置框（和保存预设对称，都要有可见内容）；检测到改动未保存就提醒；保存后前端显示"当前模型 xxx"。

**Files:**
- 修改：`frontend/src/components/ConfigPanel.tsx`
- 修改：`frontend/src/styles.css`

---

- [ ] **Step 4.1：应用预设时回填 Key 占位符，明确"已存 Key"状态**

打开 `frontend/src/components/ConfigPanel.tsx`，找到 `applyPresetToForm`（约 85 行）。当前它把 `apiKey` 清空（`setApiKey("")`），导致用户看不到"这个预设有没有 Key"。改为根据 `preset.has_api_key` 给出可见反馈：

```typescript
  function applyPresetToForm(presetId: string) {
    setSelectedPresetId(presetId);
    const preset = llmPresets.find((item) => item.id === presetId);
    if (!preset) return;
    setPresetName(preset.name);
    setBaseUrl(preset.base_url || "");
    setModel(preset.model || "");
    setMaxTokens(preset.max_tokens || 4096);
    setPresetNotes(preset.notes || "");
    // 已保存过 Key 的预设：用占位提示告诉用户"已有 Key，留空即沿用；要换 Key 就直接输入"
    setApiKey("");
    setPresetHasStoredKey(Boolean(preset.has_api_key));
    setDirty(false);  // 刚加载完，视为未改动
  }
```

在组件顶部 state 区新增两个 state：

```typescript
  const [presetHasStoredKey, setPresetHasStoredKey] = useState(false);
  const [dirty, setDirty] = useState(false);
```

把 API Key 输入框的 placeholder 改为动态提示（找到 `id="apiKey"` 的 `<input>`）：

```tsx
                  <input
                    id="apiKey"
                    type={showApiKey ? "text" : "password"}
                    value={apiKey}
                    onChange={(e) => { setApiKey(e.target.value); setDirty(true); }}
                    placeholder={presetHasStoredKey ? "已保存 Key（留空沿用，输入则覆盖）" : "sk-..."}
                  />
```

- [ ] **Step 4.2：base_url / model / maxTokens 改动时标记 dirty**

在 `ConfigPanel.tsx` 里，给这三个输入框的 `onChange` 都加上 `setDirty(true)`。找到对应 `<input>`：

```tsx
                  <input id="baseUrl" ... onChange={(e) => { setBaseUrl(e.target.value); setDirty(true); }} ... />
                  <input id="model" ... onChange={(e) => { setModel(e.target.value); setDirty(true); }} ... />
                  <input id="maxTokens" ... onChange={(e) => { setMaxTokens(Number(e.target.value || 4096)); setDirty(true); }} ... />
```

保存成功后清除 dirty。找到 `handleSave` 的成功分支，加 `setDirty(false)`：

```typescript
    try {
      await api.updateLLMConfig({ base_url: baseUrl, api_key: apiKey, model, max_tokens: maxTokens });
      onSuccess("LLM 配置已保存，当前生效模型：" + model);
      setDirty(false);
      await fetchConfigStatus();   // 刷新"当前已配置"高亮
      onConfigChanged?.();
    } catch (err) {
```

- [ ] **Step 4.3：当前生效模型高亮 + 未保存提醒条**

找到 `modal-body` 顶部的 `configStatus?.configured` 块（约 331 行），替换为更醒目的当前模型条 + 未保存提醒：

```tsx
          {configStatus?.configured && (
            <div className="config-status configured">
              <CheckCircle2 size={16} />
              <span>当前生效模型：<strong>{configStatus.model}</strong></span>
            </div>
          )}
          {dirty && (
            <div className="config-status unsaved">
              <span>⚠️ 配置已修改但尚未保存。点击底部「保存配置」使其生效。</span>
            </div>
          )}
```

- [ ] **Step 4.4：关闭窗口时若有未保存改动则二次确认**

找到 `modal-header` 里的关闭按钮（约 325 行），改为：

```tsx
          <button className="modal-close" onClick={() => {
            if (dirty && !window.confirm("当前 LLM 配置尚未保存，确定关闭吗？未保存的修改不会生效。")) {
              return;
            }
            onClose();
          }}>
            &times;
          </button>
```

- [ ] **Step 4.5：让"保存配置"按钮在缺 Key 但预设已存 Key 时也可点**

问题 1 里"保存按钮点不了"是因为 `disabled={isSaving || !baseUrl || !apiKey || !model}` 要求 apiKey 非空。但选了已存 Key 的预设时，apiKey 框是空的（Key 在后端）。用 `applyLLMPreset` 走预设应用路径解决——找到底部"保存配置"按钮，改为：当 `presetHasStoredKey && !apiKey` 时，点击走 `handleApplyPreset`（应用预设，复用后端已存 Key），否则走 `handleSave`：

```tsx
          <button
            className="primary"
            onClick={presetHasStoredKey && !apiKey ? handleApplyPreset : handleSave}
            disabled={isSaving || isApplyingPreset || !baseUrl || !model || (!apiKey && !presetHasStoredKey)}
          >
            {(isSaving || isApplyingPreset) ? (
              <>
                <Loader2 size={16} className="spinner" />
                保存中...
              </>
            ) : (
              "保存配置"
            )}
          </button>
```

同时在 `handleApplyPreset` 成功分支加 `setDirty(false)` 和当前模型提示：

```typescript
      const result = await api.applyLLMPreset(selectedPresetId, { api_key: apiKey || undefined });
      await fetchConfigStatus();
      await fetchLlmPresets();
      setDirty(false);
      onConfigChanged?.();
      onSuccess((result.message || "LLM 预设已应用") + "，当前生效模型：" + model);
```

- [ ] **Step 4.6：去掉丑陋滚动条**

打开 `frontend/src/styles.css`，找到 `.config-modal` 或 `.modal-content`（配置弹窗）的样式。新增/调整滚动区样式，让滚动条更细或隐藏但保留滚动能力。在文件末尾追加：

```css
/* 配置弹窗：美化滚动条 */
.config-modal .modal-body {
  scrollbar-width: thin;                /* Firefox */
  scrollbar-color: rgba(148, 163, 184, 0.5) transparent;
}
.config-modal .modal-body::-webkit-scrollbar {
  width: 8px;
}
.config-modal .modal-body::-webkit-scrollbar-track {
  background: transparent;
}
.config-modal .modal-body::-webkit-scrollbar-thumb {
  background-color: rgba(148, 163, 184, 0.5);
  border-radius: 4px;
}
.config-modal .modal-body::-webkit-scrollbar-thumb:hover {
  background-color: rgba(148, 163, 184, 0.8);
}
/* 未保存提醒条 */
.config-status.unsaved {
  background: rgba(251, 191, 36, 0.12);
  color: #b45309;
  border: 1px solid rgba(251, 191, 36, 0.35);
}
```

- [ ] **Step 4.7：前端构建检查**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 4.8：前端已有测试回归**

Run: `cd frontend && npm test -- --run App.test.tsx`
Expected: PASS（现有数量不减）

- [ ] **Step 4.9：提交**

```bash
git add frontend/src/components/ConfigPanel.tsx frontend/src/styles.css
git commit -m "feat: LLM 配置面板加保存确认感 — 当前模型高亮/未保存提醒/Key 回填/滚动条美化"
```

---

## Task 5：并行补卡 — 主循环串行，辅助卡片批量并发

**问题 5 的核心：** 主 Agent 串行把控全局是对的；但"补充解释卡"这类互不依赖、不受前后顺序影响的工作可以并行。让主 Agent 一次决定"补这 N 张卡"，由一个批量工具用 `asyncio.gather` 并发生成。

**Files:**
- 修改：`backend/app/agent_kernel/tools/artifacts.py`（新增 `write_explainer_cards_batch`）
- 修改：`backend/app/agent_kernel/tools/__init__.py`（注册）
- 新建：`tests/unit/test_explainer_cards_batch.py`

---

- [ ] **Step 5.1：写失败测试 — 批量并发补卡**

新建 `tests/unit/test_explainer_cards_batch.py`：

```python
"""Tests for write_explainer_cards_batch — parallel generation of independent cards."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.app.agent_kernel.models import ToolCall
from backend.app.agent_kernel.tool_registry import KernelRuntimeContext
from backend.app.agent_kernel.tools.artifacts import write_explainer_cards_batch
from backend.app.agent_state.models import SectorBreakerState
from backend.app.providers.fakes import FakeLLMProvider
from backend.app.schemas import ResearchProject, MarketScope, ResearchDepth, SourcePolicy, ProjectMode


def _project() -> ResearchProject:
    return ResearchProject(
        id="proj-001", title="T", domain="情趣用品",
        market_scope=MarketScope.MIXED, depth=ResearchDepth.QUICK,
        source_policy=SourcePolicy.RELIABLE_FIRST, project_mode=ProjectMode.DOMAIN_KNOWLEDGE,
        status="draft", created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )


class _CountingLLM(FakeLLMProvider):
    """Return a usable card body and count concurrent calls."""
    def __init__(self):
        super().__init__(response="")
        self.active = 0
        self.max_active = 0

    async def complete(self, messages):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.05)  # 模拟网络延迟，制造并发窗口
        self.active -= 1
        return (
            "# 概念卡\n\n## 一句话解释\n\n这是一个概念。\n\n"
            "## 为什么重要\n\n因为它是基础。\n\n## 如何运作\n\n它这样运作。\n\n"
            "## 关系\n\n关联主文档 [[本源与边界]]。" + "内容补充。" * 40
        )


def test_batch_generates_all_cards(tmp_path) -> None:
    llm = _CountingLLM()
    state = SectorBreakerState.initialize(project_id="proj-001", domain="情趣用品", user_goal="建库")
    ctx = KernelRuntimeContext(
        project=_project(), repository=None, state=state,
        search_provider=None, llm_provider=llm, emit_event=lambda e: asyncio.sleep(0),
    )
    tool_call = ToolCall(
        tool_name="write_explainer_cards_batch",
        args={"cards": [
            {"title": "润滑剂类型", "focus": "水基/硅基区别", "card_kind": "concept"},
            {"title": "材质安全", "focus": "医用硅胶", "card_kind": "concept"},
            {"title": "主要品牌", "focus": "头部玩家", "card_kind": "player"},
        ]},
        reason="批量补 3 张解释卡",
    )
    obs = asyncio.run(write_explainer_cards_batch(tool_call, ctx))

    assert obs.success is True
    assert len(obs.artifact_ids) == 3          # 三张卡都生成了
    assert len(ctx.artifacts) == 3
    assert llm.max_active >= 2                  # 确实发生了并发（不是串行）


def test_batch_partial_failure_keeps_successful_cards(tmp_path) -> None:
    class _FlakyLLM(FakeLLMProvider):
        def __init__(self):
            super().__init__(response="")
            self.calls = 0
        async def complete(self, messages):
            self.calls += 1
            if self.calls == 2:
                raise ValueError("simulated card failure")
            return (
                "# 卡\n\n## 一句话解释\n\n概念。\n\n## 为什么重要\n\n重要。\n\n"
                "## 如何运作\n\n运作。\n\n## 关系\n\n[[本源与边界]]。" + "补充。" * 40
            )

    llm = _FlakyLLM()
    state = SectorBreakerState.initialize(project_id="proj-001", domain="情趣用品", user_goal="建库")
    ctx = KernelRuntimeContext(
        project=_project(), repository=None, state=state,
        search_provider=None, llm_provider=llm, emit_event=lambda e: asyncio.sleep(0),
    )
    tool_call = ToolCall(
        tool_name="write_explainer_cards_batch",
        args={"cards": [
            {"title": "A", "focus": "a", "card_kind": "concept"},
            {"title": "B", "focus": "b", "card_kind": "concept"},
            {"title": "C", "focus": "c", "card_kind": "concept"},
        ]},
        reason="批量补卡，其中一张会失败",
    )
    obs = asyncio.run(write_explainer_cards_batch(tool_call, ctx))

    # 部分失败不应让整个批量工具失败；成功的卡保留
    assert obs.success is True
    assert len(obs.artifact_ids) == 2
    assert len(ctx.artifacts) == 2
```

- [ ] **Step 5.2：跑测试确认失败**

Run: `python -m pytest tests/unit/test_explainer_cards_batch.py -v`
Expected: FAIL（`write_explainer_cards_batch` 不存在）

- [ ] **Step 5.3：实现 `write_explainer_cards_batch`**

打开 `backend/app/agent_kernel/tools/artifacts.py`，在文件顶部确认已 `import asyncio`（第 5 行已有）。在 `write_explainer_card` 函数之后新增批量工具（复用现有 `_write_card_document` / `_build_writer_context` / `_build_artifact` / `_card_kind` / `_card_artifact_type` / `_card_folder` / `_safe_filename` 等已有私有函数）：

```python
async def write_explainer_cards_batch(tool_call, context: KernelRuntimeContext) -> KernelObservation:
    """Generate multiple independent explainer cards concurrently.

    The main Agent decides which cards to add (order-independent), and this tool
    fans them out with asyncio.gather. Individual card failures are skipped, not fatal.
    """
    if context.llm_provider is None:
        return KernelObservation(
            tool_name="write_explainer_cards_batch",
            success=False,
            summary="批量解释卡写作失败：没有配置 LLM Provider。",
            error="llm provider not configured",
        )
    raw_cards = tool_call.args.get("cards") or []
    specs = []
    for item in raw_cards:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("focus") or "").strip()
        focus = str(item.get("focus") or title).strip()
        if not title:
            continue
        specs.append({
            "title": title,
            "focus": focus,
            "card_kind": _card_kind(item.get("card_kind")),
            "writing_goal": str(item.get("writing_goal") or "").strip(),
            "layer_id": item.get("layer_id"),
        })
    if not specs:
        return KernelObservation(
            tool_name="write_explainer_cards_batch",
            success=False,
            summary="批量解释卡写作跳过：没有有效的 cards 输入。",
            error="no valid card specs",
        )

    async def _one(spec: dict):
        context_text = _build_writer_context(
            context, layer_id=spec["layer_id"] or "dynamic_card", title=spec["title"],
        )
        cleaned, errors = await _write_card_document(
            context,
            title=spec["title"],
            focus=spec["focus"],
            card_kind=spec["card_kind"],
            writing_goal=spec["writing_goal"],
            context_text=context_text,
        )
        if not _usable_card_markdown(cleaned):
            return {"ok": False, "title": spec["title"], "errors": errors}
        artifact = _build_artifact(
            context,
            artifact_id=f"ART-KERNEL-CARD-{uuid4().hex[:8]}",
            artifact_type=_card_artifact_type(spec["card_kind"]),
            title=spec["title"],
            content_path=f"{_card_folder(spec['card_kind'])}/{_safe_filename(spec['title'])}.md",
            content=cleaned,
            source_evidence_ids=list(dict.fromkeys(context.state.evidence_refs)),
            schema_version="v2-agent-kernel-card",
        )
        return {"ok": True, "artifact": artifact}

    results = await asyncio.gather(*[_one(spec) for spec in specs], return_exceptions=True)

    written_ids: list[str] = []
    failed_titles: list[str] = []
    for spec, result in zip(specs, results):
        if isinstance(result, Exception) or not isinstance(result, dict) or not result.get("ok"):
            failed_titles.append(spec["title"])
            continue
        context.artifacts.append(result["artifact"])
        written_ids.append(result["artifact"].id)

    summary = f"并行补写解释卡完成：成功 {len(written_ids)} 张"
    if failed_titles:
        summary += f"，跳过 {len(failed_titles)} 张（{', '.join(failed_titles[:5])}）"
    return KernelObservation(
        tool_name="write_explainer_cards_batch",
        success=bool(written_ids),
        summary=summary,
        data={"written_ids": written_ids, "failed_titles": failed_titles},
        state_delta=KernelStateDelta(artifact_ids=written_ids, task_notes=[summary]),
        artifact_ids=written_ids,
    )
```

- [ ] **Step 5.4：确认复用的私有函数存在**

执行前先在 `artifacts.py` 里确认这些函数已存在：`_write_card_document`、`_build_writer_context`、`_build_artifact`、`_card_kind`、`_card_artifact_type`、`_card_folder`、`_safe_filename`、`_usable_card_markdown`。如果 `_card_folder` 不存在，用 `write_explainer_card` 里实际使用的 content_path 构造方式替换（读该函数确认，约 200 行处用的是 `f"{_card_folder(card_kind)}/{_safe_filename(title)}.md"`）。

- [ ] **Step 5.5：注册批量工具**

打开 `backend/app/agent_kernel/tools/__init__.py`（或 `artifacts.py` 的 `register_artifact_tools`），在 `write_explainer_card` 注册之后加入：

```python
    registry.register(
        ToolSpec(
            name="write_explainer_cards_batch",
            description=(
                "Generate MULTIPLE independent explainer cards in parallel. "
                "Use this when several concept/tool/player/risk cards are needed and they do not depend on each other. "
                "Args: cards = [{title, focus, card_kind, writing_goal?, layer_id?}, ...]."
            ),
            args_schema=schema({
                "cards": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "focus": {"type": "string"},
                            "card_kind": {"type": "string"},
                            "writing_goal": {"type": "string"},
                            "layer_id": {"type": "string"},
                        },
                    },
                },
            }, required=["cards"]),
        ),
        write_explainer_cards_batch,
    )
```

- [ ] **Step 5.6：更新 master_agent 提示词，告知批量补卡能力**

打开 `backend/app/agents/prompts/master_agent_system.md`，在 Task 3（V2 计划）加入的"辅助卡片"段落里补一句引导：

```markdown
### 批量并行补卡（write_explainer_cards_batch）
当你已经写完主文档、盘点出多张互不依赖的解释卡时，优先用 write_explainer_cards_batch 一次性提交所有卡片（cards 数组），它们会并行生成，比逐张 write_explainer_card 更快。逐张写只用于单张、需要精细控制的卡片。
```

- [ ] **Step 5.7：跑测试确认通过**

Run: `python -m pytest tests/unit/test_explainer_cards_batch.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5.8：跑 Agent Kernel 全量回归**

Run: `python -m pytest tests/unit/test_agent_kernel_tools.py tests/unit/test_agent_kernel_runtime.py tests/unit/test_kernel_partial_success.py -v`
Expected: 全部 PASS

- [ ] **Step 5.9：提交**

```bash
git add backend/app/agent_kernel/tools/artifacts.py backend/app/agent_kernel/tools/__init__.py backend/app/agents/prompts/master_agent_system.md tests/unit/test_explainer_cards_batch.py
git commit -m "feat: 辅助卡片批量并行生成，主循环仍串行把控全局"
```

---

## 收尾验证（全部 Task 完成后）

- [ ] **全量测试**

Run: `python -m pytest tests/unit/test_kernel_partial_success.py tests/unit/test_agent_kernel_models.py tests/unit/test_run_narrative.py tests/unit/test_explainer_cards_batch.py tests/api/test_run_trace_export.py tests/unit/test_agent_kernel_runtime.py tests/unit/test_agent_kernel_tools.py tests/api/test_app.py -q`
Expected: 全部 PASS

- [ ] **版本隔离扫描**

Run: `python tools/check_version_isolation.py`
Expected: PASS

- [ ] **前端构建 + 测试**

Run: `cd frontend && npm run build && npm test -- --run App.test.tsx`
Expected: 全部 PASS

- [ ] **真实端到端验收（关键）**

用 Mimo + Tavily 跑一个真实项目（可复用"情趣成人用品"这类证据多的领域）。验收清单：
- run 不再因单张卡片失败而整轮 failed
- 导出目录 `docs/` 下有主文档、`cards/` 下有解释卡、`docs/00-调研复盘.md` 有第一人称复盘
- 前端事件流是人话通知，看不到 `ready_to_write`/`layer_id` 等术语
- 能下载 `run-trace-*.json` 思考日志
- 配置面板选 Mimo 后有"当前生效模型：mimo-*"提示

---

## 自检清单

### Spec 覆盖检查

| 用户问题 | 对应 Task |
|---------|---------|
| 1. 配置切换无确认感、Key 不回填、滚动条丑 | Task 4 |
| 2. Agent 叙述充满术语、看不懂、分类过多 | Task 2 |
| 3. `artifact_writing_failed` 整轮失败 | Task 1（根因：卡片失败杀 run + 产物丢弃）|
| 4. 思考日志留存/导出/自述报告、证据利用率 | Task 3 |
| 5. 辅助卡片等无依赖工作并行化 | Task 5 |
| （用户诉求）状态保留 + 断点恢复不浪费资源 | Task 1（失败也存 checkpoint + 保留真产物）+ 复用 V2 已建的 `/continue` |

### 占位符扫描

无 TBD/TODO/"fill in details"。所有代码步骤含完整代码。

### 类型一致性检查

- `KernelRunResult.failed_writes` / `partial_success` 在 Task 1 定义，runtime `_result` 中填充，pipeline 中读取 —— 一致。
- `AgentDecision.user_notice` 字段在 Task 2 的 models.py 定义、tool_decision.md 提示词、runtime emit、前端读取处名称一致。叙述由 LLM 实时生成，全程无硬编码 `if tool_name == ...` 枚举。
- `generate_run_narrative` 工具名在 Task 3 的实现、注册中一致。
- `write_explainer_cards_batch` 工具名在 Task 5 的实现、注册、提示词中一致；其面向用户的通知同样由 LLM 的 `user_notice` 生成，无需在任何地方为它单独写话术。
- `getRunTrace` 客户端方法名在 Task 3 的 client.ts 定义与 App.tsx 调用一致。
- Task 5 的批量补卡工具无需在别处登记话术：它的用户通知同样来自 LLM 的 `user_notice`（Task 2 的机制天然覆盖所有工具，包括未来新增的）。

### 执行顺序建议

Task 1（P0 bug）必须最先做且单独验证——它解决 run 失败这个最痛的问题。Task 2/3/4/5 相互独立，可并行分发给子 Agent：
- Task 2（narration）、Task 3（日志/复盘）主要动 `agent_kernel` + 少量前端
- Task 4（配置面板）纯前端
- Task 5（并行补卡）纯 `agent_kernel/tools`

Task 3 与 Task 5 都改 `tools/__init__.py` 注册区，并行时需注意合并顺序（各加各的 `register` 调用，不冲突）。Task 2 只动 `models.py`/`tool_decision.md`/`runtime.py`/`App.tsx`，与 Task 5 无文件重叠。
