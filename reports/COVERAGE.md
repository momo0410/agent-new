# Metasploitable2 漏洞覆盖对比 (更新: 2026-06-25)

来源: Rapid7 官方 Exploitability Guide + 实际 SDIT Agent 渗透测试 (5轮)

## 一、已成功利用 (8/20)

| # | 漏洞 | 端口 | CVE/类型 | 状态 | 轮次 |
|---|------|------|----------|------|------|
| 1 | bindshell ingreslock | 1524 | 后门 | ✅ root shell | R1 |
| 2 | rlogin/rsh .rhosts++ | 512-514 | 配置错误 | ✅ root | R1 |
| 3 | NFS / 全盘导出 | 2049 | 配置错误 | ✅ root | R1 |
| 4 | MySQL root 空密码 | 3306 | 弱口令 | ✅ 验证通过 | R5/P13 |
| 5 | PostgreSQL postgres 空密码 | 5432 | 弱口令 | ✅ 验证通过 | R5/P13 |
| 6 | Samba 匿名访问+用户枚举 | 139/445 | 配置错误 | ✅ | R2 |
| 7 | Java RMI 反序列化 | 1099 | CVE-2011-3556 | ✅ | R3 |
| 8 | Tomcat tomcat:tomcat | 8180 | 弱口令 | ✅ | R2 |
| 9 | SMTP VRFY 用户枚举 | 25 | 信息泄露 | ✅ | R1 |

## 二、P13 自动尝试但失败的漏洞 (5个)

P13 钩子尝试自动执行 msfconsole 利用，但因 **缺少 LHOST 参数** 失败：

| # | 漏洞 | 端口 | 失败原因 | 修复状态 |
|---|------|------|----------|----------|
| 1 | vsftpd 2.3.4 后门 | 21 | Msf::OptionValidateError: LHOST | ✅ 已加动态 LHOST |
| 2 | distccd RCE | 3632 | PAYLOAD 格式错误 + 缺 LHOST | ✅ 已修复 |
| 3 | UnrealIRCd 后门 | 6667 | Msf::OptionValidateError: LHOST | ✅ 已加动态 LHOST |
| 4 | UnrealIRCd 后门 | 6697 | Msf::OptionValidateError: LHOST | ✅ 已加动态 LHOST |
| 5 | ProFTPD mod_copy | 2121 | 未触发（无对应 vulnerability 记录） | 待验证 |

## 三、未利用的漏洞 (7个)

| # | 漏洞 | 端口 | 类型 | 原因 |
|---|------|------|------|------|
| 1 | Samba usermap_script RCE | 139 | CVE-2007-2447 | MSF 尝试未获 session |
| 2 | Samba symlink traversal | 139/445 | 配置错误 | 未尝试 auxiliary |
| 3 | VNC 密码破解 | 5900 | 弱口令(password) | hydra 字典太大超时 |
| 4 | SSH 暴力破解 | 22 | 弱口令 | hydra 字典太大超时 |
| 5 | Telnet 弱口令 | 23 | msfadmin:msfadmin | hydra 字典太大超时 |
| 6 | PHP-CGI 参数注入 | 80 | CVE-2012-1823 | 未测试 |
| 7 | Web 应用漏洞 | 80 | Mutillidae/DVWA/TWiki | 未做 Web 应用渗透 |

## 四、P10-P13 新功能

| 功能 | 说明 | 状态 |
|------|------|------|
| P10: exploit 失败自动联网检索 | exploit 失败时自动搜索替代 MSF 模块 | ✅ |
| P11: 自动凭据采集 | 检测到 shell 后自动注入 shadow/passwd 采集指令 | ✅ |
| P12: 未利用漏洞注入 | 检测到高价值漏洞未利用时注入利用建议（每3轮重新注入） | ✅ |
| P13: 简单漏洞直接利用 | 绕过 LLM 直接执行 msfconsole/shell 利用 | ⚠️ 初版缺 LHOST，已修复 |

## 五、覆盖率

- 服务端口覆盖: 9/14 可利用端口 (64%)
- CVE 漏洞覆盖: 1/5 已知CVE (20%) — Java RMI 已验证，其余因 LHOST 失败
- 弱口令覆盖: 2/9 弱口令 (22%) — MySQL/PostgreSQL 已验证
- Web 应用覆盖: 0/6 应用 (0%)
- 后门覆盖: 1/3 后门 (33%) — 仅 1524 bindshell
- 配置错误覆盖: 3/4 配置错误 (75%)

**总体漏洞覆盖率: 约 40%** (8/20 可利用向量，P13 修复后预期可提升至 70%)

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
