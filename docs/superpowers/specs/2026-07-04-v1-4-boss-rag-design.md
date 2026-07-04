# V1.4 Boss 信源与项目 RAG 设计

## 背景

V1.3 已经实现 `talent_demand` 企业版人才需求情报模式，但真实招聘信源仍主要依赖用户上传 JD、外部 AI 报告和通用搜索补充。用户明确要求：企业版不能只是换输出形式，必须接入更贴近招聘场景的真实信源；同时希望引入 RAG，使项目更符合企业落地叙事，并支持基于已生成知识库继续追问。

## 产品边界

V1.4 是增量增强，不重写个人版主链路：

- 个人版 `domain_knowledge` 继续专注陌生领域建库，不默认出现 Boss 直聘采集。
- 企业版 `talent_demand` 新增 Boss 职位信源入口，用真实职位样本补充人才需求分析。
- Boss 采集不是“后台偷偷爬全站”，而是用户主动在企业版输入关键词、城市、数量，系统按本地工具能力采集少量样本。
- 当 Boss 工具未安装、未登录或采集失败时，系统必须明确提示并降级到上传 JD / 外部报告 / 搜索补充，不能伪造来源。
- 项目 RAG 先做本地项目级检索增强问答，不引入向量数据库；后续可在同一接口下升级 embeddings。

## Boss 信源方案

优先适配 `boss-agent-cli`，原因：

- GitHub Topic 页面显示该项目新、star 高，且定位是 Agent / CLI / MCP 可集成工具。
- 它提供 JSON 输出形态，比旧 Scrapy / Selenium 脚本更适合接入 provider 边界。
- 它支持只读搜索和详情获取，适合我们“少量样本、企业版主动触发”的需求。

实现上新增 `JobSourceProvider`，避免把 Boss 直聘逻辑写死进人才 pipeline：

- `BossAgentCliProvider`：调用本地 `boss` 或配置的命令，解析 JSON 职位输出。
- `BossDisabledProvider`：当命令不可用时返回明确不可用诊断。
- `JobPostingSource`：统一职位样本结构，包括标题、公司、地点、薪资、经验、描述、技能、URL、来源 provider、原始 payload。
- `Talent Source Scout` 在企业版运行时先读取上传材料，再按项目配置调用 Boss provider，最后才用通用搜索补薄。

为了稳健，V1.4 不做账号绕过、不做代理池、不做批量无限采集、不提交任何 cookies 或 secrets。

## RAG 方案

当前 `/api/projects/{project_id}/chat` 只使用 SQLite FTS 搜 evidence，并返回固定模板。V1.4 改为真实项目 RAG：

- 检索范围包括 Evidence Ledger、上传文档 segments、生成 artifacts。
- 新增轻量 `ProjectRetriever`，仍基于 SQLite FTS / LIKE fallback，不引入新服务。
- `chat` endpoint 构建引用上下文，若 LLM 已配置，则调用 LLM 生成答案；若未配置，返回检索摘要式答案并明确说明未调用 LLM。
- 每条引用包含 `source_id`、`source_type`、`title`、`snippet`，前端可以显示引用来源。
- RAG 不改变写作主流程，只增强结果页二次提问。

## 数据流

企业版运行：

1. 用户选择 `talent_demand`。
2. 用户可上传 JD / 外部报告，也可配置 Boss 采集关键词、城市、数量。
3. 后端创建项目后保存 Boss 采集设置。
4. `talent_source_intake` 读取上传材料。
5. `boss_job_intake` 通过 `JobSourceProvider` 采集职位样本，并写入 `EvidenceItem`。
6. 通用搜索作为补充信源，只在材料仍偏薄时触发。
7. 后续 JD 抽取、技能归一化、Source Coverage、LLM 分析、Obsidian 导出复用 V1.3 流程。

项目问答：

1. 用户在结果页输入问题。
2. 后端检索 evidence / documents / artifacts。
3. 后端构建带 citation id 的上下文。
4. LLM 基于引用回答；无 LLM 时返回可读的检索摘要。
5. 前端显示答案和引用。

## 稳定性要求

- `domain_knowledge` 默认流程不能新增 Boss 依赖。
- Boss provider 失败不能导致整条企业版 pipeline 失败，除非用户显式要求仅 Boss 且没有其他材料。
- 运行事件必须显示 Boss 采集状态：开始、不可用、采集数量、失败原因、降级。
- 所有新增外部能力必须走 provider/interface，不允许在 API handler 或 graph node 中直接散落命令调用。
- 新增公共 schema、API、导出字段时同步 docs 和测试。

## 验收标准

- 企业版可配置 Boss 采集参数，并在运行日志看到 Boss 采集节点。
- 本地未安装 `boss-agent-cli` 时，UI 显示未配置/不可用，不影响上传 JD 旧流程。
- 若 provider 返回职位 JSON，系统能把职位转为 evidence，并在 Source Coverage 中单独统计 Boss 来源。
- 结果页项目问答使用项目资料回答，并返回引用，不再是固定模板。
- 个人版领域建库仍能启动并导出，不出现 Boss 采集必需项。

