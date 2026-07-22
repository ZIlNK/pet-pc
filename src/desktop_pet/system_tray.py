"""Platform-owned system tray for desktop pet instances."""
import logging

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter
from PyQt6.QtCore import Qt, pyqtSignal

from .ui_style import MENU_STYLE
from .utils import get_pets_path

logger = logging.getLogger(__name__)


def create_default_icon() -> QIcon:
    """Create a simple default icon for the system tray.

    Creates a circular icon with a pet-like appearance.
    """
    # Try to use pet image first
    pets_path = get_pets_path()
    idle_image = pets_path / "default" / "animations" / "idle.png"

    if idle_image.exists():
        try:
            pixmap = QPixmap(str(idle_image))
            if not pixmap.isNull():
                # Scale to tray icon size
                icon = QIcon(pixmap.scaled(
                    64, 64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
                return icon
        except Exception as e:
            logger.warning(f"Failed to load pet image for tray icon: {e}")

    # Create a simple default icon
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Draw a cute circular icon
    # Main circle (pet body)
    painter.setBrush(Qt.GlobalColor.white)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(8, 8, 48, 48)

    # Face features
    painter.setBrush(Qt.GlobalColor.black)
    # Eyes
    painter.drawEllipse(18, 20, 8, 8)
    painter.drawEllipse(38, 20, 8, 8)
    # Nose
    painter.drawEllipse(28, 32, 8, 6)

    # Smile
    painter.setPen(Qt.PenStyle.SolidLine)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(20, 36, 24, 16, 0, -180 * 16)

    painter.end()

    return QIcon(pixmap)


class SystemTrayIcon(QSystemTrayIcon):
    """Platform-owned system tray icon for the desktop pet application."""

    settings_requested = pyqtSignal()
    create_instance_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self, platform, parent=None):
        if platform is None or not hasattr(platform, "list_instances"):
            raise TypeError("SystemTrayIcon requires a PetPlatform")
        super().__init__(create_default_icon(), parent)
        self._platform = platform
        self.config_manager = platform.global_config
        self.setToolTip("桌面宠物")
        self._create_menu()
        self.activated.connect(self._on_activated)
        self.show()
        logger.info("System tray icon initialized")

    def _create_menu(self):
        self.menu = QMenu()
        self.menu.setStyleSheet(MENU_STYLE)
        primary = self._platform.get_primary_instance()
        primary_id = primary.pet_id if primary is not None else None

        for config in self._platform.list_instances():
            prefix = "★ " if config.pet_id == primary_id else ""
            submenu = QMenu(f"{prefix}{config.package}-{config.pet_id[:4]}", self.menu)

            show_action = QAction("显示", submenu)
            show_action.triggered.connect(
                lambda checked=False, pid=config.pet_id: self._show_instance(pid)
            )
            submenu.addAction(show_action)

            hide_action = QAction("隐藏", submenu)
            hide_action.triggered.connect(
                lambda checked=False, pid=config.pet_id: self._hide_instance(pid)
            )
            submenu.addAction(hide_action)

            close_action = QAction("关闭此桌宠", submenu)
            close_action.triggered.connect(
                lambda checked=False, pid=config.pet_id: self._close_instance(pid)
            )
            submenu.addAction(close_action)
            self.menu.addMenu(submenu)

        self.menu.addSeparator()

        create_action = QAction("创建新实例", self.menu)
        create_action.triggered.connect(self.create_instance_requested.emit)
        self.menu.addAction(create_action)

        settings_action = QAction("设置中心", self.menu)
        settings_action.triggered.connect(self.settings_requested.emit)
        self.menu.addAction(settings_action)

        api_server = self._platform.api_server
        if api_server is not None:
            self.api_toggle_action = QAction("API 服务器", self.menu)
            self.api_toggle_action.setCheckable(True)
            self.api_toggle_action.setChecked(api_server.is_running)
            self.api_toggle_action.triggered.connect(self._on_toggle_api_server)
            self.menu.addAction(self.api_toggle_action)

        self.menu.addSeparator()
        exit_action = QAction("退出", self.menu)
        exit_action.triggered.connect(self._on_exit_platform)
        self.menu.addAction(exit_action)
        self.setContextMenu(self.menu)

    def refresh_menu(self):
        if hasattr(self, "menu") and self.menu is not None:
            self.menu.clear()
        self._create_menu()

    def _show_instance(self, pet_id: str):
        widget = self._platform.get_pet_widget(pet_id)
        if widget is not None:
            widget.show()
            widget.raise_()

    def _hide_instance(self, pet_id: str):
        widget = self._platform.get_pet_widget(pet_id)
        if widget is not None:
            widget.hide()

    def _close_instance(self, pet_id: str):
        try:
            self._platform.destroy_instance(pet_id)
        except Exception as error:
            logger.exception("Failed to remove pet instance %s", pet_id)
            self.showMessage(
                "删除失败",
                str(error),
                QSystemTrayIcon.MessageIcon.Critical,
                4000,
            )
            return
        self.refresh_menu()

    def _on_exit_platform(self):
        logger.info("Exit requested from tray menu")
        self.exit_requested.emit()

    def _on_toggle_api_server(self, checked: bool):
        api_server = self._platform.api_server
        if api_server is None:
            self._set_api_action_checked(False)
            return

        success = (
            api_server.start_background()
            if checked
            else api_server.stop_background()
        )
        actual_running = api_server.is_running
        self._set_api_action_checked(actual_running)
        if not success or actual_running != checked:
            error = api_server.last_error or "API 服务器状态切换失败"
            logger.error("Failed to change API server state: %s", error)
            self.showMessage(
                "API 服务失败",
                error,
                QSystemTrayIcon.MessageIcon.Critical,
                4000,
            )

    def _set_api_action_checked(self, checked: bool):
        action = getattr(self, "api_toggle_action", None)
        if action is None:
            return
        blocked = action.blockSignals(True)
        action.setChecked(checked)
        action.blockSignals(blocked)

    def _on_activated(self, reason):
        if reason != QSystemTrayIcon.ActivationReason.DoubleClick:
            return
        primary = self._platform.get_primary_instance()
        if primary is not None:
            self._show_instance(primary.pet_id)
