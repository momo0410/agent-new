# SDIT 实施进度与最终版就绪度

## 1. 本次迭代范围

本次实施以以下两份文档为基线：

- `SDIT_当前项目改善与实施路线图_v1.0.docx`
- `SDIT_终极目标产品需求规格说明书_v1.0.docx`

落地重点覆盖路线图 P0（真实性、安全、审计基础）与 P1（控制平面解耦）的首轮可验收增量，同时对发布、依赖和高风险安全检查进行了收口。

## 2. 已落地能力

### P0：真实结果、安全边界、审计

- `src-python/app/core/contracts.py`
  - Scope Contract、Action Envelope、Event Envelope、Evidence Record、Finding Record。
  - 明确 `UNOBSERVED`、`DISCOVERED`、`SUSPECTED`、`CANDIDATE`、`ATTEMPTED`、`VERIFIED_VULNERABLE`、`EXPLOITED`、`SESSION_ESTABLISHED`、`PRIVILEGE_CONFIRMED`、`EVIDENCE_COMPLETE`、`EXHAUSTED`、`NOT_APPLICABLE` 状态。
- `src-python/app/core/evidence.py`
  - 证据规则注册、状态迁移、会话挑战、权限确认和原始证据哈希。
  - 工具退出码、框架完成消息、模型判断、端口开放等信号不再单独形成高结论。
- `src-python/app/core/event_store.py`
  - JSONL 追加式 Event Store。
  - 顺序号、前序哈希、事件哈希、读取、回放和篡改校验。
- `src-python/app/core/session_manager.py`
  - 会话创建、挑战验证、目标/任务/身份绑定、心跳和关闭。
- `src-python/app/core/scope_policy.py`
  - HMAC Scope Token、目标/CIDR/端口/动作级策略判断。
  - `Executor.run()` 在工具分发前生成并校验 Action Envelope；策略拒绝进入事件流。
- `src-python/app/core/local_auth.py`
  - 本地短时会话令牌、来源校验、敏感 Agent API 与 WebSocket 防护。
- `src-python/app/core/done_gate.py`
  - 高价值未覆盖面、报告完整性、预算、取消状态参与 Done 判定。
- `src-python/app/core/teaching_report.py`
  - 事实、推断、攻击路径、失败路径、防御视角和覆盖度的结构化教学报告。

### P1：状态与前端解耦

- `State` 增加事件旁路记录：`<state_path>.events.jsonl`。
- 发现、漏洞、里程碑、会话、动作、阶段和任务完成等关键变更进入事件流。
- `src/modules/tasks/taskStore.ts`
  - 版本兼容、幂等去重、乱序缓冲、未知版本忽略、状态折叠。
- `src/modules/tasks/contracts.ts`
  - 前端事件、快照、阶段、证据、预算和策略告警类型。

### P2：资产图与 Must-Try 基座

- `src-python/app/core/asset_graph.py`
  - 从现有 State 快照重建目标、服务节点和暴露边。
  - 节点去重、服务状态、评分和确定性 Must-Try 队列。
- 报告 View Model 增加 `asset_graph`，为后续 Planner 图消费和前端可视化保留稳定接口。

### 发布与安全质量

- CI 分支触发与当前仓库 `master` 对齐。
- 新增控制平面 Ruff、mypy、Bandit 高等级检查。
- 基准门禁对“无测试文件、跳过、空结果”执行失败处理。
- 生产依赖审计结果为 0 个 high 及以上漏洞。
- 在线搜索缓存改用 SHA-256。
- AES 兼容实现统一使用 `cryptography`，并修正 ECB 上下文使用。
- 现有 shell 执行路径保留范围策略和运行时边界，安全扫描对这些明确入口进行逐处标注。
- `httpx` 约束为 `<0.28.0`，与当前 FastAPI/Starlette 测试客户端兼容。

## 3. 与路线图及 PRD 的对应关系

| 能力域 | 状态 | 主要落点 |
|---|---|---|
| Scope Contract / Scope Token | 已落地动作级首轮 | `core/contracts.py`, `core/scope_policy.py`, `routers/api.py`, `executor.py` |
| 证据驱动状态机 | 已落地首轮 | `core/evidence.py`, `state.py` |
| Event Store / replay 基础 | 已落地旁路版本 | `core/event_store.py`, `state.py` |
| Session Manager | 已落地首轮 | `core/session_manager.py` |
| Done Gate | 已接入 Agent | `core/done_gate.py`, `agent.py` |
| 本地 API / WebSocket 会话防护 | 已落地 | `core/local_auth.py`, `main.py`, `python-api.config.ts`, `SSHTerminal.vue` |
| 前端 Task Store / Event Folding | 已落地首轮 | `src/modules/tasks/` |
| 事实优先教学报告 | 已落地首轮 | `core/teaching_report.py`, `state.py` |
| Asset Graph / Must-Try Queue | 已落地数据基座 | `core/asset_graph.py`, `state.py` |
| Web 现代攻击面统一抽象 | 下一阶段主线 | Web 插件、证据规则、路由与参数图 |
| Skill 生命周期、沙箱、Canary、回滚 | 下一阶段主线 | 技能注册、评估、版本与运行时隔离 |
| Event Store 主读模型切换 | 下一阶段主线 | 快照重建、迁移脚本、UI 全量消费事件 |

## 4. 验证结果

在当前工作区执行：

```text
Backend: 346 passed, 1 skipped
Control plane: 8 passed
Protocol/P8: 43 passed
API: 12 passed
Frontend Vitest: 9 passed
Frontend build: passed
Production npm audit: 0 vulnerabilities
Control-plane Ruff: passed
Control-plane mypy: passed
Bandit high/critical scan: passed
Local session auth smoke: 401 -> 200 -> 404 expected flow passed
git diff --check: passed
```

## 5. 下一阶段的最终版收口项

以下项目已经拆成明确的工程收口项，适合继续按路线图推进：

1. 将 Event Store 从 State 旁路记录推进到主读模型，补齐快照重建、迁移、回放和 UI 全链路消费。
2. 将现有资产图和 Must-Try Queue 接入 Planner，输出资产覆盖、证据覆盖和停止原因指标。
3. 为现代 Web 插件补齐身份态、路由、参数、API schema、业务逻辑和证据规则的统一模型。
4. 将技能注册、静态检查、基准评估、Canary、版本回滚和运行时隔离接入统一生命周期。
5. 用路线图中的真实 Alpha/Beta 数据集跑出 VATR、VPR、会话精度、误报率、Done Gate 早退率和恢复成功率，并把结果写入发布报告。
6. 完成密钥链/操作系统凭据存储迁移，逐步收窄 legacy 明文凭据路径。

## 6. 交付判定

当前版本已形成可运行、可测试、可审计的首个控制平面增量，作为路线图 P0/P1 的实施基线。发布到路线图定义的 Alpha/Beta“最终版”前，应完成第 5 节的动作级策略接入、事件主读模型、图规划、Web 统一模型、技能生命周期及真实数据集门禁；这些项目已有代码入口和测试基座，可在现有分支上连续迭代。
