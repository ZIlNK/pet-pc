# External Integrations

**Analysis Date:** 2026-04-13 · **Updated:** 2026-06-29（平台化重构 + CLI 子命令扩展）

## APIs & External Services

**HTTP API Server (Built-in):**
- aiohttp-based REST API server with multi-pet routing
- Location: `src/desktop_pet/api_server.py`
- Constructor: `ApiServer(pet=None, platform=None)` 双模式；新模式传 `platform`，旧模式传 `pet`
- Default port: 8080
- Host: configurable (default 0.0.0.0)
- IP Whitelist: configurable (default localhost only: ["127.0.0.1", "::1"])
- CORS: enabled with wildcard origin (`Access-Control-Allow-Origin: *`), supports GET/POST/PATCH/DELETE

**Multi-Pet Routing:**
- 按实例寻址：`/api/pets/<pet_id>/...` 作用于指定实例
- 查询参数：`?pet_id=...` 等价于路径前缀
- 回退：未指定 `pet_id` 时作用于**主实例**（向后兼容旧版 API）
- 解析逻辑：`ApiServer._resolve_pet(request)` / `_resolve_pet_from_args(args)`

**API Endpoints:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Get pet position, state, mode, available animations（作用于主实例） |
| `/api/mode` | POST | Set mode: `{"mode": "random"}` or `{"mode": "motion"}` |
| `/api/move` | POST | Move to coordinates: `{"x": 100, "y": 200}` |
| `/api/move_by` | POST | Relative move: `{"dx": 50, "dy": 0}` |
| `/api/move_edge` | POST | Move to edge: `{"edge": "left"}` or `{"edge": "right"}` |
| `/api/animation` | POST | Play animation with optional callback URL |
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

**AI Tool-Calling:**
- 原有控制工具（`move_to` / `play_animation` / `walk` 等）新增可选 `pet_id` 参数，未提供时作用于主实例
- 新增实例管理工具：`list_pets` / `create_pet` / `remove_pet` / `get_pet_status`
- 工具定义在 `ApiServer._build_tools()`，handler 注册到 `_tool_handlers`
- MCP Server 通过 `/api/tools` 动态发现（30s 缓存），无需修改 `mcp_server.py`

**CLI Subcommands (本地进程间通信):**
- 入口：`uv run desktop-pet <subcommand>`（`src/desktop_pet/__main__.py` argparse 分流）
- HTTP 客户端：`src/desktop_pet/cli_client.py`（同步 `httpx.Client`，短命令无需 async）
- 通信方式：通过本地 HTTP API 与主进程交互，主进程未运行时报错并提示先启动 `desktop-pet`
- API 地址解析：从 `config/user_config.json` 的 `api.host` / `api.port` 读取；`0.0.0.0` 自动转为 `127.0.0.1`；读取失败回退 `http://127.0.0.1:8080`
- 探活机制：`GET /api/status` 短超时（2 秒）检测主进程是否在运行
- 错误处理：业务错误抛 `CliError`，由 `__main__.py` 捕获后打印 stderr 并 `sys.exit(1)`

| 子命令 | 作用 | 映射端点 |
|--------|------|----------|
| `add --package <name> [--x N] [--y N]` | 新增运行桌宠实例 | `POST /api/instances` |
| `list` | 列出运行中实例 | `GET /api/instances` |
| `animate <pet_id> --name <action>` | 播放指定动画 | `POST /api/pets/<pet_id>/animation` |
| `walk <pet_id> --direction <left\|right>` | 行走动画 | `POST /api/pets/<pet_id>/walk` |
| `move <pet_id> --xy X Y [--screen N]` | 移动到绝对坐标 | `POST /api/pets/<pet_id>/move` |
| `move <pet_id> --delta DX DY` | 相对移动 | `POST /api/pets/<pet_id>/move_by` |
| `move <pet_id> --edge <left\|right> [--screen N]` | 移到屏幕边缘 | `POST /api/pets/<pet_id>/move_edge` |
| `animations <pet_id>` | 列出指定桌宠可用动画 | `GET /api/pets/<pet_id>/animations` |

> **注意**：`--hidden` 短选项从 `-h` 改为 `-H`（避免与 argparse 默认的 `-h` help 冲突）；`move` 子命令的 `--xy` / `--delta` / `--edge` 三种模式互斥，必选其一。

**Outbound Webhook Calls:**
- Animation completion callbacks via HTTP POST
- Callback URL validation (blocks private/internal IPs)
- Timeout: 5 seconds
- Payload: JSON with event, animation name, position, timestamp

## Data Storage

**Configuration Files:**
- Type: JSON files
- Location: `config/`
- Files:
  - `default_config.json` - Default configuration (committed, do not modify)。顶层含 `instances: []` 占位字段
  - `user_config.json` - User global overrides (gitignored)
  - `instances.json` - 实例配置持久化（运行时由 `InstancesStore` 生成/读写，勿手编）
- Merging:
  - 全局配置：`GlobalConfigManager` 深度合并 `default_config.json` + `user_config.json`，仅保留 `api/tray/startup/display/mcp/llm` 字段
  - 实例配置：`InstancesStore` 直接读写 `instances.json`，结构为 `{"instances": [...]}`

**Instance Config Schema:**
```json
{
  "instances": [
    {
      "pet_id": "a1b2c3d4",
      "package": "default",
      "primary": true,
      "position": {"x": 100, "y": 200},
      "screen_index": 0,
      "size": {"width": 200, "height": 159},
      "actions": {...},
      "rest_reminder": {...},
      "movement": {...},
      "behavior": {...},
      "motion_mode": {...},
      "click_detection": {...}
    }
  ]
}
```

**Pet Packages:**
- Location: `pets/{pet_name}/`
- Structure:
  - `meta.json` - Pet metadata (name, author, version, images)
  - `animations/` - Animation files (GIF, WebP, PNG, APNG)
  - `config/actions.json` - Pet-specific actions (optional)

**File Storage:**
- Local filesystem only (no cloud storage)
- Animation assets stored in pet package directories
- User-configurable pet images

**Caching:**
- Pet packages cached in `PetPlatform.pet_packages` dict（包名 → `PetPackage`）
- MCP tool definitions cached 30s in `mcp_server.py`

## Authentication & Identity

**API Authentication:**
- IP whitelist-based access control
- Default: localhost only
- Configurable via `config/default_config.json` -> `api.allowed_ips`
- IP filtering can be disabled (for ngrok/tunneling)

**No external auth providers** - Application is self-contained

## Monitoring & Observability

**Logging:**
- Standard Python logging module
- Configurable log level (DEBUG, INFO, WARNING, ERROR)
- Log output: stdout via basicConfig
- Third-party library noise reduction (PIL, aiohttp set to WARNING)

**Error Tracking:**
- No external error tracking service
- Internal logging via Python `logging` module

## CI/CD & Deployment

**Build System:**
- hatchling (PEP 517 build backend)
- Produces wheel and source distribution

**Executable Build:**
- PyInstaller (dev dependency)
- Produces Windows .exe

**Version Control:**
- Git-based workflow
- No automated CI/CD pipeline detected

## Environment Configuration

**Configuration via JSON:**
- No environment variables required for core functionality
- API host/port configured in `config/default_config.json`

**Configuration Schema (api section):**
```json
{
  "api": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 8080,
    "allowed_ips": ["127.0.0.1", "::1"]
  }
}
```

## Platform Integration

**Windows Registry:**
- Startup registration via `winreg` module
- Registry key: `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
- Managed by: `src/desktop_pet/startup_manager.py`

**System Tray:**
- PyQt6 QSystemTrayIcon
- 双模式构造：`SystemTrayIcon(platform, parent)` 或 `SystemTrayIcon(pet, parent)`
- 多实例菜单：列出所有实例，每项子菜单含"显示/隐藏"、"关闭此桌宠"
- 实例增删时通过 `PetPlatform._refresh_system_tray()` 自动刷新

## Webhooks & Callbacks

**Incoming:**
- HTTP POST endpoints (API server above)
- JSON request body parsing
- IP whitelist filtering

**Outgoing:**
- Animation completion callbacks
- User-provided callback URLs
- Security: URL validation blocks internal/private IPs
- Timeout: 5 seconds
- Uses aiohttp ClientSession for async POST

---

*Integration audit: 2026-04-13 · Updated: 2026-06-29（平台化重构 + CLI 子命令扩展）*