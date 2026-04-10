"""System tray icon for Desktop Pet.

Provides a system tray icon with menu for controlling the pet application.
"""
import logging
from pathlib import Path

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter
from PyQt6.QtCore import Qt, QSize

from .startup_manager import is_startup_enabled, set_startup_enabled
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
    """System tray icon for Desktop Pet application."""

    def __init__(self, pet_widget, config_manager):
        """Initialize the system tray icon.

        Args:
            pet_widget: The DesktopPet widget instance.
            config_manager: The ConfigManager instance.
        """
        super().__init__(create_default_icon(), pet_widget)

        self.pet = pet_widget
        self.config_manager = config_manager
        self._is_visible = True

        self.setToolTip("桌面宠物")

        self._create_menu()
        self._connect_signals()

        # Show the tray icon
        self.show()

        logger.info("System tray icon initialized")

    def _create_menu(self):
        """Create the tray menu."""
        self.menu = QMenu()

        # Show/Hide action
        self.show_hide_action = QAction("显示/隐藏", self.menu)
        self.show_hide_action.triggered.connect(self.toggle_pet_visibility)
        self.menu.addAction(self.show_hide_action)

        self.menu.addSeparator()

        # Mode switching
        mode_menu = QMenu("运动模式", self.menu)

        self.random_mode_action = QAction("随机模式", mode_menu)
        self.random_mode_action.triggered.connect(self._switch_to_random_mode)
        mode_menu.addAction(self.random_mode_action)

        self.motion_mode_action = QAction("运动模式", mode_menu)
        self.motion_mode_action.triggered.connect(self._switch_to_motion_mode)
        mode_menu.addAction(self.motion_mode_action)

        self.menu.addMenu(mode_menu)

        self.menu.addSeparator()

        # Action manager
        self.action_manager_action = QAction("动作管理", self.menu)
        self.action_manager_action.triggered.connect(self._open_action_manager)
        self.menu.addAction(self.action_manager_action)

        self.menu.addSeparator()

        # Startup option
        self.startup_action = QAction("开机自启动", self.menu)
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(is_startup_enabled())
        self.startup_action.triggered.connect(self._toggle_startup)
        self.menu.addAction(self.startup_action)

        self.menu.addSeparator()

        # Exit action
        self.exit_action = QAction("退出", self.menu)
        self.exit_action.triggered.connect(self._quit_app)
        self.menu.addAction(self.exit_action)

        self.setContextMenu(self.menu)

    def _connect_signals(self):
        """Connect internal signals."""
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        """Handle tray icon activation.

        Args:
            reason: The activation reason (click, double-click, etc.)
        """
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.toggle_pet_visibility()

    def toggle_pet_visibility(self):
        """Toggle the pet widget visibility."""
        if self._is_visible:
            self.pet.hide()
            self._is_visible = False
            self.show_hide_action.setText("显示桌宠")
        else:
            self.pet.show()
            self._is_visible = True
            self.show_hide_action.setText("隐藏桌宠")

    def set_pet_visible(self, visible: bool):
        """Set the pet widget visibility.

        Args:
            visible: True to show, False to hide.
        """
        if visible:
            self.pet.show()
            self._is_visible = True
            self.show_hide_action.setText("隐藏桌宠")
        else:
            self.pet.hide()
            self._is_visible = False
            self.show_hide_action.setText("显示桌宠")

    def _switch_to_random_mode(self):
        """Switch to random movement mode."""
        self.pet.motion_controller.set_mode("random")

    def _switch_to_motion_mode(self):
        """Switch to motion control mode."""
        self.pet.motion_controller.set_mode("motion")

    def _open_action_manager(self):
        """Open the action manager dialog."""
        self.pet.open_action_manager()

    def _toggle_startup(self, checked: bool):
        """Toggle Windows startup setting.

        Args:
            checked: True to enable startup, False to disable.
        """
        success = set_startup_enabled(checked)
        if success:
            # Update config
            self.config_manager._startup.enabled = checked
            self.startup_action.setChecked(checked)
            logger.info(f"Startup setting changed to: {checked}")
        else:
            # Revert the checkbox if failed
            self.startup_action.setChecked(is_startup_enabled())
            self.showMessage(
                "设置失败",
                "无法修改开机自启动设置",
                QSystemTrayIcon.MessageIcon.Warning,
                2000
            )

    def _quit_app(self):
        """Quit the application."""
        logger.info("Exiting application from tray menu")
        # Stop timers and cleanup
        if hasattr(self.pet, 'movement_timer'):
            self.pet.movement_timer.stop()
        if hasattr(self.pet, 'rest_timer'):
            self.pet.rest_timer.stop()

        # Hide tray icon before quitting
        self.hide()

        QApplication.quit()

    def update_startup_status(self):
        """Update the startup checkbox status from registry."""
        self.startup_action.setChecked(is_startup_enabled())