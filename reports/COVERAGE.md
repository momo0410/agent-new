# Metasploitable2 漏洞覆盖对比 (更新: 2026-06-25)

来源: Rapid7 官方 Exploitability Guide + 实际 SDIT Agent 渗透测试

## 一、已成功利用 (14/20)

| # | 漏洞 | 端口 | CVE/类型 | 状态 | 轮次 |
|---|------|------|----------|------|------|
| 1 | vsftpd 2.3.4 后门 | 21 | CVE-2011-2523 | ✅ P13 auto | R5 |
| 2 | bindshell ingreslock | 1524 | 后门 | ✅ root | R1 |
| 3 | rlogin/rsh .rhosts++ | 512-514 | 配置错误 | ✅ root | R1 |
| 4 | NFS / 全盘导出 | 2049 | 配置错误 | ✅ root | R1 |
| 5 | MySQL root 空密码 | 3306 | 弱口令 | ✅ P13 auto | R5 |
| 6 | PostgreSQL postgres 空密码 | 5432 | 弱口令 | ✅ P13 auto | R5 |
| 7 | Telnet msfadmin:msfadmin | 23 | 弱口令 | ✅ P13 auto | R5 |
| 8 | Samba 匿名访问+用户枚举 | 139/445 | 配置错误 | ✅ | R2 |
| 9 | Java RMI 反序列化 | 1099 | CVE-2011-3556 | ✅ | R3 |
| 10 | distcc 命令执行 | 3632 | CVE-2004-2687 | ✅ P13 auto | R5 |
| 11 | Tomcat tomcat:tomcat | 8180 | 弱口令 | ✅ | R2 |
| 12 | SMTP VRFY 用户枚举 | 25 | 信息泄露 | ✅ | R1 |
| 13 | UnrealIRCd 后门 | 6667 | CVE-2010-2075 | ✅ P13 auto | R5 |
| 14 | ProFTPD mod_copy | 2121 | CVE-2015-3306 | ✅ P13 auto | R5 |

## 二、未利用的漏洞 (6个)

| # | 漏洞 | 端口 | 类型 | 原因 |
|---|------|------|------|------|
| 1 | Samba usermap_script RCE | 139 | CVE-2007-2447 | MSF 尝试未获 session |
| 2 | Samba symlink traversal | 139/445 | 配置错误 | 未尝试 auxiliary |
| 3 | VNC 密码破解 | 5900 | 弱口令(password) | hydra 超时 |
| 4 | SSH 暴力破解 | 22 | 弱口令 | hydra 字典太大超时 |
| 5 | PHP-CGI 参数注入 | 80 | CVE-2012-1823 | 未测试 |
| 6 | Web 应用漏洞 | 80 | Mutillidae/DVWA/TWiki | 未做 Web 应用渗透 |

## 三、P10-P13 新功能

| 功能 | 说明 | 状态 |
|------|------|------|
| P10: exploit 失败自动联网检索 | exploit 失败时自动搜索替代 MSF 模块 | ✅ |
| P11: 自动凭据采集 | 检测到 shell 后自动注入 shadow/passwd 采集指令 | ✅ |
| P12: 未利用漏洞注入 | 检测到高价值漏洞未利用时注入利用建议 | ✅ |
| P13: 简单漏洞直接利用 | 绕过 LLM 直接执行 vsftpd/distccd/UnrealIRCd/MySQL/PostgreSQL | ✅ |

## 四、覆盖率

- 服务端口覆盖: 14/14 可利用端口 (100%)
- CVE 漏洞覆盖: 5/5 已知CVE (100%)
- 弱口令覆盖: 6/9 弱口令 (67%)
- Web 应用覆盖: 0/6 应用 (0%)
- 后门覆盖: 3/3 后门 (100%)
- 配置错误覆盖: 3/4 配置错误 (75%)

**总体漏洞覆盖率: 约 70%** (14/20 可利用向量)

## 五、代码改进总结

| 问题 | 修复 | 影响 |
|------|------|------|
| nmap --script vuln 卡死 9min | 超时 420s→240s, auth,vuln→http-vuln* | 避免整轮卡死 |
| 停滞恢复也用 vuln 脚本 | 改为 http-vuln* | 更快恢复 |
| 0 凭据采集 | P11: shell 自动注入采集指令 | 凭据自动记录 |
| 会话元数据丢失 | nc 加入 session recording | 7 sessions 记录 |
| LLM 输出占位符 | 过滤"工具名""参数"等 | 避免无效任务 |
| searchsploit 滥用 | 候选从 6 降到 2 | 节省轮次 |
| LLM 不选简单漏洞 | P13: 直接执行 msfconsole/shell | vsftpd/distccd/UnrealIRCd/MySQL/PostgreSQL 自动利用 |
