"""Global settings page."""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QGroupBox, QFormLayout,
    QLineEdit, QSpinBox, QCheckBox, QRadioButton,
    QListWidget, QListWidgetItem, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt

from ..startup_manager import is_startup_enabled, set_startup_enabled


PAGE_STYLE = """
    QWidget {
        background: #f5f7f4;
        color: #24312d;
        font-size: 13px;
    }
    QLabel {
        color: #2c3935;
    }
    QScrollArea {
        background: transparent;
        border: none;
    }
    QScrollBar:vertical {
        background: transparent;
        width: 10px;
        margin: 4px 0 4px 0;
    }
    QScrollBar::handle:vertical {
        background: #c6d0cb;
        border-radius: 5px;
        min-height: 32px;
    }
    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {
        height: 0;
    }
"""

SECTION_STYLE = """
    QGroupBox {
        background: #ffffff;
        border: 1px solid #dfe6e1;
        border-radius: 8px;
        margin-top: 18px;
        padding: 18px 18px 16px 18px;
        font-size: 15px;
        font-weight: 700;
        color: #1f2b27;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 8px;
        background: #ffffff;
    }
"""

INPUT_STYLE = """
    QLineEdit, QSpinBox, QComboBox {
        min-height: 30px;
        padding: 4px 9px;
        border: 1px solid #cfd8d3;
        border-radius: 8px;
        background: #fbfcfa;
        color: #1f2b27;
        selection-background-color: #f2c572;
    }
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
        border: 1px solid #2f7d68;
        background: #ffffff;
    }
    QListWidget {
        border: 1px solid #cfd8d3;
        border-radius: 8px;
        background: #fbfcfa;
        padding: 4px;
        color: #1f2b27;
    }
"""

CHECK_STYLE = """
    QCheckBox, QRadioButton {
        spacing: 8px;
        color: #2c3935;
        font-size: 13px;
    }
    QCheckBox::indicator, QRadioButton::indicator {
        width: 16px;
        height: 16px;
    }
"""

PRIMARY_BUTTON_STYLE = """
    QPushButton {
        background: #2f7d68;
        color: #ffffff;
        border: none;
        padding: 9px 22px;
        border-radius: 8px;
        font-weight: 700;
    }
    QPushButton:hover {
        background: #256a58;
    }
"""

SECONDARY_BUTTON_STYLE = """
    QPushButton {
        background: #ffffff;
        color: #2f7d68;
        border: 1px solid #b8c8c1;
        padding: 7px 14px;
        border-radius: 8px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: #edf5f1;
        border-color: #2f7d68;
    }
"""

STATUS_STYLE = """
    QLabel {
        background: #edf5f1;
        border: 1px solid #c6ddd3;
        border-radius: 8px;
        padding: 6px 10px;
        color: #256a58;
        font-weight: 700;
    }
"""


class GlobalSettingsPage(QWidget):
    """Page for global application settings."""

    def __init__(self, config_manager, pet=None, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.pet = pet
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup UI layout."""
        self.setStyleSheet(PAGE_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(14)

        # Title
        title = QLabel("全局设置")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #17201d;")
        layout.addWidget(title)
        description = QLabel("调整行为、提醒、启动、托盘和本地 API 访问。")
        description.setStyleSheet("font-size: 13px; color: #66736e;")
        layout.addWidget(description)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 8, 0)
        scroll_layout.setSpacing(16)

        # 1. Motion Control
        motion_group = QGroupBox("运动控制")
        motion_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        motion_layout = QFormLayout(motion_group)
        motion_layout.setSpacing(10)

        # Mode selection
        mode_layout = QHBoxLayout()
        self.random_mode_rb = QRadioButton("随机模式")
        self.motion_mode_rb = QRadioButton("运动模式")
        self.random_mode_rb.setStyleSheet("QRadioButton { spacing: 10px; }")
        self.motion_mode_rb.setStyleSheet("QRadioButton { spacing: 10px; }")
        mode_layout.addWidget(self.random_mode_rb)
        mode_layout.addWidget(self.motion_mode_rb)
        mode_layout.addStretch()
        motion_layout.addRow("当前模式", mode_layout)

        # Random interval
        self.min_interval_spin = QSpinBox()
        self.min_interval_spin.setRange(1000, 60000)
        self.min_interval_spin.setSuffix(" 毫秒")
        self.min_interval_spin.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        motion_layout.addRow("最小间隔", self.min_interval_spin)

        self.max_interval_spin = QSpinBox()
        self.max_interval_spin.setRange(1000, 60000)
        self.max_interval_spin.setSuffix(" 毫秒")
        self.max_interval_spin.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        motion_layout.addRow("最大间隔", self.max_interval_spin)

        # Speed
        self.speed_spin = QSpinBox()
        self.speed_spin.setRange(1, 20)
        self.speed_spin.setSuffix(" 像素/帧")
        self.speed_spin.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        motion_layout.addRow("运动速度", self.speed_spin)

        scroll_layout.addWidget(motion_group)

        # 2. Rest Reminder
        rest_group = QGroupBox("休息提醒")
        rest_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        rest_layout = QFormLayout(rest_group)
        rest_layout.setSpacing(10)

        self.rest_enabled_cb = QCheckBox("启用休息提醒")
        self.rest_enabled_cb.setStyleSheet("QCheckBox { spacing: 8px; }")
        rest_layout.addRow("", self.rest_enabled_cb)

        self.rest_interval_spin = QSpinBox()
        self.rest_interval_spin.setRange(1, 180)
        self.rest_interval_spin.setSuffix(" 分钟")
        self.rest_interval_spin.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        rest_layout.addRow("提醒间隔", self.rest_interval_spin)

        self.countdown_spin = QSpinBox()
        self.countdown_spin.setRange(30, 1800)
        self.countdown_spin.setSuffix(" 秒")
        self.countdown_spin.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        rest_layout.addRow("倒计时时长", self.countdown_spin)

        self.rest_intensity_combo = QComboBox()
        self.rest_intensity_combo.addItem("轻柔", "gentle")
        self.rest_intensity_combo.addItem("普通", "normal")
        self.rest_intensity_combo.addItem("强提醒", "strong")
        rest_layout.addRow("提醒强度", self.rest_intensity_combo)

        scroll_layout.addWidget(rest_group)

        # 3. Behavior
        behavior_group = QGroupBox("行为与互动")
        behavior_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        behavior_layout = QFormLayout(behavior_group)
        behavior_layout.setSpacing(10)

        self.quiet_mode_cb = QCheckBox("安静模式")
        self.quiet_mode_cb.setStyleSheet("QCheckBox { spacing: 8px; }")
        behavior_layout.addRow("", self.quiet_mode_cb)

        scroll_layout.addWidget(behavior_group)

        # 3. System Settings
        system_group = QGroupBox("系统设置")
        system_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        system_layout = QFormLayout(system_group)
        system_layout.setSpacing(10)

        self.startup_cb = QCheckBox("开机自启动")
        self.startup_cb.setStyleSheet("QCheckBox { spacing: 8px; }")
        system_layout.addRow("", self.startup_cb)

        self.tray_enabled_cb = QCheckBox("启用托盘图标")
        self.tray_enabled_cb.setStyleSheet("QCheckBox { spacing: 8px; }")
        system_layout.addRow("", self.tray_enabled_cb)

        self.minimize_to_tray_cb = QCheckBox("最小化到托盘")
        self.minimize_to_tray_cb.setStyleSheet("QCheckBox { spacing: 8px; }")
        system_layout.addRow("", self.minimize_to_tray_cb)

        scroll_layout.addWidget(system_group)

        # 4. API Settings
        api_group = QGroupBox("本地 API")
        api_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                color: #333;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        api_layout = QFormLayout(api_group)
        api_layout.setSpacing(10)

        self.api_enabled_cb = QCheckBox("启用 API 服务器")
        self.api_enabled_cb.setStyleSheet("QCheckBox { spacing: 8px; }")
        api_layout.addRow("", self.api_enabled_cb)

        self.api_status_label = QLabel("API 状态：未知")
        api_layout.addRow("API 状态", self.api_status_label)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("127.0.0.1")
        self.host_edit.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        api_layout.addRow("主机地址", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        api_layout.addRow("端口号", self.port_spin)

        # IP whitelist
        ip_label = QLabel("IP 白名单")
        api_layout.addRow(ip_label, self._create_ip_whitelist_widget())

        api_button_layout = QHBoxLayout()
        self.start_api_btn = QPushButton("启动 API")
        self.start_api_btn.clicked.connect(self.start_api_server)
        self.stop_api_btn = QPushButton("停止 API")
        self.stop_api_btn.clicked.connect(self.stop_api_server)
        api_button_layout.addWidget(self.start_api_btn)
        api_button_layout.addWidget(self.stop_api_btn)
        api_button_layout.addStretch()
        api_layout.addRow("", api_button_layout)

        scroll_layout.addWidget(api_group)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        save_btn = QPushButton("保存设置")
        save_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
        save_btn.clicked.connect(self.save_settings)
        bottom_layout.addWidget(save_btn)

        for group in (motion_group, rest_group, behavior_group, system_group, api_group):
            group.setStyleSheet(SECTION_STYLE)

        for field in (
            self.min_interval_spin,
            self.max_interval_spin,
            self.speed_spin,
            self.rest_interval_spin,
            self.countdown_spin,
            self.rest_intensity_combo,
            self.host_edit,
            self.port_spin,
            self.ip_list,
        ):
            field.setStyleSheet(INPUT_STYLE)

        for toggle in (
            self.random_mode_rb,
            self.motion_mode_rb,
            self.rest_enabled_cb,
            self.quiet_mode_cb,
            self.startup_cb,
            self.tray_enabled_cb,
            self.minimize_to_tray_cb,
            self.api_enabled_cb,
        ):
            toggle.setStyleSheet(CHECK_STYLE)

        self.api_status_label.setStyleSheet(STATUS_STYLE)
        self.start_api_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.stop_api_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)

        layout.addLayout(bottom_layout)

    def _create_ip_whitelist_widget(self) -> QWidget:
        """Create IP whitelist management widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.ip_list = QListWidget()
        self.ip_list.setStyleSheet(INPUT_STYLE)
        layout.addWidget(self.ip_list)

        btn_layout = QHBoxLayout()
        add_ip_btn = QPushButton("添加 IP")
        add_ip_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        add_ip_btn.clicked.connect(self.add_ip)
        remove_ip_btn = QPushButton("移除")
        remove_ip_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        remove_ip_btn.clicked.connect(self.remove_ip)
        btn_layout.addWidget(add_ip_btn)
        btn_layout.addWidget(remove_ip_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return widget

    def add_ip(self):
        """Add IP to whitelist."""
        self.ip_list.addItem("127.0.0.1")

    def remove_ip(self):
        """Remove selected IP from whitelist."""
        current = self.ip_list.currentRow()
        if current >= 0:
            self.ip_list.takeItem(current)

    def load_settings(self):
        """Load current settings."""
        # Motion settings
        motion_mode = self.config_manager.motion_mode
        if motion_mode.default_mode == "random":
            self.random_mode_rb.setChecked(True)
        else:
            self.motion_mode_rb.setChecked(True)

        movement = self.config_manager.movement
        self.min_interval_spin.setValue(movement.random_interval_min_ms)
        self.max_interval_spin.setValue(movement.random_interval_max_ms)
        self.speed_spin.setValue(motion_mode.movement_speed)

        # Rest reminder
        rest = self.config_manager.rest_reminder
        self.rest_enabled_cb.setChecked(rest.enabled)
        self.rest_interval_spin.setValue(rest.interval_minutes)
        self.countdown_spin.setValue(rest.countdown_seconds)
        intensity_index = self.rest_intensity_combo.findData(rest.intensity)
        self.rest_intensity_combo.setCurrentIndex(max(0, intensity_index))

        behavior = self.config_manager.behavior
        self.quiet_mode_cb.setChecked(behavior.quiet_mode_enabled)

        # System settings
        self.startup_cb.setChecked(is_startup_enabled())

        tray = self.config_manager.tray
        self.tray_enabled_cb.setChecked(tray.enabled)
        self.minimize_to_tray_cb.setChecked(tray.minimize_to_tray)

        # API settings
        api_config = self.config_manager.config.get("api", {})
        self.api_enabled_cb.setChecked(api_config.get("enabled", False))
        self.host_edit.setText(api_config.get("host", "127.0.0.1"))
        self.port_spin.setValue(api_config.get("port", 8080))

        # IP whitelist
        self.ip_list.clear()
        for ip in api_config.get("allowed_ips", []):
            self.ip_list.addItem(ip)
        self.refresh_api_status()

    def refresh_api_status(self):
        if self.pet and getattr(self.pet, "api_server", None):
            if self.pet.api_server.is_running:
                self.api_status_label.setText("API 状态：运行中")
            else:
                self.api_status_label.setText("API 状态：已停止")
        else:
            self.api_status_label.setText("API 状态：不可用")

    def start_api_server(self):
        if self.pet and hasattr(self.pet, "_start_api_server"):
            self.pet._start_api_server()
        self.refresh_api_status()

    def stop_api_server(self):
        if self.pet and hasattr(self.pet, "_stop_api_server"):
            self.pet._stop_api_server()
        self.refresh_api_status()

    def save_settings(self):
        """Save settings to config."""
        try:
            startup_enabled = self.startup_cb.isChecked()
            set_startup_enabled(startup_enabled)
            ip_list = []
            for i in range(self.ip_list.count()):
                ip_list.append(self.ip_list.item(i).text())

            host = self.host_edit.text() or "127.0.0.1"
            self.config_manager.save_global_settings({
                "motion_mode": {
                    "default_mode": "random" if self.random_mode_rb.isChecked() else "motion",
                    "movement_speed": self.speed_spin.value(),
                },
                "movement": {
                    "random_interval_min_ms": self.min_interval_spin.value(),
                    "random_interval_max_ms": self.max_interval_spin.value(),
                },
                "rest_reminder": {
                    "enabled": self.rest_enabled_cb.isChecked(),
                    "interval_minutes": self.rest_interval_spin.value(),
                    "countdown_seconds": self.countdown_spin.value(),
                    "intensity": self.rest_intensity_combo.currentData(),
                },
                "behavior": {
                    "quiet_mode_enabled": self.quiet_mode_cb.isChecked(),
                },
                "startup": {"enabled": startup_enabled},
                "tray": {
                    "enabled": self.tray_enabled_cb.isChecked(),
                    "minimize_to_tray": self.minimize_to_tray_cb.isChecked(),
                },
                "api": {
                    "enabled": self.api_enabled_cb.isChecked(),
                    "host": host,
                    "port": self.port_spin.value(),
                    "allowed_ips": ip_list,
                },
            })

            if self.pet and getattr(self.pet, "api_server", None):
                self.pet.api_server.configure(host, self.port_spin.value())
                self.pet.api_server.set_allowed_ips(ip_list)
                if self.api_enabled_cb.isChecked():
                    self.pet._start_api_server()
                else:
                    self.pet._stop_api_server()
                if getattr(self.pet, "behavior_scheduler", None):
                    self.pet.behavior_scheduler.quiet_mode_enabled = self.quiet_mode_cb.isChecked()
                self.refresh_api_status()

            QMessageBox.information(self, "保存成功", "配置已保存，部分设置重启后生效。")

        except Exception as e:
            logging.error(f"Failed to save settings: {e}")
            QMessageBox.critical(self, "保存失败", f"保存配置时出错：{str(e)}")
