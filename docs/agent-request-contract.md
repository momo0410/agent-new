# Agent Request Contract

最后更新: 2026-04-21

## 目标
统一前后端 `/api/v1/agent/run` 请求契约，避免字段语义分叉。

## 请求字段（当前生效）
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `task` | `string` | 是 | 用户任务描述 |
| `skills` | `string[]` | 否 | 指定技能列表 |
| `context` | `Record<string, any>` | 否 | 任务上下文 |
| `max_steps` | `number` | 否 | 最大执行步数 |
| `require_llm` | `boolean` | 否 | 是否强制要求 LLM |
| `llm_config` | `LLMConfig` | 否 | 前端透传 LLM 配置 |

## 已移除字段
- `allow_rule_fallback` 已从公开请求契约移除。
- 回退行为统一由 `require_llm` 控制。

## 语义约定
- `require_llm=true`: LLM 不可用时报错。
- `require_llm=false`: 允许规则回退。
- `require_llm` 未传: 使用后端默认配置。

## strictMode 映射
- 前端 `strictMode=true` -> `require_llm=true`
- 前端 `strictMode=false` -> `require_llm=false`

## llm_config 处理
- 前端传 `llm_config` 时优先使用（用于补齐 `api_key` 等）。
- 未传时使用后端 settings 中的模型配置。

## 代码锚点
- 前端类型: `src/modules/ai/agentTypes.ts`
- 前端调用: `src/modules/ai/aiCommandCenterRendererV2.ts`, `src/modules/ai/agentClient.ts`
- 后端入口: `src-python/app/routers/api.py`
- 后端服务层: `src-python/app/services/agent/application/agent_application_service.py`
