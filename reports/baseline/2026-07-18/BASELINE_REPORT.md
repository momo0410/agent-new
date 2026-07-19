# SDIT Pentest Agent 基线报告

日期：2026-07-18  
仓库：`D:\agent-new`  
分支：`master`  
原始审计提交：`f9a6d0b0427dc39d206a8189fa7dba2f2fb06ee4`  
本地环境：Python 3.14.2、Node v24.15.0、npm 11.11.0

## 1. 记录原则

本报告同时保存“审计开始时基线”和“本轮修正后复测”。两者不混写；后者用于确认改动没有让现有回归退化。所有失败、跳过、警告和工具缺失均保留。

## 2. 审计开始时基线

| 项目 | 实际结果 |
|---|---|
| Kali 后端全量测试 | 344 passed, 6 skipped, 1 warning, 27.08s |
| 前端单测 | 9 passed，2 files |
| 前端覆盖率 | Statements 71.51%，Branches 58.62%，Functions 70.96%，Lines 75.88% |
| 前端构建 | 通过；主 chunk 约 3.19 MB；存在动态/静态导入告警 |
| npm audit | 0 vulnerabilities |
| 全仓 Ruff | 803 errors |
| 全仓 mypy | 363 errors，92 notes |
| Bandit 全仓 | 155 findings：High 0、Medium 13、Low 142；4 个跳过测试 |
| Benchmark/CI | 原工作流存在分支覆盖不全、非阻断扫描和缺失结果可成功等问题 |
| 仓库卫生 | `src-python` 含多项已跟踪运行日志、扫描输出和恢复文件 |

## 3. 本轮修正后的复测

### 3.1 后端

执行：

```text
python -m pytest tests -q --tb=short --cov=app --cov-report=term-missing --cov-report=xml:coverage.xml
```

结果：**366 passed, 1 skipped, 313 warnings，约 99.08s；总覆盖率 56%**。

警告主要来自 Python 3.14 对 FastAPI/Starlette 使用 `asyncio.iscoroutinefunction` 的弃用提示，以及 HTTPX `app` shortcut 弃用提示。它们未被吞掉，后续需随依赖升级处理。

新增控制面测试：**17 passed**，覆盖 Scope Token/DNS/预算/紧急停止、严格会话、Judge、事件幂等与恢复、资产冲突、Planner 停滞、进程监督、Web 模型、Skill 门禁、模型脱敏、报告完整性、失败恢复、benchmark gate 和本地会话票据。

### 3.2 前端

执行：

```text
npm run test:coverage
npm run build
```

结果：

- 单测：**9 passed，2 files**。
- 覆盖率：Statements **63.10%**，Branches **34.66%**，Functions **62.85%**，Lines **66.45%**。
- 类型检查和 Vite 构建通过。
- vendor 分块后主入口约 **2.73 MB**；仍有导入边界告警和大 chunk 告警。

### 3.3 静态质量与安全

| 检查 | 结果 |
|---|---|
| Ruff（`app/core` + 两个关键服务） | 通过 |
| mypy（`app/core --ignore-missing-imports`） | 0 error；保留若干 untyped body note |
| Bandit `-r app -lll` | High 0；该门禁通过 |
| npm audit `--audit-level=high` | 0 high/critical vulnerabilities |
| Scope benchmark | 当前均值约 0.028 ms；CI 阈值 5 ms |

## 4. 基线中的已知限制

1. 本机没有真实 Kali/目标 Docker 环境，因此本报告没有把网络利用结果当作产品验收证据。
2. 后端覆盖率包含大量旧 API 和 SSH 分支，56% 不等同于未知目标成功率。
3. 前端只有两个测试文件，任务 Store 的新增事件分支仍需扩大覆盖。
4. Benchmark 目前主要验证策略性能和门禁逻辑，隐藏目标真值集尚未接入。
5. Release workflow 当前还未在仓库内形成可直接复现的跨平台 Tauri 产物。

## 5. 发布判定

本轮代码质量门禁和现有回归通过；产品发布门禁仍保持 **未关闭**，原因是隐藏基准、现代 Web 闭环、明文凭据迁移、全路径策略接入和跨平台发布证据尚未齐备。下一轮必须以这些缺口为验收对象，而不是只增加工具数量。
