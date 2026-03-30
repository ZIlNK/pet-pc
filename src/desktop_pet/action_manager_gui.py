import json
import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QLineEdit, QSpinBox, QCheckBox, QComboBox,
    QListWidget, QListWidgetItem, QFileDialog, QGroupBox,
    QFormLayout, QDialogButtonBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QMovie

from .config_manager import ConfigManager
from .pet_loader import PetPackage, PetAction


class AnimationSelectDialog(QDialog):
    """动画文件选择对话框 - 支持导入和选择"""

    def __init__(self, pet_package: PetPackage, parent=None, selected_files: list[str] = None):
        super().__init__(parent)
        self.pet_package = pet_package
        self.selected_files = selected_files or []
        self.imported_files: list[str] = []  # 记录本次导入的文件
        self._current_movie: Optional[QMovie] = None  # 保持 GIF 动画引用
        self.setWindowTitle("选择动画文件")
        self.setMinimumSize(600, 450)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 顶部按钮区
        btn_layout = QHBoxLayout()
        import_btn = QPushButton("📁 从文件导入...")
        import_btn.clicked.connect(self.import_files)
        btn_layout.addWidget(import_btn)

        refresh_btn = QPushButton("🔄 刷新列表")
        refresh_btn.clicked.connect(self.load_animation_files)
        btn_layout.addWidget(refresh_btn)

        btn_layout.addStretch()

        # 提示信息
        info_label = QLabel("提示：点击「从文件导入」可添加外部动画文件，将自动复制到宠物包")
        info_label.setStyleSheet("color: gray; font-size: 11px;")
        btn_layout.addWidget(info_label)

        layout.addLayout(btn_layout)

        # 主内容区
        content_layout = QHBoxLayout()

        # 左侧：文件列表（支持多选）
        list_group = QGroupBox("宠物包内的动画文件")
        list_layout = QVBoxLayout(list_group)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.load_animation_files()
        list_layout.addWidget(self.file_list)
        content_layout.addWidget(list_group, stretch=1)

        # 右侧：预览区域
        preview_group = QGroupBox("预览")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_label = QLabel("选择文件查看预览")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(200, 200)
        self.preview_label.setStyleSheet("background-color: #333; color: white;")
        preview_layout.addWidget(self.preview_label)

        self.file_info_label = QLabel("")
        self.file_info_label.setStyleSheet("color: gray; font-size: 10px;")
        self.file_info_label.setWordWrap(True)
        preview_layout.addWidget(self.file_info_label)
        content_layout.addWidget(preview_group, stretch=1)

        layout.addLayout(content_layout)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 连接信号
        self.file_list.itemSelectionChanged.connect(self.on_selection_changed)

    def load_animation_files(self):
        """从宠物包的 animations 目录加载所有动画文件"""
        self.file_list.clear()
        animations_dir = self.pet_package.animations_dir
        if not animations_dir.exists():
            return

        patterns = ["*.webp", "*.gif", "*.png", "*.apng"]

        for pattern in patterns:
            for f in sorted(animations_dir.glob(pattern)):
                item = QListWidgetItem(f.name)
                item.setData(Qt.ItemDataRole.UserRole, str(f))
                item.setToolTip(str(f))
                # 预选已选中的文件
                if f.name in self.selected_files:
                    item.setSelected(True)
                self.file_list.addItem(item)

    def import_files(self):
        """从外部导入动画文件到宠物包"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择动画文件",
            "",
            "动画文件 (*.webp *.gif *.png *.apng);;所有文件 (*.*)"
        )

        if not files:
            return

        animations_dir = self.pet_package.animations_dir
        animations_dir.mkdir(parents=True, exist_ok=True)

        imported = []
        for file_path in files:
            src_path = Path(file_path)
            dst_path = animations_dir / src_path.name

            # 检查是否已存在
            if dst_path.exists():
                reply = QMessageBox.question(
                    self,
                    "文件已存在",
                    f"文件 '{src_path.name}' 已存在，是否覆盖？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    continue

            # 复制文件
            try:
                shutil.copy2(src_path, dst_path)
                imported.append(src_path.name)
            except Exception as e:
                QMessageBox.warning(self, "导入失败", f"无法复制文件 '{src_path.name}':\n{e}")

        if imported:
            self.imported_files.extend(imported)
            self.load_animation_files()  # 刷新列表
            # 选中新导入的文件
            for i in range(self.file_list.count()):
                item = self.file_list.item(i)
                if item.text() in imported:
                    item.setSelected(True)

            QMessageBox.information(
                self,
                "导入成功",
                f"已导入 {len(imported)} 个文件到宠物包"
            )

    def on_selection_changed(self):
        """更新预览"""
        items = self.file_list.selectedItems()
        if items:
            file_path = Path(items[0].data(Qt.ItemDataRole.UserRole))
            self.show_preview(file_path)
            # 显示文件信息
            try:
                size = file_path.stat().st_size
                size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
                self.file_info_label.setText(f"文件: {file_path.name}\n大小: {size_str}")
            except OSError:
                self.file_info_label.setText(f"文件: {file_path.name}")
        else:
            self._clear_preview()
            self.preview_label.setText("选择文件查看预览")
            self.file_info_label.clear()

    def _clear_preview(self):
        """清除预览"""
        if self._current_movie:
            self._current_movie.stop()
            self._current_movie.deleteLater()
            self._current_movie = None
        self.preview_label.clear()

    def show_preview(self, file_path: Path):
        """显示静态预览或 GIF 动画"""
        self._clear_preview()

        if file_path.suffix.lower() == '.gif':
            self._current_movie = QMovie(str(file_path))
            self._current_movie.setScaledSize(QSize(200, 159))
            self.preview_label.setMovie(self._current_movie)
            self._current_movie.start()
        else:
            pixmap = QPixmap(str(file_path))
            self.preview_label.setPixmap(pixmap.scaled(
                200, 159,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

    def get_selected_files(self) -> list[str]:
        """返回选中的文件名列表（不含路径）"""
        return [item.text() for item in self.file_list.selectedItems()]


class ActionEditDialog(QDialog):
    """动作编辑对话框"""

    def __init__(self, pet_package: PetPackage, parent=None, action: Optional[PetAction] = None, existing_names: list = None):
        super().__init__(parent)
        self.pet_package = pet_package
        self.action = action
        self.existing_names = existing_names or []
        self.animation_files: list[str] = []  # 只存储文件名
        self._preview_movie: Optional[QMovie] = None  # 保持 GIF 动画引用
        self.setWindowTitle("编辑动作" if action else "添加动作")
        self.setMinimumWidth(550)
        self.setMinimumHeight(550)
        self.setup_ui()
        if action:
            self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 基本信息组
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

        layout.addWidget(basic_group)

        # 动画配置组（简化）
        self.animation_group = QGroupBox("动画文件")
        animation_layout = QVBoxLayout(self.animation_group)

        self.anim_list = QListWidget()
        self.anim_list.setToolTip("双击可预览动画")
        self.anim_list.itemDoubleClicked.connect(self.preview_animation)
        animation_layout.addWidget(self.anim_list)

        anim_btn_layout = QHBoxLayout()
        select_btn = QPushButton("📂 选择/导入动画...")
        select_btn.clicked.connect(self.select_animations)
        remove_btn = QPushButton("🗑 移除选中")
        remove_btn.clicked.connect(self.remove_animation)
        anim_btn_layout.addWidget(select_btn)
        anim_btn_layout.addWidget(remove_btn)
        animation_layout.addLayout(anim_btn_layout)

        # 预览区域
        preview_layout = QHBoxLayout()
        self.preview_label = QLabel("双击列表项预览")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(200, 159)
        self.preview_label.setStyleSheet("background-color: #333; color: white;")
        preview_layout.addStretch()
        preview_layout.addWidget(self.preview_label)
        preview_layout.addStretch()
        animation_layout.addLayout(preview_layout)

        layout.addWidget(self.animation_group)

        # 移动配置组
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

        # 按钮
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

    def select_animations(self):
        """打开动画选择对话框"""
        dialog = AnimationSelectDialog(
            self.pet_package,
            self,
            self.animation_files
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.animation_files = dialog.get_selected_files()
            self.update_anim_list()

    def preview_animation(self, item):
        """双击预览动画"""
        filename = item.text()
        file_path = self.pet_package.animations_dir / filename
        if not file_path.exists():
            return

        # 清除之前的预览
        if self._preview_movie:
            self._preview_movie.stop()
            self._preview_movie.deleteLater()
            self._preview_movie = None

        self.preview_label.clear()

        if file_path.suffix.lower() == '.gif':
            self._preview_movie = QMovie(str(file_path))
            self._preview_movie.setScaledSize(QSize(200, 159))
            self.preview_label.setMovie(self._preview_movie)
            self._preview_movie.start()
        else:
            pixmap = QPixmap(str(file_path))
            self.preview_label.setPixmap(pixmap.scaled(
                200, 159,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

    def remove_animation(self):
        """移除选中的动画文件（只从列表移除，不删除文件）"""
        current_row = self.anim_list.currentRow()
        if 0 <= current_row < len(self.animation_files):
            del self.animation_files[current_row]
            self.update_anim_list()

    def update_anim_list(self):
        """更新动画文件列表显示"""
        self.anim_list.clear()
        for filename in self.animation_files:
            self.anim_list.addItem(filename)

    def load_data(self):
        if not self.action:
            return

        self.name_edit.setText(self.action.name)
        self.type_combo.setCurrentText(self.action.type)
        self.enabled_check.setChecked(self.action.enabled)
        self.weight_spin.setValue(self.action.weight)

        if self.action.type == "animation":
            self.animation_files = self.action.animation_files.copy()
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
        if action_type == "animation" and not self.animation_files:
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

        # 保留原有的 zone_actions
        zone_actions = self.action.zone_actions if self.action else {}

        return PetAction(
            name=name,
            type=action_type,
            weight=self.weight_spin.value(),
            animation_files=self.animation_files.copy(),
            enabled=self.enabled_check.isChecked(),
            config=config,
            zone_actions=zone_actions
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
        self.action_table.setHorizontalHeaderLabels(["名称", "类型", "动画文件数", "权重", "启用"])
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

            anim_count_item = QTableWidgetItem(str(len(action.animation_files)))
            anim_count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.action_table.setItem(row, 2, anim_count_item)

            weight_item = QTableWidgetItem(str(action.weight))
            weight_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
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
        dialog = ActionEditDialog(self.pet_package, self, existing_names=existing_names)

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
        dialog = ActionEditDialog(self.pet_package, self, action, existing_names)

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
            actions_path = self.pet_package.config_dir / "actions.json"
            actions_data = {
                "actions": [
                    {
                        "name": a.name,
                        "type": a.type,
                        "weight": a.weight,
                        "animation_files": a.animation_files,
                        "enabled": a.enabled,
                        "config": a.config,
                        "zone_actions": a.zone_actions
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