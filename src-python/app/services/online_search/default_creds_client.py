"""默认密码查询客户端

数据源: cirt.net (https://cirt.net/passwords) + 内置高频数据集
- 无需 API Key
- cirt.net 无官方 JSON API，HTML 解析脆弱

设计：
  - 内置高频默认凭据数据集（覆盖渗透测试常见设备/软件），秒回且离线可用
  - 在线查询作为补充（命中内置库时直接返回，不走网络）
  - 未命中内置库时尝试 cirt.net 抓取，失败返回手动查询链接
"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

_CIRT_BASE = "https://cirt.net/passwords"
_USER_AGENT = "SDIT-PentestAgent/1.0 (security research)"


# 内置高频默认凭据数据集（渗透测试常见目标）
# 来源：公开安全文档、cirt.net、厂商默认配置文档
_BUILTIN_CREDS: dict[str, list[dict[str, str]]] = {
    "tomcat": [
        {"username": "tomcat", "password": "tomcat", "source": "builtin", "note": "Tomcat Manager 默认"},
        {"username": "admin", "password": "admin", "source": "builtin", "note": "Tomcat Manager 常见弱口令"},
        {"username": "admin", "password": "", "source": "builtin", "note": "部分版本空密码"},
        {"username": "role1", "password": "tomcat", "source": "builtin", "note": "tomcat-users.xml 默认角色"},
        {"username": "both", "password": "tomcat", "source": "builtin"},
    ],
    "mysql": [
        {"username": "root", "password": "", "source": "builtin", "note": "MySQL 默认 root 空密码"},
        {"username": "root", "password": "root", "source": "builtin", "note": "常见弱口令"},
        {"username": "root", "password": "toor", "source": "builtin"},
        {"username": "admin", "password": "admin", "source": "builtin"},
    ],
    "postgres": [
        {"username": "postgres", "password": "postgres", "source": "builtin", "note": "PostgreSQL 默认"},
        {"username": "postgres", "password": "", "source": "builtin", "note": "部分版本信任本地连接"},
        {"username": "postgres", "password": "admin", "source": "builtin"},
    ],
    "vnc": [
        {"username": "", "password": "", "source": "builtin", "note": "VNC 无认证模式"},
        {"username": "", "password": "password", "source": "builtin"},
        {"username": "admin", "password": "admin", "source": "builtin"},
    ],
    "ssh": [
        {"username": "root", "password": "toor", "source": "builtin"},
        {"username": "root", "password": "root", "source": "builtin"},
        {"username": "admin", "password": "admin", "source": "builtin"},
        {"username": "pi", "password": "raspberry", "source": "builtin", "note": "树莓派默认"},
        {"username": "ubuntu", "password": "ubuntu", "source": "builtin"},
    ],
    "ftp": [
        {"username": "anonymous", "password": "anonymous@", "source": "builtin", "note": "匿名 FTP"},
        {"username": "admin", "password": "admin", "source": "builtin"},
        {"username": "ftp", "password": "ftp", "source": "builtin"},
    ],
    "telnet": [
        {"username": "root", "password": "", "source": "builtin", "note": "旧设备常见空密码"},
        {"username": "admin", "password": "admin", "source": "builtin"},
        {"username": "root", "password": "root", "source": "builtin"},
    ],
    "cisco": [
        {"username": "", "password": "cisco", "source": "builtin", "note": "Cisco 设备默认 enable"},
        {"username": "admin", "password": "cisco", "source": "builtin"},
        {"username": "cisco", "password": "cisco", "source": "builtin"},
        {"username": "enable", "password": "cisco", "source": "builtin"},
    ],
    "router": [
        {"username": "admin", "password": "admin", "source": "builtin", "note": "家用路由器通用"},
        {"username": "admin", "password": "password", "source": "builtin"},
        {"username": "admin", "password": "", "source": "builtin"},
        {"username": "root", "password": "12345", "source": "builtin"},
    ],
    "smb": [
        {"username": "guest", "password": "", "source": "builtin", "note": "SMB guest 访问"},
        {"username": "administrator", "password": "admin", "source": "builtin"},
    ],
    "redis": [
        {"username": "", "password": "", "source": "builtin", "note": "Redis 默认无密码"},
    ],
    "mongodb": [
        {"username": "", "password": "", "source": "builtin", "note": "MongoDB 默认无认证"},
    ],
    "web": [
        {"username": "admin", "password": "admin", "source": "builtin"},
        {"username": "admin", "password": "password", "source": "builtin"},
        {"username": "admin", "password": "123456", "source": "builtin"},
        {"username": "admin", "password": "admin123", "source": "builtin"},
    ],
    "printer": [
        {"username": "admin", "password": "", "source": "builtin", "note": "HP/Canon 打印机默认"},
        {"username": "admin", "password": "admin", "source": "builtin"},
    ],
    "ipmi": [
        {"username": "ADMIN", "password": "ADMIN", "source": "builtin", "note": "IPMI 默认"},
        {"username": "admin", "password": "admin", "source": "builtin"},
    ],
}


class DefaultCredsClient:
    """默认密码查询（内置数据集 + cirt.net 兜底）。"""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def lookup(self, product: str) -> dict[str, Any]:
        """查询设备/软件默认密码。

        Args:
            product: 产品名，如 tomcat / mysql / cisco / router

        Returns:
            含 credentials 列表的字典。
        """
        product = str(product or "").strip().lower()
        if not product:
            return {"product": "", "error": "产品名为空", "credentials": []}

        # 1. 内置数据集优先（秒回、离线可用）
        creds = self._lookup_builtin(product)
        if creds:
            return {
                "product": product,
                "credentials": creds,
                "count": len(creds),
                "source": "builtin-dataset",
                "cirt_url": f"{_CIRT_BASE}?criteria={urllib.parse.quote(product)}",
            }

        # 2. 在线查 cirt.net（best effort）
        online_creds = self._fetch_cirt(product)
        if online_creds:
            return {
                "product": product,
                "credentials": online_creds,
                "count": len(online_creds),
                "source": "cirt.net",
                "cirt_url": f"{_CIRT_BASE}?criteria={urllib.parse.quote(product)}",
            }

        # 3. 兜底
        return {
            "product": product,
            "credentials": [],
            "count": 0,
            "source": "fallback",
            "cirt_url": f"{_CIRT_BASE}?criteria={urllib.parse.quote(product)}",
            "fallback_advice": (
                f"内置库和在线查询均未命中。手动查: "
                f"https://cirt.net/passwords?criteria={urllib.parse.quote(product)} "
                f"或试 hydra 爆破常见弱口令表 /usr/share/wordlists/"
            ),
        }

    def _lookup_builtin(self, product: str) -> list[dict[str, str]]:
        """在内置数据集中查找。支持模糊匹配。"""
        # 精确匹配
        if product in _BUILTIN_CREDS:
            return list(_BUILTIN_CREDS[product])

        # 模糊匹配：product 是某个 key 的子串或反过来
        results: list[dict[str, str]] = []
        for key, creds in _BUILTIN_CREDS.items():
            if product in key or key in product:
                for c in creds:
                    entry = dict(c)
                    entry["matched_via"] = key
                    results.append(entry)
        return results

    def _fetch_cirt(self, product: str) -> list[dict[str, str]]:
        """尝试抓取 cirt.net 搜索结果。失败返回空列表。"""
        url = f"{_CIRT_BASE}?criteria={urllib.parse.quote(product)}"
        html = self._http_get(url)
        if not html:
            return []

        creds: list[dict[str, str]] = []
        # cirt.net 结果是 HTML 表格，简单提取用户名/密码对
        # 格式不固定，尽量容错
        for row in re.finditer(
            r"<tr[^>]*>(?P<row>.*?)</tr>", html, re.IGNORECASE | re.DOTALL,
        ):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row.group("row"), re.IGNORECASE | re.DOTALL)
            if len(cells) >= 3:
                vendor = re.sub(r"<[^>]+>", "", cells[0]).strip()
                username = re.sub(r"<[^>]+>", "", cells[1]).strip()
                password = re.sub(r"<[^>]+>", "", cells[2]).strip()
                if username or password:
                    creds.append({
                        "username": username,
                        "password": password,
                        "source": "cirt.net",
                        "vendor": vendor,
                    })
            if len(creds) >= 15:
                break
        return creds

    def _http_get(self, url: str) -> Optional[str]:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html",
            })
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError):
            return None
