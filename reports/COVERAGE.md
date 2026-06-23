# Metasploitable2 漏洞覆盖对比

来源: Rapid7 官方 Exploitability Guide + 实际扫描

## 一、已成功利用 (12/20)

| # | 漏洞 | 端口 | CVE/类型 | 状态 | 证据 |
|---|------|------|----------|------|------|
| 1 | vsftpd 2.3.4 后门 | 21 | CVE-2011-2523 | ✅ root | uid=0, shadow hash |
| 2 | bindshell ingreslock | 1524 | 后门 | ✅ root | uid=0, shadow hash |
| 3 | rlogin/rsh .rhosts++ | 512-514 | 配置错误 | ✅ root | uid=0, shadow hash |
| 4 | NFS / 全盘导出 | 2049 | 配置错误 | ✅ root | shadow, passwd, ssh keys |
| 5 | MySQL root 空密码 | 3306 | 弱口令 | ✅ root | user(), version() |
| 6 | PostgreSQL postgres 空密码 | 5432 | 弱口令 | ✅ | pg_shadow hash |
| 7 | Telnet msfadmin:msfadmin | 23 | 弱口令 | ✅ | uid=1000, admin组 |
| 8 | Samba 匿名访问+用户枚举 | 139/445 | 配置错误 | ✅ | 34个用户, 共享列表 |
| 9 | Java RMI 反序列化 | 1099 | CVE-2011-3556 | ✅ | VULNERABLE |
| 10 | distcc 命令执行 | 3632 | CVE-2004-2687 | ✅ | VULNERABLE, CVSS 9.3 |
| 11 | Tomcat tomcat:tomcat | 8180 | 弱口令 | ✅ | Manager 访问 |
| 12 | SMTP VRFY 用户枚举 | 25 | 信息泄露 | ✅ | 全系统用户列表 |

## 二、未利用的漏洞 (8个)

| # | 漏洞 | 端口 | 类型 | 原因 |
|---|------|------|------|------|
| 1 | UnrealIRCd 后门 | 6667 | CVE-2010-2075 | exploit 未拿到 session，可能非 3.2.8.1 版本 |
| 2 | Samba usermap_script RCE | 139 | CVE-2007-2447 | 仅做了枚举，未执行 msf exploit |
| 3 | Samba symlink traversal | 139/445 | 配置错误 | 未尝试 auxiliary/admin/smb/samba_symlink_traversal |
| 4 | VNC 密码破解 | 5900 | 弱口令(password) | 仅验证了协议，未破解密码 |
| 5 | SSH 暴力破解 | 22 | 弱口令 | sshpass 未安装 |
| 6 | PHP-CGI 参数注入 | 80 | CVE-2012-1823 | 未测试 /phpinfo.php |
| 7 | Web 应用漏洞 | 80 | Mutillidae/DVWA/TWiki | 未做 Web 应用渗透 |
| 8 | ProFTPD 1.3.1 | 2121 | CVE-2015-3306 | 未测试 mod_copy |

## 三、弱口令覆盖

| 用户 | 密码 | 是否尝试 | 结果 |
|------|------|----------|------|
| msfadmin | msfadmin | ✅ | 成功 (telnet) |
| postgres | postgres | ✅ | 成功 |
| root | (空) | ✅ | 成功 (MySQL) |
| sys | batman | ❌ | 未尝试 |
| klog | 123456789 | ❌ | 未尝试 |
| service | service | ❌ | 未尝试 |
| user | user | ❌ | 未尝试 |
| admin | password | ❌ | 未尝试 (DVWA) |
| VNC | password | ❌ | 未破解 |

## 四、Web 应用 (完全未测)

| 应用 | URL | 漏洞类型 |
|------|-----|----------|
| Mutillidae | /mutillidae/ | SQLi, XSS, CSRF, 命令注入, 文件包含 |
| DVWA | /dvwa/ | SQLi, XSS, 文件上传, 命令注入 |
| phpMyAdmin | /phpMyAdmin/ | 弱口令, SQL执行 |
| TWiki | /tikiwiki/ | RCE, XSS |
| WebDAV | /dav/ | 文件上传, PUT方法 |
| phpinfo.php | /phpinfo.php | 信息泄露 |

## 五、覆盖率

- 服务端口覆盖: 12/14 可利用端口 (86%)
- CVE 漏洞覆盖: 3/5 已知CVE (60%)
- 弱口令覆盖: 4/9 弱口令 (44%)
- Web 应用覆盖: 0/6 应用 (0%)
- 后门覆盖: 2/3 后门 (67%)
- 配置错误覆盖: 3/4 配置错误 (75%)

**总体漏洞覆盖率: 约 60%** (12/20 可利用向量)
