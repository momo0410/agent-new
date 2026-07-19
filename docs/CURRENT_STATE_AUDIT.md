# SDIT Pentest Agent 当前状态审计

审计日期：2026-07-18（Asia/Shanghai）  
审计分支：`master`  
审计基线提交：`f9a6d0b0427dc39d206a8189fa7dba2f2fb06ee4`  
审计范围：仓库代码、配置、测试、工作流、报告、运行产物以及两份 V1.0 需求文档。

> 本文件只记录可从代码、命令输出或测试结果复核的事实。`已实现`表示存在可调用实现；`已验证`还要求验收场景、证据和发布环境均已闭环。当前项目仍处于 Alpha 级，未把模块数量折算成产品完成度。

## 1. 结论摘要

| 维度 | 审计结论 | 证据 |
|---|---|---|
| 产品形态 | Vue 3/TypeScript 前端 + FastAPI/Python 后端，兼容桌面桥接与本地 HTTP | `package.json`、`src-python/app/main.py`、`src/shims` |
| Agent 骨架 | 八阶段状态机、Planner、Executor、Critic、Reflection、Skill Engine、报告模块均存在 | `src-python/app/services/pentest_agent/` |
| 本轮新增底座 | Scope Contract、Judge Registry、严格会话判定、事件幂等、资产归一化、候选评分、进程监督、模型网关、报告契约、审计链、任务事件存储、评测门禁 | `src-python/app/core/` |
| 后端回归 | 366 passed, 1 skipped；覆盖率 56%；313 条依赖/运行时弃用警告 | `python -m pytest tests -q --cov=app` |
| 前端回归 | 9 passed；Statements 63.10%，Branches 34.66%，Functions 62.85%，Lines 66.45% | `npm run test:coverage` |
| 静态质量 | 核心范围 Ruff 通过；核心范围 mypy 无 error；Bandit `-lll` 高严重度 0 | 本轮命令输出 |
| 发布状态 | Web 构建通过；仍缺少真实 Tauri 工程与跨平台发布产物验证 | `npm run build`、`.github/workflows/release.yml` |
| 泛化状态 | 已清理生产 Python 中的固定路由探测地址和单目标分支；隐藏集尚未接入真实目标管理 | `agent.py`、`state.py`、`exploit_retry.py`、`evaluation.py` |

**总体判断：** 当前代码已经从“功能集合”进入“控制面骨架”阶段，但新控制面还没有覆盖所有旧 API、旧状态路径和所有工具适配器。最重要的剩余工作是把契约真正接入端到端编排，并用隐藏基准、现代 Web fixture、恢复测试和发布流水线证明行为。

## 2. 仓库与入口审计

### 2.1 目录结构

| 区域 | 主要内容 | 观察 |
|---|---|---|
| `src/` | Vue 页面、模块、Store、Tauri shim | 页面能力丰富；入口和部分桥接仍偏集中 |
| `src-python/app/main.py` | FastAPI、CORS、HTTP/WS 中间件、终端 WS | 本地会话令牌、Origin、请求大小和速率限制已存在；路由保护仍按旧前缀分层 |
| `src-python/app/routers/api.py` | 大量桌面/SSH/SFTP/Agent API | 单文件约 2200 行，领域路由尚未拆分 |
| `src-python/app/core/` | 新控制面契约与服务 | 已形成可独立测试的领域层 |
| `src-python/app/services/pentest_agent/` | 主循环、规划、执行、状态、报告、技能 | `agent.py`、`executor.py`、`state.py`、`planner.py` 仍是主要单体 |
| `src-python/tests/` | 现有回归、P0-P9、核心控制面测试 | 数量较多；真实集成/隐藏集比例仍低 |
| `docs/` | 架构、路线、进度和测试说明 | 旧进度文档与实际 CI 曾存在不一致，本审计以代码和命令为准 |
| `reports/` | 靶场记录、批次报告和历史产物 | 证据丰富但格式不完全统一，部分报告状态语义过宽 |
| `.github/workflows/` | CI、benchmark、release | CI/benchmark 已收紧；release 仍引用缺失的 Tauri 目录 |

### 2.2 Git 与仓库卫生

- 当前分支为 `master`。
- 审计开始时 HEAD 为 `f9a6d0b`，之后形成 27 个已修改文件和 22 个未跟踪文件；本轮变更尚未形成最终提交。
- 运行缓存和构建目录包括 `coverage/`、`dist/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`、`.benchmarks/`。其中部分已被忽略，部分基线 JSON 需要归档或清理。
- `src-python` 曾包含 `--help`、`--version*`、`-V*`、扫描日志、恢复文件等已跟踪运行产物；这些文件与可复现构建无关，应在仓库卫生批次中移除并保留历史证据副本。
- 根目录仍有大量截图、批次状态 JSON 和旧脚本；它们需区分“产品资产”“测试 fixture”和“个人运行产物”。

## 3. 运行与编排链审计

### 3.1 前端

- `src/main.ts` 是应用启动入口，承载路由/模块装配；`src/modules/tasks/taskStore.ts` 已开始按事件折叠任务、资产、候选、动作和证据。
- `src/config/python-api.config.ts` 统一 HTTP API 请求，并将本地会话令牌保存在运行时内存；WebSocket 改为先取得一次性 ticket，不再把长令牌放入 URL。
- `src/components/SSHTerminal.vue` 仍负责较多终端状态与连接逻辑；终端、任务控制和报告视图尚未完全拆成独立域。
- Vite 已配置 vendor 分块；构建通过，但应用入口仍约 2.73 MB，且存在动态/静态导入混用告警。

### 3.2 后端

- `app/main.py` 提供 FastAPI 生命周期、CORS、本地会话、HTTP/WS 入口和健康检查。
- `app/routers/api.py` 包含桌面窗口、设置、SSH/SFTP、检测、Agent、Skill、知识库等 API；业务职责集中，后续应按 mission/scope/event/evidence/session/report/skill 分路由。
- `app/services/pentest_agent/agent.py` 仍是主编排器；已有状态、候选、反思、报告和在线情报调用，但新 `EventSourcedTaskStore` 尚未成为唯一事实源。
- `executor.py` 已接入 ScopePolicy、ActionEnvelope、Kill Switch、进程组终止和参数化执行路径；仍有旧分支直接调用子进程或 Shell，需逐个迁移到统一 Plugin Contract。
- `state.py` 仍保存兼容旧报告的数据结构；旧字段与 canonical EvidenceStatus 之间需要迁移器和双写一致性测试。

### 3.3 WebSocket 与 SSH

- 终端和事件 WS 在握手时校验 Origin，并支持请求头令牌或一次性 ticket。
- HTTP 中间件检查 Host、Origin、请求体大小和速率；Agent/State/Report/History 旧前缀要求本地会话。
- SSH 管理器有通道并发、连接健康和终端清理逻辑；跨重启恢复、任务级句柄和审计事件仍需统一。
- `/ssh/decrypt-password` 仍是旧的明文返回接口，需迁移到只返回 SecretRef、仅在服务端解析的凭据流程。

## 4. 控制面审计

### 4.1 Scope 与安全策略

`app/core/contracts.py` 与 `app/core/scope_policy.py` 已提供：

- 不可变 ScopeContract、目标/CIDR/域名、端口、协议、时间窗、动作等级、预算、并发、速率、凭据/上传/会话/权限开关、保留策略和 revision hash。
- HMAC Scope Token，绑定 scope、mission、revision 和 contract hash。
- DNS 全地址解析校验、危险操作识别、紧急停止、审计记录、预算计数和动作幂等重放。
- Executor 在进入执行路径前重新做策略决策，并在下一动作或停止时释放并发占用。

尚存边界：旧 SSH/SFTP/检测 API 没有全部转换为 ActionEnvelope；重定向、代理、回连和会话发现目标尚未由统一网关接管；课程模板和管理员不可放宽策略尚未完成。

### 4.2 证据与判定

`contracts.py`、`evidence.py`、`judges.py`、`session_manager.py` 已形成：

- canonical 状态枚举和迁移表；高价值状态需要证据。
- 版本化 Judge Registry，包含 13 类基础 Judge。
- 严格会话证明：目标绑定、随机 challenge、两个不同命令、身份输出、心跳。
- EvidenceRuleRegistry、负向证据和状态清单。

尚存边界：旧 `success_judge.py` 与新 Judge Registry 尚未完全合并；所有历史报告、API response 和前端状态尚未统一迁移；复现运行器和 Artifact 外部存储仍是接口级能力。

### 4.3 事件、幂等与恢复

- `event_store.py` 提供不可变事件、hash chain、幂等 key、批量追加、事件流和 projector 注册表。
- `task_store.py` 能从事件重建任务、识别运行中动作、生成 snapshot。
- `failure_recovery.py` 提供失败分类和恢复优先级；`planner_contracts.py` 提供 stagnation detector。

尚存边界：生产主循环仍以旧 State 为主；恢复动作的安全审批、跨进程锁、队列重建和真实重启演练尚未闭环。

### 4.4 资产、规划与工具

- `asset_graph.py` 支持节点/边来源、时间、置信度、TTL、冲突和去重。
- `asset_normalizer.py` 将结构化/文本观察转成统一 Observation，并保留原始摘要引用。
- `planner_contracts.py` 的 CandidateAction/Scorer/PlanGraph/StagnationDetector 已可独立运行。
- `plugin_contract.py`、`tool_registry.py` 已统一插件元数据、输入/输出 Schema、证据、取消、dry-run、模拟和清理字段。
- `process_supervisor.py` 提供进程组、超时、输出上限、取消和 dry-run；显式 Shell 使用解释器参数数组。

尚存边界：旧 Planner 仍有大量工具特定分支；Tool Health、版本指纹和语义等价回退尚未由新 registry 统一驱动；资源限制和环境白名单尚未在所有平台可验证。

### 4.5 Web、模型与 Skill

- `web_model.py` 已有 WebSite、Endpoint、Parameter、AuthSession、Role、CrawlerPolicy 基础对象，并识别危险方法。
- `model_gateway.py` 已有输入脱敏、调用记录、输出 hash、Schema 校验和 token/cost 预算。
- `skill_contract.py` 和 `lifecycle_manager.py` 已有 manifest、评测记录、内容扫描、draft/canary/active/rollback/quarantine 等生命周期概念。

尚存边界：现代 Web 爬虫、认证浏览器、角色差异 Judge、DOM/网络回放和正负样本集尚未形成端到端闭环；真实外部模型调用尚未强制经过 Gateway；自动生成 Skill 的沙箱执行器与隐藏集晋级门禁仍需接入。

## 5. 测试与质量审计

### 5.1 本轮实际结果

| 检查 | 结果 | 备注 |
|---|---|---|
| 后端全量 | 366 passed, 1 skipped | Python 3.14.2，约 99 秒 |
| 后端覆盖率 | 56% | 新控制面若干模块覆盖率较高，主编排与 API 仍偏低 |
| 新控制面 | 17 passed | `tests/test_final_control_plane.py` |
| 前端单测 | 9 passed | 2 files |
| 前端覆盖率 | 63.10/34.66/62.85/66.45 | statements/branches/functions/lines |
| 前端类型与构建 | 通过 | `npm run build` |
| 核心 Ruff | 通过 | `app/core`、tool registry、lifecycle manager |
| 核心 mypy | 无 error | 保留 untyped body notes |
| Bandit high-only | 0 high | 全 app `bandit -r app -lll` |
| npm audit | 0 high/critical | 337 total dependencies |
| Scope benchmark | 均值约 0.028 ms | 门槛 5 ms |

### 5.2 主要测试缺口

1. 新 Judge 的分支覆盖偏低，尤其是负样本、冲突证据、版本迁移和复现失败。
2. ProcessSupervisor 的 Linux/Windows 进程组、孤儿进程和高输出压力测试尚未双平台跑通。
3. 新事件存储与旧 State 尚未进行 Golden Trace 一致性比较。
4. 没有真正隐藏、不可由运行时读取的 Benchmark fixture；现有 benchmark 主要验证策略性能。
5. 现代 Web 正/负样本、认证、越权、非 Shell 影响和危险链接控制尚未覆盖。
6. 前端任务 Store 增量事件、暂停/终止、证据查看和无障碍检查仍缺测试。

## 6. 安全审计结果

### 已加固项

- 本地会话令牌、生命周期、Origin 白名单、Host 白名单、请求大小和速率限制。
- WebSocket 长令牌从 query string 移除，改用 header 或一次性短票据。
- Scope Token 与 contract hash/revision 绑定；策略决策写入审计列表。
- LLM Gateway 输入脱敏和 SecretStore 的 opaque reference 接口。
- 进程监督、Kill Switch、输出上限、显式解释器入口。
- CI 中 Bandit 高严重度和 npm audit 作为阻断步骤；Benchmark 缺结果时失败。

### 高优先级剩余项

- 旧普通 API 面仍有大量直接 SSH/SFTP/文件写入操作，尚未统一经过任务级 Scope 和审计。
- `decrypt-password` 会把凭据明文返回给调用方；应废弃该路径并改为服务端 SecretRef 解析。
- 生产配置、日志和报告的敏感级别访问控制尚未形成四级日志/证据权限模型。
- 外部情报、网页内容和模型输出仍需统一作为不可信输入，禁止直接改变策略或触发高风险动作。
- `release.yml` 仍假定 `src-tauri` 存在，跨平台发布链在当前仓库状态下不可复现。

## 7. 文档与代码不一致

| 文档/说法 | 代码事实 | 处理 |
|---|---|---|
| 旧进度文档把多个 CI 修复写成完成 | 原工作流曾只覆盖 `main`，扫描部分非阻断，benchmark 缺失时可成功 | 本轮已更新工作流；以 CI 实际运行记录为准 |
| 历史报告把 `evidence + low` 视为 exploited | 新 EvidenceStatus 已拆分疑似、确认、会话和权限；旧报告仍需迁移 | 报告迁移器与 Golden Trace列入 P0 |
| 固定靶场记录被当作泛化能力 | 生产代码已清理发现的固定 IP/路由探测分支；隐藏集仍缺 | 持续扫描 + 隐藏 benchmark |
| “完成”只按模块存在判断 | PRD要求代码、测试、指标和可复现证据同时满足 | 需求矩阵采用保守状态 |

## 8. 分阶段结论

| 阶段 | 当前结论 | 下一步出口条件 |
|---|---|---|
| P0 真值/安全 | 控制面骨架已建立，端到端接入部分完成 | 全路径 Action Envelope、统一 Judge、禁止动作/越界集 100% |
| P1 解耦/工程 | 新模块可独立测试，旧单体仍是主路径 | 双写事件、Golden Trace、路由拆分和覆盖率门槛 |
| P2 未知 Linux | 已有通用契约与工具治理，真实未知集尚未证明 | 三类未知 Linux fixture + 重复运行指标 |
| P3 现代 Web | 数据模型已起步 | 端点/认证/角色/规则/非 Shell Judge 最小闭环 |
| P4 可信自进化 | 生命周期与内容门禁已起步 | 沙箱、来源隔离、正负集、灰度回滚端到端 |
| P5 教学产品 | 报告与前端基础存在 | 时间线、选择原因、攻击/防守双视角和回放 |
| P6 泛化/发布 | CI 门禁已收紧，发布链仍不完整 | 隐藏集、三次重复、跨平台产物和签名/迁移 |

## 9. 审计建议的执行顺序

1. 把 `EventSourcedTaskStore`、canonical Evidence 和 Scope Decision 接入真实 Agent 主循环，旧 State 只做兼容投影。
2. 移除明文凭据回传，补全命令/网络/文件动作的统一 policy adapter。
3. 建立本地 Docker fixture：无漏洞、版本错配、会话假成功、现代 Web 认证和网络抖动各一类。
4. 为每个 fixture 建立真值、复现脚本、负样本和三次重复 Benchmark；结果进入 Release Gate。
5. 按领域拆分 `api.py`、`agent.py`、`executor.py`、`state.py` 和前端主入口，边拆边做 Golden Trace。
6. 补齐 Tauri/容器/依赖锁定/迁移/备份恢复发布链，并在干净环境执行一次完整发布演练。

