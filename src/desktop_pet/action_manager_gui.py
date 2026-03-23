from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QLineEdit, QSpinBox, QCheckBox, QComboBox, QTextEdit,
    QListWidget, QListWidgetItem, QFileDialog, QGroupBox,
    QFormLayout, QDialogButtonBox, QWidget, QAbstractItemView
)
from PyQt6.QtCore import Qt

from .config_manager import ConfigManager, AnimationConfig
from .pet_loader import PetPackage, PetAction
from .utils import get_assets_path


class AnimationEditDialog(QDialog):
    """动画编辑对话框"""

    def __init__(self, parent=None, animation: Optional[AnimationConfig] = None):
        super().__init__(parent)
        self.animation = animation
        self.setWindowTitle("编辑动画" if animation else "添加动画")
        self.setMinimumWidth(400)
        self.setup_ui()
        if animation:
            self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("animations/your_animation/your_animation.gif")
        form_layout.addRow("路径:", self.path_edit)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self.browse_file)
        form_layout.addRow("", browse_btn)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 1000)
        self.width_spin.setValue(200)
        form_layout.addRow("宽度:", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 1000)
        self.height_spin.setValue(159)
        form_layout.addRow("高度:", self.height_spin)

        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse_file(self):
        assets_path = get_assets_path()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择动画文件", str(assets_path),
            "GIF文件 (*.gif);;所有文件 (*.*)"
        )
        if file_path:
            try:
                rel_path = Path(file_path).relative_to(assets_path)
                self.path_edit.setText(str(rel_path).replace("\\", "/"))
            except ValueError:
                QMessageBox.warning(self, "警告", "请选择assets目录下的文件")

    def load_data(self):
        if self.animation:
            self.path_edit.setText(self.animation.path)
            self.width_spin.setValue(self.animation.width)
            self.height_spin.setValue(self.animation.height)

    def get_animation(self) -> AnimationConfig:
        return AnimationConfig(
            path=self.path_edit.text().strip(),
            width=self.width_spin.value(),
            height=self.height_spin.value()
        )


class ActionEditDialog(QDialog):
    """动作编辑对话框"""

    def __init__(self, parent=None, action: Optional[PetAction] = None, existing_names: list = None):
        super().__init__(parent)
        self.action = action
        self.existing_names = existing_names or []
        self.animations: list[AnimationConfig] = []
        self.setWindowTitle("编辑动作" if action else "添加动作")
        self.setMinimumWidth(500)
        self.setMinimumHeight(500)
        self.setup_ui()
        if action:
            self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("动作名称（如：dance、sleep）")
        if self.action:
            self.name_edit.setEnabled(False)
        basic_layout.addRow("名称*:", self.name_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["animation", "movement"])
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        basic_layout.addRow("类型:", self.type_combo)

        self.enabled_check = QCheckBox("启用")
        self.enabled_check.setChecked(True)
        basic_layout.addRow("状态:", self.enabled_check)

        self.weight_spin = QSpinBox()
        self.weight_spin.setRange(1, 100)
        self.weight_spin.setValue(1)
        basic_layout.addRow("权重:", self.weight_spin)

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("动作描述")
        basic_layout.addRow("描述:", self.desc_edit)

        layout.addWidget(basic_group)

        self.animation_group = QGroupBox("动画配置")
        animation_layout = QVBoxLayout(self.animation_group)

        self.anim_list = QListWidget()
        self.anim_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        animation_layout.addWidget(self.anim_list)

        anim_btn_layout = QHBoxLayout()
        add_anim_btn = QPushButton("添加动画")
        add_anim_btn.clicked.connect(self.add_animation)
        edit_anim_btn = QPushButton("编辑动画")
        edit_anim_btn.clicked.connect(self.edit_animation)
        del_anim_btn = QPushButton("删除动画")
        del_anim_btn.clicked.connect(self.delete_animation)
        anim_btn_layout.addWidget(add_anim_btn)
        anim_btn_layout.addWidget(edit_anim_btn)
        anim_btn_layout.addWidget(del_anim_btn)
        animation_layout.addLayout(anim_btn_layout)

        layout.addWidget(self.animation_group)

        self.movement_group = QGroupBox("移动配置")
        movement_layout = QFormLayout(self.movement_group)

        self.min_dist_spin = QSpinBox()
        self.min_dist_spin.setRange(10, 1000)
        self.min_dist_spin.setValue(30)
        movement_layout.addRow("最小距离:", self.min_dist_spin)

        self.max_dist_spin = QSpinBox()
        self.max_dist_spin.setRange(10, 1000)
        self.max_dist_spin.setValue(100)
        movement_layout.addRow("最大距离:", self.max_dist_spin)

        layout.addWidget(self.movement_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.on_type_changed(self.type_combo.currentText())

    def on_type_changed(self, action_type: str):
        if action_type == "animation":
            self.animation_group.setVisible(True)
            self.movement_group.setVisible(False)
        else:
            self.animation_group.setVisible(False)
            self.movement_group.setVisible(True)

    def add_animation(self):
        dialog = AnimationEditDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            anim = dialog.get_animation()
            self.animations.append(anim)
            self.update_anim_list()

    def edit_animation(self):
        current_row = self.anim_list.currentRow()
        if current_row < 0 or current_row >= len(self.animations):
            QMessageBox.warning(self, "警告", "请先选择一个动画")
            return

        dialog = AnimationEditDialog(self, self.animations[current_row])
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.animations[current_row] = dialog.get_animation()
            self.update_anim_list()

    def delete_animation(self):
        current_row = self.anim_list.currentRow()
        if current_row < 0 or current_row >= len(self.animations):
            QMessageBox.warning(self, "警告", "请先选择一个动画")
            return

        reply = QMessageBox.question(
            self, "确认删除", "确定要删除这个动画吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            del self.animations[current_row]
            self.update_anim_list()

    def update_anim_list(self):
        self.anim_list.clear()
        for anim in self.animations:
            item_text = f"{anim.path} ({anim.width}x{anim.height})"
            self.anim_list.addItem(item_text)

    def load_data(self):
        if not self.action:
            return

        self.name_edit.setText(self.action.name)
        self.type_combo.setCurrentText(self.action.type)
        self.enabled_check.setChecked(self.action.enabled)
        self.weight_spin.setValue(self.action.weight)

        if self.action.type == "animation":
            self.animations = [AnimationConfig(path=f, width=200, height=159) for f in self.action.animation_files]
            self.update_anim_list()
        elif self.action.type == "movement":
            config = self.action.config
            self.min_dist_spin.setValue(config.get("min_distance", 30))
            self.max_dist_spin.setValue(config.get("max_distance", 100))

    def validate_and_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "验证失败", "动作名称不能为空")
            return

        if not self.action and name in self.existing_names:
            QMessageBox.warning(self, "验证失败", f"动作 '{name}' 已存在")
            return

        action_type = self.type_combo.currentText()
        if action_type == "animation" and not self.animations:
            QMessageBox.warning(self, "验证失败", "动画类型动作至少需要添加一个动画文件")
            return

        self.accept()

    def get_action(self) -> PetAction:
        name = self.name_edit.text().strip()
        action_type = self.type_combo.currentText()

        config = {}
        if action_type == "movement":
            config = {
                "min_distance": self.min_dist_spin.value(),
                "max_distance": self.max_dist_spin.value()
            }

        animation_files = [a.path for a in self.animations]

        return PetAction(
            name=name,
            type=action_type,
            weight=self.weight_spin.value(),
            animation_files=animation_files,
            enabled=self.enabled_check.isChecked(),
            config=config
        )


class ActionManagerGUI(QDialog):
    """动作管理器主窗口"""

    def __init__(self, config_manager: ConfigManager, pet_package: PetPackage, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.pet_package = pet_package
        self.setWindowTitle("动作管理器")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self.setup_ui()
        self.refresh_action_list()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        info_label = QLabel("管理桌面宠物的动作配置。修改后需要重启桌面宠物才能生效。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; padding: 5px;")
        layout.addWidget(info_label)

        self.action_table = QTableWidget()
        self.action_table.setColumnCount(5)
        self.action_table.setHorizontalHeaderLabels(["名称", "类型", "描述", "权重", "启用"])
        self.action_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.action_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.action_table.setColumnWidth(0, 120)
        self.action_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.action_table.setColumnWidth(1, 80)
        self.action_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.action_table.setColumnWidth(3, 60)
        self.action_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.action_table.setColumnWidth(4, 50)
        self.action_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.action_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.action_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.action_table.doubleClicked.connect(self.edit_selected_action)
        layout.addWidget(self.action_table)

        btn_layout = QHBoxLayout()

        add_btn = QPushButton("添加动作")
        add_btn.clicked.connect(self.add_action)
        btn_layout.addWidget(add_btn)

        edit_btn = QPushButton("编辑动作")
        edit_btn.clicked.connect(self.edit_selected_action)
        btn_layout.addWidget(edit_btn)

        delete_btn = QPushButton("删除动作")
        delete_btn.clicked.connect(self.delete_selected_action)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        save_btn = QPushButton("保存配置")
        save_btn.setStyleSheet("font-weight: bold;")
        save_btn.clicked.connect(self.save_config)
        btn_layout.addWidget(save_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def refresh_action_list(self):
        self.action_table.setRowCount(0)
        if not self.pet_package:
            return
        actions = self.pet_package.actions

        for action in actions:
            row = self.action_table.rowCount()
            self.action_table.insertRow(row)

            name_item = QTableWidgetItem(action.name)
            self.action_table.setItem(row, 0, name_item)

            type_item = QTableWidgetItem(action.type)
            self.action_table.setItem(row, 1, type_item)

            desc_item = QTableWidgetItem("")
            self.action_table.setItem(row, 2, desc_item)

            weight_item = QTableWidgetItem(str(action.weight))
            self.action_table.setItem(row, 3, weight_item)

            enabled_item = QTableWidgetItem("是" if action.enabled else "否")
            enabled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.action_table.setItem(row, 4, enabled_item)

    def get_selected_action_name(self) -> Optional[str]:
        selected = self.action_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        return self.action_table.item(row, 0).text()

    def add_action(self):
        existing_names = [a.name for a in self.pet_package.actions]
        dialog = ActionEditDialog(self, existing_names=existing_names)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            action = dialog.get_action()
            self.pet_package.actions.append(action)
            self.refresh_action_list()

    def edit_selected_action(self):
        name = self.get_selected_action_name()
        if not name:
            QMessageBox.warning(self, "警告", "请先选择一个动作")
            return

        action = next((a for a in self.pet_package.actions if a.name == name), None)
        if not action:
            return

        existing_names = [a.name for a in self.pet_package.actions if a.name != name]
        dialog = ActionEditDialog(self, action, existing_names)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_action = dialog.get_action()
            for i, a in enumerate(self.pet_package.actions):
                if a.name == name:
                    self.pet_package.actions[i] = new_action
                    break
            self.refresh_action_list()

    def delete_selected_action(self):
        name = self.get_selected_action_name()
        if not name:
            QMessageBox.warning(self, "警告", "请先选择一个动作")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除动作 '{name}' 吗？\n此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.pet_package.actions = [a for a in self.pet_package.actions if a.name != name]
            self.refresh_action_list()

    def save_config(self):
        try:
            import json
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
            QMessageBox.information(
                self, "保存成功",
                f"配置已保存到 {actions_path}\n请重启桌面宠物以应用更改。"
            )
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存配置时出错：{str(e)}")
