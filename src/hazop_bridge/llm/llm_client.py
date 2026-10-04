#!/usr/bin/env python3
"""llm_client.py Thin OpenAI-compatible chat client for the Siemens LLM endpoint.
Credentials are NEVER hardcoded here. They are read from environment
variables, which are loaded from a local '.env' file (untracked by git,
see .gitignore). Set:
SIEMENS_LLM_API_KEY
SIEMENS_LLM_BASE_URL (default: https://api.siemens.com/llm/v1)
SIEMENS_LLM_MODEL    (default: qwen-3.6-27b)
"""
import json
import os
import time
from pathlib import Path
import requests

_ENV_LOADED = False

def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no external dependency). Does not override
    variables already present in the real environment."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = Path(path)
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if key and key not in os.environ:
                os.environ[key] = val
    _ENV_LOADED = True

class LLMConfigError(RuntimeError):
    pass

class LLMRequestError(RuntimeError):
    pass

class LLMClient:
    """Minimal OpenAI-compatible chat-completions client."""
    def __init__(self, api_key: str = None, base_url: str = None,
                 model: str = None, timeout: int = 60, max_retries: int = 3):
        _load_dotenv()
        self.api_key = api_key or os.environ.get("SIEMENS_LLM_API_KEY")
        self.base_url = (base_url or os.environ.get(
            "SIEMENS_LLM_BASE_URL", "https://api.siemens.com/llm/v1")).rstrip("/")
        self.model = model or os.environ.get("SIEMENS_LLM_MODEL", "qwen-3.6-27b")
        self.timeout = timeout
        self.max_retries = max_retries

        if not self.api_key:
            raise LLMConfigError(
                "SIEMENS_LLM_API_KEY not set. Create a .env file "
                "(see .env.example) or export the environment variable."
            )

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, messages: list, tools: list = None, tool_choice = None,
             temperature: float = 0.3, max_tokens: int = 1024,
             enable_thinking: bool = False) -> dict:
        """Call the chat/completions endpoint. Returns the raw response dict.
        'enable_thinking=False' (default) disables Qwen "thinking mode" via
        vLLM's chat_template_kwargs so max_tokens is spent on the actual
        answer instead of chain-of-thought reasoning tokens. Set True if you
        want the model's reasoning trace back (e.g. for debugging).
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if not enable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        last_error = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout
                )
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 ** attempt)
                    continue
                else:
                    raise LLMRequestError(
                        f"LLM API returned status {resp.status_code}: {resp.text}"
                    )
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(1.5 ** attempt)

        raise LLMRequestError(
            f"LLM request failed after {self.max_retries} attempts: {last_error}"
        )
