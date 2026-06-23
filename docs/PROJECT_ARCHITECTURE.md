# SDIT - Linux 应急响应与安全审计平台

## 项目概述

SDIT 是一款面向 Linux 系统管理员和安全工程师的桌面级应急响应工具,采用 Tauri + Vue + Python FastAPI 全栈架构,集成 AI Agent 智能分析能力,提供系统检测、安全审计、远程管理、自动修复等一站式解决方案。

**版本**: 0.55.0  
**技术栈**: Tauri + Vue 3 + TypeScript + Python FastAPI  
**开发时间**: 2026-04-21

---

## 架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Tauri Shell (Rust)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Window Mgmt  │  │ File Dialogs │  │ System Integration   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                     Frontend (Vue 3 + TS)                        │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐ │
│  │   Core     │  │     UI     │  │    AI      │  │   SSH/    │ │
│  │  App       │  │  Renderer  │  │  Agent     │  │   SFTP    │ │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘ │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐ │
│  │ Detection  │  │  Payloader │  │ Emergency  │  │ Settings  │ │
│  │ Manager    │  │  Tools     │  │    Modal   │  │ Manager   │ │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP/Invoke
┌─────────────────────────────────────────────────────────────────┐
│                  Python Backend (FastAPI)                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   Agent Orchestrator                      │   │
│  │  ┌─────────┐  ┌────────┐  ┌────────┐  ┌──────────────┐  │   │
│  │  │ Planner │→ │Executor│→ │  Tools  │→ │  Reporting   │  │   │
│  │  └─────────┘  └────────┘  └────────┘  └──────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ SSH Manager  │  │ File Analysis│  │ Detection Manager    │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │ SSH Protocol
┌─────────────────────────────────────────────────────────────────┐
│                     Remote Linux Servers                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心模块

### 1. 前端架构 (src/)

#### 1.1 核心应用层

**SDITApp** (`src/modules/core/app.ts`)
- 应用生命周期管理 (初始化、渲染、事件绑定)
- 全局状态管理 (StateManager)
- UI 模式切换 (经典模式 / AI 指挥台模式)
- 主题系统 (浅色/深色/樱花粉)
- SSH 连接/断开管理
- 全局事件监听和窗口控制

**StateManager** (`src/modules/core/stateManager.ts`)
- 维护应用状态 (当前页面、连接状态、主题、UI 模式)
- 提供状态变更通知机制
- 与 UI 渲染器双向绑定

#### 1.2 AI Agent 系统

**架构分层**:
```
AgentService (薄 Façade)
    ↓
AgentClient (Transport Layer)
    ↓
HTTP Invoke → Python Backend
```

**AgentService** (`src/modules/ai/agentService.ts`)
- 单例模式,对外提供统一接口
- 组合调用: client + settings + task factory + logger
- 核心方法:
  - `runAgentTask()` - 执行 Agent 任务
  - `runSecurityCheck()` - 安全检查
  - `runEmergencyResponse()` - 应急响应
  - `runLogAnalysis()` - 日志分析
  - `runAutoRemediation()` - 自动修复

**AgentClient** (`src/modules/ai/agentClient.ts`)
- 底层 transport 层,负责 HTTP/invoke 调用
- 与 Python 后端通过 Tauri invoke 通信
- 错误处理和降级逻辑

**SkillRegistry** (`src/modules/ai/skillRegistry.ts`)
- 前端 Skill 快捷入口管理
- 内置 6 种快捷 Skill:
  - 主机 Triage (快速排查)
  - 日志调查
  - 进程狩猎
  - 端口狩猎
  - SSH 审计
  - 修复建议
- 关键词匹配和自动选择

#### 1.3 SSH/SFTP 远程管理

**SSHManager** (`src/modules/ssh/sshManager.ts`)
- 协调器模式,委托给 ConnectionManager 和 SystemInfoManager
- 连接生命周期管理
- 命令执行代理
- 系统信息获取 (全量/轻量/按需加载)
- 自动更新机制 (30s 间隔)

**SSHConnectionManager** (`src/modules/ssh/connectionManager.ts`)
- SSH 连接 CRUD 操作
- 连接状态管理
- 密码加密存储
- 测试连接功能

**SftpManager** (`src/modules/remote/sftpManager.ts`)
- SFTP 文件列表管理
- 目录导航和文件操作
- 多模式排序 (名称/大小/时间)
- 目录优先显示
- 权限/大小/时间格式化
- 事件监听机制

#### 1.4 快速检测系统

**QuickDetectionManager** (`src/modules/detection/quickDetectionManager.ts`)
- 全面安全扫描 (多检测项并行/串行)
- 评分系统 (100 分制):
  - Critical: -40 分
  - High: -20 分
  - Medium: -10 分
  - Low: -5 分
- 检测类别:
  - 进程分析 (可疑进程、高资源占用)
  - 端口扫描 (开放端口、高危端口)
  - SSH 审计 (配置安全)
  - 文件系统 (权限、SUID/SGID)
  - 日志分析 (异常登录)
  - 用户审计 (弱密码、权限)
  - 防火墙检查
  - 系统资源 (CPU/内存/磁盘)
- 检测报告生成
- 历史记录管理

#### 1.5 Payload 工具集

**Payloader** (`src/modules/payloader/`)
- 内网穿透载荷库
- Web 攻击载荷库
- 编码工具 (Base64/Hex/URL/ROT13)
- 反弹 Shell 生成器
- 命令模板库
- Vue 组件化架构

#### 1.6 应急响应系统

**EmergencyModal** (`src/modules/ui/emergencyModal.ts`)
- 快速应急命令集
- 场景化命令推荐:
  - 挖矿病毒应急
  - Webshell 排查
  - 横向移动检测
  - 数据泄露排查
- 命令分类和执行

#### 1.7 UI 渲染系统

**ModernUIRenderer** (`src/modules/ui/modernUIRenderer.ts`)
- 侧边栏导航
- 主工作区渲染
- 多页面管理:
  - AI 指挥台
  - 系统信息
  - SFTP 面板
  - 快速检测
  - Payload 工具
  - 命令执行
  - 日志分析
- 响应式布局
- 主题适配

### 2. Python 后端 (src-python/)

#### 2.1 应用入口

**FastAPI 主应用** (`src-python/app/main.py`)
- RESTful API 路由
- WebSocket 支持:
  - `/ws/terminal/{terminal_id}` - 实时终端
  - `/ws/events` - 事件推送
- CORS 配置
- 生命周期管理 (启动/关闭清理)
- 健康检查端点

**API 路由** (`src-python/app/routers/api.py`)
- SSH 连接管理
- SFTP 文件操作
- 系统信息获取
- Agent 任务执行
- 命令执行
- 检测和日志分析

#### 2.2 Agent 核心系统

**AgentOrchestrator** (`src-python/app/services/agent/orchestrator.py`)

Agent 系统的大脑,负责全流程编排:

```python
用户请求
  ↓
1. 技能解析 (_resolve_skills)
  - 用户指定 > 关键词匹配 > 模糊搜索 > 兜底
  - 支持 Ephemeral Skill 自动生成
  ↓
2. 上下文构建 (_build_context)
  - 注入 SSH Manager 等依赖
  ↓
3. 现场研究 (ResearchRouter)
  - external_web: 联网检索
  - host_runtime: 本地运行时研究
  - target_runtime: 靶机研究
  - target_via_ssh: SSH 跳板研究
  ↓
4. 策略校验 (PolicyGuard)
  - 安全策略评估
  - 风险等级判定
  ↓
5. 规划 (_obtain_plan)
  - LLM Planner (主路径)
  - Rule-based Planner (备选)
  - PlanBuilder 物化执行计划
  ↓
6. 执行 (Executor)
  - 按步骤执行
  - 失败重规划 (max_replan_attempts)
  - 依赖感知
  ↓
7. 报告 (ReportBuilder)
  - 发现归一化
  - 证据对齐
  - 修复建议生成
  - 最终报告组装
```

**关键特性**:
- **Execution Mode 策略模式**: 
  - `HostRuntimeStrategy` - 本地运行
  - `TargetRuntimeStrategy` - 靶机模式
  - `TargetViaSSHStrategy` - SSH 跳板
  - `ExternalWebStrategy` - 外部 Web
- **Ephemeral Skill 自动生成**: 通过 SkillGapAnalyzer + SkillGenerationService 动态生成临时 Skill
- **LLM 集成**: 支持 OpenAI/DeepSeek/Claude 等多模型
- **安全策略**: PolicyGuard 提供执行前风险评估

**Planner 系统** (`src-python/app/services/agent/planner.py`)
- **RuleBasedPlanner**: 基于关键词匹配的规则规划器
- **LLMPlanner**: 基于 LLM 的智能规划器
  - 支持 Fallback 机制
  - 可观测性追踪 (token 使用、延迟、模型信息)

**Executor 系统** (`src-python/app/services/agent/executor.py`)
- 执行计划逐步执行
- 失败自动重规划
- 依赖感知执行
- 超时和重试机制
- 执行结果收集

#### 2.3 Skill 系统

**Skill 架构**:
```
BaseSkill (抽象基类)
  ├── name/description/category (元信息)
  ├── parameters (参数 Schema)
  ├── build_steps(args, context) (动态构建步骤)
  └── get_definition() (导出元数据)

SkillRegistry (注册中心)
  ├── register(skill)
  ├── get(name)
  ├── list_skills()
  ├── match_skills(query)
  └── iter_skills()
```

**内置 Skills** (`src-python/app/services/agent/skills/builtin_skills.py`):
- `HostTriageSkill` - 主机快速分诊
- `LogInvestigationSkill` - 日志深入调查
- `ProcessHuntSkill` - 进程狩猎
- `PortHuntSkill` - 端口狩猎
- `SSHAuditSkill` - SSH 配置审计
- `FixAdvisorSkill` - 修复建议顾问

**专项 Skills**:
- `AutoRemediationSkill` - 自动修复
- `RemediationVerificationSkill` - 修复验证
- `CapabilityCheckSkill` - 能力检查
- `SafeConfigPatchSkill` - 安全配置补丁
- `HardeningBaselineSkill` - 加固基线
- `IncidentTimelineSkill` - 事件时间线
- `WebTargetProbeSkill` - Web 目标探测
- `WebPayloadAttemptSkill` - Web Payload 尝试
- `WebTargetViaSSHProbeSkill` - SSH 跳板 Web 探测
- `WebPayloadViaSSHAttemptSkill` - SSH 跳板 Payload 尝试

**Declarative Skill 平台** (`src-python/app/services/agent/skills/specs.py`):
- JSON 格式 Skill 规范定义
- SkillSpecLoader 加载器
- 支持 builtin/experimental/generated 三种来源
- 版本控制和状态管理

#### 2.4 Tool 系统

**工具注册表** (`src-python/app/services/agent/tool_registry.py`)
- 工具注册和发现
- 工具元数据管理
- 按名称/类别检索

**工具分类**:

| 类别 | 工具文件 | 核心功能 |
|-----|---------|---------|
| 检测工具 | `detection_tools.py` | 端口扫描、防火墙、用户审计、进程分析、文件权限、日志分析、SSH 审计 |
| 修复工具 | `remediation_tools.py` | 防火墙修复、SSH 加固、PAM 配置、用户管理、权限修复、服务管理 |
| 系统工具 | `system_tools.py` | 系统信息、发行版检测、服务列表、定时任务、网络连接、包管理器 |
| 文件工具 | `file_tools.py` | 文件读取、权限修改、备份恢复、关键文件检查 |
| 日志工具 | `log_tools.py` | 日志采集、分析、认证日志、系统日志 |
| 命令工具 | `command_tools.py` | 命令执行、输出解析 |
| Web 研究工具 | `web_research_tools.py` | 搜索引擎、URL 抓取 |
| 目标 HTTP 工具 | `target_http_tool.py` | HTTP 请求、指纹识别 |

#### 2.5 Execution Modes (执行模式)

**策略模式实现** (`src-python/app/services/agent/execution_modes/`):

```
ExecutionModeStrategy (抽象基类)
  ├── mode_name: 模式名称
  ├── prepare_context(): 准备上下文
  ├── run_research(): 执行研究
  ├── post_research_context_update(): 研究后更新
  ├── filter_skills(): 过滤 Skills
  ├── maybe_classify_target(): 目标分类
  ├── adjust_planner_budget(): 调整规划器预算
  ├── validate_plan(): 验证计划
  └── validate_tools_in_plan(): 验证工具
```

**四种执行模式**:

1. **HostRuntimeStrategy** (`host_runtime.py`)
   - 在本地主机执行检测和修复
   - 适用于直接 SSH 连接的场景

2. **TargetRuntimeStrategy** (`target_runtime.py`)
   - 针对远程靶机执行安全验证
   - 支持目标分类和自适应 Skill 生成

3. **TargetViaSSHStrategy** (`target_via_ssh.py`)
   - 通过 SSH 跳板机访问远程目标
   - 适用于内网靶机测试

4. **ExternalWebStrategy** (`external_web.py`)
   - 对外部 Web 目标进行研究
   - 联网信息收集

**ResearchRouter** (`src-python/app/services/agent/research/research_router.py`):
- 统一研究路由
- 模式检测
- 结果标准化

#### 2.6 Reporting 系统

**报告构建器** (`src-python/app/services/agent/reporting/`):

```
ReportBuilder (总装线)
  ├── FindingNormalizer (发现归一化)
  ├── EvidenceGrounding (证据对齐)
  ├── SummaryBuilder (摘要构建)
  ├── TracesBuilder (执行轨迹)
  ├── RemediationReportBuilder (修复报告)
  └── FinalStatusResolver (最终状态判定)
```

**NormalizedSecurityFinding** (标准化安全发现):
- `finding_id` - 唯一标识
- `module` - 所属模块 (ssh/firewall/account/filesystem/log/network)
- `title` - 问题标题
- `severity` - 严重等级 (critical/high/medium/low)
- `reason` - 原因说明
- `impact` - 影响分析
- `evidence` - 证据列表
- `recommended_actions` - 建议操作
- `fix_commands` - 修复命令
- `verify_commands` - 验证命令
- `rollback_commands` - 回滚命令

**FindingFilter** (`src-python/app/services/agent/finding_filter.py`):
- 过滤内部流程项 (检测工具名、系统信息)
- 标题质量检查 (避免函数名作为标题)
- 泛化原因过滤
- 安全类别白名单
- 去重聚合

#### 2.7 SSH 服务层

**SSHManager** (`src-python/app/services/ssh_manager.py`)
- SSH 连接管理
- 命令执行 (异步)
- SFTP 文件操作
- 终端会话管理
- WebSocket 集成

**SSHConnectionManager** (`src-python/app/services/ssh_connection_manager.py`)
- 连接配置管理
- 密码加密/解密
- 连接持久化

---

## 数据流

### 1. Agent 任务执行流

```
用户输入 (前端)
  ↓
AgentService.runAgentTask(request)
  ↓
Tauri Invoke → Python FastAPI
  ↓
AgentOrchestrator.run(request)
  ├── _resolve_skills() → [Skill]
  ├── _build_context() → {context}
  ├── ResearchRouter.run() → {research_info}
  ├── PolicyGuard.evaluate() → {policy_summary}
  ├── Planner.plan_calls() → PlannerOutput
  ├── PlanBuilder.build() → Plan
  ├── Executor.execute_plan() → ExecutionResult
  └── ReportBuilder.build() → FinalReport
  ↓
返回 JSON → 前端渲染
```

### 2. SSH 连接流

```
前端点击连接按钮
  ↓
app.handleSSHConnect()
  ↓
sshManager.connect(connectionId)
  ↓
SSHConnectionManager.connect(id)
  ↓
Python Backend: SSHManager.connect(host, port, user, password)
  ↓
paramiko.SSHClient 建立连接
  ↓
获取系统摘要 (轻量模式)
  ↓
启动自动更新 (30s)
  ↓
前端更新状态和 UI
```

### 3. 检测流程

```
用户启动检测
  ↓
QuickDetectionManager.startFullScan()
  ↓
逐项执行检测:
  ├── 进程分析 → invoke('detect_process_analysis')
  ├── 端口扫描 → invoke('detect_port_scan')
  ├── SSH 审计 → invoke('detect_ssh_audit')
  ├── 文件权限 → invoke('detect_file_permission')
  ├── 日志分析 → invoke('detect_log_analysis')
  ├── 用户审计 → invoke('detect_user_audit')
  └── 防火墙检查 → invoke('detect_firewall')
  ↓
汇总评分和发现
  ↓
生成检测报告
  ↓
前端展示结果
```

---

## 关键技术特性

### 1. AI Agent 能力

- **智能规划**: LLM 驱动的任务分解和调度
- **动态技能生成**: 根据需求自动生成临时 Skill
- **自适应执行**: 根据目标类型自动选择执行模式
- **证据对齐**: 所有发现必须附带可验证证据
- **LLM 二次解读**: 将模板化报告转为人类可读解释

### 2. 安全保障

- **策略守卫**: 执行前风险评估和操作限制
- **权限检查**: sudo 能力验证
- **回滚支持**: 所有修复操作提供回滚命令
- **审批机制**: 高危操作需人工确认

### 3. 可扩展性

- **插件化 Skill**: JSON 规范定义,支持热加载
- **工具注册表**: 统一工具管理接口
- **执行模式策略**: 新增模式只需实现 Strategy 接口
- **Declarative Skills**: 无需编写代码,JSON 定义即可

### 4. 远程管理

- **SSH 连接池**: 支持多连接管理
- **SFTP 文件操作**: 完整文件管理功能
- **实时终端**: WebSocket 实现交互式终端
- **跳板机支持**: SSH 跳板访问内网目标

### 5. UI/UX

- **双模式切换**: 经典模式 / AI 指挥台模式
- **多主题支持**: 浅色/深色/樱花粉
- **响应式布局**: 自适应窗口大小
- **状态管理**: 全局状态同步和通知

---

## 数据库/存储

### 1. 本地存储

- **Tauri Store**: 连接配置、主题设置等持久化
- **文件系统**: Skills 规范 (JSON 格式)
  - `skills/builtin/` - 内置技能
  - `skills/experimental/` - 实验技能
  - `skills/generated/` - AI 生成技能

### 2. 内存状态

- **StateManager**: 前端应用状态
- **SkillRegistry**: Skill 注册表
- **ToolRegistry**: 工具注册表
- **SSHConnectionManager**: 活跃连接管理

---

## API 端点

### REST API

| 端点 | 方法 | 功能 |
|-----|------|------|
| `/health` | GET | 健康检查 |
| `/api/v1/ssh/connect` | POST | SSH 连接 |
| `/api/v1/ssh/disconnect` | POST | SSH 断开 |
| `/api/v1/ssh/execute` | POST | 执行命令 |
| `/api/v1/sftp/list-files` | POST | 文件列表 |
| `/api/v1/sftp/read-file` | POST | 读取文件 |
| `/api/v1/sftp/write-file` | POST | 写入文件 |
| `/api/v1/agent/run` | POST | Agent 任务 |
| `/api/v1/detection/run` | POST | 执行检测 |
| `/api/v1/log/analyze` | POST | 日志分析 |

### WebSocket

| 端点 | 功能 |
|-----|------|
| `/ws/terminal/{terminal_id}` | 实时终端 I/O |
| `/ws/events` | 服务端事件推送 |

### Tauri Invoke Commands

| 命令 | 功能 |
|-----|------|
| `agent_run` | 执行 Agent 任务 |
| `agent_context` | 获取 Agent 上下文 |
| `agent_tools` | 获取工具列表 |
| `agent_skills` | 获取技能列表 |
| `ssh_execute_command` | SSH 执行命令 |
| `sftp_list_files` | SFTP 文件列表 |
| `detect_process_analysis` | 进程分析 |
| `detect_port_scan` | 端口扫描 |
| `detect_ssh_audit` | SSH 审计 |

---

## 开发指南

### 项目结构

```
new-lovely/
├── src/                          # 前端代码
│   ├── modules/
│   │   ├── core/                 # 核心应用
│   │   ├── ai/                   # AI Agent 系统
│   │   ├── ssh/                  # SSH 管理
│   │   ├── remote/               # 远程管理 (SFTP)
│   │   ├── detection/            # 快速检测
│   │   ├── payloader/            # Payload 工具
│   │   ├── emergency/            # 应急响应
│   │   ├── ui/                   # UI 渲染
│   │   └── settings/             # 设置管理
│   └── css/                      # 样式文件
├── src-python/                   # Python 后端
│   ├── app/
│   │   ├── routers/              # API 路由
│   │   ├── services/
│   │   │   ├── agent/            # Agent 核心
│   │   │   │   ├── skills/       # 技能系统
│   │   │   │   ├── tools/        # 工具系统
│   │   │   │   ├── execution_modes/  # 执行模式
│   │   │   │   ├── reporting/    # 报告系统
│   │   │   │   └── planning/     # 规划系统
│   │   │   └── *.py              # 其他服务
│   │   ├── models/               # 数据模型
│   │   └── utils/                # 工具函数
│   └── tests/                    # 测试代码
├── skills/                       # Skill 规范目录
│   ├── builtin/                  # 内置技能
│   ├── experimental/             # 实验技能
│   └── generated/                # 生成技能
└── docs/                         # 文档
```

### 添加新 Skill

**方式 1: SKILL.md 知识模式 (AI调度)**

```markdown
---
name: my_new_skill
description: 我的新技能描述
domain: custom
tags: [investigation]
---
# My New Skill
## When to Use
- 当需要检查系统状态时
## Workflow
### Step 1: 检查系统状态
执行 `uname -a` 获取系统信息
```

保存到 `skills/<category>/my-new-skill/SKILL.md`

**方式 2: skill.json 流水线模式 (规则引擎)**

```json
{
  "schema_version": "skill-spec/v1",
  "name": "my_new_skill",
  "description": "我的新技能描述",
  "category": "investigation",
  "version": "1.0.0",
  "status": "active",
  "steps": [
    {
      "id": "step1",
      "name": "检查系统状态",
      "tool_name": "execute_command",
      "parameters": {"command": "uname -a"},
      "depends_on": []
    }
  ]
}
```

保存到 `skills/<category>/my-new-skill/skill.json`

**方式 3: hybrid 混合模式**

同目录放 `skill.json` + `SKILL.md`，json 中加 `"knowledge_file": "SKILL.md"`

### 添加新 Tool

```python
from app.services.agent.tool_registry import BaseTool, ToolResult, ToolStatus

class MyNewTool(BaseTool):
    @property
    def name(self) -> str:
        return "my_new_tool"
    
    @property
    def description(self) -> str:
        return "我的新工具描述"
    
    @property
    def parameters(self) -> list:
        return []
    
    async def execute(self, params: dict, context: dict) -> ToolResult:
        # 实现工具逻辑
        return ToolResult(
            status=ToolStatus.SUCCESS,
            output={"result": "success"},
        )

# 注册到注册表
registry.register(MyNewTool())
```

### 添加新 Execution Mode

```python
from app.services.agent.execution_modes.base import ExecutionModeStrategy

class MyNewStrategy(ExecutionModeStrategy):
    @property
    def mode_name(self) -> str:
        return "my_new_mode"
    
    async def run_research(self, request, context, orchestrator):
        # 实现研究逻辑
        return {"research_mode": self.mode_name}
    
    def filter_skills(self, skills, orchestrator, context):
        # 实现技能过滤
        return skills

# 在 factory.py 中注册
MODE_STRATEGIES["my_new_mode"] = MyNewStrategy
```

---

## 测试

### 运行测试

```bash
cd src-python
pytest tests/
```

### 测试覆盖

- **单元测试**: Skill/Tool/Planner 核心逻辑
- **集成测试**: Orchestrator 全流程
- **API 契约测试**: 前后端接口一致性
- **执行安全测试**: PolicyGuard 验证

---

## 部署

### 开发环境

```bash
# 1. 安装前端依赖
npm install

# 2. 安装 Python 依赖
cd src-python
pip install -r requirements.txt

# 3. 启动 Python 后端
python run.py

# 4. 启动 Tauri 开发模式
cd ..
npm run tauri dev
```

### 生产构建

```bash
# 构建 Tauri 应用
npm run tauri build
```

---

## 最佳实践

### 1. Skill 设计

- 每个 Skill 只负责单一职责
- 使用 `build_steps()` 动态生成步骤
- 提供清晰的参数 Schema
- 遵循命名规范 (snake_case)

### 2. Tool 设计

- 工具应该是无状态的
- 提供详细的错误信息
- 支持超时和重试
- 记录执行日志

### 3. 安全考虑

- 所有高危操作必须经过 PolicyGuard
- 修复命令必须提供回滚方案
- 敏感信息不得硬编码
- 使用加密存储密码

### 4. 性能优化

- 使用轻量模式获取系统信息
- 按需加载详细数据
- 避免重复执行相同检测
- 合理使用缓存

---

## 常见问题

### Q1: Agent 任务执行失败?

检查:
1. SSH 连接是否正常
2. Python 后端是否运行
3. 日志中的错误信息
4. PolicyGuard 是否拦截

### Q2: 如何调试 Agent?

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 使用 create_with_llm() 创建 Orchestrator
orchestrator = create_with_llm(
    provider="openai",
    model_name="gpt-4",
    api_key="sk-...",
)
```

### Q3: 如何添加自定义检测项?

1. 在 `quickDetectionManager.ts` 中添加检测配置
2. 在后端实现对应的检测工具
3. 注册到工具注册表
4. 前端调用即可

---

## 更新日志

### v0.55.0 (2026-04-21)

**新增功能**:
- AI Agent 智能分析系统
- 自适应执行模式
- Ephemeral Skill 自动生成
- LLM 二次解读报告
- 证据对齐机制
- 策略守卫系统
- 修复验证流程

**架构优化**:
- 策略模式重构 Execution Modes
- Reporting 系统模块化
- 前后端分层架构
- Skill 规范化平台

**UI/UX**:
- AI 指挥台模式
- 多主题支持
- 响应式布局
- 状态管理优化

---

## 许可证

本项目采用 MIT 许可证。

---

## 联系方式

- **项目地址**: https://github.com/your-org/lovely-res
- **问题反馈**: GitHub Issues
- **文档**: /docs/

---

*本文档由 AI 自动生成,基于代码库深度分析。最后更新: 2026-04-21*
