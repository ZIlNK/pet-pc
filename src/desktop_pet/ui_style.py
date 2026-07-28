"""Shared UI design system for the desktop pet application.

集中管理颜色、字体、间距等设计 tokens，以及各界面共用的 QSS 样式
与阴影/淡入淡出等视觉效果辅助函数。所有 UI 文件应从这里取样式，
避免分散硬编码与复制粘贴。
"""

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsOpacityEffect

# ---------------------------------------------------------------------------
# 设计 tokens
# ---------------------------------------------------------------------------

# 主色（深绿）与强调色（琥珀）
PRIMARY = "#2f7d68"
PRIMARY_HOVER = "#256a58"
PRIMARY_PRESSED = "#1f5a49"
ACCENT = "#f2c572"
ACCENT_TEXT = "#17201d"

# 中性色
DARK = "#17201d"
BG = "#f5f7f4"
CARD = "#ffffff"
BORDER = "#dfe6e1"
INPUT_BORDER = "#cfd8d3"
TEXT = "#24312d"
TEXT_BODY = "#2c3935"
TEXT_HEADING = "#1f2b27"
TEXT_SECONDARY = "#66736e"
TEXT_ON_DARK = "#d9e1df"
TEXT_ON_DARK_DIM = "#9fb0aa"

# 状态色
DANGER = "#c0534a"
DANGER_HOVER = "#a84340"
SUCCESS_BG = "#edf5f1"
SUCCESS_BORDER = "#c6ddd3"

# 字体
FONT_FAMILY = '"Microsoft YaHei UI", "PingFang SC", "Segoe UI", sans-serif'
FONT_SIZE_SMALL = 11
FONT_SIZE_BODY = 13
FONT_SIZE_TITLE = 18
FONT_SIZE_PAGE_TITLE = 24

# 圆角
RADIUS_SMALL = 6
RADIUS = 8
RADIUS_CARD = 12


# ---------------------------------------------------------------------------
# 共享 QSS
# ---------------------------------------------------------------------------

def scrollbar_style() -> str:
    """Thin rounded scrollbar QSS used inside pages and lists."""
    return f"""
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 4px 0 4px 0;
    }}
    QScrollBar::handle:vertical {{
        background: #c6d0cb;
        border-radius: 5px;
        min-height: 32px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #a9b8b1;
    }}
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 0 4px 0 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: #c6d0cb;
        border-radius: 5px;
        min-width: 32px;
    }}
    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
"""


PAGE_STYLE = f"""
    QWidget {{
        background: {BG};
        color: {TEXT};
        font-size: {FONT_SIZE_BODY}px;
    }}
    QLabel {{
        color: {TEXT_BODY};
        background: transparent;
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
{scrollbar_style()}
"""

SECTION_STYLE = f"""
    QGroupBox {{
        background: {CARD};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_CARD}px;
        margin-top: 18px;
        padding: 18px 18px 16px 18px;
        font-size: 15px;
        font-weight: 700;
        color: {TEXT_HEADING};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 8px;
        background: {CARD};
    }}
"""

INPUT_STYLE = f"""
    QLineEdit, QSpinBox, QComboBox, QDoubleSpinBox {{
        min-height: 30px;
        padding: 4px 9px;
        border: 1px solid {INPUT_BORDER};
        border-radius: {RADIUS}px;
        background: #fbfcfa;
        color: {TEXT_HEADING};
        selection-background-color: {ACCENT};
        selection-color: {ACCENT_TEXT};
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {PRIMARY};
        background: {CARD};
    }}
    QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled, QDoubleSpinBox:disabled {{
        background: {BG};
        color: {TEXT_SECONDARY};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background: {CARD};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SMALL}px;
        padding: 4px;
        selection-background-color: {SUCCESS_BG};
        selection-color: {TEXT_HEADING};
        outline: none;
    }}
    QListWidget, QTableWidget {{
        border: 1px solid {INPUT_BORDER};
        border-radius: {RADIUS}px;
        background: #fbfcfa;
        padding: 4px;
        color: {TEXT_HEADING};
        gridline-color: {BORDER};
    }}
    QTableWidget {{
        background: {CARD};
    }}
    QHeaderView::section {{
        background: {BG};
        color: {TEXT_SECONDARY};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 6px 8px;
        font-weight: 600;
    }}
"""

CHECK_STYLE = f"""
    QCheckBox, QRadioButton {{
        spacing: 8px;
        color: {TEXT_BODY};
        font-size: {FONT_SIZE_BODY}px;
        background: transparent;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px;
        height: 16px;
    }}
"""

PRIMARY_BUTTON_STYLE = f"""
    QPushButton {{
        background: {PRIMARY};
        color: #ffffff;
        border: none;
        padding: 9px 22px;
        border-radius: {RADIUS}px;
        font-weight: 700;
    }}
    QPushButton:hover {{
        background: {PRIMARY_HOVER};
    }}
    QPushButton:pressed {{
        background: {PRIMARY_PRESSED};
    }}
    QPushButton:disabled {{
        background: {BORDER};
        color: {TEXT_SECONDARY};
    }}
"""

SECONDARY_BUTTON_STYLE = f"""
    QPushButton {{
        background: {CARD};
        color: {PRIMARY};
        border: 1px solid #b8c8c1;
        padding: 7px 14px;
        border-radius: {RADIUS}px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {SUCCESS_BG};
        border-color: {PRIMARY};
    }}
    QPushButton:disabled {{
        color: {TEXT_SECONDARY};
        border-color: {BORDER};
        background: {BG};
    }}
"""

DANGER_BUTTON_STYLE = f"""
    QPushButton {{
        background: {CARD};
        color: {DANGER};
        border: 1px solid #e0b8b4;
        padding: 7px 14px;
        border-radius: {RADIUS}px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: #faf0ef;
        border-color: {DANGER};
    }}
"""

CARD_STYLE = f"""
    QFrame {{
        background: {CARD};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_CARD}px;
    }}
    QFrame:hover {{
        border-color: {PRIMARY};
    }}
"""

STATUS_STYLE = f"""
    QLabel {{
        background: {SUCCESS_BG};
        border: 1px solid {SUCCESS_BORDER};
        border-radius: {RADIUS}px;
        padding: 6px 10px;
        color: {PRIMARY_HOVER};
        font-weight: 700;
    }}
"""

NAV_BUTTON_STYLE = f"""
    QPushButton {{
        text-align: left;
        padding: 11px 14px;
        border: none;
        background: transparent;
        font-size: 14px;
        color: {TEXT_ON_DARK};
        border-radius: {RADIUS}px;
        font-weight: 500;
    }}
    QPushButton:checked {{
        background: {ACCENT};
        color: {ACCENT_TEXT};
        font-weight: 700;
    }}
    QPushButton:hover:!checked {{
        background: rgba(255,255,255,0.08);
        color: #ffffff;
    }}
    QPushButton:disabled {{
        color: rgba(217,225,223,0.35);
    }}
"""

CHAT_INPUT_CONTAINER_STYLE = f"""
    QWidget#chatBubbleContainer {{
        background: {CARD};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_CARD}px;
    }}
"""

INLINE_CLOSE_BUTTON_STYLE = f"""
    QPushButton {{
        background: transparent;
        border: none;
        border-radius: 10px;
        color: {TEXT_SECONDARY};
        font-size: 14px;
        font-weight: 700;
        padding: 0;
    }}
    QPushButton:hover {{
        background: {BORDER};
        color: {TEXT_BODY};
    }}
"""

REPLY_BUBBLE_STYLE = f"""
    QLabel {{
        background: {SUCCESS_BG};
        border: 1px solid {SUCCESS_BORDER};
        border-radius: {RADIUS_CARD}px;
        padding: 8px 12px;
        color: {TEXT_BODY};
        font-size: {FONT_SIZE_BODY}px;
    }}
"""

REPLY_SCROLL_AREA_STYLE = f"""
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
{scrollbar_style()}
"""


MENU_STYLE = f"""
    QMenu {{
        background: {CARD};
        border: 1px solid {BORDER};
        border-radius: {RADIUS}px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 28px 7px 16px;
        border-radius: {RADIUS_SMALL}px;
        color: {TEXT_BODY};
    }}
    QMenu::item:selected {{
        background: {SUCCESS_BG};
        color: {TEXT_HEADING};
    }}
    QMenu::item:disabled {{
        color: {TEXT_SECONDARY};
    }}
    QMenu::separator {{
        height: 1px;
        background: {BORDER};
        margin: 5px 10px;
    }}
"""

TAB_STYLE = f"""
    QTabWidget::pane {{
        border: 1px solid {BORDER};
        border-radius: {RADIUS}px;
        background: {CARD};
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {TEXT_SECONDARY};
        padding: 8px 18px;
        border: none;
        border-bottom: 2px solid transparent;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        color: {PRIMARY};
        border-bottom: 2px solid {PRIMARY};
    }}
    QTabBar::tab:hover:!selected {{
        color: {TEXT_HEADING};
    }}
"""


def title_style(size: int = FONT_SIZE_PAGE_TITLE) -> str:
    """Inline QSS for a page title label."""
    return f"font-size: {size}px; font-weight: 700; color: {TEXT_HEADING}; background: transparent;"


def subtitle_style() -> str:
    """Inline QSS for secondary/descriptive text."""
    return f"color: {TEXT_SECONDARY}; background: transparent;"


def form_stylesheet() -> str:
    """Combined stylesheet for form-heavy pages and dialogs."""
    return SECTION_STYLE + INPUT_STYLE + CHECK_STYLE + TAB_STYLE


def global_app_stylesheet() -> str:
    """Application-wide QSS: menus, message boxes, tooltips, scrollbars."""
    return f"""
    QToolTip {{
        background: {DARK};
        color: #ffffff;
        border: none;
        border-radius: {RADIUS_SMALL}px;
        padding: 6px 10px;
        font-size: {FONT_SIZE_SMALL}px;
    }}
    QMessageBox {{
        background: {BG};
    }}
    QMessageBox QLabel {{
        color: {TEXT_BODY};
        font-size: {FONT_SIZE_BODY}px;
    }}
{MENU_STYLE}
{scrollbar_style()}
"""


# ---------------------------------------------------------------------------
# 视觉效果辅助
# ---------------------------------------------------------------------------

def apply_shadow(widget, blur: int = 24, y_offset: int = 4,
                 color=QColor(23, 32, 29, 60)) -> QGraphicsDropShadowEffect:
    """Attach a soft drop shadow to a widget and return the effect."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setXOffset(0)
    shadow.setYOffset(y_offset)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)
    return shadow


def _fade(widget, start: float, end: float, duration: int,
          on_finished=None) -> QPropertyAnimation:
    """Animate opacity for a top-level window (windowOpacity) or child widget."""
    if widget.isWindow():
        widget.setWindowOpacity(start)
        anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    else:
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
        effect.setOpacity(start)
        anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    if on_finished is not None:
        anim.finished.connect(on_finished)
    # 防止动画对象被 GC
    widget._ui_fade_animation = anim
    anim.start()
    return anim


def fade_in(widget, duration: int = 180) -> QPropertyAnimation:
    """Fade a widget in (assumes it is about to be / has just been shown)."""
    return _fade(widget, 0.0, 1.0, duration)


def fade_out(widget, duration: int = 150, on_finished=None) -> QPropertyAnimation:
    """Fade a widget out, then hide it (unless ``on_finished`` overrides)."""
    def _hide():
        widget.hide()
        # 还原不透明度，避免下次 show 时闪一下透明状态
        if widget.isWindow():
            widget.setWindowOpacity(1.0)
        else:
            effect = widget.graphicsEffect()
            if isinstance(effect, QGraphicsOpacityEffect):
                effect.setOpacity(1.0)

    return _fade(widget, 1.0, 0.0, duration, on_finished or _hide)
