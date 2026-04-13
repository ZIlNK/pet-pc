# Coding Conventions

**Analysis Date:** 2026-04-13

## Naming Patterns

**Files:**
- Python modules: `snake_case.py` (e.g., `config_manager.py`, `api_server.py`)
- Test files: `test_*.py` (e.g., `test_config_manager.py`)
- Classes: `PascalCase` (e.g., `ConfigManager`, `ApiServer`, `DesktopPet`)

**Functions:**
- Methods: `snake_case` (e.g., `load_config`, `get_allowed_ips`)
- Private methods: Leading underscore (e.g., `_load_json`, `_deep_merge`)
- Async functions: `async def` prefix (e.g., `async def start`)

**Variables:**
- Instance variables: `snake_case` with optional underscore prefix for private (e.g., `self._running`, `self._allowed_ips`)
- Local variables: `snake_case` (e.g., `default_config`, `user_config`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_INTERVAL`, `MAX_RETRIES`)

**Types:**
- Type hints: Standard Python (e.g., `list[str]`, `dict[str, Any]`, `Optional[Path]`)
- Dataclasses: `PascalCase` with `Config` suffix (e.g., `ActionConfig`, `RestReminderConfig`)

## Code Style

**Formatting:**
- Tool: Not explicitly configured (no ruff, black, or formatter detected)
- Indentation: 4 spaces
- Line length: Not enforced
- Trailing commas: Not used consistently

**Linting:**
- Tool: Not explicitly configured (no pylint, flake8, or ruff detected)
- No linting configuration files found
- Basic Python syntax enforced by interpreter

## Import Organization

**Order:**
1. Standard library imports (e.g., `import json`, `from pathlib import Path`)
2. Third-party imports (e.g., `from PyQt6.QtCore import`, `import aiohttp`)
3. Local/relative imports (e.g., `from .utils import`, `from .config_manager import`)

**Path Aliases:**
- No path aliases configured (using relative imports: `from .module import`)

**Example:**
```python
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QMovie

from .utils import get_config_path
from .motion_controller import MotionModeController
```

## Error Handling

**Patterns:**
- Try-catch for file I/O: `try...except (json.JSONDecodeError, IOError) as e:` with logging
- Validation returns: Return `None` for invalid data (e.g., `_validate_coordinates`)
- Early returns: Use guard clauses for validation (e.g., `if not path.exists(): return {}`)
- Exception propagation: Log and continue or return default values

**Examples:**
```python
def _load_json(self, path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load config file {path}: {e}")
        return {}
```

```python
def _validate_coordinates(self, data: dict) -> tuple[int, int] | None:
    try:
        x = int(data.get("x", 0))
        y = int(data.get("y", 0))
        if x < -10000 or x > 10000 or y < -10000 or y > 10000:
            return None
        return x, y
    except (ValueError, TypeError):
        return None
```

## Logging

**Framework:** `logging` module

**Patterns:**
- Module logger: `logger = logging.getLogger(__name__)`
- Log levels: `logger.info`, `logger.warning`, `logger.error`, `logger.debug`
- Context logging: Include relevant data in log messages

**Examples:**
```python
logger = logging.getLogger(__name__)

logger.info(f"API server started: http://{self._host}:{self._port}")
logger.warning(f"Access denied: IP {client_ip} not in whitelist")
logger.error(f"Failed to load animation {full_path}: {e}")
```

## Comments

**When to Comment:**
- Document public API methods with docstrings
- Explain non-obvious logic or workarounds
- Chinese comments found in some test files (e.g., `"""锚点检测器测试"""`)

**JSDoc/TSDoc:**
- Not applicable (Python project)

**Example:**
```python
def _get_client_ip(self, request: Request) -> str:
    """Get real client IP, considering proxy headers."""
    # Check X-Forwarded-For header first (comma-separated, first is client)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    ...
```

## Function Design

**Size:** No strict limits; some functions are lengthy (e.g., `load_config` in `config_manager.py`)

**Parameters:**
- Type hints for all parameters
- Default values for optional parameters
- Group related parameters into dataclasses for complex configurations

**Return Values:**
- Explicit return types in type hints
- Return `None` for invalid states
- Return `bool` for success/failure operations

## Module Design

**Exports:**
- Package init: `__init__.py` exports public classes
- Explicit exports in `desktop_pet/__init__.py`:
```python
from .states import PetState
from .pet import DesktopPet
from .config_manager import ConfigManager, ActionManager, ActionConfig, MotionModeConfig
```

**Barrel Files:**
- No barrel files detected
- Direct imports from specific modules

---

*Convention analysis: 2026-04-13*