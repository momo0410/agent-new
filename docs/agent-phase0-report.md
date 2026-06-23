# Agent Phase 0 基线稳固改造报告

## 目标与边界

本次改造聚焦 Agent 核心链路的“稳定、可回归、可调试”，遵循以下约束：

- 不破坏现有 API 路由兼容性
- 不删除现有能力，只做增强与缺陷修复
- 不做无根据的大重构
- 所有代码改动均补充测试
- 新增日志统一采用结构化日志

本轮改造覆盖的核心链路包括：

- `AgentOrchestrator`
- `Planner`（rule planner / llm planner）
- `RuntimeSkillFactory`
- `SkillGenerationService`
- `TargetSkillGenerator`
- `PolicyGuard`

## 识别到的问题清单

### 1. Target skill 生成存在真实运行时错误

`target_skill_generator.py` 中的 `_make_web_probe_skill`、`_make_graphql_skill`、`_make_api_skill` 直接引用了未定义的 `context` 变量。  
在 `remote_target` 场景触发生成时，会直接抛出 `NameError`，导致：

- `TargetSkillGenerator.generate()` 失败
- `SkillGenerationService.generate_target_skill()` 跟随失败
- 自适应 target skill 生成链路中断

### 2. Orchestrator 在 target 模式下过早失败

`orchestrator.py` 在“初始技能解析为空”时直接 fail-fast。  
这会阻断本该进入的“自适应 target skill 生成 -> replan”路径，导致：

- 对远程 URL / GraphQL / API 靶标的动态探测能力无法发挥
- 规划前就提前终止，无法体现已有 target skill 生成机制

### 3. Remote target / target via SSH 判断混淆

`orchestrator.py` 内部对 `is_remote`、`remote_target_via_ssh`、`target_url` 的组合判断不够严谨，存在模式混叠风险，表现为：

- 某些 via-SSH 请求被当作普通 remote target 处理
- 失败原因和 fallback 行为不准确
- 生成 / 重规划日志不够可靠

### 4. Planner 缺少结构化可观测性，LLM fallback 不可追踪

`planner.py` 中 LLM planner 的关键分支仍使用 `print()`。  
实际问题包括：

- 无法稳定按字段检索 fallback 原因
- 无法明确区分 rule planner / llm planner 使用情况
- 缺少 `request_id`、`planner_mode`、`fallback_used`、`llm_used` 等排障字段

### 5. RuntimeSkillFactory 对异常配置容错不足

`runtime_skill_factory.py` 存在以下风险：

- `build_steps()` 对 `args=None` / `context=None` 处理不稳
- required 参数为 `None` 时未被视为缺失
- `create_skills_from_configs()` 未先严格校验配置
- 批量创建失败时使用 `print()`，不利于回归与排障

### 6. SkillGenerationService 异常传播过于直接

`skill_generation_service.py` 对 target skill 生成异常缺少兜底处理。  
问题表现为：

- generator 内部异常会直接冒泡到上层
- 目标技能生成失败时无法返回可诊断的 warnings
- 生成技能的工具校验只依赖 `tool_registry.get()`，对 executor-backed tool registry 兼容性不足

### 7. PolicyGuard 评估结果没有稳定回写到 PlanStep

`policy_guard.py` 虽然完成了评估，但没有把关键结果稳定写回 `PlanStep`，导致：

- `requires_approval`
- `supports_dry_run`
- `risk_level`

这些字段在后续报告、调试或序列化输出中可能不一致。

### 8. Compatibility fallback 路径仍混入非结构化输出

`orchestrator.py` 的 `_execute_web_research()` 作为兼容 helper 仍保留 `print()`，会造成：

- 同一请求内混合结构化日志与标准输出
- fallback 研究链路不便于检索和回放
- 线上问题排查时上下文字段缺失

## 修改文件列表

### 代码修复

- `src-python/app/services/agent/log_utils.py`
- `src-python/app/services/agent/planner.py`
- `src-python/app/services/agent/orchestrator.py`
- `src-python/app/services/agent/runtime_skill_factory.py`
- `src-python/app/services/agent/skill_generation_service.py`
- `src-python/app/services/agent/target_skill_generator.py`
- `src-python/app/services/agent/policy_guard.py`

### 测试补充

- `src-python/tests/agent/__init__.py`
- `src-python/tests/agent/unit/__init__.py`
- `src-python/tests/agent/integration/__init__.py`
- `src-python/tests/agent/unit/test_planner.py`
- `src-python/tests/agent/unit/test_runtime_skill_factory.py`
- `src-python/tests/agent/unit/test_skill_generation_service.py`
- `src-python/tests/agent/unit/test_target_skill_generator.py`
- `src-python/tests/agent/unit/test_policy_guard.py`
- `src-python/tests/agent/integration/test_orchestrator.py`

## 逐项修改说明

### 1. `log_utils.py`

新增轻量结构化日志辅助函数 `log_event()`：

- 统一将日志编码为 JSON 行
- 自动规范化 `Enum`、`dict`、`list` 等字段
- 让普通日志 formatter 下仍能保留结构化字段

这一步是本轮“可调试化”的基础设施，不改变业务行为。

### 2. `planner.py`

改造点：

- 为 planner runtime 信息补充 `planner_mode`
- 明确记录 `llm_used`
- 为 rule planner / llm planner 暴露统一 runtime info
- 将 LLM planner 的关键 `print()` 替换为结构化日志
- 在 fallback 分支显式记录：
  - `request_id`
  - `planner_mode`
  - `fallback_used`
  - `llm_used`

结果：

- 可以从日志直接判断是否走了 LLM
- 可以区分是“LLM 正常规划”还是“LLM 失败后回落 rule planner”
- 为回归测试提供稳定断言面

### 3. `target_skill_generator.py`

修复点：

- 将 `context` 显式传入：
  - `_make_web_probe_skill()`
  - `_make_graphql_skill()`
  - `_make_api_skill()`

结果：

- 修复 remote target 生成链路的 `NameError`
- 已有 generated skill / target skill 机制可以恢复可执行状态
- `known_app_queries` 等上下文能够正确进入生成步骤

这是本轮最明确的显式运行时 bug 修复之一。

### 4. `skill_generation_service.py`

改造点：

- `generate_target_skill()` 对 generator 异常做兜底
- 生成失败时返回 warnings / recommendation，而不是直接炸栈
- 对生成技能的工具可执行性校验增加兼容：
  - 优先使用 `has_tool()`
  - 无该接口时回退到 `get()`
- 增加 target skill 校验失败的结构化日志

结果：

- target skill 生成失败不再拖垮整个链路
- executor-backed registry 场景下的生成技能更容易通过校验
- 错误信息可用于前端展示和后续排障

### 5. `runtime_skill_factory.py`

改造点：

- `build_steps()` 兼容 `args=None`、`context=None`
- required 参数显式为 `None` 时也视为缺失
- `create_skills_from_configs()` 在创建前先做 `validate_config()`
- 批量创建遇到非法配置时改为结构化日志，不再使用 `print()`
- 增强配置校验：
  - 空 `tool_name` 判定为非法
  - 非 list 的 `parameters` 判定为非法

结果：

- runtime declarative skill 的工厂行为更稳定
- 非法配置不会直接污染批量创建结果
- 更适合后续接入自动回归与配置排障

### 6. `policy_guard.py`

改造点：

- `evaluate_plan()` 评估后将以下字段回写到 `PlanStep`：
  - `requires_approval`
  - `supports_dry_run`
  - `risk_level`
- 增加计划评估摘要的结构化日志

结果：

- plan 的安全评估结果在内存对象、输出结果、后续报告之间保持一致
- 后续审批链路和调试链路可以复用同一份 step 元数据

### 7. `orchestrator.py`

改造点分为四类。

#### 7.1 目标模式识别与 fail-fast 修正

- 增加辅助判断逻辑，明确 target request 识别
- `remote_target_via_ssh` 与普通 `remote_target` 分支拆清
- 当 target 模式下初始技能为空时，不再提前失败，而是允许进入 `_obtain_plan()`

结果：

- 自适应 target skill 生成 / replan 链路恢复可达
- 避免“还没开始规划就提前终止”的错误行为

#### 7.2 规划与执行的关键结构化日志

新增或增强关键事件日志，包括：

- run 启动
- target 模式下初始技能为空
- plan ready
- execution complete
- adaptive generate-and-replan 的开始 / 失败 / 成功 / 后续失败

关键字段统一补充：

- `request_id`
- `planner_mode`
- `fallback_used`
- `llm_used`

结果：

- planner 与 orchestrator 的诊断链路打通
- 回归测试可以对关键状态做日志级断言

#### 7.3 兼容 web research fallback 路径去 `print()`

`_execute_web_research()` 中原有 `print()` 全部替换为结构化日志事件：

- `orchestrator_web_research_started`
- `orchestrator_web_research_unavailable`
- `orchestrator_web_research_failed`
- `orchestrator_web_fetch_failed`
- `orchestrator_web_research_completed`
- `orchestrator_web_research_exception`

结果：

- fallback 路径与主链路日志风格统一
- 兼容模式下也能按请求定位问题

#### 7.4 执行结果兼容性增强

在测试 / mock / 部分执行器返回对象不完整时，执行结果状态读取改为更稳健的 `getattr` 方式，减少测试和集成场景下的脆弱性。

### 8. 测试目录与基础用例

新增目录：

- `src-python/tests/agent/unit`
- `src-python/tests/agent/integration`

新增测试覆盖：

- `planner.py`
  - 验证 LLM planner fallback 的 runtime info
  - 验证结构化日志字段完整
- `orchestrator.py`
  - 验证 target 模式下不会在 adaptive planning 前过早失败
  - 验证 compatibility web research fallback 的结构化日志
- `runtime_skill_factory.py`
  - 验证 `None` 输入容错
  - 验证 required 参数校验
  - 验证非法配置被跳过并记录日志
- `skill_generation_service.py`
  - 验证 generator 异常被兜底并产出 warnings
  - 验证 executor-backed tool registry 的工具校验
- `target_skill_generator.py`
  - 验证 web / graphql / api 三类 target skill 生成时上下文被正确传递
- `policy_guard.py`
  - 验证评估结果被回写到 `PlanStep`
  - 验证结构化评估日志输出

## 测试说明

本轮主要回归命令：

```powershell
.\.venv\Scripts\python -m pytest tests/agent/unit tests/agent/integration tests/test_planner_whitelist_filter.py tests/test_runtime_skill_components.py tests/test_orchestrator_execution_mode_integration.py tests/test_orchestrator_policy_integration.py -q
```

结果：

- `59 passed`

说明：

- 新增基线测试已接入现有 pytest 体系
- 本轮改动未引入已覆盖范围内的回归
- 未修改 API 路由层，因此无需额外变更接口兼容测试

## 剩余风险

### 1. 仍存在历史代码与编码质量债

`orchestrator.py` 内部仍有较多历史兼容 helper，虽然本轮已稳定核心链路，但该文件整体职责仍偏重，后续仍建议逐步拆分“规划 / 研究 / 报告 / target skill 自适应”逻辑边界。

### 2. 现有时间处理存在弃用告警

测试过程中仍可见部分 `datetime.utcnow()` 的 deprecation warning。  
这不属于本轮主链路稳定性阻塞项，但建议在后续阶段统一替换为 timezone-aware 时间处理。

### 3. fallback 行为已可观测，但尚未形成统一事件规范

本轮已为关键链路补齐结构化日志字段，但全仓库范围内尚未形成统一 event 命名规范、字段字典和日志采样策略。  
若后续要接入 ELK / Loki / OpenTelemetry，建议单独做一次 observability 规范化。

### 4. 生成技能质量仍依赖上游策略质量

本轮修复的是“能生成、能校验、失败可诊断”，并未改变生成策略本身的能力上限。  
也就是说：

- 生成失败现在更稳
- 生成出的技能更容易被执行
- 但 skill 语义质量依然取决于上游规则和 LLM 输出质量

## 结论

Phase 0 已完成“基线稳固”目标中的关键部分：

- 修复了 target skill 生成的显式运行时错误
- 恢复了 target 模式下 adaptive planning 的可达性
- 为 planner / orchestrator / policy / runtime skill factory 等关键模块补齐最小回归测试
- 将核心排障信息统一到结构化日志中

当前系统仍保持原有 API 与能力边界，但 Agent 主链路的稳定性、可回归性和可调试性已有明显提升。
