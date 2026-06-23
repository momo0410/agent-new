"""NVD (National Vulnerability Database) REST API v2.0 客户端

数据源: https://services.nvd.nist.gov/rest/json/cves/2.0
- 无需 API Key（无 key 时限速 5 次/30 秒，够用）
- 覆盖全部 CVE 详情：描述、CVSS、影响版本、参考链接

设计：
  - 用 stdlib urllib，零额外依赖
  - 限流：滑窗记录最近调用时间，超过 5 次/30 秒时主动 sleep
  - 重试：超时 / 429 / 5xx 时指数退避重试 2 次
  - 离线友好：任何异常都返回 None，不中断 Agent 流程
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

NVD_API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_NVD_USER_AGENT = "SDIT-PentestAgent/1.0 (security research; +https://nvd.nist.gov)"


class NvdClient:
    """NVD REST API v2.0 客户端（同步、带限流与重试）。"""

    def __init__(
        self,
        api_key: str = "",
        timeout: int = 15,
        max_retries: int = 2,
        rate_window_seconds: int = 30,
        rate_max_calls: int = 5,
    ):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self._call_timestamps: list[float] = []
        self._rate_window = rate_window_seconds
        self._rate_max = rate_max_calls

    # ── 公开方法 ──────────────────────────────────────────
    def get_cve(self, cve_id: str) -> Optional[dict[str, Any]]:
        """查询单个 CVE 详情。

        Returns:
            标准化后的 CVE 字典，含 id / description / cvss / affected / references。
            查询失败或无结果时返回 None。
        """
        cve_id = self._normalize_cve(cve_id)
        if not cve_id:
            return None

        url = f"{NVD_API_BASE}?cveId={urllib.parse.quote(cve_id)}"
        raw = self._get_json(url)
        if not raw:
            return None

        vulns = raw.get("vulnerabilities") or []
        if not vulns:
            return None
        cve_obj = vulns[0].get("cve", {})
        return self._normalize_cve_response(cve_id, cve_obj)

    def search_by_keyword(self, keyword: str, max_results: int = 10) -> list[dict[str, Any]]:
        """按关键词搜索 CVE（用于"服务版本 -> 已知漏洞"的场景）。"""
        if not keyword or not keyword.strip():
            return []
        url = f"{NVD_API_BASE}?keywordSearch={urllib.parse.quote(keyword.strip())}&resultsPerPage={max_results}"
        raw = self._get_json(url)
        if not raw:
            return []
        out: list[dict[str, Any]] = []
        for item in raw.get("vulnerabilities") or []:
            cve_obj = item.get("cve", {})
            cve_id = cve_obj.get("id", "")
            if cve_id:
                out.append(self._normalize_cve_response(cve_id, cve_obj))
        return out

    # ── 内部：HTTP + 限流 + 重试 ──────────────────────────
    def _get_json(self, url: str) -> Optional[dict[str, Any]]:
        """带限流和重试的 GET 请求。失败返回 None。"""
        for attempt in range(self.max_retries + 1):
            self._respect_rate_limit()
            try:
                req = self._build_request(url)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    if resp.status == 429:
                        self._sleep_backoff(attempt)
                        continue
                    return json.loads(resp.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    self._sleep_backoff(attempt)
                    continue
                if 500 <= e.code < 600 and attempt < self.max_retries:
                    self._sleep_backoff(attempt)
                    continue
                return None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < self.max_retries:
                    self._sleep_backoff(attempt)
                    continue
                return None
            except (json.JSONDecodeError, ValueError):
                return None
        return None

    def _build_request(self, url: str) -> urllib.request.Request:
        headers = {
            "User-Agent": _NVD_USER_AGENT,
            "Accept": "application/json",
        }
        if self.api_key:
            headers["apiKey"] = self.api_key
        return urllib.request.Request(url, headers=headers)

    def _respect_rate_limit(self) -> None:
        """滑窗限流：最近 30 秒内调用超过 5 次时，sleep 到最早的调用滑出窗口。"""
        now = time.monotonic()
        self._call_timestamps = [t for t in self._call_timestamps if now - t < self._rate_window]
        if len(self._call_timestamps) >= self._rate_max:
            sleep_for = self._rate_window - (now - self._call_timestamps[0]) + 0.5
            if sleep_for > 0:
                time.sleep(min(sleep_for, self._rate_window))
        self._call_timestamps.append(time.monotonic())

    def _sleep_backoff(self, attempt: int) -> None:
        delay = min(2.0 ** attempt, 8.0)
        time.sleep(delay)

    # ── 内部：响应标准化 ──────────────────────────────────
    @staticmethod
    def _normalize_cve(cve_id: str) -> str:
        cve_id = str(cve_id or "").strip().upper()
        m = re.match(r"CVE-\d{4}-\d{4,}", cve_id)
        return m.group(0) if m else ""

    def _normalize_cve_response(self, cve_id: str, cve_obj: dict[str, Any]) -> dict[str, Any]:
        """把 NVD 原始响应提取成 Agent 友好的精简结构。"""
        descriptions = cve_obj.get("descriptions") or []
        desc_text = ""
        for d in descriptions:
            if d.get("lang") == "en":
                desc_text = d.get("value", "")
                break
        if not desc_text and descriptions:
            desc_text = descriptions[0].get("value", "")

        # CVSS 评分（优先 v3.1，其次 v3.0，最后 v2）
        cvss_score: Optional[float] = None
        cvss_severity = ""
        cvss_vector = ""
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            metrics = cve_obj.get("metrics", {}).get(key) or []
            if metrics:
                first = metrics[0].get("cvssData", {})
                cvss_score = first.get("baseScore")
                cvss_severity = first.get("baseSeverity") or metrics[0].get("baseSeverity", "")
                cvss_vector = first.get("vectorString", "")
                break

        # 影响版本范围
        affected: list[dict[str, str]] = []
        configs = cve_obj.get("configurations") or []
        for cfg in configs:
            for node in cfg.get("nodes", []) or []:
                for cpe_match in node.get("cpeMatch", []) or []:
                    cpe = cpe_match.get("criteria", "")
                    if cpe:
                        affected.append({
                            "cpe": cpe,
                            "vulnerable": cpe_match.get("vulnerable", True),
                            "version_start": cpe_match.get("versionStartIncluding", ""),
                            "version_end": cpe_match.get("versionEndIncluding", ""),
                        })

        # 参考链接
        references = []
        for ref in cve_obj.get("references") or []:
            url = ref.get("url", "")
            if url:
                references.append({
                    "url": url,
                    "source": ref.get("source", ""),
                    "tags": ref.get("tags", []),
                })

        # 发布/修改时间
        published = cve_obj.get("published", "")
        modified = cve_obj.get("lastModified", "")

        return {
            "cve_id": cve_id,
            "description": desc_text,
            "cvss_score": cvss_score,
            "cvss_severity": cvss_severity,
            "cvss_vector": cvss_vector,
            "affected_products": affected[:20],
            "references": references[:15],
            "published": published,
            "modified": modified,
            "source": "NVD",
        }
