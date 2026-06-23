import os
import uvicorn


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=_env_int("PY_BACKEND_PORT", 3001),
        # 默认关闭 reload，避免热重载重启导致内存态 SSH 会话丢失。
        # 需要热重载时可显式设置 PY_BACKEND_RELOAD=1。
        reload=_env_flag("PY_BACKEND_RELOAD", False),
        log_level="info",
    )
