import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


from .utils import get_config_path

logger = logging.getLogger(__name__)


@dataclass
class AnimationConfig:
    path: str
    width: int = 200
    height: int = 159


@dataclass
class ActionConfig:
    name: str
    enabled: bool = True
    weight: int = 1
    action_type: str = "animation"
    description: str = ""
    config: dict = field(default_factory=dict)
    animations: list[AnimationConfig] = field(default_factory=list)


@dataclass
class RestReminderConfig:
    enabled: bool = True
    interval_minutes: int = 55
    countdown_seconds: int = 300
    intensity: str = "normal"
    animation: AnimationConfig | None = None


@dataclass
class MovementConfig:
    random_interval_min_ms: int = 3000
    random_interval_max_ms: int = 15000


@dataclass
class PetConfig:
    size: int = 200
    regular_image: str = "images/pet_user_image.png"
    flying_image: str = "images/pet_flying.png"


@dataclass
class AppConfig:
    current_pet: str = "default"


@dataclass
class MotionModeConfig:
    enabled: bool = True
    default_mode: str = "random"
    movement_speed: int = 5
    animation_wait: bool = True


@dataclass
class ClickZoneConfig:
    name: str
    x: float
    y: float
    width: float
    height: float
    action: str


@dataclass
class ClickDetectionConfig:
    enabled: bool = False
    zones: list[ClickZoneConfig] = field(default_factory=list)


@dataclass
class BehaviorConfig:
    quiet_mode_enabled: bool = False
    default_head_action: str = "head"
    default_body_action: str = "body_tap"


@dataclass
class StartupConfig:
    enabled: bool = False
    start_hidden: bool = False


@dataclass
class TrayConfig:
    enabled: bool = True
    minimize_to_tray: bool = True


@dataclass
class DisplayConfig:
    """多显示器相关配置"""
    cross_screen_drag: bool = True            # 拖到边缘允许跨屏
    cross_screen_random_walk: bool = True     # 随机行为允许跨屏
    cross_screen_walk_probability: float = 0.3  # 走到边缘时跨屏的概率 (0.0~1.0)
    remember_last_screen: bool = True         # 重启时恢复上次所在屏
    default_screen_index: int | None = None   # 启动默认屏;None=主屏
    last_screen_index: int | None = None      # 上次运行时所在屏(运行时记录)


@dataclass
class LLMConfig:
    """LLM function calling 相关配置"""
    enabled: bool = False
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    system_prompt: str = "你是一个桌面宠物助手。用户会通过自然语言告诉你想让宠物做什么，你需要调用合适的工具来控制宠物。请用中文回复。"
    max_history: int = 20


_GLOBAL_SECTIONS: tuple[str, ...] = ("api", "tray", "startup", "display", "mcp", "llm")


class GlobalConfigManager:
    """仅管理全局配置字段的配置管理器。

    平台化拆分后，全局配置（api/tray/startup/display/mcp/llm）由本类管理，
    实例级配置（actions/rest_reminder/movement/behavior/motion_mode/click_detection/pet）
    由 ``InstancesStore`` 管理。

    本类复用 ``ConfigManager`` 的 dataclass（``StartupConfig`` / ``TrayConfig`` /
    ``DisplayConfig`` / ``LLMConfig``）以及 ``_load_json`` / ``_deep_merge`` 加载模式，
    但仅保留全局字段，不会暴露实例级属性。
    """

    def __init__(self, config_dir: Path | None = None):
        if config_dir is None:
            config_dir = get_config_path()
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.default_config_path = self.config_dir / "default_config.json"
        self.user_config_path = self.config_dir / "user_config.json"

        self._raw_config: dict[str, Any] = {}
        self._startup: StartupConfig | None = None
        self._tray: TrayConfig | None = None
        self._display: DisplayConfig | None = None
        self._llm: LLMConfig | None = None

        self.load_config()

    # ------------------------------------------------------------------
    # 加载与合并（复用 ConfigManager 的逻辑模式）
    # ------------------------------------------------------------------
    def load_config(self) -> None:
        default_config = self._load_json(self.default_config_path)
        user_config = self._load_json(self.user_config_path)

        merged = self._deep_merge(default_config, user_config)
        # 仅保留全局字段
        self._raw_config = {k: v for k, v in merged.items() if k in _GLOBAL_SECTIONS}
        self._parse_config()

    def _load_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "_comment" in data:
                    del data["_comment"]
                if "_instructions" in data:
                    del data["_instructions"]
                return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to load config file {path}: {e}")
            return {}

    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _parse_config(self) -> None:
        startup_data = self._raw_config.get("startup", {})
        self._startup = StartupConfig(
            enabled=startup_data.get("enabled", False),
            start_hidden=startup_data.get("start_hidden", False),
        )

        tray_data = self._raw_config.get("tray", {})
        self._tray = TrayConfig(
            enabled=tray_data.get("enabled", True),
            minimize_to_tray=tray_data.get("minimize_to_tray", True),
        )

        display_data = self._raw_config.get("display", {})
        try:
            prob = float(display_data.get("cross_screen_walk_probability", 0.3))
        except (TypeError, ValueError):
            prob = 0.3
        try:
            default_idx = display_data.get("default_screen_index")
            if default_idx is not None:
                default_idx = int(default_idx)
        except (TypeError, ValueError):
            default_idx = None
        try:
            last_idx = display_data.get("last_screen_index")
            if last_idx is not None:
                last_idx = int(last_idx)
        except (TypeError, ValueError):
            last_idx = None
        self._display = DisplayConfig(
            cross_screen_drag=display_data.get("cross_screen_drag", True),
            cross_screen_random_walk=display_data.get("cross_screen_random_walk", True),
            cross_screen_walk_probability=max(0.0, min(1.0, prob)),
            remember_last_screen=display_data.get("remember_last_screen", True),
            default_screen_index=default_idx,
            last_screen_index=last_idx,
        )

        llm_data = self._raw_config.get("llm", {})
        self._llm = LLMConfig(
            enabled=llm_data.get("enabled", False),
            api_key=llm_data.get("api_key", ""),
            base_url=llm_data.get("base_url", "https://api.openai.com/v1"),
            model=llm_data.get("model", "gpt-4o-mini"),
            system_prompt=llm_data.get("system_prompt", LLMConfig.system_prompt),
            max_history=llm_data.get("max_history", 20),
        )

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------
    @property
    def api(self) -> dict[str, Any]:
        """HTTP API 全局配置（原始 dict，结构参考 default_config.json 的 api 段）。"""
        return self._raw_config.get("api", {})

    @property
    def mcp(self) -> dict[str, Any]:
        """MCP 全局配置（原始 dict，结构参考 default_config.json 的 mcp 段）。"""
        return self._raw_config.get("mcp", {})

    @property
    def startup(self) -> StartupConfig:
        return self._startup or StartupConfig()

    @property
    def tray(self) -> TrayConfig:
        return self._tray or TrayConfig()

    @property
    def display(self) -> DisplayConfig:
        return self._display or DisplayConfig()

    @property
    def llm(self) -> LLMConfig:
        return self._llm or LLMConfig()

    @property
    def config(self) -> dict[str, Any]:
        """原始合并后的 dict（仅含全局字段）。"""
        return self._raw_config

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def reload_config(self) -> None:
        self.load_config()

    def save_global_settings(self, sections: dict[str, Any]) -> None:
        """将指定全局配置段落合并写入 user_config.json 并重新加载。

        与 ``ConfigManager.save_global_settings`` 行为一致：会保留 user_config.json
        中已有的其他段落（包括实例级字段），仅合并 ``sections`` 中指定的段落。
        """
        existing_config: dict[str, Any] = {}
        if self.user_config_path.exists():
            try:
                with open(self.user_config_path, "r", encoding="utf-8") as f:
                    existing_config = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        for section, values in sections.items():
            if isinstance(values, dict):
                current = existing_config.get(section, {})
                if not isinstance(current, dict):
                    current = {}
                current.update(values)
                existing_config[section] = current
            else:
                existing_config[section] = values

        with open(self.user_config_path, "w", encoding="utf-8") as f:
            json.dump(existing_config, f, ensure_ascii=False, indent=2)

        self.load_config()
