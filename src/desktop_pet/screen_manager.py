"""多屏幕管理模块

集中封装多显示器相关的逻辑：枚举所有屏幕、定位宠物所在屏幕、跨屏边界检测、
相邻屏幕发现、以及显示器热插拔时的宠物位置迁移。
"""
import logging
from dataclasses import dataclass
from PyQt6.QtCore import QObject, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)


@dataclass
class ScreenInfo:
    """单个屏幕的不可变快照"""
    index: int
    name: str
    geometry: QRect                 # 屏幕完整几何(虚拟桌面绝对坐标)
    available_geometry: QRect       # 去掉任务栏后的可用区域
    is_primary: bool

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "x": self.geometry.x(),
            "y": self.geometry.y(),
            "width": self.geometry.width(),
            "height": self.geometry.height(),
            "available": {
                "x": self.available_geometry.x(),
                "y": self.available_geometry.y(),
                "width": self.available_geometry.width(),
                "height": self.available_geometry.height(),
            },
            "primary": self.is_primary,
        }


class ScreenManager(QObject):
    """Platform-wide multi-screen manager keyed by pet_id."""

    screens_changed = pyqtSignal()
    current_screen_changed = pyqtSignal(str, int)

    def __init__(self, app: QApplication):
        super().__init__()
        self._app = app
        self._pets: dict[str, QWidget] = {}
        self._last_screen_indexes: dict[str, int] = {}

        if app is not None:
            app.screenAdded.connect(self._on_screens_changed)
            app.screenRemoved.connect(self._on_screens_changed)
            if hasattr(app, "screensChanged"):
                try:
                    app.screensChanged.connect(self._on_screens_changed)
                except (TypeError, AttributeError):
                    pass

    def register_pet(self, pet_id: str, pet: QWidget) -> None:
        self._pets[pet_id] = pet
        info = self.screen_for_widget(pet)
        if info is not None:
            self._last_screen_indexes[pet_id] = info.index

    def unregister_pet(self, pet_id: str) -> None:
        self._pets.pop(pet_id, None)
        self._last_screen_indexes.pop(pet_id, None)

    # === 屏幕枚举 ===
    def all_screens(self) -> list[ScreenInfo]:
        if self._app is None:
            return []
        screens = self._app.screens()
        primary = self._app.primaryScreen()
        result: list[ScreenInfo] = []
        for i, s in enumerate(screens):
            result.append(ScreenInfo(
                index=i,
                name=s.name(),
                geometry=QRect(s.geometry()),
                available_geometry=QRect(s.availableGeometry()),
                is_primary=(s is primary),
            ))
        return result

    def primary_screen(self) -> ScreenInfo | None:
        screens = self.all_screens()
        for s in screens:
            if s.is_primary:
                return s
        return screens[0] if screens else None

    def screen_by_index(self, index: int) -> ScreenInfo | None:
        screens = self.all_screens()
        if 0 <= index < len(screens):
            return screens[index]
        return None

    def screen_at(self, x: int, y: int) -> ScreenInfo | None:
        """返回包含 (x, y) 的屏幕。

        - 点在某个屏幕几何内:返回该屏幕
        - 点在多屏间隙:返回距离中心最近的屏幕(允许视觉上"贴近"某屏)
        - 点远离所有屏幕(超出 virtual_bounds):返回 None,调用方应触发迁移
        """
        if self._app is None:
            return None
        screens = self._app.screens()
        if not screens:
            return None

        # 先用 Qt 自己的 screenAt
        qscreen = self._app.screenAt(QPoint(x, y))
        if qscreen is not None:
            return self._build_screen_info(qscreen, screens)

        # 点没命中任何屏幕几何
        bounds = self.virtual_bounds()
        if bounds.width() <= 0 or bounds.height() <= 0:
            return None

        # 点是否在虚拟桌面范围内(允许多屏间隙)
        # virtual_bounds 是所有屏的并集,所以"在虚拟桌面内"= 不需要迁移
        if bounds.contains(QPoint(x, y)):
            # 在虚拟桌面内的间隙,返回距离最近的屏幕
            target = QPoint(x, y)
            best: ScreenInfo | None = None
            best_dist = float("inf")
            for info in self.all_screens():
                center = info.geometry.center()
                d = (center.x() - target.x()) ** 2 + (center.y() - target.y()) ** 2
                if d < best_dist:
                    best_dist = d
                    best = info
            return best

        # 远离所有屏幕(热插拔导致)
        return None

    def screen_for_widget(self, widget: QWidget) -> ScreenInfo | None:
        """返回 widget 中心点所在的屏幕。"""
        if widget is None:
            return None
        center = widget.geometry().center()
        return self.screen_at(center.x(), center.y())

    def virtual_bounds(self) -> QRect:
        """所有屏幕几何的并集(虚拟桌面边界)"""
        screens = self.all_screens()
        if not screens:
            return QRect()
        x_min = min(s.geometry.x() for s in screens)
        y_min = min(s.geometry.y() for s in screens)
        x_max = max(s.geometry.right() for s in screens)
        y_max = max(s.geometry.bottom() for s in screens)
        return QRect(x_min, y_min, x_max - x_min + 1, y_max - y_min + 1)

    # === 边界 ===
    def clamp_to_screen(self, screen: ScreenInfo, x: int, y: int,
                        width: int, height: int) -> tuple[int, int]:
        """把矩形 (x, y, w, h) 钳制在给定屏幕的可用区域内"""
        g = screen.available_geometry
        x = max(g.x(), min(x, g.x() + g.width() - width))
        y = max(g.y(), min(y, g.y() + g.height() - height))
        return x, y

    # === 跨屏发现 ===
    def cross_screen_destination(self, current: ScreenInfo, edge: str) -> ScreenInfo | None:
        """在 current 屏的指定方向( left/right )找相邻屏幕。

        判定:目标屏必须在 current 屏该方向的外侧,且垂直方向有重叠(overlap)。
        多块屏匹配时取距离最近的。
        """
        if current is None:
            return None
        cg = current.geometry
        best: ScreenInfo | None = None
        for other in self.all_screens():
            if other.index == current.index:
                continue
            og = other.geometry
            # 垂直方向必须有重叠
            if not (og.y() < cg.bottom() and og.bottom() > cg.y()):
                continue
            if edge == "right":
                # 相邻屏必须在 current 右侧
                if og.x() >= cg.right():
                    if best is None or og.x() < best.geometry.x():
                        best = other
            elif edge == "left":
                # 相邻屏必须在 current 左侧
                if og.right() <= cg.x():
                    if best is None or og.right() > best.geometry.right():
                        best = other
        return best

    def opposite_edge_x(self, screen: ScreenInfo, edge: str, pet_width: int) -> int:
        """给定一个相邻屏,计算从该屏进入后宠物应放置的 x 坐标(从指定边缘进入)"""
        g = screen.available_geometry
        if edge == "right":  # 从左侧进入(从左屏向右跨)
            return g.x()
        if edge == "left":   # 从右侧进入
            return g.x() + g.width() - pet_width
        return g.x()

    # === 状态更新 ===
    def notify_pet_screen(self, pet_id: str, screen_index: int) -> None:
        if self._last_screen_indexes.get(pet_id) != screen_index:
            self._last_screen_indexes[pet_id] = screen_index
            self.current_screen_changed.emit(pet_id, screen_index)

    # === 热插拔处理 ===
    def _on_screens_changed(self, *args) -> None:
        logger.warning("Display topology changed (hot-plug event)")
        QGuiApplication.processEvents()
        available = self.all_screens()
        if not available:
            logger.error("No screens available; pets stay at their current positions")
            self.screens_changed.emit()
            return

        for pet_id, pet in list(self._pets.items()):
            info = self.screen_for_widget(pet)
            if info is not None:
                self.notify_pet_screen(pet_id, info.index)
                continue

            center = pet.geometry().center()
            best = min(
                available,
                key=lambda screen: (
                    (screen.geometry.center().x() - center.x()) ** 2
                    + (screen.geometry.center().y() - center.y()) ** 2
                ),
            )
            geometry = best.available_geometry
            new_x = geometry.x() + max(0, (geometry.width() - pet.width()) // 2)
            new_y = geometry.y() + geometry.height() - pet.height()
            pet.move(new_x, new_y)
            self.notify_pet_screen(pet_id, best.index)
            logger.warning(
                "Pet %s screen disconnected; moved to screen[%s] %s at (%s, %s)",
                pet_id, best.index, best.name, new_x, new_y,
            )

        self.screens_changed.emit()

    # === 内部辅助 ===
    def _build_screen_info(self, qscreen, screens) -> ScreenInfo:
        try:
            idx = screens.index(qscreen)
        except ValueError:
            idx = 0
        primary = self._app.primaryScreen()
        return ScreenInfo(
            index=idx,
            name=qscreen.name(),
            geometry=QRect(qscreen.geometry()),
            available_geometry=QRect(qscreen.availableGeometry()),
            is_primary=(qscreen is primary),
        )
