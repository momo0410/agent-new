# 项目当前情况与目标

最后更新: 2026-06-23
文档目的: 给接手项目的人一份单文件全景说明

---

## 一、项目总目标

**做一个面向教学场景的全自动 Linux 渗透 AI Agent。**

四个关键定位：

1. **教学产品**: 面向学生 / 红队培训 / 网安课程使用。不是商业渗透平台，也不是个人玩具
2. **全自动**: 用户给一个目标 IP 就可以走开，回来看 Markdown / HTML 报告。中间过程不需要用户确认或干预
3. **通用 Linux 靶机**: 任意未知配置的 Linux 服务器。不限于 Metasploitable2/3 这种已知靶机，也不覆盖 Windows / 网络设备 / IoT
4. **当前优先级**: 自升级闭环已打通,在线搜索(v3.0)已实现。当前重点:端到端验证 + 报告教学化改造

四个核心能力（按重要性排序）：

1. **能自主完成渗透流程**: 端口扫描 -> 服务指纹 -> 匹配 skill -> LLM 规划 -> 执行 -> 拿到 shell / 证据 -> 生成报告
2. **靠 skill 学知识，不是死记命令**: skill 不是命令清单，是"漏洞为什么能打、同类漏洞怎么打"的知识本身。让模型有迁移能力
3. **能从每次渗透中自我升级**: 渗透结束后把经验（包括失败教训）沉淀成新 v2.0 skill，下一次同问题直接用本地知识，越用越聪明
4. **教学友好**: 报告中体现"为什么这么打、为什么这一步失败、下一步怎么换路径"，而不是只列命令和结果。让学生看得懂学得到

不做的事情（明确划清边界）：

- 不做 Windows 渗透
- 不做内网横向 / 域控接管的复杂场景
- 不做绕过 EDR / 杀毒规避（教学场景不需要）
- 不做需要用户审核 / 确认的半自动流程

---

## 二、项目当前情况

### 2.1 项目身份

SDIT (Security Detection and Incident Toolkit) - 一套集成 SSH 远程管理、安全检测、应急响应、报告生成的安全工具，核心是 AI 驱动的自动化渗透测试 Agent。

技术栈:

- 前端 Vue 3 + TypeScript + Vite
- 后端 Python FastAPI + asyncssh
- AI 支持 OpenAI / DeepSeek / Qwen / Ollama
- 攻击执行通过 SSH 远程在 Kali 上跑工具

### 2.2 渗透流程现状

1. 用户输入目标 IP
2. Nmap/Rustscan 端口扫描得到服务指纹（init 阶段）
3. SkillMatcher 混合检索（TF-IDF + Embedding + 规则 + RRF 融合）匹配 skill
4. OnlineSearchService 自动注入 CVE/Exploit/MSF/默认密码情报
5. LLM Planner 基于 skill 知识 + 在线情报 + 候选任务生成攻击方案（4级解析回退链）
6. Executor 执行命令（含协议适配器 Redis/JMX/Mongo、python_exploit、交互式会话），结果写回 State
7. ExploitRetryStrategy 自动轮换 MSF payload，ActionCritic LLM 诊断失败原因
8. 多轮迭代 + 阶段自动切换（init→recon→web→exploit→post→lateral）直到拿到 Shell 或 Evidence
9. Reflection 阶段：结构化评估 + LLM 反思 + SkillGenerator/FailureSkillGenerator 生成新 skill
10. SkillQualityGate 质量门控 + LifecycleManager 生命周期管理（draft→active→deprecated）
11. ExperienceStore 持久化渗透经验（embedding 语义检索）
12. 报告生成（含攻击面覆盖率分析、证据链、修复建议）

### 2.3 组件状态总览

- 前端 Vue 3 — 已完成
- 后端 FastAPI — 已完成
- 渗透 Agent 核心（pentest_agent 模块）— 已完成
  - 8阶段流水线: init→recon→web→exploit→post→lateral→reflection→done
  - 4级 LLM 解析回退链（function calling → XML → legacy → deterministic fallback）
  - TokenBudget 上下文管理（12000 token 总预算，按模块分配）
  - 停滞检测 + 攻击面预算冷却机制
- 技能引擎 SkillEngine — 已完成 v2.0 + 混合检索
  - SkillMdParser: v2.0 五段式解析（30+ 章节别名映射）
  - SkillMatcher: TF-IDF + Embedding(bge-small-zh-v1.5) + RRF 融合 + 服务名直连(+15)
  - SkillGenerator: 双层架构（程序提取事实 + LLM 反思生成，失败回退模板）
  - FailureSkillGenerator: 失败经验→skill（≥3次同信号触发）
  - SkillQualityGate: frontmatter + v2.0 章节 + 去重(0.85) + grounding 检查
  - LifecycleManager: draft→active(≥2成功+≥24h)→deprecated(>30天未用)
- 19 个 exploit-skills v2.0 — 已完成
- 在线搜索 OnlineSearchService — 已完成（v3.0）
  - 4 个工具: search_cve / search_exploit / lookup_msf_module / lookup_default_creds
  - 3 级缓存: L1 内存 → L2 磁盘(7天TTL) → L3 永久
  - NVD API v2.0 客户端（滑动窗口限流 5次/30s）
  - 内置 MSF 模块知识库 + 默认密码库（15产品）
- ExploitRetryStrategy — 已完成（MSF payload 分层轮换，8个模块映射）
- ActionCritic — 已完成（LLM 失败诊断，7种失败分类）
- 协议适配器 — 已完成（Redis RESP 11动作 + JMX/RMI 5动作含 ysoserial + MongoDB 6动作）
- Python Exploit — 已完成（子进程隔离执行 LLM 编写的 PoC，exploit_lib 辅助库）
- 交互式会话 — 已完成（PTY 支持，token 分隔命令完成，成功模式检测）
- ExperienceStore — 已完成（embedding 语义检索，目标指纹去重）
- Reflection 阶段 — 已完成（结构化评估 + LLM 反思 + skill 生成全链路）
- Kali 远程执行 — 已完成
- 报告生成 — 已完成（含攻击面覆盖率分析、覆盖率缺口检测）

---

## 三、已完成的工作

### 3.1 Skill v2.0 体系全链路升级

升级前的问题: skill 只有 Workflow 章节，等于命令清单。LLM 只会照抄，遇新场景就卡死。

升级后的设计:

- SkillMdParser 新增章节识别 principle / detection_fingerprint / failure_modes / generalization，frontmatter 支持 cve / severity
- SkillMatcher 分层注入策略，按 planning / execution / recovery 三个阶段决定章节优先级
- SkillMatcher 注入头部增加反过拟合指令，强制模型把 skill 当参考非命令
- 19 个 exploit-skills 全量升级为 v2.0 五段式
- SkillGenerator 双层架构: 程序提取事实 + LLM 反思生成，失败回退模板
- Agent 自升级闭环已打通

### 3.2 v2.0 SKILL.md 五段式结构

frontmatter 字段: name, description, domain, subdomain, tags, cve, severity, version

正文章节:

1. Principle — 漏洞原理（为什么能打，不是怎么打）
2. Detection Fingerprint — 精确检测条件 + 反例
3. Workflow — 2-3 种利用方法（msf / 手动 / 备选）
4. Failure Modes — 失败现象表格
5. Generalization — 同类漏洞列表 + 通用利用模板
6. Key Concepts — 速查表

参考完整范例: skills/exploit-skills/exploit-vsftpd-backdoor/SKILL.md

### 3.3 19 个已升级 exploit-skills

源码供应链后门类: exploit-vsftpd-backdoor, exploit-unrealircd-backdoor, exploit-irc-backdoor

命令注入类: exploit-samba-usermap, exploit-php-cgi

未认证 RCE 类: exploit-distcc-command-exec, exploit-druby-rce, exploit-java-rmi

文件写入 RCE 类: exploit-proftpd-modcopy

配置错误类: exploit-nfs-privesc

默认凭据类: exploit-mysql-weak-creds, exploit-postgres-weak-creds, exploit-tomcat-default-creds, exploit-vnc-noauth

爆破弱口令类: exploit-ssh-bruteforce, exploit-telnet-bruteforce, exploit-rlogin-rsh

通用型: exploit-apache-http, exploit-generic-bindshell

### 3.4 P0-P5 自进化闭环（已验证，R1-R7 共 44 目标）

- P0: SkillGenerator 接入 agent.py 主循环，渗透结束后自动生成 skill
- P1: 混合检索 SkillMatcher（TF-IDF + Embedding + RRF 融合）
- P2: Reflection 阶段（结构化评估 + LLM 反思 + skill 生成全链路）
- P3: ExperienceStore 语义检索（bge-small-zh-v1.5 embedding）
- P4: SkillQualityGate + LifecycleManager（质量门控 + 生命周期管理）
- P5: Generalization 章节 + 在线搜索初步

### 3.5 P6-P9 增强（已验证，R8-R9B 多轮测试）

- P6: ExploitRetryStrategy — MSF payload 分层轮换（8个模块映射），NO_SESSION 信号检测
- P6.1: Hydra 字典治理 — 运行时字典生成/裁剪，避免超大字典暴破
- P7: 协议适配器 — Redis RESP(11动作) / JMX-RMI(5动作+ysoserial) / MongoDB Wire(6动作)
- P8: python_exploit — 子进程隔离执行 LLM 编写的 PoC，exploit_lib 辅助库（HTTP/AES/base64/ysoserial）
- P9: Auto-Intel 自动情报注入 + 完成门控（防止过早退出）
- ActionCritic: LLM 失败诊断（7种分类），连续3次失败自动触发

### 3.6 agent.py 核心增强

- 8阶段流水线: init→recon→web→exploit→post→lateral→reflection→done
- 4级 LLM 解析回退链: function calling → XML tag → legacy single-tool → deterministic fallback
- TokenBudget 上下文管理: 12000 token 总预算，按模块分配配额
- 停滞检测: 连续低价值动作检测 + 高价值攻击面回退
- 攻击面预算冷却: zero-evidence 检测 + 信息增益耗尽判断
- post 阶段会话聚焦: 自动重连丢失的交互式会话

### 3.7 在线搜索（v3.0 已实现）

- OnlineSearchService: 4 工具 + 3 级缓存（L1内存→L2磁盘7天→L3永久）
- NVD API v2.0 客户端: 滑动窗口限流（5次/30s），CVE 查询 + 关键词搜索
- MSF 模块客户端: 离线知识库(6高频模块) + Rapid7 页面抓取
- 默认密码客户端: 内置15产品凭据库 + cirt.net 在线查询
- agent.py 自动注入: 根据扫描到的服务自动调用在线搜索并注入 state.service_intel

### 3.8 已变更未提交文件

核心代码:

- src-python/app/services/pentest_agent/agent.py（主循环 + 在线搜索注入 + 回退链 + 停滞检测）
- src-python/app/services/pentest_agent/executor.py（协议适配路由 + python_exploit + 工具回退）
- src-python/app/services/pentest_agent/planner.py（19 模板 + 攻击面评分 + 服务家族分桶）
- src-python/app/services/pentest_agent/state.py（TokenBudget + milestones + service_intel + doctor）
- src-python/app/services/pentest_agent/reflection.py（新增：结构化评估 + skill pipeline 触发）
- src-python/app/services/pentest_agent/capabilities.py（新增：语义能力标签推断）
- src-python/app/services/pentest_agent/critic.py（新增：LLM 失败诊断）
- src-python/app/services/pentest_agent/exploit_retry.py（新增：MSF payload 轮换）
- src-python/app/services/pentest_agent/python_exploit.py（新增：PoC 子进程执行）
- src-python/app/services/pentest_agent/interactive_session.py（新增：持久 shell 会话）
- src-python/app/services/pentest_agent/protocol_adapters/（新增：Redis/JMX/Mongo 原生协议）
- src-python/app/services/skill_engine/skill_generator.py（v2 生成 + 在线搜索上下文注入）
- src-python/app/services/skill_engine/skill_matcher.py（混合检索 + RRF 融合）
- src-python/app/services/skill_engine/skill_loader.py（learned 目录分类加载）
- src-python/app/services/skill_engine/skill_md_parser.py（30+ 章节别名映射）
- src-python/app/services/skill_engine/failure_skill_generator.py（新增：失败经验→skill）
- src-python/app/services/skill_engine/quality_gate.py（新增：质量门控）
- src-python/app/services/skill_engine/lifecycle_manager.py（新增：生命周期管理）
- src-python/app/services/skill_engine/encoder.py（新增：bge-small-zh-v1.5 共享单例）
- src-python/app/services/skill_engine/skill_embedding_index.py（新增：embedding 索引）
- src-python/app/services/online_search/（新增：全套在线搜索服务）
- src-python/app/services/experience_store/（新增：经验存储）

新增目录/文件:

- skills/exploit-skills/ 19 个目录（含 SKILL.md）
- skills/learned/{active,draft,deprecated}/ 运行时生成
- skills/.experience/ 经验存储
- skills/knowledge_base/ L3 永久缓存

---

## 四、当前待办事项

### 4.1 已完成事项 (2026-06-25 5轮渗透测试)

1. ✅ 端到端验证: Metasploitable2 完成 5 轮全自动渗透测试
   - R1: 30 findings, 8 vulns, 1 session (root via 1524 bindshell)
   - R2: 30 findings, 8 vulns, 7 sessions, 1 credential (Samba 139 exploited)
   - R3: 30 findings, 7 vulns, 12 sessions, Java RMI 1099 exploited
   - R4-R5: P13 直接利用钩子尝试自动执行 vsftpd/distccd/UnrealIRCd/MySQL/PostgreSQL
   - **实际覆盖率: 8/20 漏洞 (40%)** — P13 因缺 LHOST 参数导致 msfconsole 执行失败
   - **P13 修复后预期: 14/20 漏洞 (70%)** — LHOST 动态检测已推送，待下一轮验证

2. ✅ P10-P13 新功能开发
   - P10: exploit 失败自动联网检索替代方案
   - P11: shell 会话自动凭据采集
   - P12: 未利用高价值漏洞自动注入利用指令（每3轮重新注入）
   - P13: 简单已知漏洞直接执行利用（绕过 LLM 选择偏差）

3. ✅ 核心 bug 修复
   - nmap `--script auth,vuln` 超时 420s→240s，停滞恢复改用 `http-vuln*`
   - nc session recording 支持
   - LLM 输出占位符过滤（"工具名""参数"等）
   - searchsploit 候选从 6 降到 2
   - hydra 自动追加 `-I` 跳过恢复文件等待
   - P13 msfconsole 命令动态获取 LHOST（socket 检测 Kali IP）
   - P14 msfconsole 命令重写修复：自动移除中间 `run; exit` / `exploit; exit`，统一在 LPORT/payload 注入后追加 `exit -y`，避免追加参数落在 exit 后导致 Metasploit 长时间挂起
   - P15 msfconsole stall guard：将 msfconsole 通用超时从 900s 改为 `SDIT_MSF_STALL_TIMEOUT`（默认 90s），防止 reverse/session 模块在无会话时卡住整轮
   - P15 在线情报优先级提升：service_intel token 配额 500→1200，并提前到候选任务之前注入；上下文明确要求模型优先参考 CVE/MSF/default creds/recommended 命令
   - P16 进程组强杀：Executor 在 POSIX 下用 `setsid` 启动子进程，超时时 kill 整个 process group，避免 shell 被杀但 msfconsole/ruby 子进程残留

4. ✅ R10 首轮验证发现并修复 P14 问题
   - 流程: Windows 通过 GitHub 同步到 Kali (`git pull --ff-only origin master`)，Kali 本地运行 `SDIT_SSH_HOST=local python3 -u batch_pentest.py --targets MSF2=192.168.136.137 --max-rounds 25`
   - 发现: P13 动态 LHOST 已生效，但 msfconsole rewrite 在原始命令已含 `run; exit` 时把 `set LPORT/set payload/exploit` 追加到了 exit 后；UnrealIRCd 模块进入长时间挂起
   - 修复: 在 `executor._rewrite_msfconsole_args()` 中通用规范化 msfconsole `-x` 脚本，删除中间 exit、将 run 统一成 exploit，再注入 LPORT/payload/exit -y；不写具体 IP、端口、靶机名
   - 验证: `python -m pytest -q tests/test_p6_1_brute_dict.py` 22 passed；`tests/test_p6_exploit_retry.py tests/test_p9_auto_intel_and_completion.py tests/test_pentest_executor_fallback.py` 42 passed

5. ✅ R11 监控发现并修复 P15 问题
   - 发现: P14 rewrite 已生效，vsftpd/distccd 的 msfconsole 均约 9s 退出；但 UnrealIRCd reverse payload 仍在 `exploit; exit -y` 后挂起超过 6 分钟，阻塞整轮
   - 处理: 立即停止 R11，保留日志作为问题证据；不继续等待 900s 默认超时
   - 修复: 将 msfconsole 执行超时改为可配置 `SDIT_MSF_STALL_TIMEOUT`，默认 90s；同时提高在线情报在 LLM 上下文中的优先级和可见性
   - 验证: `python -m pytest -q tests/test_p9_auto_intel_and_completion.py tests/test_p6_1_brute_dict.py tests/test_p6_exploit_retry.py tests/test_pentest_executor_fallback.py` 64 passed

6. ✅ R12 监控发现并修复 P16 问题
   - 发现: R12 中 msfconsole 已按 90s 超时，但只杀了 shell wrapper，ruby/msfconsole 子进程变成 PPID=1 继续残留
   - 处理: 停止 R12 并手动清理残留 msfconsole/ruby 进程
   - 修复: `_run_process()` 在 POSIX 使用 `preexec_fn=os.setsid` 开新进程组，超时通过 `os.killpg(..., SIGKILL)` 强杀整组；Windows 保持 `proc.kill()` 路径
   - 验证: 同 P15 回归集合 64 passed

### 4.2 仍存在的问题

1. **hydra 爆破超时**: telnet/SSH/VNC 爆破字典大，hydra 经常跑 10+ 分钟不结束
2. **Web 应用完全未覆盖**: Mutillidae/DVWA/TWiki/phpMyAdmin 0% 覆盖
3. **凭据采集仍不足**: P11 注入指令但 LLM 不一定执行，P13 的 MySQL/PostgreSQL 自动采集可改进
4. **LLM 循环空转**: 经常在 LLM 思考阶段卡住，浪费轮次
5. **报告教学化改造**: 当前报告偏命令日志风格，需要调整为叙事风格

### 4.3 不做事项（明确划清）

- 不做 Windows 渗透
- 不做半自动 / 用户确认流程
- 不做 EDR 规避

---

## 五、未来规划

- v3.1: 用在线搜索反查修正 19 个 skill 的 Principle 章节
- v3.2: skill 知识图谱（在 Generalization 章节之间建立显式关联）
- v4.0: 多目标 / 内网横向（教学场景的进阶）
- v4.1: Windows 靶机支持

---

## 六、关键文件入口

| 文件/目录 | 作用 |
|------|------|
| **pentest_agent/** | |
| agent.py | Agent 主入口，8阶段流水线 + LLM 规划-执行循环 |
| planner.py | 规则候选任务生成（19模板 + 7服务家族 + 攻击面评分） |
| state.py | 渗透状态管理（TokenBudget + 攻击面生命周期 + milestones） |
| executor.py | 统一执行引擎（工具回退 + 协议适配路由 + python_exploit + 会话管理） |
| capabilities.py | 语义能力标签推断（17条 skill 步骤规则 + 参数规则） |
| critic.py | LLM 失败诊断（ActionCritic，7种失败分类） |
| reflection.py | 后渗透反思（结构化评估 + LLM 反思 + skill pipeline 触发） |
| exploit_retry.py | MSF payload 分层轮换策略 |
| python_exploit.py | 子进程隔离执行 LLM 编写的 PoC |
| interactive_session.py | 持久 shell 会话（PTY + token 完成检测） |
| reporting.py | 报告渲染（覆盖率分析 + 证据链 + 修复建议） |
| tool_registry.py | 工具注册（静态TOML + skill JSON + PATH扫描 + 在线搜索注入） |
| llm_client.py | LLM 客户端（OpenAI/DeepSeek/Ollama/Claude 适配） |
| kali_executor.py | Kali SSH 远程执行器 |
| protocol_adapters/ | Redis/JMX/MongoDB 原生协议适配器 |
| **skill_engine/** | |
| skill_md_parser.py | v2.0 SKILL.md 解析器 |
| skill_loader.py | Skill 加载器（builtin/experimental/exploit/learned/imported） |
| skill_matcher.py | 混合检索匹配器 + prompt 注入 |
| skill_generator.py | 成功路径→v2.0 skill（双层架构） |
| failure_skill_generator.py | 失败经验→v2.0 skill |
| quality_gate.py | 质量门控（frontmatter + 章节 + 去重 + grounding） |
| lifecycle_manager.py | 生命周期管理（draft→active→deprecated） |
| skill_index.py | TF-IDF 索引 |
| skill_embedding_index.py | Embedding 语义索引 |
| encoder.py | bge-small-zh-v1.5 共享单例编码器 |
| **online_search/** | |
| registry.py | 在线搜索服务（4工具 + 预算控制 + 去重） |
| cache.py | 3级缓存（L1内存→L2磁盘→L3永久） |
| nvd_client.py | NVD API v2.0 客户端 |
| msf_module_client.py | MSF 模块查询（离线KB + Rapid7） |
| default_creds_client.py | 默认密码查询（内置15产品 + cirt.net） |
| **experience_store/** | |
| store.py | 渗透经验存储（embedding 语义检索 + 指纹去重） |
| **skills/** | |
| exploit-skills/ | 19 个手写 v2.0 exploit skill |
| builtin/ | 5 个内置在线搜索 skill |
| imported/ | 754 个导入的网络安全 skill |
| learned/ | Agent 自学习产出（运行时生成） |

---

*本文档最后更新: 2026-06-25*
