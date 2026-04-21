"""Pet configuration page."""

import json
import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QGroupBox, QFormLayout,
    QLineEdit, QSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QAbstractItemView, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap

from ..pet_loader import PetPackage, PetAction
from ..action_manager_gui import AnimationSelectDialog, ActionEditDialog


class PetConfigPage(QWidget):
    """Page for configuring a single pet's properties."""

    back_to_list = pyqtSignal()

    def __init__(self, config_manager, pet_loader, pet_package, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.pet_loader = pet_loader
        self.pet_package = pet_package
        self._preview_movie = None

        self.setup_ui()
        self.load_pet_data()

    def set_pet_package(self, pet_package):
        """Update the current pet package."""
        self.pet_package = pet_package
        self.load_pet_data()

    def setup_ui(self):
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header with back button
        header = QHBoxLayout()
        self.back_btn = QPushButton("← 返回")
        self.back_btn.setStyleSheet("""
            QPushButton {
                background: white;
                color: #333;
                border: 1px solid #ddd;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #f5f5f5;
            }
        """)
        self.back_btn.clicked.connect(self.back_to_list.emit)
        header.addWidget(self.back_btn)

        self.title_label = QLabel("配置: 默认桌宠")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        header.addWidget(self.title_label, 1)

        layout.addLayout(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(20)

        # 1. Basic appearance section
        appearance_group = QGroupBox("基础形象")
        appearance_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        appearance_layout = QFormLayout(appearance_group)
        appearance_layout.setSpacing(10)

        # Row 1: 待机形象
        self.regular_image_edit = QLineEdit()
        self.regular_image_edit.setReadOnly(True)
        self.regular_image_edit.setStyleSheet("background: #f5f5f5; padding: 6px; border-radius: 4px;")
        regular_btn = QPushButton("更换")
        regular_btn.setStyleSheet("""
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
        regular_btn.clicked.connect(lambda: self.select_image('regular'))
        appearance_layout.addRow("待机形象", self.regular_image_edit)
        appearance_layout.addRow("", regular_btn)

        # Row 2: 缓降形象
        self.flying_image_edit = QLineEdit()
        self.flying_image_edit.setReadOnly(True)
        self.flying_image_edit.setStyleSheet("background: #f5f5f5; padding: 6px; border-radius: 4px;")
        flying_btn = QPushButton("更换")
        flying_btn.setStyleSheet("""
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
        flying_btn.clicked.connect(lambda: self.select_image('flying'))
        appearance_layout.addRow("缓降形象", self.flying_image_edit)
        appearance_layout.addRow("", flying_btn)

        # Row 3: 向左行走
        self.walk_left_label = QLabel("未设置")
        self.walk_left_label.setStyleSheet("color: #666;")
        self.walk_left_btn = QPushButton("设置")
        self.walk_left_btn.setStyleSheet("""
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
        self.walk_left_btn.clicked.connect(lambda: self.select_walk_animation('left'))
        appearance_layout.addRow("向左行走", self.walk_left_label)
        appearance_layout.addRow("", self.walk_left_btn)

        # Row 4: 向右行走
        self.walk_right_label = QLabel("未设置")
        self.walk_right_label.setStyleSheet("color: #666;")
        self.walk_right_btn = QPushButton("设置")
        self.walk_right_btn.setStyleSheet("""
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
        self.walk_right_btn.clicked.connect(lambda: self.select_walk_animation('right'))
        appearance_layout.addRow("向右行走", self.walk_right_label)
        appearance_layout.addRow("", self.walk_right_btn)

        # Row 5: 休息动画
        self.rest_animation_edit = QLineEdit()
        self.rest_animation_edit.setReadOnly(True)
        self.rest_animation_edit.setStyleSheet("background: #f5f5f5; padding: 6px; border-radius: 4px;")
        rest_btn = QPushButton("更换")
        rest_btn.setStyleSheet("""
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
        rest_btn.clicked.connect(lambda: self.select_image('rest'))
        appearance_layout.addRow("休息动画", self.rest_animation_edit)
        appearance_layout.addRow("", rest_btn)

        scroll_layout.addWidget(appearance_group)

        # 2. Actions section
        actions_group = QGroupBox("动作列表")
        actions_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        actions_layout = QVBoxLayout(actions_group)

        self.actions_table = QTableWidget()
        self.actions_table.setColumnCount(6)
        self.actions_table.setHorizontalHeaderLabels(["名称", "类型", "动画文件", "权重", "启用", "操作"])
        self.actions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.actions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.actions_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.actions_table.setStyleSheet("""
            QTableWidget {
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
            QTableWidget::item {
                padding: 5px;
            }
        """)
        actions_layout.addWidget(self.actions_table)

        add_action_btn = QPushButton("添加动作")
        add_action_btn.setStyleSheet("""
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
        add_action_btn.clicked.connect(self.add_action)
        actions_layout.addWidget(add_action_btn)

        scroll_layout.addWidget(actions_group)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        save_btn = QPushButton("保存配置")
        save_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4;
                color: white;
                border: none;
                padding: 8px 24px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #106ebe;
            }
        """)
        save_btn.clicked.connect(self.save_config)
        bottom_layout.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: white;
                color: #666;
                border: 1px solid #ddd;
                padding: 8px 24px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #f5f5f5;
            }
        """)
        cancel_btn.clicked.connect(self.back_to_list.emit)
        bottom_layout.addWidget(cancel_btn)

        layout.addLayout(bottom_layout)

    def load_pet_data(self):
        """Load pet configuration data."""
        if not self.pet_package:
            return

        self.title_label.setText(f"配置: {self.pet_package.meta.name}")

        # Load meta.json
        self.regular_image_edit.setText(self.pet_package.meta.regular_image)
        self.flying_image_edit.setText(self.pet_package.meta.flying_image)
        self.rest_animation_edit.setText(self.pet_package.meta.rest_animation)

        # Load walk animations from actions.json
        walk_action = None
        for action in self.pet_package.actions:
            if action.name == "walk":
                walk_action = action
                break

        if walk_action and len(walk_action.animation_files) >= 1:
            self.walk_left_label.setText(walk_action.animation_files[0])
        if walk_action and len(walk_action.animation_files) >= 2:
            self.walk_right_label.setText(walk_action.animation_files[1])

        # Load actions table
        self.actions_table.setRowCount(0)
        for action in self.pet_package.actions:
            row = self.actions_table.rowCount()
            self.actions_table.insertRow(row)

            self.actions_table.setItem(row, 0, QTableWidgetItem(action.name))
            self.actions_table.setItem(row, 1, QTableWidgetItem(action.type))
            self.actions_table.setItem(row, 2, QTableWidgetItem(str(len(action.animation_files))))
            self.actions_table.setItem(row, 3, QTableWidgetItem(str(action.weight)))
            self.actions_table.setItem(row, 4, QTableWidgetItem("是" if action.enabled else "否"))

    def select_image(self, image_type):
        """Select image for specific type."""
        dialog = AnimationSelectDialog(self.pet_package, self)
        if dialog.exec() == dialog.Accepted:
            files = dialog.get_selected_files()
            if files:
                filename = files[0]
                if image_type == 'regular':
                    self.regular_image_edit.setText(filename)
                    self.pet_package.meta.regular_image = filename
                elif image_type == 'flying':
                    self.flying_image_edit.setText(filename)
                    self.pet_package.meta.flying_image = filename
                elif image_type == 'rest':
                    self.rest_animation_edit.setText(filename)
                    self.pet_package.meta.rest_animation = filename

    def select_walk_animation(self, direction):
        """Select walk animation for direction."""
        dialog = AnimationSelectDialog(self.pet_package, self)
        if dialog.exec() == dialog.Accepted:
            files = dialog.get_selected_files()
            if files:
                filename = files[0]
                # Find or create walk action
                walk_action = None
                for action in self.pet_package.actions:
                    if action.name == "walk":
                        walk_action = action
                        break

                if not walk_action:
                    # Create walk action
                    walk_action = PetAction(
                        name="walk",
                        type="movement",
                        weight=1,
                        animation_files=[],
                        enabled=True,
                        config={"min_distance": 30, "max_distance": 100}
                    )
                    self.pet_package.actions.append(walk_action)

                if direction == 'left':
                    if len(walk_action.animation_files) == 0:
                        walk_action.animation_files.append(filename)
                    else:
                        walk_action.animation_files[0] = filename
                    self.walk_left_label.setText(filename)
                else:
                    if len(walk_action.animation_files) < 2:
                        while len(walk_action.animation_files) < 2:
                            walk_action.animation_files.append(filename)
                    else:
                        walk_action.animation_files[1] = filename
                    self.walk_right_label.setText(filename)

    def add_action(self):
        """Add new action."""
        existing_names = [a.name for a in self.pet_package.actions]
        dialog = ActionEditDialog(self.pet_package, self, existing_names=existing_names)
        if dialog.exec() == dialog.Accepted:
            action = dialog.get_action()
            self.pet_package.actions.append(action)
            self.load_pet_data()

    def save_config(self):
        """Save pet configuration."""
        try:
            # Save meta.json
            meta_path = self.pet_package.path / "meta.json"
            meta_data = {
                "name": self.pet_package.meta.name,
                "author": self.pet_package.meta.author,
                "version": self.pet_package.meta.version,
                "description": self.pet_package.meta.description,
                "preview": self.pet_package.meta.preview,
                "regular_image": self.regular_image_edit.text(),
                "flying_image": self.flying_image_edit.text(),
                "rest_animation": self.rest_animation_edit.text()
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)

            # Save actions.json
            actions_path = self.pet_package.config_dir / "actions.json"
            actions_data = {
                "actions": [
                    {
                        "name": a.name,
                        "type": a.type,
                        "weight": a.weight,
                        "animation_files": a.animation_files,
                        "enabled": a.enabled,
                        "config": a.config
                    }
                    for a in self.pet_package.actions
                ]
            }
            with open(actions_path, "w", encoding="utf-8") as f:
                json.dump(actions_data, f, ensure_ascii=False, indent=2)

            QMessageBox.information(self, "保存成功", "配置已保存，重启应用后生效。")
            self.back_to_list.emit()

        except Exception as e:
            logging.error(f"Failed to save pet config: {e}")
            QMessageBox.critical(self, "保存失败", f"保存配置时出错：{str(e)}")
