"""
FailureSkillGenerator — 从渗透测试的失败尝试中生成 'failure-*' SKILL.md

设计动机:
    现有 SkillGenerator 只对成功路径生成 skill，失败经验丢失。但实际渗透中
    "什么不该做 / 什么徒劳" 与 "什么有效" 同样重要。本模块从 state 中抽取
    重复失败、达到上限的尝试，生成防踩坑 skill。

输出文件名: failure-<service>-<reason>.md（写入 skills/learned/draft/）

只生成失败信号显著（≥3 次同类失败 或 surface 标记为 exhausted/failed）的条目，
避免产生噪音。
"""
from __future__ import annotations

import os
import re
import textwrap
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from .skill_generator import _sanitize_name


def _extract_failure_signals(state) -> list[dict]:
    """从 state 中提取失败信号。

    返回结构: [
        {
            "service": "ftp",
            "tool": "hydra",
            "failure_reason": "auth-failed",
            "occurrences": 5,
            "evidence_samples": ["<excerpt>", ...],
            "target_fingerprint": "192.168.1.10:21/ftp",
        }, ...
    ]
    """
    data = getattr(state, "data", state) or {}
    actions = data.get("actions_taken", []) or []
    surfaces = data.get("attack_surfaces", []) or []

    # 聚合相同 (service, tool, failure_reason) 的失败动作
    bucket: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for action in actions:
        if not isinstance(action, dict):
            continue
        status = str(action.get("status", "")).lower()
        if status not in ("failed", "error", "timeout"):
            continue
        service = str(action.get("service") or action.get("target_service") or "unknown").lower()
        tool = str(action.get("tool") or "unknown").lower()
        failure_reason = (
            str(action.get("failure_reason") or action.get("failure_type") or "unknown").lower()
        )
        bucket[(service, tool, failure_reason)].append(action)

    signals: list[dict] = []
    for (service, tool, reason), bucket_actions in bucket.items():
        if len(bucket_actions) < 3:
            continue
        # 收集证据样本
        samples = []
        for a in bucket_actions[:3]:
            evidence = a.get("evidence") or a.get("output") or a.get("error") or ""
            if isinstance(evidence, (list, tuple)):
                evidence = " | ".join(str(x) for x in evidence)
            samples.append(str(evidence)[:200])
        fingerprints = {
            f"{a.get('target', '?')}:{a.get('port', '?')}/{a.get('service', '?')}"
            for a in bucket_actions
        }
        signals.append({
            "service": service,
            "tool": tool,
            "failure_reason": reason,
            "occurrences": len(bucket_actions),
            "evidence_samples": samples,
            "target_fingerprint": " | ".join(sorted(fingerprints))[:200],
        })

    # 补充: 来自 attack_surfaces 的 exhausted 标记
    for surf in surfaces:
        if not isinstance(surf, dict):
            continue
        status = str(surf.get("status", "")).lower()
        if status not in ("exhausted", "failed", "unreachable"):
            continue
        service = str(surf.get("service") or "unknown").lower()
        signals.append({
            "service": service,
            "tool": "multiple",
            "failure_reason": f"surface-{status}",
            "occurrences": int(surf.get("attempts", 0) or 0),
            "evidence_samples": [str(surf.get("notes", ""))[:200]],
            "target_fingerprint": f"{surf.get('ip','?')}:{surf.get('port','?')}/{service}",
        })

    return signals


def _render_failure_skill_md(signal: dict, targets: list[str], llm_insight: str = "") -> str:
    """生成 failure-*.md 内容（V2 五段式，但 Workflow 改为 'Avoidance Strategy'）"""
    service = signal["service"]
    tool = signal["tool"]
    reason = signal["failure_reason"]
    occ = signal["occurrences"]
    evidence_block = "\n".join(f"- `{e}`" for e in signal["evidence_samples"][:3] if e)
    skill_name = _sanitize_name(f"failure-{service}-{tool}-{reason}")
    now = datetime.now(timezone.utc).isoformat()

    body = textwrap.dedent(
        f"""\
        ---
        name: {skill_name}
        description: 在 {service} 上使用 {tool} 因 "{reason}" 重复失败 {occ} 次的避坑经验
        domain: penetration-testing
        subdomain: failure-mode
        tags: [{service}, {tool}, failure, {reason}]
        severity: info
        version: '2.0'
        generated_at: {now}
        ---

        ## Principle

        本次渗透在 {service} 服务上使用 {tool} 工具时，反复触发 "{reason}" 失败模式。
        该模式表明：在此类目标指纹下，{tool} 对 {service} 的当前配置/版本/凭据空间无效。

        指纹: `{signal['target_fingerprint']}`

        ## Detection Fingerprint

        当遇到以下条件时，应**跳过** `{tool}` 对 `{service}` 的常规尝试：

        1. 目标服务 = {service}
        2. 已尝试 `{tool}` 工具 ≥ 3 次，全部返回 `{reason}`
        3. 错误证据样本:
        {evidence_block or '- (无具体证据)'}

        反例（仍可尝试 {tool} 的场景）:
        - 服务版本与本次不同（重新指纹后再判定）
        - 已获得高价值凭据，可换登录路径

        ## Workflow

        ### Avoidance Strategy（不要做什么）

        - **避免**: 继续用 `{tool}` 攻击 `{service}` 的同一指纹/同一凭据池
        - **检测条件**: actions_taken 中本服务 + 本工具失败计数 >= 3

        ### Alternative（建议尝试）

        - 切换工具：见 SERVICE_EXPLOIT_TEMPLATES 中 {service} 的其他模板
        - 转换攻击面：考虑同主机其他端口/服务
        - 补充情报：先做更细的版本指纹或 NSE 脚本扫描

        ## Failure Modes

        | 现象 | 原因 | 下一步 |
        |------|------|--------|
        | {tool} 输出 "{reason}" | 凭据/payload/版本不匹配 | 切换工具或重新指纹 |
        | 重试仍失败 | 配置层防御（黑名单/限速） | 放弃该攻击面或换主机 |

        ## Generalization

        - 服务类型: {service}（覆盖各版本变体）
        - 失败工具: {tool}
        - 失败签名: `{reason}`
        - 推广规则: 任何 service={service} 且 tool={tool} 的任务，若历史失败计数 ≥ 3
          且失败原因匹配本签名，应在 Planner 阶段降权或剔除

        ## Key Concepts

        - **速查**: 见到 {service}+{tool}+"{reason}" 组合 → 跳过，换策略
        - **覆盖目标**: {', '.join(targets[:3]) if targets else '(未记录)'}
        {('- **LLM 反思**: ' + llm_insight[:200]) if llm_insight else ''}
        """
    )
    return body


class FailureSkillGenerator:
    """从渗透 state 提取失败信号，生成 failure-*.md 防踩坑 skill"""

    def __init__(self, skills_root: str, output_subdir: str = "learned/draft"):
        self.skills_root = skills_root
        self.output_dir = os.path.join(skills_root, *output_subdir.split("/"))

    def generate_from_state(self, state) -> list[str]:
        """提取 state 的失败信号，写入 failure-*.md，返回文件路径列表"""
        os.makedirs(self.output_dir, exist_ok=True)
        data = getattr(state, "data", state) or {}
        targets = data.get("targets", []) or []

        signals = _extract_failure_signals(state)
        generated_paths: list[str] = []
        existing: set[str] = set(os.listdir(self.output_dir)) if os.path.isdir(self.output_dir) else set()

        for signal in signals:
            skill_name = _sanitize_name(
                f"failure-{signal['service']}-{signal['tool']}-{signal['failure_reason']}"
            )
            filename = f"{skill_name}.md"
            if filename in existing:
                # 已存在跳过；P2 阶段可改为追加 occurrences 计数
                continue
            content = _render_failure_skill_md(signal, targets)
            file_path = os.path.join(self.output_dir, filename)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                generated_paths.append(file_path)
            except OSError:
                continue
        return generated_paths


__all__ = ["FailureSkillGenerator"]
