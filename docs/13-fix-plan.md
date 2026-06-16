# MVP 修复计划

> 目标：消除所有 P0 阻塞点，补全 P1 功能缺失，使 MVP 完全对齐设计稿

## 阶段 A：workflow 暂停/恢复架构（P0 核心）

### A1. 重写 workflow 执行引擎
- 把 `run_research_workflow` 从一次性 `ainvoke` 改为分段执行
- 每个 gate 函数独立调用，gate 之间插入暂停点
- 用 `asyncio.Event` 实现暂停/恢复
- workflow 状态持久化到 SQLite（当前 run 表已有 current_gate 字段）

### A2. 实现暂停机制
- 每个 gate 完成后，检查该 gate 是否需要人工审阅（`humanReview` 标志）
- 需要审阅时：发 `waiting_for_human` 事件，设置 run status=WAITING_FOR_human，暂停
- 不需要审阅时：自动继续下一个 gate

### A3. 实现 `/resume` 端点
- 接收 run_id + 用户输入（guidance/evidence）
- 存储 user_inputs
- 恢复 workflow 执行（从 current_gate 的下一个 gate 开始）

### A4. 实现一键执行模式
- 前端提供"跳过审阅，一键执行"选项
- 后端接受 `auto_run=true` 参数，跳过所有暂停点

## 阶段 B：前端状态机重构

### B1. 重写 phase 状态机
- 新增 `waiting` phase（或复用 `reviewing`）
- 监听 SSE `waiting_for_human` 事件 → 切到 reviewing
- 监听 SSE `gate_complete` 事件 → 更新 GraphFlow 进度

### B2. 重写 ReviewView 触发逻辑
- 每收到 `gate_complete` + `waiting_for_human` 事件 → 显示 ReviewView
- ReviewView 显示当前 gate 的产物和事件
- 用户确认 → 调 `/resume` API → 切回 researching

### B3. 重写 onContinue/onSkip
- onContinue：提交 guidance/evidence → 调 resume → 切回 researching
- onSkip：直接调 resume（无用户输入）→ 切回 researching

### B4. 错误状态处理
- SSE 断开时显示错误状态（不是 toast）
- workflow 失败时前端显示失败页面
- isLoading 超时兜底（30 秒）

## 阶段 C：补全设计稿第二步（反向拆解）

### C1. 新增产物类型
- COMPETITOR_ANALYSIS（竞品数据库）
- REVENUE_STRUCTURE（收入结构）
- CONVERSION_PATH（转化路径）
- TRUST_ASSETS（信任资产）

### C2. 扩展 knowledge_map_gate 或新增 gate
- 将竞品分析、收入结构、转化路径、信任资产作为独立产物
- 每个产物有专门的 LLM prompt
- prompt 包含设计稿要求的所有字段

## 阶段 D：补全设计稿第三步（内容生态）

### D1. 新增产物类型
- CONTENT_ACCOUNTS（内容账号数据库）
- CONTENT_TOPICS（高频选题）
- CONTENT_CLASSIFICATION（内容分类）

### D2. 实现内容生态分析
- LLM prompt 要求按平台整理账号
- 分析高频选题
- 6 种内容分类（含案例型和专家IP型）

## 阶段 E：补全其他缺失

### E1. 交易单位独立产物
- 使用已定义的 `TRANSACTION_UNITS` 类型
- 从 PLAYER_MAP 中拆分出来

### E2. 行业地图增强
- 三级节点
- 新手学习顺序
- 知识卡片模板

### E3. 数据口径调查
- scope_gate 增加数据口径分析

## 阶段 F：自检与验证

### F1. 后端测试
- 所有现有测试通过
- 新增暂停/恢复测试
- 新增 user_inputs 注入测试

### F2. 前端测试
- 所有现有测试通过
- 新增逐 gate 审阅流程测试

### F3. 对账复查
- 重新运行审计，确认所有 P0/P1 问题已解决
- 确认设计稿 5 步方法论的覆盖度 > 80%

## 执行顺序
A1 → A2 → A3 → A4 → B1 → B2 → B3 → B4 → C1 → C2 → D1 → D2 → E1 → E2 → E3 → F1 → F2 → F3
