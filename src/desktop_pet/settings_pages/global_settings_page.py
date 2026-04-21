"""Global settings page."""

import json
import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QGroupBox, QFormLayout,
    QLineEdit, QSpinBox, QCheckBox, QRadioButton,
    QListWidget, QListWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt

from ..startup_manager import is_startup_enabled, set_startup_enabled


class GlobalSettingsPage(QWidget):
    """Page for global application settings."""

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title = QLabel("全局设置")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #333;")
        layout.addWidget(title)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(20)

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

        scroll_layout.addWidget(rest_group)

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
        api_group = QGroupBox("API 设置")
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

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("0.0.0.0")
        self.host_edit.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        api_layout.addRow("主机地址", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setStyleSheet("padding: 6px; border: 1px solid #ddd; border-radius: 4px;")
        api_layout.addRow("端口号", self.port_spin)

        # IP whitelist
        ip_label = QLabel("IP 白名单")
        api_layout.addRow(ip_label, self._create_ip_whitelist_widget())

        scroll_layout.addWidget(api_group)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        save_btn = QPushButton("保存配置")
        save_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4;
                color: white;
                border: none;
                padding: 8px 24px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #106ebe;
            }
        """)
        save_btn.clicked.connect(self.save_settings)
        bottom_layout.addWidget(save_btn)

        layout.addLayout(bottom_layout)

    def _create_ip_whitelist_widget(self) -> QWidget:
        """Create IP whitelist management widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.ip_list = QListWidget()
        self.ip_list.setStyleSheet("border: 1px solid #ddd; border-radius: 4px;")
        layout.addWidget(self.ip_list)

        btn_layout = QHBoxLayout()
        add_ip_btn = QPushButton("+ 添加")
        add_ip_btn.setStyleSheet("""
            QPushButton {
                background: white;
                color: #0078d4;
                border: 1px solid #0078d4;
                padding: 4px 10px;
                border-radius: 4px;
            }
        """)
        add_ip_btn.clicked.connect(self.add_ip)
        remove_ip_btn = QPushButton("- 删除")
        remove_ip_btn.setStyleSheet("""
            QPushButton {
                background: white;
                color: #666;
                border: 1px solid #ddd;
                padding: 4px 10px;
                border-radius: 4px;
            }
        """)
        remove_ip_btn.clicked.connect(self.remove_ip)
        btn_layout.addWidget(add_ip_btn)
        btn_layout.addWidget(remove_ip_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return widget

    def add_ip(self):
        """Add IP to whitelist."""
        self.ip_list.addItem("0.0.0.0")

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

        # System settings
        self.startup_cb.setChecked(is_startup_enabled())

        tray = self.config_manager.tray
        self.tray_enabled_cb.setChecked(tray.enabled)
        self.minimize_to_tray_cb.setChecked(tray.minimize_to_tray)

        # API settings
        api_config = self.config_manager.config.get("api", {})
        self.api_enabled_cb.setChecked(api_config.get("enabled", False))
        self.host_edit.setText(api_config.get("host", "0.0.0.0"))
        self.port_spin.setValue(api_config.get("port", 8080))

        # IP whitelist
        self.ip_list.clear()
        for ip in api_config.get("allowed_ips", []):
            self.ip_list.addItem(ip)

    def save_settings(self):
        """Save settings to config."""
        try:
            # Read existing user config
            user_config_path = self.config_manager.user_config_path
            user_config = {}
            if user_config_path.exists():
                with open(user_config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)

            # Motion mode
            if "motion_mode" not in user_config:
                user_config["motion_mode"] = {}
            user_config["motion_mode"]["default_mode"] = "random" if self.random_mode_rb.isChecked() else "motion"
            user_config["motion_mode"]["movement_speed"] = self.speed_spin.value()

            # Movement
            if "movement" not in user_config:
                user_config["movement"] = {}
            user_config["movement"]["random_interval_min_ms"] = self.min_interval_spin.value()
            user_config["movement"]["random_interval_max_ms"] = self.max_interval_spin.value()

            # Rest reminder
            if "rest_reminder" not in user_config:
                user_config["rest_reminder"] = {}
            user_config["rest_reminder"]["enabled"] = self.rest_enabled_cb.isChecked()
            user_config["rest_reminder"]["interval_minutes"] = self.rest_interval_spin.value()
            user_config["rest_reminder"]["countdown_seconds"] = self.countdown_spin.value()

            # System settings
            if "startup" not in user_config:
                user_config["startup"] = {}
            user_config["startup"]["enabled"] = self.startup_cb.isChecked()
            set_startup_enabled(self.startup_cb.isChecked())

            if "tray" not in user_config:
                user_config["tray"] = {}
            user_config["tray"]["enabled"] = self.tray_enabled_cb.isChecked()
            user_config["tray"]["minimize_to_tray"] = self.minimize_to_tray_cb.isChecked()

            # API settings
            if "api" not in user_config:
                user_config["api"] = {}
            user_config["api"]["enabled"] = self.api_enabled_cb.isChecked()
            user_config["api"]["host"] = self.host_edit.text()
            user_config["api"]["port"] = self.port_spin.value()

            ip_list = []
            for i in range(self.ip_list.count()):
                ip_list.append(self.ip_list.item(i).text())
            user_config["api"]["allowed_ips"] = ip_list

            # Save
            with open(user_config_path, "w", encoding="utf-8") as f:
                json.dump(user_config, f, ensure_ascii=False, indent=2)

            QMessageBox.information(self, "保存成功", "配置已保存，部分设置重启后生效。")

        except Exception as e:
            logging.error(f"Failed to save settings: {e}")
            QMessageBox.critical(self, "保存失败", f"保存配置时出错：{str(e)}")
