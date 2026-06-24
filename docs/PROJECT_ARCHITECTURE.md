# SDIT 架构文档

**版本**: 0.55.0 | **技术栈**: Tauri + Vue 3 + TypeScript + Python FastAPI | **最后更新**: 2026-06-25

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      Tauri Shell (Rust)                         │
│         Window Mgmt / File Dialogs / System Integration         │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                  Frontend (Vue 3 + TypeScript)                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐ │
│  │ Core App   │  │  UI Render │  │  AI Agent  │  │ SSH/SFTP  │ │
│  │ State Mgr  │  │  Theme Sys │  │  Service   │  │ Manager   │ │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘ │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐ │
│  │ Detection  │  │ Payloader  │  │ Emergency  │  │ Settings  │ │
│  │ Manager    │  │ Tools      │  │ Commands   │  │ Manager   │ │
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP / Tauri Invoke
┌─────────────────────────────────────────────────────────────────┐
│                  Python Backend (FastAPI)                        │
│                                                                  │
│  ┌──────────── pentest_agent（渗透测试核心）──────────────────┐  │
│  │ agent.py (主循环) → planner.py (候选生成)                  │  │
│  │   → executor.py (执行引擎) → state.py (状态管理)           │  │
│  │   → capabilities.py → critic.py → reflection.py            │  │
│  │   → exploit_retry.py → python_exploit.py                   │  │
│  │   → interactive_session.py → protocol_adapters/            │  │
│  │   → llm_client.py → tool_registry.py → reporting.py        │  │
│  │   → kali_executor.py                                       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────── skill_engine（技能引擎）──────────────────────┐  │
│  │ skill_md_parser.py → skill_loader.py → skill_matcher.py    │  │
│  │   → skill_index.py (TF-IDF) → skill_embedding_index.py     │  │
│  │   → encoder.py (bge-small-zh-v1.5)                         │  │
│  │   → skill_generator.py → failure_skill_generator.py        │  │
│  │   → quality_gate.py → lifecycle_manager.py                 │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────── online_search ────┐  ┌── experience_store ──┐       │
│  │ registry.py (调度中心)     │  │ store.py (语义检索)   │       │
│  │ cache.py (3级缓存)        │  └──────────────────────┘       │
│  │ nvd_client.py (NVD API)   │                                  │
│  │ msf_module_client.py      │  ┌── 其他服务 ─────────┐       │
│  │ default_creds_client.py   │  │ SSH / SFTP / 检测    │       │
│  └────────────────────────────┘  │ 日志分析 / 文件分析  │       │
│                                   └──────────────────────┘       │
└─────────────────────────────────────────────────────────────────┘
                              │ SSH Protocol
┌─────────────────────────────────────────────────────────────────┐
│              Kali Attack Box / Remote Linux Target               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、pentest_agent 模块 — 渗透测试核心

pentest_agent 是整个系统的大脑，由 14 个文件组成，实现从端口扫描到报告生成的全自动渗透流程。

### 2.1 八阶段流水线

```
init → recon → web → exploit → post → lateral → reflection → done
```

阶段切换由 `_auto_phase_switch()` 根据 State 中的证据自动驱动:

- init → recon: 发现开放端口
- recon → web: 确认 HTTP 服务
- web → exploit: Web 指纹完成
- exploit → post: 获得 shell 或高价值证据
- post → lateral: 发现横向移动路径
- 任意 → reflection: 任务结束（done 门控通过）

**done 门控** (`_should_block_done`): 存在未验证的高价值攻击面（exploit_surface_score ≥ 60）时阻止退出。

### 2.2 agent.py — 主循环 (~2200行)

**执行流**:
```
run(target, ...)
  ├── 初始化 State, Executor, SkillLoader/Matcher, OnlineSearchService
  ├── 初始化 ExploitRetryStrategy, ActionCritic
  ├── 主循环 (while not done):
  │     ├── State.llm_context()  ← 构建 token 预算内的上下文
  │     ├── _call_llm_with_function_call()  ← LLM 规划
  │     ├── 4级解析回退: function_call → XML → legacy → deterministic
  │     ├── _normalize_plan_tasks()  ← 验证/去重/能力推断
  │     ├── _enrich_task_identity()  ← 注入 surface_key/strategy_key
  │     ├── _enforce_minimal_task_policy()  ← 过滤重复/停滞恢复
  │     ├── _auto_inject_service_intel()  ← 在线搜索自动注入
  │     ├── _execute_planned_tasks()  ← 并行/串行执行
  │     ├── _auto_phase_switch()  ← 阶段切换
  │     └── State.save()
  └── reflection.run_reflection()  ← 后渗透反思 + skill 生成
```

**关键常量**:
- `MAX_PARALLEL_TASKS = 5` — 每轮最大并行任务
- `MAX_PARALLEL_SURFACES = 3` — 最大并发攻击面
- `MIN_SURFACE_SCORE = 50` — 攻击面最低分阈值
- `MAX_CONSECUTIVE_LLM_FAILURES = 3` — LLM 连续失败触发 critic
- `STAGNATION_WINDOW = 3` — 停滞检测窗口

**停滞检测** (`_detect_stagnation`): 连续 3 轮只执行 research/recon 类低价值动作时，生成针对未验证高价值攻击面的恢复任务。

**攻击面预算冷却** (`_is_surface_budget_or_cooldown_blocked`): 基于 zero-evidence 轮次和信息增益耗尽判断，防止对同一攻击面无意义重试。

### 2.3 planner.py — 规则候选任务生成 (~2258行)

为 LLM 提供候选任务列表，LLM 从中选择或自由规划。

**SERVICE_EXPLOIT_TEMPLATES** (19个模板):
每个模板包含: match(lambda匹配函数), tool, args模板, purpose, score, capabilities, action_type, skill_ref。
覆盖: vsftpd, proftpd, samba, IRC, distcc, Java RMI, PostgreSQL, MySQL, SSH, Telnet, VNC, NFS, DRb, rlogin/rsh, bindshell, PHP-CGI, Tomcat, Apache/HTTP。

**FAMILY_CONFIG** (7个服务家族):
web-validate, web-profile, remote-access, rpc-share, middleware-db, interactive, unknown-service — 每个家族配置默认工具/参数/分数/分块大小。

**`_exploit_surface_score(port, service)`**: 基于端口 + 服务 token 计算攻击面复杂度评分（0-100+），驱动候选排序和 done 门控。

**`build_candidate_tasks(snapshot, limit=16)`**: 主入口。按阶段分发生成器 → 治理评分/惩罚 → 去重 → 排序。

### 2.4 state.py — 渗透状态管理 (~2100行)

JSON 文件持久化的中心状态，线程安全（RLock），token 预算化的 LLM 上下文渲染。

**TokenBudget**:
- 总预算: 12000 token
- 分配: system:1500, findings:2000, attack_surfaces:1500, actions:2000, milestones:500, service_intel:500, candidates:1500, skills:1500, experience:800
- 使用 ~4 chars/token 启发式估算

**核心数据维度**:
- `targets` — 目标信息
- `findings` — 安全发现（自动归一化 + 合并）
- `vulnerabilities` — 漏洞记录
- `credentials` —  harvested 凭据
- `artifacts` — config_paths / key_material / service_artifacts
- `sessions` — 交互式会话
- `actions_taken` — 已执行动作历史
- `attack_surfaces` — 攻击面生命周期跟踪（upsert + 状态合并 + 策略去重）
- `round_plans` — 每轮计划
- `milestones` — 跨轮次关键事件
- `service_intel` — 在线搜索注入的情报
- `doctor_tools` — 工具健康缓存

**攻击面生命周期**: upsert_attack_surface 实现状态合并逻辑（_merge_surface_status 有 rank 排序），`planner_snapshot` 属性为 planner 提供只读视图。

**`llm_context()`**: 构建完整的 LLM 上下文，每个区块受 TokenBudget 配额约束。包含: 阶段、目标、经验、不可用工具、妥协状态、发现、攻击面、后续服务、候选任务、动作历史、阶段指导、里程碑、在线情报。

### 2.5 executor.py — 统一执行引擎 (~2452行)

所有工具执行通过 Executor.run() 分发:

```
run(tool_name, args)
  ├── 在线搜索路由 → OnlineSearchService.call()
  ├── 协议适配路由 → RedisAdapter/JMXAdapter/MongoAdapter.dispatch()
  ├── python_exploit 路由 → run_python_exploit()
  ├── 工具选择: _select_tool_with_fallback()
  │     ├── 主工具
  │     └── 回退链: rustscan→nmap, ffuf↔dirb, ...
  ├── 调用适配: _adapt_invocation()
  │     ├── searchsploit 参数重写
  │     ├── nmap 脚本白名单
  │     ├── nuclei 模板路径
  │     ├── hydra 字典安全 + 运行时限制
  │     ├── msfconsole payload/LPORT/exit
  │     ├── shell DB 探测保护
  │     └── timeout 上限（hydra:1200, msf:900, sqlmap:600...）
  └── 进程执行: _run_process()
        ├── PTY / pipe / streaming 模式选择
        └── Windows threading 回退
```

**交互式会话**: `_run_shell_tool()` 管理 nc/telnet 连接。支持 connect/disconnect/local/oneshot/active-session 五种模式。InteractiveSession 使用 `__LOVELY_DONE__` token 标记命令完成。

**输出解析器**: 15+ 个专用解析器（parse_port_services, parse_rustscan, parse_hydra, parse_msf 等），将原始工具输出转化为结构化数据写回 State。

### 2.6 capabilities.py — 语义能力标签 (~420行)

从工具名/参数/目的/skill 档案推断动作的语义能力:

- `_SKILL_STEP_RULES`: 17条规则映射 skill 步骤文本到能力标签
- `_infer_capabilities_from_args()`: 参数规则推断（如 `--script vuln` → `vuln_scan`）
- `infer_task_capabilities()`: 合并显式 + skill档案 + 参数规则三路推断
- `infer_action_type()`: 归一化为 research/exploit/verify/recon/post

### 2.7 critic.py — LLM 失败诊断 (~246行)

**ActionCritic**: 连续 3 次失败后触发，独立 LLM 调用诊断失败原因。
- 7种失败分类: payload_mismatch, network, target_patched, auth_required, wrong_protocol, timeout, other
- 输出 CritiqueResult: failure_category + diagnosis + next_step_suggestion
- 诊断结果注入后续 LLM 上下文

### 2.8 reflection.py — 后渗透反思 (~702行)

渗透结束后自动执行:

```
run_reflection()
  ├── StructuredEvaluator.evaluate()
  │     ├── 提取成功路径 (AttackPath)
  │     ├── 提取失败路径 (FailedPath)
  │     └── 提取未探索攻击面 (UnexploredSurface)
  │     → 判定 outcome: compromised/vulnerabilities-found/partial-success/failed-with-signals/no-progress
  ├── LLMReflector.reflect()
  │     └── JSON 输出: root_cause_analysis + generalizable_patterns + recommendations
  ├── _trigger_skill_pipeline()
  │     ├── SkillGenerator.generate_from_state()
  │     ├── FailureSkillGenerator.generate_from_state()
  │     ├── SkillQualityGate.filter()
  │     ├── LifecycleManager.register_draft() + auto_maintenance()
  │     └── SkillLoader 重载
  └── ExperienceStore.add()
```

### 2.9 exploit_retry.py — MSF payload 轮换 (~348行)

**ExploitRetryStrategy**: 检测 "no session" 信号后自动轮换 payload。

- `PAYLOAD_TIERS`: 8 个 MSF 模块的分层 payload 列表
- `FALLBACK_UNIX/WINDOWS`: 通用回退 payload 链
- `resolve_lhost()`: 自动检测本地出口 IP
- 按 (module, surface_key) 跟踪重试次数，max_retries=4

### 2.10 python_exploit.py — PoC 子进程执行 (~272行)

在隔离子进程中执行 LLM 编写的 Python exploit 代码:

- `_RUNNER_TEMPLATE`: 注入 exploit_lib 到 sys.path 后 exec 用户代码
- `RESULT_MARKER = "__EXPLOIT_RESULT__"`: stdout 协议标记
- 跨平台进程组 kill（Linux SIGKILL / Windows taskkill）
- 超时: 默认60s，最大600s，输出限制 200KB

### 2.11 interactive_session.py — 持久 shell 会话 (~297行)

**InteractiveSession**: 管理 nc/telnet 等持久连接。

- PTY 支持
- `__LOVELY_DONE__` token 标记命令完成
- 成功模式检测 + 优雅期（success_patterns + success_grace_period）
- 非阻塞 I/O + 输出静止检测

### 2.12 protocol_adapters/ — 原生协议适配器

绕过 shell 工具，直接用 Python 实现协议交互:

**BaseProtocolAdapter**: 抽象基类，提供 TCP 可用性检查 + dispatch 接口。

**RedisAdapter** (11动作): 原生 RESP 协议编解码。动作: info, config_get/set, set/get, keys, save, write_ssh_key（未授权 RCE 链）, slave_of, execute_lua, raw_cmd。

**JMXAdapter** (5动作): JRMI 握手 + nmap 脚本 + ysoserial 反序列化 payload 生成。动作: probe（直接 JRMI socket）, dump_registry, jmx_info, jmx_brute, prepare_exploit（ysoserial gadget chain）。

**MongoAdapter** (6动作): 原生 BSON 编解码 + OP_QUERY/OP_REPLY 线协议。动作: server_info, list_dbs, list_collections, find_sample, count。

### 2.13 其他核心模块

**llm_client.py** (~556行): OpenAI 兼容客户端。支持 function calling、SSE streaming、reasoning_content 提取（DeepSeek 格式）。适配 OpenAI/DeepSeek/Ollama/Claude。指数退避重试。

**tool_registry.py** (~509行): 三源合并工具注册表（静态 TOML + skill JSON + PATH 扫描）。始终注入 4 个在线搜索工具。工具分类: 命令别名、二进制别名、解析器映射（35+工具）、风险等级（40+工具）。

**reporting.py** (~491行): 报告渲染。乱码修复（gb18030→utf-8）、CVE 提取、CVSS 评分、影响分析（中文）、修复计划（4阶段）、攻击路径重建、覆盖率缺口检测。

**kali_executor.py** (~268行): SSH 远程执行器。Kali 攻击箱命令执行 + 目标跳板执行（expect 密码注入）+ 15 工具可用性检查。

---

## 三、skill_engine 模块 — 技能引擎

### 3.1 Skill 加载与解析

**skill_md_parser.py**: 解析 v2.0 SKILL.md 格式。YAML frontmatter → SkillMdMeta（name/desc/domain/subdomain/tags/version/cve/severity）。正文按 `##` 切分，30+ 章节别名映射（中英文）到标准字段: principle, detection_fingerprint, workflow, failure_modes, generalization, when_to_use, key_concepts 等。

**skill_loader.py**: 递归扫描 skills/ 目录。LoadedSkill 统一表示三种模式: knowledge（纯 MD）、pipeline（纯 JSON）、hybrid（MD+JSON）。learned/ 目录按 active/draft 分类加载，跳过 deprecated。

### 3.2 Skill 检索与匹配

**skill_matcher.py**: 多策略融合检索。

```
match(query)
  ├── 1. SERVICE_SKILL_MAP 服务名直连 (+15 boost)
  ├── 2. 规则评分 (name/desc/tag/keyword/domain 匹配)
  ├── 3. _fuse_with_hybrid_search()
  │     ├── TF-IDF 余弦相似度 (skill_index.py)
  │     ├── Embedding 余弦相似度 (skill_embedding_index.py)
  │     └── RRF 融合 (K=60)，归一化到 0-20 分
  └── 返回 top-K SkillMatch
```

**`format_knowledge_for_prompt()`**: 按阶段排序章节注入 LLM prompt:
- planning: principle → detection_fingerprint → generalization
- execution: workflow → detection_fingerprint → failure_modes
- recovery: failure_modes → workflow → detection_fingerprint

包含反过拟合前缀指令，强制 LLM 将 skill 当参考而非脚本。每 skill 3000 字符预算。

**skill_index.py**: TF-IDF 索引。平滑 IDF + 稀疏向量余弦。中英文混合分词。

**skill_embedding_index.py**: Embedding 索引。bge-small-zh-v1.5 (512维, 中英双语)。增量编码（sha256 变更检测）。numpy mmap 存储。

**encoder.py**: 线程安全单例。lazy 加载 fastembed。graceful 降级（import 失败不阻断）。

### 3.3 Skill 生成与生命周期

**skill_generator.py** (~825行): 成功路径 → v2.0 SKILL.md。

```
generate_from_state()
  ├── _extract_attack_paths()  ← 按 (port, service_tag) 聚类
  ├── 每路径:
  │     ├── _render_skill_md_v2_with_llm()  ← LLM 生成（验证 frontmatter + ≥2 章节）
  │     └── _render_skill_md()  ← 模板回退（14种服务类型原理提示）
  └── _render_summary_skill()  ← 汇总 skill
```

`_build_online_search_context()`: 从在线搜索结果中提取相关 CVE/exploit/MSF 数据注入生成 prompt。

**failure_skill_generator.py**: 失败经验 → v2.0 SKILL.md。从 state 提取失败信号（≥3次同类触发），生成 failure-*.md（Workflow 替换为规避策略+替代方案）。

**quality_gate.py**: 4 项独立检查:
1. frontmatter 必需字段（name/desc/domain/subdomain/version）
2. v2.0 五段式章节（Principle/Detection Fingerprint/Workflow/Failure Modes/Generalization）
3. 去重（difflib SequenceMatcher, 阈值 0.85）
4. grounding（CVE 必须在 state 证据中出现，可选强制执行）

**lifecycle_manager.py**: draft → active → deprecated 状态机。
- 晋升条件: ≥2 次成功使用 + ≥24h 存活
- 废弃条件: >30天未使用
- 持久化: skills/learned/.lifecycle.json

---

## 四、online_search 模块 — 在线搜索 (v3.0)

### 4.1 架构

```
OnlineSearchService (registry.py)
  ├── 4 个工具: search_cve / search_exploit / lookup_msf_module / lookup_default_creds
  ├── 预算控制: max_calls_per_pentest=10 + 查询去重
  ├── OnlineSearchCache (cache.py) — 3级缓存
  │     ├── L1: 内存 dict
  │     ├── L2: 磁盘 JSON (7天 TTL)
  │     └── L3: 永久磁盘 (skills/knowledge_base/)
  ├── NvdClient (nvd_client.py) — NVD REST API v2.0
  │     ├── 滑动窗口限流 (5次/30s)
  │     ├── 指数退避重试 (max 2次, 最长8s)
  │     └── CVE 归一化 (英文描述优先, CVSS v3.1>v3.0>v2, CPE 列表)
  ├── MsfModuleClient (msf_module_client.py)
  │     ├── 离线 KB (6个高频模块完整元数据)
  │     ├── Rapid7 页面抓取
  │     └── CVE → MSF 模块反向查找
  └── DefaultCredsClient (default_creds_client.py)
        ├── 内置 15 产品凭据库
        └── cirt.net HTML 抓取
```

### 4.2 自动注入

agent.py 的 `_auto_inject_service_intel()` 根据当前扫描到的服务自动调用在线搜索，结果写入 `state.service_intel`，后续 LLM 规划时可引用。

---

## 五、experience_store 模块 — 经验存储

**ExperienceStore** (store.py):

- `add()`: 记录渗透经验。目标指纹（OS/服务/版本/端口）→ SHA256 指纹哈希去重。embedding 编码用于语义检索。持久化到 `skills/.experience/YYYY/MM/<id>.json`。
- `query_similar_env()`: 两阶段检索 — 精确指纹匹配(score=1.0) + embedding 余弦相似度补充。
- `render_for_prompt()`: 格式化为 LLM 可注入摘要（日期/相似度/目标/结果/成功路径/建议），受 budget_chars 限制。

numpy 矩阵存储: `skills/.experience/.cache/experience.npy` + `experience_meta.json`。

---

## 六、自进化闭环

整个自进化架构串联 pentest_agent + skill_engine + experience_store:

```
渗透执行 (agent.py)
  │
  ├── 成功路径 + 失败路径记录到 State
  │
  ▼
Reflection 阶段 (reflection.py)
  ├── StructuredEvaluator → 提取 AttackPath/FailedPath/UnexploredSurface
  ├── LLMReflector → root_cause_analysis + generalizable_patterns
  │
  ├── SkillGenerator → 成功路径 → v2.0 SKILL.md → skills/learned/draft/
  ├── FailureSkillGenerator → 失败信号 → failure-*.md → skills/learned/draft/
  │
  ├── SkillQualityGate → frontmatter + 章节 + 去重 + grounding
  │     ├── 通过 → LifecycleManager.register_draft()
  │     └── 拒绝 → 记录原因，不写入
  │
  ├── LifecycleManager.auto_maintenance()
  │     ├── draft → active (≥2成功 + ≥24h)
  │     └── active → deprecated (>30天未用)
  │
  ├── SkillLoader.load_all() → 重载所有 skill（含新 active）
  │
  └── ExperienceStore.add() → 记录指纹 + 结果 + embedding
        │
        ▼
  下次渗透: SkillMatcher 匹配新生成的 skill
            ExperienceStore 注入相似环境经验
```

---

## 七、前端架构 (src/)

### 7.1 核心层

**SDITApp** (`modules/core/app.ts`): 应用生命周期管理、全局状态、UI 模式切换（经典/AI 指挥台）、主题系统（浅色/深色/樱花粉）、SSH 连接管理。

**StateManager** (`modules/core/stateManager.ts`): 应用状态维护（当前页面/连接状态/主题/UI模式），双向绑定 UI 渲染器。

### 7.2 AI Agent 系统

三层架构: AgentService（单例 Façade）→ AgentClient（HTTP Transport）→ Python Backend。

AgentService 提供: runAgentTask, runSecurityCheck, runEmergencyResponse, runLogAnalysis, runAutoRemediation。

### 7.3 功能模块

- **SSH/SFTP**: 连接 CRUD、密码加密、终端会话（WebSocket）、文件管理、30s 自动更新
- **快速检测**: 100分制评分（Critical:-40, High:-20, Medium:-10, Low:-5），7类检测并行/串行
- **Payloader**: 内网/Web 载荷库、编码工具（Base64/Hex/URL/ROT13）、反弹 Shell 生成
- **应急响应**: 场景化命令推荐（挖矿/Webshell/横向移动/数据泄露）
- **UI 渲染**: 侧边栏导航、多页面管理、响应式布局、主题适配

---

## 八、数据存储

### 文件系统

| 路径 | 用途 |
|------|------|
| skills/exploit-skills/ | 19 个手写 v2.0 SKILL.md |
| skills/builtin/ | 5 个内置在线搜索 skill |
| skills/experimental/ | 6 个实验 skill (2 MD + 6 JSON) |
| skills/imported/ | 754 个导入的网络安全 skill |
| skills/learned/{active,draft,deprecated}/ | 自学习 skill（运行时生成） |
| skills/learned/.lifecycle.json | 生命周期状态 |
| skills/.experience/ | ExperienceStore 持久化 |
| skills/knowledge_base/ | 在线搜索 L3 永久缓存 |

### 运行时状态

| 文件 | 用途 |
|------|------|
| state_*.json | 渗透状态快照（pentest_agent State） |
| reports/*.json + *.html | 渗透报告 |
| data/audit_log.db | 审计日志 |

---

## 九、API 端点

### REST API

| 端点 | 方法 | 功能 |
|-----|------|------|
| `/health` | GET | 健康检查 |
| `/api/v1/ssh/connect` | POST | SSH 连接 |
| `/api/v1/ssh/disconnect` | POST | SSH 断开 |
| `/api/v1/ssh/execute` | POST | 执行命令 |
| `/api/v1/sftp/list-files` | POST | 文件列表 |
| `/api/v1/agent/run` | POST | Agent 渗透任务 |
| `/api/v1/detection/run` | POST | 安全检测 |
| `/api/v1/log/analyze` | POST | 日志分析 |

### WebSocket

| 端点 | 功能 |
|-----|------|
| `/ws/terminal/{terminal_id}` | 实时终端 I/O |
| `/ws/events` | 事件推送 |

---

## 十、测试

22 个测试文件覆盖:

- P0-P9 各阶段功能验证（test_p0_self_evolving ~ test_p9_auto_intel_and_completion）
- Agent 基础（grounding, llm_resilience, executor_fallback, llm_client_retry, tool_registry）
- 攻击流程（exploit_flow, exploit_retry, brute_dict, protocol_adapters, python_exploit）
- API 契约（ai_chat_proxy, detection_errors, remediation_api）

```bash
cd src-python && pytest tests/
```

---

*本文档基于代码库实际结构编写，最后更新: 2026-06-25*
