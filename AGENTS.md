# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Desktop Pet (桌面宠物) is a PyQt6-based desktop pet application with animations, rest reminders, and HTTP API remote control capabilities. The project supports multiple pet "packages" with different animations and behaviors.

经过平台化重构，项目现已升级为**多桌宠平台**：

- 支持同时运行多个桌宠实例，每个实例由 `PetPackage` 实例化而来，拥有独立的配置（actions / rest_reminder / movement / behavior / motion_mode / click_detection / position / size 等）
- `PetPlatform`（`pet_platform.py`）作为顶层容器，统一管理实例的创建、销毁、列举与持久化生命周期
- 共享组件（`ApiServer` / `SystemTray` / `ScreenManager` / `GlobalConfigManager`）由平台持有，被所有实例复用
- 向后兼容：单实例旧版配置（`user_config.json` 的 `app.current_pet`）会自动迁移为 `instances.json` 中的实例

## Commands

### Run the application
```bash
uv run desktop-pet
# or
uv run python -m desktop_pet
```

### CLI 子命令（控制正在运行的桌宠平台）

主进程启动后，可通过子命令行新增桌宠实例、查看现有实例、控制指定桌宠播放动画或移动：

```bash
# 新增运行桌宠（需主进程已启动）
uv run desktop-pet add --package default --x 500 --y 300

# 列出当前运行中实例
uv run desktop-pet list

# 关闭并销毁指定桌宠实例（默认需确认，--yes 跳过）
uv run desktop-pet remove <pet_id>            # 交互式确认
uv run desktop-pet remove <pet_id> --yes      # 直接销毁，不确认

# 控制指定桌宠（需主进程已启动，pet_id 通过 list 获取）
uv run desktop-pet animate <pet_id> --name sit           # 播放动画
uv run desktop-pet walk <pet_id> --direction left        # 行走动画
uv run desktop-pet move <pet_id> --xy 500 300            # 移动到绝对坐标
uv run desktop-pet move <pet_id> --delta 50 0            # 相对移动
uv run desktop-pet move <pet_id> --edge left             # 移到屏幕边缘
uv run desktop-pet animations <pet_id>                   # 列出可用动画
uv run desktop-pet bubble <pet_id> --text "你好"          # 显示文字气泡（持续）
uv run desktop-pet bubble <pet_id> --text "提示" --duration 3000  # 3秒后自动隐藏
uv run desktop-pet bubble <pet_id> --hide                # 隐藏文字气泡
```

> **注意**：
> - 子命令通过本地 HTTP API 与主进程通信，主进程未运行时报错并提示先启动 `desktop-pet`
> - `--hidden` 短选项从 `-h` 改为 `-H`（避免与 argparse 默认的 `-h` help 冲突）
> - 无子命令时仍为启动 GUI（向后兼容）
> - `move` 子命令的 `--xy` / `--delta` / `--edge` 三种模式互斥，必选其一

### Install dependencies
```bash
uv sync
```

### Install dev dependencies (for green screen tools)
```bash
uv sync --group dev
```

### Run green screen to GIF tool (GUI)
```bash
uv run python scripts/green_screen_to_webp_gui.py
```

### Run green screen to GIF tool (CLI)
```bash
uv run python scripts/green_screen_to_Webp.py input.mp4 -o output.gif --width 200 --height 159
```

## Architecture

### Core Components

#### 平台层（多实例管理）

- **`PetPlatform`** (`pet_platform.py`): 多桌宠平台顶层容器。管理实例的创建、销毁、列举、持久化。持有共享组件（`ApiServer` / `SystemTray` / `ScreenManager` / `GlobalConfigManager`），并提供 widget 工厂注入点。负责从旧版 `user_config.json` 的 `app.current_pet` 向 `instances.json` 的向后兼容迁移。

- **`PetInstanceConfig`** (`pet_instance.py`): 单个桌宠实例的配置数据模型。包含 `pet_id` / `package` / `position` / `size` / `actions` / `rest_reminder` / `movement` / `behavior` / `motion_mode` / `click_detection` 等独立配置。支持从 `PetPackage` 默认值构建、序列化为 dict / 从 dict 反序列化、生成短 UUID 形式的 `pet_id`。

- **`InstancesStore`** (`instances_store.py`): 实例配置持久化。读写 `config/instances.json`，提供 CRUD 接口。文件不存在或损坏时返回空列表，不抛异常。

- **`GlobalConfigManager`** (`config_manager.py`): 全局配置管理器。仅管理 `api` / `tray` / `startup` / `display` / `mcp` / `llm` 等全局共享配置，不再持有实例级配置（实例配置由 `InstancesStore` + `PetInstanceConfig` 管理）。

#### 实例层（widget 与控制）

- **`DesktopPet`** (`pet.py`): 实例 widget 类，处理 UI、鼠标事件、动画，并协调各组件。管理宠物状态机（IDLE, DRAGGING, FALLING, INERTIA, REST_REMINDER, MOTION_MODE, ANIMATING）。**双模式运行**：
  - 新模式（平台下运行）：构造函数接受 `PetInstanceConfig` + `PetPackage` + `PetPlatform`，由平台统一管理生命周期
  - 旧模式（独立运行，向后兼容）：未传入平台时退化为单实例独立运行

- **`ConfigManager`** (`config_manager.py`): 旧版配置加载器， Loads and merges `default_config.json` with `user_config.json`. Provides typed config objects (ActionConfig, RestReminderConfig, MovementConfig, PetConfig). 平台化后实例级配置由 `PetInstanceConfig` 接管，但保留用于向后兼容。

- **`PetLoader`** (`pet_loader.py`): 加载并校验 `PetPackage`。从 `pets/` 目录加载宠物包，每个包包含 `meta.json`、`animations/` 目录和可选的 `config/actions.json`。平台化后职责收窄，**仅负责包的加载与校验，不再维护 `_current_pet` 状态**。

- **`MotionModeController`** (`motion_controller.py`): PyQt signal-based controller for API-driven pet control. Emits signals that `DesktopPet` connects to for movement/animation actions.

- **`ApiServer`** (`api_server.py`): aiohttp-based HTTP server for remote control. Runs in a separate thread with its own asyncio event loop. Supports IP whitelist and CORS. **多宠物路由**：支持 `/api/pets/<pet_id>/...` 路径前缀按实例寻址，以及 `/api/instances` 实例管理端点（CRUD）。原有 `/api/move` 等无 `pet_id` 端点保留，未指定时作用于主实例（向后兼容）。Includes AI tool-calling endpoints (`/api/tools`, `/api/tools/call`) and message interaction endpoints (`/api/message`, `/api/messages/pending`, `/api/chat_bubble/show`, `/api/chat_bubble/hide`).

- **`MCP Server`** (`mcp_server.py`): MCP (Model Context Protocol) server for AI agent integration (e.g., OpenClaw). Runs as a separate process in stdio mode. Dynamically discovers tools from the pet API (`/api/tools`), so new API tools are automatically available without MCP code changes.

### Key Patterns

1. **Signal-Slot Architecture**: `MotionModeController` uses PyQt signals (`move_to_requested`, `play_animation_requested`, etc.) to decouple API requests from UI updates.

2. **Configuration Merging**: User config deep-merges with defaults, allowing partial overrides.

3. **Pet Package System**: Pets are self-contained packages with their own animations and actions. The `PetLoader` validates packages by checking for `meta.json` and `animations/` directory.

4. **Async API Server**: The HTTP server runs in a daemon thread with its own event loop. Start/stop methods manage the server lifecycle.

5. **Dynamic MCP Tool Discovery**: The MCP Server fetches tool definitions from `/api/tools` at runtime (30s cache), so adding new tools to `ApiServer._build_tools()` automatically exposes them to AI agents without modifying `mcp_server.py`.

6. **Thread-Safe UI Updates from API**: Use `QTimer.singleShot(0, lambda: ...)` to schedule UI operations on the main thread from async API handlers. Do NOT use `QMetaObject.invokeMethod` — Python methods are not registered in Qt's meta-object system.

### State Flow

```
IDLE → DRAGGING → INERTIA → (gravity check) → FALLING → IDLE
                ↓
           snap_to_edge

IDLE → random_move() → MOVING → IDLE
IDLE → REST_REMINDER → (bubble click) → countdown → IDLE
MOTION_MODE → (API commands) → ANIMATING/MOVING → MOTION_MODE
```

#### 平台生命周期

```
Platform Start:
  load global config → init shared components → migrate legacy → restore instances → create widgets → start API/tray

Create Instance:
  select package → generate pet_id → create PetInstanceConfig → persist to instances.json → create DesktopPet widget → show on screen

Destroy Instance:
  close widget → remove from instances.json → remove from _widgets → refresh tray menu
```

### Important Files

- `config/default_config.json`: Default configuration (do not modify)。顶层含 `instances` 占位字段与 `_instances_note` 说明，实际实例配置存于 `instances.json`
- `config/user_config.json`: User overrides
- `config/instances.json`: 实例配置持久化（运行时由 `InstancesStore` 生成/读写，结构为 `{"instances": [...]}`）
- `pets/{pet_name}/meta.json`: Pet package metadata (name, author, version, images)
- `pets/{pet_name}/config/actions.json`: Pet-specific actions and animations
- `pets/{pet_name}/animations/`: Animation files (GIF, WebP, PNG, APNG)
- `src/desktop_pet/pet_platform.py`: 平台核心类 `PetPlatform`，多实例生命周期管理入口
- `src/desktop_pet/pet_instance.py`: 实例配置数据模型 `PetInstanceConfig` 与 `generate_pet_id`
- `src/desktop_pet/instances_store.py`: 实例配置存储 `InstancesStore`，CRUD 与持久化

## Adding New Animations

1. Prepare a green-screen video
2. Convert using GUI or CLI tool: `uv run python scripts/green_screen_to_webp_gui.py`
3. Add the animation file to `pets/{pet_name}/animations/`
4. Update `pets/{pet_name}/config/actions.json` with the new action

## HTTP API

Default port: 8080. IP whitelist defaults to localhost only.

> **多宠物路由说明**：
> - 实例管理端点（`/api/instances...`）用于创建/列举/查询/更新/销毁实例
> - 按实例寻址端点（`/api/pets/<pet_id>/...`）作用于指定实例
> - 原有 `/api/move` 等无 `pet_id` 端点保留，未指定 `pet_id` 时作用于**主实例**（向后兼容）

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Get pet position, state, mode, available animations（作用于主实例） |
| `/api/screens` | GET | Get all display screens info |
| `/api/mode` | POST | Set mode: `{"mode": "random"}` or `{"mode": "motion"}` |
| `/api/move` | POST | Move to coordinates: `{"x": 100, "y": 200}` |
| `/api/move_by` | POST | Relative move: `{"dx": 50, "dy": 0}` |
| `/api/move_edge` | POST | Move to edge: `{"edge": "left"}` or `{"edge": "right"}` |
| `/api/animation` | POST | Play animation: `{"name": "sit", "callback_url": "..."}` |
| `/api/walk` | POST | Walk animation: `{"direction": "left"}` |
| `/api/animations` | GET | List available animations |
| `/api/tools` | GET | List AI-callable tool definitions (OpenAI function calling format) |
| `/api/tools/call` | POST | Execute AI tool: `{"name": "tool_name", "arguments": {...}}` |
| `/api/chat` | POST | LLM chat with function calling |
| `/api/message` | POST | Show bubble message: `{"text": "...", "duration": 5000}` |
| `/api/messages/pending` | GET | Get and clear user message queue |
| `/api/messages/send` | POST | Add message to user queue: `{"text": "..."}` |
| `/api/chat_bubble/show` | POST | Show interactive chat bubble: `{"message": "..."}` |
| `/api/chat_bubble/hide` | POST | Hide chat bubble |
| `/api/instances` | GET | 列出所有运行中实例 |
| `/api/instances` | POST | 创建新实例 `{"package": "default", "position": {"x": 500, "y": 300}}` |
| `/api/instances/<pet_id>` | GET | 获取单个实例状态 |
| `/api/instances/<pet_id>` | PATCH | 更新实例配置 |
| `/api/instances/<pet_id>` | DELETE | 销毁实例 |
| `/api/pets/<pet_id>/status` | GET | 获取指定实例状态 |
| `/api/pets/<pet_id>/mode` | POST | 设置指定实例模式 |
| `/api/pets/<pet_id>/move` | POST | 移动指定实例 |
| `/api/pets/<pet_id>/move_by` | POST | 相对移动指定实例 |
| `/api/pets/<pet_id>/move_edge` | POST | 移动指定实例至屏幕边缘 |
| `/api/pets/<pet_id>/animation` | POST | 指定实例播放动画 |
| `/api/pets/<pet_id>/walk` | POST | 指定实例行走动画 |
| `/api/pets/<pet_id>/animations` | GET | 列出指定实例可用动画 |
| `/api/pets/<pet_id>/chat_bubble/show` | POST | 指定实例显示聊天气泡 |
| `/api/pets/<pet_id>/chat_bubble/hide` | POST | 隐藏指定实例聊天气泡 |
| `/api/pets/<pet_id>/message` | POST | 指定实例显示文字气泡 `{"text": "...", "duration": 0}` |
| `/api/pets/<pet_id>/message/hide` | POST | 隐藏指定实例文字气泡 |

## MCP Server

The MCP Server allows AI agents (OpenClaw, Claude Desktop, etc.) to control the pet via MCP protocol.

- **工具列表自动扩展**：MCP Server 通过 `/api/tools` 动态发现工具（30s 缓存），新增的 API 工具自动可用，无需修改 `mcp_server.py`
- **多实例工具自动可用**：平台化后新增的 `list_pets` / `create_pet` / `remove_pet` / `get_pet_status` 工具会自动暴露给 AI agent
- **`pet_id` 可选参数**：原有控制工具（如 `move_to` / `play_animation` 等）新增可选 `pet_id` 参数；未提供时作用于主实例（向后兼容）

### Run MCP Server

```bash
uv run desktop-pet-mcp
```

### OpenClaw Configuration

Add to `~/.openclaw/openclaw.json`:

```json
{
  "mcpServers": {
    "desktop-pet": {
      "command": "uv",
      "args": ["--directory", "D:\\code\\pet-pc", "run", "desktop-pet-mcp"]
    }
  }
}
```

### Adding New Tools for AI Agents

1. Add tool definition to `ApiServer._build_tools()` in `api_server.py`
2. Add handler to `ApiServer._tool_handlers` and implement the handler method
3. Done — MCP Server auto-discovers new tools via `/api/tools`

平台化后已自动可用的实例管理工具：

- `list_pets`：列出所有运行中实例
- `create_pet`：创建新实例（指定 package / position 等）
- `remove_pet`：销毁指定实例
- `get_pet_status`：获取指定实例状态

原有控制工具（`move_to` / `play_animation` / `walk` 等）新增可选 `pet_id` 参数，用于按实例寻址。

## Dependencies

- Python >= 3.10
- PyQt6 (UI framework)
- Pillow (image processing)
- aiohttp (HTTP API server)
- mcp (MCP protocol server)
- httpx (async HTTP client for MCP Server)
- opencv-python, numpy (dev only - for green screen tools)