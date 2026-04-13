# Testing Patterns

**Analysis Date:** 2026-04-13

## Test Framework

**Runner:**
- Framework: `pytest` >= 8.0.0
- Config file: `pytest.ini`
- Async support: `pytest-asyncio` >= 0.23.0

**Assertion Library:**
- Built-in pytest assertions

**Run Commands:**
```bash
uv run pytest                  # Run all tests
uv run pytest -v              # Verbose mode
uv run pytest -v --tb=short   # Short traceback format
```

## Test File Organization

**Location:**
- Tests directory: `tests/`
- Scripts tests: Some tests reference code from `scripts/` directory

**Naming:**
- Pattern: `test_*.py` (e.g., `test_config_manager.py`, `test_api_server.py`)

**Structure:**
```
tests/
├── __init__.py              # Package marker
├── test_config_manager.py   # ConfigManager tests
├── test_api_server.py       # ApiServer tests
├── test_anchor_detector.py  # AnchorDetector tests (scripts)
└── test_alignment_processor.py  # AlignmentProcessor tests (scripts)
```

## Test Structure

**Suite Organization:**
- Test classes: `class TestClassName:` (e.g., `class TestAnchorDetector:`)
- Test methods: `test_method_name(self):` prefixed with `test_`
- Fixtures: Use `@pytest.fixture` decorator

**Patterns:**
```python
import pytest
from desktop_pet.config_manager import ConfigManager

@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with test configs."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    # Setup test data...
    return config_dir

def test_config_manager_loads_default_config(temp_config_dir: Path):
    """Test that ConfigManager loads default configuration."""
    manager = ConfigManager(config_dir=temp_config_dir)
    assert manager.pet.size == 200
```

## Mocking

**Framework:** Manual mocking (no mock library explicitly used)

**Patterns:**
- Create `MockPet` class for API server tests:
```python
class MockPet:
    """Mock pet object for testing."""
    class MockAPI:
        def get_position(self):
            return {"x": 100, "y": 200}
        def get_state(self):
            return "IDLE"
        # ... other methods
    api = MockAPI()
```

- Mock request objects for HTTP tests:
```python
class MockRequest:
    headers = {"X-Forwarded-For": "203.0.113.1, 70.41.3.18"}
    remote = "192.168.1.1"
```

**What to Mock:**
- External dependencies (HTTP requests, file I/O)
- Pet API interface
- Request/response objects

**What NOT to Mock:**
- Core business logic being tested
- Internal state changes

## Fixtures and Factories

**Test Data:**
- Use `tmp_path` fixture for temporary file/directory creation
- Create JSON config files in fixtures

**Location:**
- Defined in-line in test files using `@pytest.fixture` decorator

**Example:**
```python
@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with test configs."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    default_config = {
        "app": {"current_pet": "default"},
        "pet": {"size": 200, ...},
        ...
    }

    with open(config_dir / "default_config.json", "w", encoding="utf-8") as f:
        json.dump(default_config, f)

    return config_dir
```

## Coverage

**Requirements:** None explicitly enforced

**View Coverage:**
```bash
uv run pytest --cov=src/desktop_pet  # If pytest-cov is installed
```

## Test Types

**Unit Tests:**
- ConfigManager tests: Configuration loading and merging
- ApiServer tests: IP filtering, validation, request handling
- Focus on isolated logic

**Integration Tests:**
- Limited integration testing observed
- Some tests use real file operations with temp directories

**E2E Tests:**
- Not used in this project

## Common Patterns

**Async Testing:**
- Configured in `pytest.ini`: `asyncio_mode = auto` and `asyncio_default_fixture_loop_scope = function`
- Async tests use `async def test_...`:

```python
# pytest.ini
[pytest]
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

**Error Testing:**
- Test boundary conditions
- Test invalid inputs return expected error values

```python
# Invalid coordinates should return None
assert server._validate_coordinates({"x": 99999, "y": 0}) is None
assert server._validate_coordinates({"x": -99999, "y": 0}) is None

# Unsafe callback URLs should be rejected
assert server._is_safe_callback_url("http://localhost/callback") is False
assert server._is_safe_callback_url("http://192.168.1.1/callback") is False
```

**Test Isolation:**
- Use `tmp_path` fixture for file-based tests
- Each test creates its own isolated test data

## Configuration Files

**pytest.ini:**
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
filterwarnings =
    ignore::DeprecationWarning
```

**pyproject.toml (dev dependencies):**
```toml
[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]
```

---

*Testing analysis: 2026-04-13*