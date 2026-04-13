# Codebase Structure

**Analysis Date:** 2026-04-13

## Directory Layout

```
D:/code/pet-pc/
├── main.py                  # PyInstaller entry point
├── pyproject.toml           # Project metadata and dependencies
├── pytest.ini               # Test configuration
├── CLAUDE.md                # Project instructions
├── README.md                # Documentation
├── src/
│   └── desktop_pet/         # Main package
│       ├── __init__.py
│       ├── __main__.py      # Module entry point
│       ├── pet.py           # Main DesktopPet widget (1200+ lines)
│       ├── config_manager.py # Configuration loading/merging
│       ├── pet_loader.py    # Pet package loading
│       ├── motion_controller.py # Signal-based motion control
│       ├── api_server.py    # aiohttp HTTP server
│       ├── states.py        # PetState enum
│       ├── utils.py         # Path resolution utilities
│       ├── system_tray.py   # System tray integration
│       ├── startup_manager.py # Windows startup registration
│       ├── setup_wizard.py  # First-run setup UI
│       ├── action_manager_gui.py # Action editing dialog
│       ├── motion_control_panel.py # Motion mode UI
│       ├── motion_listener.py # Listener interface
│       └── click_zone_dialog.py # Click zone config dialog
├── config/
│   ├── default_config.json  # Default configuration
│   └── user_config.json     # User overrides
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
├── tests/                   # Unit tests
│   ├── test_config_manager.py
│   ├── test_api_server.py
│   └── ...
├── docs/                    # Documentation files
└── .claude/                # Claude configuration
```

## Directory Purposes

**`src/desktop_pet/`:**
- Purpose: Main application source code
- Contains: All Python modules for the pet application
- Key files: `pet.py`, `config_manager.py`, `pet_loader.py`, `api_server.py`

**`config/`:**
- Purpose: Configuration files
- Contains: JSON config files (default + user overrides)
- Key files: `default_config.json`, `user_config.json`

**`pets/`:**
- Purpose: Pet package storage
- Contains: Pet "packages" - self-contained directories with animations
- Each package contains: `meta.json`, `animations/`, `config/actions.json`

**`scripts/`:**
- Purpose: Utility tools for animation processing
- Contains: Green screen removal, GIF creation, compression tools
- Usage: Run independently, not imported by main app

**`tests/`:**
- Purpose: Unit tests
- Contains: pytest test files
- Key files: `test_config_manager.py`, `test_api_server.py`

## Key File Locations

**Entry Points:**
- `src/desktop_pet/__main__.py`: Standard module execution (`python -m desktop_pet`)
- `main.py`: PyInstaller standalone build target

**Configuration:**
- `config/default_config.json`: Default settings (do not modify)
- `config/user_config.json`: User overrides (safe to modify)

**Core Logic:**
- `src/desktop_pet/pet.py`: Main DesktopPet widget class
- `src/desktop_pet/config_manager.py`: Config loading and dataclasses
- `src/desktop_pet/pet_loader.py`: Pet package loading

**Testing:**
- `tests/test_config_manager.py`: ConfigManager unit tests
- `tests/test_api_server.py`: ApiServer async tests

## Naming Conventions

**Files:**
- snake_case: All Python files use snake_case (`config_manager.py`, `api_server.py`)
- Descriptive nouns: `pet_loader.py`, `motion_controller.py`

**Classes:**
- PascalCase: `DesktopPet`, `ConfigManager`, `ApiServer`
- Descriptive nouns/phrases: `MotionModeController`, `ActionManager`

**Functions/Methods:**
- snake_case: `load_config()`, `random_move()`, `_check_pet_resources()`
- Underscore prefix for private: `_load_current_pet()`, `_on_move_to_requested()`

**Dataclasses:**
- PascalCase: `PetMeta`, `PetAction`, `ActionConfig`, `PetState`
- Suffix Config: `PetConfig`, `MovementConfig`, `RestReminderConfig`

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
- User overrides: Edit `config/user_config.json`

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
- Generated: user_config.json created on first run
- Committed: default_config.json yes, user_config.json typically not

**`tests/`:**
- Purpose: pytest unit tests
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-04-13*