# Agent UI State Model

最后更新: 2026-04-21

## 前端状态定义
`idle | preparing | running | waiting_approval | completed | failed`

定义位置:
- `src/modules/ai/agentTypes.ts`

## 当前接线结果
- `idle/preparing/running/completed/failed`: 已接线
- `waiting_approval`: 已接线（/agent/run 返回该状态时前端进入等待态）

实现位置:
- `src/modules/ai/aiCommandCenterRendererV2.ts`

## 状态映射（/agent/run）
- `status=waiting_approval` -> UI `waiting_approval`
- `status in {completed, partially_completed, preview}` -> UI `completed`
- 其他失败态 -> UI `failed`

## 交互说明
- `waiting_approval` 目前为“可见等待态”，用于提示需要审批。
- 当前 UI 未内置 `/agent/run` 审批回传动作（仅状态展示与阻塞输入）。

## 与执行态兼容
- `isRunning` 由 `isActive(state)` 派生。
- `preparing/running/waiting_approval` 均视为活跃态。
