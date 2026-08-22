"""Tests for Ollama vs vLLM provider selection."""

from __future__ import annotations

import pytest

from core.llm.factory import (
    build_llm_client,
    describe_llm_target,
    resolve_llm_provider,
)
from core.llm.ollama import OllamaClient
from core.llm.vllm import VllmClient


def test_resolve_provider_defaults_to_ollama(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert resolve_llm_provider({}) == "ollama"
    assert resolve_llm_provider({"provider": "vllm"}) == "vllm"


def test_resolve_provider_env_overrides_yaml(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "vllm")
    assert resolve_llm_provider({"provider": "ollama"}) == "vllm"


def test_resolve_provider_rejects_unknown(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        resolve_llm_provider({"provider": "llamacpp"})


def test_build_client_ollama_by_default(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    client = build_llm_client(
        {"base_url": "http://localhost:11434", "model": "gemma4:e4b"}
    )
    assert isinstance(client, OllamaClient)
    assert client.model == "gemma4:e4b"


def test_build_client_vllm_replaces_ollama_yaml_defaults(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_MODEL", raising=False)
    monkeypatch.delenv("VLLM_API_TIMEOUT", raising=False)
    client = build_llm_client(
        {
            "provider": "vllm",
            "base_url": "http://localhost:11434",
            "model": "gemma4:e4b",
            "think": False,
        }
    )
    assert isinstance(client, VllmClient)
    assert client.base_url == "http://10.10.0.108:8000/v1"
    assert client.model == "qwen3-8b"
    assert client.think is False
    assert client._max_concurrency == 100
    assert client.api_timeout == 300


def test_build_client_vllm_ignores_short_ollama_api_timeout(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("VLLM_API_TIMEOUT", raising=False)
    client = build_llm_client({"provider": "vllm", "api_timeout": 20})
    assert isinstance(client, VllmClient)
    assert client.api_timeout == 300


def test_build_client_vllm_honors_timeout_env(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("VLLM_API_TIMEOUT", "90")
    client = build_llm_client({"provider": "vllm", "api_timeout": 20})
    assert isinstance(client, VllmClient)
    assert client.api_timeout == 90


def test_build_client_ollama_keeps_model_cap_without_yaml_concurrency(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    client = build_llm_client({"provider": "ollama", "model": "qwen3.5:9b"})
    assert isinstance(client, OllamaClient)
    assert client._max_concurrency == 8


def test_build_client_honors_max_concurrency(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    client = build_llm_client({"provider": "vllm", "max_concurrency": 48})
    assert isinstance(client, VllmClient)
    assert client._max_concurrency == 48


def test_build_client_vllm_passes_thinking_token_budget(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    monkeypatch.delenv("VLLM_MODEL", raising=False)
    monkeypatch.delenv("VLLM_API_TIMEOUT", raising=False)
    client = build_llm_client(
        {
            "provider": "vllm",
            "think": True,
            "thinking_token_budget": 640,
            "max_tokens": 2048,
        }
    )
    assert isinstance(client, VllmClient)
    assert client.think is True
    assert client.thinking_token_budget == 640


def test_describe_llm_target_vllm(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("VLLM_BASE_URL", raising=False)
    provider, url, model = describe_llm_target({"provider": "vllm"})
    assert provider == "vllm"
    assert url.endswith("/v1")
    assert model == "qwen3-8b"
