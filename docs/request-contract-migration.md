# Request Contract 迁移指南

## 概述

本文档说明 `allow_rule_fallback` 字段的移除和 `require_llm` 语义的统一。

**迁移日期**: 2026-04-21  
**影响范围**: 前后端 Agent API 契约  
**破坏性变更**: ✅ 是（移除了 `allow_rule_fallback` 字段）

---

## 变更原因

### 问题背景

在之前的实现中，存在两个控制 LLM 回退行为的字段：
- `require_llm`: 是否强制要求 LLM
- `allow_rule_fallback`: 是否允许回退到规则引擎

这导致了以下问题：
1. **语义冗余**: 两个字段的含义重叠，容易混淆
2. **状态不一致**: 前端、后端、运行时可能设置不同的值
3. **维护成本高**: 需要同时维护两个字段的逻辑

### 解决方案

**单一事实来源**: 只使用 `require_llm` 控制回退行为

| require_llm | 行为 |
|-------------|------|
| `true` | 强制使用 LLM，失败时报错，不回退 |
| `false` | 优先使用 LLM，失败时自动回退到规则引擎 |
| `undefined/null` | 使用后端默认配置 |

---

## 迁移步骤

### 1. 前端代码迁移

#### ❌ 旧代码（已废弃）

```typescript
const request: AgentRunRequest = {
  task: "检查系统安全",
  require_llm: this.strictMode,
  allow_rule_fallback: !this.strictMode, // ⚠️ 已移除
};
```

#### ✅ 新代码

```typescript
const request: AgentRunRequest = {
  task: "检查系统安全",
  require_llm: this.strictMode, // 单独控制即可
};
```

#### UI 层映射

```typescript
// aiCommandCenterRenderer.ts
class AICommandCenterRenderer {
  private strictMode: boolean = false;
  
  async runAgent(userInput: string) {
    const request: AgentRunRequest = {
      task: userInput,
      require_llm: this.strictMode, // 直接映射，无需 allow_rule_fallback
    };
    
    return agentService.runAgentTask(request);
  }
}
```

**strictMode 与 require_llm 的映射关系**:
- `strictMode = true` → `require_llm = true` (严格模式，LLM 失败报错)
- `strictMode = false` → `require_llm = false` (宽松模式，允许回退)

---

### 2. 后端代码迁移

#### AgentRequest Schema

**变更前**:
```python
class AgentRequest(BaseModel):
    require_llm: Optional[bool] = Field(default=None)
    allow_rule_fallback: Optional[bool] = Field(
        default=None,
        deprecated=True,
    )
```

**变更后**:
```python
class AgentRequest(BaseModel):
    """Agent 请求
    
    注意: require_llm 由前端传入以覆盖后端默认配置。
    回退行为由 require_llm 单独控制：require_llm=False 即允许回退到规则引擎。
    """
    require_llm: Optional[bool] = Field(
        default=None,
        description="前端传入的 LLM 强制要求。None 时使用后端默认配置；True/False 覆盖后端配置",
    )
    # allow_rule_fallback 已移除
```

#### Application Service

**变更前**:
```python
def build_planner_config(
    self,
    *,
    agent_config: AgentSettings,
    require_llm: Optional[bool],
    allow_rule_fallback: Optional[bool],  # ⚠️ 已移除
) -> PlannerConfig:
    if allow_rule_fallback is not None:
        logger.warning("allow_rule_fallback parameter is deprecated...")
    
    effective_allow_rule_fallback = False
    # ...
```

**变更后**:
```python
def build_planner_config(
    self,
    *,
    agent_config: AgentSettings,
    require_llm: Optional[bool],
) -> PlannerConfig:
    """构建 PlannerConfig
    
    注意:
    - require_llm: 前端传入时优先使用，否则使用后端默认配置
    - 回退行为由 require_llm 单独控制：require_llm=False 即允许回退到规则引擎
    """
    effective_require_llm = (
        agent_config.planner.require_llm
        if require_llm is None
        else require_llm
    )
    # allow_rule_fallback 固定为 False，回退行为由 require_llm 控制
    effective_allow_rule_fallback = False
    
    # ...
```

---

### 3. API 调用迁移

#### HTTP API

**变更前**:
```bash
POST /api/v1/agent/run
{
  "task": "检查 SSH 配置",
  "require_llm": false,
  "allow_rule_fallback": true  # ⚠️ 已移除
}
```

**变更后**:
```bash
POST /api/v1/agent/run
{
  "task": "检查 SSH 配置",
  "require_llm": false  # 单独控制即可
}
```

---

## 兼容性说明

### 向后兼容性

❌ **不兼容**: `allow_rule_fallback` 字段已从所有公开 API 中移除

如果旧代码仍在使用此字段：
- **前端 TypeScript**: 编译时会报错（类型定义已移除）
- **后端 Python**: Pydantic 验证会拒绝未知字段（除非配置 `extra='allow'`）

### 迁移窗口期

建议立即迁移，因为：
1. 字段已在所有核心代码路径中移除
2. 测试套件已更新，不再测试此字段
3. 文档已同步更新

---

## 常见场景示例

### 场景 1: 严格模式（生产环境推荐）

```typescript
// 前端
const request: AgentRunRequest = {
  task: "安全检查",
  require_llm: true,  // 必须使用 LLM
};

// 行为：
// - LLM 可用 → 使用 LLM 规划
// - LLM 不可用 → 直接报错，不回退
```

### 场景 2: 宽松模式（开发/测试环境）

```typescript
// 前端
const request: AgentRunRequest = {
  task: "日志分析",
  require_llm: false,  // 允许回退
};

// 行为：
// - LLM 可用 → 使用 LLM 规划
// - LLM 不可用 → 自动回退到规则引擎
```

### 场景 3: 使用后端默认配置

```typescript
// 前端
const request: AgentRunRequest = {
  task: "应急响应",
  // 不设置 require_llm
};

// 行为：使用后端 settings.json 中的 agent.planner.require_llm 配置
```

---

## 测试验证

### 运行测试套件

```bash
cd src-python
pytest tests/test_agent_request_contract.py -v
pytest tests/test_agent_application_service.py -v
pytest tests/test_agent_api_contract.py -v
```

### 关键测试用例

1. **test_require_llm_optional**: 验证 `require_llm` 为可选字段
2. **test_no_allow_rule_fallback_field**: 验证 `allow_rule_fallback` 已移除
3. **test_require_llm_from_frontend_overrides_backend**: 验证前端覆盖后端配置
4. **test_allow_rule_fallback_always_false**: 验证内部固定为 False

---

## 故障排查

### 问题 1: 前端编译错误

**错误信息**:
```
Property 'allow_rule_fallback' does not exist on type 'AgentRunRequest'.
```

**解决方案**:
移除所有 `allow_rule_fallback` 赋值，只保留 `require_llm`。

### 问题 2: 后端验证错误

**错误信息**:
```
pydantic.ValidationError: 1 validation error for AgentRequest
allow_rule_fallback
  Extra inputs are not permitted
```

**解决方案**:
从请求体中移除 `allow_rule_fallback` 字段。

### 问题 3: 回退行为不符合预期

**症状**: 设置了 `require_llm=false` 但仍然报错

**检查清单**:
1. 确认 `require_llm` 正确传递到后端
2. 检查后端日志，确认 `planner_config.allow_rule_fallback` 为 `False`
3. 验证 LLM adapter 是否正确创建

---

## 相关文档

- [Agent Request Contract 规范](./agent-request-contract.md)
- [Agent 架构设计](../src-python/app/services/agent/README.md)
- [Planner 配置说明](../src-python/app/services/agent/planner.py)

---

## 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-04-21 | 1.0 | 初始版本，移除 `allow_rule_fallback` 字段 |

---

## 联系与支持

如有问题，请联系：
- GitHub Issues: https://github.com/momo0410/new-lovely/issues
- 文档维护者: Agent 团队
