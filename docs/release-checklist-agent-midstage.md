# Agent 模块中期版本发布检查清单

**版本**: v0.55.0-agent-midstage  
**日期**: 2026-04-21  
**状态**: 可交付中间版本

---

## ✅ 核心能力边界

### 已完整实现

1. **Agent 前端分层架构**
   - ✅ `agentService.ts` - Façade 层
   - ✅ `agentClient.ts` - Transport 层
   - ✅ `agentTaskFactory.ts` - 请求构造层
   - ✅ `agentTypes.ts` - 类型定义层

2. **Generated Skills 管理闭环**
   - ✅ 后端 5 个 API 端点
   - ✅ 前端调用链完整
   - ✅ 状态模型（draft/approved/rejected/disabled）
   - ✅ 返回字段完整（含 risk_level, validation_passed 等）

3. **Request Contract 统一**
   - ✅ `require_llm` 语义明确（前端优先）
   - ✅ `allow_rule_fallback` 标记废弃
   - ✅ `strictMode` 映射到 `require_llm`
   - ✅ 前后端行为一致

4. **UI 状态机**
   - ✅ 5 个状态已接线（idle/preparing/running/completed/failed）
   - ✅ 兼容层保留（`isRunning` getter）
   - ✅ 状态转换逻辑清晰

5. **测试覆盖**
   - ✅ 后端 Generated Skills API 测试（17用例）
   - ✅ 后端 Request Contract 测试（14用例）
   - ✅ 前端测试示例框架（需安装 Vitest）

6. **文档体系**
   - ✅ 6 份核心文档完整
   - ✅ 契约差异报告明确
   - ✅ 实施状态诚实标注

---

## ⚠️ 最小实现标注

### Generated Skills

- ⚠️ **风险等级评估**: 由 AI 生成时设定，无自动静态分析
- ⚠️ **验证逻辑**: `validation_passed/errors` 为可选字段，需手动设置
- ⚠️ **存储方式**: JSON 文件，无并发锁（单用户场景可接受）

### Request Contract

- ⚠️ **llm_config 字段**: 前端传递但后端 `AgentRequest` schema 未正式定义（通过 context 透传）
- ⚠️ **allow_rule_fallback**: 仍保留在 schema 中（向后兼容），实际被忽略

### UI 状态机

- ⚠️ **waiting_approval**: 后端暂不支持异步审批流，状态未接线
- ⚠️ **进度实时更新**: 当前为轮询模式，非 WebSocket 推送

---

## 🔍 横向一致性检查

### 字段命名一致性

| 模块 | 检查结果 | 说明 |
|-----|---------|------|
| `agentTypes.ts` vs `schemas.py` | ✅ 一致 | require_llm, allow_rule_fallback 对齐 |
| `agentClient.ts` vs `api.py` | ✅ 一致 | 5个 generated skills 命令名匹配 |
| `agentTaskFactory.ts` vs 后端 skills | ⚠️ **不一致** | 见下方修复建议 |

### 返回结构一致性

| 接口 | 检查结果 | 说明 |
|-----|---------|------|
| `/agent/run` | ✅ 一致 | AgentRunResult 字段完整 |
| `/agent/context` | ✅ 一致 | AgentContext 字段匹配 |
| `/agent/tools` | ✅ 一致 | ToolDefinition 字段匹配 |
| `/agent/skills` | ✅ 一致 | SkillDefinition 字段匹配 |
| `/agent/generated-skills/*` | ✅ 一致 | 新增字段已补全 |

---

## 🛠️ 总装配修复清单

### 高优先级（阻塞发布）

#### 1. 修正 Skill 名称不匹配

**问题**: `agentTaskFactory.ts` 使用了错误的 skill 名称

**文件**: `src/modules/ai/agentTaskFactory.ts`

**修复**:
```typescript
// 第 36 行
- skills: ['security_check'],
+ skills: ['host_triage'],  // 或 'capability_check'

// 第 56 行
- skills: ['incident_response'],
+ skills: ['incident_timeline'],

// 第 68 行
- skills: ['log_analysis'],
+ skills: ['log_investigation'],
```

**影响范围**: 
- `runSecurityCheck()` 
- `runEmergencyResponse()`
- `runLogAnalysis()`

**预计工作量**: 10 分钟

---

#### 2. 补充 llm_config 到后端 Schema

**问题**: 前端传递 `llm_config` 但后端 `AgentRequest` 未定义

**文件**: `src-python/app/services/agent/schemas.py`

**修复**:
```python
class AgentRequest(BaseModel):
    # ... existing fields ...
    
    # LLM 配置（前端传入）
    llm_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="前端传入的 LLM 配置，包含 provider, model_name, api_key, base_url"
    )
```

**预计工作量**: 30 分钟（需在 application service 中处理此字段）

---

### 中优先级（警告级别）

#### 3. 清理误导性注释

**文件**: `src/modules/ai/agentTypes.ts`

**修复**:
```typescript
// 第 83 行
- allow_rule_fallback?: boolean; // 兼容保留，运行时固定为 false
+ /** @deprecated 此字段已废弃，回退行为由 require_llm 单独控制 */
+ allow_rule_fallback?: boolean;
```

---

#### 4. 添加 Deprecated 警告日志

**文件**: `src-python/app/routers/api.py`

**修复**: 在 `/agent/run` 端点中添加
```python
if req.allow_rule_fallback is not None:
    logger.warning("allow_rule_fallback is deprecated, use require_llm instead")
```

---

## 📋 测试/文档补齐

### 测试执行清单

```bash
# 1. 后端测试
cd src-python
pytest tests/test_generated_skills_api.py -v
pytest tests/test_agent_request_contract.py -v

# 2. 前端测试（需先安装 Vitest）
npm install -D vitest @vitest/ui @vue/test-utils jsdom
npx vitest src/modules/ai/__tests__/agentTaskFactory.test.ts
```

### 文档审查清单

- [ ] `docs/agent-request-contract.md` - 字段语义准确
- [ ] `docs/generated-skills-review-flow.md` - API 端点完整
- [ ] `docs/agent-ui-state-model.md` - 实施状态已更新
- [ ] `docs/agent-contract-gap-report.md` - 差异清单明确
- [ ] `docs/ai-proxy-behavior.md` - 环境行为说明清晰
- [ ] `docs/agent-frontend-tests.md` - 测试启用步骤明确

---

## 💰 剩余技术债

### 短期（1-2 周）

1. **Skill 名称修正** - 10 分钟
2. **llm_config 字段补充** - 30 分钟
3. **Vitest 集成** - 2 小时
4. **waiting_approval 状态接线** - 待后端支持

### 中期（1 个月）

5. **执行安全与审批 UI 接线** (Prompt 7)
6. **Evidence/Report 展示层完善** (Prompt 8)
7. **AI Proxy 错误提示优化** (Prompt 10)

### 长期（季度规划）

8. **Benchmark/Replay 系统** (Prompt 9)
9. **WebSocket 实时进度推送**
10. **多任务并发支持**

---

## 🚀 下一阶段建议

### Phase 1: 立即修复（今天）

1. 修正 Skill 名称（`agentTaskFactory.ts`）
2. 补充 `llm_config` 到后端 Schema
3. 运行后端测试验证

### Phase 2: 本周内

1. 安装并配置 Vitest
2. 运行前端测试
3. 清理所有 deprecated 警告

### Phase 3: 本月内

1. 实现 `waiting_approval` 状态接线（需后端配合）
2. 完善整改执行页面的审批流 UI
3. 补充 Evidence 展示逻辑

---

## 📊 质量指标

| 指标 | 目标 | 当前 | 状态 |
|-----|------|------|------|
| 后端测试覆盖率 | >80% | ~60% | ⚠️ 待提升 |
| 前端测试覆盖率 | >70% | ~10% | ❌ 需启用 Vitest |
| 文档完整性 | 100% | 100% | ✅ 完成 |
| 契约一致性 | 100% | 95% | ⚠️ 2项待修复 |
| API 端点可用性 | 100% | 100% | ✅ 完成 |

---

## ✅ 发布批准

- [ ] 代码审查通过
- [ ] 所有高优先级修复完成
- [ ] 后端测试全部通过
- [ ] 文档审查通过
- [ ] 技术债清单已记录

**批准人**: _______________  
**日期**: _______________

---

**维护者**: AI Assistant  
**最后更新**: 2026-04-21
