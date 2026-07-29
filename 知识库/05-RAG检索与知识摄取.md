# RAG 检索与知识摄取

## 检索对象

ProjectRetriever 统一检索四类信息：

- Web/Manual/User Material 形成的 Evidence；
- 上传报告和导入资料的 Document；
- Document Segment；
- Active Artifact 和 Vault Note。

Chat、Follow-up 和 Agent Tool 共用同一个 Retriever，避免用户问答和 Agent 研究使用两套不同索引。

## Lexical Retrieval

Lexical 候选来自：

- SQLite FTS5 Evidence Index；
- Evidence、Document、Segment、Artifact 的轻量词项匹配；
- 中文连续文本切成双字词项，英文提取字母数字 Token；
- Snippet 尽量截取在命中词附近。

优点是速度快、可解释、专有名词精确。缺点是同义词和无关键词重合的语义问题可能召回不到。

## Local Vector Retrieval

### Embedding Provider

当前适配器：FastEmbed。

默认模型：

```text
BAAI/bge-small-zh-v1.5
```

模型在本地缓存，Document 使用 `passage_embed()`，Query 使用 `query_embed()`，符合非对称检索模型的编码契约。向量在写入前进行 L2 Normalize，查询时通过点积得到 Cosine Similarity。

真实模型维度为 512。代码没有硬编码 512，而是从 Provider 返回向量推断并校验 Dimension。

相关配置：

```text
SECTORBREAKER_EMBEDDING_PROVIDER=auto|fastembed|disabled
SECTORBREAKER_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
SECTORBREAKER_EMBEDDING_CACHE_DIR=<local path>
SECTORBREAKER_EMBEDDING_THREADS=<positive integer>
```

未显式指定缓存目录时，模型保存在用户目录的 `.cache/sectorbreaker/fastembed`，不会写进 Git 仓库。

### Chunk 策略

- Evidence 将标题、摘要、Snippet 和 Raw Excerpt 合并为一个 Chunk；
- 有 Segment 的 Document 按 Segment 索引；
- 无 Segment 的 Document 整体索引；
- Artifact 按 Markdown Heading 切分；
- 默认单 Chunk 约 1400 字符，Overlap 约 180 字符。

Vector Search 对同一个 Parent Document 只保留最优 Segment，防止一个长文档占满候选列表。

## Content-hash 增量索引

每个 Chunk 记录：

- Project ID；
- Chunk ID、Source ID、Parent ID；
- Source Type、Title、Path、URL；
- Content Hash；
- Embedding Provider、Model、Dimension；
- Float32 Vector Bytes；
- Verification Status 和 Indexed Time。

同步规则：

- Chunk 不存在：生成 Embedding；
- Content Hash 变化：重新 Embedding；
- 只改 Metadata：复用旧 Vector，仅更新 Citation Metadata；
- Source 被删除或 Artifact 被 Supersede：删除 Stale Chunk；
- Force Rebuild：在一个 SQLite Transaction 中发布新 Snapshot。

如果 Force Rebuild 的模型加载或 Embedding 失败，事务回滚，旧索引仍然可用。

## 为什么不用 pgvector

SectorBreaker 当前是 Local-first、单用户/私有化知识工作台，SQLite 能同时保存控制面数据、FTS 和派生向量索引，部署成本低、备份简单、可离线运行。

选择 SQLite 不是因为不懂 pgvector，而是当前产品边界不需要引入独立 PostgreSQL 服务。若未来演进为多用户和高并发，再迁移到 PostgreSQL/pgvector 或专用 Vector Store 更合理。

## RRF 融合

Lexical Score 和 Vector Similarity 量纲不同，不能简单相加。系统使用 Reciprocal Rank Fusion：

```text
fused_score = 1 / (k + lexical_rank)
            + 1 / (k + vector_rank)
```

当前 `k=60`。RRF 只依赖名次，既保留精确关键词召回，也利用语义召回。

Citation 返回：

- Retrieval Mode：lexical/vector/hybrid；
- Lexical Rank/Score；
- Vector Rank/Score；
- Fused Score；
- Embedding Model；
- Source/Parent ID；
- Relative Path、URL、Content Hash；
- Verification Status；
- 命中局部 Snippet。

## Honest Degradation

状态区分：

- `hybrid`：向量检索成功参与；
- `hybrid_pending`：配置了模型但还未完成首次加载/索引；
- `lexical`：用户主动禁用 Embedding；
- `lexical_degraded`：本来希望使用 Embedding，但运行时或模型不可用。

这是一个重要产品原则：不能把关键词检索包装成“语义 RAG”。

## 用户资料摄取

上传的 PDF/TXT/Markdown 会转成 Project Document，并切为 Segment，提取 Citation。Agent 启动时先通过 Report Internalizer 把资料中的 Claim、Entity 和 Open Question 写入 State。

外部 AI 报告的信任策略：

- 默认是 Low/Partial Trust；
- 可以用于 Context 和 Search Lead；
- 不直接作为 Verified Fact；
- 后续由 Web Search 或 Verifier 补充证据；
- 在 Trace 和 Writer Context 中保留其存在。

## Follow-up Growth

用户追问时：

1. ProjectRetriever 先查已有知识；
2. LLM 使用 Citation 回答，LLM 不可用时可走确定性 Citation Fallback；
3. Follow-up 保存成 `followups/*.md` Active Artifact；
4. 重复的规范化问题复用已有 Artifact；
5. 只把当前 Project 中真实存在的 Evidence ID 写入 Artifact。

## RAG 评估怎么讲

当前自动化覆盖：

- 无共享关键词的语义 Query 能召回目标 Chunk；
- Lexical-only 和 Vector-only 候选都能进入 RRF；
- 不变内容不会重复 Embedding；
- 改变内容会重新索引；
- Superseded Revision 不会召回；
- 失败 Rebuild 保留旧 Snapshot；
- Dimension Mismatch 明确降级；
- Agent Retrieval Tool 和 Chat 共用同一 Retriever。

项目还有真实 FastEmbed Smoke Test，验证非关键词语义召回，而不是只用 Fake Embedding 证明流程能跑。
