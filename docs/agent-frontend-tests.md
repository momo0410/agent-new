# Agent Frontend Tests

最后更新: 2026-04-21

## 覆盖模块
- `src/modules/ai/__tests__/agentTaskFactory.test.ts`
- `src/modules/ai/__tests__/agentClient.test.ts`
- `src/modules/ai/__tests__/agentService.test.ts`

## 本轮执行结果
执行命令:

```bash
npx vitest run src/modules/ai/__tests__/agentTaskFactory.test.ts src/modules/ai/__tests__/agentClient.test.ts src/modules/ai/__tests__/agentService.test.ts
```

结果:
- Test Files: `3 passed`
- Tests: `58 passed`

## 本轮修复点
1. `agentClient.invoke`：无参数调用不再额外传 `undefined`，与测试预期一致。
2. `agentService.test`：修复 `vi.mock` hoist 顺序问题（改用 `vi.hoisted`）。
3. `aiCommandCenterRendererV2`：接入 `/agent/run` 的 `waiting_approval` 状态映射与展示文案。
4. `AgentRunResult.status`：扩充到后端真实可能返回值，消除类型收窄差异。

## 仍可补充
- 目前未覆盖 `aiCommandCenterRendererV2` 的 UI 级状态渲染快照测试。
- 建议后续补 1 组状态映射单测（`waiting_approval/completed/failed`）。
