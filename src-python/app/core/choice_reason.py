"""Convert internal model output into short, observable decision explanations."""

from __future__ import annotations

import json
import re
from typing import Any

_PRIVATE_BLOCK = re.compile(
    r"<\s*(?:think|thinking|thought|analysis|reasoning)\b[^>]*>.*?<\s*/\s*(?:think|thinking|thought|analysis|reasoning)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_TOOL_BLOCK = re.compile(r"<\s*(?:tool|function|command|secret|private)\b[^>]*>.*?<\s*/\s*(?:tool|function|command|secret|private)\s*>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"</?[^>]{1,80}>")
_SPACE = re.compile(r"\s+")


def _structured_reason(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("choice_reason", "reason", "purpose", "decision", "summary"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        return ""
    text = str(value or "").strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            return _structured_reason(json.loads(text))
        except (TypeError, ValueError, json.JSONDecodeError):
            return ""
    return text


def summarize_choice_reason(value: Any, purpose: str = "", *, max_length: int = 240) -> str:
    """Return a bounded reason based on observable purpose, never private blocks."""
    raw = _structured_reason(value)
    had_private = bool(_PRIVATE_BLOCK.search(raw))
    cleaned = _PRIVATE_BLOCK.sub(" ", raw)
    cleaned = _TOOL_BLOCK.sub(" ", cleaned)
    cleaned = _TAG.sub(" ", cleaned)
    cleaned = _SPACE.sub(" ", cleaned).strip(" -:;\n\t")
    if had_private and not cleaned:
        cleaned = str(purpose or "").strip()
    if not cleaned:
        cleaned = str(purpose or "").strip()
    if not cleaned:
        cleaned = "基于当前目标、范围和可观察证据选择动作"
    return cleaned[: max(40, int(max_length))].rstrip()


__all__ = ["summarize_choice_reason"]
