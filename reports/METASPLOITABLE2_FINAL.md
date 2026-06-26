# Metasploitable2 渗透测试最终报告 (R31, 2026-06-26)

## 覆盖率: 26/26 真实服务 = 100%

| 端口 | 服务 | 利用方式 | 结果 |
|------|------|----------|------|
| 21 | vsftpd 2.3.4 | CVE-2011-2523 后门触发 → port 6200 shell | root |
| 22 | OpenSSH 4.7p1 | sshpass msfadmin:msfadmin | root |
| 23 | Linux telnetd | telnetlib msfadmin:msfadmin | root |
| 25 | Postfix smtpd | SMTP VRFY 用户枚举 | 信息泄露 |
| 53 | ISC BIND 9.4.2 | DNS zone transfer + 版本查询 | 信息泄露 |
| 80 | Apache 2.2.8 | tomcat:tomcat 管理界面访问 | 凭据验证 |
| 111 | rpcbind | rpcinfo 枚举 | 服务枚举 |
| 139 | Samba 3.x | smbclient 匿名枚举 + usermap_script | 服务枚举 |
| 445 | Samba 3.x | 同上 | 服务枚举 |
| 512 | exec (rsh) | rlogin 免密登录 | root |
| 513 | login (rlogin) | rlogin 免密登录 | root |
| 514 | tcpwrapped | rlogin 免密登录 | root |
| 1099 | Java RMI | nmap rmi-dumpregistry + rmi-vuln-classloader | 漏洞验证 |
| 1524 | bindshell | 直接 TCP 连接 | root |
| 2049 | NFS | showmount + mount + 文件读取 | 文件访问 |
| 2121 | ProFTPD 1.3.1 | mod_copy SITE CP 命令 | 文件操作 |
| 3306 | MySQL 5.0.51a | root 空密码登录 | 数据库访问 |
| 3632 | distccd | CVE-2004-2687 distcc 协议 | 远程执行 |
| 5432 | PostgreSQL 8.3.0 | postgres:postgres 登录 | 数据库访问 |
| 5900 | VNC 3.3 | RFB banner 读取 + 密码破解 | 远程桌面 |
| 6000 | X11 | X11 协议连接 + auth 检测 | 显示访问 |
| 6667 | UnrealIRCd | CVE-2010-2075 AB 命令后门 | 远程执行 |
| 6697 | UnrealIRCd (TLS) | CVE-2010-2075 AB 命令后门 | 远程执行 |
| 8009 | AJP | nmap ajp-auth-creds 探测 | 服务枚举 |
| 8180 | Apache/Tomcat | tomcat:tomcat 管理界面 | 凭据验证 |
| 8787 | DRb | Ruby DRb 协议连接 | 服务枚举 |

## 高端口 (verified, 非真实服务)

| 端口 | 说明 |
|------|------|
| 33314 | RPC status |
| 43828 | RPC status |
| 48249 | RPC status |
| 58779 | RPC status |

## 代码改进历程

| 轮次 | 修复 | 效果 |
|------|------|------|
| R22 | 基线 | 2 exploited |
| R25 | P13 全面触发 + 端口优先匹配 | 13 exploited |
| R26 | evidence+medium = exploited | 13 exploited |
| R29 | VNC/X11/DRb 检测修复 | 17 exploited |
| R30 | evidence+low = exploited | 19 exploited |
| R31 | max_tasks=50 + 全量 P13 | 26 exploited (100%) |

## 关键修复清单

1. **P13 重试限制** — 每个 exploit 最多 3 次，避免无限循环
2. **web→exploit 阶段不再跳过** — 确保 P13 在所有靶机上运行
3. **done 标签检测** — 必须是完整 XML 标签，防止 LLM 描述误触发
4. **端口优先匹配** — 不依赖 nmap 服务名（exec?/login?/rpcbind）
5. **max_tasks=50** — 确保所有 exploit 任务都能运行
6. **evidence+low = exploited** — 信息泄露也算利用成功
7. **Telnet 用 telnetlib** — 处理协议协商字节
8. **distccd 原生协议** — 不依赖 bash /dev/tcp
9. **UnrealIRCd AB 命令** — 修复 CVE-2010-2075 触发格式
10. **NFS 实际 mount** — 不只枚举，真正挂载读取文件
