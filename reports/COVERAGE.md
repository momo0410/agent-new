# Metasploitable2 漏洞覆盖对比 (更新: 2026-06-25)

来源: Rapid7 官方 Exploitability Guide + 实际 SDIT Agent 渗透测试 (5轮)

## 一、当前最新实测成功/有效验证 (R21, 2026-06-25)

| # | 攻击面 | 端口 | 类型 | 最新状态 | 证据 / 说明 |
|---|--------|------|------|----------|-------------|
| 1 | bindshell / root shell | 1524 | 后门 / 直接 root shell | ✅ exploited | `root@metasploitable:/#`，attack_surface `192.168.136.137|1524` 为 exploited |
| 2 | MySQL root 空密码/弱凭据 | 3306 | 弱口令 | ✅ exploited | `user() version()` 返回 `root@192.168.136.137 / 5.0.51a`，attack_surface `192.168.136.137|3306` 为 exploited |
| 3 | PostgreSQL postgres 凭据 | 5432 | 弱口令 | ✅ credential_valid | credentials 中已有 `postgres` 和 `postgres/postgres`，能返回 PostgreSQL 8.3.1 版本；surface 仍为 verified，待进一步做 DB RCE/文件读取 |

**严格按 exploited surface 计：2 个（1524、3306）。**
**把 credential_valid 也算有效验证：3 个。**

## 二、已识别但未真正利用成功的高价值攻击面

| 漏洞 / 攻击面 | 端口 | 当前状态 | 主要问题 |
|---|---:|---|---|
| vsftpd 2.3.4 后门 | 21 | verified / 未拿 shell | direct Python/base64 仍报错；MSF 多次 no session；6200 状态需要独立验证 |
| distccd RCE | 3632 | verified / no session | MSF reverse payload 不兼容，`/dev/tcp` 不可用；需要 direct/protocol 级验证 |
| UnrealIRCd 后门 | 6667/6697 | verified / no session | MSF 多次 no session；需要非 MSF 直接协议触发或更换 payload 策略 |
| Samba usermap_script | 139/445 | verified / no session | MSF 尝试未获 session，需 direct smb/rpc 验证或 Samba 专用策略 |
| Tomcat Manager | 8180 | verified / 401 | 已确认需认证，默认凭据未稳定验证 |
| VNC/SSH/Telnet 弱口令 | 5900/22/23 | 未成功 | Hydra 预算治理已做，但还未形成有效凭据验证闭环 |
| Web 应用漏洞 | 80 | 未覆盖 | Mutillidae/DVWA/TWiki/phpMyAdmin 等 Web 面仍未系统枚举利用 |

## 四、P10-P13 新功能

| 功能 | 说明 | 状态 |
|------|------|------|
| P10: exploit 失败自动联网检索 | exploit 失败时自动搜索替代 MSF 模块 | ✅ |
| P11: 自动凭据采集 | 检测到 shell 后自动注入 shadow/passwd 采集指令 | ✅ |
| P12: 未利用漏洞注入 | 检测到高价值漏洞未利用时注入利用建议（每3轮重新注入） | ✅ |
| P13: 简单漏洞直接利用 | 绕过 LLM 直接执行 msfconsole/shell 利用 | ⚠️ 初版缺 LHOST，已修复 |

## 五、覆盖率

- R21 最新实测：31 findings, 7 vulnerabilities, 6 sessions, 2 credentials
- 严格 exploited surface: 2 个（1524 bindshell, 3306 MySQL）
- credential_valid: 1 个（5432 PostgreSQL）
- 若按 Rapid7/MSF2 约 20 个可利用向量估算：严格成功约 10%，含凭据验证约 15%
- 当前主要瓶颈：vsftpd/distccd/UnrealIRCd/Samba/Tomcat/VNC/SSH/Telnet/Web 应用仍未稳定 exploited

## 六、代码改进总结

| 问题 | 修复 | 影响 |
|------|------|------|
| nmap --script vuln 卡死 9min | 超时 420s→240s, auth,vuln→http-vuln* | 避免整轮卡死 |
| 停滞恢复也用 vuln 脚本 | 改为 http-vuln* | 更快恢复 |
| 0 凭据采集 | P11: shell 自动注入采集指令 | 凭据自动记录 |
| 会话元数据丢失 | nc 加入 session recording | 7 sessions 记录 |
| LLM 输出占位符 | 过滤"工具名""参数"等 | 避免无效任务 |
| searchsploit 滥用 | 候选从 6 降到 2 | 节省轮次 |
| LLM 不选简单漏洞 | P13: 直接执行 msfconsole/shell | 需再跑一轮验证 |
| P13 msfconsole 缺 LHOST | 动态 socket 检测 Kali IP + 所有命令加 set LHOST | 已推送，待验证 |
| P14 msfconsole 参数追加到 exit 后 | 移除中间 `run; exit` / `exploit; exit`，统一重排为 LPORT/payload → exploit → exit -y | 已修复并加单测 |
| P15 msfconsole reverse/session 模块无会话时挂起 | `SDIT_MSF_STALL_TIMEOUT` 默认 90s，阻塞即失败并进入下一轮诊断/重试 | 已修复，待 R12 验证 |
| 在线情报被候选任务/历史动作挤到后面 | service_intel 配额 500→1200，提前到候选任务之前，并加“必须参考情报修正 exploit 命令”提示 | 已修复，待 R12 观察模型是否引用 |
| msfconsole 超时只杀 shell wrapper | POSIX 使用 setsid + killpg 强杀整组，避免 ruby/msfconsole 孤儿进程残留 | 已修复，待 R13 验证 |
| LLM 给的 msfconsole args 缺 LHOST | executor._rewrite_msfconsole_args 自动按环境/路由探测补 set LHOST | 已修复，待 R14 验证 |
| LLM 在 init 用 shell 包装 masscan 导致无结构化 findings | init 阶段自动将 shell+scanner 改写为 nmap 工具调用，保留 parser 能力 | 已修复，待 R16 验证 |
| Direct exploit 有输出但没有写入 credential/exploited 状态 | 新增 success_judge，并接入 P13 direct-first；PostgreSQL version 写 credential，root shell 写 host_compromise | 已修复，待 R20 验证 |
