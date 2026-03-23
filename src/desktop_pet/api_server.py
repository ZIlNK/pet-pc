import asyncio
import json
from datetime import datetime
from typing import Optional

import aiohttp
from aiohttp import web
from aiohttp.web import Request, Response

from .motion_controller import MotionModeController


class ApiServer:
    def __init__(self, pet):
        self._pet = pet
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._running = False
        self._host = "0.0.0.0"
        self._port = 8080
        self._allowed_ips: list[str] = ["127.0.0.1", "::1"]

    def configure(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    def set_allowed_ips(self, ips: list[str]) -> None:
        self._allowed_ips = ips

    def add_allowed_ip(self, ip: str) -> None:
        if ip not in self._allowed_ips:
            self._allowed_ips.append(ip)

    def remove_allowed_ip(self, ip: str) -> None:
        if ip in self._allowed_ips:
            self._allowed_ips.remove(ip)

    def get_allowed_ips(self) -> list[str]:
        return self._allowed_ips.copy()

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> bool:
        if self._running:
            return True

        self._app = web.Application()
        self._setup_ip_filter()
        self._setup_routes()
        self._setup_cors()

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, self._host, self._port)
        try:
            await self._site.start()
            self._running = True
            print(f"API 服务器已启动: http://{self._host}:{self._port}")
            print(f"IP 白名单: {self._allowed_ips}")
            return True
        except Exception as e:
            print(f"启动 API 服务器失败: {e}")
            return False

    async def stop(self) -> bool:
        if not self._running:
            return True

        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

        self._running = False
        self._app = None
        self._runner = None
        self._site = None
        print("API 服务器已停止")
        return True

    def _setup_ip_filter(self) -> None:
        if self._app is None:
            return

        @web.middleware
        async def ip_filter_middleware(request: Request, handler):
            client_ip = request.remote
            if client_ip is None:
                client_ip = request.client_ip if hasattr(request, 'client_ip') else "unknown"

            if client_ip not in self._allowed_ips:
                print(f"拒绝访问: IP {client_ip} 不在白名单中")
                return web.json_response(
                    {"success": False, "error": "Access denied"},
                    status=403
                )

            return await handler(request)

        self._app.middlewares.append(ip_filter_middleware)

    def _setup_routes(self) -> None:
        if self._app is None:
            return

        self._app.router.add_get("/api/status", self.handle_status)
        self._app.router.add_post("/api/mode", self.handle_mode)
        self._app.router.add_post("/api/move", self.handle_move)
        self._app.router.add_post("/api/move_by", self.handle_move_by)
        self._app.router.add_post("/api/move_edge", self.handle_move_edge)
        self._app.router.add_post("/api/animation", self.handle_animation)
        self._app.router.add_post("/api/walk", self.handle_walk)
        self._app.router.add_get("/api/animations", self.handle_animations_list)

    def _setup_cors(self) -> None:
        if self._app is None:
            return

        async def cors_middleware(app, handler):
            async def middleware(request):
                if request.method == "OPTIONS":
                    response = Response()
                    response.headers["Access-Control-Allow-Origin"] = "*"
                    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
                    return response
                response = await handler(request)
                response.headers["Access-Control-Allow-Origin"] = "*"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type"
                return response
            return middleware

        self._app.middlewares.append(cors_middleware)

    async def handle_status(self, request: Request) -> Response:
        position = self._pet.api.get_position()
        state = self._pet.api.get_state()
        mode = self._pet.api.get_mode()
        animations = self._pet.api.get_available_animations()

        return web.json_response({
            "position": position,
            "state": state,
            "mode": mode,
            "animations": animations
        })

    async def handle_mode(self, request: Request) -> Response:
        try:
            data = await request.json()
            mode = data.get("mode")
            if mode not in ("random", "motion"):
                return web.json_response({"success": False, "error": "Invalid mode"}, status=400)

            success = self._pet.api.set_mode(mode)
            return web.json_response({"success": success})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def handle_move(self, request: Request) -> Response:
        try:
            data = await request.json()
            x = data.get("x", 0)
            y = data.get("y", 0)

            if self._pet.api.get_mode() != "motion":
                self._pet.api.set_mode("motion")

            success = self._pet.api.move_to(x, y)
            return web.json_response({"success": success})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def handle_move_by(self, request: Request) -> Response:
        try:
            data = await request.json()
            dx = data.get("dx", 0)
            dy = data.get("dy", 0)

            if self._pet.api.get_mode() != "motion":
                self._pet.api.set_mode("motion")

            success = self._pet.api.move_by(dx, dy)
            return web.json_response({"success": success})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def handle_move_edge(self, request: Request) -> Response:
        try:
            data = await request.json()
            edge = data.get("edge")

            if edge not in ("left", "right"):
                return web.json_response({"success": False, "error": "Invalid edge"}, status=400)

            if self._pet.api.get_mode() != "motion":
                self._pet.api.set_mode("motion")

            success = self._pet.api.move_to_edge(edge)
            return web.json_response({"success": success})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def handle_animation(self, request: Request) -> Response:
        try:
            data = await request.json()
            name = data.get("name")
            callback_url = data.get("callback_url")

            if not name:
                return web.json_response({"success": False, "error": "Animation name required"}, status=400)

            if self._pet.api.get_mode() != "motion":
                self._pet.api.set_mode("motion")

            success = self._pet.api.play_animation(name)

            if success and callback_url:
                asyncio.create_task(self._send_animation_callback(name, callback_url))

            return web.json_response({"success": success, "animation": name})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def handle_walk(self, request: Request) -> Response:
        try:
            data = await request.json()
            direction = data.get("direction")

            if direction not in ("left", "right"):
                return web.json_response({"success": False, "error": "Invalid direction"}, status=400)

            if self._pet.api.get_mode() != "motion":
                self._pet.api.set_mode("motion")

            success = self._pet.api.play_walk(direction)
            return web.json_response({"success": success})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def handle_animations_list(self, request: Request) -> Response:
        animations = self._pet.api.get_available_animations()
        return web.json_response({"animations": animations})

    async def _send_animation_callback(self, animation_name: str, callback_url: str) -> None:
        if not callback_url:
            return

        payload = {
            "event": "animation_completed",
            "animation": animation_name,
            "position": self._pet.api.get_position(),
            "timestamp": datetime.now().isoformat() + "Z"
        }

        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(callback_url, json=payload) as response:
                    if response.status == 200:
                        print(f"动画回调成功: {animation_name} -> {callback_url}")
                    else:
                        print(f"动画回调响应异常: {response.status}")
        except asyncio.TimeoutError:
            print(f"动画回调超时: {animation_name} -> {callback_url}")
        except Exception as e:
            print(f"动画回调失败: {animation_name} -> {callback_url}, error: {e}")
