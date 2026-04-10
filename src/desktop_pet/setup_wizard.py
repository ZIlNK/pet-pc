"""Initial setup wizard shown when no pet packages are found."""
import json
import logging
import re
import shutil
import zipfile
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QTabWidget,
    QWidget,
)

from .utils import get_pets_path

logger = logging.getLogger(__name__)


class SetupWizard(QDialog):
    """Initial setup wizard shown when no pet packages are found."""

    def __init__(self, pets_path: Path | None = None, parent=None):
        super().__init__(parent)
        self.pets_path = pets_path or get_pets_path()
        self.selected_dir: Path | None = None
        self._imported = False
        self._selected_image_path: Path | None = None
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("Desktop Pet - 初始配置")
        self.setFixedSize(450, 400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # 创建 Tab 控件
        tabs = QTabWidget(self)

        # Tab 1: 快速创建
        quick_create_widget = self._create_quick_create_tab()
        tabs.addTab(quick_create_widget, "快速创建")

        # Tab 2: 高级导入
        advanced_widget = self._create_advanced_tab()
        tabs.addTab(advanced_widget, "高级导入")

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(tabs)

        # 底部按钮
        btn_bottom = QHBoxLayout()
        btn_bottom.addStretch()

        btn_skip = QPushButton("跳过")
        btn_skip.clicked.connect(self.skip_setup)
        btn_bottom.addWidget(btn_skip)

        btn_exit = QPushButton("退出")
        btn_exit.clicked.connect(self.reject)
        btn_bottom.addWidget(btn_exit)

        main_layout.addLayout(btn_bottom)

    def _create_quick_create_tab(self) -> QWidget:
        """创建快速创建 Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        # 欢迎信息
        title = QLabel("<h3>上传图片快速创建桌宠</h3>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        description = QLabel("只需上传一张图片，即可创建您的专属桌宠")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setStyleSheet("color: gray;")
        layout.addWidget(description)

        # 表单布局
        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        # 宠物名称输入
        self.pet_name_input = QLineEdit()
        self.pet_name_input.setPlaceholderText("输入宠物名称，如：小可爱")
        self.pet_name_input.setMinimumWidth(250)
        form_layout.addRow("宠物名称:", self.pet_name_input)

        layout.addLayout(form_layout)

        # 图片选择区域
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)

        self.image_path_label = QLabel("未选择图片")
        self.image_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_path_label.setStyleSheet("border: 1px dashed #aaa; padding: 20px; color: gray;")
        image_layout.addWidget(self.image_path_label)

        btn_select_image = QPushButton("选择图片")
        btn_select_image.setMinimumHeight(40)
        btn_select_image.clicked.connect(self._select_image_for_quick_create)
        image_layout.addWidget(btn_select_image)

        layout.addWidget(image_container)

        # 创建按钮
        btn_create = QPushButton("创建桌宠")
        btn_create.setMinimumHeight(45)
        btn_create.setStyleSheet("font-weight: bold;")
        btn_create.clicked.connect(self._quick_create_pet)
        layout.addWidget(btn_create)

        layout.addStretch()

        return widget

    def _create_advanced_tab(self) -> QWidget:
        """创建高级导入 Tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)

        # 欢迎信息
        title = QLabel("<h3>高级导入</h3>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        info_label = QLabel("\n请选择以下方式之一来添加宠物资源：")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        # 按钮容器
        btn_container = QWidget()
        btn_layout = QVBoxLayout(btn_container)
        btn_layout.setSpacing(10)

        # 选项1: 选择宠物资源目录
        btn_select_dir = QPushButton("选择宠物资源目录")
        btn_select_dir.setToolTip("选择一个包含宠物资源包的目录")
        btn_select_dir.clicked.connect(self.select_pets_directory)
        btn_select_dir.setMinimumHeight(40)
        btn_layout.addWidget(btn_select_dir)

        # 选项2: 导入宠物资源包
        btn_import = QPushButton("导入宠物资源包 (ZIP)")
        btn_import.setToolTip("从ZIP文件导入宠物资源包")
        btn_import.clicked.connect(self.import_pet_package)
        btn_import.setMinimumHeight(40)
        btn_layout.addWidget(btn_import)

        # 选项3: 从项目复制默认宠物
        btn_copy_default = QPushButton("从项目复制默认宠物")
        btn_copy_default.setToolTip("从项目目录复制默认宠物资源 (开发模式)")
        btn_copy_default.clicked.connect(self.copy_default_pet_from_project)
        btn_copy_default.setMinimumHeight(40)
        btn_layout.addWidget(btn_copy_default)

        layout.addWidget(btn_container)

        # 说明
        info_frame = QWidget()
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(10, 10, 10, 10)

        structure_label = QLabel(
            "宠物资源包结构要求：\n"
            "pets/宠物名/meta.json\n"
            "pets/宠物名/animations/*.webp (或 .gif, .png)"
        )
        structure_label.setStyleSheet("color: gray; font-size: 11px;")
        info_layout.addWidget(structure_label)

        layout.addWidget(info_frame)

        return widget

    def _select_image_for_quick_create(self):
        """选择图片用于快速创建"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择宠物图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;所有文件 (*)",
        )

        if file_path:
            self._selected_image_path = Path(file_path)
            # 显示文件名
            self.image_path_label.setText(self._selected_image_path.name)
            self.image_path_label.setStyleSheet("border: 1px dashed #aaa; padding: 20px; color: #333;")

    def _quick_create_pet(self):
        """快速创建宠物素材包"""
        # 验证名称
        pet_name = self.pet_name_input.text().strip()
        if not pet_name:
            QMessageBox.warning(self, "输入错误", "请输入宠物名称")
            return

        # 验证图片
        if not hasattr(self, '_selected_image_path') or not self._selected_image_path:
            QMessageBox.warning(self, "选择错误", "请选择一张图片")
            return

        if not self._selected_image_path.exists():
            QMessageBox.warning(self, "文件错误", "选择的图片文件不存在")
            return

        try:
            # 生成唯一目录名
            unique_name = self._generate_unique_pet_name(pet_name)
            pet_dir = self.pets_path / unique_name
            animations_dir = pet_dir / "animations"
            config_dir = pet_dir / "config"

            # 创建目录结构
            self.pets_path.mkdir(parents=True, exist_ok=True)
            animations_dir.mkdir(parents=True, exist_ok=True)
            config_dir.mkdir(parents=True, exist_ok=True)

            # 处理图片并保存
            target_image = animations_dir / "idle.png.webp"
            if not self._process_user_image(self._selected_image_path, target_image):
                QMessageBox.critical(self, "处理失败", "图片处理失败，请重试")
                return

            # 生成 meta.json
            meta_content = {
                "name": pet_name,
                "author": "用户",
                "version": "1.0.0",
                "description": "使用图片快速创建",
                "preview": "idle.png.webp",
                "regular_image": "idle.png.webp",
                "flying_image": "idle.png.webp",
                "rest_animation": "idle.png.webp"
            }
            with open(pet_dir / "meta.json", "w", encoding="utf-8") as f:
                json.dump(meta_content, f, ensure_ascii=False, indent=2)

            # 生成 actions.json
            actions_content = {
                "actions": [
                    {
                        "name": "idle",
                        "type": "animation",
                        "weight": 0,
                        "animation_files": ["idle.png.webp"],
                        "enabled": True,
                        "config": {},
                        "zone_actions": {}
                    }
                ]
            }
            with open(config_dir / "actions.json", "w", encoding="utf-8") as f:
                json.dump(actions_content, f, ensure_ascii=False, indent=2)

            self._imported = True
            QMessageBox.information(
                self,
                "创建成功",
                f"成功创建宠物 '{pet_name}'！",
            )
            self.accept()

        except Exception as e:
            logger.error(f"Failed to create pet: {e}", exc_info=True)
            QMessageBox.critical(self, "创建失败", "创建宠物时发生错误，请重试。")

    def select_pets_directory(self):
        """Select an existing pets directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "选择宠物资源目录",
            str(self.pets_path.parent) if self.pets_path.parent.exists() else "",
        )

        if dir_path:
            selected_path = Path(dir_path)
            # Check if it's a valid pets directory
            if self._validate_pets_dir(selected_path):
                self._use_pets_directory(selected_path)
            else:
                # Check if it contains a pets subdirectory
                pets_subdir = selected_path / "pets"
                if pets_subdir.exists() and self._validate_pets_dir(pets_subdir):
                    self._use_pets_directory(pets_subdir)
                else:
                    QMessageBox.warning(
                        self,
                        "无效目录",
                        "所选目录不包含有效的宠物资源包。\n"
                        "请确保目录中包含宠物包（每个宠物包需要 meta.json 和 animations 目录）。",
                    )

    def _validate_pets_dir(self, path: Path) -> bool:
        """Check if a directory contains valid pet packages."""
        if not path.exists():
            return False

        for item in path.iterdir():
            if item.is_dir():
                meta_file = item / "meta.json"
                animations_dir = item / "animations"
                if meta_file.exists() and animations_dir.exists():
                    return True
        return False

    def _use_pets_directory(self, source_path: Path):
        """Use the selected pets directory by copying or linking."""
        try:
            # Ensure target directory exists
            self.pets_path.mkdir(parents=True, exist_ok=True)

            # Copy all pet packages from source to target
            copied_count = 0
            for item in source_path.iterdir():
                if item.is_dir():
                    target = self.pets_path / item.name
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(item, target)
                    copied_count += 1

            if copied_count > 0:
                self._imported = True
                QMessageBox.information(
                    self,
                    "导入成功",
                    f"成功导入 {copied_count} 个宠物资源包！",
                )
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "导入失败",
                    "未找到有效的宠物资源包。",
                )
        except Exception as e:
            logger.error(f"Failed to copy pets directory: {e}")
            QMessageBox.critical(
                self,
                "导入失败",
                f"复制宠物资源时发生错误：\n{e}",
            )

    def import_pet_package(self):
        """Import a pet package from a ZIP file or directory."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择宠物资源包",
            "",
            "ZIP 文件 (*.zip);;所有文件 (*)",
        )

        if file_path:
            self._import_from_zip(Path(file_path))

    def _import_from_zip(self, zip_path: Path):
        """Import a pet package from a ZIP file."""
        try:
            # Create temp extraction directory
            import tempfile
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Extract ZIP
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(temp_path)

                # Find pet packages in extracted content
                found_pets = self._find_pet_packages(temp_path)

                if not found_pets:
                    QMessageBox.warning(
                        self,
                        "无效资源包",
                        "ZIP 文件中未找到有效的宠物资源包。\n"
                        "请确保 ZIP 包含宠物目录（含 meta.json 和 animations 目录）。",
                    )
                    return

                # Ensure target directory exists
                self.pets_path.mkdir(parents=True, exist_ok=True)

                # Copy found pets
                copied_count = 0
                for pet_path in found_pets:
                    target = self.pets_path / pet_path.name
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(pet_path, target)
                    copied_count += 1

                self._imported = True
                QMessageBox.information(
                    self,
                    "导入成功",
                    f"成功导入 {copied_count} 个宠物资源包！",
                )
                self.accept()

        except zipfile.BadZipFile:
            QMessageBox.critical(
                self,
                "导入失败",
                "无效的 ZIP 文件。",
            )
        except Exception as e:
            logger.error(f"Failed to import pet package: {e}")
            QMessageBox.critical(
                self,
                "导入失败",
                f"导入宠物资源包时发生错误：\n{e}",
            )

    def _find_pet_packages(self, path: Path) -> list[Path]:
        """Find all valid pet packages in a directory."""
        pets = []

        # Check if path itself is a pet package
        if (path / "meta.json").exists() and (path / "animations").exists():
            return [path]

        # Look for pet packages in subdirectories
        for item in path.iterdir():
            if item.is_dir():
                if (item / "meta.json").exists() and (item / "animations").exists():
                    pets.append(item)
                else:
                    # Recursively search
                    pets.extend(self._find_pet_packages(item))

        return pets

    def copy_default_pet_from_project(self):
        """Copy default pet from project directory (for development)."""
        # Try to find the project's default pet
        project_root = Path(__file__).parent.parent.parent
        default_pet_source = project_root / "pets" / "default"

        if not default_pet_source.exists():
            QMessageBox.warning(
                self,
                "未找到默认宠物",
                "项目目录中未找到默认宠物资源包。\n"
                "请确保项目目录中存在 pets/default/ 目录。",
            )
            return

        try:
            # Ensure target directory exists
            self.pets_path.mkdir(parents=True, exist_ok=True)

            # Copy default pet
            target = self.pets_path / "default"
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(default_pet_source, target)

            self._imported = True
            QMessageBox.information(
                self,
                "复制成功",
                "成功复制默认宠物资源包！",
            )
            self.accept()

        except Exception as e:
            logger.error(f"Failed to copy default pet: {e}")
            QMessageBox.critical(
                self,
                "复制失败",
                f"复制默认宠物时发生错误：\n{e}",
            )

    def skip_setup(self):
        """Skip setup and continue with empty pets."""
        reply = QMessageBox.question(
            self,
            "跳过配置",
            "跳过配置将无法显示宠物。\n确定要跳过吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Create empty pets directory
            self.pets_path.mkdir(parents=True, exist_ok=True)
            self.accept()

    def _process_user_image(self, source_path: Path, target_path: Path) -> bool:
        """处理用户上传的图片：缩放并转换为 WebP"""
        try:
            with Image.open(source_path) as img:
                # 检查是否为有效图片
                if img.mode not in ('RGBA', 'RGB', 'P'):
                    img = img.convert('RGBA')

                # 自动缩放（保持宽高比，最大宽度 300px）
                max_width = 300
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

                # 创建目标目录
                target_path.parent.mkdir(parents=True, exist_ok=True)

                # 转换为 WebP 格式并保存
                img.save(target_path, "WEBP", quality=95)
            return True

        except Exception as e:
            logger.error(f"Failed to process image: {e}")
            return False

    def _generate_unique_pet_name(self, base_name: str) -> str:
        """生成唯一的宠物目录名，避免冲突"""
        # 清理名称：只保留字母、数字、下划线
        clean_name = re.sub(r'[^\w]', '_', base_name)
        if not clean_name:
            clean_name = "my_pet"

        pets_path = self.pets_path
        final_name = clean_name

        # 检查是否已存在，逐次增加数字后缀
        counter = 1
        while (pets_path / final_name).exists():
            final_name = f"{clean_name}_{counter}"
            counter += 1

        return final_name

    @property
    def imported(self) -> bool:
        """Return True if pets were successfully imported."""
        return self._imported