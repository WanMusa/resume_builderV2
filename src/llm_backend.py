from datetime import time
import json
import os
import re
import subprocess
import time as time_module
from typing import Protocol, Dict, Any

from jsonschema import validate


# ── Protocol ──────────────────────────────────────────────────────────────────

class LLMBackend(Protocol):
    def complete(self, prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        ...


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _load_config() -> Dict[str, Any]:
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_api_key(provider_name: str, provider_cfg: Dict[str, Any]) -> str:
    env_var = provider_cfg.get("api_key_env")
    if not env_var:
        raise RuntimeError(f"Provider '{provider_name}' missing 'api_key_env' in config.json")
    key = os.getenv(env_var)
    if not key:
        raise RuntimeError(
            f"Environment variable '{env_var}' is not set. "
            f"Add it to your .env file or GitHub Actions secrets."
        )
    return key


# ── Provider implementations ──────────────────────────────────────────────────

class CopilotCLIBackend:
    """GitHub Copilot CLI — uses the CLI's own authenticated session, no API key needed."""

    def __init__(self, model: str):
        self.model = model

    def complete(self, prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        cmd = [
            "copilot", "-p", prompt, "-s",
            f"--model={self.model}",
            "--no-ask-user",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())
        if result.returncode != 0:
            raise RuntimeError(
                f"Copilot CLI failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        raw = _strip_code_fences(result.stdout)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Copilot output is not valid JSON: {e}\nOutput:\n{result.stdout}"
            ) from e
        validate(instance=data, schema=json_schema)
        return data

class OpenrouterBackend:
    """OpenRouterAi"""

    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        import urllib.request

        payload = json.dumps({
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())

        raw = body["choices"][0]["message"]["content"]
        data = json.loads(_strip_code_fences(raw))
        validate(instance=data, schema=json_schema)
        return data
    
class OpenAIBackend:
    """OpenAI-compatible REST API (OpenAI, Azure OpenAI, any OpenAI-compatible endpoint)."""

    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        import urllib.request

        payload = json.dumps({
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())

        raw = body["choices"][0]["message"]["content"]
        data = json.loads(_strip_code_fences(raw))
        validate(instance=data, schema=json_schema)
        return data


class GeminiBackend:
    """Google Gemini via REST API with native JSON mode (no markdown wrapping)."""

    def __init__(self, model: str, api_key: str, json_mode: bool = True):
        self.model = model
        self.api_key = api_key
        self.json_mode = json_mode

    def complete(self, prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        import urllib.request

        generation_config: Dict[str, Any] = {}
        if self.json_mode:
            generation_config["responseMimeType"] = "application/json"

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }).encode()

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        # --- Adding retry logic ---
        body = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url, data=payload, headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req) as resp:
                    body = json.loads(resp.read())
                break  # If successful, break out of the loop
                
            except urllib.error.HTTPError as e:
                # If we get a 429 and haven't run out of retries, wait and try again
                if e.code == 429 and attempt < max_retries - 1:
                    print(f"⚠️ Hit Gemini rate limit (429). Waiting 35 seconds... (Attempt {attempt+1}/{max_retries})")
                    time_module.sleep(35) # Wait for the minute-limit to reset
                else:
                    raise 
        
        if body is None:
            raise RuntimeError("Gemini request failed after all retries")
        # -----------------------

        raw = body["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(_strip_code_fences(raw))
        validate(instance=data, schema=json_schema)
        return data


class AnthropicBackend:
    """Anthropic Claude via Messages API."""

    def __init__(self, model: str, api_key: str):
        self.model = model
        self.api_key = api_key

    def complete(self, prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        import urllib.request

        payload = json.dumps({
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read())

        raw = body["content"][0]["text"]
        data = json.loads(_strip_code_fences(raw))
        validate(instance=data, schema=json_schema)
        return data


# ── Factory ───────────────────────────────────────────────────────────────────

def get_backend(stage_name: str) -> LLMBackend:
    """
    Resolve the correct LLM backend for a pipeline stage from config.json.

    config.json structure:
      providers.<name>  — connection details (api_key_env, base_url, feature flags)
      stages.<stage>    — which provider + model to use for this stage
    """
    cfg = _load_config()

    stage_cfg = cfg.get("stages", {}).get(stage_name)
    if not stage_cfg:
        raise RuntimeError(f"No stage config for '{stage_name}' in config.json")

    provider_name = stage_cfg.get("provider")
    model = stage_cfg.get("model")
    if not provider_name or not model:
        raise RuntimeError(
            f"Stage '{stage_name}' must specify both 'provider' and 'model' in config.json"
        )

    provider_cfg = cfg.get("providers", {}).get(provider_name)
    if provider_cfg is None:
        raise RuntimeError(
            f"Provider '{provider_name}' not found in config.json providers section"
        )

    if provider_name == "copilot_cli":
        return CopilotCLIBackend(model=model)

    if provider_name == "openai":
        return OpenAIBackend(
            model=model,
            api_key=_resolve_api_key(provider_name, provider_cfg),
            base_url=provider_cfg.get("base_url", "https://api.openai.com/v1"),
        )

    if provider_name == "gemini":
        return GeminiBackend(
            model=model,
            api_key=_resolve_api_key(provider_name, provider_cfg),
            json_mode=provider_cfg.get("json_mode", True),
        )

    if provider_name == "anthropic":
        return AnthropicBackend(
            model=model,
            api_key=_resolve_api_key(provider_name, provider_cfg),
        )

    if provider_name == "openrouter":
        return OpenrouterBackend(
            model=model,
            api_key=_resolve_api_key(provider_name, provider_cfg),
            base_url=provider_cfg.get("base_url", "https://openrouter.ai/api/v1"),
        )

    raise RuntimeError(
        f"Unsupported provider '{provider_name}'. "
        f"Add a class and an entry in get_backend() in llm_backend.py."
    )
