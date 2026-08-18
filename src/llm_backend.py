import json
import os
import subprocess
from dataclasses import dataclass
from typing import Protocol, Dict, Any

from jsonschema import validate


@dataclass
class LLMConfig:
    backend: str
    model: str


class LLMBackend(Protocol):
    def complete(self, prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        ...


class CopilotCLIBackend:
    def __init__(self, model: str):
        self.model = model

    def complete(self, prompt: str, json_schema: Dict[str, Any]) -> Dict[str, Any]:
        env = os.environ.copy()
        # Important for Actions runner auth
        # GITHUB_TOKEN is expected to be set at workflow step env.
        cmd = [
            "copilot",
            "-p",
            prompt,
            "-s",
            f"--model={self.model}",
            "--no-ask-user",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if result.returncode != 0:
            raise RuntimeError(
                f"Copilot CLI failed (exit {result.returncode}): {result.stderr.strip()}"
            )

        raw = result.stdout.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Copilot output is not valid JSON: {e}\nOutput:\n{raw}") from e

        validate(instance=data, schema=json_schema)
        return data


def _load_config() -> Dict[str, Any]:
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def get_backend(stage_name: str) -> LLMBackend:
    cfg = _load_config()
    stage_cfg = cfg.get(stage_name)
    if not stage_cfg:
        raise RuntimeError(f"Missing config for stage '{stage_name}' in config.json")

    backend = stage_cfg.get("backend")
    model = stage_cfg.get("model")
    if backend == "copilot_cli":
        return CopilotCLIBackend(model=model)

    raise RuntimeError(f"Unsupported backend '{backend}' for stage '{stage_name}'")