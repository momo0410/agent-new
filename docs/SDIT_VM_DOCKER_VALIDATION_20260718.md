# SDIT Kali VM / Docker 实机验证记录

## Git 同步证据

- GitHub：`https://github.com/momo0410/agent-new.git`
- `master` 验证提交：`4738bb719054e689991afc0649cb5923fcdc7be3`
- Kali 干净验证目录：`/root/agent-new-sync-220b8bf`
- Kali 工作区 HEAD：`4738bb719054e689991afc0649cb5923fcdc7be3`
- Kali 验证目录工作树：clean

## Docker 目标验证

- 镜像：`bkimminich/juice-shop:latest`
- 容器：`sdit-juice-shop`
- 容器地址：`172.17.0.2`
- 暴露端口：`3000/tcp`
- HTTP 探活：`HTTP_STATUS=200`
- 项目 Executor + Nmap：识别 `3000/tcp open`，并从 Nmap 未命名服务的 HTTP 指纹归一为 `http (HTTP response detected)`。
- 项目 State/Finalize/Phase：产生 HTTP finding、攻击面记录，阶段由 `init` 推进到 `recon`。

## VM 靶机发现验证

目标：`192.168.136.137`（Metasploitable，本地 VMware 网段）

项目 Executor 通过 Nmap `--top-ports 100` 发现 18 个开放服务，包含：

`21/ftp`、`22/ssh`、`23/telnet`、`25/smtp`、`53/domain`、`80/http`、`111/rpcbind`、`139/netbios-ssn`、`445/netbios-ssn`、`2049/rpcbind`、`2121/ftp`、`3306/mysql`、`5432/postgresql`、`5900/vnc`、`6000/X11`、`8009/ajp13`。

项目 State/Finalize/Planner 验证：

- findings：18
- attack surfaces：19
- `init -> recon` 阶段推进成功
- recon 候选任务：8 组
- 高价值 Web、远程接入、RPC/NFS、数据库、图形服务面均进入候选计划

## 发现并修复的问题

Docker Juice Shop 在 Nmap service probe 中返回 `ppp?`，但响应内容实际为 HTTP。旧解析逻辑直接保留未知服务名，导致 Web 攻击面识别依赖后续工具，发现结果不稳定。

修复内容：

- `Executor.parse_port_services()` 对 Nmap `SF-Port...` 指纹读取 HTTP 响应特征。
- 对 `?`、`unknown`、`ppp?`、`tcpwrapped` 等未知服务，在同端口确认 HTTP 响应时归一为 `http (HTTP response detected)`。
- 新增单元测试并在 Kali 真实 Docker 目标上回归验证。

## Kali 验证结果

```text
Backend full suite: 341 passed, 7 skipped
Control-plane tests: 12 passed
Benchmark: 1 passed, 1 benchmark sample
Frontend tests: 9 passed
Frontend build: passed
npm audit (all dependencies): 0 vulnerabilities
npm audit --omit=dev --audit-level=high: 0 vulnerabilities
```

## 当前运行状态

- `sdit-juice-shop` 保持运行，供后续回归测试使用。
- 现有 `/root/agent-new` 保留原有实验数据与脏工作树；验证使用独立干净目录，避免覆盖历史靶场报告。

