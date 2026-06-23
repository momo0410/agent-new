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
4. **当前优先级**: 稳住 skill 体系 + 自升级闭环。联网检索是 v3.0 的事，本期暂不实现

四个核心能力（按重要性排序）：

1. **能自主完成渗透流程**: 端口扫描 -> 服务指纹 -> 匹配 skill -> LLM 规划 -> 执行 -> 拿到 shell / 证据 -> 生成报告
2. **靠 skill 学知识，不是死记命令**: skill 不是命令清单，是"漏洞为什么能打、同类漏洞怎么打"的知识本身。让模型有迁移能力
3. **能从每次渗透中自我升级**: 渗透结束后把经验（包括失败教训）沉淀成新 v2.0 skill，下一次同问题直接用本地知识，越用越聪明
4. **教学友好**: 报告中体现"为什么这么打、为什么这一步失败、下一步怎么换路径"，而不是只列命令和结果。让学生看得懂学得到

不做的事情（明确划清边界）：

- 不做 Windows 渗透
- 不做内网横向 / 域控接管的复杂场景
- 不做绕过 EDR / 杀毒规避（教学场景不需要）
- 本期不做联网检索（v3.0 再做）
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
2. Nmap 端口扫描得到服务指纹
3. SkillMatcher 根据服务名匹配 skill
4. LLM Planner 基于 skill 知识生成攻击方案
5. Executor 执行命令，结果写回 State
6. 多轮迭代直到拿到 Shell 或 Evidence
7. SkillGenerator 自动总结生成新 skill 写入 skills/learned/
8. 报告生成

### 2.3 组件状态总览

- 前端 Vue 3 — 已完成
- 后端 FastAPI — 已完成
- 渗透 Agent 核心 — 已完成
- 技能引擎 SkillEngine — 已完成 v2.0 升级
- 17 个 exploit-skills v2.0 — 已完成
- Agent 自升级闭环 — 已完成
- Kali 远程执行 — 已完成
- 报告生成 — 已完成
- 联网检索 — v3.0 任务，本期不做

---

## 三、已完成的工作（最近两轮）

### 3.1 Skill v2.0 体系全链路升级

升级前的问题: skill 只有 Workflow 章节，等于命令清单。LLM 只会照抄，遇新场景就卡死。

升级后的设计:

- SkillMdParser 新增章节识别 principle / detection_fingerprint / failure_modes / generalization，frontmatter 支持 cve / severity
- SkillMatcher 分层注入策略，按 planning / execution / recovery 三个阶段决定章节优先级
- SkillMatcher 注入头部增加反过拟合指令，强制模型把 skill 当参考非命令
- 17 个 exploit-skills 全量升级为 v2.0 五段式
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

### 3.3 17 个已升级 exploit-skills

源码供应链后门类: exploit-vsftpd-backdoor, exploit-unrealircd-backdoor, exploit-irc-backdoor

命令注入类: exploit-samba-usermap, exploit-php-cgi

未认证 RCE 类: exploit-distcc-command-exec, exploit-druby-rce, exploit-java-rmi

文件写入 RCE 类: exploit-proftpd-modcopy

配置错误类: exploit-nfs-privesc

默认凭据类: exploit-mysql-weak-creds, exploit-postgres-weak-creds, exploit-tomcat-default-creds, exploit-vnc-noauth

爆破弱口令类: exploit-ssh-bruteforce, exploit-telnet-bruteforce, exploit-rlogin-rsh

### 3.4 已变更未提交文件

代码修改:

- src-python/app/services/pentest_agent/agent.py
- src-python/app/services/pentest_agent/executor.py
- src-python/app/services/pentest_agent/planner.py
- src-python/app/services/skill_engine/skill_generator.py
- src-python/app/services/skill_engine/skill_loader.py
- src-python/app/services/skill_engine/skill_matcher.py
- src-python/app/services/skill_engine/skill_md_parser.py

新增:

- skills/exploit-skills/ 17 个新目录
- skills/learned/ 空目录运行时生成
- src-python/app/services/pentest_agent/kali_executor.py（v2 凭据安全版）
- src-python/app/services/discover.py（多靶机发现服务）
- test_exploit_flow.py

---

## 四、本期还要做的事

明确范围: 本期不做联网检索。把已完成的工作跑稳、跑出教学价值。

### 4.1 必做事项

1. 端到端验证: 用 Metasploitable2 完整跑一遍，确认 17 个 v2.0 skill 在真实渗透中正常工作
2. 验证自升级闭环: 渗透结束后 SkillGenerator 真的能生成可用的 v2.0 skill 落到 skills/learned/，下一轮命中
3. 验证 Principle 章节的事实准确性: 17 个 skill 中 Principle 部分是基于训练记忆写的，可能有错。需用人工或后续 v3.0 联网检索修正
4. 报告生成的教学化改造: 报告中要体现"为什么这么打、为什么失败、怎么换路径"，让学生看得懂学得到。当前报告偏命令日志风格，需要调整为叙事风格

### 4.2 不做事项（明确划清）

- 不做联网检索（v3.0 再说）
- 不做 Windows 渗透
- 不做半自动 / 用户确认流程
- 不做 EDR 规避

---

## 五、未来规划（v3.0 及以后）

仅列出，本期不做:

- v3.0: 联网检索能力（NVD / ExploitDB / MSF docs / 默认密码库）
- v3.1: 用联网检索反查修正 17 个 skill 的 Principle 章节
- v3.2: skill 知识图谱（在 Generalization 章节之间建立显式关联）
- v4.0: 多目标 / 内网横向（教学场景的进阶）
- v4.1: Windows 靶机支持

---

## 六、关键文件入口

| 文件 | 作用 |
|------|------|
| src-python/app/services/pentest_agent/agent.py | Agent 主入口，驱动规划-执行循环 |
| src-python/app/services/pentest_agent/planner.py | LLM 驱动的任务规划器 |
| src-python/app/services/pentest_agent/executor.py | 命令执行器 |
| src-python/app/services/pentest_agent/state.py | 渗透状态管理 |
| src-python/app/services/pentest_agent/llm_client.py | LLM 客户端 |
| src-python/app/services/pentest_agent/tool_registry.py | 工具注册中心 |
| src-python/app/services/skill_engine/skill_md_parser.py | SKILL.md 解析器 |
| src-python/app/services/skill_engine/skill_loader.py | Skill 加载器 |
| src-python/app/services/skill_engine/skill_matcher.py | Skill 匹配器 + prompt 注入 |
| src-python/app/services/skill_engine/skill_generator.py | Skill 自动生成器（双层架构） |
| skills/exploit-skills/ | 17 个手写的 v2.0 exploit skill |
| skills/learned/ | Agent 自学习产出，运行时生成 |
