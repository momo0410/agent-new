# Agent Runtime 设计说明

> **文档用途**: 梳理当前 Agent 主链路架构，供后续开发者快速理解核心流程与扩展点。
> **最后更新**: 2026-04-20
> **约束**: 本文档基于现有代码静态分析生成，不涉及任何重构建议。
> **重构状态**: 已完成四步架构重构，详见 README.md "Agent 架构（四步重构后）" 章节

---

## 一、调用链路总览

### 1.1 完整执行流程

```
HTTP POST /api/v1/agent/run
    ↓
[Router] api.py: agent_run()
    ├─ 读取 AgentSettings (enabled, planner, mcp)
    ├─ 构建 PlannerConfig
    ├─ 加载 ToolRegistry (internal + MCP tools)
    ├─ 创建 AgentOrchestrator(planner_config, tool_registry)
    └─ 调用 orchestrator.run(agent_request)
         ↓
[Orchestrator] orchestrator.py: run(request)
    │
    ├─ 阶段1: _resolve_skills(request)
    │   ├─ 用户显式指定 skills → 直接获取
    │   ├─ 注册表模糊匹配 → match_skills(task)
    │   ├─ 规则规划器关键词匹配 → RuleBasedPlanner._match_skill_by_keywords()
    │   └─ 兜底: 取第一个 skill
    │
    ├─ 阶段2: _build_context(request)
    │   └─ 注入 ssh_manager (如未提供)
    │
    ├─ 阶段3: _obtain_plan(request, skills, context)
    │   ├─ 路径1: planner.plan_calls() → PlannerOutput(calls=[SkillCall])
    │   │          └─ _calls_to_plan() → skill.build_steps(args, ctx) → Plan
    │   ├─ 路径2: planner.plan() → Plan (旧版兼容)
    │   └─ 路径3: _fallback_plan_from_skills() → skill.build_steps({}, ctx) → Plan
    │
    ├─ 阶段4: executor.execute_plan(plan, request, context, max_replan_attempts)
    │   ├─ 遍历 plan.steps
    │   ├─ 对每个 step: execute_step(step, context)
    │   │   └─ tool_registry.execute_tool(step.tool_name, params, context)
    │   │       ├─ 优先走 _executors (MCP tools)
    │   │       └─ 再走 _tools (内置 BaseTool)
    │   ├─ 失败重规划逻辑 (仅 auto_remediation skill)
    │   │   ├─ _should_replan_step() 判断是否可重规划
    │   │   └─ _replan_steps() 生成新步骤列表
    │   └─ 返回 ExecutionResult
    │
    └─ 阶段5: _assemble_report(request, execution_result, report, skills, ...)
        ├─ _group_steps_by_skill() 按 skill_id 分组步骤
        ├─ 为每个 skill 生成 StructuredResult
        ├─ _normalize_findings_from_steps() 提取标准化安全问题
        ├─ _build_security_remediation_report() 构建整改报告
        ├─ _build_traces() 构建执行追踪记录
        ├─ _handle_remediation_classification() 自动修复分类 (fixed/unfixed/blocked)
        ├─ _build_structured_output() 构建详细结构化输出
        └─ _determine_final_status() 判定最终状态
            ↓
返回 FinalReport (序列化为 JSON)
```

### 1.2 关键文件职责

| 文件 | 职责 |
|------|------|
| `src-python/app/routers/api.py` | HTTP 入口，参数校验，配置读取，响应序列化 |
| `src-python/app/services/agent/orchestrator.py` | 编排全流程：解析→规划→执行→报告组装 |
| `src-python/app/services/agent/planner.py` | 规划器：RuleBasedPlanner (关键词匹配) / LLMPlanner (LLM 推理) |
| `src-python/app/services/agent/executor.py` | 执行器：逐步执行 Plan，记录 StepExecution，支持失败重规划 |
| `src-python/app/services/agent/tool_registry.py` | 工具注册表：管理内置 tools + MCP tools，统一执行接口 |
| `src-python/app/services/agent/skills/registry.py` | Skill 注册表：管理所有 Skill 实例，提供查询/匹配接口 |
| `src-python/app/services/agent/schemas.py` | 共享数据模型定义 (AgentRequest, Plan, SkillCall 等) |

---

## 二、关键数据结构

### 2.1 请求层

#### `AgentRunRequest` (Pydantic Model - API 入口)
```python
class AgentRunRequest(BaseModel):
    task: str                          # 用户任务描述 (自然语言)
    skills: List[str]                  # 显式指定的 skill 名称列表 (可选)
    context: Dict[str, Any]            # 额外上下文 (通常包含 ssh_manager)
    max_steps: int = 10                # 最大执行步数
```

**来源**: `src-python/app/routers/api.py:272-278`

**转换**: 在 `agent_run()` 中转换为 `AgentRequest` 并注入 `ssh_manager`。

---

#### `AgentRequest` (内部请求对象)
```python
class AgentRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task: str
    skills: List[str] = []
    context: Dict[str, Any] = {}
    max_steps: int = 10
```

**来源**: `src-python/app/services/agent/schemas.py`

**用途**: 贯穿 orchestrator/planner/executor 的核心请求对象。

---

### 2.2 规划层

#### `Plan` (执行计划)
```python
class Plan(BaseModel):
    id: str
    request_id: str
    steps: List[PlanStep]              # 有序步骤列表
    status: PlanStatus = "planned"     # planned / executing / completed / failed
```

**来源**: `src-python/app/services/agent/schemas.py`

**生成路径**:
- `planner.plan_calls()` → `_calls_to_plan()` → `skill.build_steps()` → `Plan`
- `planner.plan()` → 直接返回 `Plan` (旧版)
- `_fallback_plan_from_skills()` → `skill.build_steps({}, ctx)` → `Plan`

---

#### `PlanStep` (计划中的单个步骤)
```python
class PlanStep(BaseModel):
    id: str
    step_number: int                   # 步骤序号 (从 1 开始)
    description: str                   # 人类可读描述
    skill_id: Optional[str]            # 所属 Skill 名称 (用于结果归组)
    tool_name: str                     # 要调用的工具名
    parameters: Dict[str, Any]         # 传给工具的参数
    status: str = "pending"            # pending / running / completed / failed / skipped
```

**来源**: `src-python/app/services/agent/schemas.py`

**关键点**: `skill_id` 字段是 Orchestrator 在 `_calls_to_plan()` 中注入的，用于后续按 Skill 归组执行结果。

---

#### `PlannerOutput` (规划器输出 - 新版标准)
```python
class PlannerOutput(BaseModel):
    calls: List[SkillCall]             # Skill 调用列表
    reasoning: str                     # 规划推理说明
```

**来源**: `src-python/app/services/agent/schemas.py`

**用途**: Planner 的标准输出格式，由 Orchestrator 通过 `_calls_to_plan()` 转换为 `Plan`。

---

#### `SkillCall` (Skill 调用指令)
```python
class SkillCall(BaseModel):
    skill: str                         # Skill 名称
    args: Dict[str, Any]               # 从任务文本中提取的参数
    confidence: float                  # 匹配置信度 (0.0 ~ 1.0)
```

**来源**: `src-python/app/services/agent/schemas.py`

**生成**:
- `RuleBasedPlanner`: 关键词匹配 + `ParamExtractor.extract(task, skill_name)`
- `LLMPlanner`: LLM 推理后解析 JSON

---

### 2.3 执行层

#### `StepExecution` (步骤执行记录)
```python
class StepExecution(BaseModel):
    step_id: str
    step_number: int
    tool_name: str
    skill_id: Optional[str]            # 从 PlanStep 传入，用于按 Skill 归组
    parameters: Dict[str, Any]
    status: ExecutionStatus            # pending / running / completed / failed / skipped
    result: Optional[AgentToolResult]  # 工具执行结果
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: int
    error: Optional[str]
```

**来源**: `src-python/app/services/agent/executor.py:21-34`

**生成**: `Executor.execute_step()` 每执行一个 PlanStep 就创建一个 StepExecution。

---

#### `ExecutionResult` (执行结果汇总)
```python
class ExecutionResult(BaseModel):
    id: str
    plan_id: str
    request_id: str
    step_executions: List[StepExecution]  # 所有步骤的执行记录
    status: ExecutionStatus
    started_at: datetime
    completed_at: Optional[datetime]
    total_duration_ms: int
    final_summary: Optional[str]
    structured_output: Dict[str, Any]
    replan_count: int                  # 重规划次数 (仅 auto_remediation)
```

**来源**: `src-python/app/services/agent/executor.py:37-50`

**生成**: `Executor.execute_plan()` 返回。

---

#### `AgentToolResult` (工具执行结果)
```python
class AgentToolResult(BaseModel):
    id: str
    tool_name: str
    status: ToolStatus                 # success / error / partial
    output: Optional[Any]              # 工具输出 (通常是 dict 或 str)
    error: Optional[str]
    duration_ms: int
    metadata: Dict[str, Any]           # 元数据 (如 risk_level, error_type, verification_passed)
    timestamp: datetime
```

**来源**: `src-python/app/services/agent/tool_registry.py:33-43`

**生成**: `BaseTool.execute()` 或 MCP executor 返回。

---

### 2.4 报告层

#### `FinalReport` (最终报告 - 对外输出)
```python
class FinalReport(BaseModel):
    id: str
    request_id: str
    task: str
    status: str                        # running / completed / failed / partially_completed / ...
    skill_name: Optional[str]          # 主要执行的 skill 名称
    plan: Optional[Dict[str, Any]]     # 序列化后的 Plan
    traces: List[Dict[str, Any]]       # 执行追踪记录
    final: Optional[Dict[str, Any]]    # 汇总信息 (summary, evidence, risks, recommendations, commands, ...)
    skill_results: List[StructuredResult]  # 按 Skill 分组的结构化结果
    raw_summary: str                   # Markdown 格式的摘要
    structured_output: Dict[str, Any]  # 详细结构化输出 (含 remediation_report)
    total_duration_ms: int
    created_at: datetime

    # 自动修复扩展字段
    environment: Optional[Dict[str, Any]]  # 目标环境信息
    fixed_items: List[str]             # 已修复项
    unfixed_items: List[str]           # 未修复项
    blocked_items: List[str]           # 被阻塞项 (如权限不足)
    replan_count: int                  # 重规划次数
    final_status: Optional[str]        # 最终状态码
```

**来源**: `src-python/app/services/agent/orchestrator.py:110-133`

**生成**: `Orchestrator._assemble_report()` 组装后返回。

---

#### `StructuredResult` (单个 Skill 的结构化结果)
```python
class StructuredResult(BaseModel):
    id: str
    skill_name: str
    summary: str
    findings: List[Dict[str, Any]]     # 该 Skill 发现的安全问题
    recommendations: List[str]         # 建议
    risk_level: str                    # low / medium / high / critical
    metadata: Dict[str, Any]
```

**来源**: `src-python/app/services/agent/orchestrator.py:73-82`

**关键点**: 每个 StructuredResult **只基于该 skill 的步骤**，不再全局统计。

---

#### `NormalizedSecurityFinding` (标准化安全发现项)
```python
class NormalizedSecurityFinding(BaseModel):
    check_id: str                      # 唯一标识 (如 "detect_ssh_audit:1")
    module: str                        # 模块名 (ssh / firewall / network / process / ...)
    title: str                         # 人类可读的问题标题
    severity: str                      # critical / high / medium / low
    category: str                      # 分类 (authentication / network_exposure / ...)
    evidence: List[Any]                # 证据列表
    impact: str                        # 潜在影响
    reason: str                        # 为什么这是风险
    recommended_actions: List[str]     # 推荐操作
    fix_commands: List[str]            # 修复命令
    verify_commands: List[str]         # 验证命令
    rollback_commands: List[str]       # 回滚命令
    notes: List[str]                   # 注意事项
```

**来源**: `src-python/app/services/agent/schemas.py`

**生成**: `Orchestrator._normalize_findings_from_steps()` 从 StepExecution 中提取并标准化。

---

#### `SecurityRemediationReport` (安全整改报告)
```python
class SecurityRemediationReport(BaseModel):
    report_title: str
    executive_summary: str             # 高层摘要
    prioritized_plan: List[str]        # 优先级整改计划
    detailed_items: List[SecurityDetailedItem]  # 详细整改项
    normalized_findings: List[NormalizedSecurityFinding]  # 原始发现项
```

**来源**: `src-python/app/services/agent/orchestrator.py:102-107`

**生成**: `Orchestrator._build_security_remediation_report()` 构建。

---

## 三、扩展点详解

### 3.1 Planner Adapter 注入点

**位置**: `src-python/app/services/agent/planner.py:602-604`

```python
class LLMPlanner(BasePlanner):
    def set_llm_adapter(self, adapter: Any) -> None:
        """注入 LLM 调用适配器（需实现 .chat(messages) -> LLMResponse）"""
        self._llm_adapter = adapter
```

**扩展示例**:
```python
from app.services.agent.planner import LLMPlanner, create_planner
from app.services.agent.llm_adapter import UnifiedLLMAdapter

planner = create_planner(PlannerConfig(enable_llm_planner=True))
if isinstance(planner, LLMPlanner):
    llm_adapter = UnifiedLLMAdapter(your_custom_adapter)
    planner.set_llm_adapter(llm_adapter)
```

**约束**:
- Adapter 必须实现 `async chat(messages: List[Message]) -> LLMResponse`
- `LLMResponse` 需有 `content: str` 属性

**回退机制**:
- 无 adapter → 自动回退到 `RuleBasedPlanner`
- JSON 解析失败 → 回退到 `RuleBasedPlanner`
- LLM 返回无效 skill 名 → 过滤后若空则回退

---

### 3.2 Skill 扩展点

**位置**: `src-python/app/services/skill_engine/skill_loader.py`

**新增 Skill 步骤**:

1. **创建 SKILL.md (知识模式)**:
```markdown
---
name: my_custom_skill
description: 我的自定义技能描述
domain: custom
tags: [custom]
---
# My Custom Skill
## When to Use
- 当需要执行自定义操作时
## Workflow
### Step 1: 检查目标
### Step 2: 执行操作
```

2. **创建 skill.json (流水线模式)**:
```json
{
  "schema_version": "skill-spec/v1",
  "name": "my_custom_skill",
  "version": "1.0.0",
  "description": "我的自定义技能描述",
  "category": "investigation",
  "status": "active",
  "source": "generated",
  "steps": [
    {
      "id": "step1",
      "name": "检查目标",
      "description": "检查目标路径",
      "tool_name": "execute_command",
      "parameters": {"command": "ls -la /tmp"},
      "depends_on": []
    }
  ]
}
```

3. **(可选) hybrid 模式**: 同目录放 skill.json + SKILL.md，json 中加 `"knowledge_file": "SKILL.md"`

**加载方式**:
```python
from app.services.skill_engine import SkillLoader

loader = SkillLoader("skills/")
skills = loader.load_all()
# mode: "pipeline" | "knowledge" | "hybrid"
```

---

### 3.3 Tool Metadata 扩展点

**位置**: `src-python/app/services/agent/tool_registry.py:88-167`

**两种注册方式**:

#### 方式1: 继承 `BaseTool` (内置工具)
```python
from app.services.agent.tool_registry import BaseTool, AgentToolResult, ToolStatus

class MyCustomTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_custom_tool"

    @property
    def description(self) -> str:
        return "我的自定义工具"

    @property
    def parameters(self) -> List[Dict[str, Any]]:
        return [
            {"name": "param1", "type": "string", "description": "参数1"},
        ]

    async def execute(self, parameters: Dict[str, Any], context: Dict[str, Any]) -> AgentToolResult:
        try:
            # 执行逻辑
            result = do_something(parameters["param1"])

            return AgentToolResult(
                tool_name=self.name,
                status=ToolStatus.SUCCESS,
                output=result,
                metadata={
                    "risk_level": "low",      # 可选: low / medium / high / critical
                    "verification_passed": True,  # 可选: 验证是否通过
                    "error_type": None,        # 可选: permission_denied / file_not_found / ...
                },
            )
        except Exception as e:
            return AgentToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error=str(e),
                metadata={"error_type": "unknown"},
            )

# 注册
registry = get_default_registry()
registry.register(MyCustomTool())
```

#### 方式2: 注册 Executor (MCP Tools)
```python
from app.services.agent.tool_registry import ToolRegistry, AgentToolResult, ToolStatus

async def my_executor(params: Dict[str, Any], ctx: Dict[str, Any]) -> AgentToolResult:
    try:
        result = await call_external_api(params)
        return AgentToolResult(
            tool_name="my_mcp_tool",
            status=ToolStatus.SUCCESS,
            output=result,
        )
    except Exception as e:
        return AgentToolResult(
            tool_name="my_mcp_tool",
            status=ToolStatus.ERROR,
            error=str(e),
        )

registry = ToolRegistry()
registry.register_executor("my_mcp_tool", my_executor)
```

**Metadata 约定字段**:
| 字段 | 类型 | 用途 |
|------|------|------|
| `risk_level` | str | 风险等级 (low/medium/high/critical)，用于 Orchestrator 判定整体风险 |
| `verification_passed` | bool | 验证是否通过，用于自动修复场景 |
| `error_type` | str | 错误类型 (permission_denied / file_not_found / unsupported_distribution / ...)，用于重规划决策 |

**执行优先级**:
1. 优先走 `_executors` (MCP tools)
2. 再走 `_tools` (内置 BaseTool)

---

### 3.4 Report 构建解耦点

**位置**: `src-python/app/services/agent/orchestrator.py:332-442`

`_assemble_report()` 方法已拆分为多个子方法，可按需覆写或扩展：

| 子方法 | 职责 | 扩展场景 |
|--------|------|----------|
| `_group_steps_by_skill()` | 按 skill_id 分组步骤 | 自定义归组逻辑 |
| `_extract_findings_from_steps()` | 从步骤提取安全问题 | 自定义 finding 提取规则 |
| `_normalize_findings_from_steps()` | 标准化安全问题 | 添加新的检测模块模板 |
| `_build_security_remediation_report()` | 构建整改报告 | 自定义报告格式 |
| `_build_traces()` | 构建执行追踪 | 添加更多 trace 字段 |
| `_handle_remediation_classification()` | 自动修复分类 | 自定义 fixed/unfixed/blocked 判定逻辑 |
| `_build_structured_output()` | 构建结构化输出 | 添加自定义输出字段 |
| `_determine_final_status()` | 判定最终状态 | 添加新的状态码 |
| `_generate_final_summary()` | 生成 Markdown 摘要 | 自定义摘要格式 |

**扩展示例 - 添加自定义 finding 模板**:
```python
# 在 Orchestrator._finding_template() 中添加新模块
@staticmethod
def _finding_template(tool_name: str) -> Dict[str, Any]:
    templates = {
        # ... 现有模板
        "my_custom_detection": {
            "module": "custom",
            "category": "security",
            "title": "自定义检测问题",
            "impact": "潜在影响描述",
            "reason": "为什么这是风险",
            "recommended_actions": ["建议操作1", "建议操作2"],
            "fix_commands": ["修复命令1"],
            "verify_commands": ["验证命令1"],
            "rollback_commands": ["回滚命令1"],
            "notes": ["注意事项"],
        },
    }
    return templates.get(tool_name, {...})  # 默认模板
```

**扩展示例 - 自定义最终状态判定**:
```python
def _determine_final_status(self, report, execution_result, is_auto_remediation, ...):
    # 调用父类逻辑
    super()._determine_final_status(...)

    # 添加自定义状态
    if some_custom_condition:
        report.status = "custom_status"
        report.final_status = "custom_status"
```

---

## 四、关键设计决策

### 4.1 双模式 Planner

- **RuleBasedPlanner**: 关键词匹配 + 正则参数提取，无需 LLM，适合离线/低成本场景
- **LLMPlanner**: LLM 推理选择 skill + 提取参数，适合复杂任务理解
- **回退链**: LLMPlanner 失败 → RuleBasedPlanner；plan_calls 不可用 → plan()；plan 返回空 → _fallback_plan_from_skills()

### 4.2 Skill 动态构建

- **旧架构**: Planner 直接输出 Plan (固定步骤)
- **新架构**: Planner 输出 SkillCall (skill + args) → Skill.build_steps(args, ctx) 动态生成步骤
- **优势**: Skill 可根据参数自适应调整执行步骤，提高灵活性

### 4.3 按 Skill 归组结果

- **关键修复**: 每个 `StructuredResult` 只基于该 skill 的步骤，不再全局统计
- **实现**: `_group_steps_by_skill()` 按 `skill_id` 分组 `step_executions`
- **目的**: 避免不同 skill 的结果混淆，提高报告准确性

### 4.4 标准化安全问题

- **NormalizedSecurityFinding**: 统一的安全问题表示格式
- **提取逻辑**: 从 `AgentToolResult.output` 中解析，结合 `_finding_template()` 补全元数据
- **过滤逻辑**: `finding_filter.py` 中的 `filter_findings()` 过滤内部流程和无效发现

### 4.5 失败重规划 (仅 auto_remediation)

- **触发条件**: `is_auto_remediation == True` 且 `max_replan_attempts > 0`
- **不可重规划错误**: permission_denied / unsupported_distribution / high_risk_blocked / ssh_not_connected
- **重规划策略**: 根据 `error_type` 调整剩余步骤 (如 file_not_found → 跳过相关步骤)

---

## 五、常见问题排查

### Q1: 如何调试 Planner 选择了错误的 Skill?

**排查步骤**:
1. 检查 `RuleBasedPlanner.KEYWORD_MAPPING` 中是否有对应关键词
2. 查看 `PlannerOutput.reasoning` 字段了解匹配依据
3. 如需更精准匹配，调整关键词权重或改用 LLMPlanner

### Q2: 为什么 Skill 的步骤没有按预期执行?

**排查步骤**:
1. 检查 `build_steps(args, context)` 接收到的 `args` 是否正确
2. 查看 `ParamExtractor.extract()` 是否正确提取了参数
3. 确认 `context` 中包含所需依赖 (如 `ssh_manager`)

### Q3: 如何添加新的检测模块到整改报告?

**步骤**:
1. 在 `Orchestrator._finding_template()` 中添加新模块模板
2. 在 `_normalize_findings_from_step()` 中添加工具名到模块的映射
3. 确保工具返回的 `AgentToolResult.metadata.risk_level` 正确设置

### Q4: MCP Tools 未生效?

**排查步骤**:
1. 确认 `settings.agent.mcp_enabled == True`
2. 确认 `settings.agent.mcp` 配置正确
3. 查看 `load_mcp_tools_if_enabled()` 日志，确认 MCP adapter 初始化成功
4. 检查 `ToolRegistry._executors` 中是否包含预期的 tool name

---

## 六、附录

### A. 内置 Skills 列表

| Skill 名称 | 分类 | 描述 |
|-----------|------|------|
| `host_triage` | triage | 主机快速评估 |
| `log_investigation` | investigation | 日志调查分析 |
| `process_hunt` | investigation | 进程狩猎 |
| `port_hunt` | investigation | 端口扫描 |
| `ssh_audit` | audit | SSH 安全审计 |
| `fix_advisor` | remediation | 修复建议 |
| `capability_check` | triage | 环境能力检查 |
| `hardening_baseline` | audit | 安全基线检查 |
| `auto_remediation` | remediation | 自动修复 (支持重规划) |
| `incident_timeline` | investigation | 事件时间线还原 |
| `remediation_verification` | remediation | 修复效果验证 |
| `safe_config_patch` | remediation | 安全配置修补 |

### B. 内置 Tools 类别

| 类别 | 注册函数 | 示例工具 |
|------|---------|---------|
| System | `register_system_tools()` | get_hostname, get_os_info, check_sudo |
| Detection | `register_detection_tools()` | detect_ssh_audit, detect_port_scan, detect_process |
| Log | `register_log_tools()` | read_system_log, read_journalctl_log |
| File | `register_file_tools()` | read_file, list_files, analyze_file |
| Command | `register_command_tools()` | execute_command, execute_with_timeout |
| Remediation | `register_remediation_tools()` | patch_ssh_config, patch_firewall, patch_user_permissions |

### C. 相关文件索引

```
src-python/app/
├── routers/
│   └── api.py                          # HTTP 入口 (agent_run, agent_get_skills, ...)
├── services/agent/
│   ├── orchestrator.py                 # 核心编排器
│   ├── planner.py                      # 规划器 (RuleBased / LLM)
│   ├── executor.py                     # 执行器
│   ├── tool_registry.py                # 工具注册表
│   ├── schemas.py                      # 共享数据模型
│   ├── finding_filter.py               # 发现项过滤器
│   ├── context_builder.py              # 上下文构建器
│   ├── llm_adapter.py                  # LLM 适配器
│   ├── mcp.py                          # MCP 集成
│   ├── skills/
│   │   ├── registry.py                 # Skill 注册表
│   │   └── *.py                        # 具体 Skill 实现
│   └── tools/
│       └── *.py                        # 具体 Tool 实现
```

---

**文档维护**: 当上述文件发生结构性变更时，请同步更新本文档。
