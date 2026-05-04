from __future__ import annotations

import atexit
import functools
import json
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Queue
from typing import Any

from .errors import ManiaMapAnalyserError


class _QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class StaticFileServer:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.port: int | None = None
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return

        handler = functools.partial(_QuietStaticHandler, directory=str(self.root))
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = int(self._server.server_address[1])
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="ma-static-server",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return

        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self.port = None

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None


@dataclass(frozen=True)
class RenderRequest:
    output_path: Path
    payload: dict[str, Any]
    capture_target: str


class ChromiumRenderRuntime:
    def __init__(self, static_root: Path) -> None:
        self.static_root = static_root
        self._jobs: Queue[tuple[str, RenderRequest | None, Future | None]] = Queue()
        self._ready = threading.Event()
        self._closed = False
        self._startup_error: Exception | None = None
        self._static_server: StaticFileServer | None = None
        self._browser = None
        self._context = None
        self._playwright = None
        self._bridge_url: str | None = None
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="ma-browser-worker",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self.close)

    def render(self, request: RenderRequest) -> Path:
        self._ready.wait()
        if self._startup_error is not None:
            raise self._normalize_startup_error(self._startup_error)
        if self._closed:
            raise ManiaMapAnalyserError("Chromium 渲染线程已关闭")

        future: Future = Future()
        self._jobs.put(("render", request, future))
        return future.result()

    def close(self) -> None:
        if self._closed:
            return

        self._closed = True
        self._jobs.put(("stop", None, None))
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def _worker_loop(self) -> None:
        try:
            self._static_server = StaticFileServer(self.static_root)
            self._static_server.start()
            if not self._static_server.port:
                raise ManiaMapAnalyserError("本地静态文件服务启动失败")

            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-dev-shm-usage",
                    "--font-render-hinting=medium",
                ],
            )
            self._context = self._browser.new_context(
                viewport={"width": 900, "height": 1400},
                device_scale_factor=2,
                color_scheme="dark",
            )
            self._bridge_url = (
                f"http://127.0.0.1:{self._static_server.port}"
                "/bridge/render_bridge.html"
            )
        except Exception as exc:  # pragma: no cover - startup failures are environment-specific
            self._startup_error = exc
            self._ready.set()
            self._shutdown_worker()
            return

        self._ready.set()

        while True:
            action, request, future = self._jobs.get()
            if action == "stop":
                break
            if action != "render" or request is None or future is None:
                continue

            try:
                result = self._render_page(request)
            except Exception as exc:
                future.set_exception(exc)
            else:
                future.set_result(result)

        self._shutdown_worker()

    def _render_page(self, request: RenderRequest) -> Path:
        if self._context is None or self._bridge_url is None:
            raise ManiaMapAnalyserError("Chromium 渲染上下文未就绪")

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        page = self._context.new_page()
        page.set_default_timeout(120000)

        try:
            payload_json = json.dumps(request.payload, ensure_ascii=False)
            page.add_init_script(script=f"window.__MA_RENDER_PAYLOAD = {payload_json};")
            page.goto(self._bridge_url, wait_until="load")
            page.wait_for_load_state("networkidle")
            page.wait_for_function("window.__MA_RENDER_DONE === true")
            render_state = page.evaluate(
                "() => ({"
                "error: window.__MA_RENDER_ERROR || null,"
                "statusText: window.__MA_RENDER_STATUS_TEXT || '',"
                "statusKind: window.__MA_RENDER_STATUS_KIND || ''"
                "})"
            )
            if render_state.get("error"):
                raise ManiaMapAnalyserError(str(render_state["error"]))

            selector = "#capture-surface"
            if request.capture_target == "graph_only":
                selector = "#body-graph-wrap"

            locator = page.locator(selector)
            if locator.count() == 0:
                raise ManiaMapAnalyserError(f"未找到截图目标：{selector}")

            locator.screenshot(
                path=str(request.output_path),
                animations="disabled",
            )
        except Exception as exc:
            raise self._normalize_runtime_error(exc) from exc
        finally:
            page.close()

        if not request.output_path.is_file() or request.output_path.stat().st_size <= 0:
            raise ManiaMapAnalyserError("截图输出失败，PNG 文件不存在或为空")
        return request.output_path

    def _shutdown_worker(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        if self._static_server is not None:
            self._static_server.stop()
            self._static_server = None

    def _normalize_startup_error(self, exc: Exception) -> ManiaMapAnalyserError:
        message = str(exc)
        lowered = message.lower()
        if "no module named 'playwright'" in lowered:
            return ManiaMapAnalyserError(
                "未安装 Playwright，请先执行 `pip install -r requirements.txt`"
            )
        if "executable doesn't exist" in lowered or "browsertype.launch" in lowered:
            return ManiaMapAnalyserError(
                "未安装 Chromium 内核，请先执行 `playwright install chromium`"
            )
        return ManiaMapAnalyserError(f"启动 Chromium 失败：{message}")

    def _normalize_runtime_error(self, exc: Exception) -> ManiaMapAnalyserError:
        if isinstance(exc, ManiaMapAnalyserError):
            return exc
        return ManiaMapAnalyserError(f"Playwright 渲染失败：{exc}")
