# P8 Curated Exploit Lab — B 路线（自进化方向）

> **方向调整**: 抛弃硬编码 PoC 库（含 AES key 字典 / gadget 表），改为提供
> **代码运行环境 + 通用积木库**，让 LLM 自己写 Python PoC，失败 traceback 回灌
> 给 LLM 下一轮修正。这才是"自进化"应有的形态。

---

## 设计

### 1. python_exploit 工具

LLM 调用入口:
```
tool: python_exploit
args: JSON {"code": "<python source>", "timeout": 60, "label": "shiro try1"}
```

或裸代码（不含 JSON 包裹时自动 fallback）:
```
args: "from exploit_lib import emit, success; emit(success('hello'))"
```

实现位置: `src-python/app/services/pentest_agent/python_exploit.py`

特性:
- **子进程隔离** — 不污染 agent 主进程, 即便代码崩溃/死循环也不卡 agent
- **超时强杀** — 跨平台进程组终止 (Linux killpg / Windows taskkill /T)
- **结果协议** — `emit()` 输出 `__EXPLOIT_RESULT__ <json>` 行被解析为正式结果
- **失败诊断回路** — 失败时 stderr 头部追加到 result.result, LLM 下一轮看到 traceback 自己改
- **exploit_lib 自动可用** — sys.modules 注入, LLM 直接 `from exploit_lib import *`
- **输出限长** — stdout/stderr 各 200KB 截断, 不会爆 LLM 上下文

### 2. exploit_lib 通用积木

实现位置: `src-python/app/services/pentest_agent/exploit_lib/__init__.py`

**零漏洞特定知识** — 不存任何 CVE / AES key / gadget 字典. 只提供:

| 类别 | helper |
|------|--------|
| 网络 | `lhost()`, `tcp_open()`, `port_open()` |
| HTTP | `http_get()`, `http_post()`, `http_put()`, `http_request()` 返回 dict |
| 编码 | `base64_encode/decode`, `hex_encode/decode`, `url_encode` |
| AES | `aes_cbc_encrypt/decrypt`, `aes_cbc_b64`, `aes_ecb_encrypt` (薄封装 pycryptodome) |
| Java | `find_jar`, `ysoserial_payload(gadget, cmd)`, `ysoserial_gadgets()`, `marshalsec_ldap_refserver` |
| 子进程 | `run(cmd)`, `run_capture(cmd)` |
| 结果 | `emit(result)`, `success(evidence, **extra)`, `failure(reason, **extra)` |
| 文件 | `tmpfile`, `write_bytes`, `read_bytes` |
| 索引 | `help_index()` — 一次返回所有 helper 签名 + 说明 |

LLM 第一次用时可调 `help_index()` 拿到能力清单, 之后凭记忆/经验组合.

### 3. 失败诊断回路（关键自进化机制）

```
Round N: LLM 写 PoC → python_exploit → 子进程崩溃 NameError
                                          ↓
                              executor 把 stderr 拼到 result
                                          ↓
Round N+1 prompt 看到 traceback → LLM 改代码再提交
                                          ↓
                              成功 → P4 把成功 PoC 沉淀到 draft skill
                                          ↓
              下次同类目标: P3 向量检索拉回这个 skill, LLM 改下 target 直接用
```

### 4. 与 P6/P7 协同

- **P7 Protocol Adapter** 解决"协议层不会说"问题 (redis/mongo/jmx 协议)
- **P8 python_exploit** 解决"应用层 PoC 不会写"问题 (Shiro/Fastjson/Struts2 等 HTTP 层)
- **P6 ExploitRetry + Critic** 是元能力, 同时帮 P7/P8 失败时换策略

例: 打 Shiro 1.2.4 的典型流程
1. LLM 用 `lookup_msf_module` / `search_exploit` 查到这是 RememberMe 反序列化
2. LLM 提交 python_exploit code:
   - http_get 探测 rememberMe Cookie 响应
   - 在线 search 拿到候选 AES key（不写死 key 字典）
   - 调 `ysoserial_payload('CommonsCollections5', cmd)`
   - 调 `aes_cbc_b64()` 加密
   - 提交 Cookie, 判断 Set-Cookie 信号
   - emit(success/failure)
3. 若失败 traceback 含 'pycryptodome 未安装', LLM 下一轮改 gadget 或调 `run(['pip', 'install', 'pycryptodome'])`
4. 成功后 draft skill 沉淀, 下次打 Shiro 直接用

### 5. 安全约束

- `python_exploit` 标记 `risk=critical`, 走 agent 的高风险确认流
- 子进程默认 PATH 与主进程一致 (不限制), 但 timeout 强制 ≤ 600s
- stdout/stderr 严格限长, 不让代码刷屏吃 token
- runner 模板用临时文件, exec 完即删

### 6. 验证

`tests/test_p8_python_exploit.py` 23 个单测全过:
- exploit_lib 通用积木 (lhost/AES/tcp_open/base64) 主进程行为
- python_exploit 子进程隔离 (emit / 超时 / 异常 / env 注入 / HTTP)
- Executor 集成 (注册 / dispatch / 失败 stderr 回灌)

### 7. 不做的事

- ❌ 不内置 CVE 字典 (LLM 用 search_cve / search_exploit 查)
- ❌ 不内置 AES key 字典 (LLM 用 online_search 查或弱口令爆破)
- ❌ 不预写 PoC 模板 (LLM 写, 失败 traceback 帮它改, 成功进 skill 库)
- ❌ 不限制 helper 可调用的标准库 (Python 完整能力)

这才是真正的自进化: **环境提供能力, LLM 提供策略, 失败回路驱动改进, 成功结果沉淀复用**.
