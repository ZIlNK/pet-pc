import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING, Any
from PyQt6.QtWidgets import QLabel, QWidget, QMenu, QLineEdit, QPushButton, QVBoxLayout
from PyQt6.QtGui import QPixmap, QMovie, QImageReader, QAction, QCursor
from PyQt6.QtCore import Qt, QPoint, QTimer, QSize, pyqtSignal

from .states import PetState
from .state_machine import PetStateMachine
from .utils import get_assets_path
from .config_manager import (
    ActionConfig,
    ClickZoneConfig,
    RestReminderConfig,
    MovementConfig,
    PetConfig,
    BehaviorConfig,
    MotionModeConfig,
)
from .pet_loader import PetPackage
from .pet_instance import PetInstanceConfig, build_effective_actions
from .motion_controller import MotionModeController
from .motion_control_panel import MotionControlPanel
from .behavior_scheduler import BehaviorScheduler
from .screen_manager import ScreenInfo

if TYPE_CHECKING:
    from .pet_platform import PetPlatform

logger = logging.getLogger(__name__)


class ChatBubble(QWidget):
    """可交互的聊天气泡，用于显示消息和接收用户输入。"""

    message_sent = pyqtSignal(str)  # 用户发送消息时触发

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedWidth(220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # 消息显示区域
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(
            "color: #333; font-size: 12px; padding: 4px; background: transparent;"
        )
        self.message_label.setMaximumHeight(80)
        layout.addWidget(self.message_label)

        # 输入框
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("输入消息...")
        self.input_field.setStyleSheet(
            "border: 1px solid #ccc; border-radius: 4px; padding: 4px; font-size: 11px;"
        )
        self.input_field.returnPressed.connect(self._on_send)
        layout.addWidget(self.input_field)

        # 发送按钮
        self.send_button = QPushButton("发送")
        self.send_button.setFixedHeight(24)
        self.send_button.setStyleSheet(
            "background-color: #4a9eff; color: white; border: none; "
            "border-radius: 4px; font-size: 11px; padding: 2px 8px;"
        )
        self.send_button.clicked.connect(self._on_send)
        layout.addWidget(self.send_button)

        self.setStyleSheet(
            "background-color: white; border: 2px solid #4a9eff; "
            "border-radius: 10px;"
        )
        self.hide()

    def set_message(self, text: str):
        self.message_label.setText(text)

    def _on_send(self):
        text = self.input_field.text().strip()
        if text:
            self.message_sent.emit(text)
            self.input_field.clear()


class DesktopPet(QWidget):
    # 跨线程通信 signals（API server 在子线程的 asyncio loop 里调用这些 emit，
    # Qt 自动通过 QueuedConnection 投递到主线程执行对应的 slot，
    # 修复 QTimer.singleShot 在子线程不触发的 bug）
    show_chat_bubble_requested = pyqtSignal(str)
    hide_chat_bubble_requested = pyqtSignal()
    show_custom_bubble_requested = pyqtSignal(str, int)
    hide_custom_bubble_requested = pyqtSignal()

    def __init__(self, instance_config: PetInstanceConfig,
                 pet_package: PetPackage,
                 platform: "PetPlatform"):
        """Create a platform-owned desktop pet instance."""
        if instance_config is None or pet_package is None or platform is None:
            raise TypeError("DesktopPet requires instance_config, pet_package, and platform")
        super().__init__()
        self._instance_config = instance_config.clone()
        self._pet_package = pet_package
        self._platform = platform
        self._global_config = platform.global_config
        self._init_platform_mode(self._instance_config, pet_package, platform)

    def _init_platform_mode(
        self,
        instance_config: PetInstanceConfig,
        pet_package: PetPackage,
        platform: "PetPlatform",
    ) -> None:
        # 平台化核心引用
        self._instance_config = instance_config.clone()
        self._pet_package = pet_package
        self._platform = platform
        self._global_config = platform.global_config

        self.assets_path = get_assets_path()

        # 每个实例使用独立的 effective actions，不修改共享资源包。
        self.current_pet_package: PetPackage = pet_package
        self.effective_actions = build_effective_actions(pet_package, self._instance_config.actions)

        behavior_cfg = self.behavior_config
        self.behavior_scheduler = BehaviorScheduler(
            quiet_mode_enabled=behavior_cfg.quiet_mode_enabled,
            default_head_action=behavior_cfg.default_head_action,
            default_body_action=behavior_cfg.default_body_action,
        )

        # 状态机管理
        self._state_machine = PetStateMachine(self)
        self.state = self._state_machine.state  # 兼容属性

        self.movement_timer = QTimer()
        self.movement_timer.timeout.connect(self.random_move)
        self.previous_pos = QPoint(0, 0)
        self.current_animation_type: str | None = None
        self.current_action: ActionConfig | None = None

        self.rest_timer = QTimer()
        self.rest_timer.timeout.connect(self.show_rest_bubble)

        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_seconds = 0

        self.rest_timer_display = QTimer()
        self.rest_timer_display.timeout.connect(self.update_rest_timer_display)

        rest_config = self.rest_reminder_config
        self.rest_timer_seconds = rest_config.interval_minutes * 60
        if rest_config.enabled:
            self.rest_timer.start(rest_config.interval_minutes * 60 * 1000)
        self.rest_timer_display.start(1000)

        # 实例级 click_detection
        self._click_detection_enabled = False
        self._click_zones: list[ClickZoneConfig] = []
        click_detection_config = self.click_detection_config_dict
        self._click_detection_enabled = click_detection_config.get("enabled", False)
        click_zones_data = click_detection_config.get("zones", [])
        for zone_data in click_zones_data:
            self._click_zones.append(ClickZoneConfig(
                name=zone_data.get("name", ""),
                x=zone_data.get("x", 0.0),
                y=zone_data.get("y", 0.0),
                width=zone_data.get("width", 0.0),
                height=zone_data.get("height", 0.0),
                action=zone_data.get("action", "")
            ))

        self.current_gif: QMovie | None = None
        self.walk_left_gif: QMovie | None = None
        self.walk_right_gif: QMovie | None = None
        self.hui_gif: QMovie | None = None
        self.idle_gif: QMovie | None = None

        self.motion_controller = MotionModeController(self)
        motion_cfg = self.motion_mode_config
        self.motion_controller.configure(default_mode=motion_cfg.default_mode, movement_speed=motion_cfg.movement_speed, animation_wait=motion_cfg.animation_wait)
        self._connect_motion_controller_signals()

        # 所有实例共享平台的多屏幕管理器。
        if platform.screen_manager is None:
            raise RuntimeError("PetPlatform screen manager is not initialized")
        self.screen_manager = platform.screen_manager
        self.screen_manager.screens_changed.connect(self._on_screens_topology_changed)
        self.screen_manager.current_screen_changed.connect(self._on_current_screen_changed)

        # 跨线程 chat bubble signal（API 由平台统一管理，但仍需连接回调以备外部 emit）
        self.show_chat_bubble_requested.connect(self.show_chat_bubble)
        self.hide_chat_bubble_requested.connect(self.hide_chat_bubble)
        self.show_custom_bubble_requested.connect(self.show_custom_bubble)
        self.hide_custom_bubble_requested.connect(self._hide_custom_bubble)

        # 加载宠物包动画 + 点击区域
        self._load_pet_animations()
        self.load_click_zones_from_pet()

        self.initUI()
        self._on_set_mode_requested(motion_cfg.default_mode)

    def _connect_motion_controller_signals(self) -> None:
        """Connect the platform-owned motion controller to this widget."""
        self.motion_controller.move_to_requested.connect(self._on_move_to_requested)
        self.motion_controller.move_by_requested.connect(self._on_move_by_requested)
        self.motion_controller.move_to_edge_requested.connect(self._on_move_to_edge_requested)
        self.motion_controller.play_animation_requested.connect(self._on_play_animation_requested)
        self.motion_controller.play_walk_requested.connect(self._on_play_walk_requested)
        self.motion_controller.stop_animation_requested.connect(self._on_stop_animation_requested)
        self.motion_controller.set_mode_requested.connect(self._on_set_mode_requested)
    @property
    def rest_reminder_config(self) -> RestReminderConfig:
        """Return this instance's rest-reminder configuration."""
        data = self._instance_config.rest_reminder or {}
        return RestReminderConfig(
            enabled=data.get("enabled", True),
            interval_minutes=data.get("interval_minutes", 55),
            countdown_seconds=data.get("countdown_seconds", 300),
            intensity=data.get("intensity", "normal"),
            animation=None,
        )
    @property
    def movement_config(self) -> MovementConfig:
        """Return this instance's random-movement configuration."""
        data = self._instance_config.movement or {}
        return MovementConfig(
            random_interval_min_ms=data.get("random_interval_min_ms", 3000),
            random_interval_max_ms=data.get("random_interval_max_ms", 15000),
        )
    @property
    def behavior_config(self) -> BehaviorConfig:
        """Return this instance's behavior configuration."""
        data = self._instance_config.behavior or {}
        return BehaviorConfig(
            quiet_mode_enabled=data.get("quiet_mode_enabled", False),
            default_head_action=data.get("default_head_action", "head"),
            default_body_action=data.get("default_body_action", "body_tap"),
        )
    @property
    def pet_config(self) -> PetConfig:
        """Return this instance's visual-size configuration."""
        return PetConfig(
            size=self._instance_config.size or 200,
            regular_image="images/pet_user_image.png",
            flying_image="images/pet_flying.png",
        )
    @property
    def motion_mode_config(self) -> MotionModeConfig:
        """Return this instance's motion-mode configuration."""
        data = self._instance_config.motion_mode or {}
        return MotionModeConfig(
            enabled=data.get("enabled", True),
            default_mode=data.get("default_mode", "random"),
            movement_speed=data.get("movement_speed", 5),
            animation_wait=data.get("animation_wait", True),
        )
    @property
    def click_detection_config_dict(self) -> dict[str, Any]:
        """Return this instance's click-detection configuration."""
        return self._instance_config.click_detection or {}
    @property
    def display_config(self):
        """Return the platform-wide display configuration."""
        return self._global_config.display
    @property
    def _global_api_config_dict(self) -> dict[str, Any]:
        """Return the platform-wide HTTP API configuration."""
        return self._global_config.api or {}
    @property
    def _global_mcp_config_dict(self) -> dict[str, Any]:
        """Return the platform-wide MCP configuration."""
        return self._global_config.mcp or {}
    @property
    def tray_config(self):
        """Return the platform-wide tray configuration."""
        return self._global_config.tray
    def on_config_updated(self, new_config: PetInstanceConfig) -> None:
        self._instance_config = new_config.clone()
        self.effective_actions = build_effective_actions(
            self.current_pet_package, self._instance_config.actions
        )
        self._load_pet_animations()
        self.load_click_zones_from_pet()

        behavior = self.behavior_config
        self.behavior_scheduler = BehaviorScheduler(
            quiet_mode_enabled=behavior.quiet_mode_enabled,
            default_head_action=behavior.default_head_action,
            default_body_action=behavior.default_body_action,
        )
        motion = self.motion_mode_config
        self.motion_controller.configure(
            default_mode=motion.default_mode,
            movement_speed=motion.movement_speed,
            animation_wait=motion.animation_wait,
        )

        rest = self.rest_reminder_config
        self.rest_timer_seconds = rest.interval_minutes * 60
        self.rest_timer.stop()
        if rest.enabled:
            self.rest_timer.start(rest.interval_minutes * 60 * 1000)
        self._reload_visual_size()
        self._on_set_mode_requested(motion.default_mode)
        self.move(self._instance_config.position["x"], self._instance_config.position["y"])
        if self._instance_config.screen_index is not None:
            self.screen_manager.notify_pet_screen(
                self._instance_config.pet_id, self._instance_config.screen_index
            )

    def _reload_visual_size(self) -> None:
        pet_config = self.pet_config
        animations_dir = self.current_pet_package.animations_dir
        default_regular = self.assets_path / pet_config.regular_image
        default_flying = self.assets_path / pet_config.flying_image
        self.regular_pixmap = self._load_pixmap(
            animations_dir / self.current_pet_package.meta.regular_image,
            default_regular,
            pet_config.size,
        )
        self.flying_pixmap = self._load_pixmap(
            animations_dir / self.current_pet_package.meta.flying_image,
            default_flying,
            pet_config.size,
        )
        if self.hui_gif is not None:
            rest_animation_path = (
                animations_dir / self.current_pet_package.meta.rest_animation
            )
            self.hui_gif.setScaledSize(self._scaled_animation_size(rest_animation_path))
        if hasattr(self, "label"):
            self.label.setFixedSize(self.regular_pixmap.size())
            self.label.setPixmap(self.regular_pixmap)
        self._natural_pet_size = (self.regular_pixmap.width() + 100, self.regular_pixmap.height())
        self.setFixedSize(*self._natural_pet_size)

    def get_config(self) -> PetInstanceConfig:
        """Return a snapshot of the current instance configuration."""
        return self._instance_config.clone()
    def close_instance(self) -> None:
        """Explicitly remove this instance from the platform."""
        try:
            self._platform.destroy_instance(self._instance_config.pet_id)
        except Exception as exc:
            logger.exception("Failed to close pet instance %s", self._instance_config.pet_id)
            self.show_custom_bubble(f"关闭失败：{exc}", 5000)
    def _persist_position_if_platform(self) -> None:
        """Persist the widget's latest position through the owning platform."""
        try:
            self._platform.persist_instance_position(
                self._instance_config.pet_id, self.x(), self.y()
            )
            self._instance_config.position = {"x": int(self.x()), "y": int(self.y())}
        except Exception:
            logger.exception(
                "Failed to persist position for pet %s",
                self._instance_config.pet_id,
            )
    @property
    def state(self) -> PetState:
        """获取当前状态（兼容属性）"""
        return self._state_machine.state

    @state.setter
    def state(self, value: PetState):
        """设置状态（兼容属性，优先使用状态机方法）"""
        self._state_machine.transition_to(value, force=True)

    def _load_pixmap(self, image_path: Path, default_path: Path, size: int) -> QPixmap:
        """加载并缩放图片

        Args:
            image_path: 首选图片路径
            default_path: 备用默认路径
            size: 目标尺寸

        Returns:
            缩放后的 QPixmap
        """
        # 优先使用指定路径，否则回退到默认
        target_path = image_path if image_path.exists() else default_path
        pixmap = QPixmap(str(target_path))
        return pixmap.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

    def _animation_canvas_size(self) -> QSize:
        """Return the regular image size fitted into the configured square bound."""
        pet_config = self.pet_config
        regular_path = (
            self.current_pet_package.animations_dir
            / self.current_pet_package.meta.regular_image
        )
        if not regular_path.exists():
            regular_path = self.assets_path / pet_config.regular_image

        source_size = QImageReader(str(regular_path)).size()
        bounds = QSize(pet_config.size, pet_config.size)
        if not source_size.isValid():
            return bounds
        return source_size.scaled(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def _scaled_animation_size(self, animation_path: Path) -> QSize:
        """Fit an animation into the regular-image canvas without distortion."""
        canvas_size = self._animation_canvas_size()
        source_size = QImageReader(str(animation_path)).size()
        if not source_size.isValid():
            return canvas_size
        scale = min(
            canvas_size.width() / source_size.width(),
            canvas_size.height() / source_size.height(),
        )
        return QSize(
            min(canvas_size.width(), round(source_size.width() * scale)),
            min(canvas_size.height(), round(source_size.height() * scale)),
        )

    def _load_pet_animations(self) -> None:
        for attr in ("idle_gif", "walk_left_gif", "walk_right_gif"):
            movie = getattr(self, attr, None)
            if movie is not None:
                movie.stop()
            setattr(self, attr, None)

        if not self.current_pet_package:
            return

        animations_dir = self.current_pet_package.animations_dir

        for action in self.effective_actions:
            if not action.enabled:
                continue
            if action.name == "idle" and action.animation_files:
                idle_path = animations_dir / action.animation_files[0]
                if idle_path.exists():
                    try:
                        self.idle_gif = QMovie(str(idle_path))
                        self.idle_gif.setScaledSize(self._scaled_animation_size(idle_path))
                    except Exception as e:
                        logger.error(f"Failed to load idle animation: {e}")

            if action.name == "walk" and action.animation_files:
                if len(action.animation_files) >= 1:
                    walk_left_path = animations_dir / action.animation_files[0]
                    if walk_left_path.exists():
                        try:
                            self.walk_left_gif = QMovie(str(walk_left_path))
                            self.walk_left_gif.setScaledSize(self._scaled_animation_size(walk_left_path))
                        except Exception as e:
                            logger.error(f"Failed to load walk_left animation: {e}")
                if len(action.animation_files) >= 2:
                    walk_right_path = animations_dir / action.animation_files[1]
                    if walk_right_path.exists():
                        try:
                            self.walk_right_gif = QMovie(str(walk_right_path))
                            self.walk_right_gif.setScaledSize(self._scaled_animation_size(walk_right_path))
                        except Exception as e:
                            logger.error(f"Failed to load walk_right animation: {e}")

    def _detect_click_zone(self, x: float, y: float) -> str | None:
        for zone in self._click_zones:
            if (zone.x <= x <= zone.x + zone.width and
                zone.y <= y <= zone.y + zone.height):
                return zone.name
        return None

    def _play_zone_animation(self, zone_name: str) -> None:
        for zone in self._click_zones:
            if zone.name == zone_name:
                self.play_animation_action_by_name(zone.action)
                return

    def _available_action_names(self) -> list[str]:
        if not self.current_pet_package:
            return []
        return [action.name for action in self.effective_actions if action.enabled]

    def play_animation_action_by_name(self, action_name: str) -> None:
        if not self.current_pet_package:
            return
        for action in self.effective_actions:
            if action.name == action_name:
                self.play_animation_action(action)
                return

    def set_click_detection_enabled(self, enabled: bool) -> None:
        self._click_detection_enabled = enabled

    def set_click_zones(self, zones: list[ClickZoneConfig]) -> None:
        self._click_zones = zones

    def load_click_zones_from_pet(self) -> None:
        config = self.click_detection_config_dict
        self._click_detection_enabled = bool(config.get("enabled", False))
        self._click_zones = [
            ClickZoneConfig(
                name=zone.get("name", ""),
                x=zone.get("x", 0.0),
                y=zone.get("y", 0.0),
                width=zone.get("width", 0.0),
                height=zone.get("height", 0.0),
                action=zone.get("action", ""),
            )
            for zone in config.get("zones", [])
        ]

    def initUI(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        pet_config = self.pet_config
        default_regular = self.assets_path / pet_config.regular_image
        default_flying = self.assets_path / pet_config.flying_image

        # 从当前 PetPackage 加载静态图片
        if self.current_pet_package:
            animations_dir = self.current_pet_package.animations_dir
            regular_path = animations_dir / self.current_pet_package.meta.regular_image
            flying_path = animations_dir / self.current_pet_package.meta.flying_image
        else:
            regular_path = default_regular
            flying_path = default_flying

        # 使用统一的加载方法
        self.regular_pixmap = self._load_pixmap(regular_path, default_regular, pet_config.size)
        self.flying_pixmap = self._load_pixmap(flying_path, default_flying, pet_config.size)

        # 从当前资源包加载休息提醒动画
        if self.current_pet_package:
            animations_dir = self.current_pet_package.animations_dir
            rest_animation_name = self.current_pet_package.meta.rest_animation
            rest_animation_path = animations_dir / rest_animation_name
            if rest_animation_path.exists():
                try:
                    self.hui_gif = QMovie(str(rest_animation_path))
                    self.hui_gif.setScaledSize(self._scaled_animation_size(rest_animation_path))
                except Exception as e:
                    logger.error(f"Failed to load rest reminder animation: {e}")
                    self.hui_gif = None
            else:
                # 回退到默认配置
                self.hui_gif = None
        else:
            # 回退到默认配置
            self.hui_gif = None

        self.label = QLabel(self)
        self.label.setFixedSize(self.regular_pixmap.size())
        self.label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.label.setPixmap(self.regular_pixmap)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        self.bubble_label = QLabel(self)
        self.bubble_label.setText("注意休息！\n点击开始倒计时")
        self.bubble_label.setStyleSheet(
            """
            background-color: white;
            border: 2px solid #ccc;
            border-radius: 10px;
            padding: 8px;
            color: black;
            font-size: 12px;
            text-align: center;
            """
        )
        self.bubble_label.installEventFilter(self)
        self.bubble_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        pet_width = self.regular_pixmap.width()
        bubble_width = 120
        x_pos = (pet_width - bubble_width) // 2
        y_pos = 25
        self.bubble_label.move(x_pos, y_pos)
        self.bubble_label.hide()

        # 可交互聊天气泡（用于 MCP/AI 消息交互）
        self.chat_bubble = ChatBubble()
        self.chat_bubble.message_sent.connect(self._on_chat_message_sent)

        original_width = self.regular_pixmap.width()
        increased_width = original_width + 100
        # 保存自然尺寸(用于跨屏 DPI 缩放后还原 + 计算贴底位置)
        self._natural_pet_size = (increased_width, self.regular_pixmap.height())
        self._in_size_reset = False
        self.resize(*self._natural_pet_size)
        # 固定尺寸:防止 Windows per-monitor DPI 缩放把 widget 撑大
        # 跨屏时被 OS 拉到 3.4x DPI 屏后,widget 物理尺寸会变 1013x539,
        # 导致贴底算法算错 Y(顶在屏中)。setFixedSize 把 widget 卡在自然尺寸。
        self.setFixedSize(*self._natural_pet_size)

        self.label.move(0, 0)
        
        bubble_width = 120
        x_pos = 10
        y_pos = 10
        self.bubble_label.move(x_pos, y_pos)

        # 选择启动屏幕:remember_last_screen > default_screen_index > 主屏
        display_cfg = self.display_config
        target_screen = None

        instance_screen_index = self._instance_config.screen_index
        instance_position = self._instance_config.position

        if instance_screen_index is not None:
            target_screen = self.screen_manager.screen_by_index(instance_screen_index)
        if target_screen is None and display_cfg.remember_last_screen and display_cfg.last_screen_index is not None:
            target_screen = self.screen_manager.screen_by_index(display_cfg.last_screen_index)
        if target_screen is None and display_cfg.default_screen_index is not None:
            target_screen = self.screen_manager.screen_by_index(display_cfg.default_screen_index)
        if target_screen is None:
            target_screen = self.screen_manager.primary_screen()
        if target_screen is None:
            # 极端兜底:取第一块屏
            all_s = self.screen_manager.all_screens()
            target_screen = all_s[0] if all_s else None

        if instance_position and isinstance(instance_position, dict):
            x = int(instance_position.get("x", 100))
            y = int(instance_position.get("y", 0))
        elif target_screen is not None:
            g = target_screen.available_geometry
            x = g.x() + 100
            y = g.y() + g.height() - self.height()
        else:
            # 无屏幕的极端情况(理论上不会发生),保持原行为
            x, y = 100, 0
        self.move(x, y)
        self.switch_to_static(self.regular_pixmap)

        self.is_dragging = False
        self.drag_position = QPoint()
        self.setMouseTracking(True)

    def resizeEvent(self, event):
        """检测跨屏 DPI 缩放并强制还原到自然尺寸。"""
        super().resizeEvent(event)
        natural_w, natural_h = self._natural_pet_size
        cur_w, cur_h = self.width(), self.height()
        if (cur_w, cur_h) != (natural_w, natural_h) and not self._in_size_reset:
            self._in_size_reset = True
            self.resize(natural_w, natural_h)
            self._in_size_reset = False

    def _natural_pet_height(self) -> int:
        """返回 widget 的逻辑高度(用于贴底计算,避免 DPI 缩放后用错尺寸)。"""
        return self._natural_pet_size[1]

    def start_random_movement_timer(self):
        movement_config = self.movement_config
        random_interval = random.randint(
            movement_config.random_interval_min_ms,
            movement_config.random_interval_max_ms
        )
        self.movement_timer.start(random_interval)

    def show_rest_bubble(self):
        rest_config = self.rest_reminder_config
        if rest_config.intensity == "gentle":
            reminder_text = "休息一下吧\n点击开始倒计时"
        elif rest_config.intensity == "strong":
            reminder_text = "该休息了！\n点击开始倒计时"
        else:
            reminder_text = "注意休息！\n点击开始倒计时"
        self.bubble_label.setText(reminder_text)
        bubble_width = 120
        x_pos = 10
        y_pos = 10
        self.bubble_label.move(x_pos, y_pos)
        self.bubble_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.bubble_label.show()

        self.state = PetState.REST_REMINDER
        self.movement_timer.stop()

        if self.motion_controller.get_mode() == "motion":
            self.motion_controller.pause_motion()

        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()

        if self.hui_gif and self.hui_gif.isValid():
            self.label.setMovie(self.hui_gif)
            self.hui_gif.start()
            self.current_gif = self.hui_gif

    def bubble_clicked(self, event=None):
        was_motion_mode = self.motion_controller.get_mode() == "motion"

        self.rest_timer.stop()

        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()

        self.switch_to_static()
        self.state = PetState.IDLE

        rest_config = self.rest_reminder_config
        self.countdown_seconds = rest_config.countdown_seconds
        self.bubble_label.setText(f"休息倒计时: {self.countdown_seconds}")
        self.countdown_timer.start(1000)

        if was_motion_mode:
            self.motion_controller.resume_motion()

    def update_countdown(self):
        self.countdown_seconds -= 1
        if self.countdown_seconds > 0:
            self.bubble_label.setText(f"休息倒计时: {self.countdown_seconds}")
        else:
            self.countdown_timer.stop()
            self.bubble_label.setText("休息一下吧！")
            QTimer.singleShot(2000, self.restart_rest_timer)

    def update_rest_timer_display(self):
        self.rest_timer_seconds = max(0, self.rest_timer_seconds - 1)

    def restart_rest_timer(self):
        self.bubble_label.hide()
        self.bubble_label.setText("注意休息！\n点击开始倒计时")
        rest_config = self.rest_reminder_config
        self.rest_timer_seconds = rest_config.interval_minutes * 60
        self.rest_timer.start(rest_config.interval_minutes * 60 * 1000)

    def show_custom_bubble(self, text: str, duration_ms: int = 5000):
        """显示自定义气泡消息（用于 CLI/MCP/AI 消息展示）。

        视觉样式同休息提醒气泡（灰边框、居中、120px），但保持鼠标穿透
        以避免点击误触休息倒计时。

        Args:
            text: 要显示的消息文本
            duration_ms: 显示时长（毫秒），0=持续显示，默认 5 秒
        """
        self.bubble_label.setText(text)
        self.bubble_label.setStyleSheet(
            """
            background-color: white;
            border: 2px solid #ccc;
            border-radius: 10px;
            padding: 8px;
            color: black;
            font-size: 12px;
            text-align: center;
            """
        )
        bubble_width = 120
        x_pos = 10
        y_pos = 10
        self.bubble_label.setFixedWidth(bubble_width)
        self.bubble_label.move(x_pos, y_pos)
        self.bubble_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.bubble_label.show()
        if duration_ms > 0:
            QTimer.singleShot(duration_ms, self._hide_custom_bubble)

    def _hide_custom_bubble(self):
        """隐藏自定义气泡并恢复休息提醒气泡默认文案"""
        self.bubble_label.hide()
        self.bubble_label.setText("注意休息！\n点击开始倒计时")

    def show_chat_bubble(self, message: str = ""):
        """显示可交互的聊天气泡。

        Args:
            message: 初始显示的消息文本
        """
        if message:
            self.chat_bubble.set_message(message)
        # 定位在宠物上方
        self.chat_bubble.move(self.x() - 110, self.y() - 140)
        self.chat_bubble.show()

    def hide_chat_bubble(self):
        """隐藏聊天气泡"""
        self.chat_bubble.hide()

    def _on_chat_message_sent(self, text: str):
        """Forward a chat-bubble message to the platform API queue."""
        self._platform.api_server.add_user_message(text)
        logger.info("[ChatBubble] User sent message: %s", text)
    def _toggle_chat_bubble(self):
        """切换聊天气泡的显示/隐藏"""
        if self.chat_bubble.isVisible():
            self.chat_bubble.hide()
        else:
            self.chat_bubble.set_message("有什么想说的？")
            self.chat_bubble.move(self.x() - 110, self.y() - 140)
            self.chat_bubble.show()

    def switch_to_gif(self, direction: str = 'right'):
        if self.state == PetState.REST_REMINDER:
            logger.debug("Skipping GIF switch during rest reminder state")
            return
        
        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()
        
        logger.debug(f"Switching to {direction} GIF")
        target_gif = self.walk_left_gif if direction == 'left' else self.walk_right_gif

        if target_gif and target_gif.isValid():
            logger.debug(f"Showing {direction} GIF")
            self.label.setMovie(target_gif)
            target_gif.start()
            self.current_gif = target_gif
        else:
            logger.debug("Target GIF not found or invalid, switching to static image")
            self.switch_to_static()

    def switch_to_static(self, pixmap: QPixmap | None = None):
        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()

        if pixmap is None:
            pixmap = self.regular_pixmap
        self.label.setPixmap(pixmap)
        
        if self.state != PetState.REST_REMINDER:
            self.state = PetState.IDLE
            self.start_random_movement_timer()
    
    def play_animation_action(self, action: ActionConfig):
        if self.state == PetState.REST_REMINDER:
            logger.debug("Skipping animation during rest reminder state")
            return

        self.movement_timer.stop()

        self._disconnect_current_gif_signals()

        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()

        logger.info(f"Playing animation: {action.name}")

        movie = self._load_pet_animation(action.name)
        if movie and movie.isValid():
            logger.debug(f"Showing animation GIF: {action.name}")
            self.label.setMovie(movie)

            self.current_animation_type = action.name
            self.current_action = action

            movie.finished.connect(self._on_animation_finished)
            movie.frameChanged.connect(self._check_gif_finished)

            self.previous_frame = -1
            self.gif_played_once = False

            movie.start()
            self.current_gif = movie
        else:
            logger.debug("Animation GIF not found, showing static image")
            self.switch_to_static()
            self.start_random_movement_timer()

    def _load_pet_animation(self, action_name: str) -> QMovie | None:
        if not self.current_pet_package:
            return None

        animations_dir = self.current_pet_package.animations_dir

        pet_action = None
        for action in self.effective_actions:
            if action.name == action_name:
                pet_action = action
                break

        if not pet_action or not pet_action.animation_files:
            return None

        animation_file = pet_action.animation_files[0]
        animation_path = animations_dir / animation_file

        if not animation_path.exists():
            return None

        try:
            movie = QMovie(str(animation_path))
            movie.setScaledSize(self._scaled_animation_size(animation_path))
            return movie
        except Exception as e:
            logger.error(f"Failed to load animation {animation_path}: {e}")
            return None
    
    def _disconnect_current_gif_signals(self):
        if self.current_gif:
            try:
                self.current_gif.finished.disconnect()
            except TypeError:
                pass
            try:
                self.current_gif.frameChanged.disconnect()
            except TypeError:
                pass
    
    def _on_animation_finished(self):
        action_name = self.current_animation_type
        logger.debug(f"Animation finished: {action_name}")
        
        self._disconnect_current_gif_signals()
        self.switch_to_static()
        self.start_random_movement_timer()

    def _check_gif_finished(self):
        if self.current_gif:
            frame_count = self.current_gif.frameCount()
            current_frame = self.current_gif.currentFrameNumber()
            
            if hasattr(self, 'previous_frame') and frame_count > 0:
                if not self.gif_played_once and (
                    current_frame == frame_count or 
                    (self.previous_frame > current_frame and self.previous_frame > 0)
                ):
                    self.gif_played_once = True
                    self._on_animation_finished()
            
            self.previous_frame = current_frame

    def execute_movement_action(self, action: ActionConfig):
        if self.state == PetState.IDLE:
            current = self._current_screen_info()
            if current is None:
                return
            g = current.available_geometry

            direction = random.choice([-1, 1])
            logger.debug(f"Random movement direction: {direction}")

            config = action.config
            min_dist = config.get("min_distance", 30)
            max_dist = config.get("max_distance", 100)
            move_distance = random.randint(min_dist, max_dist)

            current_x = self.x()
            new_x = current_x + (direction * move_distance)

            pet_width = self.width()
            min_x = g.x()
            max_x = g.x() + g.width() - pet_width
            new_x = max(min_x, min(new_x, max_x))

            y = g.y() + g.height() - self.height()

            # 跨屏机会
            cross = self._maybe_cross_screen_random(direction, new_x)
            if cross is not None:
                new_x, new_y_cross, dest = cross
                self._do_cross_screen_move(new_x, new_y_cross, dest)
                return

            if direction < 0:
                self.switch_to_gif('left')
            else:
                self.switch_to_gif('right')

            self.start_smooth_move(current_x, new_x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.previous_pos = event.globalPosition().toPoint()
            self.state = PetState.DRAGGING
            self._press_time = event.timestamp()
            if hasattr(self, 'inertia_timer') and self.inertia_timer:
                self.inertia_timer.stop()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.is_dragging:
            new_x = event.globalPosition().toPoint().x() - self.drag_position.x()
            old_x = self.x()

            if new_x < old_x:
                self.switch_to_gif('left')
            elif new_x > old_x:
                self.switch_to_gif('right')

            self.move(event.globalPosition().toPoint() - self.drag_position)
            self.previous_pos = event.globalPosition().toPoint()
            # 拖拽跨屏时更新当前屏
            new_info = self.screen_manager.screen_for_widget(self)
            cur = self._current_screen_info()
            if new_info is not None and (cur is None or new_info.index != cur.index):
                self.screen_manager.notify_pet_screen(self._instance_config.pet_id, new_info.index)
            event.accept()

    def snap_to_edge(self):
        """贴到当前屏幕底部;若紧贴相邻屏幕的边且配置允许,跨到相邻屏"""
        current = self._current_screen_info()
        if current is None:
            return
        g = current.available_geometry
        pet_geometry = self.geometry()

        x = pet_geometry.x()
        width = pet_geometry.width()
        y_axis = g.y() + g.height() - pet_geometry.height()

        # 检查是否需要跨屏
        display_cfg = self.display_config
        if display_cfg.cross_screen_drag:
            # 仅当贴在该侧 5px 内时尝试跨屏
            margin = 5
            if x <= g.x() + margin:
                dest = self.screen_manager.cross_screen_destination(current, "left")
                if dest is not None:
                    new_x = self.screen_manager.opposite_edge_x(dest, "left", width)
                    self._do_cross_screen_move(new_x, y_axis, dest)
                    return
            elif x >= g.x() + g.width() - width - margin:
                dest = self.screen_manager.cross_screen_destination(current, "right")
                if dest is not None:
                    new_x = self.screen_manager.opposite_edge_x(dest, "right", width)
                    self._do_cross_screen_move(new_x, y_axis, dest)
                    return

        min_x = g.x()
        max_x = g.x() + g.width() - width
        x = max(min_x, min(x, max_x))

        self.move(x, y_axis)
        self.switch_to_static(self.regular_pixmap)
        self.state = PetState.IDLE

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            self.state = PetState.INERTIA

            press_time = getattr(self, '_press_time', 0)
            release_time = event.timestamp()
            click_duration = release_time - press_time
            is_click = click_duration < 200

            current_pos = event.globalPosition().toPoint()
            pos_diff = current_pos - self.previous_pos
            velocity_x = pos_diff.x() / 2
            velocity_y = pos_diff.y() / 2

            if is_click and self._click_detection_enabled:
                pet_pos = self.frameGeometry().topLeft()
                click_x = (current_pos.x() - pet_pos.x()) / self.width()
                click_y = (current_pos.y() - pet_pos.y()) / self.height()
                zone_name = self._detect_click_zone(click_x, click_y)
                if zone_name:
                    self._play_zone_animation(zone_name)
                    event.accept()
                    return
                default_action = self.behavior_scheduler.default_click_action(
                    click_x, click_y, self._available_action_names()
                )
                if default_action:
                    self.play_animation_action_by_name(default_action)
                    event.accept()
                    return

            self.start_inertia(velocity_x, velocity_y)

            if velocity_x < 0:
                self.switch_to_gif('left')
            elif velocity_x > 0:
                self.switch_to_gif('right')
            else:
                self.switch_to_static()

            QTimer.singleShot(200, self._post_release_safety_check)

            event.accept()

    def contextMenuEvent(self, event):
        context_menu = QMenu(self)

        chat_action = QAction("与 AI 对话", self)
        chat_action.triggered.connect(self._toggle_chat_bubble)
        context_menu.addAction(chat_action)

        open_settings_action = QAction("打开设置中心", self)
        open_settings_action.triggered.connect(self._open_settings_center)
        context_menu.addAction(open_settings_action)

        context_menu.addSeparator()
        close_instance_action = QAction("关闭此桌宠", self)
        close_instance_action.triggered.connect(self.close_instance)
        context_menu.addAction(close_instance_action)

        context_menu.exec(event.globalPos())
    def _open_settings_center(self):
        """Open the platform settings center."""
        from .settings_center import SettingsCenter

        settings_center = SettingsCenter(self._platform, self)
        settings_center.exec()
    def _switch_to_motion_mode(self):
        self.motion_controller.set_mode("motion")

    def _switch_to_random_mode(self):
        self.motion_controller.set_mode("random")

    def _on_set_mode_requested(self, mode: str):
        if mode == "random":
            self.movement_timer.stop()
            if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
                self.current_gif.stop()
            self.switch_to_static()
            self.state = PetState.IDLE
            self.start_random_movement_timer()
        else:
            self.movement_timer.stop()
            self.state = PetState.MOTION_MODE

    def _on_move_to_requested(self, x: int, y: int, screen_index=None):
        pet_width = self.width()
        pet_height = self.height()

        # 解析目标屏幕
        target_screen = self._resolve_target_screen(screen_index, x, y)
        if target_screen is not None:
            # 把坐标先钳制到目标屏,再视情况做跨屏提示
            x, y = self.screen_manager.clamp_to_screen(target_screen, x, y, pet_width, pet_height)
            info = target_screen
        else:
            info = self._current_screen_info()

        # 当显式指定了不同屏幕,直接传送过去(不动画跨屏)
        current_info = self._current_screen_info()
        cross_screen = (
            screen_index is not None
            and current_info is not None
            and info is not None
            and info.index != current_info.index
        )

        if cross_screen:
            # 跨屏传送:不切换方向动画(避免误判),直接落位
            self._do_cross_screen_move(x, y, info)
            return

        current_x = self.x()
        current_y = self.y()

        if x < current_x:
            self.switch_to_gif('left')
        elif x > current_x:
            self.switch_to_gif('right')

        self.start_smooth_move(current_x, x, y)

    def _on_move_by_requested(self, dx: int, dy: int):
        current_x = self.x()
        current_y = self.y()
        self._on_move_to_requested(current_x + dx, current_y + dy, None)

    def _on_move_to_edge_requested(self, edge: str, screen_index=None):
        pet_width = self.width()

        target = self._resolve_target_screen(screen_index, None, None)
        if target is None:
            target = self._current_screen_info()
        if target is None:
            return

        g = target.available_geometry
        if edge == "left":
            x = g.x()
        elif edge == "right":
            x = g.x() + g.width() - pet_width
        else:
            return
        y = self.y()

        current_info = self._current_screen_info()
        cross_screen = (
            current_info is not None
            and target.index != current_info.index
        )
        if cross_screen:
            self._do_cross_screen_move(x, y, target)
            return

        self._on_move_to_requested(x, y, target.index)

    def _on_play_animation_requested(self, name: str):
        action = self.effective_actions if self.current_pet_package else []
        found_action = None
        for a in action:
            if a.name == name:
                found_action = a
                break
        if found_action:
            self.play_animation_action(found_action)

    def _on_play_walk_requested(self, direction: str, screen_index=None):
        pet_width = self.width()

        target = self._resolve_target_screen(screen_index, None, None)
        if target is None:
            target = self._current_screen_info()
        if target is None:
            return

        g = target.available_geometry
        if direction == "left":
            target_x = g.x()
        else:
            target_x = g.x() + g.width() - pet_width

        current_info = self._current_screen_info()
        cross_screen = (
            current_info is not None
            and target.index != current_info.index
        )
        if cross_screen:
            # 跨屏时:先切方向动画,再做平滑移动
            self.switch_to_gif(direction)
            self.start_smooth_move(self.x(), target_x, self.y())
            # 同时更新当前屏
            self.screen_manager.notify_pet_screen(self._instance_config.pet_id, target.index)
            return

        self.switch_to_gif(direction)
        self.start_smooth_move(self.x(), target_x, self.y())

    def _on_stop_animation_requested(self):
        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()
        self.switch_to_static()
        self.state = PetState.MOTION_MODE

    def _open_motion_control_panel(self):
        panel = MotionControlPanel(self, self)
        panel.exec()

    def _current_screen_info(self) -> ScreenInfo | None:
        """返回宠物当前所在屏幕的 ScreenInfo"""
        return self.screen_manager.screen_for_widget(self)

    def _resolve_target_screen(self, screen_index, x: int | None, y: int | None) -> ScreenInfo | None:
        """根据调用方参数解析出真实的目标屏幕。

        - 显式 screen_index(非 None):用 screen_by_index,越界返回 None
        - 否则:按 (x, y) 自动选;x/y 都是 None 时回退当前屏
        """
        if screen_index is not None:
            info = self.screen_manager.screen_by_index(int(screen_index))
            return info
        if x is not None and y is not None:
            info = self.screen_manager.screen_at(x, y)
            if info is not None:
                return info
        return self._current_screen_info()

    def _do_cross_screen_move(self, x: int, y: int, target: ScreenInfo) -> None:
        """显式跨屏传送:瞬时切屏 + 落位 + 更新当前屏状态"""
        self.move(x, y)
        self.screen_manager.notify_pet_screen(self._instance_config.pet_id, target.index)
        self.switch_to_static(self.regular_pixmap)
        self.state = PetState.IDLE
        self.start_random_movement_timer()
        logger.debug(
            f"Cross-screen teleport to screen[{target.index}] at ({x}, {y})"
        )

    def _maybe_cross_screen_random(self, direction: int, target_x_in_current: int) -> tuple[int, int, ScreenInfo] | None:
        """随机行走时,如果触达当前屏边界,按概率决定是否跨到相邻屏。

        返回: (new_x, new_y, target_screen) 或 None(不跨屏)
        """
        display_cfg = self.display_config
        if not display_cfg.cross_screen_random_walk:
            return None
        if random.random() > display_cfg.cross_screen_walk_probability:
            return None

        current = self._current_screen_info()
        if current is None:
            return None
        g = current.available_geometry
        pet_width = self.width()
        pet_height = self.height()

        edge = "right" if direction > 0 else "left"
        # 边界裕量(像素)——只有触达边缘才考虑跨屏
        margin = 5
        if edge == "right" and target_x_in_current < g.x() + g.width() - pet_width - margin:
            return None
        if edge == "left" and target_x_in_current > g.x() + margin:
            return None

        dest = self.screen_manager.cross_screen_destination(current, edge)
        if dest is None:
            return None
        new_x = self.screen_manager.opposite_edge_x(dest, edge, pet_width)
        new_y = g.y() + g.height() - pet_height  # 保持当前 y 对齐到底部
        return (new_x, new_y, dest)

    # === 多屏幕事件回调 ===
    def _on_screens_topology_changed(self) -> None:
        """显示器拓扑变化(ScreenManager 已迁移过宠物位置)

        这里只做收尾:重新启动随机运动 + 通知监听器。
        """
        # 重启随机运动计时器(因为位置可能变了)
        try:
            self.start_random_movement_timer()
        except Exception as e:
            logger.debug(f"restart timer after hot-plug: {e}")

    def _on_current_screen_changed(self, pet_id: str, index: int) -> None:
        if pet_id != self._instance_config.pet_id:
            return
        try:
            idx = int(index)
            self._platform.persist_instance_screen(pet_id, idx)
            self._instance_config.screen_index = idx
            self._instance_config.position = {"x": int(self.x()), "y": int(self.y())}
        except Exception as exc:
            logger.debug("persist instance screen failed: %s", exc)

    @property
    def api(self):
        return self.motion_controller

    def eventFilter(self, obj, event):
        if obj == self.bubble_label and event.type() == event.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self.bubble_clicked(None)
                return True
        return super().eventFilter(obj, event)

    def start_inertia(self, velocity_x, velocity_y):
        self.inertia_velocity_x = velocity_x
        self.inertia_velocity_y = velocity_y

        if velocity_x < 0:
            self.switch_to_gif('left')
        else:
            self.switch_to_static()

        # Stop existing timer if running
        if hasattr(self, 'inertia_timer') and self.inertia_timer:
            self.inertia_timer.stop()

        self.inertia_timer = QTimer()
        self.inertia_timer.timeout.connect(self.apply_inertia)
        self.inertia_timer.start(16)

    def _safe_current_screen_info(self) -> ScreenInfo | None:
        """带回退的"当前屏":优先用宠物所在屏,失败时返回主屏。

        跨屏拖动期间鼠标可能落在两屏间隙或屏幕外几像素,
        此时 _current_screen_info() 会返回 None。需要一个总能拿到屏的版本,
        否则惯性 / 重力 / 落地逻辑会被卡住,宠物飘在空中。
        """
        info = self._current_screen_info()
        if info is not None:
            return info
        return self.screen_manager.primary_screen()

    def _snap_to_current_bottom(self) -> None:
        """把宠物强制贴到当前屏底部。失败时回退到主屏底部。

        用"自然尺寸"而不是当前 widget 尺寸算 pet_h,避免跨屏 DPI 缩放
        把 widget 撑大后,顶部 Y 算成屏中(底其实没贴错,但视觉飘空)。
        """
        info = self._safe_current_screen_info()
        if info is None:
            return
        g = info.available_geometry
        pet_w, pet_h = self._natural_pet_size
        min_x = g.x()
        max_x = g.x() + g.width() - pet_w
        cur_x = max(min_x, min(self.x(), max_x))
        new_y = g.y() + g.height() - pet_h
        if self.width() != pet_w or self.height() != pet_h:
            self._in_size_reset = True
            self.resize(pet_w, pet_h)
            self._in_size_reset = False
        self.move(cur_x, new_y)

    def _post_release_safety_check(self) -> None:
        """拖动释放后的兜底检查:确保宠物贴到当前屏底部。

        惯性 / 重力正常情况下会让宠物贴底;这一步是安全网,
        处理任何边界条件(例如屏幕拓扑变化、随机移动干扰等)导致的漂浮。
        """
        if getattr(self, 'is_dragging', False):
            return
        try:
            if self.motion_controller.get_mode() == "motion":
                return
        except Exception:
            pass

        pet_w, pet_h = self._natural_pet_size
        if self.width() != pet_w or self.height() != pet_h:
            self._in_size_reset = True
            self.resize(pet_w, pet_h)
            self._in_size_reset = False
        if pet_w <= 0 or pet_h <= 0:
            return

        cur = self._current_screen_info()
        primary = self.screen_manager.primary_screen()
        target = cur if cur is not None else primary
        if target is None:
            return

        g = target.available_geometry
        bottom_y = g.y() + g.height() - pet_h
        cur_y = self.y()
        if abs(cur_y - bottom_y) > 2:
            for attr in ('gravity_timer', 'inertia_timer', 'animation_timer'):
                t = getattr(self, attr, None)
                if t is not None:
                    try:
                        t.stop()
                    except Exception:
                        pass
            min_x = g.x()
            max_x = g.x() + g.width() - pet_w
            cur_x = max(min_x, min(self.x(), max_x))
            self.move(cur_x, bottom_y)
            self.switch_to_static(self.regular_pixmap)
            self.state = PetState.IDLE
            self.start_random_movement_timer()
            self._persist_position_if_platform()

    def apply_inertia(self):
        self.inertia_velocity_x *= 0.92
        self.inertia_velocity_y *= 0.92

        new_x = self.x() + int(self.inertia_velocity_x)
        new_y = self.y() + int(self.inertia_velocity_y)

        current = self._safe_current_screen_info()
        g = current.available_geometry if current is not None else None
        pet_width, pet_height = self._natural_pet_size

        bounds = self.screen_manager.virtual_bounds()
        new_x = max(bounds.x(), min(new_x, bounds.right() - pet_width))
        new_y = max(bounds.y(), min(new_y, bounds.bottom() - pet_height))

        self.move(new_x, new_y)

        new_info = self.screen_manager.screen_for_widget(self)
        if new_info is not None:
            cur_info = self._current_screen_info()
            if cur_info is None or new_info.index != cur_info.index:
                self.screen_manager.notify_pet_screen(self._instance_config.pet_id, new_info.index)

        post_screen = self._current_screen_info()
        post_g = self._safe_current_screen_info().available_geometry if post_screen is not None else (g if g is not None else None)

        if abs(self.inertia_velocity_x) < 0.5 and abs(self.inertia_velocity_y) < 0.5:
            self.inertia_timer.stop()
            if post_screen is None:
                primary = self.screen_manager.primary_screen()
                if primary is not None:
                    pg = primary.available_geometry
                    pet_w, pet_h = self._natural_pet_size
                    new_x = pg.x() + max(0, (pg.width() - pet_w) // 2)
                    new_y = pg.y() + pg.height() - pet_h
                    self.move(new_x, new_y)
                self.state = PetState.IDLE
                self.switch_to_static(self.regular_pixmap)
                self.start_random_movement_timer()
                self._persist_position_if_platform()
                return
            mid = post_g.y() + post_g.height() / 2
            if self.y() < mid:
                self.start_gravity_fall()
            else:
                self._snap_to_current_bottom()
                self.switch_to_static(self.regular_pixmap)
                self.state = PetState.IDLE
                self.start_random_movement_timer()
                self._persist_position_if_platform()
        elif post_screen is not None and new_y >= post_g.y() + post_g.height() - pet_height and self.inertia_velocity_y > 0:
            self.inertia_timer.stop()
            self._snap_to_current_bottom()
            self.switch_to_static(self.regular_pixmap)
            self.state = PetState.IDLE
            self.start_random_movement_timer()
            self._persist_position_if_platform()

    def start_gravity_fall(self):
        self.state = PetState.FALLING
        self.switch_to_static(self.flying_pixmap)

        if hasattr(self, 'gravity_timer') and self.gravity_timer:
            self.gravity_timer.stop()

        self.gravity_timer = QTimer()
        self.gravity_timer.timeout.connect(self.apply_gravity)
        self.current_fall_speed = 1
        self.gravity_timer.start(30)

    def apply_gravity(self):
        current = self._safe_current_screen_info()
        if current is None:
            if hasattr(self, 'gravity_timer') and self.gravity_timer:
                self.gravity_timer.stop()
            self.state = PetState.IDLE
            return
        g = current.available_geometry
        current_y = self.y()
        new_y = current_y + self.current_fall_speed

        _, pet_h = self._natural_pet_size
        bottom_y = g.y() + g.height() - pet_h

        if new_y >= bottom_y:
            self.move(self.x(), bottom_y)
            self.gravity_timer.stop()
            self.switch_to_static(self.regular_pixmap)
            self.state = PetState.IDLE
            self._persist_position_if_platform()
        else:
            self.current_fall_speed = min(self.current_fall_speed + 0.5, 10)
            self.move(self.x(), int(new_y))

    def random_move(self):
        if self.state != PetState.IDLE:
            return

        if self.motion_controller.get_mode() == "motion":
            return

        if not self.current_pet_package:
            logger.warning("No pet package loaded")
            return

        action = self.behavior_scheduler.choose_next_action(self.effective_actions)
        if not action:
            logger.warning("No available actions")
            return

        logger.debug(f"Random action: {action.name}")

        if action.type == "movement":
            self.execute_movement_action_from_pet(action)
        elif action.type == "animation":
            self.play_animation_action_from_pet(action)
        elif action.type == "chase":
            self.execute_chase_action(action)
        else:
            logger.warning(f"Unknown action type: {action.type}")

    def execute_movement_action_from_pet(self, action):
        if self.state == PetState.IDLE:
            current = self._current_screen_info()
            if current is None:
                return
            g = current.available_geometry

            direction = random.choice([-1, 1])
            logger.debug(f"Random movement direction: {direction}")

            min_dist = action.config.get("min_distance", 30)
            max_dist = action.config.get("max_distance", 100)
            move_distance = random.randint(min_dist, max_dist)

            current_x = self.x()
            new_x = current_x + (direction * move_distance)

            pet_width = self.width()
            min_x = g.x()
            max_x = g.x() + g.width() - pet_width
            new_x = max(min_x, min(new_x, max_x))

            y = g.y() + g.height() - self.height()

            cross = self._maybe_cross_screen_random(direction, new_x)
            if cross is not None:
                new_x, new_y_cross, dest = cross
                self._do_cross_screen_move(new_x, new_y_cross, dest)
                return

            if direction < 0:
                self.switch_to_gif('left')
            else:
                self.switch_to_gif('right')

            self.start_smooth_move(current_x, new_x, y)

    def execute_chase_action(self, action: ActionConfig):
        """追逐鼠标 action"""
        if self.state != PetState.IDLE:
            return

        config = action.config
        speed = config.get("speed", 3)
        stop_distance = config.get("stop_distance", 50)
        trigger_distance = config.get("trigger_distance", 300)

        # 获取鼠标位置
        mouse_pos = QCursor.pos()
        pet_x = self.x()
        pet_y = self.y()
        pet_width = self.width()
        pet_height = self.height()

        # 计算宠物中心点
        pet_center_x = pet_x + pet_width // 2
        pet_center_y = pet_y + pet_height // 2

        # 计算到鼠标的距离
        dx = mouse_pos.x() - pet_center_x
        dy = mouse_pos.y() - pet_center_y
        distance = (dx ** 2 + dy ** 2) ** 0.5

        # 检查是否在触发距离内
        if distance > trigger_distance:
            logger.debug(f"Mouse too far ({distance:.0f}px), skipping chase")
            return

        # 检查是否已到达停止距离
        if distance <= stop_distance:
            logger.debug(f"Reached target ({distance:.0f}px), stopping chase")
            return

        # 计算移动方向（归一化）
        move_x = (dx / distance) * speed if distance > 0 else 0
        move_y = (dy / distance) * speed if distance > 0 else 0

        # 获取屏幕边界(用当前屏幕)
        current = self._current_screen_info()
        if current is None:
            return
        g = current.available_geometry

        # 计算新位置
        new_x = pet_x + move_x
        new_y = pet_y + move_y

        # 边界检查
        new_x = max(g.x(), min(new_x, g.x() + g.width() - pet_width))
        new_y = max(g.y(), min(new_y, g.y() + g.height() - pet_height))

        # 切换到对应的行走动画方向
        if move_x > 0:
            self.switch_to_gif('right')
        else:
            self.switch_to_gif('left')

        # 执行移动
        self.move(int(new_x), int(new_y))

        logger.debug(f"Chasing mouse: distance={distance:.0f}px, moved to ({new_x}, {new_y})")

    def play_animation_action_from_pet(self, action):
        if self.state == PetState.REST_REMINDER:
            logger.debug("Skipping animation during rest reminder state")
            return

        self.movement_timer.stop()

        self._disconnect_current_gif_signals()

        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()

        logger.info(f"Playing animation: {action.name}")

        movie = self._load_pet_animation(action.name)
        if movie and movie.isValid():
            logger.debug(f"Showing animation GIF: {action.name}")
            self.label.setMovie(movie)

            self.current_animation_type = action.name
            self.current_action = action

            movie.finished.connect(self._on_animation_finished)
            movie.frameChanged.connect(self._check_gif_finished)

            self.previous_frame = -1
            self.gif_played_once = False

            movie.start()
            self.current_gif = movie
        else:
            logger.debug("Animation GIF not found, showing static image")
            self.switch_to_static()
            self.start_random_movement_timer()

    def start_smooth_move(self, start_x, end_x, y):
        # 不再强制 y = 屏幕底部 - 宠物高度;改由调用方传入合理 y
        # 仍然做一次合理范围钳制,避免动画跑到屏幕外
        bounds = self.screen_manager.virtual_bounds()
        pet_h = self.height()
        if bounds.height() > 0:
            y = max(bounds.y(), min(int(y), bounds.bottom() - pet_h))

        self.animation_start_x = start_x
        self.animation_end_x = end_x
        self.animation_current_y = y

        distance = abs(end_x - start_x)
        pixels_per_step = self.motion_controller.movement_speed

        if distance == 0:
            self.animation_total_steps = 1
        else:
            self.animation_total_steps = max(1, int(distance / pixels_per_step))

        self.animation_step = 0

        # Stop existing timer if running
        if hasattr(self, 'animation_timer') and self.animation_timer:
            self.animation_timer.stop()

        if not hasattr(self, 'animation_timer'):
            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self.animate_move)
        self.animation_timer.start(20)

    def animate_move(self):
        if self.animation_step < self.animation_total_steps:
            progress = self.animation_step / self.animation_total_steps
            eased_progress = 1 - (1 - progress) ** 2
            current_x = self.animation_start_x + (self.animation_end_x - self.animation_start_x) * eased_progress
            self.move(int(current_x), self.animation_current_y)
            self.animation_step += 1
            # 平滑移动时跨屏:更新当前屏
            new_info = self.screen_manager.screen_for_widget(self)
            cur = self._current_screen_info()
            if new_info is not None and (cur is None or new_info.index != cur.index):
                self.screen_manager.notify_pet_screen(self._instance_config.pet_id, new_info.index)
        else:
            self.animation_timer.stop()
            self.move(self.animation_end_x, self.animation_current_y)
            self.switch_to_static()
            self.state = PetState.IDLE
            self.start_random_movement_timer()
            # 最终位置确认当前屏
            final_info = self.screen_manager.screen_for_widget(self)
            if final_info is not None:
                self.screen_manager.notify_pet_screen(self._instance_config.pet_id, final_info.index)
