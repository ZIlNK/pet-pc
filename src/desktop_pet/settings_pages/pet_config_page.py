"""Per-instance configuration page for the multi-pet platform."""

import copy
import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QGroupBox, QFormLayout,
    QLineEdit, QSpinBox, QCheckBox, QComboBox,
    QMessageBox, QDialog
)
from PyQt6.QtCore import pyqtSignal

from ..click_zone_dialog import ClickZoneConfigDialog
from ..config_manager import ClickZoneConfig
from ..ui_style import (
    SECTION_STYLE, INPUT_STYLE, CHECK_STYLE,
    PRIMARY_BUTTON_STYLE, SECONDARY_BUTTON_STYLE,
    FONT_SIZE_TITLE, title_style, subtitle_style,
)


logger = logging.getLogger(__name__)


class PetConfigPage(QWidget):
    """Page for configuring a single pet's properties."""

    back_to_list = pyqtSignal()

    def __init__(self, instance_config, platform, parent=None):
        if instance_config is None or platform is None:
            raise TypeError("PetConfigPage requires instance_config and platform")
        super().__init__(parent)
        self.instance_config = instance_config
        self.platform = platform
        self.pet_package = platform.pet_packages.get(instance_config.package)
        self._preview_movie = None
        self._click_zones_buffer = copy.deepcopy(
            (instance_config.click_detection or {}).get("zones", [])
        )
        self.setup_ui()
        self.load_pet_data()

    def set_instance(self, instance_config):
        self.instance_config = instance_config
        self.pet_package = self.platform.pet_packages.get(instance_config.package)
        self._click_zones_buffer = copy.deepcopy(
            (instance_config.click_detection or {}).get("zones", [])
        )
        self.load_pet_data()

    def setup_ui(self):
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(15)

        # Header with back button
        header = QHBoxLayout()
        self.back_btn = QPushButton("← 返回")
        self.back_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.back_btn.clicked.connect(self.back_to_list.emit)
        header.addWidget(self.back_btn)

        self.title_label = QLabel("配置: 默认桌宠")
        self.title_label.setStyleSheet(title_style(FONT_SIZE_TITLE))
        header.addWidget(self.title_label, 1)

        layout.addLayout(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(20)

        # 1. 实例级配置组（仅新模式显示）
        self.instance_group = QGroupBox("实例设置")
        instance_layout = QFormLayout(self.instance_group)
        instance_layout.setSpacing(10)

        self.package_combo = QComboBox()
        for package_name in self.platform.pet_packages:
            self.package_combo.addItem(package_name, package_name)
        instance_layout.addRow("资源包", self.package_combo)

        # 位置
        pos_layout = QHBoxLayout()
        self.pos_x_spin = QSpinBox()
        self.pos_x_spin.setRange(-10000, 10000)
        self.pos_y_spin = QSpinBox()
        self.pos_y_spin.setRange(-10000, 10000)
        pos_layout.addWidget(QLabel("X:"))
        pos_layout.addWidget(self.pos_x_spin)
        pos_layout.addWidget(QLabel("Y:"))
        pos_layout.addWidget(self.pos_y_spin)
        instance_layout.addRow("位置", pos_layout)

        # 尺寸
        self.size_spin = QSpinBox()
        self.size_spin.setRange(50, 1000)
        self.size_spin.setSuffix(" px")
        instance_layout.addRow("尺寸", self.size_spin)

        scroll_layout.addWidget(self.instance_group)

        # 2. 休息提醒组
        rest_group = QGroupBox("休息提醒")
        rest_layout = QFormLayout(rest_group)
        rest_layout.setSpacing(10)

        self.rest_enabled_cb = QCheckBox("启用休息提醒")
        rest_layout.addRow("", self.rest_enabled_cb)

        self.rest_interval_spin = QSpinBox()
        self.rest_interval_spin.setRange(1, 180)
        self.rest_interval_spin.setSuffix(" 分钟")
        rest_layout.addRow("提醒间隔", self.rest_interval_spin)

        self.countdown_spin = QSpinBox()
        self.countdown_spin.setRange(30, 1800)
        self.countdown_spin.setSuffix(" 秒")
        rest_layout.addRow("倒计时时长", self.countdown_spin)

        self.rest_intensity_combo = QComboBox()
        self.rest_intensity_combo.addItem("轻柔", "gentle")
        self.rest_intensity_combo.addItem("普通", "normal")
        self.rest_intensity_combo.addItem("强提醒", "strong")
        rest_layout.addRow("提醒强度", self.rest_intensity_combo)

        scroll_layout.addWidget(rest_group)

        # 3. 移动设置组
        movement_group = QGroupBox("随机移动")
        movement_layout = QFormLayout(movement_group)
        movement_layout.setSpacing(10)

        self.min_interval_spin = QSpinBox()
        self.min_interval_spin.setRange(1000, 60000)
        self.min_interval_spin.setSuffix(" 毫秒")
        movement_layout.addRow("最小间隔", self.min_interval_spin)

        self.max_interval_spin = QSpinBox()
        self.max_interval_spin.setRange(1000, 60000)
        self.max_interval_spin.setSuffix(" 毫秒")
        movement_layout.addRow("最大间隔", self.max_interval_spin)

        scroll_layout.addWidget(movement_group)

        # 4. 运动模式组
        motion_group = QGroupBox("运动模式")
        motion_layout = QFormLayout(motion_group)
        motion_layout.setSpacing(10)

        self.motion_enabled_cb = QCheckBox("启用运动模式")
        motion_layout.addRow("", self.motion_enabled_cb)

        self.motion_default_mode_combo = QComboBox()
        self.motion_default_mode_combo.addItem("随机模式", "random")
        self.motion_default_mode_combo.addItem("运动模式", "motion")
        motion_layout.addRow("默认模式", self.motion_default_mode_combo)

        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(1, 20)
        self.speed_spin.setSuffix(" 级")
        motion_layout.addRow("运动速度", self.speed_spin)

        scroll_layout.addWidget(motion_group)

        # 5. 行为组
        behavior_group = QGroupBox("行为与互动")
        behavior_layout = QFormLayout(behavior_group)
        behavior_layout.setSpacing(10)

        self.quiet_mode_cb = QCheckBox("安静模式")
        behavior_layout.addRow("", self.quiet_mode_cb)

        self.head_action_edit = QLineEdit()
        behavior_layout.addRow("默认头部动作", self.head_action_edit)

        self.body_action_edit = QLineEdit()
        behavior_layout.addRow("默认身体动作", self.body_action_edit)

        scroll_layout.addWidget(behavior_group)

        # 6. 基础形象组（旧模式专用，新模式下隐藏）
        self.appearance_group = QGroupBox("基础形象")
        appearance_layout = QFormLayout(self.appearance_group)
        appearance_layout.setSpacing(10)

        self.regular_image_edit = QLineEdit()
        self.regular_image_edit.setReadOnly(True)
        regular_btn = QPushButton("更换")
        regular_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        regular_btn.clicked.connect(lambda: self.select_image('regular'))
        appearance_layout.addRow("待机形象", self.regular_image_edit)
        appearance_layout.addRow("", regular_btn)

        self.flying_image_edit = QLineEdit()
        self.flying_image_edit.setReadOnly(True)
        flying_btn = QPushButton("更换")
        flying_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        flying_btn.clicked.connect(lambda: self.select_image('flying'))
        appearance_layout.addRow("缓降形象", self.flying_image_edit)
        appearance_layout.addRow("", flying_btn)

        self.walk_left_label = QLabel("未设置")
        self.walk_left_label.setStyleSheet(subtitle_style())
        self.walk_left_btn = QPushButton("设置")
        self.walk_left_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.walk_left_btn.clicked.connect(lambda: self.select_walk_animation('left'))
        appearance_layout.addRow("向左行走", self.walk_left_label)
        appearance_layout.addRow("", self.walk_left_btn)

        self.walk_right_label = QLabel("未设置")
        self.walk_right_label.setStyleSheet(subtitle_style())
        self.walk_right_btn = QPushButton("设置")
        self.walk_right_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.walk_right_btn.clicked.connect(lambda: self.select_walk_animation('right'))
        appearance_layout.addRow("向右行走", self.walk_right_label)
        appearance_layout.addRow("", self.walk_right_btn)

        self.rest_animation_edit = QLineEdit()
        self.rest_animation_edit.setReadOnly(True)
        rest_btn = QPushButton("更换")
        rest_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        rest_btn.clicked.connect(lambda: self.select_image('rest'))
        appearance_layout.addRow("休息动画", self.rest_animation_edit)
        appearance_layout.addRow("", rest_btn)

        scroll_layout.addWidget(self.appearance_group)

        # 7. 点击检测配置组（旧模式专用）
        self.click_detection_group = QGroupBox("点击检测配置")
        click_detection_layout = QVBoxLayout(self.click_detection_group)

        self.click_enabled_cb = QCheckBox("启用点击区域检测")
        click_detection_layout.addWidget(self.click_enabled_cb)
        self.click_zone_count_label = QLabel("当前配置: 0 个点击区域")
        click_detection_layout.addWidget(self.click_zone_count_label)

        click_zone_btn = QPushButton("配置点击区域")
        click_zone_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        click_zone_btn.clicked.connect(self.configure_click_zones)
        click_detection_layout.addWidget(click_zone_btn)

        scroll_layout.addWidget(self.click_detection_group)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # 应用统一样式
        for grp in (
            self.instance_group, rest_group, movement_group,
            motion_group, behavior_group,
            self.appearance_group, self.click_detection_group,
        ):
            grp.setStyleSheet(SECTION_STYLE)

        for field in (
            self.package_combo, self.pos_x_spin, self.pos_y_spin, self.size_spin,
            self.rest_interval_spin, self.countdown_spin, self.rest_intensity_combo,
            self.min_interval_spin, self.max_interval_spin,
            self.speed_spin, self.motion_default_mode_combo,
            self.head_action_edit, self.body_action_edit,
            self.regular_image_edit, self.flying_image_edit, self.rest_animation_edit,
        ):
            field.setStyleSheet(INPUT_STYLE)

        for toggle in (
            self.rest_enabled_cb, self.motion_enabled_cb, self.quiet_mode_cb,
            self.click_enabled_cb,
        ):
            toggle.setStyleSheet(CHECK_STYLE)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        save_btn = QPushButton("保存配置")
        save_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        save_btn.clicked.connect(self.save_config)
        bottom_layout.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        cancel_btn.clicked.connect(self.back_to_list.emit)
        bottom_layout.addWidget(cancel_btn)

        layout.addLayout(bottom_layout)

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def load_pet_data(self):
        """Load the selected instance configuration."""
        self._load_instance_data()
        self.instance_group.setVisible(True)
        self.appearance_group.setVisible(False)
        self.click_detection_group.setVisible(True)

    def _load_instance_data(self):
        """从 PetInstanceConfig 加载实例级配置。"""
        cfg = self.instance_config
        title = f"实例配置: {cfg.package} ({cfg.pet_id})"
        self.title_label.setText(title)

        package_index = self.package_combo.findData(cfg.package)
        if package_index < 0:
            self.package_combo.addItem(f"{cfg.package} (???)", cfg.package)
            package_index = self.package_combo.count() - 1
        self.package_combo.setCurrentIndex(package_index)

        # 位置
        pos = cfg.position or {"x": 0, "y": 0}
        self.pos_x_spin.setValue(int(pos.get("x", 0)))
        self.pos_y_spin.setValue(int(pos.get("y", 0)))

        # 尺寸
        self.size_spin.setValue(int(getattr(cfg, "size", 200) or 200))

        # 休息提醒
        rest = cfg.rest_reminder or {}
        self.rest_enabled_cb.setChecked(bool(rest.get("enabled", True)))
        self.rest_interval_spin.setValue(int(rest.get("interval_minutes", 55)))
        self.countdown_spin.setValue(int(rest.get("countdown_seconds", 300)))
        idx = self.rest_intensity_combo.findData(rest.get("intensity", "normal"))
        self.rest_intensity_combo.setCurrentIndex(max(0, idx))

        # 移动
        movement = cfg.movement or {}
        self.min_interval_spin.setValue(int(movement.get("random_interval_min_ms", 3000)))
        self.max_interval_spin.setValue(int(movement.get("random_interval_max_ms", 15000)))

        # 运动模式
        motion = cfg.motion_mode or {}
        self.motion_enabled_cb.setChecked(bool(motion.get("enabled", True)))
        idx = self.motion_default_mode_combo.findData(motion.get("default_mode", "random"))
        self.motion_default_mode_combo.setCurrentIndex(max(0, idx))
        self.speed_spin.setValue(int(motion.get("movement_speed", 5)))

        # 行为
        behavior = cfg.behavior or {}
        self.quiet_mode_cb.setChecked(bool(behavior.get("quiet_mode_enabled", False)))
        self.head_action_edit.setText(str(behavior.get("default_head_action", "head")))
        self.body_action_edit.setText(str(behavior.get("default_body_action", "body_tap")))

        click = cfg.click_detection or {}
        self.click_enabled_cb.setChecked(bool(click.get("enabled", False)))
        self._click_zones_buffer = copy.deepcopy(click.get("zones", []))
        self.click_zone_count_label.setText(
            f"当前配置: {len(self._click_zones_buffer)} 个点击区域"
        )

    def configure_click_zones(self):
        if self.pet_package is None:
            QMessageBox.warning(self, "不可用", "当前实例的资源包不存在。")
            return
        dialog = ClickZoneConfigDialog(self.pet_package, parent=self)
        zones = [ClickZoneConfig(**zone) for zone in self._click_zones_buffer]
        dialog.zones = zones
        dialog.overlay.zones = zones
        dialog.update_zone_list()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._click_zones_buffer = [
                {
                    "name": zone.name,
                    "x": zone.x,
                    "y": zone.y,
                    "width": zone.width,
                    "height": zone.height,
                    "action": zone.action,
                }
                for zone in dialog.get_zones()
            ]
            self.click_zone_count_label.setText(
                f"当前配置: {len(self._click_zones_buffer)} 个点击区域"
            )

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------
    def save_config(self):
        """Validate, apply, and persist the instance configuration."""
        try:
            self._save_instance_config()
            QMessageBox.information(self, "保存成功", "配置已保存，部分设置重启后生效。")
            self.back_to_list.emit()
        except Exception as e:
            logger.error(f"Failed to save pet config: {e}")
            QMessageBox.critical(self, "保存失败", f"保存配置时出错：{str(e)}")

    def _save_instance_config(self):
        """新模式：通过 platform 更新实例配置。"""
        pet_id = self.instance_config.pet_id
        updates = {
            "package": self.package_combo.currentData(),
            "position": {
                "x": self.pos_x_spin.value(),
                "y": self.pos_y_spin.value(),
            },
            "size": self.size_spin.value(),
            "rest_reminder": {
                "enabled": self.rest_enabled_cb.isChecked(),
                "interval_minutes": self.rest_interval_spin.value(),
                "countdown_seconds": self.countdown_spin.value(),
                "intensity": self.rest_intensity_combo.currentData(),
            },
            "movement": {
                "random_interval_min_ms": self.min_interval_spin.value(),
                "random_interval_max_ms": self.max_interval_spin.value(),
            },
            "motion_mode": {
                "enabled": self.motion_enabled_cb.isChecked(),
                "default_mode": self.motion_default_mode_combo.currentData(),
                "movement_speed": self.speed_spin.value(),
            },
            "behavior": {
                "quiet_mode_enabled": self.quiet_mode_cb.isChecked(),
                "default_head_action": self.head_action_edit.text() or "head",
                "default_body_action": self.body_action_edit.text() or "body_tap",
            },
            "click_detection": {
                "enabled": self.click_enabled_cb.isChecked(),
                "zones": copy.deepcopy(self._click_zones_buffer),
            },
        }
        updated = self.platform.update_instance_config(pet_id, updates)
        self.instance_config = updated
        self.pet_package = self.platform.pet_packages.get(updated.package)
        self._click_zones_buffer = copy.deepcopy(
            (updated.click_detection or {}).get("zones", [])
        )
