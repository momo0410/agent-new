# Evidence Model

## 目标

当前 Agent 报告链路升级为 evidence-grounded 模式后，所有可报告结论都需要满足两件事：

1. 能回到具体 `step` 和 `tool output`
2. 能区分“真实安全发现”和“仅表示证据采集失败/不足的执行性问题”

本设计保持现有 `structured_output` 兼容，不删除已有字段，只新增可渐进式接入的 grounding 字段。

## 核心对象

### `EvidenceRecord`

统一证据对象，负责把一条证据绑定到执行层。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `evidence_id` | `str` | 证据稳定 ID，供 finding 通过 `evidence_ref` 引用 |
| `kind` | `str` | 证据类型，当前包括 `tool_output` / `step_error` / `step_metadata` |
| `source_type` | `str` | 来源类型，当前固定为 `step_output` |
| `source_mode` | `str` | 来源执行模式，典型值：`host_runtime` / `remote_target` / `remote_target_via_ssh` |
| `step_id` | `str` | 证据所属 step ID |
| `step_number` | `int` | 证据所属 step 序号 |
| `tool_name` | `str` | 产出证据的工具名 |
| `transport_kind` | `str` | 传输类型，典型值：`local` / `ssh` / `http` |
| `output_path` | `str?` | 证据在 tool output 中的定位路径，例如 `config_issues[0]` |
| `summary` | `str` | 证据摘要，适合前端列表展示 |
| `content` | `Any` | 证据原始内容 |
| `content_preview` | `str` | 截断后的可读预览 |
| `metadata` | `dict` | 附加上下文，例如错误标记 |

### `NormalizedSecurityFinding`

原有 finding 结构保留，新增 grounding 字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `evidence_ref` | `list[str]` | 证据引用 ID 列表，指向 `evidence_catalog` |
| `confidence` | `float` | 提取置信度，范围 `[0, 1]` |
| `extraction_reason` | `str` | 说明该 finding 是如何从证据中抽取出来的 |

保留不变的字段：

- `check_id`
- `module`
- `title`
- `severity`
- `category`
- `evidence`
- `impact`
- `reason`
- `recommended_actions`
- `fix_commands`
- `verify_commands`
- `rollback_commands`
- `notes`

兼容策略：

- `evidence` 继续保留，避免前端历史逻辑失效
- 新前端优先使用 `evidence_ref -> evidence_catalog`
- 老前端仍可继续读 `evidence`

### `NormalizedFindingsBundle`

为了避免 normalizer、report builder、remediation report 重复丢字段，统一使用：

- `findings`
- `evidence_catalog`

report builder 和 remediation report 都应从同一个 bundle 读取数据，而不是各自重新拼接 finding。

## 证据生成规则

### 主机模式

`host_runtime` 下的证据通常来自：

- 本机命令输出
- 主机探测工具输出
- 本机配置/日志检测结果
- step 执行失败时的错误对象

此时：

- `source_mode = host_runtime`
- `transport_kind` 多为 `local`，也可能是 `ssh`

### 远程目标模式

`remote_target` / `remote_target_via_ssh` 下的证据通常来自：

- HTTP 探测结果
- 目标站点/接口响应摘要
- 通过 SSH 代理执行的远程命令输出

此时：

- `source_mode` 明确标记远程模式
- `transport_kind` 用来区分 `http` 和 `ssh`
- 前端可以据此选择不同的跳转/展示方式

## 报告输出位置

### `final`

新增：

- `findings`
- `evidence_catalog`
- `risk_findings`
- `grounding_validation`

兼容保留：

- `evidence` 继续存在，语义上作为 `findings` 的兼容别名使用

### `structured_output`

新增：

- `findings`
- `evidence_catalog`
- `grounding_validation`
- `grounded_evidence_count`

`structured_output.steps[*]` 新增：

- `evidence_refs`
- `finding_refs`

这样前端可直接从 step 卡片反查到 finding 和 evidence。

### `remediation_report`

新增：

- `evidence_catalog`
- `grounding_validation`

`detailed_items[*]` 新增：

- `evidence_ref`
- `confidence`
- `extraction_reason`
- `related_steps`

## 前端接入建议

### 渐进式方式

第一阶段：

- 继续使用 `final.evidence`
- 逐步展示 `finding.evidence_ref`

第二阶段：

- 接入 `final.evidence_catalog`
- 支持 `finding -> evidence -> step -> traces` 跳转

第三阶段：

- 在 step 侧直接展示 `evidence_refs` / `finding_refs`
- 使用 `grounding_validation` 做显式告警

### 推荐关联路径

1. `final.findings[*].evidence_ref`
2. `final.evidence_catalog[*].evidence_id`
3. `final.evidence_catalog[*].step_id`
4. `traces[*].step_id` 或 `structured_output.steps[*].step_id`

## 非目标

本次设计不做以下事情：

- 不删除旧字段
- 不强制前端一次性切换到新 schema
- 不尝试对所有自然语言总结做语义级事实校验
