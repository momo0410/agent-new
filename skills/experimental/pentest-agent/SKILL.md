---
name: pentest-agent
description: 全自动渗透测试智能体。接收目标IP/域名，自动完成信息收集→Web攻击→漏洞利用→后渗透→横向移动全流程。当用户要求渗透测试、安全评估、漏洞扫描时使用。
---

# 渗透测试 Agent

## 工作流

```
init → recon → web → exploit → post → lateral → done
  │        │       │        │         │        │
  └─→ 写入state.json ← 每个阶段追加发现 ←───────────┘
```

## 启动

```python
from app.services.pentest_agent import pentest_agent_run

pentest_agent_run("192.168.1.100", llm_fn=your_llm, dry_run=True)
```

## 阶段说明

### 1. recon - 信息收集
- 技能: `skills/experimental/pentest_recon.json`
- 工具: nmap, rustscan, amass, whatweb
- 触发: phase=init 或 phase=recon
- 产出: 端口+服务列表, 子域名, Web指纹

### 2. web - Web 攻击
- 技能: `skills/experimental/pentest_web.json`
- 工具: nuclei, ffuf, dirb, sqlmap
- 触发: 发现 HTTP 端口 (80/443/8080)
- 产出: 漏洞列表, 目录发现, SQL注入结果

### 3. exploit - 漏洞利用
- 技能: `skills/experimental/pentest_exploit.json`
- 工具: searchsploit, hydra, msfconsole
- 触发: phase=web 完成 + 发现漏洞
- 产出: 凭据, Shell会话

### 4. post - 后渗透
- 技能: `skills/experimental/pentest_post.json`
- 工具: crackmapexec, impacket-secretsdump
- 触发: 获取凭据
- 产出: 更多凭据, 敏感信息, 权限提升

### 5. lateral - 横向移动
- 技能: `skills/experimental/pentest_lateral.json`
- 工具: cme-smb, cme-winrm, impacket-psexec
- 触发: 有凭据 + 多个目标
- 产出: 新增可控主机

## 调用格式

Agent 每轮输出:
```
<tool>工具名</tool>
<args>参数</args>
```

终止:
```
<done>所有路径已尝试完毕</done>
```

## 文件

| 文件 | 说明 |
|------|------|
| `state.json` | 状态文件，Agent 读写的唯一持久化入口 |
| `report.md` | 完成后生成的渗透测试报告 |
| `tools.toml` | 工具注册表，声明所有可用工具 |
| `executor.py` | 工具执行器，CLI 封装层 |
| `agent.py` | 主循环，LLM 驱动决策 |
| `state.py` | 状态管理，JSON 读写 |
