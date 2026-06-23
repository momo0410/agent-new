# Remediation Execution Flow

最后更新: 2026-04-21

## 接口
`POST /api/v1/execute-selected-remediations`

实现文件:
- `src-python/app/routers/api.py`

## 关键流程
1. 校验 `selected_findings` 与 `rollback_mode`。
2. 安全解析 SSH 上下文（无 `get_default_connection_id` 依赖）。
3. 按 `dry_run / rollback_mode / approval / budget` 进入对应分支。
4. 汇总 `results` 与 `overall_status`。

## SSH 兼容与降级策略（已实现）
- `ssh is None`: 受控返回，不抛 500。
- `is_connected` 不可用: 受控返回，不抛 500。
- 无活跃连接: 对真实执行返回结构化 `error`。
- `dry_run` 与 `rollback_mode=preview`: 不强依赖 SSH，可继续执行预算/审批/预览路径。

## 已修复回归点
历史问题:
- 直接调用不存在方法 `SSHManager.get_default_connection_id()` 导致 500。

当前行为:
- 已改为能力检测与连接状态检测，不再调用该方法。
- 已有回归测试覆盖“无该方法时不崩溃”。

## 状态语义
### finding 级
- `dry_run`
- `pending_approval`
- `blocked`
- `completed`
- `failed`
- `rollback_preview`
- `rollback_completed`

### overall 级
- `dry_run`
- `pending_approval`
- `blocked`
- `all_completed`
- `partially_completed`
- `failed`
- `rollback_preview`
- `rollback_completed`
- `rollback_partially_completed`
- `rollback_failed`

## 测试覆盖
- `src-python/tests/test_execute_selected_remediations_api.py`
  - dry-run 场景
  - rollback preview 场景
  - budget 阻断场景
  - 无默认 SSH 方法回归场景
