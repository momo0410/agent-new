"""三级缓存 —— L1 内存 / L2 磁盘(7天) / L3 永久

缓存键：由各 client 自定义，通常是查询参数的稳定哈希。
  - L1: OnlineSearchService 实例内 dict，本次渗透生命周期，秒回
  - L2: 用户 cache 目录 sdit/online_search/，7 天 TTL，不同靶机之间复用
  - L3: skills/knowledge_base/cve/，永久，CVE 信息不变，命中后写 JSON

写入策略：查到结果后同时写 L1 + L2（CVE 类结果额外写 L3）。
读取策略：L1 -> L2 -> L3 -> 在线查询。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Optional


def stable_cache_key(*parts: str) -> str:
    """根据多个字符串片段生成稳定的缓存键（sha1 前 16 位）。"""
    raw = "|".join(str(p) for p in parts if p is not None)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class OnlineSearchCache:
    """三级缓存管理器。

    Args:
        l2_dir: L2 磁盘缓存目录（7 天 TTL）。None 则禁用 L2。
        l3_dir: L3 永久缓存目录（CVE 等）。None 则禁用 L3。
        l2_ttl_seconds: L2 缓存有效期，默认 7 天。
    """

    def __init__(
        self,
        l2_dir: Optional[str] = None,
        l3_dir: Optional[str] = None,
        l2_ttl_seconds: int = 7 * 24 * 3600,
    ):
        self._l1: dict[str, dict[str, Any]] = {}
        self._l2_dir = l2_dir
        self._l3_dir = l3_dir
        self._l2_ttl = l2_ttl_seconds
        if l2_dir:
            os.makedirs(l2_dir, exist_ok=True)
        if l3_dir:
            os.makedirs(l3_dir, exist_ok=True)

    # ── 读取 ──────────────────────────────────────────────
    def get(self, namespace: str, key: str) -> Optional[dict[str, Any]]:
        """按 L1 -> L2 -> L3 顺序查找。命中 L2/L3 时回填 L1。"""
        full_key = f"{namespace}:{key}"

        # L1
        if full_key in self._l1:
            return self._l1[full_key]

        # L2（带 TTL）
        if self._l2_dir:
            entry = self._read_json(self._l2_path(namespace, key))
            if entry and self._not_expired(entry):
                self._l1[full_key] = entry["data"]
                return entry["data"]

        # L3（永久，仅 CVE 等稳定数据）
        if self._l3_dir:
            entry = self._read_json(self._l3_path(namespace, key))
            if entry:
                self._l1[full_key] = entry.get("data", entry)
                return self._l1[full_key]

        return None

    # ── 写入 ──────────────────────────────────────────────
    def put(
        self,
        namespace: str,
        key: str,
        data: dict[str, Any],
        permanent: bool = False,
    ) -> None:
        """写入缓存。permanent=True 时写入 L3（永久），否则只写 L1+L2。"""
        full_key = f"{namespace}:{key}"
        self._l1[full_key] = data

        if permanent and self._l3_dir:
            self._write_json(self._l3_path(namespace, key), {"data": data, "key": key})
        elif self._l2_dir:
            self._write_json(
                self._l2_path(namespace, key),
                {"data": data, "ts": time.time(), "key": key},
            )

    # ── 管理 ──────────────────────────────────────────────
    def clear_l1(self) -> None:
        self._l1.clear()

    def clear_l2(self) -> int:
        """清空 L2 磁盘缓存，返回删除的文件数。"""
        if not self._l2_dir or not os.path.isdir(self._l2_dir):
            return 0
        count = 0
        for root, _, files in os.walk(self._l2_dir):
            for f in files:
                if f.endswith(".json"):
                    try:
                        os.remove(os.path.join(root, f))
                        count += 1
                    except OSError:
                        pass
        return count

    def l2_size(self) -> int:
        if not self._l2_dir or not os.path.isdir(self._l2_dir):
            return 0
        return sum(1 for _, _, fs in os.walk(self._l2_dir) for f in fs if f.endswith(".json"))

    # ── 内部 ──────────────────────────────────────────────
    def _l2_path(self, namespace: str, key: str) -> str:
        sub = os.path.join(self._l2_dir, namespace)
        os.makedirs(sub, exist_ok=True)
        return os.path.join(sub, f"{key}.json")

    def _l3_path(self, namespace: str, key: str) -> str:
        sub = os.path.join(self._l3_dir, namespace)
        os.makedirs(sub, exist_ok=True)
        return os.path.join(sub, f"{key}.json")

    @staticmethod
    def _read_json(path: str) -> Optional[dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_json(path: str, data: dict[str, Any]) -> None:
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass

    def _not_expired(self, entry: dict[str, Any]) -> bool:
        ts = entry.get("ts", 0)
        return (time.time() - ts) < self._l2_ttl
