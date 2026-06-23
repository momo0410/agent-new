# Report Grounding Rules

## 目标

报告系统只允许输出“能被证据支持的结论”。模型可以解释证据，但不能绕过证据自行制造新的风险结论。

## 基本规则

### 1. 高优先级 finding 必须绑定证据

适用范围：

- `severity in {high, critical}`

要求：

- `evidence_ref` 不能为空
- `evidence_ref` 中的每个 ID 都必须在 `evidence_catalog` 中存在

### 2. 证据必须能回到 step 和 tool output

每个 `EvidenceRecord` 至少应包含：

- `step_id`
- `step_number`
- `tool_name`
- `output_path`

没有 step trace 的 evidence 视为无效证据。

### 3. `extraction_reason` 只能描述“如何从证据抽取”

允许：

- “Extracted from detect_ssh_audit output at config_issues[0]”
- “Aggregated from detect_port_scan output at open_ports[*]”

不允许：

- 没有证据却直接给出漏洞断言
- 将猜测写成 extraction reason

### 4. step 执行失败不等于确认漏洞

如果某个 step 失败：

- 可以生成 `execution_failure` 类 finding
- 该 finding 表示“证据采集失败/执行受阻”
- 不应把它当成已确认安全漏洞

## LLM 解释规则

### 1. 模型只能解释输入里已有的 finding

LLM 输出中的：

- `priority_risks[*].finding_id`
- `repair_candidates[*].finding_id`

必须命中现有 normalized findings。

### 2. 模型输出必须显式带 `evidence_ref`

对于：

- `priority_risks[*]`
- `repair_candidates[*]`

都必须输出 `evidence_ref`，且这些引用必须属于对应 finding。

### 3. 模型不能新增未提供的风险

如果 LLM 返回：

- 未知的 `finding_id`
- 未知的 `evidence_ref`
- 未与 finding 绑定的跨 finding 证据

则视为 grounding 失败。

### 4. grounding 失败时回退

当 LLM 解释未通过 grounding 校验时：

- 不直接透传不可信解释
- 回退到 rule-based grounded interpretation

## 校验器规则

校验器输出 `grounding_validation`，包含：

- `passed`
- `status`
- `issues`
- `stats`

### 错误级问题

典型错误：

- `missing_high_priority_evidence`
- `unknown_evidence_ref`
- `broken_step_trace`
- `evidence_missing_step_trace`
- `llm_missing_finding_ref`
- `llm_unknown_finding_ref`
- `llm_missing_evidence_ref`
- `llm_unknown_evidence_ref`

### 警告级问题

典型警告：

- `missing_extraction_reason`
- `llm_cross_bound_evidence_ref`

## 输出约束

### `final`

应至少包含：

- `findings`
- `evidence_catalog`
- `grounding_validation`

兼容字段：

- `final.evidence` 继续保留

### `structured_output`

应至少包含：

- `findings`
- `evidence_catalog`
- `grounding_validation`
- `steps[*].evidence_refs`
- `steps[*].finding_refs`

### `remediation_report`

必须使用规范化 findings，不允许重新从自由文本推导新的结论。

## 前后端协作约定

前端如果要显示“该结论来自哪里”，推荐链路：

1. 读 `finding.evidence_ref`
2. 定位 `evidence_catalog`
3. 根据 `evidence.step_id` 回到 `structured_output.steps` 或 `traces`
4. 用 `output_path` 和 `content_preview` 做精确展示

## 兼容策略

为了不让现有消费方一次性失效：

- 旧字段保留
- 新字段只增不删
- `final.evidence` 仍然可用
- 新前端逐步迁移到 `findings + evidence_catalog + grounding_validation`
