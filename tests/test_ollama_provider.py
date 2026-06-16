"""OllamaProvider 单元测试（无需真实 Ollama 服务）。"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.ai_router import OllamaProvider, LLMCallResult, AIRouter


# ─── Test 1: 初始化默认参数 ────────────────────────────────────────────────


def test_ollama_provider_init_defaults():
    """验证默认参数设置正确。"""
    with patch.dict(os.environ, {}, clear=True):
        provider = OllamaProvider()

    assert provider.base_url == "http://localhost:11434"
    assert provider.model == "llama3.2"
    assert provider.timeout == 120.0
    assert provider.sanitize_data is True


# ─── Test 2: 从环境变量初始化 ───────────────────────────────────────────────


def test_ollama_provider_init_from_env():
    """验证环境变量被正确读取。"""
    env = {
        "OLLAMA_ENABLED": "true",
        "OLLAMA_BASE_URL": "http://192.168.1.100:11434",
        "OLLAMA_MODEL": "qwen2.5:14b",
        "OLLAMA_TIMEOUT": "60",
        "OLLAMA_SANITIZE_DATA": "false",
    }
    with patch.dict(os.environ, env, clear=True):
        provider = OllamaProvider()

    assert provider.base_url == "http://192.168.1.100:11434"
    assert provider.model == "qwen2.5:14b"
    assert provider.timeout == 60.0
    assert provider.sanitize_data is False


# ─── Test 3: is_available 返回 False（服务未运行）─────────────────────────────


def test_ollama_provider_is_available_false():
    """Ollama 服务未运行时 is_available 返回 False。"""
    with patch.dict(os.environ, {}, clear=True):
        provider = OllamaProvider()

    with patch.object(provider, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_get_client.return_value = mock_client

        assert provider.is_available() is False


# ─── Test 4: chat 返回 LLMCallResult（离线不抛异常）─────────────────────────


def test_ollama_provider_chat_returns_result():
    """即使 Ollama 服务离线，chat 仍返回 LLMCallResult 而非抛异常。"""
    with patch.dict(os.environ, {}, clear=True):
        provider = OllamaProvider()

    messages = [{"role": "user", "content": "Hello"}]

    with patch.object(provider, "_get_client") as mock_get_client:
        import httpx
        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_get_client.return_value = mock_client

        result = provider.chat(messages)

    assert isinstance(result, LLMCallResult)
    assert result.provider == "ollama"
    assert result.error == "connection_failed"
    assert "Connection refused" in result.content or "not running" in result.content


# ─── Test 5: sanitize 移除 API Key ───────────────────────────────────────────


def test_ollama_provider_sanitize_removes_api_keys():
    """_sanitize_messages 能移除 API Key。"""
    with patch.dict(os.environ, {}, clear=True):
        provider = OllamaProvider()

    messages = [
        {
            "role": "user",
            "content": (
                "Please process this with api_key=sk-test-DO-NOT-USE-IN-PRODUCTION-aaaaaaaaaaaaaaaaaaaa "
                "and another key 'apiKey: abcdefghijklmnopqrstuvwxyz1234567890'"
            ),
        }
    ]
    sanitized = provider._sanitize_messages(messages)
    content = sanitized[0]["content"]

    assert "sk-test-DO-NOT-USE-IN-PRODUCTION" not in content
    assert "abcdefghijklmnopqrstuvwxyz1234567890" not in content
    assert "[REDACTED API KEY]" in content


# ─── Test 6: sanitize 移除 Bearer Token ─────────────────────────────────────


def test_ollama_provider_sanitize_removes_tokens():
    """_sanitize_messages 能移除 JWT Bearer Token。"""
    with patch.dict(os.environ, {}, clear=True):
        provider = OllamaProvider()

    messages = [
        {
            "role": "user",
            "content": (
                "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
                ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0"
                ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
            ),
        }
    ]
    sanitized = provider._sanitize_messages(messages)
    content = sanitized[0]["content"]

    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in content
    assert "[REDACTED TOKEN]" in content


# ─── Test 7: sanitize 移除文件路径 ──────────────────────────────────────────


def test_ollama_provider_sanitize_removes_paths():
    """_sanitize_messages 能移除 macOS/Linux 文件路径。"""
    with patch.dict(os.environ, {}, clear=True):
        provider = OllamaProvider()

    messages = [
        {
            "role": "user",
            "content": (
                "Please read from data/test.csv "
                "and /home/user/projects/main.py"
            ),
        }
    ]
    sanitized = provider._sanitize_messages(messages)
    content = sanitized[0]["content"]

    assert "/Users/" not in content
    assert "/home/user/projects" not in content
    assert "[FILE PATH]" in content


# ─── Test 8: ModelPool 启用 Ollama 时包含 OllamaProvider ─────────────────────


def test_model_pool_has_ollama_when_enabled():
    """OLLAMA_ENABLED=true 时，AIRouter.ollama 属性返回 OllamaProvider。"""
    with patch.dict(
        os.environ,
        {"OLLAMA_ENABLED": "true"},
        clear=True,
    ):
        router = AIRouter(use_cache=False)
        # 强制初始化
        router._lazy_init()

    assert router.ollama is not None
    assert isinstance(router.ollama, OllamaProvider)
    assert router.ollama.base_url == "http://localhost:11434"


# ─── Test 9: ModelPool 未启用 Ollama 时返回 None ────────────────────────────


def test_model_pool_ollama_none_when_disabled():
    """OLLAMA_ENABLED=false / 未设置时，AIRouter.ollama 为 None。"""
    with patch.dict(os.environ, {}, clear=True):
        router = AIRouter(use_cache=False)
        router._lazy_init()

    assert router.ollama is None
