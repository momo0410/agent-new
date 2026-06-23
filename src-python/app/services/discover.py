"""多靶机发现服务 — 把"找出可渗透的目标"和"渗透单个目标"解耦。

设计要点
========
- 单一职责: 只回答"现在有哪些可达靶机"，不做任何渗透动作
- 输出 Target 列表，每条含 ip / source / hints（端口提示、容器元数据等）
- 不假设任何凭据、不假设特定靶机类型（与 v2.0 项目定位一致: 通用 Linux）
- 所有发现都在 Kali 攻击机上做（通过 KaliExecutor），避免污染本机环境

发现来源
========
1. 网段扫描 (nmap -sn): 找出 Kali 同网段所有存活 IP
2. Docker 容器枚举 (docker ps): 找出 Kali 上跑的容器靶机及其端口映射

调用方
======
- v3.0 多靶机编排层: 列出 -> 逐个调 agent.py 的 run()
- 本期暂作工具库，由 FastAPI 路由 / CLI 入口手动调用

不做的事
========
- 不做端口扫描细节（agent.py 自带 nmap 流程）
- 不做指纹识别（同上）
- 不做凭据猜测（隔离原则: 发现 != 渗透）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# 仅类型注解时引入，避免循环依赖
from .pentest_agent.kali_executor import KaliExecutor


@dataclass
class Target:
    """一个待渗透的目标。"""
    ip: str
    source: str                # "network" | "docker"
    hostname: str = ""
    hints: dict[str, Any] = field(default_factory=dict)
    # hints 可包含:
    #   container_name: str        (source=docker)
    #   image: str                 (source=docker)
    #   host_port: int             (source=docker, Kali 主机上映射的端口)
    #   container_port: int        (source=docker, 容器内端口)


class TargetDiscovery:
    """多靶机发现器。所有发现操作都通过 KaliExecutor 在攻击机上执行。"""

    # 默认排除项: Kali 自身 + 默认网关。调用方可追加更多。
    DEFAULT_EXCLUDES: set[str] = set()

    def __init__(self, executor: KaliExecutor, exclude_ips: Optional[set[str]] = None):
        self.executor = executor
        self.exclude_ips = set(exclude_ips or set()) | self.DEFAULT_EXCLUDES

    # ── 公共入口 ────────────────────────────────────────────────

    def discover_all(self) -> list[Target]:
        """运行所有发现来源，合并去重后返回。"""
        targets: list[Target] = []
        targets.extend(self.discover_docker())
        targets.extend(self.discover_network())
        return self._dedupe(targets)

    # ── 网段扫描 ────────────────────────────────────────────────

    def discover_network(self) -> list[Target]:
        """扫描 Kali 所在网段，发现所有存活主机（排除 Kali 自身和网关）。"""
        kali_ip = self.executor.kali_host

        # 自动取 Kali 所在的 /24 网段
        r = self.executor.run_on_kali(
            f"ip -o -f inet addr show | grep '{kali_ip}' | awk '{{print $4}}'",
            timeout=5,
        )
        subnet = (r.get("stdout") or "").strip()
        if not subnet:
            base = ".".join(kali_ip.split(".")[:3]) + ".0/24"
            subnet = base

        # 自动排除默认网关
        gw_r = self.executor.run_on_kali(
            "ip route | grep default | awk '{print $3}' | head -1", timeout=5
        )
        gateway = (gw_r.get("stdout") or "").strip()
        excludes = set(self.exclude_ips)
        excludes.add(kali_ip)
        if gateway:
            excludes.add(gateway)

        # nmap -sn 仅做存活探测，不做端口扫描（端口扫描留给 agent.py）
        r = self.executor.run_on_kali(
            f"nmap -sn {subnet} -oG - 2>/dev/null", timeout=60
        )
        targets: list[Target] = []
        for line in (r.get("stdout") or "").split("\n"):
            m = re.search(r"Host:\s+(\d+\.\d+\.\d+\.\d+)\s+\(([^)]*)\)", line)
            if not m:
                continue
            ip = m.group(1)
            hostname = m.group(2) or ""
            if ip in excludes:
                continue
            targets.append(Target(ip=ip, source="network", hostname=hostname))
        return targets

    # ── Docker 容器靶机 ───────────────────────────────────────────

    def discover_docker(self) -> list[Target]:
        """枚举 Kali 上运行的 Docker 容器及其端口映射。

        典型场景: 在 Kali 本机跑 DVWA / WebGoat / Metasploitable3 容器做练习。
        """
        r = self.executor.run_on_kali(
            "docker ps --format '{{.Names}}|{{.Image}}|{{.Ports}}' 2>/dev/null", timeout=10
        )
        targets: list[Target] = []
        for line in (r.get("stdout") or "").strip().split("\n"):
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            name, image, ports = parts[0].strip(), parts[1].strip(), parts[2].strip()

            # 解析 "0.0.0.0:8080->80/tcp" 形式的端口映射
            port_matches = re.findall(r"0\.0\.0\.0:(\d+)->(\d+)/tcp", ports)
            if not port_matches:
                # 没有端口映射的容器无法从外部访问，跳过
                continue
            for host_port, container_port in port_matches:
                targets.append(Target(
                    # Docker 容器通过 127.0.0.1 访问（避免 iptables/nmap filtered 问题）
                    ip="127.0.0.1",
                    source="docker",
                    hostname=name,
                    hints={
                        "container_name": name,
                        "image": image,
                        "host_port": int(host_port),
                        "container_port": int(container_port),
                    },
                ))
        return targets

    # ── 内部 ────────────────────────────────────────────────────

    @staticmethod
    def _dedupe(targets: list[Target]) -> list[Target]:
        """同一 (ip, source, host_port) 组合只保留一次，docker 优先。"""
        seen: set[tuple] = set()
        result: list[Target] = []
        # docker 在前（discover_all 已保证顺序）
        for t in targets:
            key = (t.ip, t.source, t.hints.get("host_port"))
            if key in seen:
                continue
            seen.add(key)
            result.append(t)
        return result
