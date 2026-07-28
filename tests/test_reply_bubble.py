import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from desktop_pet.pet import ChatBubble, DesktopPet
from desktop_pet.reply_bubble import (
    DEFAULT_REPLY_DURATION_MS,
    ReplyBubbleStack,
    split_reply_sentences,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize(
    "text,expected",
    [
        (
            "\u4f60\u597d\u3002\u771f\u7684\u5417\uff1fYes! Fine;",
            ["\u4f60\u597d\u3002", "\u771f\u7684\u5417\uff1f", "Yes!", "Fine;"],
        ),
        ("Really?! Wow!!!", ["Really?!", "Wow!!!"]),
        (
            "\u7b2c\u4e00\u884c\n\n\u7b2c\u4e8c\u884c\u2026\u2026",
            ["\u7b2c\u4e00\u884c", "\u7b2c\u4e8c\u884c\u2026\u2026"],
        ),
        ("Value 3.14 is fine. Next", ["Value 3.14 is fine.", "Next"]),
        ("one, two: three", ["one, two: three"]),
        ("   \n ", []),
    ],
)
def test_split_reply_sentences(text, expected):
    assert split_reply_sentences(text) == expected


def test_chat_bubble_is_input_only(qapp):
    bubble = ChatBubble()
    try:
        assert not hasattr(bubble, "message_label")
        assert bubble.input_field.placeholderText() == "\u6709\u4ec0\u4e48\u60f3\u8bf4\u7684\uff1f"
    finally:
        bubble.close()


def test_reply_stack_builds_ordered_bubbles_and_replaces_previous(qapp):
    stack = ReplyBubbleStack()
    try:
        assert stack.show_reply("First. Second!", duration_ms=0)
        assert [label.text() for label in stack.bubble_labels] == ["First.", "Second!"]
        assert all(label.height() >= label.sizeHint().height() for label in stack.bubble_labels)
        assert stack.show_reply("Replacement?", duration_ms=0)
        assert [label.text() for label in stack.bubble_labels] == ["Replacement?"]
    finally:
        stack.close()


def test_short_chinese_sentence_stays_on_one_line(qapp):
    stack = ReplyBubbleStack()
    try:
        stack.show_reply("\u4f60", duration_ms=0)
        single_character_height = stack.bubble_labels[0].height()

        stack.show_reply("\u4f60\u597d\u8001\u677f\uff01", duration_ms=0)
        label = stack.bubble_labels[0]
        assert label.height() == single_character_height
    finally:
        stack.close()


class _PositionedWidget:
    def __init__(self, width, height, visible=True):
        self._width = width
        self._height = height
        self._visible = visible
        self._x = 0
        self._y = 0

    def width(self):
        return self._width

    def height(self):
        return self._height

    def isVisible(self):
        return self._visible

    def x(self):
        return self._x

    def y(self):
        return self._y

    def move(self, x, y):
        self._x = x
        self._y = y


class _ScreenManager:
    @staticmethod
    def clamp_to_screen(screen, x, y, width, height):
        geometry = screen.available_geometry
        return (
            max(geometry.x(), min(x, geometry.right() - width + 1)),
            max(geometry.y(), min(y, geometry.bottom() - height + 1)),
        )


def test_reply_stack_is_centered_above_pet_head():
    screen = type("Screen", (), {"available_geometry": QRect(0, 0, 1920, 1080)})()
    pet = type("Pet", (), {})()
    pet.screen_manager = _ScreenManager()
    pet._safe_current_screen_info = lambda: screen
    pet.x = lambda: 100
    pet.y = lambda: 300
    pet.width = lambda: 300
    pet.height = lambda: 180
    pet.label = _PositionedWidget(200, 180)
    pet.reply_bubbles = _PositionedWidget(140, 100)
    pet.chat_bubble = _PositionedWidget(330, 60)

    DesktopPet._position_auxiliary_windows(pet)

    assert (pet.reply_bubbles.x(), pet.reply_bubbles.y()) == (130, 192)
    assert (pet.chat_bubble.x(), pet.chat_bubble.y()) == (35, 124)


def test_reply_stack_constrains_tall_content_for_scrolling(qapp):
    stack = ReplyBubbleStack()
    try:
        text = "\n".join(f"Sentence {index}." for index in range(12))
        stack.show_reply(text, duration_ms=0, max_height=80)
        qapp.processEvents()
        assert len(stack.bubble_labels) == 12
        assert stack.height() == 80
        assert stack.scroll_area.verticalScrollBar().maximum() > 0
    finally:
        stack.close()


def test_reply_stack_uses_default_and_explicit_durations(qapp):
    stack = ReplyBubbleStack()
    try:
        stack.show_reply("Default.")
        assert stack.hide_timer.isActive()
        assert stack.hide_timer.interval() == DEFAULT_REPLY_DURATION_MS

        stack.show_reply("Explicit.", duration_ms=1234)
        assert stack.hide_timer.isActive()
        assert stack.hide_timer.interval() == 1234

        stack.show_reply("Persistent.", duration_ms=0)
        assert not stack.hide_timer.isActive()
    finally:
        stack.close()


def test_new_reply_restarts_timer_and_hide_resets_state(qapp):
    stack = ReplyBubbleStack()
    try:
        stack.show_reply("First.", duration_ms=1000)
        QTest.qWait(30)
        remaining_before = stack.hide_timer.remainingTime()
        stack.show_reply("Second.", duration_ms=1000)
        remaining_after = stack.hide_timer.remainingTime()
        assert remaining_after > remaining_before

        stack.scroll_area.verticalScrollBar().setValue(1)
        stack.hide_reply()
        assert not stack.isVisible()
        assert not stack.hide_timer.isActive()
        assert stack.bubble_labels == []
        assert stack.scroll_area.verticalScrollBar().value() == 0
    finally:
        stack.close()


def test_reply_stack_rejects_invalid_duration(qapp):
    stack = ReplyBubbleStack()
    try:
        with pytest.raises(ValueError, match="duration_ms"):
            stack.show_reply("Invalid.", duration_ms=60001)
    finally:
        stack.close()
