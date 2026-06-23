"""共享 FastEmbed 编码器单例

被 SkillEmbeddingIndex 和（P3）ExperienceStore 共用，避免重复加载 ONNX 模型。
模型: BAAI/bge-small-zh-v1.5（中英双语，512 维）
CPU 加载约 5-10 秒，单条 encode 约 5ms。

加载失败时返回 None，由调用方降级到 TF-IDF / 字符串相似度。
"""
from __future__ import annotations

import logging
import threading
from typing import Iterable, Optional

LOGGER = logging.getLogger(__name__)

# 默认模型 —— 改用环境变量 HERMES_EMBED_MODEL 可覆盖
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
EMBED_DIM = 512


class _EncoderSingleton:
    _instance: Optional["_EncoderSingleton"] = None
    _lock = threading.Lock()

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._load_attempted = False
        self._load_failed = False

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        if self._load_failed:
            return False
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            LOGGER.warning("fastembed 未安装，embedding 功能停用: %s", exc)
            self._load_failed = True
            return False
        try:
            self._model = TextEmbedding(model_name=self.model_name)
            LOGGER.info("FastEmbed 模型加载成功: %s", self.model_name)
            return True
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("FastEmbed 模型加载失败 %s: %s", self.model_name, exc)
            self._load_failed = True
            return False
        finally:
            self._load_attempted = True

    def encode_batch(self, texts: Iterable[str]) -> Optional[list[list[float]]]:
        if not self._ensure_loaded():
            return None
        try:
            # fastembed.embed 返回 generator of np.ndarray
            return [list(map(float, vec)) for vec in self._model.embed(list(texts))]
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("FastEmbed encode 失败: %s", exc)
            return None

    def encode_one(self, text: str) -> Optional[list[float]]:
        result = self.encode_batch([text])
        return result[0] if result else None

    @property
    def available(self) -> bool:
        if not self._load_attempted:
            self._ensure_loaded()
        return self._model is not None and not self._load_failed


def get_encoder(model_name: str = DEFAULT_MODEL) -> _EncoderSingleton:
    """获取全局共享编码器（同一 model_name 复用）"""
    with _EncoderSingleton._lock:
        if (_EncoderSingleton._instance is None
                or _EncoderSingleton._instance.model_name != model_name):
            _EncoderSingleton._instance = _EncoderSingleton(model_name)
        return _EncoderSingleton._instance


__all__ = ["get_encoder", "DEFAULT_MODEL", "EMBED_DIM"]
