# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

Desktop Pet (桌面宠物) is a PyQt6-based desktop pet application with animations, rest reminders, and HTTP API remote control capabilities. The project supports multiple pet "packages" with different animations and behaviors.

## Commands

### Run the application
```bash
uv run desktop-pet
# or
uv run python -m desktop_pet
```

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

- **`DesktopPet`** (`pet.py`): Main widget class that handles UI, mouse events, animations, and coordinates all components. Manages pet state machine (IDLE, DRAGGING, FALLING, INERTIA, REST_REMINDER, MOTION_MODE, ANIMATING).

- **`ConfigManager`** (`config_manager.py`): Loads and merges `default_config.json` with `user_config.json`. Provides typed config objects (ActionConfig, RestReminderConfig, MovementConfig, PetConfig).

- **`PetLoader`** (`pet_loader.py`): Loads pet "packages" from `pets/` directory. Each package contains `meta.json`, `animations/` directory, and optional `config/actions.json`.

- **`MotionModeController`** (`motion_controller.py`): PyQt signal-based controller for API-driven pet control. Emits signals that `DesktopPet` connects to for movement/animation actions.

- **`ApiServer`** (`api_server.py`): aiohttp-based HTTP server for remote control. Runs in a separate thread with its own asyncio event loop. Supports IP whitelist and CORS. Includes AI tool-calling endpoints (`/api/tools`, `/api/tools/call`) and message interaction endpoints (`/api/message`, `/api/messages/pending`, `/api/chat_bubble/show`, `/api/chat_bubble/hide`).

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

### Important Files

- `config/default_config.json`: Default configuration (do not modify)
- `config/user_config.json`: User overrides
- `pets/{pet_name}/meta.json`: Pet package metadata (name, author, version, images)
- `pets/{pet_name}/config/actions.json`: Pet-specific actions and animations
- `pets/{pet_name}/animations/`: Animation files (GIF, WebP, PNG, APNG)

## Adding New Animations

1. Prepare a green-screen video
2. Convert using GUI or CLI tool: `uv run python scripts/green_screen_to_webp_gui.py`
3. Add the animation file to `pets/{pet_name}/animations/`
4. Update `pets/{pet_name}/config/actions.json` with the new action

## HTTP API

Default port: 8080. IP whitelist defaults to localhost only.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Get pet position, state, mode, available animations |
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

## MCP Server

The MCP Server allows AI agents (OpenClaw, Claude Desktop, etc.) to control the pet via MCP protocol.

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

## Dependencies

- Python >= 3.10
- PyQt6 (UI framework)
- Pillow (image processing)
- aiohttp (HTTP API server)
- mcp (MCP protocol server)
- httpx (async HTTP client for MCP Server)
- opencv-python, numpy (dev only - for green screen tools)