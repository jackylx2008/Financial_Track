from __future__ import annotations

import json
import platform
import secrets
import subprocess
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse


class ReviewFileServer:
    """Serve the review HTML locally and open approved source files via the OS."""

    def __init__(self, html_path: Path, allowed_root: Path) -> None:
        self.html_path = html_path.resolve()
        self.allowed_root = allowed_root.resolve()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._token = secrets.token_urlsafe(24)

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("review file server has not started")
        return f"http://127.0.0.1:{self._server.server_port}/?token={self._token}"

    def start(self) -> str:
        if self._server is not None:
            return self.url
        handler = _handler_factory(
            self.html_path,
            self.allowed_root,
            self._token,
            open_with_default_application,
        )
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="review-file-server", daemon=True)
        self._thread.start()
        return self.url

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None


def resolve_allowed_source(value: str, allowed_root: Path) -> Path:
    path = Path(value).expanduser().resolve()
    root = allowed_root.resolve()
    if not path.is_file() or (path != root and root not in path.parents):
        raise ValueError("只允许打开项目 raw_data 目录中已存在的来源文件")
    return path


def open_with_default_application(path: Path) -> None:
    system = platform.system()
    if system == "Windows":
        _open_with_windows_file_association(path)
    elif system == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _open_with_windows_file_association(path: Path) -> None:
    """Ask Windows Shell to run the registered ``open`` verb for this exact file."""
    import ctypes

    result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
        None,
        "open",
        str(path),
        None,
        str(path.parent),
        1,
    )
    if int(result) <= 32:
        raise OSError(f"Windows 默认程序打开失败（ShellExecuteW 错误码 {int(result)}）：{path}")


def _handler_factory(
    html_path: Path,
    allowed_root: Path,
    token: str,
    opener: Callable[[Path], None],
) -> type[BaseHTTPRequestHandler]:
    class ReviewHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            if parse_qs(parsed.query).get("token", [""])[0] != token:
                self._send_json({"error": "无效的本地审核会话"}, HTTPStatus.FORBIDDEN)
                return
            if parsed.path in {"/", "/review"}:
                self._serve_review()
                return
            if parsed.path == "/open-source":
                self._open_source(parse_qs(parsed.query).get("path", [""])[0])
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def _serve_review(self) -> None:
            if not html_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "review HTML does not exist")
                return
            body = html_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _open_source(self, value: str) -> None:
            try:
                source = resolve_allowed_source(value, allowed_root)
                opener(source)
            except (OSError, ValueError) as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"status": "opened", "path": str(source)}, HTTPStatus.OK)

        def _send_json(self, payload: dict[str, str], status: HTTPStatus) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ReviewHandler
