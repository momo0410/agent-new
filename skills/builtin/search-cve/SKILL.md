---
name: search-cve
description: 联网检索 CVE 详情（NVD）。当检测到 CVE 编号但本地 skill 无匹配时，调用 search_cve 查权威信息。
domain: penetration-testing
subdomain: reconnaissance
tags:
  - online-search
  - cve
  - nvd
  - intelligence
  - lookup
version: '2.0'
---

# search-cve

## Principle
渗透测试中，Agent 的本地 skill 库是静态的（17 个手写 skill + learned/ 中的自学习产出），无法覆盖所有 CVE。当 nmap 扫到某个服务版本、或上下文中出现一个本地 skill 未覆盖的 CVE 编号时，**主动联网查 NVD** 拿到权威描述（CVSS、影响版本、原理、参考链接），比凭训练记忆猜测更准确。

这是"本地优先、联网补充"策略的一部分：先查本地 SkillMatcher，无命中再联网，联网结果最终通过自升级闭环反哺成本地 skill。

## Detection Fingerprint
**应当调用 search_cve 的场景**（满足任一即可）：
- nmap 服务指纹含明确版本号（如 `vsftpd 2.3.4`），且 SkillMatcher 未匹配到任何 exploit-skill
- 上下文 / exploit 输出中出现了具体的 CVE 编号（如 `CVE-2011-2523`），但本地无对应 skill
- 连续 3 次 exploit 失败且无 skill 失败回退方案，需要查证目标是否真有已知漏洞
- searchsploit 返回结果中提到 CVE 编号，需要进一步了解该 CVE 的原理与影响范围

**反例（不要调用）**：
- 本地已有对应 exploit-skill（如扫到 vsftpd 2.3.4 且 `exploit-vsftpd-backdoor` 已命中）—— 直接用本地，更快更省
- 没有具体 CVE 编号也没有明确服务版本 —— 先用 nmap/searchsploit 拿到指纹再查
- 同一次渗透已经查过同一个 CVE —— 去重机制会拦截，不要重复发起

## Workflow

### 方法 A：按 CVE 编号精确查询（推荐）
```json
{
  "tool": "search_cve",
  "args": {"cve_id": "CVE-2011-2523"}
}
```
返回：CVSS 评分、影响版本范围、英文描述、参考链接。命中 L3 永久缓存时秒回且不计预算。

### 方法 B：从服务版本反查（先用 search_exploit）
如果只有服务版本没有 CVE 编号，先调 `search_exploit` 用关键词搜，拿到候选 CVE 列表后再用本工具逐个查详情。

### 调用前的判断
在调用前，先输出 `<think>` 说明：
1. 为什么本地 skill 不够用（哪个服务/版本没匹配上）
2. 期望从 NVD 拿到什么（原理？影响版本？利用参考？）

### 调用后的处理
拿到 CVE 详情后：
1. 阅读英文 description 理解漏洞原理
2. 看 affected_products 判断目标版本是否在影响范围内
3. 看 references 找 ExploitDB / Rapid7 / 厂商公告链接
4. 基于这些信息生成攻击方案，进入 exploit 阶段
5. 渗透结束后这些检索结果会被 SkillGenerator 自动提炼成 v2.0 skill 写入 skills/learned/

## Failure Modes
| 现象 | 原因 | 下一步 |
|---|---|---|
| 返回 `offline_mode: true` | NVD 不可达 / 超时 / 网络隔离 | 用本地 searchsploit 兜底，或凭已有 skill 继续 |
| 返回 `budget_exceeded: true` | 本次渗透联网查询已达上限(默认10次) | 复用已缓存结果，优先打高价值目标 |
| 返回"查询失败或无此 CVE" | CVE 编号拼错 / NVD 未收录 | 检查编号格式 `CVE-YYYY-NNNNN`，或改用 search_exploit 关键词搜 |
| 同一 CVE 第二次查返回缓存 | 去重机制生效（正常） | 直接用缓存结果，不要重试 |

## Generalization
这是"联网情报检索"类技能。识别套路：
1. **本地知识有边界** —— 任何静态 skill 库都有覆盖盲区，联网检索是必要补充
2. **权威源优先** —— NVD 是 CVE 的权威数据源，比模型记忆可靠
3. **查到即沉淀** —— 联网结果不应是一次性的，必须通过自升级闭环变成本地 skill

**同类检索技能**：
| 工具 | 数据源 | 适用场景 |
|---|---|---|
| search_cve | NVD | 有 CVE 编号，查详情 |
| search_exploit | NVD关键词 + 本地searchsploit | 有服务版本，找已知漏洞 |
| lookup_msf_module | Rapid7 | 要用 MSF 模块但不确定参数 |
| lookup_default_creds | cirt.net | 扫到设备/软件要试默认密码 |

**通用检索决策模板**：
1. 先问"本地 skill 命中了吗？" —— 命中就用本地
2. 没命中再问"我有 CVE 编号还是服务版本？" —— 决定调哪个工具
3. 联网拿到结果后问"这个结果值得复用吗？" —— 值得就等自升级闭环沉淀

## Key Concepts
| 字段 | 值 |
|---|---|
| 工具名 | search_cve |
| 参数 | `{"cve_id": "CVE-YYYY-NNNNN"}` |
| 数据源 | NVD REST API v2.0（无需 API Key） |
| 缓存 | L1 内存 + L2 磁盘7天 + L3 永久(knowledge_base/cve/) |
| 限流 | 5 次/30 秒，每次渗透最多 10 次 |
| 离线兜底 | 失败返回 error，不中断 Agent |
