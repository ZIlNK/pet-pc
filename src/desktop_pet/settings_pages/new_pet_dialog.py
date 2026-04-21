"""New pet creation dialog."""

import json
import shutil
import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QMessageBox,
    QFormLayout, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

from ..utils import get_pets_path


class NewPetDialog(QDialog):
    """Dialog for creating a new pet package."""

    def __init__(self, config_manager, pet_loader, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.pet_loader = pet_loader
        self.selected_image_path = None

        self.setWindowTitle("新建桌宠")
        self.setMinimumSize(500, 450)
        self.setup_ui()

    def setup_ui(self):
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("新建桌宠")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        layout.addWidget(title)

        layout.addSpacing(10)

        # Form
        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        # Pet name
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("请输入桌宠名称")
        self.name_edit.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """)
        form_layout.addRow("桌宠名称 *", self.name_edit)

        # Author
        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText("（可选）")
        self.author_edit.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """)
        form_layout.addRow("作者", self.author_edit)

        layout.addLayout(form_layout)

        # Idle image selection
        image_group = QWidget()
        image_layout = QVBoxLayout(image_group)
        image_layout.setContentsMargins(0, 0, 0, 0)

        image_label = QLabel("待机形象 *")
        image_label.setStyleSheet("font-size: 13px; color: #333;")
        image_layout.addWidget(image_label)

        image_btn_layout = QHBoxLayout()
        self.image_path_label = QLabel("未选择文件")
        self.image_path_label.setStyleSheet("color: #666; font-size: 12px;")
        self.image_path_label.setWordWrap(True)

        select_btn = QPushButton("选择图片")
        select_btn.setStyleSheet("""
            QPushButton {
                background: white;
                color: #0078d4;
                border: 1px solid #0078d4;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #e3f2fd;
            }
        """)
        select_btn.clicked.connect(self.select_image)
        image_btn_layout.addWidget(self.image_path_label, 1)
        image_btn_layout.addWidget(select_btn)

        image_layout.addLayout(image_btn_layout)

        # Preview
        self.preview_label = QLabel("预览")
        self.preview_label.setFixedHeight(120)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background: #333; color: white; border-radius: 8px;")
        image_layout.addWidget(self.preview_label)

        layout.addWidget(image_group)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        create_btn = QPushButton("创建")
        create_btn.setDefault(True)
        create_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4;
                color: white;
                border: none;
                padding: 8px 24px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #106ebe;
            }
        """)
        create_btn.clicked.connect(self.create_pet)
        btn_layout.addWidget(create_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: white;
                color: #666;
                border: 1px solid #ddd;
                padding: 8px 24px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #f5f5f5;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def select_image(self):
        """Select idle image file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择待机形象",
            "",
            "图片文件 (*.png *.gif *.webp *.apng);;所有文件 (*.*)"
        )

        if file_path:
            self.selected_image_path = Path(file_path)
            self.image_path_label.setText(self.selected_image_path.name)

            # Show preview
            try:
                if self.selected_image_path.suffix.lower() in ['.gif']:
                    from PyQt6.QtGui import QMovie
                    movie = QMovie(str(self.selected_image_path))
                    movie.setScaledSize(150, 100)
                    self.preview_label.setMovie(movie)
                    movie.start()
                else:
                    pixmap = QPixmap(str(self.selected_image_path))
                    scaled = pixmap.scaled(
                        150, 100,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.preview_label.setPixmap(scaled)
                    self.preview_label.setText("")
            except Exception as e:
                logging.warning(f"Failed to load preview: {e}")

    def create_pet(self):
        """Create new pet package."""
        # Validate
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "验证失败", "请输入桌宠名称")
            return

        if not self.selected_image_path:
            QMessageBox.warning(self, "验证失败", "请选择待机形象")
            return

        # Validate name - remove invalid characters
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in invalid_chars:
            if char in name:
                QMessageBox.warning(self, "验证失败", "桌宠名称包含无效字符")
                return

        # Create pet directory
        pets_path = get_pets_path()
        pet_dir = pets_path / name

        if pet_dir.exists():
            QMessageBox.warning(self, "验证失败", f"桌宠 '{name}' 已存在")
            return

        try:
            # Create directories
            pet_dir.mkdir(parents=True)
            animations_dir = pet_dir / "animations"
            animations_dir.mkdir()
            config_dir = pet_dir / "config"
            config_dir.mkdir()

            # Copy image file
            image_filename = self.selected_image_path.name
            dst_image = animations_dir / image_filename
            shutil.copy2(self.selected_image_path, dst_image)

            # Create meta.json
            author = self.author_edit.text().strip() or "用户"
            meta = {
                "name": name,
                "author": author,
                "version": "1.0.0",
                "description": "",
                "preview": image_filename,
                "regular_image": image_filename,
                "flying_image": image_filename,
                "rest_animation": image_filename
            }
            with open(pet_dir / "meta.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            # Create actions.json
            actions = {
                "actions": [
                    {
                        "name": "idle",
                        "type": "animation",
                        "weight": 1,
                        "animation_files": [image_filename],
                        "enabled": True,
                        "config": {}
                    }
                ]
            }
            with open(config_dir / "actions.json", "w", encoding="utf-8") as f:
                json.dump(actions, f, ensure_ascii=False, indent=2)

            QMessageBox.information(self, "创建成功", f"桌宠 '{name}' 创建成功！\n请在列表中点击配置完善其他内容。")
            self.accept()

        except Exception as e:
            logging.error(f"Failed to create pet: {e}")
            QMessageBox.critical(self, "创建失败", f"创建桌宠时出错：{str(e)}")

            # Cleanup on failure
            if pet_dir.exists():
                shutil.rmtree(pet_dir, ignore_errors=True)
