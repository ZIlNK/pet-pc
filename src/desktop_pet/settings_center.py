"""Platform-owned settings center for desktop pet instances."""

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QStackedWidget, QPushButton, QLabel
)
from PyQt6.QtCore import Qt

from .settings_pages import (
    PetListPage, PetConfigPage, GlobalSettingsPage,
    ActionControlPage, InstanceManagerPage,
)
from .ui_style import (
    NAV_BUTTON_STYLE, BG, TEXT, DARK, BORDER, TEXT_ON_DARK_DIM,
)

logger = logging.getLogger(__name__)


class SettingsCenter(QDialog):
    """Main settings center dialog with navigation."""

    def __init__(self, platform, parent=None):
        """Create the settings center for a PetPlatform."""
        if platform is None or not hasattr(platform, "list_instances"):
            raise TypeError("SettingsCenter requires a PetPlatform")
        super().__init__(parent)
        self.platform = platform
        self.config_manager = platform.global_config
        self.pet_loader = platform.pet_loader
        self.current_pet_id = None
        self.pet_config_page = None
        self.action_control_page = None

        self.setWindowTitle("桌面宠物设置")
        self.setMinimumSize(980, 720)
        self.setStyleSheet(f"""
            QDialog {{
                background: {BG};
                color: {TEXT};
            }}
            QStackedWidget {{
                background: {BG};
            }}
        """)
        self.setup_ui()
        self.connect_signals()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
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

        self.instance_manager_page = InstanceManagerPage(self.platform, self)
        self.content_stack.addWidget(self.instance_manager_page)

        # Pet list page
        self.pet_list_page = PetListPage(
            self.config_manager,
            self.pet_loader,
            platform=self.platform,
            parent=self,
        )
        self.content_stack.addWidget(self.pet_list_page)

        # Global settings page
        self.global_settings_page = GlobalSettingsPage(self.platform, self)
        self.content_stack.addWidget(self.global_settings_page)

        # Pet config page will be added when needed

        main_layout.addWidget(self.content_stack, 1)

    def _create_left_nav(self) -> QWidget:
        """Create left navigation panel."""
        nav_widget = QWidget()
        nav_widget.setFixedWidth(190)
        nav_widget.setStyleSheet(f"""
            QWidget {{
                background: {DARK};
                border-right: 1px solid {BORDER};
            }}
        """)
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(16, 24, 16, 18)
        nav_layout.setSpacing(8)

        # Title
        title = QLabel("桌面宠物")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #ffffff;")
        nav_layout.addWidget(title)
        subtitle = QLabel("设置中心")
        subtitle.setStyleSheet(f"font-size: 12px; color: {TEXT_ON_DARK_DIM};")
        nav_layout.addWidget(subtitle)
        nav_layout.addSpacing(22)

        self.instance_nav_btn = QPushButton("实例管理")
        self.instance_nav_btn.setCheckable(True)
        self.instance_nav_btn.setChecked(True)
        self.instance_nav_btn.setStyleSheet(NAV_BUTTON_STYLE)
        nav_layout.addWidget(self.instance_nav_btn)

        # Pet nav button
        self.pet_nav_btn = QPushButton("宠物库")
        self.pet_nav_btn.setCheckable(True)
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
        # 选择实例后启用
        self.action_nav_btn.setEnabled(False)
        nav_layout.addWidget(self.action_nav_btn)

        nav_layout.addStretch()

        return nav_widget

    def connect_signals(self):
        """Connect navigation signals."""
        self.instance_nav_btn.clicked.connect(self.show_instance_manager_page)
        self.pet_nav_btn.clicked.connect(self.show_pet_page)
        self.global_nav_btn.clicked.connect(self.show_global_settings_page)
        self.action_nav_btn.clicked.connect(self.show_action_control_page)

        # Connect pet list page signals
        self.pet_list_page.pet_selected.connect(self.on_pet_selected)
        self.pet_list_page.new_pet_requested.connect(self.on_new_pet_requested)
        self.pet_list_page.import_requested.connect(self.on_import_requested)
        self.pet_list_page.instance_created.connect(self._on_instance_created_from_list)

        # 实例管理页信号
        self.instance_manager_page.instance_selected.connect(self._on_instance_selected)
        self.instance_manager_page.create_instance_requested.connect(self._on_create_instance_requested)
        self.instance_manager_page.instance_closed.connect(self._on_instance_closed)
        self.instance_manager_page.instance_created.connect(self._on_instance_created_from_list)

    # ------------------------------------------------------------------
    # 页面切换
    # ------------------------------------------------------------------
    def _reset_nav_buttons(self):
        """重置所有导航按钮的选中状态。"""
        self.instance_nav_btn.setChecked(False)
        self.pet_nav_btn.setChecked(False)
        self.global_nav_btn.setChecked(False)
        self.action_nav_btn.setChecked(False)

    def show_instance_manager_page(self):
        """显示实例管理页。"""
        self._reset_nav_buttons()
        self.instance_nav_btn.setChecked(True)
        self.instance_manager_page.refresh_instances()
        self.content_stack.setCurrentWidget(self.instance_manager_page)

    def show_pet_page(self):
        """Show pet list page."""
        self._reset_nav_buttons()
        self.pet_nav_btn.setChecked(True)
        self.pet_list_page.refresh_pets()
        self.content_stack.setCurrentWidget(self.pet_list_page)

    def show_global_settings_page(self):
        """Show global settings page."""
        self._reset_nav_buttons()
        self.global_nav_btn.setChecked(True)
        self.content_stack.setCurrentWidget(self.global_settings_page)

    def show_action_control_page(self):
        """Show action control page."""
        if self.action_control_page is None:
            return
        self._reset_nav_buttons()
        self.action_nav_btn.setChecked(True)
        self.content_stack.setCurrentWidget(self.action_control_page)

    def on_pet_selected(self, pet_package):
        """Package cards are informational; instance creation uses their button."""
        return

    def on_new_pet_requested(self):
        """Handle new pet creation request."""
        from .settings_pages import NewPetDialog
        dialog = NewPetDialog(self.config_manager, self.pet_loader, self)
        if dialog.exec() == dialog.Accepted:
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
                with zipfile.ZipFile(file_path, 'r') as zf:
                    zf.extractall(temp_dir)

                temp_path = Path(temp_dir)
                meta_files = list(temp_path.glob("*/meta.json"))
                if not meta_files:
                    QMessageBox.warning(self, "导入失败", "资源包缺少 meta.json 文件")
                    return

                pet_dir = meta_files[0].parent
                animations_dir = pet_dir / "animations"

                if not animations_dir.exists():
                    QMessageBox.warning(self, "导入失败", "资源包缺少 animations 目录")
                    return

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

                shutil.copytree(pet_dir, dest_dir)

                try:
                    pkg = self.platform.pet_loader.load_pet(pet_name)
                    if pkg is not None:
                        self.platform.pet_packages[pkg.name] = pkg
                except Exception as e:
                    logger.warning(f"Failed to refresh platform packages: {e}")

                self.pet_list_page.refresh_pets()
                QMessageBox.information(self, "导入成功", f"桌宠 '{pet_name}' 导入成功！")

        except Exception as e:
            logger.error(f"Failed to import pet: {e}")
            QMessageBox.critical(self, "导入失败", f"导入时出错：{str(e)}")

    def on_back_to_list(self):
        """Handle back to pet list."""
        self.pet_list_page.refresh_pets()
        self.show_pet_page()

    # ------------------------------------------------------------------
    # 新模式：实例选择与编辑
    # ------------------------------------------------------------------
    def _on_instance_selected(self, pet_id: str):
        """实例管理页选中实例：构建/复用配置页与动作控制页。"""
        self.current_pet_id = pet_id
        instance_config = self.platform.get_instance_config(pet_id)
        if instance_config is None:
            logger.warning(f"Instance {pet_id} not found")
            return

        # 创建或更新 PetConfigPage
        if self.pet_config_page is None:
            self.pet_config_page = PetConfigPage(
                instance_config=instance_config,
                platform=self.platform,
                parent=self,
            )
            self.pet_config_page.back_to_list.connect(self._on_back_to_instance_list)
            self.content_stack.addWidget(self.pet_config_page)
        else:
            self.pet_config_page.set_instance(instance_config)

        # 创建或更新 ActionControlPage
        if self.action_control_page is None:
            self.action_control_page = ActionControlPage(
                instance_config=instance_config,
                platform=self.platform,
                parent=self,
            )
            self.content_stack.addWidget(self.action_control_page)
        else:
            self.action_control_page.set_instance(instance_config)

        self.action_nav_btn.setEnabled(True)

        # 默认跳转到配置页
        self._reset_nav_buttons()
        self.pet_nav_btn.setChecked(True)
        self.content_stack.setCurrentWidget(self.pet_config_page)

    def _on_back_to_instance_list(self):
        """从实例配置页返回实例管理列表。"""
        if self.instance_manager_page is not None:
            self.instance_manager_page.refresh_instances()
            self.show_instance_manager_page()
        else:
            self.show_pet_page()

    def _on_create_instance_requested(self):
        """实例管理页请求创建新实例：跳转到宠物库选择资源包。"""
        self.show_pet_page()

    def _on_instance_created_from_list(self, pet_id: str):
        """宠物库或实例管理页创建实例成功后刷新。"""
        if self.instance_manager_page is not None:
            self.instance_manager_page.refresh_instances()
        # 默认选中刚创建的实例
        self._on_instance_selected(pet_id)

    def _on_instance_closed(self, pet_id: str):
        """实例被关闭后清理状态。"""
        if self.current_pet_id == pet_id:
            self.current_pet_id = None
            # 关闭后回到实例管理页
            self.show_instance_manager_page()
