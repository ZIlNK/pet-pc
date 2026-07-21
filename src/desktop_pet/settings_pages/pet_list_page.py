"""Pet list page for Settings Center."""

import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGridLayout, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QMovie

logger = logging.getLogger(__name__)


ANIMATED_PREVIEW_SUFFIXES = {".gif", ".webp", ".apng"}


def resolve_pet_preview_path(pet_package) -> Path | None:
    animations_dir = pet_package.animations_dir
    for filename in (pet_package.meta.preview, pet_package.meta.regular_image):
        if not filename:
            continue
        preview_path = animations_dir / filename
        if preview_path.exists():
            return preview_path
    return None


PRIMARY_BUTTON_STYLE = """
    QPushButton {
        background: #2f7d68;
        color: #ffffff;
        border: none;
        padding: 6px 12px;
        border-radius: 4px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: #256a58;
    }
    QPushButton:disabled {
        background: #cfd8d3;
        color: #f5f7f4;
    }
"""

SECONDARY_BUTTON_STYLE = """
    QPushButton {
        background: white;
        color: #2f7d68;
        border: 1px solid #2f7d68;
        padding: 6px 12px;
        border-radius: 4px;
    }
    QPushButton:hover {
        background: #edf5f1;
    }
    QPushButton:disabled {
        color: #cfd8d3;
        border-color: #cfd8d3;
        background: #f5f7f4;
    }
"""

CARD_STYLE = """
    QFrame {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 12px;
    }
    QFrame:hover {
        border-color: #2f7d68;
        background: #fafafa;
    }
"""


class PetListPage(QWidget):
    """Page displaying list of available pets as cards."""

    # Signals
    pet_selected = pyqtSignal(object)  # PetPackage
    new_pet_requested = pyqtSignal()
    import_requested = pyqtSignal()
    # 实例创建成功后发出，携带 pet_id（仅 platform 模式下有效）
    instance_created = pyqtSignal(str)

    def __init__(self, config_manager, pet_loader, platform=None, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.pet_loader = pet_loader
        self.platform = platform
        self.pets = []
        self.pet_cards = []
        self.preview_movies = []

        self.setup_ui()
        self.refresh_pets()

    def setup_ui(self):
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        header = QLabel("您的桌宠")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #333;")
        header_layout.addWidget(header)
        header_layout.addStretch()

        # 实例计数标签（仅 platform 模式下显示）
        self.instance_count_label = QLabel("")
        self.instance_count_label.setStyleSheet(
            "font-size: 13px; color: #2f7d68; font-weight: 600;"
        )
        header_layout.addWidget(self.instance_count_label)
        layout.addLayout(header_layout)

        # Scroll area for pet cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none;")

        self.cards_container = QWidget()
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setSpacing(15)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(self.cards_container)
        layout.addWidget(scroll)

    def refresh_pets(self):
        """Refresh the pet list."""
        self.pets = self.pet_loader.scan_pets()
        self._render_pet_cards()
        self._refresh_instance_count()

    def _refresh_instance_count(self):
        """刷新已运行实例计数显示。"""
        if self.platform is None:
            self.instance_count_label.setText("")
            return
        try:
            instances = self.platform.list_instances()
        except Exception as e:
            logger.warning(f"Failed to list instances: {e}")
            self.instance_count_label.setText("")
            return
        count = len(instances)
        if count > 0:
            self.instance_count_label.setText(f"已有 {count} 个实例")
        else:
            self.instance_count_label.setText("")

    def _render_pet_cards(self):
        """Render pet cards in grid."""
        # Clear existing cards
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.pet_cards.clear()
        for movie in self.preview_movies:
            movie.stop()
        self.preview_movies.clear()

        # Pet cards
        col = 0
        for pet in self.pets:
            card = self._create_pet_card(pet)
            self.cards_layout.addWidget(card, 0, col)
            self.pet_cards.append(card)
            col += 1

        # New pet card
        new_card = self._create_new_pet_card()
        self.cards_layout.addWidget(new_card, 0, col)

        # Import card
        import_card = self._create_import_card()
        self.cards_layout.addWidget(import_card, 0, col + 1)

    def _create_pet_card(self, pet_package) -> QFrame:
        """Create a pet card widget。每张卡片包含预览与「创建实例」按钮。"""
        card = QFrame()
        card.setFixedSize(180, 230)
        card.setStyleSheet(CARD_STYLE)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(5)

        # Preview
        preview = QLabel()
        preview.setFixedHeight(90)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet("background: #f5f5f5; border-radius: 8px;")

        # Try to load preview media, falling back to the regular pet image.
        try:
            preview_file = resolve_pet_preview_path(pet_package)
            if preview_file and preview_file.suffix.lower() in ANIMATED_PREVIEW_SUFFIXES:
                movie = QMovie(str(preview_file))
                movie.setScaledSize(preview.size())
                if movie.isValid():
                    preview.setMovie(movie)
                    movie.start()
                    self.preview_movies.append(movie)
                else:
                    preview.setText("预览不可用")
                    preview.setStyleSheet("background: #f5f5f5; border-radius: 8px; color: #888;")
            elif preview_file:
                pixmap = QPixmap(str(preview_file))
                scaled = pixmap.scaled(
                    80, 80,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                preview.setPixmap(scaled)
            else:
                preview.setText("预览不可用")
                preview.setStyleSheet("background: #f5f5f5; border-radius: 8px; color: #888;")
        except Exception as e:
            logger.warning(f"Failed to load pet preview for {pet_package.name}: {e}")
            preview.setText("预览不可用")
            preview.setStyleSheet("background: #f5f5f5; border-radius: 8px; color: #888;")

        layout.addWidget(preview)

        # Name
        name = QLabel(pet_package.meta.name)
        name.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        layout.addWidget(name)

        # Author
        author = QLabel(f"作者: {pet_package.meta.author}")
        author.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(author)

        layout.addStretch()

        # 「创建实例」按钮：platform 为 None 时禁用
        create_btn = QPushButton("创建实例")
        create_btn.setEnabled(self.platform is not None)
        if self.platform is not None:
            create_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        else:
            create_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(lambda: self._create_instance_for(pet_package))
        layout.addWidget(create_btn)

        # 整张卡片点击：选中（用于查看详情）
        card.mousePressEvent = lambda e: self.pet_selected.emit(pet_package)
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        return card

    def _create_new_pet_card(self) -> QFrame:
        """Create new pet card."""
        card = QFrame()
        card.setFixedSize(180, 230)
        card.setStyleSheet("""
            QFrame {
                background: #f8f8f8;
                border: 2px dashed #ccc;
                border-radius: 12px;
            }
            QFrame:hover {
                border-color: #2f7d68;
                background: #e8f4fc;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)

        # Plus icon
        plus = QLabel("+")
        plus.setAlignment(Qt.AlignmentFlag.AlignCenter)
        plus.setStyleSheet("font-size: 48px; color: #888; margin-top: 20px;")
        layout.addWidget(plus)

        text = QLabel("新建桌宠")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setStyleSheet("color: #666; font-size: 13px;")
        layout.addWidget(text)

        layout.addStretch()

        # Make clickable
        card.mousePressEvent = lambda e: self.new_pet_requested.emit()
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        return card

    def _create_import_card(self) -> QFrame:
        """Create import card."""
        card = QFrame()
        card.setFixedSize(180, 230)
        card.setStyleSheet("""
            QFrame {
                background: #f8f8f8;
                border: 2px dashed #ccc;
                border-radius: 12px;
            }
            QFrame:hover {
                border-color: #2f7d68;
                background: #e8f4fc;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)

        # Import icon
        icon = QLabel("📦")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 36px; margin-top: 20px;")
        layout.addWidget(icon)

        text = QLabel("导入")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setStyleSheet("color: #666; font-size: 13px;")
        layout.addWidget(text)

        layout.addStretch()

        # Make clickable
        card.mousePressEvent = lambda e: self.import_requested.emit()
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        return card

    def _create_instance_for(self, pet_package):
        """点击「创建实例」按钮：通过 platform 创建实例并发出信号。"""
        if self.platform is None:
            return
        try:
            pet_id = self.platform.create_instance(pet_package.name)
        except Exception as e:
            logger.error(f"Failed to create instance for {pet_package.name}: {e}")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "创建失败", f"创建实例时出错：{e}")
            return
        self._refresh_instance_count()
        self.instance_created.emit(pet_id)
