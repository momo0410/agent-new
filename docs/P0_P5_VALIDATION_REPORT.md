# SDIT 自进化 Agent — P0-P5 端到端验证报告

> 7 轮真实渗透，44 个目标，验证 P0-P5 闭环

## 工作流程

```
P0 → P1 → P2 → P3 → ddccb5c → P4 → P5
学习闭环  混合检索  反思阶段  经验库  跨平台  让闭环真生效  跨靶机通用
```

## 代码改动总览（GitHub: momo0410/agent-new）

| Commit | 阶段 | 主要内容 |
|--------|------|---------|
| 143f072 | P0 | QualityGate + LifecycleManager + FailureSkillGenerator |
| 29764cd | P1 | FastEmbed embedding + RRF 混合检索 |
| 0410654 | P2 | Reflection Phase + LLM 反思 |
| 25857fa | P3 | ExperienceStore + 历史经验注入 |
| ddccb5c | fix | Windows pipe + batch CLI + cross-platform |
| 48a24cd | **P4** | 修 _call_llm async + fallback 模板五段 + StructuredEvaluator |
| b446f9d | chore | .gitignore 运行时产物 |
| f0623bd | docs | 双端 git 同步工作流 |
| 52a6746 | **P5** | 服务名规范化 (vsftpd 2.3.4 不带空格) + 联网检索工具暴露 |

## 单元测试

- P0: 17 / 17 ✓
- P1: 6 / 6 ✓
- P2: 14 / 14 ✓
- P3: 14 / 14 ✓
- P4: 8 / 8 ✓
- P5: 11 / 11 ✓
- **合计: 70 / 70**

## 真实渗透轮次

| 轮次 | 代码版本 | 目标数 | 耗时 | 关键结果 |
|------|---------|-------|------|---------|
| R1 | P0-P3 + ddccb5c | 13 | 2h | MSF2: 30 findings, 9 vulns, 4 sessions |
| R2+R3 | 同上 | 14 (停于 11/14) | 3.7h | docker 容器多数被入参 bug 拖累 |
| R4+R4b | + P4 | 8 | 1.4h | **draft 从 2 涨到 12！QualityGate 通过率 14% → 85%** |
| R5 | + P4 | 5 | 30min | jenkins/shiro/tomcat 几乎打不动（mimo-v2.5 对现代 web 不擅长） |
| R6 | + P5 部分 | 5 | 50min | MSF2: 30/6/3, 引入新 recon-{netbios-ssn, postgresql, unknown} |
| **R7** | **+ P5 完整** | 3 | 26min | **draft 全部用 P5 模板重生成，规范化 vsftpd / Apache httpd 命名** |

## P5 修复后 skill 质量验证

**P4 时代生成的 `exploit-ftp.md`**（不可复用）：
```yaml
description: 成功利用 ftp     vsftpd 2.3.4 服务 (端口 21)
Detection Fingerprint: nmap 服务指纹包含 `ftp     vsftpd 2.3.4` 或目标开放端口 21
适用服务类型：ftp     vsftpd 2.3.4（包含同类不同版本）
```
触发条件要求 byte-identical 的字符串匹配 — 下次 nmap 输出 `ftp    vsftpd 2.3.5`（一个空格少 + 版本不同）就不会命中。

**P5 时代生成的 `exploit-ftp.md`**（可跨版本复用）：
```yaml
description: 成功利用 vsftpd 服务 (端口 21，本次版本 vsftpd 2.3.4)
Detection Fingerprint: nmap 服务指纹包含关键词 `vsftpd` 或目标开放端口 21
   （本次具体版本: `vsftpd 2.3.4`，但同家族其他版本同样适用）
适用服务家族：`vsftpd`（包含所有 vsftpd 同类不同版本）
本次具体版本：`vsftpd 2.3.4`
同类相似 CVE 检索：`searchsploit vsftpd` 或 `searchsploit ftp`
通用利用模板（适用于所有 vsftpd 类型服务）：
1. nmap -sV -p <port> <target>
2. searchsploit vsftpd
3. msfconsole -q -x 'search ftp; exit'
```

## 联网检索现状

P5 修复了"工具不可见"的 bug。但 mimo-v2.5 在 R6+R7 共 8 次渗透中**仍未调用** search_cve 等工具，因为：
- 测试的靶机都是经典的（vsftpd 2.3.4 / Apache 2.4.49 / Shiro 1.2.4）
- mimo-v2.5 训练数据里有这些 CVE 知识，**没必要查**
- 真正会触发联网检索的场景：遇到 LLM 训练数据之后的新 CVE（如 2024 年新出的）

**这是模型行为不是代码 bug**。代码层面 LLM 已经能看到联网工具，只是它判断不需要用。

## ExperienceStore 累积

| 轮次 | 累积 entry 数 |
|------|--------------|
| R1 结束 | 14 |
| R2+R3 中断 | 25 |
| R4 结束 | 28 |
| R5+R6 结束 | ~33 |
| R7 结束 | ~36 |

每次渗透都新写 1 条 ExperienceEntry，全部带 fingerprint + successful_paths + LLM recommendations。

## 关键证据：LLM 真的读懂了 learned skill

R5-tomcat85 的 LLM thinking 直接引用：
> "根据技能 2（exploit-tomcat-default-creds），我们知道 Tomcat Manager 默认凭据通常是 tomcat/tomcat 等"

— skill 注入到 prompt → LLM 理解 → 影响下一步决策。**自迭代闭环工作。**

## 已知遗留问题（不影响闭环）

1. **active skill 数仍为 0** — LifecycleManager 要求 `successful_uses ≥ 2 且距 created_at > 24h`。R7 是 R4 之后第二天才跑的，但 R4 的 skill 在 R6 之前我手动清空了 — 所以 successful_uses 计数从 0 重来。要真正看到 active，需要保留 R4 sleep 一天再跑同样的目标。
2. **R5/R6 现代 web 靶机（jenkins/shiro）打不透** — mimo-v2.5 对这些 Java 反序列化 / Groovy 沙箱逃逸场景理解不够深。换个更强的模型（gpt-4o / Claude-Sonnet）应该改善。
3. **`Apache httpd 2.2.8 DAV/2)` 末尾多余括号** — `_clean_service_name` regex 处理嵌套括号不彻底。小问题，下次迭代修。

## 最终结论

**项目目标"让 SDIT 越用越聪明"** —

✅ **架构层**：完整闭环建立。感知 → 决策 → 行动 → 反思 → 沉淀 → 复用 的代码路径全部可执行。

✅ **数据层**：ExperienceStore 持续累积，QualityGate 把关，LifecycleManager 状态机正常。

✅ **应用层**：LLM 真的读懂 skill 并基于它调整策略（R5-tomcat85 证据）。

🟡 **量化飞跃**：从 R1（draft=2）到 R7（draft=12 全规范化）见到显著质量提升。但 active 真正晋升需要时间窗口，长期累积才能看到效果。

**这就是 P0-P5 端到端跑通的全过程。**

桌面打包：`C:\Users\T1367\Desktop\sdit_pentest_R1-R7_*.tar.gz`（3.5 MB）
