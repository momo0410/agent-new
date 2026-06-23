from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from fastapi.testclient import TestClient
from app.main import app
from app.routers import api as api_router


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        json_data: Optional[Any] = None,
        text_data: str = "",
        headers: Optional[Dict[str, str]] = None,
        stream_chunks: Optional[List[bytes]] = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self._text_data = text_data
        self.headers = headers or {"content-type": "application/json"}
        self._stream_chunks = stream_chunks or []

    @property
    def text(self) -> str:
        if self._text_data:
            return self._text_data
        if self._json_data is None:
            return ""
        return json.dumps(self._json_data, ensure_ascii=False)

    def json(self) -> Any:
        if self._json_data is None:
            raise ValueError("No JSON payload")
        return self._json_data

    async def aread(self) -> bytes:
        return self.text.encode("utf-8")

    async def aiter_raw(self):
        for chunk in self._stream_chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


def test_ai_chat_proxy_non_stream_success(monkeypatch) -> None:
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, headers: Dict[str, str], json: Dict[str, Any]):
            assert url == "https://example.com/v1/chat/completions"
            assert headers.get("Authorization") == "Bearer test-key"
            assert json.get("model") == "deepseek-v3.2"
            return _FakeResponse(
                status_code=200,
                json_data={"choices": [{"message": {"content": "连接成功"}}]},
            )

    monkeypatch.setattr(api_router.httpx, "AsyncClient", _FakeAsyncClient)
    client = TestClient(app)
    response = client.post(
        "/api/v1/ai/chat-proxy",
        json={
            "url": "https://example.com/v1/chat/completions",
            "headers": {"Authorization": "Bearer test-key"},
            "body": {"model": "deepseek-v3.2", "messages": [{"role": "user", "content": "ping"}], "stream": False},
            "timeout_seconds": 20,
        },
    )
    client.close()
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["choices"][0]["message"]["content"] == "连接成功"


def test_ai_chat_proxy_non_stream_upstream_404_is_wrapped_as_502(monkeypatch) -> None:
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, headers: Dict[str, str], json: Dict[str, Any]):
            return _FakeResponse(
                status_code=404,
                text_data='{"detail":"Not Found"}',
                headers={"content-type": "application/json"},
            )

    monkeypatch.setattr(api_router.httpx, "AsyncClient", _FakeAsyncClient)
    client = TestClient(app)
    response = client.post(
        "/api/v1/ai/chat-proxy",
        json={
            "url": "https://example.com/v1/chat/completions",
            "headers": {"Authorization": "Bearer test-key"},
            "body": {"model": "deepseek-v3.2", "messages": [{"role": "user", "content": "ping"}], "stream": False},
            "timeout_seconds": 20,
        },
    )
    client.close()
    assert response.status_code == 502
    assert "AI 上游返回 404: Not Found" in response.json().get("detail", "")


def test_ai_chat_proxy_stream_passthrough(monkeypatch) -> None:
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        def build_request(self, method: str, url: str, headers: Dict[str, str], json: Dict[str, Any]):
            return {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
            }

        async def send(self, request: Dict[str, Any], stream: bool = False):
            assert stream is True
            assert request["method"] == "POST"
            return _FakeResponse(
                status_code=200,
                headers={"content-type": "text/event-stream"},
                stream_chunks=[
                    b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n',
                    b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n',
                    b"data: [DONE]\n\n",
                ],
            )

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(api_router.httpx, "AsyncClient", _FakeAsyncClient)
    client = TestClient(app)
    response = client.post(
        "/api/v1/ai/chat-proxy",
        json={
            "url": "https://example.com/v1/chat/completions",
            "headers": {"Authorization": "Bearer test-key"},
            "body": {"model": "deepseek-v3.2", "messages": [{"role": "user", "content": "ping"}], "stream": True},
            "timeout_seconds": 20,
        },
    )
    client.close()
    assert response.status_code == 200
    assert "data: {\"choices\":[{\"delta\":{\"content\":\"hello\"}}]}" in response.text
    assert "data: [DONE]" in response.text
