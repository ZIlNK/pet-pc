# Architecture

**Analysis Date:** 2026-04-13 · **Updated:** 2026-06-29（平台化重构 + CLI 子命令扩展）

## Pattern Overview

**Overall:** Event-driven Multi-Pet Platform with Signal-Slot Architecture

**Key Characteristics:**
- PyQt6-based multi-pet platform: 同时运行 N 个桌宠实例，每个实例独立配置
- 平台层（`PetPlatform`）持有共享组件：`ApiServer` / `SystemTray` / `ScreenManager` / `GlobalConfigManager`
- 实例层（`DesktopPet`）作为平台下的 widget，双模式构造（新模式 + 旧模式向后兼容）
- Signal-slot pattern for decoupling API/server from UI
- State machine for pet behavior (IDLE, DRAGGING, FALLING, INERTIA, etc.)
- Async HTTP server for remote control with multi-pet routing
- Pet package system for swappable animations

## Layers

**Platform Layer（新增 2026-06-29）:**
- Purpose: 多桌宠平台顶层容器，统一管理实例生命周期与共享组件
- Location: `src/desktop_pet/pet_platform.py`
- Contains: `PetPlatform` 类，持有 `GlobalConfigManager` / `PetLoader` / `InstancesStore` / `pet_packages` / `_widgets` / `api_server` / `system_tray` / `screen_manager`
- Depends on: 所有平台下组件
- Used by: `__main__.py` 入口

**Instance Config Layer（新增 2026-06-29）:**
- Purpose: 实例级配置数据模型与持久化
- Location: `src/desktop_pet/pet_instance.py`（`PetInstanceConfig` dataclass）、`src/desktop_pet/instances_store.py`（`InstancesStore` 读写 `config/instances.json`）
- Contains: 实例字段（pet_id/package/primary/position/size/actions/rest_reminder/movement/behavior/motion_mode/click_detection），CRUD + 向后兼容迁移
- Used by: `PetPlatform`、`ApiServer`、`SettingsCenter`

**Global Config Layer（重构 2026-06-29）:**
- Purpose: 仅管理全局共享配置（api/tray/startup/display/mcp/llm）
- Location: `src/desktop_pet/config_manager.py`
- Contains: `GlobalConfigManager`（新增）、`ConfigManager`（保留用于旧模式向后兼容）
- Depends on: `config/default_config.json`、`config/user_config.json`

**UI Layer（实例 widget）:**
- Purpose: 单个桌宠实例的 UI、鼠标事件、动画
- Location: `src/desktop_pet/pet.py`
- Contains: `DesktopPet` QWidget subclass，**双模式构造**：新模式接受 `PetInstanceConfig` + `PetPackage` + `PetPlatform`；旧模式退化为独立运行
- Depends on: PyQt6, PetInstanceConfig, MotionModeController, PetPlatform（新模式）
- Used by: `PetPlatform._widget_factory`

**Pet Package Layer:**
- Purpose: Load and validate pet packages from filesystem
- Location: `src/desktop_pet/pet_loader.py`
- Contains: `PetLoader` class, `PetPackage`, `PetMeta`, `PetAction` dataclasses
- Depends on: `pets/` directory structure
- Used by: `PetPlatform`, `SetupWizard`
- Note: 平台化后职责收窄，**不再维护 `_current_pet` 状态**

**Motion Control Layer:**
- Purpose: Signal-based controller for API-driven pet control
- Location: `src/desktop_pet/motion_controller.py`
- Contains: `MotionModeController` with PyQt signals
- Pattern: 每实例独立持有

**API Server Layer（多宠物路由）:**
- Purpose: aiohttp-based HTTP server for remote control + AI tool-calling
- Location: `src/desktop_pet/api_server.py`
- Contains: `ApiServer(pet=None, platform=None)` 双模式构造；多宠物路由通过 `_resolve_pet` 解析 `pet_id`（路径前缀 `/api/pets/<pet_id>/...` → 查询参数 `?pet_id=...` → 主实例回退）
- Endpoints: 原有控制端点 + `/api/instances`（GET/POST）、`/api/instances/<pet_id>`（GET/PATCH/DELETE）+ `/api/pets/<pet_id>/...` 按实例寻址
- AI Tools: 原有控制工具新增 `pet_id` 可选参数；新增 `list_pets` / `create_pet` / `remove_pet` / `get_pet_status`
- Depends on: aiohttp, MotionModeController signals
- Used by: `PetPlatform`, MCP Server (via HTTP)

**MCP Server Layer:**
- Purpose: MCP protocol server for AI agent integration (OpenClaw, Claude Desktop, etc.)
- Location: `src/desktop_pet/mcp_server.py`
- Transport: stdio mode (spawned by AI agent as subprocess)
- Pattern: Dynamically fetches tool definitions from `/api/tools` (30s cache)；平台化新增的实例管理工具自动可用，无需修改 `mcp_server.py`

**System Integration Layer（多实例菜单）:**
- Purpose: System tray, startup management, setup wizard
- Location: `src/desktop_pet/system_tray.py`, `startup_manager.py`, `setup_wizard.py`
- Contains: System tray icon（双模式，新模式列出所有实例，支持单独显示/隐藏/关闭）, Windows startup registration, first-run setup UI
- Used by: `PetPlatform`（新模式）、`DesktopPet`（旧模式）

## Data Flow

**Application Startup（平台化）:**

1. `main.py` 转发到 `__main__.py`
2. `__main__.py` 用 argparse 解析子命令；若有子命令（`add` / `list` / `animate` / `walk` / `move` / `animations`）则走 CLI 分支（通过 `cli_client.py` 调用本地 HTTP API，主进程未运行时报错退出），不启动 GUI
3. 无子命令时创建 QApplication，检查宠物资源（首次运行显示 SetupWizard）
4. 创建 `PetPlatform`，注入 `widget_factory`，调用 `start()`
5. `start()` 流程：迁移旧版 `app.current_pet`（若 instances.json 为空）→ 从 `instances.json` 恢复实例列表 → 为每个实例创建 widget → 初始化共享 `ScreenManager`
6. 若无实例，用首个可用包创建 primary 实例
7. 启动 API 服务器、创建系统托盘

**Create Instance Flow:**

1. 选择 `package` → 生成 `pet_id`（短 UUID）→ 构建 `PetInstanceConfig` → 持久化到 `instances.json` → 通过 `widget_factory` 创建 `DesktopPet` → 显示到屏幕
2. 末尾调用 `_refresh_system_tray()` 刷新托盘菜单

**Destroy Instance Flow:**

1. 关闭 widget → 从 `instances.json` 移除 → 从 `_widgets` 移除 → 刷新托盘菜单

**Random Movement Flow:**

1. QTimer fires `random_move()`
2. Weighted random selection from enabled actions
3. If action.type == "movement": `execute_movement_action()`
4. If action.type == "animation": `play_animation_action()`
5. Animation completes, return to IDLE state

**Drag Interaction Flow:**

1. mousePressEvent: state = DRAGGING
2. mouseMoveEvent: move widget, switch to walk GIF
3. mouseReleaseEvent: state = INERTIA
4. Calculate velocity, start inertia timer
5. If velocity low: snap_to_edge, state = IDLE
6. If velocity high: apply inertia, check for gravity
7. 拖动/惯性/重力结束时调用 `platform.persist_instance_position(pet_id, x, y)` 持久化

**API Remote Control Flow（多宠物路由）:**

1. HTTP request to ApiServer
2. `_resolve_pet(request)` 解析 `pet_id`：路径前缀 → 查询参数 → 主实例回退
3. ApiServer validates request, extracts parameters
4. 跨线程通过 `_run_in_main_thread` 或 PyQt signal + QueuedConnection 调度到主线程
5. DesktopPet slot handlers execute requested action
6. Response returned to HTTP client

## Key Abstractions

**PetPlatform:** 多桌宠平台顶层容器，统一管理实例与共享组件。

**PetInstanceConfig:** 单个桌宠实例的配置数据模型，含位置/尺寸/动作/休息提醒/行为/运动模式/点击区域等独立字段。

**InstancesStore:** 实例配置持久化，CRUD + 向后兼容迁移（旧 `app.current_pet` → primary 实例）。

**PetPackage:** Represents a complete pet "theme" with animations.

**PetState Enum:** Finite state machine for pet behavior (IDLE, DRAGGING, INERTIA, FALLING, MOVING, REST_REMINDER, MOTION_MODE, ANIMATING).

## Entry Points

**Primary Entry:**
- Location: `src/desktop_pet/__main__.py`（`python -m desktop_pet` / `uv run desktop-pet` / `main.py` 均汇聚于此）
- Responsibilities: argparse 子命令分流（`add` / `list` / `animate` / `walk` / `move` / `animations`）；无子命令时执行 QApplication setup + `PetPlatform` 实例化与启动

**CLI Subcommand Entry:**
- Location: `src/desktop_pet/cli_client.py`（由 `__main__.py` 的 `_run_add` / `_run_list` / `_run_animate` / `_run_walk` / `_run_move` / `_run_animations` 调用）
- Triggers: 用户执行 `uv run desktop-pet <subcommand>`
- Responsibilities: 通过本地 HTTP API 控制运行中的桌宠平台；主进程未运行时报错退出

**HTTP API Entry:**
- Location: `src/desktop_pet/api_server.py`
- Triggers: HTTP requests to configured port
- Responsibilities: Handle REST endpoints（含多宠物路由）, emit motion signals

**MCP Entry:**
- Location: `src/desktop_pet/mcp_server.py`（`uv run desktop-pet-mcp`）
- Triggers: AI agent spawns as subprocess
- Responsibilities: Dynamic tool discovery via `/api/tools`

## Error Handling

**Strategy:** Graceful degradation with logging

**Patterns:**
- Try-except blocks around file I/O (images, configs, instances.json)
- 文件不存在或损坏时返回空列表（`InstancesStore._load_raw`），不抛异常
- Fallback to default pet if loading fails
- Silent failures for optional features (API server, rest reminder)
- Logging at appropriate levels (DEBUG for flow, ERROR for failures)

## Cross-Cutting Concerns

**Logging:** Python stdlib logging, configured in entry points with DEBUG/INFO levels, third-party loggers (PIL, aiohttp) set to WARNING

**Validation:** Coordinate bounds checking in API server, IP whitelist for API access, callback URL security checks

**Authentication:** IP-based whitelist for API access (configurable in user_config.json)

**Thread Safety:** API server 在子线程 asyncio loop 中运行；跨线程 UI 操作必须用 `QTimer.singleShot(0, lambda: ...)` 或 PyQt signal + QueuedConnection 调度到主线程；不要用 `QMetaObject.invokeMethod`。

---

*Architecture analysis: 2026-04-13 · Updated: 2026-06-29（平台化重构 + CLI 子命令扩展）*