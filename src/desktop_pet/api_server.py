import asyncio
import ipaddress
import json
import logging
import os
import threading
from collections import deque
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from aiohttp import web
from aiohttp.web import Request, Response
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from .motion_controller import MotionModeController
from .instances_store import InstancesStoreError
from .pet_instance import (
    InstanceConfigError,
    InstanceConflictError,
    InstanceNotFoundError,
    PackageNotFoundError,
)

logger = logging.getLogger(__name__)


class _MainThreadInvoker(QObject):
    """在主线程创建的 QObject，通过 signal 把 callable 投递到主线程执行。

    解决 ``QTimer.singleShot`` 在子线程不触发的 bug（详见 pet.py 同名注释）：
    API server 跑在子线程的 asyncio loop 里，``QTimer.singleShot(0, ...)``
    创建的 timer 属于子线程，而子线程没有 Qt 事件循环，timer 永远不触发。

    用 ``pyqtSignal`` + QueuedConnection 是项目既定的跨线程调度方案：
    signal emit 在子线程调用时，slot 会在 receiver 所在线程（主线程）执行。
    """

    call_requested = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        # 跨线程连接默认就是 QueuedConnection，显式声明以便阅读
        from PyQt6.QtCore import Qt

        self.call_requested.connect(self._on_call, Qt.ConnectionType.QueuedConnection)

    def _on_call(self, payload: tuple):
        """主线程 slot：执行 func 并把结果回传到 asyncio loop。"""
        func, loop, future = payload
        try:
            result = func()
            loop.call_soon_threadsafe(future.set_result, result)
        except Exception as e:
            loop.call_soon_threadsafe(future.set_exception, e)

# ── OpenClaw http-channel 双向 webhook ──────────────────────────
# 出站方向：用户消息 POST 到 OpenClaw openclaw-http-channel 插件的入站 webhook。
# 入站方向：Agent 回复由插件出站适配器 POST 到 /api/openclaw/reply 接收端。
DEFAULT_OPENCLAW_WEBHOOK_URL = "http://127.0.0.1:18789/webhooks/http-channel"
DEFAULT_OPENCLAW_PEER = "boss"


class ApiServer:
    def __init__(self, platform):
        """Create a platform-owned API server."""
        if platform is None:
            raise TypeError("ApiServer requires a PetPlatform")
        self._platform = platform
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._running = False
        self._host = "127.0.0.1"
        self._port = 8080
        self._allowed_ips: list[str] = ["127.0.0.1", "::1"]
        self._trust_proxy_headers = False
        self._chat_histories: dict[str, deque] = {}
        self._user_messages: deque = deque(maxlen=100)
        self._openclaw_webhook_url = DEFAULT_OPENCLAW_WEBHOOK_URL
        self._openclaw_peer = DEFAULT_OPENCLAW_PEER
        self._openclaw_secret_token: str = ""
        self._openclaw_loop: Optional[asyncio.AbstractEventLoop] = None
        self._main_thread_invoker = _MainThreadInvoker()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lifecycle_lock = threading.RLock()
        self._startup_event: Optional[threading.Event] = None
        self._startup_error: Optional[BaseException] = None
        self._startup_task: Optional[asyncio.Task] = None
        self._stop_requested = threading.Event()
        self._last_error: Optional[BaseException] = None

    def _resolve_pet_sync(self, pet_id: str | None = None):
        if pet_id:
            return self._platform.get_pet_widget(pet_id)
        primary = self._platform.get_primary_instance()
        if primary is None:
            return None
        return self._platform.get_pet_widget(primary.pet_id)

    async def _resolve_pet(self, request: Request):
        pet_id = request.match_info.get("pet_id") or request.query.get("pet_id")
        return await self._run_in_main_thread(lambda: self._resolve_pet_sync(pet_id))

    async def _resolve_pet_from_args(self, args: dict):
        pet_id = args.get("pet_id")
        return await self._run_in_main_thread(lambda: self._resolve_pet_sync(pet_id))

    async def _run_in_main_thread(self, func):
        if QThread.currentThread() == self._main_thread_invoker.thread():
            return func()
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._main_thread_invoker.call_requested.emit((func, loop, future))
        return await future

    @staticmethod
    def _pet_not_found_response() -> Response:
        return web.json_response({"error": "pet not found"}, status=404)

    @staticmethod
    def _status_for_error(error: BaseException) -> int:
        if isinstance(error, (InstanceNotFoundError, PackageNotFoundError)):
            return 404
        if isinstance(error, InstanceConflictError):
            return 409
        if isinstance(error, (InstanceConfigError, ValueError, TypeError, json.JSONDecodeError)):
            return 400
        return 500

    @classmethod
    def _error_response(cls, error: BaseException) -> Response:
        return web.json_response({"error": str(error)}, status=cls._status_for_error(error))

    def configure(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    def set_allowed_ips(self, ips: list[str]) -> None:
        self._allowed_ips = ips

    def set_trust_proxy_headers(self, trusted: bool) -> None:
        self._trust_proxy_headers = trusted

    def add_allowed_ip(self, ip: str) -> None:
        if ip not in self._allowed_ips:
            self._allowed_ips.append(ip)

    def remove_allowed_ip(self, ip: str) -> None:
        if ip in self._allowed_ips:
            self._allowed_ips.remove(ip)

    def get_allowed_ips(self) -> list[str]:
        return self._allowed_ips.copy()

    def set_openclaw_config(self, webhook_url: str, peer: str, secret_token: str = "") -> None:
        if webhook_url:
            self._openclaw_webhook_url = webhook_url
        if peer:
            self._openclaw_peer = peer
        if secret_token:
            self._openclaw_secret_token = secret_token

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_error(self) -> Optional[BaseException]:
        return self._last_error

    async def start(self) -> bool:
        if self._running:
            return True
        self._last_error = None
        self._app = web.Application()
        self._setup_ip_filter()
        self._setup_routes()
        self._setup_cors()
        self._runner = web.AppRunner(self._app)
        try:
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self._host, self._port)
            await self._site.start()
        except BaseException as error:
            self._last_error = error
            logger.error("Failed to start API server: %s", error)
            if self._runner is not None:
                try:
                    await self._runner.cleanup()
                except Exception:
                    logger.exception("Failed to clean up API runner after startup failure")
            self._app = None
            self._runner = None
            self._site = None
            self._running = False
            return False
        self._running = True
        self._openclaw_loop = asyncio.get_running_loop()
        logger.info("API server started: http://%s:%s", self._host, self._port)
        return True

    async def stop(self) -> bool:
        site, runner = self._site, self._runner
        error: BaseException | None = None
        try:
            if site is not None:
                try:
                    await site.stop()
                except Exception as exc:
                    error = exc
            if runner is not None:
                try:
                    await runner.cleanup()
                except Exception as exc:
                    if error is None:
                        error = exc
        finally:
            self._site = None
            self._runner = None
            self._app = None
            self._running = False
            self._openclaw_loop = None
        if error is not None:
            self._last_error = error
            logger.error("Failed to stop API server: %s", error)
            return False
        logger.info("API server stopped")
        return True

    def _background_main(self, startup_event: threading.Event) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        startup_task = loop.create_task(self.start())
        with self._lifecycle_lock:
            self._loop = loop
            self._startup_task = startup_task
        started = False
        try:
            started = bool(loop.run_until_complete(startup_task))
            if not started and self._startup_error is None:
                self._startup_error = self._last_error or RuntimeError("API server failed to start")
        except asyncio.CancelledError:
            if self._startup_error is None:
                self._startup_error = self._last_error or TimeoutError("API server startup cancelled")
        except BaseException as error:
            self._startup_error = error
            self._last_error = error
            logger.exception("API background thread failed during startup")
        finally:
            with self._lifecycle_lock:
                if self._startup_task is startup_task:
                    self._startup_task = None
            startup_event.set()
        try:
            if started and not self._stop_requested.is_set():
                loop.run_forever()
        finally:
            if not startup_task.done():
                startup_task.cancel()
                loop.run_until_complete(asyncio.gather(startup_task, return_exceptions=True))
            if self._running or self._runner is not None:
                try:
                    loop.run_until_complete(self.stop())
                except Exception as error:
                    self._last_error = error
                    logger.exception("API background cleanup failed")
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            with self._lifecycle_lock:
                if self._loop is loop:
                    self._loop = None
                if self._thread is threading.current_thread():
                    self._thread = None
                self._startup_event = None
                self._startup_task = None

    def start_background(self, timeout: float = 5) -> bool:
        with self._lifecycle_lock:
            if self._running:
                return True
            if self._thread is not None and self._thread.is_alive():
                event = self._startup_event
                thread = self._thread
            else:
                self._startup_error = None
                self._last_error = None
                self._stop_requested.clear()
                event = threading.Event()
                self._startup_event = event
                thread = threading.Thread(
                    target=self._background_main,
                    args=(event,),
                    daemon=True,
                    name="desktop-pet-api",
                )
                self._thread = thread
                thread.start()
        if event is not None and event.wait(timeout):
            return self._running and self._startup_error is None

        timeout_error = TimeoutError("API server startup timed out")
        self._startup_error = timeout_error
        self._last_error = timeout_error
        self._stop_requested.set()
        with self._lifecycle_lock:
            loop = self._loop
            startup_task = self._startup_task
        if loop is not None and loop.is_running():
            if startup_task is not None:
                loop.call_soon_threadsafe(startup_task.cancel)
            else:
                loop.call_soon_threadsafe(loop.stop)
        if thread is not threading.current_thread():
            thread.join(timeout)
        return False

    def stop_background(self, timeout: float = 5) -> bool:
        with self._lifecycle_lock:
            thread = self._thread
            loop = self._loop
        if thread is None:
            if self._running:
                self._last_error = RuntimeError("API server was not started in background")
                return False
            return True
        if thread is threading.current_thread():
            self._last_error = RuntimeError("stop_background cannot run on the API server thread")
            return False

        self._stop_requested.set()
        success = True
        if loop is not None and loop.is_running():
            async def stop_and_halt():
                stopped = await self.stop()
                loop.call_soon(loop.stop)
                return stopped

            try:
                future = asyncio.run_coroutine_threadsafe(stop_and_halt(), loop)
                success = bool(future.result(timeout=timeout))
            except Exception as error:
                self._last_error = error
                logger.exception("Failed to stop API server in background")
                success = False
        thread.join(timeout)
        if thread.is_alive():
            self._last_error = TimeoutError("API server thread did not stop")
            return False
        return success and not self._running

    def _get_client_ip(self, request: Request) -> str:
        """Get real client IP, considering proxy headers."""
        if not self._trust_proxy_headers:
            return request.remote or "unknown"

        # Check X-Forwarded-For header first (comma-separated, first is client)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.remote or "unknown"

    def _setup_ip_filter(self) -> None:
        if self._app is None:
            return

        @web.middleware
        async def ip_filter_middleware(request: Request, handler):
            # IP 白名单已禁用（使用 ngrok 等内网穿透时需要）
            if not self._allowed_ips:
                return await handler(request)

            client_ip = self._get_client_ip(request)

            logger.debug(f"[API] Request from IP: {client_ip}, whitelist: {self._allowed_ips}")

            if client_ip not in self._allowed_ips:
                logger.warning(f"Access denied: IP {client_ip} not in whitelist")
                return web.json_response(
                    {"success": False, "error": "Access denied"},
                    status=403
                )

            return await handler(request)

        self._app.middlewares.append(ip_filter_middleware)

    def _setup_routes(self) -> None:
        if self._app is None:
            return

        # 旧版单宠物路由（保留，向后兼容）
        self._app.router.add_get("/api/status", self.handle_status)
        self._app.router.add_get("/api/screens", self.handle_screens)
        self._app.router.add_post("/api/mode", self.handle_mode)
        self._app.router.add_post("/api/move", self.handle_move)
        self._app.router.add_post("/api/move_by", self.handle_move_by)
        self._app.router.add_post("/api/move_edge", self.handle_move_edge)
        self._app.router.add_post("/api/animation", self.handle_animation)
        self._app.router.add_post("/api/walk", self.handle_walk)
        self._app.router.add_get("/api/animations", self.handle_animations_list)

        # 多宠物路由：/api/pets/{pet_id}/<endpoint>
        # handler 内通过 _resolve_pet 统一解析 pet_id
        self._app.router.add_get("/api/pets/{pet_id}/status", self.handle_status)
        self._app.router.add_post("/api/pets/{pet_id}/mode", self.handle_mode)
        self._app.router.add_post("/api/pets/{pet_id}/move", self.handle_move)
        self._app.router.add_post("/api/pets/{pet_id}/move_by", self.handle_move_by)
        self._app.router.add_post("/api/pets/{pet_id}/move_edge", self.handle_move_edge)
        self._app.router.add_post("/api/pets/{pet_id}/animation", self.handle_animation)
        self._app.router.add_post("/api/pets/{pet_id}/walk", self.handle_walk)
        self._app.router.add_get("/api/pets/{pet_id}/animations", self.handle_animations_list)
        self._app.router.add_post("/api/pets/{pet_id}/chat_bubble/show", self.handle_show_chat_bubble)
        self._app.router.add_post("/api/pets/{pet_id}/chat_bubble/hide", self.handle_hide_chat_bubble)
        self._app.router.add_post("/api/pets/{pet_id}/message", self.handle_show_message)
        self._app.router.add_post("/api/pets/{pet_id}/message/hide", self.handle_hide_message)

        # 实例管理端点
        self._app.router.add_get("/api/instances", self.handle_list_instances)
        self._app.router.add_post("/api/instances", self.handle_create_instance)
        self._app.router.add_get("/api/instances/{pet_id}", self.handle_get_instance)
        self._app.router.add_patch("/api/instances/{pet_id}", self.handle_update_instance)
        self._app.router.add_delete("/api/instances/{pet_id}", self.handle_delete_instance)

        # AI tool-calling endpoints
        self._app.router.add_get("/api/tools", self.handle_tools_list)
        self._app.router.add_post("/api/tools/call", self.handle_tools_call)
        self._app.router.add_post("/api/chat", self.handle_chat)

        # 消息交互端点（MCP/AI 消息展示与用户输入）
        self._app.router.add_post("/api/message", self.handle_show_message)
        self._app.router.add_get("/api/messages/pending", self.handle_pending_messages)
        self._app.router.add_post("/api/messages/send", self.handle_send_message)
        self._app.router.add_post("/api/chat_bubble/show", self.handle_show_chat_bubble)
        self._app.router.add_post("/api/chat_bubble/hide", self.handle_hide_chat_bubble)

        # OpenClaw http-channel 接收端：接收 Agent 回复推送
        self._app.router.add_post("/api/openclaw/reply", self.handle_openclaw_reply)

    def _setup_cors(self) -> None:
        if self._app is None:
            return

        @web.middleware
        async def cors_middleware(request: Request, handler):
            if request.method == "OPTIONS":
                response = web.Response()
            else:
                response = await handler(request)

            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return response

        self._app.middlewares.append(cors_middleware)

    def _validate_coordinates(self, data: dict) -> tuple[int, int] | None:
        """Validate required integer coordinates."""
        if "x" not in data or "y" not in data:
            return None
        x, y = data.get("x"), data.get("y")
        if type(x) is not int or type(y) is not int:
            return None
        if not (-10000 <= x <= 10000 and -10000 <= y <= 10000):
            return None
        return x, y

    def _validate_delta(self, data: dict) -> tuple[int, int] | None:
        """Validate required integer movement deltas."""
        if "dx" not in data or "dy" not in data:
            return None
        dx, dy = data.get("dx"), data.get("dy")
        if type(dx) is not int or type(dy) is not int:
            return None
        if not (-10000 <= dx <= 10000 and -10000 <= dy <= 10000):
            return None
        return dx, dy

    def _parse_screen_index(self, data: dict, pet=None) -> int | None:
        """从请求数据中解析 screen 字段(可选)。

        - 缺省 / null / 非法类型:返回 None(自动按坐标选屏)
        - 整数:返回 int(越界由调用方处理)
        - 越界整数:返回 -1(标记为非法,调用方返回 400)

        Args:
            data: 请求数据 dict。
            pet: target pet widget used to validate the screen index.
        """
        if "screen" not in data:
            return None
        raw = data.get("screen")
        if raw is None:
            return None
        try:
            idx = int(raw)
        except (ValueError, TypeError):
            return -1
        sm = getattr(pet, "screen_manager", None)
        if sm is None:
            return idx
        if sm.screen_by_index(idx) is None:
            return -1
        return idx

    def _is_safe_callback_url(self, url: str) -> bool:
        """Check if callback URL is safe (no internal network access)."""
        try:
            parsed = urlparse(url)

            # Only allow http/https
            if parsed.scheme not in ("http", "https"):
                return False

            hostname = parsed.hostname
            if not hostname:
                return False

            # Block private/internal IP ranges
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return False
            except ValueError:
                # Not an IP address, could be a domain - allow for now
                pass

            # Block localhost variants
            blocked_hosts = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
            if hostname.lower() in blocked_hosts:
                return False

            return True
        except Exception:
            return False

    async def _run_pet_operation(self, request: Request, operation):
        pet_id = request.match_info.get("pet_id") or request.query.get("pet_id")

        def invoke():
            pet = self._resolve_pet_sync(pet_id)
            if pet is None:
                raise InstanceNotFoundError(f"pet not found: {pet_id or 'primary'}")
            return operation(pet)

        return await self._run_in_main_thread(invoke)

    async def handle_status(self, request: Request) -> Response:
        try:
            def collect(pet):
                position = pet.api.get_position()
                sm = getattr(pet, "screen_manager", None)
                screens = [screen.to_dict() for screen in sm.all_screens()] if sm else []
                return {
                    "position": position,
                    "state": pet.api.get_state(),
                    "mode": pet.api.get_mode(),
                    "animations": pet.api.get_available_animations(),
                    "current_screen": position.get("screen", -1),
                    "screens": screens,
                }
            return web.json_response(await self._run_pet_operation(request, collect))
        except Exception as error:
            return self._error_response(error)

    async def handle_screens(self, request: Request) -> Response:
        try:
            def collect(pet):
                sm = getattr(pet, "screen_manager", None)
                position = pet.api.get_position()
                return {
                    "screens": [screen.to_dict() for screen in sm.all_screens()] if sm else [],
                    "current_screen": position.get("screen", -1),
                }
            return web.json_response(await self._run_pet_operation(request, collect))
        except Exception as error:
            return self._error_response(error)

    async def handle_mode(self, request: Request) -> Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response({"success": False, "error": "Invalid JSON body"}, status=400)
        mode = data.get("mode")
        if mode not in ("random", "motion"):
            return web.json_response({"success": False, "error": "Invalid mode"}, status=400)
        try:
            success = await self._run_pet_operation(request, lambda pet: pet.api.set_mode(mode))
            return web.json_response({"success": bool(success)})
        except Exception as error:
            return self._error_response(error)

    async def handle_move(self, request: Request) -> Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response({"success": False, "error": "Invalid JSON body"}, status=400)
        coords = self._validate_coordinates(data)
        if coords is None:
            return web.json_response({"success": False, "error": "Invalid coordinates"}, status=400)
        x, y = coords
        try:
            def move(pet):
                screen = self._parse_screen_index(data, pet)
                if screen == -1:
                    raise InstanceConfigError("screen index out of range")
                if pet.api.get_mode() != "motion":
                    pet.api.set_mode("motion")
                return pet.api.move_to(x, y, screen)
            success = await self._run_pet_operation(request, move)
            return web.json_response({"success": bool(success)})
        except Exception as error:
            return self._error_response(error)

    async def handle_move_by(self, request: Request) -> Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response({"success": False, "error": "Invalid JSON body"}, status=400)
        delta = self._validate_delta(data)
        if delta is None:
            return web.json_response({"success": False, "error": "Invalid delta"}, status=400)
        dx, dy = delta
        try:
            def move(pet):
                if pet.api.get_mode() != "motion":
                    pet.api.set_mode("motion")
                return pet.api.move_by(dx, dy)
            success = await self._run_pet_operation(request, move)
            return web.json_response({"success": bool(success)})
        except Exception as error:
            return self._error_response(error)

    async def handle_move_edge(self, request: Request) -> Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response({"success": False, "error": "Invalid JSON body"}, status=400)
        edge = data.get("edge")
        if edge not in ("left", "right"):
            return web.json_response({"success": False, "error": "Invalid edge"}, status=400)
        try:
            def move(pet):
                screen = self._parse_screen_index(data, pet)
                if screen == -1:
                    raise InstanceConfigError("screen index out of range")
                if pet.api.get_mode() != "motion":
                    pet.api.set_mode("motion")
                return pet.api.move_to_edge(edge, screen)
            success = await self._run_pet_operation(request, move)
            return web.json_response({"success": bool(success)})
        except Exception as error:
            return self._error_response(error)

    async def handle_animation(self, request: Request) -> Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response({"success": False, "error": "Invalid JSON body"}, status=400)
        name = data.get("name")
        if not isinstance(name, str) or not name:
            return web.json_response({"success": False, "error": "Animation name required"}, status=400)
        callback_url = data.get("callback_url")
        try:
            def play(pet):
                if pet.api.get_mode() != "motion":
                    pet.api.set_mode("motion")
                success = pet.api.play_animation(name)
                return success, pet.api.get_position()
            success, position = await self._run_pet_operation(request, play)
        except Exception as error:
            return self._error_response(error)
        if success and callback_url and self._is_safe_callback_url(callback_url):
            asyncio.create_task(self._send_animation_callback(name, callback_url, position))
        elif callback_url and not self._is_safe_callback_url(callback_url):
            logger.warning("Unsafe callback URL rejected: %s", callback_url)
        return web.json_response({"success": bool(success), "animation": name})

    async def handle_walk(self, request: Request) -> Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response({"success": False, "error": "Invalid JSON body"}, status=400)
        direction = data.get("direction")
        if direction not in ("left", "right"):
            return web.json_response({"success": False, "error": "Invalid direction"}, status=400)
        try:
            def walk(pet):
                screen = self._parse_screen_index(data, pet)
                if screen == -1:
                    raise InstanceConfigError("screen index out of range")
                if pet.api.get_mode() != "motion":
                    pet.api.set_mode("motion")
                return pet.api.play_walk(direction, screen)
            success = await self._run_pet_operation(request, walk)
            return web.json_response({"success": bool(success)})
        except Exception as error:
            return self._error_response(error)

    async def handle_animations_list(self, request: Request) -> Response:
        try:
            animations = await self._run_pet_operation(
                request, lambda pet: pet.api.get_available_animations()
            )
            return web.json_response({"animations": animations})
        except Exception as error:
            return self._error_response(error)

    async def _send_animation_callback(self, animation_name: str, callback_url: str, position: dict) -> None:
        payload = {
            "event": "animation_completed",
            "animation": animation_name,
            "position": position,
            "timestamp": datetime.now().isoformat() + "Z",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(callback_url, json=payload) as response:
                    if response.status != 200:
                        logger.warning("Animation callback failed with status: %s", response.status)
        except Exception as error:
            logger.error("Animation callback failed: %s -> %s, error: %s", animation_name, callback_url, error)

    async def handle_list_instances(self, request: Request) -> Response:
        def collect():
            instances = []
            for config in self._platform.list_instances():
                widget = self._platform.get_pet_widget(config.pet_id)
                position = widget.api.get_position() if widget is not None else config.position
                state = widget.api.get_state() if widget is not None else "unknown"
                instances.append({
                    "pet_id": config.pet_id,
                    "package": config.package,
                    "primary": config.primary,
                    "position": position,
                    "state": state,
                    "size": config.size,
                    "screen_index": config.screen_index,
                })
            return instances
        try:
            return web.json_response({"instances": await self._run_in_main_thread(collect)})
        except Exception as error:
            return self._error_response(error)

    async def handle_create_instance(self, request: Request) -> Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)
        if not isinstance(data, dict):
            return web.json_response({"error": "JSON body must be an object"}, status=400)
        try:
            def create():
                package = data.get("package", "default")
                position = data.get("position")
                pet_id = self._platform.create_instance(package, position, config=data)
                config = self._platform.get_instance_config(pet_id)
                return config.to_dict() if config else {"pet_id": pet_id}
            result = await self._run_in_main_thread(create)
            return web.json_response(result, status=201)
        except Exception as error:
            return self._error_response(error)

    async def handle_get_instance(self, request: Request) -> Response:
        pet_id = request.match_info.get("pet_id")
        try:
            def collect():
                config = self._platform.get_instance_config(pet_id)
                if config is None:
                    raise InstanceNotFoundError(f"pet not found: {pet_id}")
                widget = self._platform.get_pet_widget(pet_id)
                result = config.to_dict()
                result["state"] = widget.api.get_state() if widget else "unknown"
                result["mode"] = widget.api.get_mode() if widget else "unknown"
                result["position"] = widget.api.get_position() if widget else config.position
                return result
            return web.json_response(await self._run_in_main_thread(collect))
        except Exception as error:
            return self._error_response(error)

    async def handle_update_instance(self, request: Request) -> Response:
        pet_id = request.match_info.get("pet_id")
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)
        if not isinstance(data, dict):
            return web.json_response({"error": "JSON body must be an object"}, status=400)
        try:
            updated = await self._run_in_main_thread(
                lambda: self._platform.update_instance_config(pet_id, data)
            )
            return web.json_response(updated.to_dict())
        except Exception as error:
            return self._error_response(error)

    async def handle_delete_instance(self, request: Request) -> Response:
        pet_id = request.match_info.get("pet_id")
        try:
            success = await self._run_in_main_thread(
                lambda: self._platform.destroy_instance(pet_id)
            )
            if not success:
                raise InstanceNotFoundError(f"pet not found: {pet_id}")
            return web.json_response({"success": True})
        except Exception as error:
            return self._error_response(error)

    # ========== AI Tool-Calling ==========

    def _get_primary_pet(self):
        return self._resolve_pet_sync()

    def _build_tools(self) -> list[dict]:
        """构建 AI 可调用的工具定义列表（OpenAI function calling 格式）。

        包含固定的控制类工具和动态的宠物动画动作工具。
        多宠物模式下，所有控制类工具均新增可选参数 ``pet_id`` 用于指定目标实例。
        """
        # pet_id 通用参数定义（多宠物模式下用于路由到指定桌宠实例）
        pet_id_param = {
            "type": "string",
            "description": "目标桌宠实例 ID，不指定则作用于主实例",
        }

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_pet_status",
                    "description": "获取桌面宠物的当前状态，包括位置、状态、模式和可用动画列表",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pet_id": pet_id_param,
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "set_pet_mode",
                    "description": "设置宠物运行模式。random 模式下宠物自主随机行动，motion 模式下可通过 API 控制宠物",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "mode": {
                                "type": "string",
                                "enum": ["random", "motion"],
                                "description": "运行模式：random=自主随机行动，motion=API受控模式",
                            },
                            "pet_id": pet_id_param,
                        },
                        "required": ["mode"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "move_pet_to",
                    "description": "将宠物移动到屏幕上的指定坐标位置",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "x": {
                                "type": "integer",
                                "description": "目标 X 坐标（像素）",
                            },
                            "y": {
                                "type": "integer",
                                "description": "目标 Y 坐标（像素）",
                            },
                            "screen": {
                                "type": "integer",
                                "description": "目标屏幕索引（可选，不填则按坐标自动选择屏幕）",
                            },
                            "pet_id": pet_id_param,
                        },
                        "required": ["x", "y"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "move_pet_by",
                    "description": "将宠物相对当前位置移动指定偏移量",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "dx": {
                                "type": "integer",
                                "description": "X 方向偏移量（像素，正数向右，负数向左）",
                            },
                            "dy": {
                                "type": "integer",
                                "description": "Y 方向偏移量（像素，正数向下，负数向上）",
                            },
                            "pet_id": pet_id_param,
                        },
                        "required": ["dx", "dy"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "move_pet_to_edge",
                    "description": "将宠物移动到屏幕的左边缘或右边缘",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "edge": {
                                "type": "string",
                                "enum": ["left", "right"],
                                "description": "目标边缘方向",
                            },
                            "screen": {
                                "type": "integer",
                                "description": "目标屏幕索引（可选，不填则使用当前屏幕）",
                            },
                            "pet_id": pet_id_param,
                        },
                        "required": ["edge"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "walk_pet",
                    "description": "让宠物向左或向右行走",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "direction": {
                                "type": "string",
                                "enum": ["left", "right"],
                                "description": "行走方向",
                            },
                            "screen": {
                                "type": "integer",
                                "description": "目标屏幕索引（可选，不填则使用当前屏幕）",
                            },
                            "pet_id": pet_id_param,
                        },
                        "required": ["direction"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_screens",
                    "description": "获取所有显示器屏幕信息，包括分辨率和位置",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pet_id": pet_id_param,
                        },
                        "required": [],
                    },
                },
            },
        ]

        # 多宠物模式独有工具：实例管理
        tools.append({
        "type": "function",
        "function": {
            "name": "list_pets",
            "description": "列出当前所有运行中的桌宠实例（含 pet_id、包名、位置、状态）",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        })
        tools.append({
        "type": "function",
        "function": {
            "name": "create_pet",
            "description": "创建一个新的桌宠实例并显示在屏幕上",
            "parameters": {
                "type": "object",
                "properties": {
                    "package": {
                        "type": "string",
                        "description": "宠物资源包名（如 'default'）；不指定时使用默认包",
                    },
                    "x": {
                        "type": "integer",
                        "description": "初始 X 坐标（像素）",
                    },
                    "y": {
                        "type": "integer",
                        "description": "初始 Y 坐标（像素）",
                    },
                },
                "required": [],
            },
        },
        })
        tools.append({
        "type": "function",
        "function": {
            "name": "remove_pet",
            "description": "销毁指定的桌宠实例",
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {
                        "type": "string",
                        "description": "要销毁的桌宠实例 ID",
                    },
                },
                "required": ["pet_id"],
            },
        },
        })

        # 动态添加宠物动画动作工具（基于主实例的动画列表）
        primary_pet = self._get_primary_pet()
        animations = primary_pet.api.get_available_animations() if primary_pet is not None else []
        if animations:
            tools.append({
                "type": "function",
                "function": {
                    "name": "play_animation",
                    "description": "播放指定的宠物动画。可用动画名见参数说明",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "enum": animations,
                                "description": f"要播放的动画名称，可选值：{', '.join(animations)}",
                            },
                            "pet_id": pet_id_param,
                        },
                        "required": ["name"],
                    },
                },
            })
        else:
            tools.append({
                "type": "function",
                "function": {
                    "name": "play_animation",
                    "description": "播放指定的宠物动画（当前无可用动画）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "要播放的动画名称",
                            },
                            "pet_id": pet_id_param,
                        },
                        "required": ["name"],
                    },
                },
            })

        # 消息交互工具
        tools.append({
            "type": "function",
            "function": {
                "name": "show_message",
                "description": "在宠物旁边显示气泡消息，可用于向用户展示通知或对话内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "要显示的消息文本",
                        },
                        "duration": {
                            "type": "integer",
                            "description": "消息显示时长（毫秒），默认 5000（5秒）",
                        },
                        "pet_id": pet_id_param,
                    },
                    "required": ["text"],
                },
            },
        })
        tools.append({
            "type": "function",
            "function": {
                "name": "get_user_messages",
                "description": "获取用户通过宠物气泡输入的待处理消息，获取后队列会被清空",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        })
        tools.append({
            "type": "function",
            "function": {
                "name": "show_chat_bubble",
                "description": "显示可交互的聊天气泡，用户可以在气泡中输入消息回复",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "初始显示的消息文本",
                        },
                        "pet_id": pet_id_param,
                    },
                    "required": [],
                },
            },
        })
        tools.append({
            "type": "function",
            "function": {
                "name": "hide_chat_bubble",
                "description": "隐藏可交互的聊天气泡",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pet_id": pet_id_param,
                    },
                    "required": [],
                },
            },
        })

        return tools

    async def handle_tools_list(self, request: Request) -> Response:
        """GET /api/tools - 返回 AI 可调用的工具定义列表"""
        tools = await self._run_in_main_thread(self._build_tools)
        return web.json_response({"tools": tools})

    async def handle_tools_call(self, request: Request) -> Response:
        """POST /api/tools/call - execute an AI tool call."""
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response(
                {"success": False, "error": "Invalid JSON body"},
                status=400,
            )

        tool_name = data.get("name")
        arguments = data.get("arguments", {})
        if not isinstance(tool_name, str) or not tool_name:
            return web.json_response(
                {"success": False, "error": "Tool name is required"},
                status=400,
            )
        if not isinstance(arguments, dict):
            return web.json_response(
                {"success": False, "error": "Tool arguments must be an object"},
                status=400,
            )

        handler = self._tool_handlers.get(tool_name)
        if handler is None:
            return web.json_response(
                {"success": False, "error": f"Unknown tool: {tool_name}"},
                status=400,
            )

        try:
            result = await handler(arguments)
        except Exception as error:
            logger.error("Tool call error: %s -> %s", tool_name, error)
            return web.json_response(
                self._tool_error(error),
                status=self._status_for_error(error),
            )
        if not isinstance(result, dict):
            error = RuntimeError(f"Tool handler returned invalid result: {tool_name}")
            return web.json_response(self._tool_error(error), status=500)
        return web.json_response(result, status=self._tool_result_status(result))

    @property
    def _tool_handlers(self) -> dict:
        """工具名到处理函数的映射"""
        handlers = {
            "get_pet_status": self._tool_get_pet_status,
            "set_pet_mode": self._tool_set_pet_mode,
            "move_pet_to": self._tool_move_pet_to,
            "move_pet_by": self._tool_move_pet_by,
            "move_pet_to_edge": self._tool_move_pet_to_edge,
            "walk_pet": self._tool_walk_pet,
            "play_animation": self._tool_play_animation,
            "get_screens": self._tool_get_screens,
            "show_message": self._tool_show_message,
            "get_user_messages": self._tool_get_user_messages,
            "show_chat_bubble": self._tool_show_chat_bubble,
            "hide_chat_bubble": self._tool_hide_chat_bubble,
        }
        # 多宠物模式独有工具
        handlers["list_pets"] = self._tool_list_pets
        handlers["create_pet"] = self._tool_create_pet
        handlers["remove_pet"] = self._tool_remove_pet
        return handlers

    async def _run_tool_pet(self, args: dict, operation):
        pet_id = args.get("pet_id")

        def invoke():
            pet = self._resolve_pet_sync(pet_id)
            if pet is None:
                raise InstanceNotFoundError(f"pet not found: {pet_id or 'primary'}")
            return operation(pet)

        return await self._run_in_main_thread(invoke)

    @staticmethod
    def _tool_error(error: BaseException) -> dict:
        return {"success": False, "error": str(error), "error_type": type(error).__name__}

    @staticmethod
    def _tool_result_status(result: dict) -> int:
        if result.get("success") is not False:
            return 200
        error_type = result.get("error_type")
        if error_type in {"InstanceNotFoundError", "PackageNotFoundError"}:
            return 404
        if error_type == "InstanceConflictError":
            return 409
        if error_type in {
            "InstanceConfigError",
            "ValueError",
            "TypeError",
            "JSONDecodeError",
        }:
            return 400
        return 500

    async def _tool_get_pet_status(self, args: dict) -> dict:
        try:
            def collect(pet):
                return {
                    "position": pet.api.get_position(),
                    "state": pet.api.get_state(),
                    "mode": pet.api.get_mode(),
                    "animations": pet.api.get_available_animations(),
                }
            return {"success": True, "data": await self._run_tool_pet(args, collect)}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_set_pet_mode(self, args: dict) -> dict:
        mode = args.get("mode")
        if mode not in ("random", "motion"):
            return self._tool_error(InstanceConfigError("Invalid mode"))
        try:
            success = await self._run_tool_pet(args, lambda pet: pet.api.set_mode(mode))
            return {"success": bool(success), "data": {"mode": mode}}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_move_pet_to(self, args: dict) -> dict:
        coords = self._validate_coordinates(args)
        if coords is None:
            return self._tool_error(InstanceConfigError("Invalid coordinates"))
        x, y = coords
        try:
            def move(pet):
                screen = self._parse_screen_index(args, pet)
                if screen == -1:
                    raise InstanceConfigError("screen index out of range")
                if pet.api.get_mode() != "motion":
                    pet.api.set_mode("motion")
                return pet.api.move_to(x, y, screen)
            success = await self._run_tool_pet(args, move)
            return {"success": bool(success), "data": {"x": x, "y": y}}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_move_pet_by(self, args: dict) -> dict:
        delta = self._validate_delta(args)
        if delta is None:
            return self._tool_error(InstanceConfigError("Invalid delta"))
        dx, dy = delta
        try:
            def move(pet):
                if pet.api.get_mode() != "motion":
                    pet.api.set_mode("motion")
                return pet.api.move_by(dx, dy)
            success = await self._run_tool_pet(args, move)
            return {"success": bool(success), "data": {"dx": dx, "dy": dy}}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_move_pet_to_edge(self, args: dict) -> dict:
        edge = args.get("edge")
        if edge not in ("left", "right"):
            return self._tool_error(InstanceConfigError("Invalid edge"))
        try:
            def move(pet):
                screen = self._parse_screen_index(args, pet)
                if screen == -1:
                    raise InstanceConfigError("screen index out of range")
                if pet.api.get_mode() != "motion":
                    pet.api.set_mode("motion")
                return pet.api.move_to_edge(edge, screen)
            success = await self._run_tool_pet(args, move)
            return {"success": bool(success), "data": {"edge": edge}}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_walk_pet(self, args: dict) -> dict:
        direction = args.get("direction")
        if direction not in ("left", "right"):
            return self._tool_error(InstanceConfigError("Invalid direction"))
        try:
            def walk(pet):
                screen = self._parse_screen_index(args, pet)
                if screen == -1:
                    raise InstanceConfigError("screen index out of range")
                if pet.api.get_mode() != "motion":
                    pet.api.set_mode("motion")
                return pet.api.play_walk(direction, screen)
            success = await self._run_tool_pet(args, walk)
            return {"success": bool(success), "data": {"direction": direction}}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_play_animation(self, args: dict) -> dict:
        name = args.get("name")
        if not isinstance(name, str) or not name:
            return self._tool_error(InstanceConfigError("Animation name required"))
        try:
            def play(pet):
                if pet.api.get_mode() != "motion":
                    pet.api.set_mode("motion")
                return pet.api.play_animation(name)
            success = await self._run_tool_pet(args, play)
            return {"success": bool(success), "data": {"animation": name}}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_get_screens(self, args: dict) -> dict:
        try:
            def collect(pet):
                sm = getattr(pet, "screen_manager", None)
                position = pet.api.get_position()
                return {
                    "screens": [screen.to_dict() for screen in sm.all_screens()] if sm else [],
                    "current_screen": position.get("screen", -1),
                }
            return {"success": True, "data": await self._run_tool_pet(args, collect)}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_show_message(self, args: dict) -> dict:
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            return self._tool_error(InstanceConfigError("text is required"))
        try:
            duration = int(args.get("duration", 5000))
        except (TypeError, ValueError):
            return self._tool_error(InstanceConfigError("duration must be an integer"))
        try:
            await self._run_tool_pet(
                args, lambda pet: pet.show_custom_bubble_requested.emit(text.strip(), duration)
            )
            return {"success": True, "data": {"text": text.strip(), "duration": duration}}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_get_user_messages(self, args: dict) -> dict:
        messages = list(self._user_messages)
        self._user_messages.clear()
        return {"success": True, "data": {"messages": messages}}

    async def _tool_show_chat_bubble(self, args: dict) -> dict:
        message = args.get("message", "")
        try:
            await self._run_tool_pet(
                args, lambda pet: pet.show_chat_bubble_requested.emit(str(message))
            )
            return {"success": True}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_hide_chat_bubble(self, args: dict) -> dict:
        try:
            await self._run_tool_pet(args, lambda pet: pet.hide_chat_bubble_requested.emit())
            return {"success": True}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_list_pets(self, args: dict) -> dict:
        try:
            def collect():
                instances = []
                for config in self._platform.list_instances():
                    widget = self._platform.get_pet_widget(config.pet_id)
                    instances.append({
                        "pet_id": config.pet_id,
                        "package": config.package,
                        "primary": config.primary,
                        "position": widget.api.get_position() if widget else config.position,
                        "state": widget.api.get_state() if widget else "unknown",
                        "size": config.size,
                    })
                return instances
            return {"success": True, "data": {"instances": await self._run_in_main_thread(collect)}}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_create_pet(self, args: dict) -> dict:
        package = args.get("package", "default")
        x, y = args.get("x"), args.get("y")
        if (x is None) != (y is None):
            return self._tool_error(InstanceConfigError("x and y must be provided together"))
        if x is None:
            position = None
        else:
            coords = self._validate_coordinates({"x": x, "y": y})
            if coords is None:
                return self._tool_error(InstanceConfigError("Invalid coordinates"))
            position = {"x": coords[0], "y": coords[1]}
        try:
            def create():
                pet_id = self._platform.create_instance(package, position)
                config = self._platform.get_instance_config(pet_id)
                return config.to_dict() if config else {"pet_id": pet_id}
            return {"success": True, "data": await self._run_in_main_thread(create)}
        except Exception as error:
            return self._tool_error(error)

    async def _tool_remove_pet(self, args: dict) -> dict:
        pet_id = args.get("pet_id")
        if not pet_id:
            return self._tool_error(InstanceConfigError("pet_id is required"))
        try:
            success = await self._run_in_main_thread(
                lambda: self._platform.destroy_instance(pet_id)
            )
            if not success:
                raise InstanceNotFoundError(f"pet not found: {pet_id}")
            return {"success": True, "data": {"pet_id": pet_id}}
        except Exception as error:
            return self._tool_error(error)

    # ========== LLM Chat with Function Calling ==========

    def _get_llm_config(self) -> dict:
        cm = getattr(self._platform, "global_config", None)
        if cm is None:
            return {}
        llm = getattr(cm, "llm", None)
        if llm is None:
            return {}
        return {
            "enabled": llm.enabled,
            "api_key": llm.api_key,
            "base_url": llm.base_url.rstrip("/"),
            "model": llm.model,
            "system_prompt": llm.system_prompt,
            "max_history": llm.max_history,
        }

    def _get_history(self, session_id: str, max_history: int) -> deque:
        """获取或创建对话历史"""
        if session_id not in self._chat_histories:
            self._chat_histories[session_id] = deque(maxlen=max_history)
        return self._chat_histories[session_id]

    async def handle_chat(self, request: Request) -> Response:
        """POST /api/chat - 通过 LLM function calling 控制宠物

        请求体格式：
        {
            "message": "让宠物坐下",      // 必填，用户消息
            "session_id": "default",      // 可选，会话ID（默认 "default"）
            "system_prompt": "...",        // 可选，覆盖默认系统提示
            "model": "...",               // 可选，覆盖默认模型
            "api_key": "...",             // 可选，覆盖配置中的 api_key
            "base_url": "...",            // 可选，覆盖配置中的 base_url
            "clear_history": false        // 可选，是否清除对话历史
        }
        """
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response(
                {"success": False, "error": "Invalid JSON body"},
                status=400,
            )

        message = data.get("message")
        if not isinstance(message, str) or not message.strip():
            return web.json_response(
                {"success": False, "error": "message is required"},
                status=400,
            )

        message = message.strip()

        # 获取 LLM 配置（请求参数可覆盖）
        llm_config = self._get_llm_config()
        if not llm_config.get("enabled"):
            return web.json_response(
                {"success": False, "error": "LLM is not enabled. Set llm.enabled=true in config."},
                status=400,
            )

        api_key = data.get("api_key") or llm_config.get("api_key", "")
        base_url = data.get("base_url") or llm_config.get("base_url", "https://api.openai.com/v1")
        model = data.get("model") or llm_config.get("model", "gpt-4o-mini")
        system_prompt = data.get("system_prompt") or llm_config.get("system_prompt", "")
        max_history = llm_config.get("max_history", 20)

        if not api_key:
            return web.json_response(
                {"success": False, "error": "LLM api_key is not configured"},
                status=400,
            )

        session_id = data.get("session_id", "default")

        # 清除历史
        if data.get("clear_history"):
            self._chat_histories.pop(session_id, None)

        history = self._get_history(session_id, max_history)

        # 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        # 构建工具定义
        tools = await self._run_in_main_thread(self._build_tools)

        # Function calling 循环
        tool_results = []
        max_iterations = 5  # 防止无限循环

        for iteration in range(max_iterations):
            # 调用 LLM
            try:
                llm_response = await self._call_llm(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    tools=tools,
                )
            except Exception as e:
                logger.error(f"LLM API call failed: {e}")
                return web.json_response(
                    {"success": False, "error": f"LLM API call failed: {str(e)}"},
                    status=500,
                )

            choice = llm_response.get("choices", [{}])[0]
            assistant_message = choice.get("message", {})

            # 将助手消息加入消息列表
            messages.append(assistant_message)

            # 检查是否有 tool_calls
            tool_calls = assistant_message.get("tool_calls")

            if not tool_calls:
                # LLM 没有调用工具，直接返回文本回复
                reply = assistant_message.get("content", "")

                # 保存对话历史
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": reply})

                return web.json_response({
                    "success": True,
                    "reply": reply,
                    "tool_calls": tool_results,
                    "model": model,
                    "session_id": session_id,
                })

            # 执行所有 tool_calls
            for tool_call in tool_calls:
                fn = tool_call.get("function", {})
                tool_name = fn.get("name", "")
                try:
                    tool_args = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}

                tool_call_id = tool_call.get("id", "")

                logger.info(f"[Chat] LLM calls tool: {tool_name}({tool_args})")

                # 执行工具
                handler = self._tool_handlers.get(tool_name)
                if handler:
                    try:
                        result = await handler(tool_args)
                    except Exception as e:
                        result = {"success": False, "error": str(e)}
                else:
                    result = {"success": False, "error": f"Unknown tool: {tool_name}"}

                tool_results.append({
                    "name": tool_name,
                    "arguments": tool_args,
                    "result": result,
                })

                # 将工具结果加入消息列表
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        # 超过最大迭代次数
        last_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                last_content = msg["content"]
                break

        history.append({"role": "user", "content": message})
        if last_content:
            history.append({"role": "assistant", "content": last_content})

        return web.json_response({
            "success": True,
            "reply": last_content or "工具调用次数已达上限",
            "tool_calls": tool_results,
            "model": model,
            "session_id": session_id,
        })

    async def _call_llm(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict],
        tools: list[dict],
    ) -> dict:
        """调用 OpenAI 兼容的 LLM API"""
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    raise RuntimeError(f"LLM API returned {response.status}: {text}")
                return await response.json()

    # ========== 消息交互端点 ==========

    async def _forward_to_openclaw(self, text: str, timestamp: str) -> None:
        """将用户消息 POST 到 OpenClaw openclaw-http-channel 插件的入站 webhook

        采用 openclaw-http-channel 入站协议：body 为 {from, text, chatType}。
        使用 httpx 异步发送，失败不影响桌宠主流程。

        注意：openclaw-http-channel 的 inbound handler 会立即返回 202（accepted），
        然后异步处理 agent turn。Agent 回复通过独立的出站 webhook 推送回来，
        不在此请求的响应中返回。超时设为 10 秒足够。
        """
        body = {
            "from": self._openclaw_peer,
            "text": text,
            "chatType": "direct",
        }
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._openclaw_webhook_url, json=body)
                if 200 <= resp.status_code < 300:
                    dispatched = resp.json().get("dispatched", True)
                    logger.info(
                        f"[OpenClaw] Message forwarded (dispatched={dispatched}): {text[:50]}"
                    )
                else:
                    logger.warning(
                        f"[OpenClaw] Webhook returned {resp.status_code}: {resp.text[:200]}"
                    )
        except Exception as e:
            logger.warning(f"[OpenClaw] Failed to forward message: {type(e).__name__}: {e!r}")

    def add_user_message(self, text: str) -> None:
        """将用户消息添加到队列并转发到 OpenClaw

        消息入队供 MCP get_user_messages 轮询，同时异步 POST 到
        OpenClaw pet-bubble channel webhook 触发实时 session turn。
        转发失败不影响桌宠主流程。
        """
        msg = {
            "text": text,
            "timestamp": datetime.now().isoformat(),
        }
        self._user_messages.append(msg)
        # 异步转发到 OpenClaw webhook（不阻塞 UI 线程）
        # 注意：add_user_message 在 Qt 主线程被调用（ChatBubble 信号槽），而
        # _openclaw_loop 是 API 子线程的事件循环。必须用 run_coroutine_threadsafe
        # 才能安全跨线程调度——ensure_future 用的 call_soon 非线程安全，
        # 不会唤醒目标 loop，导致协程被延迟到 loop 下次自然活动时才执行。
        if self._openclaw_loop and self._openclaw_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._forward_to_openclaw(text, msg["timestamp"]),
                loop=self._openclaw_loop,
            )
        else:
            logger.warning(f"[OpenClaw] Event loop not ready, message queued only. loop={self._openclaw_loop}")

    async def handle_show_message(self, request: Request) -> Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response({"success": False, "error": "Invalid JSON body"}, status=400)
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            return web.json_response({"success": False, "error": "text is required"}, status=400)
        try:
            duration = int(data.get("duration", 5000))
        except (TypeError, ValueError):
            return web.json_response({"success": False, "error": "duration must be an integer"}, status=400)
        try:
            await self._run_pet_operation(
                request, lambda pet: pet.show_custom_bubble_requested.emit(text.strip(), duration)
            )
            return web.json_response({"success": True, "text": text.strip(), "duration": duration})
        except Exception as error:
            return self._error_response(error)

    async def handle_hide_message(self, request: Request) -> Response:
        try:
            await self._run_pet_operation(
                request, lambda pet: pet.hide_custom_bubble_requested.emit()
            )
            return web.json_response({"success": True})
        except Exception as error:
            return self._error_response(error)

    async def handle_pending_messages(self, request: Request) -> Response:
        messages = list(self._user_messages)
        self._user_messages.clear()
        return web.json_response({"messages": messages})

    async def handle_send_message(self, request: Request) -> Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response({"success": False, "error": "Invalid JSON body"}, status=400)
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            return web.json_response({"success": False, "error": "text is required"}, status=400)
        self.add_user_message(text.strip())
        return web.json_response({"success": True, "text": text.strip()})

    async def handle_show_chat_bubble(self, request: Request) -> Response:
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            return web.json_response(
                {"success": False, "error": "Invalid JSON body"}, status=400
            )
        message = data.get("message")
        if not isinstance(message, str):
            return web.json_response(
                {"success": False, "error": "message must be a string"}, status=400
            )
        try:
            await self._run_pet_operation(
                request, lambda pet: pet.show_chat_bubble_requested.emit(message)
            )
            return web.json_response({"success": True})
        except Exception as error:
            return self._error_response(error)

    async def handle_hide_chat_bubble(self, request: Request) -> Response:
        try:
            await self._run_pet_operation(
                request, lambda pet: pet.hide_chat_bubble_requested.emit()
            )
            return web.json_response({"success": True})
        except Exception as error:
            return self._error_response(error)

    async def handle_openclaw_reply(self, request: Request) -> Response:
        """POST /api/openclaw/reply - 接收 OpenClaw Agent 回复

        作为 openclaw-http-channel 出站方向（B 层）的接收端：插件把 Agent 回复
        POST 到本端点，body 格式为 {channel, accountId, to, text, timestamp}，
        携带 ``X-HTTP-Channel-Secret`` header 做鉴权。

        收到回复后通过 ``show_chat_bubble_requested`` 信号投递到主线程 ChatBubble 显示。
        """
        # 1. 方法校验
        if request.method != "POST":
            logger.warning(f"[OpenClaw Reply] Rejected: method={request.method} (POST only)")
            return web.json_response(
                {"error": "Method Not Allowed"}, status=405
            )

        # 记录请求到达（全链路诊断）
        logger.info(
            f"[OpenClaw Reply] Received request: content_type={request.headers.get('Content-Type', '?')}, "
            f"has_secret_header={'X-HTTP-Channel-Secret' in request.headers}"
        )

        # 2. 鉴权：校验 X-HTTP-Channel-Secret header
        if self._openclaw_secret_token:
            secret = request.headers.get("X-HTTP-Channel-Secret", "")
            if secret != self._openclaw_secret_token:
                logger.warning("[OpenClaw Reply] Rejected: secret token mismatch")
                return web.json_response(
                    {"error": "Invalid secret token"}, status=401
                )

        # 3. 解析 body
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise InstanceConfigError("JSON body must be an object")
        except Exception:
            logger.warning("[OpenClaw Reply] Rejected: invalid JSON body")
            return web.json_response(
                {"error": "Invalid JSON body"}, status=400
            )

        text = data.get("text", "")
        if not isinstance(text, str) or not text.strip():
            logger.warning(f"[OpenClaw Reply] Rejected: text missing or empty, got {type(text).__name__}")
            return web.json_response(
                {
                    "error": "Payload must be { to?: string, text: string, ... }"
                },
                status=400,
            )
        text = text.strip()

        # OpenClaw peer targets the current primary pet.
        try:
            def show_reply():
                pet = self._resolve_pet_sync()
                if pet is None:
                    raise InstanceNotFoundError("pet not found: primary")
                pet.show_chat_bubble_requested.emit(text)
            await self._run_in_main_thread(show_reply)
        except Exception as error:
            return self._error_response(error)
        return web.json_response({"received": True})
