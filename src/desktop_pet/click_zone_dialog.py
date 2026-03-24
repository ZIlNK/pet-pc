from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QComboBox, QSpinBox, QFormLayout, QGroupBox,
    QMessageBox, QAbstractItemView, QDialogButtonBox, QSizePolicy, QWidget
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QMovie

from .config_manager import ClickZoneConfig


class ClickZoneOverlay(QWidget):
    """可拖动的区域覆盖层，同时显示宠物图像"""

    zone_changed = pyqtSignal(int, dict)

    def __init__(self, parent=None, zones=None, image_size=None):
        super().__init__(parent)
        self.zones = zones or []
        self.image_size = image_size or (200, 159)
        self.selected_zone = -1
        self.is_dragging = False
        self.is_resizing = False
        self.resize_handle = -1
        self.drag_start = QPointF()
        self.zone_start_rect = QRectF()
        self.setMinimumSize(*self.image_size)
        self.setMaximumSize(*self.image_size)
        self.setMouseTracking(True)

        self.pixmap: QPixmap | None = None

        self.colors = [
            QColor(255, 0, 0, 100),
            QColor(0, 255, 0, 100),
            QColor(0, 0, 255, 100),
            QColor(255, 255, 0, 100),
            QColor(255, 0, 255, 100),
            QColor(0, 255, 255, 100),
            QColor(128, 0, 128, 100),
            QColor(255, 165, 0, 100),
        ]

    def setPixmap(self, pixmap: QPixmap):
        """设置要显示的图像"""
        self.pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 先绘制背景图像
        if self.pixmap and not self.pixmap.isNull():
            painter.drawPixmap(0, 0, self.pixmap.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

        # 再绘制选择区域
        for i, zone in enumerate(self.zones):
            x = zone.x * self.width()
            y = zone.y * self.height()
            w = zone.width * self.width()
            h = zone.height * self.height()

            rect = QRectF(x, y, w, h)

            if i == self.selected_zone:
                color = self.colors[i % len(self.colors)]
                fill_color = QColor(color.red(), color.green(), color.blue(), 150)
                painter.setBrush(QBrush(fill_color))
                painter.setPen(QPen(QColor(255, 255, 255), 2))
            else:
                color = self.colors[i % len(self.colors)]
                fill_color = QColor(color.red(), color.green(), color.blue(), 80)
                painter.setBrush(QBrush(fill_color))
                painter.setPen(QPen(color, 2))

            painter.drawRect(rect)

            if i == self.selected_zone:
                self.draw_resize_handles(painter, rect)

            text_rect = QRectF(rect)
            text_rect.setHeight(20)
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, zone.name)

    def draw_resize_handles(self, painter, rect):
        handle_size = 8
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(QPen(QColor(0, 0, 0), 1))

        handles = [
            QPointF(rect.left(), rect.top()),
            QPointF(rect.center().x(), rect.top()),
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right(), rect.center().y()),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.center().x(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()),
            QPointF(rect.left(), rect.center().y()),
        ]

        for hp in handles:
            painter.drawRect(
                QRectF(
                    hp.x() - handle_size / 2,
                    hp.y() - handle_size / 2,
                    handle_size,
                    handle_size
                )
            )

    def get_resize_handle_at(self, pos):
        if self.selected_zone < 0 or self.selected_zone >= len(self.zones):
            return -1

        zone = self.zones[self.selected_zone]
        x = zone.x * self.width()
        y = zone.y * self.height()
        w = zone.width * self.width()
        h = zone.height * self.height()
        rect = QRectF(x, y, w, h)

        handle_size = 10
        handles = [
            QPointF(rect.left(), rect.top()),
            QPointF(rect.center().x(), rect.top()),
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right(), rect.center().y()),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.center().x(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()),
            QPointF(rect.left(), rect.center().y()),
        ]

        for i, hp in enumerate(handles):
            handle_rect = QRectF(
                hp.x() - handle_size,
                hp.y() - handle_size,
                handle_size * 2,
                handle_size * 2
            )
            if handle_rect.contains(pos):
                return i

        return -1

    def mousePressEvent(self, event):
        pos = event.position()

        if event.button() == Qt.MouseButton.LeftButton:
            self.resize_handle = self.get_resize_handle_at(pos)

            if self.resize_handle >= 0:
                self.is_resizing = True
            else:
                for i, zone in enumerate(self.zones):
                    x = zone.x * self.width()
                    y = zone.y * self.height()
                    w = zone.width * self.width()
                    h = zone.height * self.height()
                    rect = QRectF(x, y, w, h)

                    if rect.contains(pos):
                        self.selected_zone = i
                        self.is_dragging = True
                        self.zone_start_rect = QRectF(x, y, w, h)
                        self.zone_changed.emit(i, self.get_zone_data(i))
                        break
                else:
                    self.selected_zone = -1

            self.drag_start = pos
            self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()

        if self.is_resizing and self.selected_zone >= 0:
            self.apply_resize(pos)
        elif self.is_dragging and self.selected_zone >= 0:
            self.apply_drag(pos)
        else:
            handle = self.get_resize_handle_at(pos)
            if handle >= 0:
                cursors = [
                    Qt.CursorShape.SizeAllCursor,
                    Qt.CursorShape.SizeVerCursor,
                    Qt.CursorShape.SizeAllCursor,
                    Qt.CursorShape.SizeHorCursor,
                    Qt.CursorShape.SizeAllCursor,
                    Qt.CursorShape.SizeVerCursor,
                    Qt.CursorShape.SizeAllCursor,
                    Qt.CursorShape.SizeHorCursor,
                ]
                self.setCursor(cursors[handle])
            else:
                zone_under_mouse = -1
                for i, zone in enumerate(self.zones):
                    x = zone.x * self.width()
                    y = zone.y * self.height()
                    w = zone.width * self.width()
                    h = zone.height * self.height()
                    rect = QRectF(x, y, w, h)
                    if rect.contains(pos):
                        zone_under_mouse = i
                        break

                if zone_under_mouse >= 0:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)

    def apply_drag(self, pos):
        if self.selected_zone < 0:
            return

        zone = self.zones[self.selected_zone]

        dx = (pos.x() - self.drag_start.x()) / self.width()
        dy = (pos.y() - self.drag_start.y()) / self.height()

        new_x = max(0, min(1 - zone.width, self.zone_start_rect.left() / self.width() + dx))
        new_y = max(0, min(1 - zone.height, self.zone_start_rect.top() / self.height() + dy))

        zone.x = new_x
        zone.y = new_y

        self.zone_changed.emit(self.selected_zone, self.get_zone_data(self.selected_zone))
        self.update()

    def apply_resize(self, pos):
        if self.selected_zone < 0:
            return

        zone = self.zones[self.selected_zone]

        x = zone.x * self.width()
        y = zone.y * self.height()
        w = zone.width * self.width()
        h = zone.height * self.height()

        start_x = self.zone_start_rect.left()
        start_y = self.zone_start_rect.top()
        start_w = self.zone_start_rect.width()
        start_h = self.zone_start_rect.height()

        dx = pos.x() - self.drag_start.x()
        dy = pos.y() - self.drag_start.y()

        min_size = 10

        if self.resize_handle == 0:
            new_x = start_x + dx
            new_w = start_w - dx
            new_y = start_y + dy
            new_h = start_h - dy
        elif self.resize_handle == 1:
            new_x = start_x
            new_w = start_w
            new_y = start_y + dy
            new_h = start_h - dy
        elif self.resize_handle == 2:
            new_x = start_x
            new_w = start_w + dx
            new_y = start_y + dy
            new_h = start_h - dy
        elif self.resize_handle == 3:
            new_x = start_x
            new_w = start_w + dx
            new_y = start_y
            new_h = start_h
        elif self.resize_handle == 4:
            new_x = start_x
            new_w = start_w + dx
            new_y = start_y
            new_h = start_h + dy
        elif self.resize_handle == 5:
            new_x = start_x
            new_w = start_w
            new_y = start_y
            new_h = start_h + dy
        elif self.resize_handle == 6:
            new_x = start_x + dx
            new_w = start_w - dx
            new_y = start_y
            new_h = start_h + dy
        else:
            new_x = start_x
            new_w = start_w
            new_y = start_y
            new_h = start_h

        if new_w < min_size:
            if self.resize_handle in [0, 6]:
                new_x = start_x + start_w - min_size
            new_w = min_size
        if new_h < min_size:
            if self.resize_handle in [0, 1, 2]:
                new_y = start_y + start_h - min_size
            new_h = min_size

        new_x = max(0, min(self.width() - new_w, new_x))
        new_y = max(0, min(self.height() - new_h, new_y))
        new_w = min(new_w, self.width() - new_x)
        new_h = min(new_h, self.height() - new_y)

        zone.x = new_x / self.width()
        zone.y = new_y / self.height()
        zone.width = new_w / self.width()
        zone.height = new_h / self.height()

        self.zone_changed.emit(self.selected_zone, self.get_zone_data(self.selected_zone))
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            self.is_resizing = False
            self.resize_handle = -1
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def get_zone_data(self, index):
        if index < 0 or index >= len(self.zones):
            return {}
        zone = self.zones[index]
        return {
            "name": zone.name,
            "x": zone.x,
            "y": zone.y,
            "width": zone.width,
            "height": zone.height,
            "action": zone.action
        }

    def update_zone(self, index, data):
        if index < 0 or index >= len(self.zones):
            return
        zone = self.zones[index]
        if "name" in data:
            zone.name = data["name"]
        if "x" in data:
            zone.x = data["x"]
        if "y" in data:
            zone.y = data["y"]
        if "width" in data:
            zone.width = data["width"]
        if "height" in data:
            zone.height = data["height"]
        if "action" in data:
            zone.action = data["action"]
        self.update()

    def set_selected_zone(self, index):
        self.selected_zone = index
        self.update()

    def add_zone(self, zone):
        self.zones.append(zone)
        self.update()

    def remove_zone(self, index):
        if 0 <= index < len(self.zones):
            del self.zones[index]
            if self.selected_zone >= len(self.zones):
                self.selected_zone = len(self.zones) - 1 if self.zones else -1
            self.update()


class ClickZoneConfigDialog(QDialog):
    """点击区域配置对话框"""

    def __init__(self, pet_package, config_manager=None, parent=None):
        super().__init__(parent)
        self.pet_package = pet_package
        self.config_manager = config_manager
        self.zones = []
        self.image_size = (200, 159)
        self.setup_ui()
        self.load_current_zones()

    def setup_ui(self):
        self.setWindowTitle("点击区域配置")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)

        main_layout = QHBoxLayout(self)

        left_group = QGroupBox("宠物图像")
        left_layout = QVBoxLayout(left_group)

        self.overlay = ClickZoneOverlay(zones=self.zones, image_size=self.image_size)
        self.overlay.zone_changed.connect(self.on_zone_changed)
        self.overlay.setStyleSheet("border: 1px solid #ccc; background-color: #f0f0f0;")

        overlay_container = QHBoxLayout()
        overlay_container.addStretch()
        overlay_container.addWidget(self.overlay)
        overlay_container.addStretch()

        self.load_pet_image()

        left_layout.addLayout(overlay_container)

        main_layout.addWidget(left_group, 1)

        right_group = QGroupBox("区域列表")
        right_layout = QVBoxLayout(right_group)

        self.zone_list = QListWidget()
        self.zone_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.zone_list.currentRowChanged.connect(self.on_zone_list_selection_changed)
        right_layout.addWidget(self.zone_list)

        list_btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加区域")
        add_btn.clicked.connect(self.add_zone)
        list_btn_layout.addWidget(add_btn)

        delete_btn = QPushButton("删除区域")
        delete_btn.clicked.connect(self.delete_zone)
        list_btn_layout.addWidget(delete_btn)
        right_layout.addLayout(list_btn_layout)

        self.edit_group = QGroupBox("区域属性")
        self.edit_group.setEnabled(False)
        edit_layout = QFormLayout(self.edit_group)

        self.name_edit = QSpinBox()
        self.name_edit.setRange(1, 100)
        self.name_edit.valueChanged.connect(self.on_zone_property_changed)
        edit_layout.addRow("区域编号:", self.name_edit)

        self.action_combo = QComboBox()
        self.action_combo.currentIndexChanged.connect(self.on_zone_property_changed)
        edit_layout.addRow("对应动作:", self.action_combo)

        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 100)
        self.x_spin.setSuffix(" %")
        self.x_spin.valueChanged.connect(self.on_zone_property_changed)
        edit_layout.addRow("X 位置:", self.x_spin)

        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, 100)
        self.y_spin.setSuffix(" %")
        self.y_spin.valueChanged.connect(self.on_zone_property_changed)
        edit_layout.addRow("Y 位置:", self.y_spin)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 100)
        self.width_spin.setSuffix(" %")
        self.width_spin.valueChanged.connect(self.on_zone_property_changed)
        edit_layout.addRow("宽度:", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 100)
        self.height_spin.setSuffix(" %")
        self.height_spin.valueChanged.connect(self.on_zone_property_changed)
        edit_layout.addRow("高度:", self.height_spin)

        right_layout.addWidget(self.edit_group)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.validate_and_accept)
        btn_box.rejected.connect(self.reject)
        right_layout.addWidget(btn_box)

        main_layout.addWidget(right_group, 1)

        self.load_actions()

    def load_pet_image(self):
        if not self.pet_package:
            return

        animations_dir = self.pet_package.animations_dir
        regular_image_name = self.pet_package.meta.regular_image
        image_path = animations_dir / regular_image_name

        if image_path.exists():
            pixmap = QPixmap(str(image_path))
            if not pixmap.isNull():
                self.overlay.setPixmap(pixmap)

    def load_actions(self):
        self.action_combo.clear()
        self.action_combo.addItem("-- 选择动作 --", "")

        if self.pet_package:
            for action in self.pet_package.actions:
                if action.enabled:
                    self.action_combo.addItem(action.name, action.name)

    def load_current_zones(self):
        self.zones.clear()

        if self.config_manager:
            click_detection = self.config_manager.config.get("click_detection", {})
            zones_data = click_detection.get("zones", [])
            for zone_data in zones_data:
                zone = ClickZoneConfig(
                    name=zone_data.get("name", ""),
                    x=zone_data.get("x", 0.0),
                    y=zone_data.get("y", 0.0),
                    width=zone_data.get("width", 0.2),
                    height=zone_data.get("height", 0.2),
                    action=zone_data.get("action", "")
                )
                self.zones.append(zone)
        elif self.pet_package:
            for action in self.pet_package.actions:
                if action.zone_actions:
                    for zone_name, zone_action in action.zone_actions.items():
                        zone = ClickZoneConfig(
                            name=zone_name,
                            x=0.0,
                            y=0.0,
                            width=0.2,
                            height=0.2,
                            action=zone_action
                        )
                        self.zones.append(zone)

        self.overlay.zones = self.zones
        self.update_zone_list()

    def update_zone_list(self):
        self.zone_list.clear()
        for i, zone in enumerate(self.zones):
            item_text = f"{zone.name} ({zone.action or '未设置'})"
            self.zone_list.addItem(item_text)

    def on_zone_list_selection_changed(self, row):
        if row >= 0 and row < len(self.zones):
            self.edit_group.setEnabled(True)
            zone = self.zones[row]

            self.overlay.set_selected_zone(row)

            self.name_edit.blockSignals(True)
            self.name_edit.setValue(int(zone.name) if zone.name.isdigit() else row + 1)
            self.name_edit.blockSignals(False)

            index = self.action_combo.findData(zone.action)
            self.action_combo.blockSignals(True)
            self.action_combo.setCurrentIndex(index if index >= 0 else 0)
            self.action_combo.blockSignals(False)

            self.x_spin.blockSignals(True)
            self.x_spin.setValue(int(zone.x * 100))
            self.x_spin.blockSignals(False)

            self.y_spin.blockSignals(True)
            self.y_spin.setValue(int(zone.y * 100))
            self.y_spin.blockSignals(False)

            self.width_spin.blockSignals(True)
            self.width_spin.setValue(int(zone.width * 100))
            self.width_spin.blockSignals(False)

            self.height_spin.blockSignals(True)
            self.height_spin.setValue(int(zone.height * 100))
            self.height_spin.blockSignals(False)
        else:
            self.edit_group.setEnabled(False)

    def on_zone_changed(self, index, data):
        if index < 0 or index >= len(self.zones):
            return

        zone = self.zones[index]
        zone.x = data.get("x", zone.x)
        zone.y = data.get("y", zone.y)
        zone.width = data.get("width", zone.width)
        zone.height = data.get("height", zone.height)

        if self.zone_list.currentRow() == index:
            self.x_spin.blockSignals(True)
            self.x_spin.setValue(int(zone.x * 100))
            self.x_spin.blockSignals(False)

            self.y_spin.blockSignals(True)
            self.y_spin.setValue(int(zone.y * 100))
            self.y_spin.blockSignals(False)

            self.width_spin.blockSignals(True)
            self.width_spin.setValue(int(zone.width * 100))
            self.width_spin.blockSignals(False)

            self.height_spin.blockSignals(True)
            self.height_spin.setValue(int(zone.height * 100))
            self.height_spin.blockSignals(False)

    def on_zone_property_changed(self):
        row = self.zone_list.currentRow()
        if row < 0 or row >= len(self.zones):
            return

        zone = self.zones[row]

        zone.x = self.x_spin.value() / 100.0
        zone.y = self.y_spin.value() / 100.0
        zone.width = self.width_spin.value() / 100.0
        zone.height = self.height_spin.value() / 100.0
        zone.action = self.action_combo.currentData() or ""

        self.overlay.update_zone(row, {
            "x": zone.x,
            "y": zone.y,
            "width": zone.width,
            "height": zone.height,
            "action": zone.action
        })

        self.zone_list.currentItem().setText(f"{zone.name} ({zone.action or '未设置'})")

    def add_zone(self):
        new_index = len(self.zones) + 1
        new_zone = ClickZoneConfig(
            name=str(new_index),
            x=0.1 * (new_index - 1),
            y=0.1 * (new_index - 1),
            width=0.2,
            height=0.2,
            action=""
        )
        self.zones.append(new_zone)
        self.overlay.zones = self.zones
        self.update_zone_list()
        self.zone_list.setCurrentRow(len(self.zones) - 1)

    def delete_zone(self):
        row = self.zone_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "警告", "请先选择一个区域")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除区域 '{self.zones[row].name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.overlay.remove_zone(row)
            self.zones = self.overlay.zones
            self.update_zone_list()

    def validate_and_accept(self):
        for zone in self.zones:
            if not zone.name:
                QMessageBox.warning(self, "验证失败", "区域名称不能为空")
                return

            if zone.x < 0 or zone.y < 0 or zone.width <= 0 or zone.height <= 0:
                QMessageBox.warning(self, "验证失败", f"区域 '{zone.name}' 的位置或大小无效")
                return

            if zone.x + zone.width > 1 or zone.y + zone.height > 1:
                QMessageBox.warning(self, "验证失败", f"区域 '{zone.name}' 超出边界")
                return

        self.accept()

    def get_zones(self):
        return self.zones

    def save_to_pet_package(self):
        if not self.pet_package:
            return False

        try:
            import json

            if self.config_manager:
                user_config_path = self.config_manager.user_config_path
                existing_config = {}
                if user_config_path.exists():
                    try:
                        with open(user_config_path, "r", encoding="utf-8") as f:
                            existing_config = json.load(f)
                    except (json.JSONDecodeError, IOError):
                        pass

                zones_data = []
                for zone in self.zones:
                    zones_data.append({
                        "name": zone.name,
                        "x": zone.x,
                        "y": zone.y,
                        "width": zone.width,
                        "height": zone.height,
                        "action": zone.action
                    })

                existing_config["click_detection"] = {
                    "enabled": existing_config.get("click_detection", {}).get("enabled", False),
                    "zones": zones_data
                }

                with open(user_config_path, "w", encoding="utf-8") as f:
                    json.dump(existing_config, f, ensure_ascii=False, indent=2)
                return True
            else:
                for action in self.pet_package.actions:
                    action.zone_actions.clear()

                actions_by_name = {a.name: a for a in self.pet_package.actions}

                for zone in self.zones:
                    if zone.action and zone.action in actions_by_name:
                        actions_by_name[zone.action].zone_actions[zone.name] = zone.action

                actions_path = self.pet_package.config_dir / "actions.json"
                actions_data = []
                for action in self.pet_package.actions:
                    action_dict = {
                        "name": action.name,
                        "type": action.type,
                        "weight": action.weight,
                        "animation_files": action.animation_files,
                        "enabled": action.enabled,
                        "config": action.config,
                        "zone_actions": action.zone_actions
                    }
                    actions_data.append(action_dict)

                data = {"actions": actions_data}
                with open(actions_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                return True
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存配置时出错：{str(e)}")
            return False
