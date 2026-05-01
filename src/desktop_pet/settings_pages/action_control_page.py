"""Action control page for Settings Center."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QFormLayout,
    QSpinBox, QListWidget, QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt


class ActionControlPage(QWidget):
    """Page for manually controlling pet actions."""

    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self.pet = pet
        self.motion_controller = pet.motion_controller
        self.setup_ui()
        self.refresh_animations()
        self.update_position_display()
        self.refresh_click_detection_state()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Mode control group
        mode_group = QGroupBox("模式控制")
        mode_layout = QHBoxLayout(mode_group)

        self.mode_label = QLabel("当前模式: 随机模式")
        mode_layout.addWidget(self.mode_label)

        self.random_mode_btn = QPushButton("切换到随机模式")
        self.random_mode_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #005a9e;
            }
        """)
        self.random_mode_btn.clicked.connect(self.switch_to_random)
        mode_layout.addWidget(self.random_mode_btn)

        self.motion_mode_btn = QPushButton("切换到运动模式")
        self.motion_mode_btn.setStyleSheet("""
            QPushButton {
                background: #5cb85c;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #449d44;
            }
        """)
        self.motion_mode_btn.clicked.connect(self.switch_to_motion)
        mode_layout.addWidget(self.motion_mode_btn)

        layout.addWidget(mode_group)

        # Position control group
        position_group = QGroupBox("位置控制")
        position_layout = QFormLayout(position_group)

        self.pos_label = QLabel("(0, 0)")
        position_layout.addRow("当前位置:", self.pos_label)

        coord_layout = QHBoxLayout()
        self.x_spin = QSpinBox()
        self.x_spin.setRange(0, 3840)
        self.y_spin = QSpinBox()
        self.y_spin.setRange(0, 2160)
        coord_layout.addWidget(QLabel("X:"))
        coord_layout.addWidget(self.x_spin)
        coord_layout.addWidget(QLabel("Y:"))
        coord_layout.addWidget(self.y_spin)

        position_layout.addRow("目标坐标:", coord_layout)

        move_btn_layout = QHBoxLayout()
        self.move_to_btn = QPushButton("移动到")
        self.move_to_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #005a9e;
            }
        """)
        self.move_to_btn.clicked.connect(self.on_move_to_clicked)
        move_btn_layout.addWidget(self.move_to_btn)

        self.move_to_edge_left_btn = QPushButton("左边缘")
        self.move_to_edge_left_btn.clicked.connect(lambda: self.on_move_to_edge("left"))
        move_btn_layout.addWidget(self.move_to_edge_left_btn)

        self.move_to_edge_right_btn = QPushButton("右边缘")
        self.move_to_edge_right_btn.clicked.connect(lambda: self.on_move_to_edge("right"))
        move_btn_layout.addWidget(self.move_to_edge_right_btn)

        position_layout.addRow("", move_btn_layout)

        layout.addWidget(position_group)

        # Direction move group
        direction_group = QGroupBox("方向移动")
        direction_layout = QHBoxLayout(direction_group)

        self.up_btn = QPushButton("↑")
        self.up_btn.setMaximumWidth(50)
        self.up_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f0;
                border: 1px solid #ccc;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
        """)
        self.up_btn.clicked.connect(lambda: self.on_direction_move(0, -50))
        direction_layout.addWidget(self.up_btn)

        self.down_btn = QPushButton("↓")
        self.down_btn.setMaximumWidth(50)
        self.down_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f0;
                border: 1px solid #ccc;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
        """)
        self.down_btn.clicked.connect(lambda: self.on_direction_move(0, 50))
        direction_layout.addWidget(self.down_btn)

        self.left_btn = QPushButton("←")
        self.left_btn.setMaximumWidth(50)
        self.left_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f0;
                border: 1px solid #ccc;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
        """)
        self.left_btn.clicked.connect(lambda: self.on_direction_move(-50, 0))
        direction_layout.addWidget(self.left_btn)

        self.right_btn = QPushButton("→")
        self.right_btn.setMaximumWidth(50)
        self.right_btn.setStyleSheet("""
            QPushButton {
                background: #f0f0f0;
                border: 1px solid #ccc;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
        """)
        self.right_btn.clicked.connect(lambda: self.on_direction_move(50, 0))
        direction_layout.addWidget(self.right_btn)

        layout.addWidget(direction_group)

        # Animation control group
        animation_group = QGroupBox("动画控制")
        animation_layout = QVBoxLayout(animation_group)

        self.animation_list = QListWidget()
        self.animation_list.setMaximumHeight(120)
        animation_layout.addWidget(self.animation_list)

        anim_btn_layout = QHBoxLayout()
        self.play_anim_btn = QPushButton("播放选中动画")
        self.play_anim_btn.setStyleSheet("""
            QPushButton {
                background: #5cb85c;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #449d44;
            }
        """)
        self.play_anim_btn.clicked.connect(self.on_play_animation)
        anim_btn_layout.addWidget(self.play_anim_btn)

        self.stop_anim_btn = QPushButton("停止动画")
        self.stop_anim_btn.setStyleSheet("""
            QPushButton {
                background: #d9534f;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #c9302c;
            }
        """)
        self.stop_anim_btn.clicked.connect(self.on_stop_animation)
        anim_btn_layout.addWidget(self.stop_anim_btn)

        animation_layout.addLayout(anim_btn_layout)

        layout.addWidget(animation_group)

        # Walk control group
        walk_group = QGroupBox("行走控制")
        walk_layout = QHBoxLayout(walk_group)

        self.walk_left_btn = QPushButton("← 向左行走")
        self.walk_left_btn.setStyleSheet("""
            QPushButton {
                background: #f0ad4e;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #ec971f;
            }
        """)
        self.walk_left_btn.clicked.connect(lambda: self.on_play_walk("left"))
        walk_layout.addWidget(self.walk_left_btn)

        self.walk_right_btn = QPushButton("向右行走 →")
        self.walk_right_btn.setStyleSheet("""
            QPushButton {
                background: #f0ad4e;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #ec971f;
            }
        """)
        self.walk_right_btn.clicked.connect(lambda: self.on_play_walk("right"))
        walk_layout.addWidget(self.walk_right_btn)

        layout.addWidget(walk_group)

        # Click detection group
        click_detection_group = QGroupBox("点击检测")
        click_detection_layout = QHBoxLayout(click_detection_group)

        self.click_detection_checkbox = QCheckBox("启用点击检测")
        self.click_detection_checkbox.stateChanged.connect(self.on_click_detection_changed)
        click_detection_layout.addWidget(self.click_detection_checkbox)

        layout.addWidget(click_detection_group)

        # Refresh button
        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #005a9e;
            }
        """)
        self.refresh_btn.clicked.connect(self.refresh_all)
        layout.addWidget(self.refresh_btn)

    def refresh_animations(self):
        self.animation_list.clear()
        animations = self.motion_controller.get_available_animations()
        self.animation_list.addItems(animations)

    def update_position_display(self):
        pos = self.motion_controller.get_position()
        self.pos_label.setText(f"({pos['x']}, {pos['y']})")
        self.x_spin.setValue(pos['x'])
        self.y_spin.setValue(pos['y'])

    def refresh_all(self):
        self.update_position_display()
        self.refresh_animations()
        mode = self.motion_controller.get_mode()
        self.mode_label.setText(f"当前模式: {'运动模式' if mode == 'motion' else '随机模式'}")

    def switch_to_random(self):
        self.motion_controller.set_mode("random")
        self.mode_label.setText("当前模式: 随机模式")

    def switch_to_motion(self):
        self.motion_controller.set_mode("motion")
        self.mode_label.setText("当前模式: 运动模式")

    def on_move_to_clicked(self):
        if self.motion_controller.get_mode() != "motion":
            QMessageBox.warning(self, "警告", "请先切换到运动模式")
            return
        x = self.x_spin.value()
        y = self.y_spin.value()
        self.motion_controller.move_to(x, y)

    def on_move_to_edge(self, edge):
        if self.motion_controller.get_mode() != "motion":
            QMessageBox.warning(self, "警告", "请先切换到运动模式")
            return
        self.motion_controller.move_to_edge(edge)

    def on_direction_move(self, dx, dy):
        if self.motion_controller.get_mode() != "motion":
            QMessageBox.warning(self, "警告", "请先切换到运动模式")
            return
        self.motion_controller.move_by(dx, dy)

    def on_play_animation(self):
        if self.motion_controller.get_mode() != "motion":
            QMessageBox.warning(self, "警告", "请先切换到运动模式")
            return
        current_item = self.animation_list.currentItem()
        if current_item:
            anim_name = current_item.text()
            self.motion_controller.play_animation(anim_name)

    def on_stop_animation(self):
        self.motion_controller.stop_animation()

    def on_play_walk(self, direction):
        if self.motion_controller.get_mode() != "motion":
            QMessageBox.warning(self, "警告", "请先切换到运动模式")
            return
        self.motion_controller.play_walk(direction)

    def on_click_detection_changed(self, state):
        enabled = state == Qt.CheckState.Checked.value
        self.pet.set_click_detection_enabled(enabled)
        self.pet.config_manager.set_click_detection_enabled(enabled)
        self.pet.config_manager.save_config()

    def refresh_click_detection_state(self):
        enabled = self.pet.config_manager.get_click_detection_enabled()
        self.click_detection_checkbox.setChecked(enabled)
