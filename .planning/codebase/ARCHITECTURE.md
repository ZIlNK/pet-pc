# Architecture

**Analysis Date:** 2026-04-13

## Pattern Overview

**Overall:** Event-driven Desktop Application with Signal-Slot Architecture

**Key Characteristics:**
- PyQt6-based desktop widget with frameless window
- Signal-slot pattern for decoupling API/server from UI
- State machine for pet behavior (IDLE, DRAGGING, FALLING, INERTIA, etc.)
- Async HTTP server for remote control
- Pet package system for swappable animations

## Layers

**UI Layer:**
- Purpose: Main desktop pet window and user interface
- Location: `src/desktop_pet/pet.py`
- Contains: `DesktopPet` QWidget subclass, animations, mouse event handlers
- Depends on: PyQt6, ConfigManager, MotionModeController, ApiServer
- Used by: `__main__.py` entry point

**Configuration Layer:**
- Purpose: Load/merge configs, provide typed config objects
- Location: `src/desktop_pet/config_manager.py`
- Contains: `ConfigManager` class, dataclasses for all config types
- Depends on: JSON files in `config/`
- Used by: DesktopPet, ActionManagerGUI

**Pet Package Layer:**
- Purpose: Load and validate pet packages from filesystem
- Location: `src/desktop_pet/pet_loader.py`
- Contains: `PetLoader` class, `PetPackage`, `PetMeta`, `PetAction` dataclasses
- Depends on: `pets/` directory structure
- Used by: DesktopPet, SetupWizard

**Motion Control Layer:**
- Purpose: Signal-based controller for API-driven pet control
- Location: `src/desktop_pet/motion_controller.py`
- Contains: `MotionModeController` with PyQt signals
- Signals: `move_to_requested`, `play_animation_requested`, `set_mode_requested`, etc.
- Depends on: DesktopPet (for state/position access)
- Used by: ApiServer

**API Server Layer:**
- Purpose: aiohttp-based HTTP server for remote control
- Location: `src/desktop_pet/api_server.py`
- Contains: `ApiServer` class with async request handlers
- Endpoints: `/api/status`, `/api/move`, `/api/animation`, etc.
- Depends on: aiohttp, MotionModeController signals
- Used by: DesktopPet

**System Integration Layer:**
- Purpose: System tray, startup management, setup wizard
- Location: `src/desktop_pet/system_tray.py`, `startup_manager.py`, `setup_wizard.py`
- Contains: System tray icon, Windows startup registration, first-run setup UI
- Depends on: PyQt6 QSystemTrayIcon, winreg (Windows only)
- Used by: DesktopPet

## Data Flow

**Application Startup:**

1. `main.py` or `__main__.py` creates QApplication
2. DesktopPet constructor checks for pet resources
3. If no pets found, shows SetupWizard
4. ConfigManager loads default + user config
5. PetLoader loads current pet package
6. UI initialized with pet images/animations
7. Random movement timer starts
8. Rest reminder timer starts (if enabled)

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

**API Remote Control Flow:**

1. HTTP request to ApiServer
2. ApiServer validates request, extracts parameters
3. ApiServer calls MotionModeController methods
4. MotionModeController emits PyQt signals
5. DesktopPet slot handlers execute requested action
6. Response returned to HTTP client

## Key Abstractions

**PetPackage:**
- Purpose: Represents a complete pet "theme" with animations
- Examples: Loaded from `pets/{pet_name}/`
- Pattern: Contains meta.json, animations/, config/actions.json

**ActionConfig / PetAction:**
- Purpose: Defines available behaviors (animations, movements)
- Examples: "walk", "sit", "read" actions
- Pattern: Weight-based random selection, type区分 movement/animation

**PetState Enum:**
- Purpose: Finite state machine for pet behavior
- States: IDLE, DRAGGING, INERTIA, FALLING, MOVING, REST_REMINDER, MOTION_MODE, ANIMATING
- Pattern: State guards prevent conflicting operations

**MotionModeController Signals:**
- Purpose: Decouple API requests from UI thread
- Pattern: PyQt signal emission, DesktopPet slot connection

## Entry Points

**Primary Entry:**
- Location: `src/desktop_pet/__main__.py` (via `python -m desktop_pet`)
- Location: `main.py` (PyInstaller standalone)
- Triggers: Command line execution
- Responsibilities: QApplication setup, logging config, DesktopPet instantiation

**System Tray Entry:**
- Location: `src/desktop_pet/__main__.py`
- Triggers: Application already running, tray icon click
- Responsibilities: Restore/hide pet, show context menu

**HTTP API Entry:**
- Location: `src/desktop_pet/api_server.py`
- Triggers: HTTP requests to configured port
- Responsibilities: Handle REST endpoints, emit motion signals

## Error Handling

**Strategy:** Graceful degradation with logging

**Patterns:**
- Try-except blocks around file I/O (images, configs)
- Fallback to default pet if loading fails (`_load_current_pet`)
- Silent failures for optional features (API server, rest reminder)
- Logging at appropriate levels (DEBUG for flow, ERROR for failures)

## Cross-Cutting Concerns

**Logging:** Python stdlib logging, configured in entry points with DEBUG/INFO levels, third-party loggers (PIL, aiohttp) set to WARNING

**Validation:** Coordinate bounds checking in API server, IP whitelist for API access, callback URL security checks

**Authentication:** IP-based whitelist for API access (configurable in user_config.json)

---

*Architecture analysis: 2026-04-13*