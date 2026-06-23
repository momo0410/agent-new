---
name: search-msf-module
description: 联网查 Metasploit 模块文档（Rapid7）。要用 MSF 模块但不确定参数/payload 时调用 lookup_msf_module。
domain: penetration-testing
subdomain: reconnaissance
tags:
  - online-search
  - metasploit
  - msfconsole
  - rapid7
version: '2.0'
---

# search-msf-module

## Principle
Metasploit 有数千个模块，每个模块的必填参数、可用 payload、rank 各不相同。当 LLM 决定用某个 MSF 模块但不确定其参数或 payload 时，**查模块文档**比凭记忆猜参数更可靠（错误的参数会导致 msfconsole 报错并卡住流程）。

本工具查 Rapid7 模块数据库（https://www.rapid7.com/db/modules/），同时内置高频模块的离线知识库，离线时也能秒回关键信息。

## Detection Fingerprint
**应当调用 lookup_msf_module 的场景**：
- 决定使用某个 MSF 模块（如 `exploit/unix/ftp/vsftpd_234_backdoor`），但不确定必填参数
- search_cve / search_exploit 返回的 CVE 关联了 MSF 模块，想确认模块用法
- msfconsole 报错 "Unknown payload" 或 "Missing required option"，需要查正确参数

**反例（不要调用）**：
- 本地 exploit-skill 的 Workflow 章节已给出完整 msfconsole 命令 —— 直接用
- 还没确定用哪个模块 —— 先 search_exploit 找候选

## Workflow

### 方法 A：按模块全名查询
```json
{
  "tool": "lookup_msf_module",
  "args": {"module_name": "exploit/unix/ftp/vsftpd_234_backdoor"}
}
```
返回：描述、rank、必填参数、可用 payload、参考链接。高频模块走离线知识库秒回。

### 方法 B：msfconsole 直接查（离线兜底）
如果联网失败，返回结果中会带 `manual_command`，可直接执行：
```bash
msfconsole -q -x 'use exploit/unix/ftp/vsftpd_234_backdoor; info; exit -y'
```

### 模块名格式
必须是完整路径：`类型/平台/.../模块名`，如：
- `exploit/unix/ftp/vsftpd_234_backdoor`
- `exploit/multi/samba/usermap_script`
- `auxiliary/scanner/smb/smb_version`

## Failure Modes
| 现象 | 原因 | 下一步 |
|---|---|---|
| 返回 manual_command | 在线失败且不在离线库 | 执行返回的 msfconsole info 命令 |
| 返回"模块名为空" | 模块名缺失 | 检查 args 格式 |
| 模块名不含 / | 格式不完整 | 补全为 类型/路径/模块名 |

## Generalization
这是"工具用法查询"类检索。识别套路：
1. **先查再打** —— 用 MSF 模块前确认参数，避免报错卡住
2. **离线库覆盖高频** —— vsftpd/samba/unrealircd 等已内置，无需联网
3. **info 命令兜底** —— 任何模块都能 `msfconsole -x 'use X; info'` 查

## Key Concepts
| 字段 | 值 |
|---|---|
| 工具名 | lookup_msf_module |
| 参数 | `{"module_name": "exploit/unix/ftp/vsftpd_234_backdoor"}` |
| 数据源 | Rapid7 db + 内置离线知识库 |
| 离线库 | 覆盖 vsftpd/samba/unrealircd/distcc/postgres/php-cgi 等高频模块 |
