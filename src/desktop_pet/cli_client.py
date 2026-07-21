"""CLI HTTP 客户端：通过本地 HTTP API 控制正在运行的桌宠平台。

本模块供 ``desktop-pet add`` / ``desktop-pet list`` 子命令使用，封装：
- 从 ``config/user_config.json`` 读取 API 地址
- 探活主进程是否在运行
- 调用 ``POST /api/instances`` 创建实例
- 调用 ``GET /api/instances`` 列出实例

所有 HTTP 调用使用 ``httpx`` 同步客户端（CLI 是短命令，无需 async）。
"""
import json
import logging
from pathlib import Path

import httpx

from .utils import get_config_path

logger = logging.getLogger(__name__)

# 默认探活超时（秒）
_DEFAULT_CHECK_TIMEOUT = 2.0
# 默认请求超时（秒）
_DEFAULT_REQUEST_TIMEOUT = 15.0


class CliError(Exception):
    """CLI 业务错误，由 __main__.py 捕获后打印并 sys.exit(1)。"""


def get_api_base(config_dir: Path | None = None) -> str:
    """从 ``config/user_config.json`` 读取 API 地址，构造 ``http://<host>:<port>``。

    - ``host`` 为 ``0.0.0.0`` 时转为 ``127.0.0.1``（CLI 总是连本机）
    - 读取失败或字段缺失时回退 ``http://127.0.0.1:8080``
    """
    if config_dir is None:
        config_dir = get_config_path()
    user_config_path = Path(config_dir) / "user_config.json"

    host = "127.0.0.1"
    port = 8080
    try:
        with open(user_config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        api = data.get("api", {}) if isinstance(data, dict) else {}
        raw_host = api.get("host", host)
        # 0.0.0.0 表示监听所有网卡，CLI 连本机用 127.0.0.1
        if raw_host in ("0.0.0.0", "::", ""):
            host = "127.0.0.1"
        else:
            host = raw_host
        port = int(api.get("port", port))
    except (json.JSONDecodeError, IOError, ValueError, TypeError) as e:
        logger.debug("Failed to read api config from %s: %s", user_config_path, e)

    return f"http://{host}:{port}"


def check_main_process(api_base: str, timeout: float = _DEFAULT_CHECK_TIMEOUT) -> bool:
    """探活主进程：``GET /api/status`` 短超时，返回是否可达。"""
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{api_base}/api/status")
            return resp.status_code == 200
    except httpx.HTTPError as e:
        logger.debug("Main process check failed: %s", e)
        return False


def add_instance(
    api_base: str,
    package: str,
    x: int | None = None,
    y: int | None = None,
    timeout: float = _DEFAULT_REQUEST_TIMEOUT,
) -> dict:
    """``POST /api/instances`` 创建新桌宠实例。

    ``x`` / ``y`` 均为 None 时不传 position（由主进程使用包默认值）。
    成功返回 ``{"pet_id", "package", "position"}``。
    连接失败或 HTTP 非 2xx 抛 ``CliError``。
    """
    payload: dict = {"package": package}
    if x is not None or y is not None:
        payload["position"] = {
            "x": x if x is not None else 100,
            "y": y if y is not None else 100,
        }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{api_base}/api/instances", json=payload)
    except httpx.HTTPError as e:
        raise CliError(f"连接主进程失败：{e}") from e

    if resp.status_code != 201:
        raise CliError(
            f"创建实例失败（HTTP {resp.status_code}）：{_safe_text(resp)}"
        )

    try:
        return resp.json()
    except ValueError as e:
        raise CliError(f"主进程返回了非 JSON 响应：{e}") from e


def list_instances(
    api_base: str, timeout: float = _DEFAULT_REQUEST_TIMEOUT
) -> list[dict]:
    """``GET /api/instances`` 列出运行中实例。

    返回实例 dict 列表，每项含 ``pet_id`` / ``package`` / ``position`` 等字段。
    连接失败或 HTTP 非 2xx 抛 ``CliError``。
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{api_base}/api/instances")
    except httpx.HTTPError as e:
        raise CliError(f"连接主进程失败：{e}") from e

    if resp.status_code != 200:
        raise CliError(
            f"获取实例列表失败（HTTP {resp.status_code}）：{_safe_text(resp)}"
        )

    try:
        data = resp.json()
    except ValueError as e:
        raise CliError(f"主进程返回了非 JSON 响应：{e}") from e

    instances = data.get("instances", []) if isinstance(data, dict) else []
    return instances if isinstance(instances, list) else []


def remove_instance(
    api_base: str,
    pet_id: str,
    timeout: float = _DEFAULT_REQUEST_TIMEOUT,
) -> None:
    """``DELETE /api/instances/<pet_id>`` 销毁指定实例。

    成功（HTTP 200）无返回值；连接失败、HTTP 非 200 或 pet_id 不存在抛
    ``CliError``。pet_id 为空字符串时抛 ``CliError``（防御性）。
    """
    if not pet_id:
        raise CliError("pet_id 不能为空")
    url = f"{api_base}/api/instances/{pet_id}"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.delete(url)
    except httpx.HTTPError as e:
        raise CliError(f"连接主进程失败：{e}") from e

    if resp.status_code == 404:
        raise CliError(f"实例不存在：pet_id={pet_id}")
    if resp.status_code != 200:
        raise CliError(
            f"销毁实例失败（HTTP {resp.status_code}）：{_safe_text(resp)}"
        )


# ---------------------------------------------------------------------------
# 控制类指令：作用于指定 pet_id
# ---------------------------------------------------------------------------
def _post_pet_command(
    api_base: str,
    pet_id: str,
    endpoint: str,
    payload: dict,
    expected_status: int = 200,
    timeout: float = _DEFAULT_REQUEST_TIMEOUT,
) -> dict:
    """通用 ``POST /api/pets/<pet_id>/<endpoint>`` 调用。

    ``pet_id`` 为空字符串时抛 ``CliError``（防御性）。
    返回响应 JSON dict；HTTP 非 ``expected_status`` 抛 ``CliError``。
    """
    if not pet_id:
        raise CliError("pet_id 不能为空")
    url = f"{api_base}/api/pets/{pet_id}/{endpoint}"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload)
    except httpx.HTTPError as e:
        raise CliError(f"连接主进程失败：{e}") from e
    if resp.status_code != expected_status:
        raise CliError(f"指令失败（HTTP {resp.status_code}）：{_safe_text(resp)}")
    try:
        return resp.json()
    except ValueError as e:
        raise CliError(f"主进程返回了非 JSON 响应：{e}") from e


def play_animation(
    api_base: str,
    pet_id: str,
    name: str,
    timeout: float = _DEFAULT_REQUEST_TIMEOUT,
) -> dict:
    """``POST /api/pets/<pet_id>/animation`` 播放指定动画。"""
    return _post_pet_command(
        api_base, pet_id, "animation", {"name": name}, 200, timeout
    )


def walk_pet(
    api_base: str,
    pet_id: str,
    direction: str,
    timeout: float = _DEFAULT_REQUEST_TIMEOUT,
) -> dict:
    """``POST /api/pets/<pet_id>/walk`` 行走动画。"""
    return _post_pet_command(
        api_base, pet_id, "walk", {"direction": direction}, 200, timeout
    )


def move_to(
    api_base: str,
    pet_id: str,
    x: int,
    y: int,
    screen: int | None = None,
    timeout: float = _DEFAULT_REQUEST_TIMEOUT,
) -> dict:
    """``POST /api/pets/<pet_id>/move`` 移动到绝对坐标。"""
    payload: dict = {"x": x, "y": y}
    if screen is not None:
        payload["screen"] = screen
    return _post_pet_command(api_base, pet_id, "move", payload, 200, timeout)


def move_by(
    api_base: str,
    pet_id: str,
    dx: int,
    dy: int,
    timeout: float = _DEFAULT_REQUEST_TIMEOUT,
) -> dict:
    """``POST /api/pets/<pet_id>/move_by`` 相对移动。"""
    return _post_pet_command(
        api_base, pet_id, "move_by", {"dx": dx, "dy": dy}, 200, timeout
    )


def move_edge(
    api_base: str,
    pet_id: str,
    edge: str,
    screen: int | None = None,
    timeout: float = _DEFAULT_REQUEST_TIMEOUT,
) -> dict:
    """``POST /api/pets/<pet_id>/move_edge`` 移到屏幕边缘。"""
    payload: dict = {"edge": edge}
    if screen is not None:
        payload["screen"] = screen
    return _post_pet_command(api_base, pet_id, "move_edge", payload, 200, timeout)


def list_animations(
    api_base: str, pet_id: str, timeout: float = _DEFAULT_REQUEST_TIMEOUT
) -> list[str]:
    """``GET /api/pets/<pet_id>/animations`` 列出指定桌宠可用动画。"""
    if not pet_id:
        raise CliError("pet_id 不能为空")
    url = f"{api_base}/api/pets/{pet_id}/animations"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
    except httpx.HTTPError as e:
        raise CliError(f"连接主进程失败：{e}") from e
    if resp.status_code != 200:
        raise CliError(
            f"获取动画列表失败（HTTP {resp.status_code}）：{_safe_text(resp)}"
        )
    try:
        data = resp.json()
    except ValueError as e:
        raise CliError(f"主进程返回了非 JSON 响应：{e}") from e
    animations = data.get("animations", []) if isinstance(data, dict) else []
    return animations if isinstance(animations, list) else []


def show_bubble(
    api_base: str,
    pet_id: str,
    text: str,
    duration: int = 0,
    timeout: float = _DEFAULT_REQUEST_TIMEOUT,
) -> dict:
    """``POST /api/pets/<pet_id>/message`` 显示文字气泡。

    ``duration=0`` 表示持续显示（不自动隐藏）；``>0`` 表示 N 毫秒后自动隐藏。
    """
    return _post_pet_command(
        api_base, pet_id, "message",
        {"text": text, "duration": duration}, 200, timeout,
    )


def hide_bubble(
    api_base: str,
    pet_id: str,
    timeout: float = _DEFAULT_REQUEST_TIMEOUT,
) -> dict:
    """``POST /api/pets/<pet_id>/message/hide`` 隐藏文字气泡。"""
    return _post_pet_command(
        api_base, pet_id, "message/hide", {}, 200, timeout,
    )


def _safe_text(resp: httpx.Response) -> str:
    """安全提取响应文本用于错误信息（截断防过长）。"""
    try:
        text = resp.text
    except Exception:
        return ""
    return text[:200]
