# Codebase Structure

**Analysis Date:** 2026-04-13 · **Updated:** 2026-06-29（平台化重构 + CLI 子命令扩展）

## Directory Layout

```
D:/code/pet-pc/
├── main.py                  # PyInstaller entry point（转发到 __main__.py）
├── pyproject.toml           # Project metadata and dependencies
├── pytest.ini               # Test configuration
├── CLAUDE.md                # Claude Code 速查（指向 AGENTS.md）
├── AGENTS.md                # 项目规则手册（架构/API/组件细节权威来源）
├── README.md                # 用户文档
├── src/
│   └── desktop_pet/         # Main package
│       ├── __init__.py
│       ├── __main__.py      # Module entry point（argparse + add/list/animate/walk/move/animations 子命令）
│       ├── cli_client.py    # CLI HTTP 客户端（子命令通过本地 API 控制运行中平台）
│       ├── pet.py           # DesktopPet 实例 widget（双模式构造）
│       ├── pet_platform.py  # PetPlatform 多桌宠平台顶层容器
│       ├── pet_instance.py  # PetInstanceConfig 实例配置 dataclass
│       ├── instances_store.py # InstancesStore 实例配置持久化
│       ├── config_manager.py # GlobalConfigManager + 旧版 ConfigManager
│       ├── pet_loader.py    # Pet package loading（已移除 _current_pet）
│       ├── motion_controller.py # Signal-based motion control
│       ├── api_server.py    # aiohttp HTTP server（多宠物路由 + AI tool-calling）
│       ├── mcp_server.py    # MCP protocol server (stdio, dynamic discovery)
│       ├── screen_manager.py # 多实例共享 ScreenManager
│       ├── system_tray.py   # 系统托盘（双模式，多实例菜单）
│       ├── settings_center.py # 设置中心（接受 PetPlatform）
│       ├── settings_pages/  # 设置页面目录
│       │   ├── instance_manager_page.py # 实例管理页
│       │   ├── pet_list_page.py        # 宠物库（"创建实例"按钮）
│       │   ├── pet_config_page.py      # 实例配置编辑
│       │   ├── action_control_page.py  # 动作控制（作用于选中实例）
│       │   └── global_settings_page.py # 全局设置
│       ├── states.py        # PetState enum
│       ├── state_machine.py # PetStateMachine
│       ├── utils.py         # Path resolution utilities
│       ├── startup_manager.py # Windows startup registration
│       ├── setup_wizard.py  # First-run setup UI
│       ├── action_manager_gui.py # Action editing dialog
│       ├── motion_control_panel.py # Motion mode UI
│       ├── motion_listener.py # Listener interface
│       ├── behavior_scheduler.py # 行为调度器（每实例独立）
│       └── click_zone_dialog.py # Click zone config dialog
├── config/
│   ├── default_config.json  # Default configuration（含 instances 占位）
│   ├── user_config.json     # User global overrides
│   └── instances.json       # 实例配置（运行时由 InstancesStore 生成/读写，勿手编）
├── pets/
│   └── default/             # Default pet package
│       ├── meta.json        # Pet metadata
│       ├── animations/      # Animation files (webp, gif, png)
│       └── config/
│           └── actions.json # Action definitions
├── scripts/                 # Utility scripts
│   ├── green_screen_to_Webp.py
│   ├── green_screen_to_webp_gui.py
│   ├── create_gif.py
│   ├── gif_to_apng.py
│   ├── webp_tool.py
│   ├── compress_animations.py
│   └── ...
├── tests/                   # Unit + integration tests
│   ├── test_pet_instance.py     # PetInstanceConfig 测试
│   ├── test_config_split.py     # GlobalConfigManager + InstancesStore 测试
│   ├── test_pet_platform.py     # PetPlatform 测试
│   ├── test_api_server.py       # ApiServer 多宠物路由测试
│   ├── test_multi_pet_integration.py # 集成测试（端到端验证）
│   ├── test_pet_list_page.py    # 设置中心 UI 测试
│   ├── test_cli_client.py       # CLI 子命令 HTTP 客户端测试
│   └── ...
├── .planning/codebase/      # 内部架构分析文档
├── .trae/                   # Trae IDE 配置与文档
└── openclaw-plugins/        # OpenClaw 集成插件
```

## Directory Purposes

**`src/desktop_pet/`:**
- Purpose: Main application source code
- Contains: 平台层（pet_platform/pet_instance/instances_store）+ 实例层（pet）+ 共享组件（api_server/system_tray/screen_manager/config_manager）
- Key files: `pet_platform.py`, `pet.py`, `pet_instance.py`, `instances_store.py`, `api_server.py`

**`src/desktop_pet/settings_pages/`:**
- Purpose: 设置中心各页面
- Contains: `instance_manager_page.py`（实例管理）、`pet_list_page.py`（宠物库）、`pet_config_page.py`（实例配置）、`action_control_page.py`（动作控制）、`global_settings_page.py`（全局设置）

**`config/`:**
- Purpose: Configuration files
- Contains: `default_config.json`（默认，勿改）、`user_config.json`（全局覆盖）、`instances.json`（实例配置，运行时生成）
- Note: `instances.json` 由 `InstancesStore` 维护，**不要手动编辑**

**`pets/`:**
- Purpose: Pet package storage
- Contains: Pet "packages" - self-contained directories with animations
- Each package contains: `meta.json`, `animations/`, `config/actions.json`

**`scripts/`:**
- Purpose: Utility tools for animation processing
- Contains: Green screen removal, GIF creation, compression tools
- Usage: Run independently, not imported by main app

**`tests/`:**
- Purpose: Unit + integration tests
- Contains: pytest test files，含 `test_multi_pet_integration.py` 端到端集成测试

## Key File Locations

**Entry Points:**
- `src/desktop_pet/__main__.py`: Standard module execution（`python -m desktop_pet` / `uv run desktop-pet` / `main.py` 均汇聚于此）。含 argparse 子命令 `add` / `list` / `animate` / `walk` / `move` / `animations`，无子命令时启动 GUI
- `src/desktop_pet/cli_client.py`: CLI 子命令的 HTTP 客户端（探活主进程 + 调用本地 API）
- `main.py`: PyInstaller standalone build target（转发到 `__main__.py`）

**Platform Core:**
- `src/desktop_pet/pet_platform.py`: `PetPlatform` 多实例生命周期入口
- `src/desktop_pet/pet_instance.py`: `PetInstanceConfig` 数据模型 + `generate_pet_id`
- `src/desktop_pet/instances_store.py`: `InstancesStore` CRUD + 向后兼容迁移

**Configuration:**
- `config/default_config.json`: Default settings (do not modify)
- `config/user_config.json`: User global overrides (safe to modify)
- `config/instances.json`: Instance configs (runtime-generated, do not edit)

**Core Logic:**
- `src/desktop_pet/pet.py`: `DesktopPet` 实例 widget（双模式）
- `src/desktop_pet/config_manager.py`: `GlobalConfigManager` + 旧版 `ConfigManager`
- `src/desktop_pet/api_server.py`: `ApiServer` 多宠物路由 + AI tool-calling

**Testing:**
- `tests/test_pet_platform.py`: PetPlatform unit tests
- `tests/test_api_server.py`: ApiServer async tests（多宠物路由）
- `tests/test_multi_pet_integration.py`: 端到端集成测试

## Naming Conventions

**Files:**
- snake_case: All Python files use snake_case (`config_manager.py`, `api_server.py`)
- Descriptive nouns: `pet_loader.py`, `motion_controller.py`

**Classes:**
- PascalCase: `DesktopPet`, `PetPlatform`, `PetInstanceConfig`, `InstancesStore`, `ApiServer`
- Descriptive nouns/phrases: `MotionModeController`, `GlobalConfigManager`

**Functions/Methods:**
- snake_case: `load_config()`, `random_move()`, `create_instance()`
- Underscore prefix for private: `_init_platform_mode()`, `_resolve_pet()`

**Dataclasses:**
- PascalCase: `PetMeta`, `PetAction`, `ActionConfig`, `PetState`
- Suffix Config: `PetInstanceConfig`, `PetConfig`, `MovementConfig`, `RestReminderConfig`

## Where to Add New Code

**New Feature:**
- Primary code: Add to `src/desktop_pet/` (appropriate module)
- Tests: Add to `tests/`

**New Component/Module:**
- Implementation: Create new file in `src/desktop_pet/`
- Export: Add to `src/desktop_pet/__init__.py` if needed

**New Pet Action:**
- Animation file: Add to `pets/{pet_name}/animations/`
- Action definition: Edit `pets/{pet_name}/config/actions.json`

**Configuration:**
- Default values: Edit `config/default_config.json`
- User global overrides: Edit `config/user_config.json`
- Instance configs: 通过 `PetPlatform.create_instance()` / `update_instance_config()` API 修改，不要手编 `instances.json`

**New API Tool for AI Agents:**
1. Add tool definition to `ApiServer._build_tools()` in `api_server.py`
2. Add handler to `ApiServer._tool_handlers` and implement the handler method
3. Done — MCP Server auto-discovers new tools via `/api/tools`

**Utilities:**
- Shared helpers: Add to `src/desktop_pet/utils.py`
- Animation processing: Add to `scripts/` directory

## Special Directories

**`pets/`:**
- Purpose: Pet packages - swappable animation sets
- Generated: No (manually curated)
- Committed: Yes - contains default pet assets

**`scripts/`:**
- Purpose: Standalone utilities for asset creation
- Generated: No
- Committed: Yes - development tools

**`config/`:**
- Purpose: Runtime configuration
- Generated: `user_config.json` and `instances.json` created on first run
- Committed: `default_config.json` yes; `user_config.json` / `instances.json` typically not

**`tests/`:**
- Purpose: pytest unit + integration tests
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-04-13 · Updated: 2026-06-29（平台化重构 + CLI 子命令扩展）*