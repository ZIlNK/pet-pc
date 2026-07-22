"""Per-instance action configuration page."""

import copy
import logging

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..ui_style import (
    PRIMARY_BUTTON_STYLE, SECONDARY_BUTTON_STYLE,
    FONT_SIZE_TITLE, title_style, subtitle_style,
)

logger = logging.getLogger(__name__)


class ActionControlPage(QWidget):
    """Edit effective action overrides for one platform instance."""

    def __init__(self, instance_config, platform, parent=None):
        if instance_config is None or platform is None:
            raise TypeError("ActionControlPage requires instance_config and platform")
        super().__init__(parent)
        self.platform = platform
        self.instance_config = instance_config
        self._actions_buffer = copy.deepcopy(instance_config.actions or {})
        self._setup_ui()
        self._load_actions_table()

    def set_instance(self, instance_config) -> None:
        if instance_config is None:
            raise TypeError("instance_config is required")
        self.instance_config = instance_config
        self._actions_buffer = copy.deepcopy(instance_config.actions or {})
        self._load_actions_table()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(15)

        title = QLabel("动作配置")
        title.setStyleSheet(title_style(FONT_SIZE_TITLE))
        layout.addWidget(title)

        self.actions_group = QGroupBox("实例动作配置")
        actions_layout = QVBoxLayout(self.actions_group)

        hint = QLabel("编辑当前实例的动作启用状态和权重；资源包文件不会被修改。")
        hint.setStyleSheet(subtitle_style())
        hint.setWordWrap(True)
        actions_layout.addWidget(hint)

        self.actions_table = QTableWidget()
        self.actions_table.setColumnCount(4)
        self.actions_table.setHorizontalHeaderLabels(
            ["动作名", "启用", "权重", "动画文件数"]
        )
        self.actions_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.actions_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.actions_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        actions_layout.addWidget(self.actions_table)

        buttons = QHBoxLayout()
        toggle_button = QPushButton("切换启用状态")
        toggle_button.setStyleSheet(SECONDARY_BUTTON_STYLE)
        toggle_button.clicked.connect(self._toggle_selected_action)
        buttons.addWidget(toggle_button)

        increase_button = QPushButton("权重 +1")
        increase_button.setStyleSheet(SECONDARY_BUTTON_STYLE)
        increase_button.clicked.connect(lambda: self._adjust_selected_weight(1))
        buttons.addWidget(increase_button)

        decrease_button = QPushButton("权重 -1")
        decrease_button.setStyleSheet(SECONDARY_BUTTON_STYLE)
        decrease_button.clicked.connect(lambda: self._adjust_selected_weight(-1))
        buttons.addWidget(decrease_button)
        buttons.addStretch()
        actions_layout.addLayout(buttons)

        save_button = QPushButton("保存动作配置")
        save_button.setStyleSheet(PRIMARY_BUTTON_STYLE)
        save_button.clicked.connect(self._save_instance_actions)
        actions_layout.addWidget(save_button)

        layout.addWidget(self.actions_group)

    def _load_actions_table(self) -> None:
        self.actions_table.setRowCount(0)
        for name, action_data in self._actions_buffer.items():
            row = self.actions_table.rowCount()
            self.actions_table.insertRow(row)
            self.actions_table.setItem(row, 0, QTableWidgetItem(str(name)))
            enabled = bool(action_data.get("enabled", True))
            self.actions_table.setItem(row, 1, QTableWidgetItem("是" if enabled else "否"))
            self.actions_table.setItem(
                row, 2, QTableWidgetItem(str(action_data.get("weight", 1)))
            )
            animation_files = action_data.get("animation_files", []) or []
            self.actions_table.setItem(
                row, 3, QTableWidgetItem(str(len(animation_files)))
            )

    def _selected_action(self):
        row = self.actions_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "提示", "请先选择一个动作。")
            return None
        name_item = self.actions_table.item(row, 0)
        if name_item is None:
            return None
        return self._actions_buffer.get(name_item.text())

    def _toggle_selected_action(self) -> None:
        action = self._selected_action()
        if action is None:
            return
        action["enabled"] = not bool(action.get("enabled", True))
        self._load_actions_table()

    def _adjust_selected_weight(self, delta: int) -> None:
        action = self._selected_action()
        if action is None:
            return
        try:
            current = int(action.get("weight", 1))
        except (TypeError, ValueError):
            current = 1
        action["weight"] = max(0, current + delta)
        self._load_actions_table()

    def _save_instance_actions(self) -> None:
        try:
            updated = self.platform.update_instance_config(
                self.instance_config.pet_id,
                {"actions": copy.deepcopy(self._actions_buffer)},
            )
        except Exception as error:
            logger.exception("Failed to save instance actions")
            QMessageBox.critical(self, "保存失败", f"保存动作配置时出错：{error}")
            return
        self.instance_config = updated
        self._actions_buffer = copy.deepcopy(updated.actions or {})
        self._load_actions_table()
        QMessageBox.information(self, "保存成功", "动作配置已保存。")
