"""实例管理页面 - 列出/创建/关闭桌宠实例。"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QGridLayout, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal

logger = logging.getLogger(__name__)


PRIMARY_TAG_STYLE = """
    background: #f2c572;
    color: #17201d;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
"""

CREATE_BUTTON_STYLE = """
    QPushButton {
        background: #2f7d68;
        color: #ffffff;
        border: none;
        padding: 8px 18px;
        border-radius: 8px;
        font-weight: 700;
    }
    QPushButton:hover {
        background: #256a58;
    }
    QPushButton:disabled {
        background: #cfd8d3;
        color: #f5f7f4;
    }
"""

EDIT_BUTTON_STYLE = """
    QPushButton {
        background: #0078d4;
        color: white;
        border: none;
        padding: 6px 12px;
        border-radius: 4px;
    }
    QPushButton:hover {
        background: #106ebe;
    }
"""

CLOSE_BUTTON_STYLE = """
    QPushButton {
        background: #d9534f;
        color: white;
        border: none;
        padding: 6px 12px;
        border-radius: 4px;
    }
    QPushButton:hover {
        background: #c9302c;
    }
"""

CARD_STYLE = """
    QFrame {
        background: #ffffff;
        border: 1px solid #dfe6e1;
        border-radius: 10px;
    }
    QFrame:hover {
        border-color: #2f7d68;
    }
"""


class InstanceManagerPage(QWidget):
    """实例管理页面：列出所有桌宠实例，支持创建/编辑/关闭。"""

    # 选中实例时发出，携带 pet_id
    instance_selected = pyqtSignal(str)
    # 创建新实例请求（打开资源包选择对话框）
    create_instance_requested = pyqtSignal()
    # 实例被关闭后发出，携带 pet_id（便于其他页面刷新）
    instance_closed = pyqtSignal(str)
    # 实例创建成功后发出，携带 pet_id
    instance_created = pyqtSignal(str)

    def __init__(self, platform, parent=None):
        super().__init__(parent)
        self.platform = platform
        self._instance_cards = []

        self.setup_ui()
        if self.platform is not None:
            self.refresh_instances()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def setup_ui(self):
        """构建页面布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(14)

        # 顶部标题与创建按钮
        header_layout = QHBoxLayout()
        title = QLabel("实例管理")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #17201d;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.create_btn = QPushButton("+ 创建新实例")
        self.create_btn.setStyleSheet(CREATE_BUTTON_STYLE)
        self.create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_btn.setEnabled(self.platform is not None)
        self.create_btn.clicked.connect(self._on_create_clicked)
        header_layout.addWidget(self.create_btn)

        layout.addLayout(header_layout)

        description = QLabel("管理当前运行中的桌宠实例，可编辑配置或关闭实例。")
        description.setStyleSheet("font-size: 13px; color: #66736e;")
        layout.addWidget(description)

        # 实例计数标签
        self.count_label = QLabel("暂无实例")
        self.count_label.setStyleSheet("font-size: 13px; color: #2c3935; font-weight: 600;")
        layout.addWidget(self.count_label)

        # 滚动区域：实例卡片列表
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none;")

        self.cards_container = QWidget()
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self.cards_container)

        layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # 数据刷新
    # ------------------------------------------------------------------
    def refresh_instances(self):
        """从 platform 拉取实例列表并重新渲染。"""
        # 清理旧卡片
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._instance_cards.clear()

        if self.platform is None:
            self.count_label.setText("平台未就绪")
            return

        try:
            instances = self.platform.list_instances()
        except Exception as e:
            logger.error("Failed to list instances: %s", e)
            instances = []

        for idx, config in enumerate(instances):
            card = self._create_instance_card(config)
            self.cards_layout.addWidget(card, idx // 2, idx % 2)
            self._instance_cards.append(card)

        # 更新计数
        count = len(instances)
        if count == 0:
            self.count_label.setText("暂无实例")
        else:
            self.count_label.setText(f"已有 {count} 个实例")

    # ------------------------------------------------------------------
    # 卡片创建
    # ------------------------------------------------------------------
    def _create_instance_card(self, config) -> QFrame:
        """创建单个实例卡片。"""
        card = QFrame()
        card.setFixedHeight(140)
        card.setStyleSheet(CARD_STYLE)
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        # 第一行：包名 + primary 标记
        top_layout = QHBoxLayout()
        name_label = QLabel(f"资源包: {config.package}")
        name_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #1f2b27;")
        top_layout.addWidget(name_label)
        top_layout.addStretch()

        if getattr(config, "primary", False):
            primary_tag = QLabel("主实例")
            primary_tag.setStyleSheet(PRIMARY_TAG_STYLE)
            top_layout.addWidget(primary_tag)
        layout.addLayout(top_layout)

        # pet_id
        pet_id_label = QLabel(f"ID: {config.pet_id}")
        pet_id_label.setStyleSheet("font-size: 12px; color: #66736e;")
        layout.addWidget(pet_id_label)

        # 位置
        pos = config.position or {"x": 0, "y": 0}
        pos_label = QLabel(f"位置: ({pos.get('x', 0)}, {pos.get('y', 0)})")
        pos_label.setStyleSheet("font-size: 12px; color: #66736e;")
        layout.addWidget(pos_label)

        layout.addStretch()

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        edit_btn = QPushButton("编辑配置")
        edit_btn.setStyleSheet(EDIT_BUTTON_STYLE)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda _, pid=config.pet_id: self._on_edit_clicked(pid))
        btn_layout.addWidget(edit_btn)

        close_btn = QPushButton("关闭此桌宠")
        close_btn.setStyleSheet(CLOSE_BUTTON_STYLE)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(lambda _, pid=config.pet_id: self._on_close_clicked(pid))
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        # 点击卡片本身也触发选中
        card.mousePressEvent = lambda e, pid=config.pet_id: self.instance_selected.emit(pid)

        return card

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------
    def _on_create_clicked(self):
        """点击「创建新实例」按钮。"""
        if self.platform is None:
            QMessageBox.warning(self, "不可用", "平台未就绪，无法创建实例。")
            return

        # 优先通过信号让上层打开资源包选择对话框（宠物库页）
        # 若上层未处理，则使用 platform 中第一个可用包创建
        if self.receivers(self.create_instance_requested) > 0:
            self.create_instance_requested.emit()
            return

        # 兜底：从 platform.pet_packages 选第一个包
        packages = getattr(self.platform, "pet_packages", {}) or {}
        if not packages:
            QMessageBox.warning(self, "无可用资源包", "未找到任何桌宠资源包，请先导入。")
            return

        package_name = next(iter(packages.keys()))
        try:
            pet_id = self.platform.create_instance(package_name)
        except Exception as e:
            logger.error("Failed to create instance: %s", e)
            QMessageBox.critical(self, "创建失败", f"创建实例时出错：{e}")
            return

        self.refresh_instances()
        self.instance_created.emit(pet_id)
        QMessageBox.information(self, "创建成功", f"已创建实例：{pet_id}")

    def _on_edit_clicked(self, pet_id: str):
        """点击「编辑配置」按钮。"""
        self.instance_selected.emit(pet_id)

    def _on_close_clicked(self, pet_id: str):
        """点击「关闭此桌宠」按钮。"""
        reply = QMessageBox.question(
            self, "确认关闭",
            f"确定要关闭桌宠实例 {pet_id} 吗？\n该实例的配置也会从持久化存储中移除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.platform is None:
            return
        try:
            self.platform.destroy_instance(pet_id)
        except Exception as e:
            logger.error("Failed to destroy instance %s: %s", pet_id, e)
            QMessageBox.critical(self, "关闭失败", f"关闭实例时出错：{e}")
            return

        self.refresh_instances()
        self.instance_closed.emit(pet_id)
