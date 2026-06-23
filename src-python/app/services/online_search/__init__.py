"""OnlineSearchService — 联网检索能力

为渗透测试 Agent 提供联网检索扩展，查询 NVD / ExploitDB / MSF 文档 / 默认密码。

设计目标（见 docs/handoff-03-online-search-design.md）：
  - 离线模式 100% 可用：搜索失败时 Agent 仍能正常工作
  - 三级缓存：L1 内存 / L2 磁盘 7 天 / L3 永久 knowledge_base
  - 限流与预算：NVD 5 次/30 秒，每次渗透最多 N 次（默认 10）
  - 本地 skill 优先：联网检索是本地 skill 缺失时的补充，不是替代

对外统一入口：OnlineSearchService
"""

from .registry import OnlineSearchService, get_online_search_service, reset_online_search_service

__all__ = ["OnlineSearchService", "get_online_search_service", "reset_online_search_service"]
