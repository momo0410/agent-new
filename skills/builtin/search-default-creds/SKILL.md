---
name: search-default-creds
description: 联网查设备/软件默认密码。扫到路由器/IoT/打印机/数据库等设备时调用 lookup_default_creds 查默认凭据。
domain: penetration-testing
subdomain: reconnaissance
tags:
  - online-search
  - default-credentials
  - weak-password
  - cirt
version: '2.0'
---

# search-default-creds

## Principle
路由器、IoT 设备、打印机、数据库等服务常以出厂默认凭据运行。nmap 扫到这些服务后，**查默认密码表**比盲目爆破更高效——默认密码只有几组，试一次就知道。

本工具内置高频产品的默认凭据数据集（tomcat/mysql/postgres/vnc/cisco/router 等），离线秒回；未命中时尝试 cirt.net 在线查询。

## Detection Fingerprint
**应当调用 lookup_default_creds 的场景**：
- nmap 扫到特定设备/软件（路由器 web 管理界面、Tomcat Manager、VNC、打印机等）
- 服务版本已知有默认凭据问题（如 Tomcat 6.x 默认 tomcat/tomcat）
- 需要 hydra 爆破前的"快赢"尝试（默认密码试一次就几秒）

**反例（不要调用）**：
- 已知服务有明确 exploit-skill（如 vsftpd 后门）—— 直接用 exploit，不必试密码
- 目标是互联网公网服务且明确禁止爆破 —— 跳过

## Workflow

### 方法 A：按产品名查询
```json
{
  "tool": "lookup_default_creds",
  "args": {"product": "tomcat"}
}
```
返回：凭据列表（username/password/source）。内置库覆盖的产品秒回。

### 方法 B：拿到凭据后验证
```json
{"tool": "curl", "args": "-u tomcat:tomcat http://{target}:8080/manager/html"}
```
对 HTTP 服务用 curl 验证；对 SSH/Telnet 用对应客户端；对数据库用 mysql/psql。

### 支持的产品（内置库）
tomcat / mysql / postgres / vnc / ssh / ftp / telnet / cisco / router / smb / redis / mongodb / web / printer / ipmi

模糊匹配：输入 "apache tomcat" 也能命中 "tomcat"。

## Failure Modes
| 现象 | 原因 | 下一步 |
|---|---|---|
| 返回空凭据列表 | 内置库和在线均未命中 | 用 hydra 爆破常见弱口令表 |
| 返回 fallback_advice | 产品名太生僻 | 访问 cirt.net 手动查 |
| 默认密码试了都不对 | 设备已改密码 | 转 hydra 爆破或找其他入口 |

## Generalization
这是"默认配置利用"类技能。识别套路：
1. **设备类目标优先试默认密码** —— 路由器/IoT/打印机改密码率低
2. **数据库服务试空密码** —— MySQL/Redis/MongoDB 常默认无认证
3. **试完默认转爆破** —— 默认密码是快赢，不行再 hydra

**同类决策**：有 CVE → search_cve；有服务版本 → search_exploit；要用 MSF → lookup_msf_module；试默认密码 → lookup_default_creds。

## Key Concepts
| 字段 | 值 |
|---|---|
| 工具名 | lookup_default_creds |
| 参数 | `{"product": "tomcat"}` |
| 数据源 | 内置数据集 + cirt.net |
| 内置覆盖 | 15+ 高频产品，模糊匹配 |
| 离线可用 | 内置库不依赖网络 |
