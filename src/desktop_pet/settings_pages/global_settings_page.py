"""Global settings page.

仅显示全局配置项：API、托盘、启动、显示、LLM、MCP。
实例级配置（actions/rest_reminder/movement/behavior/motion_mode/click_detection）
已迁移至实例配置页。
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QGroupBox, QFormLayout,
    QLineEdit, QSpinBox, QCheckBox, QRadioButton,
    QListWidget, QMessageBox, QComboBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt

from ..startup_manager import is_startup_enabled, set_startup_enabled
from ..ui_style import (
    PAGE_STYLE, SECTION_STYLE, INPUT_STYLE, CHECK_STYLE,
    PRIMARY_BUTTON_STYLE, SECONDARY_BUTTON_STYLE, STATUS_STYLE,
)


class GlobalSettingsPage(QWidget):
    """Page for global application settings."""

    def __init__(self, platform, parent=None):
        """Create a global settings page owned by ``PetPlatform``."""
        if platform is None or not hasattr(platform, "global_config"):
            raise TypeError("GlobalSettingsPage requires a PetPlatform")
        super().__init__(parent)
        self.platform = platform
        self.config_manager = platform.global_config

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
        description = QLabel("调整 API、托盘、启动、显示、LLM 与 MCP 等全局项。实例级配置请到「实例管理」中编辑。")
        description.setStyleSheet("font-size: 13px; color: #66736e;")
        description.setWordWrap(True)
        layout.addWidget(description)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 8, 0)
        scroll_layout.setSpacing(16)

        # 1. 系统设置（启动 + 托盘）
        system_group = QGroupBox("系统设置")
        system_layout = QFormLayout(system_group)
        system_layout.setSpacing(10)

        self.startup_cb = QCheckBox("开机自启动")
        system_layout.addRow("", self.startup_cb)

        self.start_hidden_cb = QCheckBox("启动时隐藏窗口")
        system_layout.addRow("", self.start_hidden_cb)

        self.tray_enabled_cb = QCheckBox("启用托盘图标")
        system_layout.addRow("", self.tray_enabled_cb)

        self.minimize_to_tray_cb = QCheckBox("最小化到托盘")
        system_layout.addRow("", self.minimize_to_tray_cb)

        scroll_layout.addWidget(system_group)

        # 2. 显示设置（跨屏行为）
        display_group = QGroupBox("显示设置")
        display_layout = QFormLayout(display_group)
        display_layout.setSpacing(10)

        self.cross_screen_drag_cb = QCheckBox("允许拖动跨屏")
        display_layout.addRow("", self.cross_screen_drag_cb)

        self.cross_screen_random_walk_cb = QCheckBox("允许随机行为跨屏")
        display_layout.addRow("", self.cross_screen_random_walk_cb)

        self.remember_last_screen_cb = QCheckBox("重启时恢复上次所在屏")
        display_layout.addRow("", self.remember_last_screen_cb)

        self.cross_screen_walk_prob_spin = QDoubleSpinBox()
        self.cross_screen_walk_prob_spin.setRange(0.0, 1.0)
        self.cross_screen_walk_prob_spin.setSingleStep(0.1)
        self.cross_screen_walk_prob_spin.setDecimals(2)
        display_layout.addRow("边缘跨屏概率", self.cross_screen_walk_prob_spin)

        scroll_layout.addWidget(display_group)

        # 3. 本地 API
        api_group = QGroupBox("本地 API")
        api_layout = QFormLayout(api_group)
        api_layout.setSpacing(10)

        self.api_enabled_cb = QCheckBox("启用 API 服务器")
        api_layout.addRow("", self.api_enabled_cb)

        self.api_status_label = QLabel("API 状态：未知")
        api_layout.addRow("API 状态", self.api_status_label)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("127.0.0.1")
        api_layout.addRow("主机地址", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        api_layout.addRow("端口号", self.port_spin)

        # IP 白名单
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

        # 4. LLM 设置
        llm_group = QGroupBox("LLM 设置")
        llm_layout = QFormLayout(llm_group)
        llm_layout.setSpacing(10)

        self.llm_enabled_cb = QCheckBox("启用 LLM 调用")
        llm_layout.addRow("", self.llm_enabled_cb)

        self.llm_api_key_edit = QLineEdit()
        self.llm_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.llm_api_key_edit.setPlaceholderText("sk-...")
        llm_layout.addRow("API Key", self.llm_api_key_edit)

        self.llm_base_url_edit = QLineEdit()
        self.llm_base_url_edit.setPlaceholderText("https://api.openai.com/v1")
        llm_layout.addRow("Base URL", self.llm_base_url_edit)

        self.llm_model_edit = QLineEdit()
        self.llm_model_edit.setPlaceholderText("gpt-4o-mini")
        llm_layout.addRow("模型", self.llm_model_edit)

        self.llm_max_history_spin = QSpinBox()
        self.llm_max_history_spin.setRange(1, 200)
        llm_layout.addRow("最大历史轮数", self.llm_max_history_spin)

        scroll_layout.addWidget(llm_group)

        # 5. MCP 设置
        mcp_group = QGroupBox("MCP 设置")
        mcp_layout = QFormLayout(mcp_group)
        mcp_layout.setSpacing(10)

        self.mcp_enabled_cb = QCheckBox("启用 MCP 服务")
        mcp_layout.addRow("", self.mcp_enabled_cb)

        scroll_layout.addWidget(mcp_group)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # 应用统一样式
        for group in (system_group, display_group, api_group, llm_group, mcp_group):
            group.setStyleSheet(SECTION_STYLE)

        for field in (
            self.host_edit, self.port_spin, self.ip_list,
            self.cross_screen_walk_prob_spin,
            self.llm_api_key_edit, self.llm_base_url_edit,
            self.llm_model_edit, self.llm_max_history_spin,
        ):
            field.setStyleSheet(INPUT_STYLE)

        for toggle in (
            self.startup_cb, self.start_hidden_cb,
            self.tray_enabled_cb, self.minimize_to_tray_cb,
            self.cross_screen_drag_cb, self.cross_screen_random_walk_cb,
            self.remember_last_screen_cb,
            self.api_enabled_cb,
            self.llm_enabled_cb, self.mcp_enabled_cb,
        ):
            toggle.setStyleSheet(CHECK_STYLE)

        self.api_status_label.setStyleSheet(STATUS_STYLE)
        self.start_api_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)
        self.stop_api_btn.setStyleSheet(SECONDARY_BUTTON_STYLE)

        # Bottom buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        save_btn = QPushButton("保存设置")
        save_btn.setStyleSheet(PRIMARY_BUTTON_STYLE)
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
        if not self.config_manager:
            return

        # 启动
        startup = self._get_config_value("startup", {})
        self.startup_cb.setChecked(is_startup_enabled())
        self.start_hidden_cb.setChecked(bool(startup.get("start_hidden", False)))

        # 托盘
        tray = self._get_tray()
        self.tray_enabled_cb.setChecked(getattr(tray, "enabled", True))
        self.minimize_to_tray_cb.setChecked(getattr(tray, "minimize_to_tray", True))

        # 显示
        display = self._get_display()
        self.cross_screen_drag_cb.setChecked(getattr(display, "cross_screen_drag", True))
        self.cross_screen_random_walk_cb.setChecked(getattr(display, "cross_screen_random_walk", True))
        self.remember_last_screen_cb.setChecked(getattr(display, "remember_last_screen", True))
        self.cross_screen_walk_prob_spin.setValue(float(getattr(display, "cross_screen_walk_probability", 0.3)))

        # API
        api_config = self._get_api_config()
        self.api_enabled_cb.setChecked(bool(api_config.get("enabled", False)))
        self.host_edit.setText(api_config.get("host", "127.0.0.1"))
        self.port_spin.setValue(int(api_config.get("port", 8080)))
        self.ip_list.clear()
        for ip in api_config.get("allowed_ips", []):
            self.ip_list.addItem(ip)
        self.refresh_api_status()

        # LLM
        llm = self._get_llm()
        self.llm_enabled_cb.setChecked(getattr(llm, "enabled", False))
        self.llm_api_key_edit.setText(getattr(llm, "api_key", ""))
        self.llm_base_url_edit.setText(getattr(llm, "base_url", "https://api.openai.com/v1"))
        self.llm_model_edit.setText(getattr(llm, "model", "gpt-4o-mini"))
        self.llm_max_history_spin.setValue(int(getattr(llm, "max_history", 20)))

        # MCP
        mcp_config = self._get_mcp_config()
        self.mcp_enabled_cb.setChecked(bool(mcp_config.get("enabled", False)))

    # ------------------------------------------------------------------
    # 配置访问辅助
    # ------------------------------------------------------------------
    def _get_config_value(self, section, default):
        """从 config_manager 的原始 dict 中读取段落。"""
        if self.config_manager is None:
            return default
        cfg = getattr(self.config_manager, "config", None) or {}
        return cfg.get(section, default)

    def _get_tray(self):
        if self.config_manager is None:
            return None
        # GlobalConfigManager 暴露 tray 属性
        return getattr(self.config_manager, "tray", None)

    def _get_display(self):
        if self.config_manager is None:
            return None
        return getattr(self.config_manager, "display", None)

    def _get_llm(self):
        if self.config_manager is None:
            return None
        return getattr(self.config_manager, "llm", None)

    def _get_api_config(self):
        """获取 API 配置 dict。GlobalConfigManager 通过 .api 属性访问。"""
        if self.config_manager is None:
            return {}
        api_attr = getattr(self.config_manager, "api", None)
        if isinstance(api_attr, dict):
            return api_attr
        return {}

    def _get_mcp_config(self):
        """获取 MCP 配置 dict。GlobalConfigManager 通过 .mcp 属性访问。"""
        if self.config_manager is None:
            return {}
        mcp_attr = getattr(self.config_manager, "mcp", None)
        if isinstance(mcp_attr, dict):
            return mcp_attr
        return {}

    # ------------------------------------------------------------------
    # API 服务控制
    # ------------------------------------------------------------------
    def refresh_api_status(self):
        api_server = self.platform.api_server
        if api_server is None:
            self.api_status_label.setText("API 状态：不可用")
        elif api_server.is_running:
            self.api_status_label.setText("API 状态：运行中")
        else:
            self.api_status_label.setText("API 状态：已停止")

    def start_api_server(self):
        api_server = self.platform.api_server
        if api_server is None:
            QMessageBox.warning(self, "不可用", "API 服务器未初始化。")
            return
        if not api_server.start_background():
            QMessageBox.critical(
                self,
                "启动失败",
                str(api_server.last_error or "API 服务器启动失败"),
            )
        self.refresh_api_status()

    def stop_api_server(self):
        api_server = self.platform.api_server
        if api_server is None:
            QMessageBox.warning(self, "不可用", "API 服务器未初始化。")
            return
        if not api_server.stop_background():
            QMessageBox.critical(
                self,
                "停止失败",
                str(api_server.last_error or "API 服务器停止失败"),
            )
        self.refresh_api_status()

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------
    def save_settings(self):
        """Save settings to config."""
        if not self.config_manager:
            QMessageBox.warning(self, "不可用", "配置管理器未就绪。")
            return
        try:
            startup_enabled = self.startup_cb.isChecked()
            set_startup_enabled(startup_enabled)

            ip_list = []
            for i in range(self.ip_list.count()):
                ip_list.append(self.ip_list.item(i).text())

            host = self.host_edit.text() or "127.0.0.1"

            sections = {
                "startup": {
                    "enabled": startup_enabled,
                    "start_hidden": self.start_hidden_cb.isChecked(),
                },
                "tray": {
                    "enabled": self.tray_enabled_cb.isChecked(),
                    "minimize_to_tray": self.minimize_to_tray_cb.isChecked(),
                },
                "display": {
                    "cross_screen_drag": self.cross_screen_drag_cb.isChecked(),
                    "cross_screen_random_walk": self.cross_screen_random_walk_cb.isChecked(),
                    "remember_last_screen": self.remember_last_screen_cb.isChecked(),
                    "cross_screen_walk_probability": float(self.cross_screen_walk_prob_spin.value()),
                },
                "api": {
                    "enabled": self.api_enabled_cb.isChecked(),
                    "host": host,
                    "port": self.port_spin.value(),
                    "allowed_ips": ip_list,
                },
                "llm": {
                    "enabled": self.llm_enabled_cb.isChecked(),
                    "api_key": self.llm_api_key_edit.text(),
                    "base_url": self.llm_base_url_edit.text() or "https://api.openai.com/v1",
                    "model": self.llm_model_edit.text() or "gpt-4o-mini",
                    "max_history": self.llm_max_history_spin.value(),
                },
                "mcp": {
                    "enabled": self.mcp_enabled_cb.isChecked(),
                },
            }

            old_api = self._get_api_config().copy()
            api_server = self.platform.api_server
            was_running = bool(api_server and api_server.is_running)
            endpoint_changed = (
                old_api.get("host", "127.0.0.1") != host
                or int(old_api.get("port", 8080)) != self.port_spin.value()
            )

            self.config_manager.save_global_settings(sections)

            if api_server is not None:
                api_server.set_allowed_ips(ip_list)
                api_server.set_trust_proxy_headers(
                    bool(old_api.get("trust_proxy_headers", False))
                )
                if endpoint_changed and was_running:
                    if not api_server.stop_background():
                        raise RuntimeError(
                            str(api_server.last_error or "API 服务器停止失败")
                        )
                    api_server.configure(host, self.port_spin.value())
                elif endpoint_changed:
                    api_server.configure(host, self.port_spin.value())

                should_run = self.api_enabled_cb.isChecked()
                if should_run and not api_server.is_running:
                    if not api_server.start_background():
                        raise RuntimeError(
                            str(api_server.last_error or "API 服务器启动失败")
                        )
                elif not should_run and api_server.is_running:
                    if not api_server.stop_background():
                        raise RuntimeError(
                            str(api_server.last_error or "API 服务器停止失败")
                        )
                self.refresh_api_status()

            QMessageBox.information(self, "保存成功", "配置已保存。")

        except Exception as e:
            logging.error(f"Failed to save settings: {e}")
            QMessageBox.critical(self, "保存失败", f"保存配置时出错：{str(e)}")
