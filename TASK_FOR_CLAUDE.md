# SDIT 渗透测试漏洞利用率修复任务

## 目标
修复 Metasploitable2 靶机漏洞利用率低的问题，目标是 100% 利用率。

## 当前状态 (R21)
- 已成功利用: 2个 (bindshell 1524, MySQL 3306)
- 已验证凭据: 1个 (PostgreSQL 5432)
- 未成功利用: vsftpd, distccd, UnrealIRCd, Samba, VNC, rlogin, Tomcat

## 需要修复的文件

### 1. direct_exploits.py
路径: src-python/app/services/pentest_agent/direct_exploits.py

当前只有 bindshell/vsftpd/MySQL/PostgreSQL 的直接利用。
需要添加:
- distccd (3632): 使用 DIST00000001 协议头发送命令
- UnrealIRCd (6667/6697): 使用 AB 前缀触发后门
- Samba (139/445): 使用 smbclient 注入命令
- rlogin/rsh (512/513/514): 直接 rsh 命令执行
- VNC (5900): 检测无认证访问

### 2. success_judge.py
路径: src-python/app/services/pentest_agent/success_judge.py

需要添加对新 exploit 的成功检测逻辑。

### 3. agent.py simple_exploits 列表
路径: src-python/app/services/pentest_agent/agent.py (约5070行)

当前 simple_exploits 只有 6 项，需要扩展到覆盖所有攻击面。
注意 lambda 闭包问题。

## 待完成
1. 验证 direct_exploits.py 能正确生成所有 exploit 任务
2. 修复 lambda 闭包问题
3. 加强 done gate
4. 同步到 Kali 运行测试
5. 迭代修复直到 100%
