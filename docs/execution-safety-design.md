# Execution Safety Design

## Goal

在不改变现有主流程入口的前提下，把当前 Agent 执行层升级为一套可预演、可审批、可回滚、可限制预算的执行系统。

当前保留的主入口：

- `/api/v1/agent/run`
- `/api/v1/execute-selected-remediations`

本次改造不新增新的主执行入口，只为现有入口补充可选安全控制字段和更完整的结构化返回。

## Core Changes

### 1. PlanStep 强化

`PlanStep` / `AgentPlanStep` 现在包含以下执行安全字段：

- `risk_level`
- `is_mutation`
- `supports_dry_run`
- `requires_approval`
- `rollback_supported`
- `expected_side_effects`

同时新增了前端消费字段：

- `step_fingerprint`
- `approval_ticket`
- `rollback_preview`

这些字段会被：

- `PlanBuilder`
- execution mode strategy
- `PolicyGuard`
- `Executor`
- report/structured output serializer

统一透传。

### 2. 统一安全层

新增：

- `app/services/agent/execution_safety.py`
- `app/services/agent/approval_store.py`

职责拆分如下：

- `ExecutionSafetyConfig`: 从请求上下文解析 dry-run、approval、budget。
- `ExecutionBudgetGuard`: 统一处理最大步数、最大 mutation、最大 SSH 命令、最大 HTTP 请求数。
- `RollbackPreview`: 统一生成回滚预览载荷。
- `ApprovalStore`: 生成和跟踪审批票据。

### 3. Policy Guard 升级

`PolicyGuard.evaluate_plan(plan, context=...)` 现在会：

- 结合上下文回填 `risk_level / is_mutation / rollback_supported / expected_side_effects`
- 为 mutation step 生成 `preview` 或 `pending_approval`
- 为高风险 step 自动生成 `pending_approval`
- 为需要审批的 step 生成 `approval_ticket`
- 为可回滚 step 生成 `rollback_preview`

强约束规则：

- 无 dry-run 支持的 mutation 不允许自动执行
- 高风险 step 默认不自动执行
- mutation step 默认先 `preview`，审批后才能真正执行

### 4. Executor 升级

`Executor.execute_plan()` 现在支持：

- budget preflight
- preview / pending_approval / blocked / execute 的统一状态流转
- 每步预算快照
- 审批票据回写
- 回滚预览回写

`ExecutionResult` / `StepExecution` 会输出：

- `approval_tickets`
- `budget_snapshot`
- `rollback_preview`
- `transport_kind`
- `expected_side_effects`

## Request Contract

### `/api/v1/agent/run`

不改入口，安全参数通过 `context.execution_safety` 传入：

```json
{
  "task": "修复 SSH 配置",
  "skills": ["safe_config_patch"],
  "context": {
    "execution_mode": "host_runtime",
    "execution_safety": {
      "dry_run": true,
      "auto_approve": false,
      "approved_step_ids": [],
      "approval_ids": [],
      "budget": {
        "max_steps": 10,
        "max_mutation_steps": 2,
        "max_ssh_commands": 6,
        "max_http_requests": 0
      }
    }
  }
}
```

### `/api/v1/execute-selected-remediations`

不改入口，直接扩展请求体：

```json
{
  "task": "安全修复",
  "dry_run": true,
  "auto_approve": false,
  "approval_ids": [],
  "approved_finding_ids": [],
  "rollback_mode": "none",
  "budget": {
    "max_steps": 5,
    "max_mutation_steps": 2,
    "max_ssh_commands": 4,
    "max_http_requests": 0
  },
  "selected_findings": []
}
```

`rollback_mode` 取值：

- `none`
- `preview`
- `execute`

## Response Contract

前端现在可以直接消费以下字段。

### Plan / Step

`report.plan.steps[*]` 包含：

- `execution_mode`
- `risk_level`
- `is_mutation`
- `supports_dry_run`
- `requires_approval`
- `rollback_supported`
- `expected_side_effects`
- `step_fingerprint`
- `approval_ticket`
- `rollback_preview`
- `blocked_reason`

### Final / Structured Output

`report.final` 和 `structured_output` 中新增：

- `budget`
- `approval_tickets`

每个 step 还会包含：

- `approval_status`
- `approval_ticket`
- `rollback_preview`
- `budget_snapshot`
- `transport_kind`

### execute-selected-remediations

每个结果项新增：

- `approval_required`
- `approval_ticket`
- `expected_side_effects`
- `rollback_preview`
- `rollback_results`
- `budget_snapshot`

顶层新增：

- `approval_tickets`
- `budget`

## Status Model

统一使用以下状态：

- `pending`
- `preview`
- `pending_approval`
- `blocked`
- `completed`
- `failed`
- `partially_completed`

remediation 入口还补充：

- `dry_run`
- `rollback_preview`
- `rollback_completed`

## Frontend Flow

推荐交互流程：

1. 前端先发起普通执行或 `dry_run=true`。
2. 如果返回 `preview` 或 `pending_approval`，展示：
   - risk level
   - expected side effects
   - rollback preview
   - approval ticket
   - budget snapshot
3. 用户确认后，前端携带：
   - `/agent/run`: `context.execution_safety.approval_ids`
   - `/execute-selected-remediations`: `approval_ids` 或 `approved_finding_ids`
4. 系统在相同步骤指纹下放行执行。
5. 如需撤销，前端使用同一 remediation 入口提交：
   - `rollback_mode=preview`
   - 或 `rollback_mode=execute`

## Budget Guard

当前支持四类预算：

- `max_steps`
- `max_mutation_steps`
- `max_ssh_commands`
- `max_http_requests`

执行器与 remediation 入口共享相同语义：

- preview / pending_approval 只消耗 step budget
- 真正执行 mutation 时消耗 mutation budget
- SSH 命令执行消耗 ssh budget
- HTTP 请求执行消耗 http budget

预算超限时不会继续执行，而是将步骤置为 `blocked`，并回写：

- `blocked_reason`
- `budget_snapshot`

## Approval Gate

审批票据是前端继续提交执行的桥梁。

票据包含：

- `id`
- `step_id`
- `step_fingerprint`
- `title`
- `risk_level`
- `reason`
- `expected_side_effects`
- `rollback_supported`
- `rollback_preview`

审批通过的两种方式：

- 传 `approval_ids`
- 传稳定的 step/finding id 到 `approved_step_ids` / `approved_finding_ids`

## Rollback

### Rollback Preview

用于展示：

- 是否支持回滚
- 回滚命令列表
- 回滚时可能产生的副作用
- 摘要说明

### Rollback Execute

当前已在 remediation 入口落地：

- `rollback_mode=execute`

对于通用 Agent step，当前已完成：

- 回滚能力建模
- 回滚预览输出

后续如某类 tool 具备真实回滚执行器，只需在 step metadata 中补充回滚执行信息即可接入。

## Host Mode vs Remote Target Mode

### Host Mode

适用：

- SSH 主机巡检
- 配置修复
- 服务启停

特点：

- mutation 主要体现在 SSH 命令或主机配置修改
- 预算重点关注：
  - `max_mutation_steps`
  - `max_ssh_commands`
- 副作用提示面向主机本身
- rollback 通常表现为配置恢复、服务回退

### remote_target

适用：

- 远程 HTTP 目标探测
- API / Web 目标验证

特点：

- 预算重点关注：
  - `max_http_requests`
  - `max_mutation_steps`
- 对 `POST/PUT/PATCH/DELETE` 一类请求视为 mutation
- 高风险远程写操作默认不自动执行
- 副作用提示强调“不要影响扫描主机，只影响目标服务状态”

### remote_target_via_ssh

这是混合模式：

- 通过 SSH 跳板发起动作
- 真正目标是远程 target

预算上需要同时考虑：

- `max_ssh_commands`
- `max_http_requests`
- `max_mutation_steps`

副作用提示会同时说明：

- 动作从 SSH jump host 发起
- 目标应当是 remote target，而不是 jump host 自身

## Compatibility Notes

- 不改原有 API path
- 旧请求仍可继续工作
- 新字段都是增量增强
- 原有 `PolicyGuard` 风格保留：仍以 `preview / pending_approval / blocked / sequential` 为主轴

## Tests Added

本次补充了以下测试方向：

- `PolicyGuard` 回写新字段、生成审批票据、生成回滚预览
- `PlanBuilder` 透传 `rollback_supported / expected_side_effects`
- `Executor` 对 preview 和 budget guard 的执行行为
- `execute-selected-remediations` 的：
  - dry-run
  - approval gate
  - budget guard
  - rollback preview
