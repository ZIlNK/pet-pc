"""Settings Center - Unified settings GUI for Desktop Pet."""

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QStackedWidget, QPushButton, QLabel
)
from PyQt6.QtCore import Qt

from .settings_pages import PetListPage, PetConfigPage, GlobalSettingsPage, ActionControlPage

logger = logging.getLogger(__name__)


NAV_BUTTON_STYLE = """
    QPushButton {
        text-align: left;
        padding: 11px 14px;
        border: none;
        background: transparent;
        font-size: 14px;
        color: #d9e1df;
        border-radius: 8px;
        font-weight: 500;
    }
    QPushButton:checked {
        background: #f2c572;
        color: #17201d;
        font-weight: 700;
    }
    QPushButton:hover:!checked {
        background: rgba(255,255,255,0.08);
        color: #ffffff;
    }
    QPushButton:disabled {
        color: rgba(217,225,223,0.35);
    }
"""


class SettingsCenter(QDialog):
    """Main settings center dialog with navigation."""

    def __init__(self, config_manager, pet_loader, pet=None, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.pet_loader = pet_loader
        self.pet = pet
        self.current_pet_package = None
        self.pet_config_page = None

        self.setWindowTitle("桌面宠物设置")
        self.setMinimumSize(980, 720)
        self.setStyleSheet("""
            QDialog {
                background: #f5f7f4;
                color: #24312d;
            }
            QStackedWidget {
                background: #f5f7f4;
            }
        """)
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        """Setup the main UI layout."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left navigation panel
        self.left_nav = self._create_left_nav()
        main_layout.addWidget(self.left_nav, 0)

        # Right content area
        self.content_stack = QStackedWidget()

        # Pet list page
        self.pet_list_page = PetListPage(
            self.config_manager,
            self.pet_loader,
            self
        )
        self.content_stack.addWidget(self.pet_list_page)

        # Global settings page
        self.global_settings_page = GlobalSettingsPage(
            self.config_manager,
            self.pet,
            self
        )
        self.content_stack.addWidget(self.global_settings_page)

        # Action control page
        if self.pet:
            self.action_control_page = ActionControlPage(self.pet, self)
            self.content_stack.addWidget(self.action_control_page)
            self.action_nav_btn.setEnabled(True)

        # Pet config page will be added when needed

        main_layout.addWidget(self.content_stack, 1)

    def _create_left_nav(self) -> QWidget:
        """Create left navigation panel."""
        nav_widget = QWidget()
        nav_widget.setFixedWidth(190)
        nav_widget.setStyleSheet("""
            QWidget {
                background: #17201d;
                border-right: 1px solid #dfe6e1;
            }
        """)
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(16, 24, 16, 18)
        nav_layout.setSpacing(8)

        # Title
        title = QLabel("桌面宠物")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #ffffff;")
        nav_layout.addWidget(title)
        subtitle = QLabel("设置中心")
        subtitle.setStyleSheet("font-size: 12px; color: #9fb0aa;")
        nav_layout.addWidget(subtitle)
        nav_layout.addSpacing(22)

        # Pet nav button
        self.pet_nav_btn = QPushButton("宠物库")
        self.pet_nav_btn.setCheckable(True)
        self.pet_nav_btn.setChecked(True)
        self.pet_nav_btn.setStyleSheet(NAV_BUTTON_STYLE)
        nav_layout.addWidget(self.pet_nav_btn)

        # Global settings nav button
        self.global_nav_btn = QPushButton("全局设置")
        self.global_nav_btn.setCheckable(True)
        self.global_nav_btn.setStyleSheet(NAV_BUTTON_STYLE)
        nav_layout.addWidget(self.global_nav_btn)

        # Action control nav button
        self.action_nav_btn = QPushButton("动作控制")
        self.action_nav_btn.setCheckable(True)
        self.action_nav_btn.setStyleSheet(NAV_BUTTON_STYLE)
        self.action_nav_btn.setEnabled(False)  # Disabled until pet is set
        nav_layout.addWidget(self.action_nav_btn)

        nav_layout.addStretch()

        return nav_widget

    def connect_signals(self):
        """Connect navigation signals."""
        self.pet_nav_btn.clicked.connect(self.show_pet_page)
        self.global_nav_btn.clicked.connect(self.show_global_settings_page)
        self.action_nav_btn.clicked.connect(self.show_action_control_page)

        # Connect pet list page signals
        self.pet_list_page.pet_selected.connect(self.on_pet_selected)
        self.pet_list_page.new_pet_requested.connect(self.on_new_pet_requested)
        self.pet_list_page.import_requested.connect(self.on_import_requested)

    def show_pet_page(self):
        """Show pet list page."""
        self.pet_nav_btn.setChecked(True)
        self.global_nav_btn.setChecked(False)
        self.action_nav_btn.setChecked(False)
        self.content_stack.setCurrentWidget(self.pet_list_page)

    def show_global_settings_page(self):
        """Show global settings page."""
        self.global_nav_btn.setChecked(True)
        self.pet_nav_btn.setChecked(False)
        self.action_nav_btn.setChecked(False)
        self.content_stack.setCurrentWidget(self.global_settings_page)

    def show_action_control_page(self):
        """Show action control page."""
        if not self.pet:
            return
        self.action_nav_btn.setChecked(True)
        self.pet_nav_btn.setChecked(False)
        self.global_nav_btn.setChecked(False)
        self.content_stack.setCurrentWidget(self.action_control_page)
        self.action_control_page.refresh_all()

    def on_pet_selected(self, pet_package):
        """Handle pet selection - enter config mode."""
        self.current_pet_package = pet_package

        # Check if pet config page exists, if not create it
        if self.pet_config_page is None:
            self.pet_config_page = PetConfigPage(
                self.config_manager,
                self.pet_loader,
                pet_package,
                self
            )
            self.pet_config_page.back_to_list.connect(self.on_back_to_list)
            self.content_stack.addWidget(self.pet_config_page)
        else:
            self.pet_config_page.set_pet_package(pet_package)

        self.pet_nav_btn.setChecked(True)
        self.global_nav_btn.setChecked(False)
        self.content_stack.setCurrentWidget(self.pet_config_page)

    def on_new_pet_requested(self):
        """Handle new pet creation request."""
        from .settings_pages import NewPetDialog
        dialog = NewPetDialog(self.config_manager, self.pet_loader, self)
        if dialog.exec() == dialog.Accepted:
            # Refresh pet list
            self.pet_list_page.refresh_pets()

    def on_import_requested(self):
        """Handle import pet package request."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        import zipfile
        import tempfile
        import shutil

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入桌宠资源包",
            "",
            "ZIP 文件 (*.zip)"
        )

        if not file_path:
            return

        try:
            from .utils import get_pets_path
            pets_path = get_pets_path()

            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract zip
                with zipfile.ZipFile(file_path, 'r') as zf:
                    zf.extractall(temp_dir)

                temp_path = Path(temp_dir)

                # Validate structure
                meta_files = list(temp_path.glob("*/meta.json"))
                if not meta_files:
                    QMessageBox.warning(self, "导入失败", "资源包缺少 meta.json 文件")
                    return

                pet_dir = meta_files[0].parent
                animations_dir = pet_dir / "animations"

                if not animations_dir.exists():
                    QMessageBox.warning(self, "导入失败", "资源包缺少 animations 目录")
                    return

                # Read meta.json to get pet name
                import json
                with open(pet_dir / "meta.json", "r", encoding="utf-8") as f:
                    meta = json.load(f)

                pet_name = meta.get("name", pet_dir.name)
                dest_dir = pets_path / pet_name

                if dest_dir.exists():
                    reply = QMessageBox.question(
                        self, "确认覆盖",
                        f"桌宠 '{pet_name}' 已存在，是否覆盖？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.No:
                        return
                    shutil.rmtree(dest_dir)

                # Copy to pets directory
                shutil.copytree(pet_dir, dest_dir)

                self.pet_list_page.refresh_pets()
                QMessageBox.information(self, "导入成功", f"桌宠 '{pet_name}' 导入成功！")

        except Exception as e:
            logger.error(f"Failed to import pet: {e}")
            QMessageBox.critical(self, "导入失败", f"导入时出错：{str(e)}")

    def on_back_to_list(self):
        """Handle back to pet list."""
        self.pet_list_page.refresh_pets()
        self.show_pet_page()
