from curses import raw
from datetime import time
import json
import logging
import urllib.request, urllib.error
import os
import re
import subprocess
import time as time_module
import logging
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


def _drop_unexpected_top_level_keys(data: Dict[str, Any], json_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Best-effort schema mode isn't a hard guarantee — models can still add
    an extra top-level key here and there. If the schema forbids extras
    (additionalProperties: false) and the model added one anyway, drop it
    rather than failing the whole job when every actually-required field
    is present and valid.
    """
    if json_schema.get("additionalProperties") is not False:
        return data
    allowed = set(json_schema.get("properties", {}).keys())
    dropped = [k for k in data.keys() if k not in allowed]
    if dropped:
        logging.warning(f"Dropping unexpected top-level key(s) from LLM output: {dropped}")
        data = {k: v for k, v in data.items() if k in allowed}
    return data


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
        data = _drop_unexpected_top_level_keys(data, json_schema)
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
        data = _drop_unexpected_top_level_keys(data, json_schema)
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
        data = _drop_unexpected_top_level_keys(data, json_schema)
        validate(instance=data, schema=json_schema)
        return data

class GroqBackend:
    """Groq (configured Groq models)."""

    def __init__(self, model: str, api_key: str, base_url: str, json_mode: bool = True):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.json_mode = json_mode

    def _schema_name(self, json_schema: Dict[str, Any]) -> str:
        title = json_schema.get("title", "response")
        return re.sub(r"[^a-zA-Z0-9_]", "_", title).lower() or "response"

    def _post(self, payload_dict: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload_dict).encode()

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "github-actions/runner python-requests/2.32.0",
                "Origin": "https://api.groq.com",
            },
        )
        logging.info(f"Request payload: {payload_dict}")

        try: 
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())

        except urllib.error.HTTPError as e:
            logging.error(f"HTTP Status: {e.code}")
            try:
                error_body = e.read().decode("utf-8", errors="replace")
                logging.error(f"HTTP Body: {error_body}")
            except Exception:
                logging.error("Could not read error body")
            raise

    def complete(self, prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        print("******** ENTERED GROQ COMPLETE ********")
        base_payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant. Return JSON only."},
                {"role": "user", "content": prompt}
            ],
        }

        if self.json_mode:
            # Prefer Groq's schema-aware structured outputs (best-effort
            # mode) over plain JSON mode — this gives the model the actual
            # schema to follow instead of relying only on the prompt text,
            # and catches malformed output before it reaches local
            # validation. Not all models support it (e.g. compound-mini),
            # so we fall back to json_object automatically on rejection.
            schema_payload = dict(base_payload)
            schema_payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": self._schema_name(json_schema),
                    "strict": False,
                    "schema": json_schema,
                },
            }

            try:
                body = self._post(schema_payload)
            except urllib.error.HTTPError as e:
                logging.warning(
                    f"json_schema response_format rejected for model {self.model} "
                    f"(HTTP {e.code}); falling back to json_object mode."
                )
                fallback_payload = dict(base_payload)
                fallback_payload["response_format"] = {"type": "json_object"}
                try:
                    body = self._post(fallback_payload)
                except (urllib.error.HTTPError, TypeError) as e2:
                    logging.error(f"An API error occurred: {e2}")
                    logging.error(f"Request payload: {fallback_payload}")

                    try:
                        body = e2.read().decode("utf-8", errors="replace")
                        logging.error(f"Response body: {body}")
                    except Exception:
                        pass
                    raise e2
                
            except TypeError as e:
                logging.error(f"An API error occurred: {e}")
                logging.error(f"Request payload: {schema_payload}")
                raise e
        else:
            try:
                print("Calling model...")
                body = self._post(base_payload)
                print("Model call completed")
                print("===== RESPONSE BODY =====")
                print(repr(body))
                print("=========================")

            except (urllib.error.HTTPError, TypeError) as e:
                logging.error(f"An API error occurred: {e}")
                logging.error(f"Request payload: {base_payload}")
                raise e

        raw = body["choices"][0]["message"]["content"]

        print(f"RAW CONTENT LENGTH: {len(raw)}")
        print(f"RAW CONTENT: {repr(raw)}")

        raw = body["choices"][0]["message"]["content"]

        raw = re.sub(
            r"(?s)<think>.*?</think>",
            "",
            raw
        ).strip()

        print("AFTER THINK REMOVAL:")
        print(raw[:1000])

        data = json.loads(_strip_code_fences(raw))

        data = _drop_unexpected_top_level_keys(data, json_schema)
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
        data = _drop_unexpected_top_level_keys(data, json_schema)
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
        data = _drop_unexpected_top_level_keys(data, json_schema)
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

    if provider_name == "groq":
        return GroqBackend(
            model=model,
            api_key=_resolve_api_key(provider_name, provider_cfg),
            base_url=provider_cfg.get("base_url", "https://api.groq.com/openai/v1"),
            json_mode=provider_cfg.get("json_mode", True),
        )

    raise RuntimeError(
        f"Unsupported provider '{provider_name}'. "
        f"Add a class and an entry in get_backend() in llm_backend.py."
    )
