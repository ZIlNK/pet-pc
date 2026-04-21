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


class PetListPage(QWidget):
    """Page displaying list of available pets as cards."""

    # Signals
    pet_selected = pyqtSignal(object)  # PetPackage
    new_pet_requested = pyqtSignal()
    import_requested = pyqtSignal()

    def __init__(self, config_manager, pet_loader, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.pet_loader = pet_loader
        self.pets = []
        self.pet_cards = []

        self.setup_ui()
        self.refresh_pets()

    def setup_ui(self):
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header = QLabel("您的桌宠")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #333;")
        layout.addWidget(header)

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

    def _render_pet_cards(self):
        """Render pet cards in grid."""
        # Clear existing cards
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.pet_cards.clear()

        current_pet = self.config_manager.get_current_pet_name()

        # Pet cards
        col = 0
        for pet in self.pets:
            card = self._create_pet_card(pet, pet.name == current_pet)
            self.cards_layout.addWidget(card, 0, col)
            self.pet_cards.append(card)
            col += 1

        # New pet card
        new_card = self._create_new_pet_card()
        self.cards_layout.addWidget(new_card, 0, col)

        # Import card
        import_card = self._create_import_card()
        self.cards_layout.addWidget(import_card, 0, col + 1)

    def _create_pet_card(self, pet_package, is_current=False) -> QFrame:
        """Create a pet card widget."""
        card = QFrame()
        card.setFixedSize(180, 230)
        card.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
            }
            QFrame:hover {
                border-color: #0078d4;
                background: #fafafa;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(5)

        # Preview
        preview = QLabel()
        preview.setFixedHeight(90)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet("background: #f5f5f5; border-radius: 8px;")

        # Try to load preview image
        try:
            animations_dir = pet_package.animations_dir
            preview_file = animations_dir / pet_package.meta.preview
            if preview_file.exists():
                pixmap = QPixmap(str(preview_file))
                scaled = pixmap.scaled(
                    80, 80,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                preview.setPixmap(scaled)
            else:
                preview.setText("预览")
                preview.setStyleSheet("background: #f5f5f5; border-radius: 8px; color: #888;")
        except Exception as e:
            preview.setText("预览")
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

        # Current tag or switch button
        if is_current:
            current_label = QLabel("当前使用")
            current_label.setStyleSheet("""
                background: #0078d4;
                color: white;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
            """)
            current_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(current_label)

            config_btn = QPushButton("配置")
            config_btn.setStyleSheet("""
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
            """)
            config_btn.clicked.connect(lambda: self.pet_selected.emit(pet_package))
            layout.addWidget(config_btn)
        else:
            switch_btn = QPushButton("切换使用")
            switch_btn.setStyleSheet("""
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
            switch_btn.clicked.connect(lambda: self._switch_to_pet(pet_package))
            layout.addWidget(switch_btn)

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
                border-color: #0078d4;
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
                border-color: #0078d4;
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

    def _switch_to_pet(self, pet_package):
        """Switch to a different pet."""
        self.config_manager.set_current_pet(pet_package.name)
        self.refresh_pets()
