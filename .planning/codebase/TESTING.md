# Testing Patterns

**Analysis Date:** 2026-04-13 · **Updated:** 2026-06-29（平台化重构 + CLI 子命令扩展）

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
uv run pytest tests/test_multi_pet_integration.py -v  # 仅运行集成测试
```

## Test File Organization

**Location:**
- Tests directory: `tests/`
- Scripts tests: Some tests reference code from `scripts/` directory

**Naming:**
- Pattern: `test_*.py` (e.g., `test_pet_platform.py`, `test_api_server.py`)

**Structure:**
```
tests/
├── __init__.py
├── test_pet_instance.py            # PetInstanceConfig 数据模型测试
├── test_config_split.py            # GlobalConfigManager + InstancesStore 测试
├── test_pet_platform.py            # PetPlatform 平台核心测试
├── test_api_server.py              # ApiServer 多宠物路由测试
├── test_multi_pet_integration.py   # 端到端集成测试
├── test_pet_list_page.py           # 设置中心 UI 测试
├── test_cli_client.py              # CLI 子命令 HTTP 客户端测试（mock httpx.Client）
├── test_config_manager.py          # 旧版 ConfigManager 测试
├── test_motion_controller.py       # MotionModeController 测试
├── test_behavior_scheduler.py      # BehaviorScheduler 测试
├── test_screen_manager.py          # ScreenManager 测试
├── test_cross_screen_snap.py       # 跨屏吸附测试
├── test_display_config.py          # 显示配置测试
├── test_anchor_detector.py         # AnchorDetector tests (scripts)
└── test_alignment_processor.py     # AlignmentProcessor tests (scripts)
```

## Test Structure

**Suite Organization:**
- Test classes: `class TestClassName:` (e.g., `class TestMultiInstanceApiIsolation:`)
- Test methods: `test_method_name(self):` prefixed with `test_`
- Fixtures: Use `@pytest.fixture` decorator

**Patterns:**
```python
import pytest
from desktop_pet.pet_instance import PetInstanceConfig
from desktop_pet.pet_platform import PetPlatform

@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with test configs."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    # Setup test data...
    return config_dir

def test_pet_platform_creates_instance(temp_config_dir):
    """Test that PetPlatform creates instance."""
    platform = PetPlatform(config_dir=temp_config_dir, widget_factory=mock_factory)
    pet_id = platform.create_instance("default")
    assert pet_id in platform.list_pet_widgets()
```

## Mocking

**Framework:** Manual mocking (no mock library explicitly used)

**Patterns:**
- 平台测试中注入 mock `widget_factory`：签名 `(pet_id, config, pet_package) -> widget`，返回记录调用次数的 Mock 对象
- API server 测试中创建 `MockPlatform` 类实现 `list_instances` / `get_primary_instance` / `create_instance` / `destroy_instance` 等方法
- 集成测试中自定义 `_MockAPI` 与 `_MockWidget` 真实记录 `move_to_calls` 列表，以便断言不同实例互不干扰
- CLI 客户端测试用 `unittest.mock.patch("desktop_pet.cli_client.httpx.Client", return_value=mock_client)` 替换 httpx，mock 需设 `__enter__` / `__exit__`（因为代码用 `with httpx.Client(...) as client:`）
- Mock request objects for HTTP tests:
```python
class MockRequest:
    headers = {"X-Forwarded-For": "203.0.113.1, 70.41.3.18"}
    remote = "192.168.1.1"
```

**What to Mock:**
- External dependencies (HTTP requests, file I/O)
- widget_factory（避免创建真实 QWidget）
- Platform / Pet API interface

**What NOT to Mock:**
- Core business logic being tested
- Internal state changes
- `InstancesStore` 真实文件 I/O（用 `tmp_path` 隔离）

## Fixtures and Factories

**Test Data:**
- Use `tmp_path` fixture for temporary file/directory creation
- Create JSON config files in fixtures
- 平台测试用 `sample_meta` / `sample_actions` / `sample_package` fixture 构造测试用 `PetPackage`

**Location:**
- Defined in-line in test files using `@pytest.fixture` decorator

**Example:**
```python
@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with test configs."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir

@pytest.fixture
def patched_pet_loader(monkeypatch, sample_package):
    """Patch PetLoader.scan_pets to return sample package."""
    def _scan(self):
        return [sample_package]
    monkeypatch.setattr(PetLoader, "scan_pets", _scan)
```

## Coverage

**Requirements:** None explicitly enforced

**View Coverage:**
```bash
uv run pytest --cov=src/desktop_pet  # If pytest-cov is installed
```

**Current Status:** 252 tests passing（含 7 个集成测试 + 18 个 CLI 客户端测试）

## Test Types

**Unit Tests:**
- `test_pet_instance.py`: PetInstanceConfig 序列化与默认值
- `test_config_split.py`: GlobalConfigManager + InstancesStore CRUD
- `test_pet_platform.py`: PetPlatform 创建/销毁/列举/持久化
- `test_api_server.py`: ApiServer 多宠物路由、IP 过滤、工具调用
- `test_cli_client.py`: CLI 子命令 HTTP 客户端（mock httpx.Client，验证请求体与错误处理）
- Focus on isolated logic

**Integration Tests:**
- `test_multi_pet_integration.py`: 端到端验证
  - `TestMultiInstanceApiIsolation`: 2 个实例通过 API 分别控制互不干扰
  - `TestBackwardCompatibility`: 旧 API（无 pet_id）作用于主实例
  - `TestRestartRecovery`: 实例列表与配置完整恢复
  - `TestMcpToolDiscovery`: `/api/tools` 返回新工具与 `pet_id` 参数

**E2E Tests:**
- 通过 `aiohttp.test_utils.TestClient` 进行 in-process HTTP 端到端测试

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

**HTTP API Testing:**
```python
async def test_move_pet(api_client):
    resp = await api_client.post("/api/pets/pet_id_1/move", json={"x": 100, "y": 200})
    assert resp.status == 200
```

**Error Testing:**
- Test boundary conditions
- Test invalid inputs return expected error values

```python
# Invalid coordinates should return None
assert server._validate_coordinates({"x": 99999, "y": 0}) is None

# Unsafe callback URLs should be rejected
assert server._is_safe_callback_url("http://localhost/callback") is False
```

**Test Isolation:**
- Use `tmp_path` fixture for file-based tests
- Each test creates its own isolated test data
- 平台测试通过 `config_dir=tmp_path` 隔离 instances.json

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

*Testing analysis: 2026-04-13 · Updated: 2026-06-29（平台化重构 + CLI 子命令扩展）*