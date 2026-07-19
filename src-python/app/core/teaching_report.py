from __future__ import annotations

from typing import Any


def build_teaching_report(data: dict[str, Any]) -> dict[str, Any]:
    """Build a fact-first teaching view from the persisted task snapshot.

    This intentionally uses observable actions and evidence references.  It
    never serializes model chain-of-thought or treats a model statement as a
    finding.
    """
    actions = [item for item in data.get("actions_taken", []) if isinstance(item, dict)]
    findings = [item for item in data.get("findings", []) if isinstance(item, dict)]
    vulnerabilities = [item for item in data.get("vulnerabilities", []) if isinstance(item, dict)]
    failures = [
        {
            "time": item.get("time", ""),
            "tool": item.get("tool", ""),
            "failure_type": item.get("failure_type", "") or "unknown",
            "reason": item.get("error", "") or item.get("result", ""),
            "next_change": item.get("next_step", "先补充前置条件或选择语义等价路径"),
        }
        for item in actions
        if str(item.get("status", "")).lower() in {"failed", "timeout", "error"} or item.get("error")
    ]
    path = [
        {
            "step": index,
            "time": item.get("time", ""),
            "tool": item.get("tool", ""),
            "purpose": item.get("purpose", "") or item.get("choice_reason", ""),
            "result": item.get("result", ""),
            "status": item.get("status", ""),
            "evidence_ref": item.get("evidence_id", item.get("id", "")),
        }
        for index, item in enumerate(actions, 1)
        if str(item.get("action_type", "")).lower() in {"recon", "exploit", "verify", "post"}
    ]
    facts = [
        {"kind": "observation", "text": f"发现 {item.get('ip', item.get('target', '?'))}:{item.get('port', '?')} / {item.get('service', '?')}", "source": "tool-output"}
        for item in findings
    ]
    facts.extend(
        {"kind": "verified-finding", "text": str(item.get("name", "未命名发现")), "source": item.get("evidence", "state.vulnerabilities")}
        for item in vulnerabilities
    )
    defense = [
        {"priority": "P0", "action": "修复或隔离已验证入口", "verification": "重新执行对应 Evidence Rule 并保留负面对照"},
        {"priority": "P1", "action": "收紧服务暴露和凭据策略", "verification": "复查端口、认证和配置证据"},
        {"priority": "P2", "action": "将检测信号纳入监控", "verification": "用同一时间线确认日志、告警和复测结果"},
    ]
    return {
        "facts": facts,
        "inferences": [
            "推断必须引用至少一个事实或证据，不等同于漏洞已验证。",
            "没有会话不代表没有风险；没有证据也不代表目标阴性。",
        ],
        "attack_path": path,
        "failure_path": failures,
        "defense_view": defense,
        "coverage": {
            "findings": len(findings),
            "vulnerabilities": len(vulnerabilities),
            "actions": len(actions),
            "unresolved_surfaces": sum(
                1 for item in data.get("attack_surfaces", [])
                if isinstance(item, dict) and str(item.get("status", "")).lower() not in {"exploited", "verified", "exhausted", "blocked"}
            ),
        },
    }
