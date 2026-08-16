"""OpenAI-compatible client for the lab vLLM server.

The GPU box (gpu-sv-008) exposes two endpoints — see
https://github.com/hirototamura/vllm_server :

- http://10.10.0.108:8000/v1  model qwen3-8b   (daily deliberation)
- http://10.10.0.108:8001/v1  model qwen3-32b  (heavier judgment)

Reachable on the lab LAN or via VPN; not a public address.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter

from core.llm.base import LLMClient

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://10.10.0.108:8000/v1"
DEFAULT_MODEL = "qwen3-8b"
DEFAULT_API_KEY = "dummy"
VLLM_BASE_URL_ENV = "VLLM_BASE_URL"
VLLM_API_KEY_ENV = "VLLM_API_KEY"
VLLM_API_TIMEOUT_ENV = "VLLM_API_TIMEOUT"
API_TIMEOUT = 300
CONNECTION_CHECK_TIMEOUT = 5

# Lab server: 8B is 6-way replicated (theoretical ~384); 32B is capped at 32.
_MODEL_CONCURRENCY_DEFAULTS = [
    (["70b", "72b"], 16),
    (["32b", "34b"], 32),
    (["14b", "13b"], 64),
    (["7b", "8b"], 100),
]
_CONCURRENCY_FALLBACK = 64


def _default_concurrency(model: str) -> int:
    lower = model.lower()
    for keywords, limit in _MODEL_CONCURRENCY_DEFAULTS:
        if any(k in lower for k in keywords):
            return limit
    return _CONCURRENCY_FALLBACK


def normalize_vllm_base_url(url: str) -> str:
    """Ensure the OpenAI-compatible root ends with /v1."""
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned:
        return DEFAULT_BASE_URL
    if cleaned.endswith("/v1"):
        return cleaned
    return f"{cleaned}/v1"


def looks_like_ollama_url(url: str) -> bool:
    lowered = (url or "").lower()
    return ":11434" in lowered or "/api/" in lowered


def resolve_vllm_base_url(llm_cfg: Optional[Dict[str, Any]] = None) -> str:
    """Resolve vLLM URL: env VLLM_BASE_URL overrides yaml; Ollama URLs fall back to lab default."""
    env_url = os.environ.get(VLLM_BASE_URL_ENV, "").strip()
    if env_url:
        return normalize_vllm_base_url(env_url)
    cfg_url = str((llm_cfg or {}).get("base_url", "")).strip()
    if not cfg_url or looks_like_ollama_url(cfg_url):
        return DEFAULT_BASE_URL
    return normalize_vllm_base_url(cfg_url)


def resolve_vllm_model(llm_cfg: Optional[Dict[str, Any]] = None) -> str:
    """Use yaml/env model when it looks like a vLLM id; otherwise the lab 8B default."""
    env_model = os.environ.get("VLLM_MODEL", "").strip()
    if env_model:
        return env_model
    cfg_model = str((llm_cfg or {}).get("model", "")).strip()
    if not cfg_model or ":" in cfg_model:
        # Ollama tags look like gemma4:e4b / qwen3.5:9b — not vLLM served-model ids.
        return DEFAULT_MODEL
    return cfg_model


def resolve_vllm_api_key(llm_cfg: Optional[Dict[str, Any]] = None) -> str:
    env_key = os.environ.get(VLLM_API_KEY_ENV, "").strip()
    if env_key:
        return env_key
    cfg_key = str((llm_cfg or {}).get("api_key", "")).strip()
    return cfg_key or DEFAULT_API_KEY


def resolve_vllm_api_timeout(llm_cfg: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """vLLM HTTP timeout in seconds.

    YAML ``api_timeout`` is Ollama-oriented (often 10–20s) and is ignored so
    parallel lab rounds keep the 300s client default. Override with
    ``VLLM_API_TIMEOUT``.
    """
    _ = llm_cfg
    env_raw = os.environ.get(VLLM_API_TIMEOUT_ENV, "").strip()
    if not env_raw:
        return None
    return int(env_raw)


def vllm_auth_headers(llm_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    return {"Authorization": f"Bearer {resolve_vllm_api_key(llm_cfg)}"}


class VllmClient(LLMClient):
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.7,
        max_tokens: int = 200,
        repeat_penalty: float = 1.1,
        min_p: float = 0.05,
        max_concurrency: int = -1,
        think: Optional[bool] = None,
        api_timeout: Optional[int] = None,
        api_key: str = DEFAULT_API_KEY,
    ):
        resolved = _default_concurrency(model) if max_concurrency == -1 else max_concurrency
        super().__init__(max_concurrency=resolved)
        self.base_url = normalize_vllm_base_url(base_url)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.repeat_penalty = repeat_penalty
        self.min_p = min_p
        self.think = think
        self.api_timeout = api_timeout or API_TIMEOUT
        self.api_key = api_key or DEFAULT_API_KEY
        self.api_url = f"{self.base_url}/chat/completions"
        self._pool_size = max(8, int(resolved) if resolved else 8)
        self._local = threading.local()

    @property
    def _session(self) -> requests.Session:
        # requests.Session is not thread-safe; parallel generate_async workers
        # each get their own session / connection pool.
        session = getattr(self._local, "session", None)
        if session is None:
            session = _build_http_session(self._pool_size)
            self._local.session = session
        return session

    def generate(self, prompt: str) -> str:
        try:
            payload: Dict[str, Any] = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "repetition_penalty": self.repeat_penalty,
                "min_p": self.min_p,
            }
            if self.think is not None:
                payload["chat_template_kwargs"] = {"enable_thinking": bool(self.think)}
            response = self._session.post(
                self.api_url,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.api_timeout,
            )
            response.raise_for_status()
            message = (response.json().get("choices") or [{}])[0].get("message") or {}
            content = message.get("content") or ""
            return str(content).strip()
        except Exception as e:
            logger.error("VllmClient.generate error: %s", e)
            return ""

    def check_connection(self) -> bool:
        try:
            response = self._session.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=CONNECTION_CHECK_TIMEOUT,
            )
            return response.status_code == 200
        except Exception:
            return False


def _build_http_session(pool_size: int) -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
