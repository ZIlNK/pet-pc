# Technology Stack

**Analysis Date:** 2026-04-13

## Languages

**Primary:**
- Python 3.10+ - Core application logic, UI, API server
- Python 3.10, 3.11, 3.12 - Supported versions per pyproject.toml

## Runtime

**Environment:**
- Python standard interpreter
- PyInstaller support for executable builds (dev dependency)

**Package Manager:**
- uv (official Python package manager)
- Lockfile: `uv.lock` (present in project)
- Configuration: `pyproject.toml`

## Frameworks

**Core UI:**
- PyQt6 >= 6.6.0 - Desktop GUI framework (Qt for Python)
- Used for: Main window, system tray, dialogs, widgets

**Image Processing:**
- Pillow >= 10.0.0 - Image loading, manipulation, and format conversion
- Used for: Animation frames, pet images, GIF processing

**HTTP/API:**
- aiohttp >= 3.9.0 - Async HTTP server for remote control API
- Used for: REST API server in `api_server.py`

**Build/Package:**
- hatchling - Build backend for pyproject.toml
- PyInstaller >= 6.0.0 (dev) - Compiles Python to Windows executable

**Development Tools (dev dependencies):**
- opencv-python >= 4.8.0 - Video processing for green screen removal
- numpy >= 1.24.0 - Numerical operations for image processing
- pytest >= 8.0.0 - Testing framework
- pytest-asyncio >= 0.23.0 - Async test support

## Key Dependencies

**Core Runtime:**
- `PyQt6>=6.6.0` - UI framework
- `Pillow>=10.0.0` - Image processing
- `aiohttp>=3.9.0` - HTTP API server

**Dev Dependencies:**
- `opencv-python>=4.8.0` - Green screen video processing
- `numpy>=1.24.0` - Image array operations
- `pytest>=8.0.0` - Testing
- `pytest-asyncio>=0.23.0` - Async testing
- `pyinstaller>=6.0.0` - Executable build

## Configuration

**Environment:**
- Configuration file-based: JSON config files in `config/`
- Default config: `config/default_config.json`
- User overrides: `config/user_config.json`
- ConfigManager merges defaults with user settings (deep merge)

**Configuration Options:**
- Actions (walk, sit, read animations)
- Rest reminder intervals
- Movement parameters
- Pet appearance (size, images)
- Motion mode settings
- API server configuration (host, port, IP whitelist)
- Startup behavior
- System tray settings

**Build:**
- `pyproject.toml` - Project metadata, dependencies, build config
- hatchling build system

## Platform Requirements

**Development:**
- Python >= 3.10
- uv package manager
- Windows (for system tray and startup features)

**Production:**
- Windows executable (via PyInstaller) or Python environment
- Desktop environment with system tray support

---

*Stack analysis: 2026-04-13*