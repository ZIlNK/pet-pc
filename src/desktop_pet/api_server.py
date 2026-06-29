import asyncio
import ipaddress
import json
import logging
import os
from collections import deque
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from aiohttp import web
from aiohttp.web import Request, Response

from .motion_controller import MotionModeController

logger = logging.getLogger(__name__)

# ── OpenClaw pet-bubble channel webhook（简化方案 v0.4） ─────────
# 桌宠用户消息直接 POST 到 OpenClaw channel plugin webhook，无需文件钩子。
DEFAULT_OPENCLAW_WEBHOOK_URL = "http://127.0.0.1:18789/pet-bubble-webhook"
DEFAULT_OPENCLAW_PEER = "boss"


class ApiServer:
    def __init__(self, pet):
        self._pet = pet
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._running = False
        self._host = "127.0.0.1"
        self._port = 8080
        self._allowed_ips: list[str] = ["127.0.0.1", "::1"]
        self._trust_proxy_headers = False
        # LLM 对话历史（按 session_id 隔离）
        self._chat_histories: dict[str, deque] = {}
        # 用户消息队列（来自 ChatBubble 的用户输入）
        self._user_messages: deque = deque(maxlen=100)
        # OpenClaw pet-bubble channel 配置
        self._openclaw_webhook_url = DEFAULT_OPENCLAW_WEBHOOK_URL
        self._openclaw_peer = DEFAULT_OPENCLAW_PEER
        self._openclaw_loop: Optional[asyncio.AbstractEventLoop] = None

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

    def set_openclaw_config(self, webhook_url: str, peer: str) -> None:
        """配置 OpenClaw pet-bubble channel webhook 地址和 peer"""
        if webhook_url:
            self._openclaw_webhook_url = webhook_url
        if peer:
            self._openclaw_peer = peer

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
            self._openclaw_loop = asyncio.get_running_loop()
            logger.info(f"API server started: http://{self._host}:{self._port}")
            logger.info(f"IP whitelist: {self._allowed_ips}")
            logger.info(f"OpenClaw webhook: {self._openclaw_webhook_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
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
        logger.info("API server stopped")
        return True

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

        self._app.router.add_get("/api/status", self.handle_status)
        self._app.router.add_get("/api/screens", self.handle_screens)
        self._app.router.add_post("/api/mode", self.handle_mode)
        self._app.router.add_post("/api/move", self.handle_move)
        self._app.router.add_post("/api/move_by", self.handle_move_by)
        self._app.router.add_post("/api/move_edge", self.handle_move_edge)
        self._app.router.add_post("/api/animation", self.handle_animation)
        self._app.router.add_post("/api/walk", self.handle_walk)
        self._app.router.add_get("/api/animations", self.handle_animations_list)

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
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return response

        self._app.middlewares.append(cors_middleware)

    def _validate_coordinates(self, data: dict) -> tuple[int, int] | None:
        """Validate and sanitize coordinate values."""
        try:
            x = int(data.get("x", 0))
            y = int(data.get("y", 0))

            # Basic sanity check (negative coords allowed for off-screen moves)
            if x < -10000 or x > 10000 or y < -10000 or y > 10000:
                return None

            return x, y
        except (ValueError, TypeError):
            return None

    def _validate_delta(self, data: dict) -> tuple[int, int] | None:
        """Validate movement delta values."""
        try:
            dx = int(data.get("dx", 0))
            dy = int(data.get("dy", 0))
            return dx, dy
        except (ValueError, TypeError):
            return None

    def _parse_screen_index(self, data: dict) -> int | None:
        """从请求数据中解析 screen 字段(可选)。

        - 缺省 / null / 非法类型:返回 None(自动按坐标选屏)
        - 整数:返回 int(越界由调用方处理)
        - 越界整数:返回 -1(标记为非法,调用方返回 400)
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
        sm = getattr(self._pet, "screen_manager", None)
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

    async def handle_status(self, request: Request) -> Response:
        position = self._pet.api.get_position()
        state = self._pet.api.get_state()
        mode = self._pet.api.get_mode()
        animations = self._pet.api.get_available_animations()

        screens = []
        current_screen = position.get("screen", -1)
        sm = getattr(self._pet, "screen_manager", None)
        if sm is not None:
            try:
                screens = [s.to_dict() for s in sm.all_screens()]
            except Exception:
                screens = []

        return web.json_response({
            "position": position,
            "state": state,
            "mode": mode,
            "animations": animations,
            "current_screen": current_screen,
            "screens": screens,
        })

    async def handle_screens(self, request: Request) -> Response:
        sm = getattr(self._pet, "screen_manager", None)
        if sm is None:
            return web.json_response({"screens": [], "current_screen": -1})
        try:
            screens = [s.to_dict() for s in sm.all_screens()]
        except Exception:
            screens = []
        pos = self._pet.api.get_position()
        return web.json_response({
            "screens": screens,
            "current_screen": pos.get("screen", -1),
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
            coords = self._validate_coordinates(data)
            if coords is None:
                return web.json_response({"success": False, "error": "Invalid coordinates"}, status=400)

            x, y = coords
            screen = self._parse_screen_index(data)
            if screen == -1:
                return web.json_response({"success": False, "error": "screen index out of range"}, status=400)

            if self._pet.api.get_mode() != "motion":
                self._pet.api.set_mode("motion")

            success = self._pet.api.move_to(x, y, screen)
            return web.json_response({"success": success})
        except Exception as e:
            return web.json_response({"success": False, "error": str(e)}, status=400)

    async def handle_move_by(self, request: Request) -> Response:
        try:
            data = await request.json()
            delta = self._validate_delta(data)
            if delta is None:
                return web.json_response({"success": False, "error": "Invalid delta values"}, status=400)

            dx, dy = delta

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

            screen = self._parse_screen_index(data)
            if screen == -1:
                return web.json_response({"success": False, "error": "screen index out of range"}, status=400)

            if self._pet.api.get_mode() != "motion":
                self._pet.api.set_mode("motion")

            success = self._pet.api.move_to_edge(edge, screen)
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
                if not self._is_safe_callback_url(callback_url):
                    logger.warning(f"Unsafe callback URL rejected: {callback_url}")
                else:
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

            screen = self._parse_screen_index(data)
            if screen == -1:
                return web.json_response({"success": False, "error": "screen index out of range"}, status=400)

            if self._pet.api.get_mode() != "motion":
                self._pet.api.set_mode("motion")

            success = self._pet.api.play_walk(direction, screen)
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
                        logger.info(f"Animation callback success: {animation_name} -> {callback_url}")
                    else:
                        logger.warning(f"Animation callback failed with status: {response.status}")
        except asyncio.TimeoutError:
            logger.warning(f"Animation callback timeout: {animation_name} -> {callback_url}")
        except Exception as e:
            logger.error(f"Animation callback failed: {animation_name} -> {callback_url}, error: {e}")

    # ========== AI Tool-Calling ==========

    def _build_tools(self) -> list[dict]:
        """构建 AI 可调用的工具定义列表（OpenAI function calling 格式）。

        包含固定的控制类工具和动态的宠物动画动作工具。
        """
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_pet_status",
                    "description": "获取桌面宠物的当前状态，包括位置、状态、模式和可用动画列表",
                    "parameters": {
                        "type": "object",
                        "properties": {},
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
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ]

        # 动态添加宠物动画动作工具
        animations = self._pet.api.get_available_animations()
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
                    "properties": {},
                    "required": [],
                },
            },
        })

        return tools

    async def handle_tools_list(self, request: Request) -> Response:
        """GET /api/tools - 返回 AI 可调用的工具定义列表"""
        tools = self._build_tools()
        return web.json_response({"tools": tools})

    async def handle_tools_call(self, request: Request) -> Response:
        """POST /api/tools/call - 执行 AI 工具调用

        请求体格式：
        {
            "name": "工具名称",
            "arguments": { ... }  // 可选
        }
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"success": False, "error": "Invalid JSON body"},
                status=400,
            )

        tool_name = data.get("name")
        arguments = data.get("arguments", {})

        if not tool_name:
            return web.json_response(
                {"success": False, "error": "Tool name is required"},
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
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Tool call error: {tool_name} -> {e}")
            return web.json_response(
                {"success": False, "error": str(e)},
                status=500,
            )

    @property
    def _tool_handlers(self) -> dict:
        """工具名到处理函数的映射"""
        return {
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

    async def _tool_get_pet_status(self, args: dict) -> dict:
        position = self._pet.api.get_position()
        state = self._pet.api.get_state()
        mode = self._pet.api.get_mode()
        animations = self._pet.api.get_available_animations()

        screens = []
        current_screen = position.get("screen", -1)
        sm = getattr(self._pet, "screen_manager", None)
        if sm is not None:
            try:
                screens = [s.to_dict() for s in sm.all_screens()]
            except Exception:
                screens = []

        return {
            "success": True,
            "data": {
                "position": position,
                "state": state,
                "mode": mode,
                "animations": animations,
                "current_screen": current_screen,
                "screens": screens,
            },
        }

    async def _tool_set_pet_mode(self, args: dict) -> dict:
        mode = args.get("mode")
        if mode not in ("random", "motion"):
            return {"success": False, "error": "Invalid mode, must be 'random' or 'motion'"}

        success = self._pet.api.set_mode(mode)
        return {"success": success, "data": {"mode": mode}}

    async def _tool_move_pet_to(self, args: dict) -> dict:
        coords = self._validate_coordinates(args)
        if coords is None:
            return {"success": False, "error": "Invalid coordinates"}

        x, y = coords
        screen = self._parse_screen_index(args)
        if screen == -1:
            return {"success": False, "error": "Screen index out of range"}

        if self._pet.api.get_mode() != "motion":
            self._pet.api.set_mode("motion")

        success = self._pet.api.move_to(x, y, screen)
        return {"success": success, "data": {"x": x, "y": y, "screen": screen}}

    async def _tool_move_pet_by(self, args: dict) -> dict:
        delta = self._validate_delta(args)
        if delta is None:
            return {"success": False, "error": "Invalid delta values"}

        dx, dy = delta
        if self._pet.api.get_mode() != "motion":
            self._pet.api.set_mode("motion")

        success = self._pet.api.move_by(dx, dy)
        return {"success": success, "data": {"dx": dx, "dy": dy}}

    async def _tool_move_pet_to_edge(self, args: dict) -> dict:
        edge = args.get("edge")
        if edge not in ("left", "right"):
            return {"success": False, "error": "Invalid edge, must be 'left' or 'right'"}

        screen = self._parse_screen_index(args)
        if screen == -1:
            return {"success": False, "error": "Screen index out of range"}

        if self._pet.api.get_mode() != "motion":
            self._pet.api.set_mode("motion")

        success = self._pet.api.move_to_edge(edge, screen)
        return {"success": success, "data": {"edge": edge, "screen": screen}}

    async def _tool_walk_pet(self, args: dict) -> dict:
        direction = args.get("direction")
        if direction not in ("left", "right"):
            return {"success": False, "error": "Invalid direction, must be 'left' or 'right'"}

        screen = self._parse_screen_index(args)
        if screen == -1:
            return {"success": False, "error": "Screen index out of range"}

        if self._pet.api.get_mode() != "motion":
            self._pet.api.set_mode("motion")

        success = self._pet.api.play_walk(direction, screen)
        return {"success": success, "data": {"direction": direction, "screen": screen}}

    async def _tool_play_animation(self, args: dict) -> dict:
        name = args.get("name")
        if not name:
            return {"success": False, "error": "Animation name is required"}

        if self._pet.api.get_mode() != "motion":
            self._pet.api.set_mode("motion")

        success = self._pet.api.play_animation(name)
        if success:
            return {"success": True, "data": {"animation": name}}
        else:
            available = self._pet.api.get_available_animations()
            return {
                "success": False,
                "error": f"Animation '{name}' not found or not available",
                "data": {"available_animations": available},
            }

    async def _tool_get_screens(self, args: dict) -> dict:
        sm = getattr(self._pet, "screen_manager", None)
        if sm is None:
            return {"success": True, "data": {"screens": [], "current_screen": -1}}

        try:
            screens = [s.to_dict() for s in sm.all_screens()]
        except Exception:
            screens = []

        pos = self._pet.api.get_position()
        return {
            "success": True,
            "data": {
                "screens": screens,
                "current_screen": pos.get("screen", -1),
            },
        }

    async def _tool_show_message(self, args: dict) -> dict:
        text = args.get("text", "").strip()
        if not text:
            return {"success": False, "error": "text is required"}
        duration = args.get("duration", 5000)
        try:
            duration = int(duration)
        except (ValueError, TypeError):
            duration = 5000
        from PyQt6.QtCore import QTimer
        self._pet.show_custom_bubble_requested.emit(text, duration)
        return {"success": True, "data": {"text": text, "duration": duration}}

    async def _tool_get_user_messages(self, args: dict) -> dict:
        messages = list(self._user_messages)
        self._user_messages.clear()
        return {"success": True, "data": {"messages": messages}}

    async def _tool_show_chat_bubble(self, args: dict) -> dict:
        message = args.get("message", "")
        # 修复：QTimer.singleShot 在子线程的 asyncio loop 里不触发。
        # 改用 Qt signal 跨线程投递（QueuedConnection 自动路由到主线程）
        self._pet.show_chat_bubble_requested.emit(message)
        return {"success": True}

    async def _tool_hide_chat_bubble(self, args: dict) -> dict:
        # 修复：QTimer.singleShot 在子线程的 asyncio loop 里不触发。
        # 改用 Qt signal 跨线程投递（QueuedConnection 自动路由到主线程）
        self._pet.hide_chat_bubble_requested.emit()
        return {"success": True}

    # ========== LLM Chat with Function Calling ==========

    def _get_llm_config(self) -> dict:
        """从 ConfigManager 获取 LLM 配置"""
        cm = getattr(self._pet, "config_manager", None)
        if cm is None:
            return {}
        llm = cm.llm
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
        except Exception:
            return web.json_response(
                {"success": False, "error": "Invalid JSON body"},
                status=400,
            )

        message = data.get("message", "").strip()
        if not message:
            return web.json_response(
                {"success": False, "error": "message is required"},
                status=400,
            )

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
        tools = self._build_tools()

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
        """将用户消息直接 POST 到 OpenClaw pet-bubble channel webhook

        使用 httpx 异步发送，失败不影响桌宠主流程。
        """
        body = {
            "text": text,
            "peer": self._openclaw_peer,
            "timestamp": timestamp,
            "metadata": {"source": "pet-bubble"},
        }
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(self._openclaw_webhook_url, json=body)
                if resp.status_code == 200:
                    logger.info(f"[OpenClaw] Message forwarded: {text[:50]}")
                else:
                    logger.warning(
                        f"[OpenClaw] Webhook returned {resp.status_code}: {resp.text[:200]}"
                    )
        except Exception as e:
            logger.warning(f"[OpenClaw] Failed to forward message: {e}")

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
        if self._openclaw_loop and self._openclaw_loop.is_running():
            asyncio.ensure_future(
                self._forward_to_openclaw(text, msg["timestamp"]),
                loop=self._openclaw_loop,
            )
        else:
            logger.debug("[OpenClaw] Event loop not ready, message queued only")

    async def handle_show_message(self, request: Request) -> Response:
        """POST /api/message - 在宠物旁显示气泡消息

        请求体：{"text": "消息内容", "duration": 5000}
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"success": False, "error": "Invalid JSON body"}, status=400
            )

        text = data.get("text", "").strip()
        if not text:
            return web.json_response(
                {"success": False, "error": "text is required"}, status=400
            )

        duration = data.get("duration", 5000)
        try:
            duration = int(duration)
        except (ValueError, TypeError):
            duration = 5000

        # 通过 QTimer 在主线程中显示气泡
        from PyQt6.QtCore import QTimer
        self._pet.show_custom_bubble_requested.emit(text, duration)

        return web.json_response({"success": True, "text": text, "duration": duration})

    async def handle_pending_messages(self, request: Request) -> Response:
        """GET /api/messages/pending - 获取并清空用户消息队列"""
        messages = list(self._user_messages)
        self._user_messages.clear()
        return web.json_response({"messages": messages})

    async def handle_send_message(self, request: Request) -> Response:
        """POST /api/messages/send - 将消息添加到用户消息队列

        请求体：{"text": "用户消息"}
        """
        try:
            data = await request.json()
        except Exception:
            return web.json_response(
                {"success": False, "error": "Invalid JSON body"}, status=400
            )

        text = data.get("text", "").strip()
        if not text:
            return web.json_response(
                {"success": False, "error": "text is required"}, status=400
            )

        self.add_user_message(text)
        return web.json_response({"success": True, "text": text})

    async def handle_show_chat_bubble(self, request: Request) -> Response:
        """POST /api/chat_bubble/show - 显示可交互的聊天气泡

        请求体：{"message": "初始消息"}
        """
        try:
            data = await request.json()
        except Exception:
            data = {}

        message = data.get("message", "")

        # 修复：QTimer.singleShot 在子线程的 asyncio loop 里不触发。
        # 改用 Qt signal 跨线程投递（QueuedConnection 自动路由到主线程）
        self._pet.show_chat_bubble_requested.emit(message)

        return web.json_response({"success": True})

    async def handle_hide_chat_bubble(self, request: Request) -> Response:
        """POST /api/chat_bubble/hide - 隐藏聊天气泡"""
        from PyQt6.QtCore import QTimer
        self._pet.hide_chat_bubble_requested.emit()

        return web.json_response({"success": True})
