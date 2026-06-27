# BATCH_20260627 全量测试报告

> 日期: 2026-06-27
> 执行端: Kali root@192.168.136.143
> 靶机总数: 44 (Docker)
> Agent 版本: P39 (b0de871)

---

## 总览

| 指标 | 值 |
|------|-----|
| 总靶机 | 44 |
| 已测试 | 21 |
| Skipped (镜像拉取失败) | 23 |
| **有 exploited** | **14/21 (66%)** |
| 零 exploited | 7 |
| 总 exploited 面 | 27 |
| 总 verified 面 | 33 |
| 总 credentials | 26 |

---

## 成功利用 (14 靶机)

| 靶机 | exploited | verified | total | creds | 耗时 | 覆盖率 |
|------|-----------|----------|-------|-------|------|--------|
| activemq | 5 | 2 | 7 | 2 | 324s | 71% |
| solr811 | 4 | 1 | 5 | 2 | 397s | 80% |
| solr820 | 4 | 0 | 4 | 1 | 407s | 100% |
| pikachu | 2 | 1 | 3 | 1 | 232s | 66% |
| tomcat85 | 2 | 0 | 2 | 1 | 188s | 100% |
| couchdb | 2 | 0 | 2 | 2 | 233s | 100% |
| linuxsrv02 | 1 | 3 | 4 | 5 | 375s | 25% |
| dvwa | 1 | 0 | 1 | 1 | 154s | 100% |
| httpd2449 | 1 | 0 | 1 | 1 | 140s | 100% |
| httpd2450 | 1 | 0 | 1 | 1 | 149s | 100% |
| struts2-2525 | 1 | 0 | 1 | 1 | 132s | 100% |
| redis4 | 1 | 0 | 1 | 1 | 177s | 100% |
| thinkphp5023 | 1 | 0 | 1 | 1 | 158s | 100% |
| linuxsrv01 | 1 | 0 | 1 | 1 | 197s | 100% |

## 零利用 (7 靶机)

| 靶机 | verified | 原因 | 改进方向 |
|------|----------|------|---------|
| tomcat7 | 25 | 25 个 verified 但 success_judge 未标记 exploited | 调整 success_judge 判定规则 |
| linuxsrv03 | 1 | 服务未就绪 | 增加就绪等待 |
| juice-shop | 0 | LLM 决策被丢弃 (P39 修复后单独测试 exploited=1) | P39 think 提取已生效 |
| nexus | 0 | 容器未就绪 (nmap 0 hosts up) | 就绪检查已修复 (530s) |
| jenkins | 0 | 容器未就绪 (nmap 0 hosts up) | 同上 |
| flask111 | 0 | 容器未就绪 (nmap 0 hosts up) | 同上 |
| shiro124 | 0 | 批处理崩溃后重启，结果为 0 | 已重启 |

## Skipped (23 靶机)

全部因 Docker 镜像拉取失败 (pull_failed)。Kali 网络可能无法访问 Docker Hub。

1 个因端口冲突 (php-xxe: port 80 already allocated)。

---

## P39 改动效果

| 改动 | 效果验证 |
|------|---------|
| `_extract_tools_from_think()` | juice-shop Round 2 成功提取 `['whatweb', 'hydra', 'curl']` |
| FC 空 tasks 回退 | 解决了 FC 返回空 plan 阻塞后续解析的问题 |
| `_plan_web()` 扩展 | planner 现在生成 whatweb + nikto + ffuf 三个候选 |
| web phase 零证据阈值 2→4 | 给 web 测试更多轮次执行时间 |
| 就绪检查 75s→530s | 解决 Java 服务 (nexus/jenkins) 启动慢导致的 0 hosts up |

### juice-shop P39 前后对比

| 指标 | P38 前 | P39 后 (单独测试) |
|------|--------|-------------------|
| exploited | 0 | **1** |
| credentials | 0 | **1** |
| LLM 决策提取 | 0 个 | **3 个** (whatweb/hydra/curl) |
| 服务识别 | ppp? (未知) | OWASP Juice Shop |

---

## 对比 R26 进度

| 指标 | R26 (P37) | BATCH_20260627 (P39) |
|------|-----------|---------------------|
| 已测试靶机 | 1 (MSF2) | **21** (Docker) |
| exploited 率 | 41% (13/32) | **66% (14/21)** |
| 总 exploited 面 | 13 | **27** |
| 总 credentials | 11 | **26** |

---

## 待解决

1. **23 个靶机镜像拉取失败** — 需要在 Kali 上预拉取所有镜像
2. **tomcat7 success_judge** — 25 个 verified 但 0 exploited，需调整判定
3. **LLM 不会主动说"用 sqlmap"** — think 提取只能提取 LLM 明确提到的工具
4. **Web 深度测试** — nikto/ffuf 已加入 planner，但 LLM 还没学会链式利用
