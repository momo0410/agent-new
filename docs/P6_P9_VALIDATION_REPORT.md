# SDIT 自进化渗透 Agent 当前验证报告（P6-P9 / R8-R9B）

生成时间：2026-06-24
项目路径：`D:\agent-new` / Kali `/root/agent-new`
GitHub：`momo0410/agent-new`
当前 HEAD：`cf39f77 fix(P9): prioritize high-value auto-intel and raise online budget`

---

## 1. 项目目标确认

SDIT 自进化渗透 Agent 的目标不是做一个只列风险的扫描器，而是做一个能完成以下闭环的工程化渗透 Agent：

1. 自动发现端口和服务。
2. 自动补全漏洞情报、MSF 模块、默认凭据和 PoC 信息。
3. 自动选择攻击路径和 payload。
4. 真实执行 exploit，并用 shell/session/命令输出验证结果。
5. 失败后根据 evidence / stderr / traceback 自我修正。
6. 成功后沉淀经验，下一次遇到相似环境自动复用。
7. 对多攻击面目标，不能拿到一个 shell 就结束，要尽量覆盖高价值攻击面。

一句话：目标是**会查资料、会试错、会总结、会迁移的自动渗透测试 Agent**，不是硬编码靶机脚本。

---

## 2. 已完成代码阶段

### P6：ExploitRetryStrategy + ActionCritic

已完成并推送：`16cdb4d`

能力：
- msfconsole 失败时给出 payload 轮换建议。
- 连续失败时触发 critic 诊断并注入下一轮上下文。
- 对 LHOST/LPORT 冲突做自动修正。

R8 实测证据：
- 日志出现：`msfconsole 已自动设置 payload=cmd/unix/interact`
- 日志出现：`msfconsole 已自动设置 LPORT=...，避免 4444 端口冲突`

问题：
- 目前只对 `failed/error/timeout` 动作注入重试建议；某些 msfconsole 返回 `rc=0` 但输出里含 `OptionValidateError`，会被误记为 completed，导致 P6 未触发。

---

### P7：Protocol Adapters

已完成并推送：`cbba47d`

新增：
- `redis_eval`
- `mongo_eval`
- `jmx_invoke`

能力：
- Redis RESP 协议不用再让 LLM 用 `nc` 乱发 bash 命令。
- MongoDB/JMX 有协议适配入口。

R8 实测证据：
- R8-redis 中 `redis_eval` 已被调用。
- R8-redis summary：`sessions_count=1`。

问题：
- LLM 曾调用 `redis_eval {action: list_dbs}`，但 RedisAdapter 没有这个 action。
- 说明工具 description 还不够强，需要把 Redis 可用 action 白名单渲染得更明显，或者给 RedisAdapter 增加 alias：`list_dbs -> info/keys` 的安全降级。

---

### P8：python_exploit + exploit_lib（B 路线）

已完成并推送：`4b8c652`

重要方向调整：
- 放弃硬编码 PoC / AES key 字典 / gadget 表。
- 改为提供 `python_exploit` 子进程隔离执行环境 + `exploit_lib` 通用积木。
- LLM 自己写 PoC，失败后根据 stderr/traceback 修改。

能力：
- `python_exploit`：执行 LLM 提交的 Python PoC，超时强杀，stdout/stderr 结构化回传。
- `exploit_lib`：HTTP、AES、base64、ysoserial、lhost、tcp_open、emit/success/failure 等通用 helper。

测试：
- P8 23 个单测通过。

R8 实测问题：
- LLM 没有主动调用 `python_exploit`。
- 原因：system prompt 和 tool description 对“Shiro/Fastjson/Struts2 这类复杂 HTTP/JAVA 漏洞应使用 python_exploit”提示不足。
- P9 已开始修复这个方向，但还未完成端到端验证。

---

### P6.1：Hydra 字典治理

已完成并推送：`18248ff`

原因：
- R8 中 LLM 选择 hydra + rockyou/john 大字典，导致 SSH/Telnet 爆破卡住几十分钟甚至理论上可到数十天。

修复：
- 禁用 `rockyou.txt` / `rockyou.txt.gz`。
- 默认 fallback 改为 `/usr/share/wordlists/metasploit/unix_passwords.txt`。
- hydra 默认 `-t 16 -w 5 -f`。
- 大字典阈值从 100MB 降到 5MB。
- hydra timeout cap 改为 1200s。
- planner 模板里的 rockyou 已移除。

测试：
- 新增 `tests/test_p6_1_brute_dict.py`，20 个单测通过。

---

### P9：Auto-Intel + 高价值攻击面完成门

已完成并推送：
- `8ecf0f6 feat(P9): auto-intel enrichment + high-value exploit completion gate`
- `cf39f77 fix(P9): prioritize high-value auto-intel and raise online budget`

原因：
- R8-MSF2 中虽然 `OnlineSearchService` 已启用，但只搜索原始 nmap 服务串，例如 `ftp         vsftpd 2.3.4`，CVE 命中率差。
- auto-intel 只调用 `search_exploit`，不自动 follow-up `lookup_msf_module` / `lookup_default_creds`。
- LLM 拿到一个 root shell 后倾向提前转 post/done，没有继续覆盖 vsftpd/distccd/unreal/samba 等高价值攻击面。

修复：
- 服务指纹规范化：
  - `ftp         vsftpd 2.3.4` -> `vsftpd 2.3.4`
  - `ssh         OpenSSH 4.7p1 Debian 8ubuntu1 (protocol 2.0)` -> `OpenSSH 4.7p1 Debian 8ubuntu1`
  - `http        Apache httpd 2.2.8 ((Ubuntu) DAV/2)` -> `Apache httpd 2.2.8`
- auto-intel 自动补：
  - `search_exploit`
  - `lookup_msf_module`
  - `lookup_default_creds`
- service_intel 渲染 MSF payload/options/recommended_msfconsole_args。
- 高价值攻击面只有 `exploited/exhausted` 才算闭环；`verified` 不再等于“已打透”。
- exploit 阶段即使已有 session，也不会自动进入 post，除非高价值攻击面闭环或连续无证据。
- OnlineSearch 预算从 10 提到 50。
- auto-intel 按攻击面分数排序，优先处理 bindshell/vsftpd/distccd/unreal/tomcat 等高价值服务。

测试：
- 新增 `tests/test_p9_auto_intel_and_completion.py`，8 个单测通过。
- 本地选择性全套：P0-P9 共 `170 passed`。
- Kali 上 P9/P6.1 测试通过。

---

## 3. 实测结果

### R8-MSF2

路径：Kali `/root/agent-new/reports/R8/20260624_111557_R8-MSF2/`

结果摘要：

| 指标 | 数值 |
|---|---:|
| 开放端口 | 30 |
| 漏洞记录 | 6 |
| sessions | 4 |
| credentials | 36 |
| actions | 53 |
| 最终阶段 | done |
| 用时 | 1990.2s |

主要识别漏洞：
- vsftpd 2.3.4 后门（21/tcp）critical
- Metasploitable root shell bindshell（1524/tcp）critical
- distccd RCE（3632/tcp）high
- UnrealIRCd 后门（6667/tcp）critical
- UnrealIRCd 后门（6697/tcp）critical
- 已验证可利用路径：1524/tcp

实际确认：
- 1524/tcp 直接 nc 获得 root shell：`root@metasploitable:/#`
- VNC/若干服务有 session 记录，但 session 元数据不完整，需要后续修正 session schema。

没有完全打透的原因：
1. LLM 在 R8 阶段没有充分使用联网检索工具。
2. msfconsole 对 vsftpd/distccd/unreal 的利用多数只做到“尝试/验证”，未形成稳定 session。
3. 拿到 1524 root shell 后，Agent 过早进入 post/done，未强制继续打其他高价值攻击面。
4. hydra 大字典拖慢流程。

对应修复：P6.1 + P9 已完成。

---

### R8-redis

路径：Kali `/root/agent-new/reports/R8/20260624_114907_R8-redis/`

结果摘要：

| 指标 | 数值 |
|---|---:|
| findings | 13 |
| vulns | 0 |
| sessions | 1 |
| actions | 55 |
| final_phase | done |
| 用时 | 516.4s |

现象：
- `redis_eval` 被调用，说明 P7 工具已出现在 LLM 可用工具中。
- 但 LLM 调用过错误 action：`list_dbs`，RedisAdapter 不支持。

问题：
- RedisAdapter action 列表需要更强提示或增加 alias。
- Redis 利用链还没完整打到写 SSH key / slaveof / Lua 等路径。

---

### R8-shiro

路径：Kali `/root/agent-new/reports/R8/20260624_115744_R8-shiro/`

结果摘要：

| 指标 | 数值 |
|---|---:|
| findings | 13 |
| vulns | 1 |
| sessions | 1 |
| credentials | 6 |
| actions | 60 |
| final_phase | done |
| 用时 | 593.3s |

识别到：
- 1 个中危弱认证/可复用凭据类漏洞。

问题：
- LLM 未调用 P8 `python_exploit` 编写 Shiro rememberMe PoC。
- 说明 P8 工具虽然可用，但触发策略仍不足。
- 后续需要在 web/java 漏洞场景中强制/半强制候选任务引入 `python_exploit`。

---

### R8-fastjson

状态：中断。

原因：
- 用户要求停止当前测试，未完整跑完。

---

### R9 / R9B-MSF2

目的：验证 P9 修复后是否能先把 MSF2 更完整打透。

R9：
- 第一次 R9 在 P9.1 修复前启动。
- 发现 auto-intel 预算 10 不够，服务多时过早耗尽。
- 已停止。

R9B：
- 使用 HEAD `cf39f77`。
- 用户要求停止测试时处于 recon 阶段。
- 路径：Kali `/root/agent-new/reports/R9B_MSF2_FULL/20260624_124302_R9B-MSF2/`

已观察到的改进：
- OnlineSearch 预算已显示为 50。
- auto-intel 已按规范化关键词注入：
  - `metasploitable root shell`
  - `vsftpd 2.3.4`
  - `openssh 4.7p1 debian 8ubuntu1`
  - `apache httpd 2.2.8`
  - `proftpd 1.3.1`
  - `distccd distccd v1`
  - `postgresql db 8.3.0 - 8.3.7`
  - `vnc`
- R9B state：
  - phase: recon
  - findings: 30
  - vulnerabilities: 5
  - sessions: 1
  - actions: 9
  - service_intel: 8

新发现问题：
- vsftpd msfconsole：
  - LLM 选择了 `PAYLOAD cmd/unix/interact`，方向正确。
  - 但 executor 自动补了 `LPORT`，导致 msf 报：`OptionValidateError ... LHOST`。
  - 说明 msfconsole adapter 对 interact/bind 类 payload 不应该补 LHOST/LPORT。
- UnrealIRCd：
  - LLM 选择了 `PAYLOAD cmd/unix/interact`，不适合该模块。
  - msfconsole 报：`Unknown command: run/exploit`。
  - 说明 recommended_msfconsole_args 不能统一写 `run`，要根据模块/payload 选择 `exploit -j` 或 `run`，并且需要兼容当前 metasploit 命令语法。

R9B 已按用户要求停止。

---

## 4. 当前主要问题清单

### 问题 1：msfconsole 参数重写不区分 payload 类型

表现：
- `cmd/unix/interact` 不需要 LHOST/LPORT。
- executor 仍自动补 LPORT，MSF 又要求 LHOST，导致 `OptionValidateError`。

影响：
- vsftpd 2.3.4 后门仍未稳定拿到 session。

建议修复：
- `_rewrite_msfconsole_args()` 中：
  - 如果 payload 含 `interact` 或 `bind`，不要自动补 LHOST/LPORT。
  - 只有 reverse payload 才补 LHOST/LPORT。
  - 对 vsftpd 优先走直接触发 + nc 6200 fallback，而不是完全依赖 msfconsole。

---

### 问题 2：MSF 推荐命令的 `run/exploit` 兼容性不足

表现：
- UnrealIRCd 使用 `run` / `exploit` 时出现 unknown command。

建议修复：
- 不要在通用推荐里统一写 `run`。
- 对 msfconsole 命令统一生成：
  - `use module; set ...; check; exploit -j; sleep 8; sessions -l; exit -y`
- 如果 payload 是 interact/bind，则用 foreground `run` 或模块特定命令。
- executor 需要把 msfconsole stdout 中的 `Unknown command` / `OptionValidateError` 识别为失败，而不是 rc=0 completed。

---

### 问题 3：verified 被算作阶段闭环仍不够严

P9 已修一部分：verified 高价值攻击面现在仍会 pending。

但还需要补：
- `verified` 应按服务分级：
  - RCE/backdoor 类：只有 `exploited` 或明确无法利用 `exhausted` 才闭环。
  - Web 信息泄露类：`verified` 可以闭环。
  - 登录爆破类：`exhausted` 才闭环。

---

### 问题 4：session 结构不完整

表现：
- R8-MSF2 有 4 个 session，但 3 个 session 的 `session_id/transport/banner` 为空。

影响：
- 报告无法明确说明每个 session 来自哪个 exploit。
- 后渗透阶段不容易复用正确 session。

建议修复：
- `upsert_session()` 必须要求：
  - session_id
  - source tool/action id
  - surface_id
  - port
  - connect command
  - privilege evidence
- 空 session 不应计入 `sessions_count`。

---

### 问题 5：P8 python_exploit 仍未被主动调用

表现：
- R8-shiro 未调用 `python_exploit`。

建议修复：
- planner 为以下服务生成 python_exploit 候选任务：
  - shiro
  - fastjson
  - struts2
  - spring
  - jenkins
  - tomcat manager war upload
- web/java 阶段如果 search_exploit 有 PoC 但无现成工具，应优先给 `python_exploit` 任务。

---

### 问题 6：RedisAdapter action 名称对 LLM 不友好

表现：
- LLM 调用 `redis_eval action=list_dbs`。

建议修复：
- 增加安全 alias：
  - `list_dbs` -> `info` + `keys *` 或明确返回 Redis 无数据库列表概念。
  - `list_keys` -> `keys`。
  - `dump_info` -> `info`。
- tool description 列出 action 白名单和示例。

---

## 5. 已验证有效的改动

1. **服务情报自动检索方向已纠正**
   - R9B 中已看到 auto-intel 用规范化关键词检索。
   - 例如 `vsftpd 2.3.4` 成功注入 `cves=1 msf=1 creds=yes`。

2. **OnlineSearch 预算不足已修复**
   - 从 10 提高到 50。
   - auto-intel 从“原始顺序”改为“按攻击面分数排序”。

3. **hydra 大字典问题已修复**
   - planner 不再建议 rockyou。
   - executor 对 rockyou 有黑名单拦截。

4. **MSF2 不会拿到一个 root shell 就直接判定完成**
   - P9 已改 exploit 阶段退出条件。

---

## 6. 建议下一步优先级

### P9.1：修 msfconsole adapter（最高优先级）

目标：让 vsftpd/distccd/unreal/samba 这几个 MSF2 核心 RCE 面能稳定拿 session。

具体：
1. 识别 payload 类型：interact / bind / reverse。
2. 只有 reverse payload 自动补 LHOST/LPORT。
3. 对 msfconsole 输出中的 `OptionValidateError`、`Unknown command`、`Exploit completed, but no session` 标为 failed。
4. vsftpd 增加 direct fallback：触发 FTP 后门后直接 `nc target 6200`。
5. 增加单测。

### P9.2：MSF2 后渗透 checklist

目标：拿到 root shell 后自动完成：
- `id; whoami; uname -a`
- `/etc/passwd`, `/etc/shadow`
- service config：tomcat/mysql/postgres/samba/vnc
- 凭据复用验证
- 其他高价值端口继续 exploit

### P9.3：python_exploit 候选任务生成

目标：让 Shiro/Fastjson/Struts2/Spring/Jenkins 这类复杂 exploit 真正走 P8。

### P9.4：RedisAdapter alias

目标：降低 LLM action 拼错概率，提高 Redis 靶机打透率。

---

## 7. 结论

当前项目已经从 P0-P5 的“自进化闭环原型”推进到 P6-P9 的“工程化渗透 Agent”阶段：

已具备：
- 多阶段自动规划。
- 历史经验注入。
- 在线情报自动补全。
- 协议适配器。
- LLM 自写 PoC 执行环境。
- payload 重试和 critic 框架。
- hydra 字典治理。

但距离“MSF2 完全打透并稳定迁移到所有靶机”还差几个关键工程点：
- msfconsole adapter 仍不够稳。
- verified/exploited 的证据语义仍需更严格。
- P8 python_exploit 还没有被 planner 主动触发。
- session 数据结构要补完整。

当前最应该继续做的是：**P9.1 msfconsole adapter 稳定化**。
这一步完成后，再重跑单靶机 MSF2，目标应该是：
- sessions >= 5
- 至少覆盖 1524 / vsftpd / distccd / unreal / samba 中 4 类以上
- 不再出现 `OptionValidateError` / `Unknown command` 被误判 completed
