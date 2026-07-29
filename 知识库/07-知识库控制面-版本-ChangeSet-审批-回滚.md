# 知识库控制面：版本、ChangeSet、审批与回滚

## 为什么不能让 Agent 直接改 Markdown

知识库是长期资产，直接覆盖会带来：

- 用户在 Agent 运行期间已经修改文件，Agent 覆盖新内容；
- 无法知道改了什么、为什么改；
- 事实性修改没有证据；
- 失败时无法恢复；
- Specialist 或 LLM 越权执行删除、移动。

SectorBreaker 把知识写入拆成“提案”和“应用”两个阶段。

## Artifact Revision

每个 Artifact 包含：

- ID、Project ID、Type、Title、Content Path；
- Content 和 Source Evidence IDs；
- Schema Version；
- Revision；
- SHA-256 Content Hash；
- Active；
- Supersedes / Superseded By；
- Run ID 和 ChangeSet ID；
- Created At。

Revision 是不可变的。更新不会修改旧 Row，而是：

1. 新建 Artifact；
2. Revision = Predecessor Revision + 1；
3. 旧 Artifact Active = False；
4. 旧 Artifact.superseded_by 指向新 ID；
5. 新 Artifact.supersedes 指向旧 ID。

普通检索和导出只读取 Active Revision。

## ChangeSet 数据结构

ChangeSet 保存：

- Project、Origin Run、Maintenance Task；
- Status；
- Summary 和 Evidence IDs；
- 一个或多个 Operation；
- Created By Agent；
- Approve/Apply/Rollback 时间；
- Applied/Rollback Artifact IDs；
- Error。

Operation 保存：

- `create` 或 `update`；
- Safe Relative Markdown Path；
- Base Hash；
- Before Content；
- After Content；
- Unified Diff；
- 是否 Factual Change。

## Propose

`ChangeSetService.propose()`：

1. 根据 Path 查 Active Artifact；
2. 有 Active Artifact -> Update，否则 Create；
3. Before 和 After 完全相同则拒绝；
4. 计算 Unified Diff；
5. 保存 Proposed ChangeSet。

Agent 的 `revise_layer_document` 工具只生成完整 After Content 和 ChangeSet，不会激活新 Revision。

## Approve

只有 `proposed` 状态可以批准。批准记录 `approved_at`，但此时知识仍未改变。

## Apply 的完整门禁

### 状态门

必须已 Approved。

### 文件和字节预算

Operation 数不能超过 `max_files_per_run`，After Content 总字节不能超过 `max_changed_bytes`。

### Evidence 门

ChangeSet 中每个 Evidence ID 都必须属于当前 Project。只要包含未知 ID，整个 ChangeSet Denied。

Factual Change 在 Policy 要求证据时，Evidence IDs 不能为空。

### 路径和操作门

- 只支持安全相对 Markdown 路径；
- 拒绝 `..`、隐藏路径和非 `.md`；
- 第一版只允许 Create/Update，不允许 Move/Delete；
- Create 需要 Policy.allow_create；
- Existing Update 必须有 Active Artifact。

### Optimistic Concurrency

Update 的 Current Content Hash 必须等于 Proposal 时的 Base Hash。不一致说明用户或其他 Run 已经修改该笔记，ChangeSet 进入 `conflicted`，不会覆盖。

### Whole-journal Prevalidation

多 Operation ChangeSet 在写任何 Revision 前先验证全部 Operation。后一个 Operation 冲突时，前一个也不会被部分应用。

## Apply 后发生什么

- 每个 Operation 生成新 Artifact Revision；
- 新 Revision 继承 ChangeSet Evidence 和 Origin Run；
- ChangeSet -> Applied；
- Maintenance Task -> Done；
- Waiting Run 可以在人工批准后恢复，并把新 Revision 识别为本轮产物。

## Rollback

只有 Applied ChangeSet 可以回滚。

### 回滚 Update

确认当前 Active Revision 仍然是当时 Apply 产生的 Artifact，然后创建一个新的 Rollback Revision，内容逐字恢复 Before Content。

### 回滚 Create

将新建 Artifact 标记 Inactive。

Rollback 本身也写入历史，不会删除审计链。

## 为什么回滚不是简单把旧 Row Active=True

对 Update 创建新的 Rollback Revision，可以保持时间线单向、记录“谁在什么时候执行了回滚”，同时避免修改历史 Revision 的语义。对于新建文件，撤销其 Active 状态更符合“该路径在变更前不存在”。

## Vault Import

导入流程：

- 解析绝对 Root；
- 只扫描 Markdown；
- 忽略 `.git`、`.obsidian`、`.sectorbreaker`、`.trash`、Node Modules 等；
- 拒绝逃逸 Root 的 Symlink/Path；
- 校验 UTF-8；
- 限制 Max Files 和 Total Bytes；
- 保留 Relative Path；
- 对 Path、Size、Content Hash 计算 Snapshot Hash；
- 相同 Snapshot 直接复用；
- 变化笔记创建新 Artifact Revision。

源 Vault 不被修改。

## Deterministic Audit

不用 LLM 的检查：

- Broken Wikilink；
- Orphan Note；
- Duplicate Title；
- Missing Front Matter；
- Missing Evidence Metadata；
- TODO/FIXME/待补证/待验证。

Finding ID 和 Maintenance Task Fingerprint 使用稳定 Hash，相同 Snapshot 重复审计不会重复创建 Open Task。

## Export

Exporter 只输出 Active Revision，并清理上次 Manifest 中已不再 Active 的受管文件，避免 Superseded 文件残留。

输出包括：

```text
README.md / SectorBreaker Home.md
docs/
cards/
followups/
sources/evidence-ledger.md
.obsidian/
.sectorbreaker/
  project.json
  agent_state.json
  evidence_ledger.json
  artifact_manifest.json
  health_snapshot.json
  maintenance_backlog.json
  change_sets.json
  open_questions.json
  trace_summary.json
manifest.json
```

## 面试回答：怎么避免 Agent 覆盖用户新改的内容

> 修改已有知识时，我们采用 Optimistic Concurrency。Agent 提案会记录 Active Revision 的 SHA-256 Base Hash、Before/After Content 和 Unified Diff。Apply 前重新读取当前 Active Hash，只要不一致就标记 Conflict，整组 ChangeSet 不写任何 Revision。这样用户在审核期间的手动修改不会被静默覆盖。
