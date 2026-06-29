"""Desktop Pet MCP Server — 动态发现模式

自动从宠物 API 获取可用工具列表，桌宠新增功能后 MCP 零改动即可使用。

运行方式：uv run desktop-pet-mcp（stdio 模式）
前置条件：桌面宠物应用已启动且 API 服务器在运行（默认 http://127.0.0.1:8080）
"""

import asyncio
import json
import logging
import os
import time
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    TextContent,
    Tool,
)

logger = logging.getLogger(__name__)

PET_API_BASE = os.environ.get("PET_API_BASE", "http://127.0.0.1:8080/api")

server = Server("desktop-pet")

# ── 工具缓存 ──────────────────────────────────────────────

_tools_cache: list[dict] | None = None
_tools_cache_time: float = 0
_TOOLS_CACHE_TTL = 30  # 缓存 30 秒


async def _fetch_tools() -> list[dict]:
    """从宠物 API 获取可用工具列表（带缓存）"""
    global _tools_cache, _tools_cache_time
    now = time.time()
    if _tools_cache is not None and (now - _tools_cache_time) < _TOOLS_CACHE_TTL:
        return _tools_cache

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{PET_API_BASE}/tools")
            data = resp.json()
            _tools_cache = data.get("tools", [])
            _tools_cache_time = now
            return _tools_cache
    except Exception as e:
        logger.warning(f"Failed to fetch tools from pet API: {e}")
        if _tools_cache is not None:
            return _tools_cache
        return []


# ── MCP 协议处理 ──────────────────────────────────────────


@server.list_tools()
async def list_tools() -> list[Tool]:
    """动态获取宠物可用工具列表"""
    raw_tools = await _fetch_tools()
    tools = []
    for t in raw_tools:
        func = t.get("function", {})
        name = func.get("name")
        if not name:
            continue
        tools.append(Tool(
            name=name,
            description=func.get("description", ""),
            inputSchema=func.get("parameters", {
                "type": "object",
                "properties": {},
                "required": [],
            }),
        ))
    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> list[TextContent]:
    """统一转发工具调用到宠物 API"""
    arguments = arguments or {}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{PET_API_BASE}/tools/call",
                json={"name": name, "arguments": arguments},
            )
            result = resp.json()
    except httpx.ConnectError:
        return [TextContent(
            type="text",
            text="无法连接到桌面宠物 API，请确保宠物应用已启动",
        )]
    except Exception as e:
        return [TextContent(type="text", text=f"调用失败: {e}")]

    if result.get("success"):
        data = result.get("data", result)
        if isinstance(data, dict):
            text = json.dumps(data, ensure_ascii=False, indent=2)
        else:
            text = str(data)
        return [TextContent(type="text", text=text)]
    else:
        error = result.get("error", "未知错误")
        return [TextContent(type="text", text=f"操作失败: {error}")]


@server.list_resources()
async def list_resources() -> list:
    """列出宠物资源"""
    from mcp.types import Resource, ResourceTemplate
    return [
        Resource(
            uri="pet://status",
            name="pet_status",
            description="桌面宠物当前状态（位置、模式、动画等）",
            mimeType="application/json",
        )
    ]


@server.read_resource()
async def read_resource(uri) -> str:
    """读取宠物资源"""
    uri_str = str(uri)
    if uri_str == "pet://status":
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{PET_API_BASE}/tools/call",
                    json={"name": "get_pet_status", "arguments": {}},
                )
                result = resp.json()
                data = result.get("data", result)
                return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps({"error": f"Unknown resource: {uri_str}"})


@server.list_prompts()
async def list_prompts() -> list:
    """列出可用提示词"""
    from mcp.types import Prompt
    return [
        Prompt(
            name="control_pet",
            description="控制桌面宠物的提示词模板",
            arguments=[],
        )
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict | None = None) -> str:
    """获取提示词"""
    if name == "control_pet":
        return (
            "你是一个桌面宠物的控制助手。你可以通过以下方式与宠物交互：\n"
            "\n"
            "1. 控制宠物行为：移动、播放动画、切换模式等\n"
            "2. 向用户展示消息：通过 show_message 在宠物旁显示气泡文字\n"
            "3. 接收用户消息：通过 get_user_messages 获取用户在宠物气泡中输入的内容\n"
            "4. 交互式对话：通过 show_chat_bubble 显示可输入的聊天气泡\n"
            "\n"
            "请根据用户的需求，调用合适的工具来控制宠物或与用户交互。\n"
            "回复时请使用中文。"
        )
    return f"Unknown prompt: {name}"


# ── 入口 ───────────────────────────────────────────────────


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
