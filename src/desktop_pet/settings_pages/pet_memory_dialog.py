"""Managed-memory dialog for a pet-bound OpenClaw Agent."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..openclaw_memory_client import OpenClawMemoryClient, OpenClawMemoryError
from ..ui_style import (
    DANGER_BUTTON_STYLE,
    INPUT_STYLE,
    PAGE_STYLE,
    PRIMARY_BUTTON_STYLE,
    SECONDARY_BUTTON_STYLE,
    subtitle_style,
    title_style,
)


class _MemoryRequestThread(QThread):
    succeeded = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, client, operation: str, args: tuple, parent=None):
        super().__init__(parent)
        self.client = client
        self.operation = operation
        self.args = args

    def run(self):
        try:
            result = getattr(self.client, self.operation)(*self.args)
        except OpenClawMemoryError as error:
            self.failed.emit(error.kind, str(error))
        except Exception as error:
            self.failed.emit("server", str(error))
        else:
            self.succeeded.emit(self.operation, result)


class PetMemoryDialog(QDialog):
    """List and edit only the plugin-managed region of an Agent MEMORY.md."""

    def __init__(self, pet_name: str, agent_id: str, platform, parent=None):
        super().__init__(parent)
        self.agent_id = agent_id
        mcp = platform.global_config.mcp
        self.client = OpenClawMemoryClient(
            mcp.get("openclaw_hooks_url", ""),
            mcp.get("openclaw_secret_token", ""),
        )
        self._request_thread = None
        self._setup_ui(pet_name)
        self.refresh_memories()

    def _setup_ui(self, pet_name: str):
        self.setWindowTitle("OpenClaw 长期记忆")
        self.resize(660, 460)
        self.setStyleSheet(PAGE_STYLE + INPUT_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title = QLabel("管理长期记忆")
        title.setStyleSheet(title_style())
        layout.addWidget(title)

        identity = QLabel(f"桌宠: {pet_name}    Agent ID: {self.agent_id}")
        identity.setStyleSheet(subtitle_style())
        layout.addWidget(identity)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(subtitle_style())
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["记忆内容", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setStyleSheet(INPUT_STYLE)
        layout.addWidget(self.table, 1)

        add_row = QHBoxLayout()
        self.memory_edit = QLineEdit()
        self.memory_edit.setMaxLength(500)
        self.memory_edit.setPlaceholderText("输入一条长期记忆（最多 500 字符）")
        self.memory_edit.setStyleSheet(INPUT_STYLE)
        self.memory_edit.returnPressed.connect(self.add_memory)
        add_row.addWidget(self.memory_edit, 1)
        self.add_btn = QPushButton("新增")
        self.add_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.add_btn.clicked.connect(self.add_memory)
        add_row.addWidget(self.add_btn)
        layout.addLayout(add_row)

        actions = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.refresh_btn.clicked.connect(self.refresh_memories)
        actions.addWidget(self.refresh_btn)
        self.clear_btn = QPushButton("清空全部")
        self.clear_btn.setStyleSheet(DANGER_BUTTON_STYLE)
        self.clear_btn.clicked.connect(self.clear_memories)
        actions.addWidget(self.clear_btn)
        actions.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        close_btn.clicked.connect(self.accept)
        actions.addWidget(close_btn)
        layout.addLayout(actions)

    def _set_busy(self, busy: bool):
        self.refresh_btn.setDisabled(busy)
        self.clear_btn.setDisabled(busy)
        self.add_btn.setDisabled(busy)
        self.memory_edit.setDisabled(busy)
        if busy:
            self.status_label.setText("正在加载…")

    def _start_request(self, operation: str, *args):
        if self._request_thread is not None and self._request_thread.isRunning():
            return
        self._set_busy(True)
        thread = _MemoryRequestThread(self.client, operation, args, self)
        thread.succeeded.connect(self._request_succeeded)
        thread.failed.connect(self._request_failed)
        thread.finished.connect(self._request_finished)
        self._request_thread = thread
        thread.start()

    def _request_succeeded(self, operation: str, result):
        if operation == "list_memories":
            self._render_memories(result)
            return
        if operation == "add_memory":
            self.memory_edit.clear()
        self.status_label.setText("操作成功，正在刷新…")
        self._refresh_after_request = True

    def _request_failed(self, kind: str, message: str):
        labels = {
            "connection": "连接失败：请确认 OpenClaw 已启动。",
            "auth": "鉴权失败：请检查共享密钥。",
            "conflict": "记忆文件结构损坏，已拒绝修改。",
            "server": "OpenClaw 记忆服务返回错误。",
        }
        self.status_label.setText(f"{labels.get(kind, labels['server'])} {message}")

    def _request_finished(self):
        refresh = bool(getattr(self, "_refresh_after_request", False))
        self._refresh_after_request = False
        self._set_busy(False)
        thread = self.sender()
        if thread is self._request_thread:
            self._request_thread = None
        thread.deleteLater()
        if refresh:
            self.refresh_memories()

    def _render_memories(self, memories):
        self.table.setRowCount(0)
        valid = [item for item in memories if isinstance(item, dict)]
        for row, memory in enumerate(valid):
            memory_id = str(memory.get("id", ""))
            text = str(memory.get("text", ""))
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(text))
            delete_btn = QPushButton("删除")
            delete_btn.setStyleSheet(DANGER_BUTTON_STYLE)
            delete_btn.clicked.connect(
                lambda _checked=False, mid=memory_id, value=text: self.delete_memory(mid, value)
            )
            self.table.setCellWidget(row, 1, delete_btn)
        if valid:
            self.status_label.setText(f"共 {len(valid)} 条记忆。")
        else:
            self.status_label.setText("暂无受管理的长期记忆。")

    def refresh_memories(self):
        self._start_request("list_memories", self.agent_id)

    def add_memory(self):
        text = " ".join(self.memory_edit.text().split())
        if not text:
            QMessageBox.warning(self, "无法新增", "记忆内容不能为空。")
            return
        self._start_request("add_memory", self.agent_id, text)

    def delete_memory(self, memory_id: str, text: str):
        answer = QMessageBox.question(
            self,
            "删除记忆",
            f"确定删除这条记忆吗？\n\n{text}",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_request("delete_memory", self.agent_id, memory_id)

    def clear_memories(self):
        answer = QMessageBox.question(
            self,
            "清空长期记忆",
            "确定清空该 Agent 的全部受管理记忆吗？此操作不会删除 MEMORY.md 的其他内容。",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_request("clear_memories", self.agent_id)
