# Agent Kernel Design Philosophy

## Why This Document Exists

SectorBreaker 的 V2 重构不能再继续把“智能体”实现成固定 workflow。此前多轮迭代已经证明：即使代码里出现了 Master Agent、ReAct、State、L1-L5、覆盖判断等名词，如果生产路径仍然是“按固定节点遍历、每层搜一两次、最后调用写作器”，最终呈现出来的仍然只是一个调用过 LLM 的程序，而不是 Agent。

本文件记录新的最高架构原则：SectorBreaker 的核心必须是 `LLM + State + Tools + ReAct Loop`。LangGraph 可以继续使用，但它不是大脑。LangGraph 只负责状态承载、循环路由、中断恢复、checkpoint 和事件流。真正的判断必须交给 LLM。

## Non-Negotiable Principle

SectorBreaker must be an Agent Kernel, not a fixed research workflow.

The core loop is:

```text
build_context_pack(state)
  -> llm_decide(context, available_tools)
  -> execute_tool(action)
  -> observe_result
  -> apply_state_delta
  -> llm_decide(updated_state, available_tools)
```

如果实现退化成下面这种结构，就是错误方向：

```text
L1 search once
  -> L2 search once
  -> L3 search once
  -> L4 search once
  -> L5 search once
  -> write fixed documents
```

L1-L5 是认知地图和 coverage rubric，不是死流程。它们应该存在于 State 中，用来帮助 LLM 判断“当前知识库哪里缺、下一步该做什么”，而不是由代码强制遍历。

## Product Identity

SectorBreaker 不是搜索产品，也不是自动报告生成器。它是一个领域研究 Agent，目标是帮助用户进入陌生领域，形成可持续填充、可验证、可导入 Obsidian 的知识系统。

它与通用 Agent 的差异不在于“也能搜索”，而在于：

- 它有面向领域破壁的认知框架；
- 它把上传报告、搜索结果、证据、主张、实体、关系和问题内化到结构化 State；
- 它把调研过程转化为 Obsidian 知识库，而不是一次性回答；
- 它能在用户反馈后继续补库、扩展层级、创建子卡片或重新验证。

## The Brain

LLM 是大脑。它必须负责关键判断：

- 用户到底想了解什么；
- 当前 State 中有哪些材料；
- 上传的外部 AI 报告覆盖了什么；
- 还缺什么信息；
- 应该调用哪个工具；
- 搜索应该用什么 query；
- 搜索结果是否有价值；
- 哪些内容应该进入长期 State；
- 哪些是噪音或失败尝试；
- 哪些主张需要验证；
- 什么时候可以写某个知识库文档；
- 什么时候需要继续搜索；
- 什么时候需要问用户；
- 什么时候应该阻断或降级。

代码可以提供边界、工具、预算、schema 和安全规则，但不能用固定 if-else 替代这些判断。

## The State

State 是智能体的运行记忆和世界模型。它不是 prompt 的临时拼接，也不是搜索结果列表。

State 至少包含：

- `meta_context`: project id, domain, user goal, market scope, source policy, product mode, constraints, safety policies;
- `knowledge_schema`: L1-L5 或动态扩展后的认知层级，每层有 goal, guiding questions, coverage status, missing dimensions;
- `shared_knowledge`: entities, claims, relationships, source memories, open questions, layer outputs;
- `evidence_store_refs`: uploaded documents, document segments, citations, search evidence, extracted pages, rejected source diagnostics;
- `working_memory`: active task, attempted tool calls, observations, failed queries, reflections, local stop reason;
- `decision_log`: thought summaries, actions, observations, state deltas, coverage judgments, route decisions;
- `artifact_memory`: generated files, review results, known gaps, revision tasks;
- `human_feedback`: user questions, clarifications, requested expansions, rejected assumptions.

State 更新必须经过结构化 reducer 或明确 tool。不能让 raw web dump、失败尝试、重复片段和无关噪音污染 shared knowledge。

## The Tools

Tools 是 Agent 的行动能力。工具必须真实工作，不得只是壳子。

V2 Agent Kernel 的最小工具集：

- `search_web`: 通过 `SearchProvider` 搜索网络，返回 raw result count、accepted evidence ids、rejected diagnostics 和 source summaries;
- `read_uploaded_report`: 读取用户上传的外部 AI 调研报告、JD、笔记或资料片段;
- `retrieve_project_memory`: 从项目 evidence、documents、segments、artifacts 中检索相关上下文;
- `inspect_evidence`: 查看某条 evidence 的标题、摘要、来源、质量、claims、verification status;
- `internalize_observation`: 把 observation 转成 entities、claims、relationships、open questions、source memories;
- `update_task_state`: 更新当前任务进度、缺口、下一步候选动作;
- `write_layer_document`: 基于当前 State 和目标层写 Obsidian Markdown;
- `review_artifact`: 检查文档是否详实、证据是否足、是否需要扩写或补搜;
- `ask_user`: 在信息不足、边界不清或安全风险高时进入 human-in-the-loop;
- `finish_run`: 当 Agent 认为知识库足够可用时结束并导出。

工具调用必须经过 provider/repository/service 边界。Graph nodes 和 API handlers 不直接调用外部服务。

## External AI Reports

外部 AI DeepSearch 报告是一等输入，不是旁路附件。

它们进入 Agent Kernel 的方式：

1. Store raw document.
2. Segment document.
3. Extract citations, URLs, claims, entities, open questions.
4. Create low/partial-trust source memories and evidence refs.
5. Put report summary and citation map into State.
6. Let Master Agent decide which claims can be used, which require verification, which become search leads.
7. Use search as supplement and verification, not as blind restart.

最终写作必须能引用这些材料。上传报告如果没有进入 State 和 writer context，就视为失败。

## L1-L5 As Cognitive Guide

L1-L5 是人的智慧提供的认知地图：

- L1 What & Why: 是什么，为什么存在，解决什么需求；
- L2 Who: 谁在用，谁提供，玩家、资源、社区、机构；
- L3 How: 原理、工具、框架、流程、前置概念、隐藏术语；
- L4 Money / Incentives: 价值流、成本、盈利方式、上下游、外包环节；
- L5 Risks / Boundaries: 政策、平台、技术、伦理、安全、骗局、稳定性边界。

Agent 可以选择先做 L1，也可以因为上传报告已经覆盖 L2 而跳过重复搜索；可以在 L3 发现“号池”后创建新的下钻任务；可以在用户反馈“不懂股票是什么”时新建 L0 前置扫盲层。

L1-L5 只规定“什么是好知识库”，不规定“每一步必须怎么走”。

## Prompt System

V2 不能使用简单 prompt。Prompt 是 Agent 的认知宪法，必须与 State schema 和 Tool schema 配套。

需要的 prompt 文件：

- `master_agent_system.md`: 身份、目标、状态阅读方式、工具使用规则、停止条件、安全边界；
- `state_reader.md`: 如何区分已知事实、低可信材料、待验证问题、噪音和工作记忆；
- `tool_decision.md`: 每轮如何输出结构化 action，不输出自由散文；
- `search_strategy.md`: 如何根据当前缺口规划 query，避免机械分词；
- `state_internalizer.md`: 如何把 observation 转成 structured state delta；
- `coverage_judge.md`: 如何判断某层是否足够，不使用固定证据条数替代判断；
- `artifact_writer.md`: 如何写详实的 Obsidian Markdown；
- `artifact_reviewer.md`: 如何检查输出是否过薄、口水、缺证据、缺链接或需要补搜；
- `human_feedback_router.md`: 如何把用户反馈转成补库、修订、搜索、问答或新层级。

对用户展示的是 `thought_summary`，不是隐藏链式思考。事件流要展示：Agent 理解了什么、为什么调用工具、观察到了什么、State 更新了什么、下一步为什么这么走。

## LangGraph Role

LangGraph 可以使用，但图必须围绕 Agent loop，而不是固定业务流水线。

推荐图形：

```text
initialize_state
  -> ingest_uploaded_materials
  -> agent_decide
  -> execute_tool
  -> apply_state_delta
  -> route
       -> agent_decide
       -> human_in_loop
       -> export
       -> blocked
```

LangGraph 的职责：

- checkpoint state;
- route action;
- support human-in-the-loop;
- resume after feedback;
- emit run events;
- enforce max iterations and tool budget;
- persist artifacts and state snapshots.

LangGraph 不负责把研究拆成固定 L1-L5 流水线。

## Acceptance Definition

一个版本只有满足以下条件，才配叫 V2 Agent Kernel：

- 运行事件流能看到 `Thought Summary -> Action -> Observation -> State Update -> Decision`;
- 搜索 query 由 LLM 根据 State 和缺口生成，不是固定字符串拼接；
- 上传外部报告会影响搜索规划、State 和最终写作；
- Agent 可以在信息不足时继续搜索、换 query、读材料、检索项目记忆或问用户；
- 信息充分性由 LLM coverage judgment 给出结构化理由，固定条数只能作为 guardrail；
- 写作按 L1-L5 或动态 schema 输出，不能复用 V1 固定模板；
- LLM 写作失败不能伪装成功，必须 visible degrade 或重试；
- 生成内容必须详实、证据关联、Obsidian 友好；
- 用户反馈可以重新进入 Agent loop，触发补库或新建卡片；
- 旧的固定 `v2_pipeline.py` 不能继续作为生产主路径。
