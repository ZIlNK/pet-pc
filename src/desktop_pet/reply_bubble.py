"""Sentence-based reply bubbles displayed beside a desktop pet."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .ui_style import REPLY_BUBBLE_STYLE, REPLY_SCROLL_AREA_STYLE, fade_in, fade_out

DEFAULT_REPLY_DURATION_MS = 10000
MAX_REPLY_DURATION_MS = 60000
MAX_BUBBLE_WIDTH = 290
MAX_STACK_WIDTH = 320
MAX_STACK_HEIGHT = 420
BUBBLE_SPACING = 6
STACK_MARGIN = 8

_SENTENCE_ENDINGS = frozenset("\u3002\uff01\uff1f!?\uff1b;.\u2026")


def split_reply_sentences(text: str) -> list[str]:
    """Split reply text at sentence-ending punctuation while preserving it."""
    if not isinstance(text, str):
        return []

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    sentences: list[str] = []
    buffer: list[str] = []
    index = 0

    def flush() -> None:
        sentence = "".join(buffer).strip()
        buffer.clear()
        if sentence:
            sentences.append(sentence)

    while index < len(normalized):
        char = normalized[index]
        if char == "\n":
            flush()
            index += 1
            continue

        buffer.append(char)
        is_decimal_point = (
            char == "."
            and index > 0
            and index + 1 < len(normalized)
            and normalized[index - 1].isdigit()
            and normalized[index + 1].isdigit()
        )
        if char not in _SENTENCE_ENDINGS or is_decimal_point:
            index += 1
            continue

        index += 1
        while index < len(normalized):
            next_char = normalized[index]
            if next_char not in _SENTENCE_ENDINGS:
                break
            buffer.append(next_char)
            index += 1
        flush()

    flush()
    return sentences


class ReplyBubbleStack(QWidget):
    """Top-level stack of sentence bubbles with one shared auto-hide timer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(STACK_MARGIN, STACK_MARGIN, STACK_MARGIN, STACK_MARGIN)
        outer_layout.setSpacing(0)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setStyleSheet(REPLY_SCROLL_AREA_STYLE)
        outer_layout.addWidget(self.scroll_area)

        self.content = QWidget()
        self.content.setObjectName("replyBubbleContent")
        self.bubble_layout = QVBoxLayout(self.content)
        self.bubble_layout.setContentsMargins(0, 0, 0, 0)
        self.bubble_layout.setSpacing(BUBBLE_SPACING)
        self.bubble_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.scroll_area.setWidget(self.content)

        self.bubble_labels: list[QLabel] = []
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_auto_hide)
        self.hide()

    @property
    def hide_timer(self) -> QTimer:
        """Expose the shared timer for diagnostics and focused UI tests."""
        return self._hide_timer

    def show_reply(
        self,
        text: str,
        duration_ms: int = DEFAULT_REPLY_DURATION_MS,
        max_height: int = MAX_STACK_HEIGHT,
    ) -> bool:
        sentences = split_reply_sentences(text)
        if not sentences:
            self.hide_reply()
            return False
        if type(duration_ms) is not int or not 0 <= duration_ms <= MAX_REPLY_DURATION_MS:
            raise ValueError("duration_ms must be an integer between 0 and 60000")

        self._stop_transitions()
        self._clear_bubbles()
        self.scroll_area.verticalScrollBar().setValue(0)

        widest = 0
        content_height = 0
        for sentence in sentences:
            label = self._create_bubble(sentence)
            self.bubble_layout.addWidget(label, 0, Qt.AlignmentFlag.AlignLeft)
            self.bubble_labels.append(label)
            widest = max(widest, label.width())
            content_height += label.height()

        content_height += BUBBLE_SPACING * max(0, len(self.bubble_labels) - 1)
        stack_height_limit = max(2 * STACK_MARGIN + 1, min(MAX_STACK_HEIGHT, int(max_height)))
        viewport_height_limit = stack_height_limit - 2 * STACK_MARGIN
        viewport_height = min(content_height, viewport_height_limit)
        viewport_width = min(MAX_STACK_WIDTH - 2 * STACK_MARGIN, widest + 12)
        if content_height > viewport_height_limit:
            viewport_width = min(MAX_STACK_WIDTH - 2 * STACK_MARGIN, viewport_width + 10)

        self.scroll_area.setFixedSize(max(1, viewport_width), max(1, viewport_height))
        self.setFixedSize(
            self.scroll_area.width() + 2 * STACK_MARGIN,
            self.scroll_area.height() + 2 * STACK_MARGIN,
        )
        self.show()
        self.raise_()
        fade_in(self)
        if duration_ms > 0:
            self._hide_timer.start(duration_ms)
        return True

    def hide_reply(self) -> None:
        """Immediately hide and reset the stack."""
        self._stop_transitions()
        self._finish_hide()

    def _create_bubble(self, text: str) -> QLabel:
        label = QLabel(text, self.content)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        label.setStyleSheet(REPLY_BUBBLE_STYLE)

        label.ensurePolished()
        metrics = QFontMetrics(label.font())
        natural_width = max(64, metrics.horizontalAdvance(text) + 34)
        label.setWordWrap(natural_width > MAX_BUBBLE_WIDTH)
        width = min(MAX_BUBBLE_WIDTH, natural_width)
        label.setFixedWidth(width)
        label.setFixedHeight(max(36, label.sizeHint().height()))
        return label

    def _start_auto_hide(self) -> None:
        if not self.isVisible():
            return
        fade_out(self, on_finished=self._finish_hide)

    def _stop_transitions(self) -> None:
        self._hide_timer.stop()
        animation = getattr(self, "_ui_fade_animation", None)
        if animation is not None:
            animation.stop()
        self.setWindowOpacity(1.0)

    def _finish_hide(self) -> None:
        self.hide()
        self.setWindowOpacity(1.0)
        self._clear_bubbles()
        self.scroll_area.verticalScrollBar().setValue(0)

    def _clear_bubbles(self) -> None:
        while self.bubble_layout.count():
            item = self.bubble_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.bubble_labels.clear()

    def sizeHint(self) -> QSize:
        return self.size()
