# Agent Contract Gap Report (Final)

最后更新: 2026-04-21

## 结论
当前前后端契约已达到收尾可交付状态。

## 已对齐字段与接口
### 1) /agent/run 请求契约
| 项 | 状态 | 说明 |
|---|---|---|
| `task/skills/context/max_steps` | 已对齐 | 前后端一致 |
| `require_llm` | 已对齐 | strictMode 统一映射 |
| `llm_config` | 已对齐 | 前端透传，后端可消费 |
| `allow_rule_fallback` | 已移除 | 不再出现在公开请求体 |

### 2) Agent 状态机
| 项 | 状态 | 说明 |
|---|---|---|
| 类型定义 `AgentRunStatus` | 已对齐 | 包含 `waiting_approval` |
| `/agent/run` `waiting_approval` 返回 | 已接入 | 后端最终状态可返回该值 |
| 前端状态接线 | 已接入 | Renderer 根据 `result.status` 映射 UI 状态 |

### 3) ExecuteSelectedRemediations
| 项 | 状态 | 说明 |
|---|---|---|
| `dry_run/approval/budget/rollback` 字段 | 已对齐 | 请求/响应已包含 |
| SSH 缺省连接保护 | 已修复 | 不再因 `get_default_connection_id` 缺失 500 |
| 受控降级 | 已实现 | 无 SSH 时返回结构化结果/错误 |

### 4) Generated Skills
| 项 | 状态 | 说明 |
|---|---|---|
| list/approve/reject/delete/cleanup | 已闭环 | API 与 store 行为一致 |
| 状态与过期逻辑 | 已实现 | `draft/approved/rejected/disabled` + cleanup |

## 尚未完全对齐或兼容处理
| 项 | 当前处理 | 风险级别 |
|---|---|---|
| `/agent/run` 审批交互回传 | 仅接线 `waiting_approval` 展示态，未内置审批动作流 | 中 |
| 审批票据持久化 | 以内存/进程态为主，不是跨重启强一致 | 中 |

## 假接通或待补调用
- 无“假成功”路径。
- 已确认 `execute-selected-remediations` 在无默认 SSH 连接时为受控返回，不再抛裸 500。

## 测试验证
### 后端（本轮）
- 命令:
  - `python -m pytest src-python/tests/agent/unit/test_generated_skill_store.py src-python/tests/test_generated_skills_api.py src-python/tests/test_execute_selected_remediations_api.py src-python/tests/test_agent_api_contract.py src-python/tests/test_final_status_resolver.py -q`
- 结果: `58 passed`

### 前端（本轮）
- 命令:
  - `npx vitest run src/modules/ai/__tests__/agentTaskFactory.test.ts src/modules/ai/__tests__/agentClient.test.ts src/modules/ai/__tests__/agentService.test.ts`
- 结果: `58 passed`
