from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from localai.modules.config_loader import as_bool, as_float, as_int


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LlamaCppConfig:
    base_url: str
    model: str
    api_key: str
    timeout_sec: int
    max_tokens: int
    temperature: float
    autostart: bool
    server_path: str
    model_path: str
    mmproj_path: str
    extra_dll_dirs: list[str]
    n_gpu_layers: int
    ctx_size: int
    reasoning: str
    reasoning_budget: int | None
    startup_timeout_sec: int
    startup_poll_interval_sec: float
    stdout_log_path: Path
    stderr_log_path: Path

    @classmethod
    def from_config(cls, config: dict[str, Any], project_root: Path) -> "LlamaCppConfig":
        raw = config.get("llamacpp", {})
        model_path = str(raw.get("model_path", "")).strip()
        model = str(raw.get("model", "")).strip() or Path(model_path).stem or "local-model"
        return cls(
            base_url=str(raw.get("base_url", "http://127.0.0.1:8080/v1")).strip(),
            model=model,
            api_key=str(raw.get("api_key", "")).strip(),
            timeout_sec=as_int(raw.get("timeout_sec"), 120),
            max_tokens=as_int(raw.get("max_tokens"), 4096),
            temperature=as_float(raw.get("temperature"), 0.0),
            autostart=as_bool(raw.get("autostart", True)),
            server_path=str(raw.get("server_path", "")).strip(),
            model_path=model_path,
            mmproj_path=str(raw.get("mmproj_path", "")).strip(),
            extra_dll_dirs=_split_paths(raw.get("extra_dll_dirs", ""), project_root),
            n_gpu_layers=as_int(raw.get("n_gpu_layers"), 999),
            ctx_size=as_int(raw.get("ctx_size"), 8192),
            reasoning=str(raw.get("reasoning", "off")).strip(),
            reasoning_budget=_optional_int(raw.get("reasoning_budget")),
            startup_timeout_sec=as_int(raw.get("startup_timeout_sec"), 180),
            startup_poll_interval_sec=as_float(raw.get("startup_poll_interval_sec"), 1.0),
            stdout_log_path=_resolve_path(project_root, raw.get("stdout_log_path", "./log/llama_server.out.log")),
            stderr_log_path=_resolve_path(project_root, raw.get("stderr_log_path", "./log/llama_server.err.log")),
        )


def normalize_urls(base_url: str) -> tuple[str, str]:
    parsed = urlparse(base_url.rstrip("/"))
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(f"Invalid llamacpp.base_url: {base_url}")

    root_url = f"{parsed.scheme}://{parsed.netloc}"
    api_path = parsed.path.rstrip("/")
    api_url = f"{root_url}{api_path}" if api_path else root_url
    return root_url, api_url


def request_json(
    url: str,
    payload: dict[str, Any] | None = None,
    method: str = "GET",
    timeout_sec: int = 120,
    api_key: str = "",
) -> dict[str, Any]:
    body = None
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        content = response.read().decode("utf-8")
    return json.loads(content) if content else {}


class LlamaCppClient:
    def __init__(self, config: LlamaCppConfig) -> None:
        self.config = config
        self.root_url, self.api_url = normalize_urls(config.base_url)
        self._process: subprocess.Popen[Any] | None = None

    def check_server(self) -> tuple[dict[str, Any], dict[str, Any]]:
        logger.info("Checking llama.cpp health endpoint: %s/health", self.root_url)
        health = request_json(
            f"{self.root_url}/health",
            timeout_sec=self.config.timeout_sec,
            api_key=self.config.api_key,
        )
        logger.info("Checking llama.cpp models endpoint: %s/models", self.api_url)
        models = request_json(
            f"{self.api_url}/models",
            timeout_sec=self.config.timeout_sec,
            api_key=self.config.api_key,
        )
        return health, models

    def ensure_server(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            health, models = self.check_server()
            logger.info("llama.cpp service is already running")
            return health, models
        except Exception as exc:
            logger.info("llama.cpp service is not ready: %s", exc)
            if not self.config.autostart:
                raise

        logger.info("Autostart is enabled; starting llama.cpp service")
        process = self.start_server()
        deadline = time.time() + self.config.startup_timeout_sec
        last_error: Exception | None = None

        while time.time() < deadline:
            if process.poll() is not None:
                details = _tail(self.config.stderr_log_path)
                raise RuntimeError(
                    f"llama-server exited early with returncode={process.returncode}. stderr tail:\n{details}"
                )
            try:
                health, models = self.check_server()
                logger.info("llama.cpp service became ready")
                return health, models
            except Exception as exc:
                last_error = exc
                logger.info(
                    "Waiting for llama.cpp service; retrying in %.1f sec; last_error=%s",
                    self.config.startup_poll_interval_sec,
                    exc,
                )
                time.sleep(self.config.startup_poll_interval_sec)

        stderr_tail = _tail(self.config.stderr_log_path)
        raise RuntimeError(f"Timed out waiting for llama-server. Last error: {last_error}\n{stderr_tail}")

    def start_server(self) -> subprocess.Popen[Any]:
        command = self.build_server_command()
        logger.info("Starting llama.cpp command: %s", _redact_command(command))
        logger.info("llama.cpp stdout log: %s", self.config.stdout_log_path)
        logger.info("llama.cpp stderr log: %s", self.config.stderr_log_path)
        self.config.stdout_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.stderr_log_path.parent.mkdir(parents=True, exist_ok=True)

        stdout_file = self.config.stdout_log_path.open("a", encoding="utf-8")
        stderr_file = self.config.stderr_log_path.open("a", encoding="utf-8")
        env = os.environ.copy()
        dll_dirs = [str(Path(command[0]).resolve().parent), *self.config.extra_dll_dirs]
        env["PATH"] = os.pathsep.join([*dll_dirs, env.get("PATH", "")])
        try:
            process = subprocess.Popen(
                command,
                stdout=stdout_file,
                stderr=stderr_file,
                cwd=str(Path(command[0]).resolve().parent),
                env=env,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        finally:
            stdout_file.close()
            stderr_file.close()
        self._process = process
        logger.info("llama.cpp process started; pid=%s", process.pid)
        return process

    def shutdown_server(self, timeout_sec: float = 10.0) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is not None:
            self._process = None
            return

        logger.info("Stopping llama.cpp process; pid=%s", process.pid)
        process.terminate()
        try:
            process.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            logger.info("llama.cpp process did not stop in %.1f sec; killing pid=%s", timeout_sec, process.pid)
            process.kill()
            process.wait(timeout=timeout_sec)
        finally:
            self._process = None

    def build_server_command(self) -> list[str]:
        server_path = Path(self.config.server_path)
        model_path = Path(self.config.model_path)
        mmproj_path = Path(self.config.mmproj_path) if self.config.mmproj_path else None

        if not server_path.exists():
            raise RuntimeError(f"llama-server not found: {server_path}")
        if not model_path.exists():
            raise RuntimeError(f"Model file not found: {model_path}")
        if mmproj_path and not mmproj_path.exists():
            raise RuntimeError(f"mmproj file not found: {mmproj_path}")

        parsed = urlparse(self.config.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8080

        command = [str(server_path), "-m", str(model_path)]
        if mmproj_path:
            command.extend(["--mmproj", str(mmproj_path)])
        if self.config.model:
            command.extend(["--alias", self.config.model])
        if self.config.reasoning:
            command.extend(["--reasoning", self.config.reasoning])
        if self.config.reasoning_budget is not None:
            command.extend(["--reasoning-budget", str(self.config.reasoning_budget)])
        if self.config.ctx_size > 0:
            command.extend(["-c", str(self.config.ctx_size)])
        command.extend(
            [
                "-ngl",
                str(self.config.n_gpu_layers),
                "--host",
                host,
                "--port",
                str(port),
                "--verbose",
            ]
        )
        return command

    def model_ids(self, models_payload: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for item in models_payload.get("data", []):
            model_id = item.get("id")
            if model_id:
                ids.append(str(model_id))
        for item in models_payload.get("models", []):
            model_id = item.get("model") or item.get("name") or item.get("id")
            if model_id:
                ids.append(str(model_id))
        return ids

    def assert_model_available(self, models_payload: dict[str, Any]) -> None:
        model_ids = self.model_ids(models_payload)
        if self.config.model not in model_ids:
            raise RuntimeError(f"Configured model is not available: {self.config.model}. Available: {model_ids}")
        logger.info("Configured llama.cpp model is available: %s", self.config.model)

    def chat(self, prompt: str, max_tokens: int | None = None) -> str:
        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.config.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = request_json(
            f"{self.api_url}/chat/completions",
            payload=payload,
            method="POST",
            timeout_sec=self.config.timeout_sec,
            api_key=self.config.api_key,
        )
        return response["choices"][0]["message"]["content"].strip()


def _resolve_path(project_root: Path, value: Any) -> Path:
    path = Path(str(value))
    if path.is_absolute():
        return path
    return project_root / path


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return as_int(value)


def _split_paths(value: Any, project_root: Path) -> list[str]:
    if isinstance(value, list):
        return [str(_resolve_path(project_root, item)) for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [str(_resolve_path(project_root, item.strip())) for item in re.split(r"[;|]", text) if item.strip()]


def _tail(path: Path, lines: int = 80) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def _redact_command(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)
