import sys
import random
import asyncio
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QMenu
from PyQt6.QtGui import QPixmap, QMovie, QAction
from PyQt6.QtCore import Qt, QPoint, QTimer, QSize
from PIL import Image

from .states import PetState
from .utils import get_assets_path
from .config_manager import ConfigManager, ActionManager, ActionConfig, ClickZoneConfig
from .action_manager_gui import ActionManagerGUI
from .pet_loader import PetLoader, PetPackage
from .motion_controller import MotionModeController
from .motion_control_panel import MotionControlPanel
from .api_server import ApiServer


class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()

        self._api_loop = None
        self.assets_path = get_assets_path()
        self.config_manager = ConfigManager()
        self.action_manager = ActionManager(self.config_manager, self.assets_path)
        self.pet_loader = PetLoader()

        self.current_pet_package: PetPackage | None = None

        self.state = PetState.IDLE
        self.movement_timer = QTimer()
        self.movement_timer.timeout.connect(self.random_move)
        self.start_random_movement_timer()
        self.previous_pos = QPoint(0, 0)
        self.current_animation_type: str | None = None
        self.current_action: ActionConfig | None = None

        self.rest_timer = QTimer()
        self.rest_timer.timeout.connect(self.show_rest_bubble)

        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_countdown)
        self.countdown_seconds = 0

        self.rest_timer_display = QTimer()
        self.rest_timer_display.timeout.connect(self.update_rest_timer_display)

        rest_config = self.config_manager.rest_reminder
        self.rest_timer_seconds = rest_config.interval_minutes * 60

        if rest_config.enabled:
            self.rest_timer.start(rest_config.interval_minutes * 60 * 1000)
        self.rest_timer_display.start(1000)

        self._click_detection_enabled = False
        self._click_zones: list[ClickZoneConfig] = []
        click_detection_config = self.config_manager.config.get("click_detection", {})
        self._click_detection_enabled = click_detection_config.get("enabled", False)
        click_zones_data = click_detection_config.get("zones", [])
        for zone_data in click_zones_data:
            self._click_zones.append(ClickZoneConfig(
                name=zone_data.get("name", ""),
                x=zone_data.get("x", 0.0),
                y=zone_data.get("y", 0.0),
                width=zone_data.get("width", 0.0),
                height=zone_data.get("height", 0.0),
                action=zone_data.get("action", "")
            ))

        self.current_gif: QMovie | None = None
        self.walk_left_gif: QMovie | None = None
        self.walk_right_gif: QMovie | None = None
        self.hui_gif: QMovie | None = None
        self.idle_gif: QMovie | None = None

        self.motion_controller = MotionModeController(self)
        self.motion_controller.move_to_requested.connect(self._on_move_to_requested)
        self.motion_controller.move_by_requested.connect(self._on_move_by_requested)
        self.motion_controller.move_to_edge_requested.connect(self._on_move_to_edge_requested)
        self.motion_controller.play_animation_requested.connect(self._on_play_animation_requested)
        self.motion_controller.play_walk_requested.connect(self._on_play_walk_requested)
        self.motion_controller.stop_animation_requested.connect(self._on_stop_animation_requested)
        self.motion_controller.set_mode_requested.connect(self._on_set_mode_requested)

        self.api_server = ApiServer(self)
        api_config = self.config_manager.config.get("api", {})
        if api_config.get("enabled", False):
            host = api_config.get("host", "0.0.0.0")
            port = api_config.get("port", 8080)
            allowed_ips = api_config.get("allowed_ips", ["127.0.0.1", "::1"])
            self.api_server.configure(host, port)
            self.api_server.set_allowed_ips(allowed_ips)

        self._load_current_pet()
        self.initUI()

    def _load_current_pet(self) -> None:
        pet_name = self.config_manager.get_current_pet_name()
        pet_package = self.pet_loader.load_pet(pet_name)

        if pet_package:
            self.current_pet_package = pet_package
            self.pet_loader.set_current_pet(pet_package)
            print(f"已加载桌宠资源包: {pet_package.meta.name}")
            self._load_pet_animations()
        else:
            print(f"无法加载桌宠资源包: {pet_name}，尝试使用默认资源包")
            pet_package = self.pet_loader.load_pet("default")
            if pet_package:
                self.current_pet_package = pet_package
                self.pet_loader.set_current_pet(pet_package)
                print(f"已加载默认桌宠资源包: {pet_package.meta.name}")
                self._load_pet_animations()
            else:
                print("错误: 无法加载任何桌宠资源包")

    def _load_pet_animations(self) -> None:
        if not self.current_pet_package:
            return

        animations_dir = self.current_pet_package.animations_dir

        for action in self.current_pet_package.actions:
            if action.name == "idle" and action.animation_files:
                idle_path = animations_dir / action.animation_files[0]
                if idle_path.exists():
                    try:
                        self.idle_gif = QMovie(str(idle_path))
                        self.idle_gif.setScaledSize(QSize(200, 159))
                    except Exception as e:
                        print(f"Failed to load idle animation: {e}")

            if action.name == "walk" and action.animation_files:
                if len(action.animation_files) >= 1:
                    walk_left_path = animations_dir / action.animation_files[0]
                    if walk_left_path.exists():
                        try:
                            self.walk_left_gif = QMovie(str(walk_left_path))
                            self.walk_left_gif.setScaledSize(QSize(200, 159))
                        except Exception as e:
                            print(f"Failed to load walk_left animation: {e}")
                if len(action.animation_files) >= 2:
                    walk_right_path = animations_dir / action.animation_files[1]
                    if walk_right_path.exists():
                        try:
                            self.walk_right_gif = QMovie(str(walk_right_path))
                            self.walk_right_gif.setScaledSize(QSize(200, 159))
                        except Exception as e:
                            print(f"Failed to load walk_right animation: {e}")

    def _detect_click_zone(self, x: float, y: float) -> str | None:
        for zone in self._click_zones:
            if (zone.x <= x <= zone.x + zone.width and
                zone.y <= y <= zone.y + zone.height):
                return zone.name
        return None

    def _play_zone_animation(self, zone_name: str) -> None:
        for zone in self._click_zones:
            if zone.name == zone_name:
                self.play_animation_action_by_name(zone.action)
                return

    def play_animation_action_by_name(self, action_name: str) -> None:
        if not self.current_pet_package:
            return
        for action in self.current_pet_package.actions:
            if action.name == action_name:
                self.play_animation_action(action)
                return

    def set_click_detection_enabled(self, enabled: bool) -> None:
        self._click_detection_enabled = enabled

    def set_click_zones(self, zones: list[ClickZoneConfig]) -> None:
        self._click_zones = zones

    def initUI(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        pet_config = self.config_manager.pet
        
        # 从当前 PetPackage 加载静态图片
        if self.current_pet_package:
            animations_dir = self.current_pet_package.animations_dir
            
            # 加载常规图片
            regular_image_name = self.current_pet_package.meta.regular_image
            regular_image_path = animations_dir / regular_image_name
            
            # 如果资源包中没有指定图片，使用默认路径
            if not regular_image_path.exists():
                regular_image_path = self.assets_path / pet_config.regular_image
            
            img = Image.open(regular_image_path)
            # 使用资源包的 animations 目录保存临时文件
            temp_path = animations_dir / 'temp_fixed.png'
            img.save(temp_path, icc_profile=None)

            regular_pixmap = QPixmap(str(regular_image_path))
            self.regular_pixmap = regular_pixmap.scaled(
                pet_config.size, pet_config.size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            # 加载飞行图片
            flying_image_name = self.current_pet_package.meta.flying_image
            flying_image_path = animations_dir / flying_image_name
            
            # 如果资源包中没有指定图片，使用默认路径
            if not flying_image_path.exists():
                flying_image_path = self.assets_path / pet_config.flying_image
            
            try:
                flying_img = Image.open(flying_image_path)
                # 使用资源包的 animations 目录保存临时文件
                temp_flying_path = animations_dir / 'temp_flying_fixed.png'
                flying_img.save(temp_flying_path, icc_profile=None)
                flying_pixmap = QPixmap(str(flying_image_path))
            except Exception:
                flying_pixmap = QPixmap(str(flying_image_path))
            self.flying_pixmap = flying_pixmap.scaled(
                pet_config.size, pet_config.size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            # 回退到默认配置
            regular_image_path = self.assets_path / pet_config.regular_image
            img = Image.open(regular_image_path)
            # 使用资源包的 animations 目录保存临时文件
            temp_path = animations_dir / 'temp_fixed.png'
            img.save(temp_path, icc_profile=None)

            regular_pixmap = QPixmap(str(regular_image_path))
            self.regular_pixmap = regular_pixmap.scaled(
                pet_config.size, pet_config.size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            flying_image_path = self.assets_path / pet_config.flying_image
            try:
                flying_img = Image.open(flying_image_path)
                # 使用资源包的 animations 目录保存临时文件
                temp_flying_path = animations_dir / 'temp_flying_fixed.png'
                flying_img.save(temp_flying_path, icc_profile=None)
                flying_pixmap = QPixmap(str(flying_image_path))
            except Exception:
                flying_pixmap = QPixmap(str(flying_image_path))
            self.flying_pixmap = flying_pixmap.scaled(
                pet_config.size, pet_config.size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

        # 从当前资源包加载休息提醒动画
        if self.current_pet_package:
            animations_dir = self.current_pet_package.animations_dir
            rest_animation_name = self.current_pet_package.meta.rest_animation
            rest_animation_path = animations_dir / rest_animation_name
            if rest_animation_path.exists():
                try:
                    self.hui_gif = QMovie(str(rest_animation_path))
                    self.hui_gif.setScaledSize(QSize(200, 159))
                except Exception as e:
                    print(f"加载休息提醒动画失败: {e}")
                    self.hui_gif = None
            else:
                # 回退到默认配置
                self.hui_gif = self.action_manager.load_rest_reminder_movie()
        else:
            # 回退到默认配置
            self.hui_gif = self.action_manager.load_rest_reminder_movie()

        self.label = QLabel(self)
        self.label.setPixmap(self.regular_pixmap)
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        self.bubble_label = QLabel(self)
        self.bubble_label.setText("注意休息！\n点击开始倒计时")
        self.bubble_label.setStyleSheet(
            """
            background-color: white;
            border: 2px solid #ccc;
            border-radius: 10px;
            padding: 8px;
            color: black;
            font-size: 12px;
            text-align: center;
            """
        )
        self.bubble_label.installEventFilter(self)
        self.bubble_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        pet_width = self.regular_pixmap.width()
        bubble_width = 120
        x_pos = (pet_width - bubble_width) // 2
        y_pos = 25
        self.bubble_label.move(x_pos, y_pos)
        self.bubble_label.hide()

        original_width = self.regular_pixmap.width()
        increased_width = original_width + 100
        self.resize(increased_width, self.regular_pixmap.height())
        
        self.label.move(0, 0)
        
        bubble_width = 120
        x_pos = 10
        y_pos = 10
        self.bubble_label.move(x_pos, y_pos)

        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        x = 100
        y = screen_geometry.height() - self.height()
        self.move(x, y)
        self.switch_to_static(self.regular_pixmap)

        self.is_dragging = False
        self.drag_position = QPoint()
        self.setMouseTracking(True)
        self.show()

    def start_random_movement_timer(self):
        movement_config = self.config_manager.movement
        random_interval = random.randint(
            movement_config.random_interval_min_ms,
            movement_config.random_interval_max_ms
        )
        self.movement_timer.start(random_interval)

    def show_rest_bubble(self):
        self.bubble_label.setText("注意休息！\n点击开始倒计时")
        bubble_width = 120
        x_pos = 10
        y_pos = 10
        self.bubble_label.move(x_pos, y_pos)
        self.bubble_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.bubble_label.show()

        self.state = PetState.REST_REMINDER
        self.movement_timer.stop()

        if self.motion_controller.get_mode() == "motion":
            self.motion_controller.pause_motion()

        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()

        if self.hui_gif and self.hui_gif.isValid():
            self.label.setMovie(self.hui_gif)
            self.hui_gif.start()
            self.current_gif = self.hui_gif

    def bubble_clicked(self, event=None):
        was_motion_mode = self.motion_controller.get_mode() == "motion"

        self.rest_timer.stop()

        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()

        self.switch_to_static()
        self.state = PetState.IDLE

        rest_config = self.config_manager.rest_reminder
        self.countdown_seconds = rest_config.countdown_seconds
        self.bubble_label.setText(f"休息倒计时: {self.countdown_seconds}")
        self.countdown_timer.start(1000)

        if was_motion_mode:
            self.motion_controller.resume_motion()

    def update_countdown(self):
        self.countdown_seconds -= 1
        if self.countdown_seconds > 0:
            self.bubble_label.setText(f"休息倒计时: {self.countdown_seconds}")
        else:
            self.countdown_timer.stop()
            self.bubble_label.setText("休息一下吧！")
            QTimer.singleShot(2000, self.restart_rest_timer)

    def update_rest_timer_display(self):
        self.rest_timer_seconds = max(0, self.rest_timer_seconds - 1)

    def restart_rest_timer(self):
        self.bubble_label.hide()
        self.bubble_label.setText("注意休息！\n点击开始倒计时")
        rest_config = self.config_manager.rest_reminder
        self.rest_timer_seconds = rest_config.interval_minutes * 60
        self.rest_timer.start(rest_config.interval_minutes * 60 * 1000)

    def switch_to_gif(self, direction: str = 'right'):
        if self.state == PetState.REST_REMINDER:
            print("休息提醒状态下不执行GIF切换")
            return
        
        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()
        
        print(f"切换到{direction} GIF")
        target_gif = self.walk_left_gif if direction == 'left' else self.walk_right_gif
        
        if target_gif and target_gif.isValid():
            print("显示目标GIF")
            self.label.setMovie(target_gif)
            target_gif.start()
            self.current_gif = target_gif
        else:
            print("目标GIF不存在或无效，切换到静态图像")
            self.switch_to_static()

    def switch_to_static(self, pixmap: QPixmap | None = None):
        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()

        if pixmap is None:
            pixmap = self.regular_pixmap
        self.label.setPixmap(pixmap)
        
        if self.state != PetState.REST_REMINDER:
            self.state = PetState.IDLE
            self.start_random_movement_timer()
    
    def play_animation_action(self, action: ActionConfig):
        if self.state == PetState.REST_REMINDER:
            print("休息提醒状态下不执行动画")
            return

        self.movement_timer.stop()

        self._disconnect_current_gif_signals()

        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()

        print(f"播放动画: {action.name}")

        movie = self._load_pet_animation(action.name)
        if movie and movie.isValid():
            print(f"显示动画GIF: {action.name}")
            self.label.setMovie(movie)

            self.current_animation_type = action.name
            self.current_action = action

            movie.finished.connect(self._on_animation_finished)
            movie.frameChanged.connect(self._check_gif_finished)

            self.previous_frame = -1
            self.gif_played_once = False

            movie.start()
            self.current_gif = movie
        else:
            print(f"动画GIF不存在，显示静态图像")
            self.switch_to_static()
            self.start_random_movement_timer()

    def _load_pet_animation(self, action_name: str) -> QMovie | None:
        if not self.current_pet_package:
            return None

        animations_dir = self.current_pet_package.animations_dir

        pet_action = None
        for action in self.current_pet_package.actions:
            if action.name == action_name:
                pet_action = action
                break

        if not pet_action or not pet_action.animation_files:
            return None

        animation_file = pet_action.animation_files[0]
        animation_path = animations_dir / animation_file

        if not animation_path.exists():
            return None

        try:
            movie = QMovie(str(animation_path))
            movie.setScaledSize(QSize(200, 159))
            return movie
        except Exception as e:
            print(f"加载动画失败 {animation_path}: {e}")
            return None
    
    def _disconnect_current_gif_signals(self):
        if self.current_gif:
            try:
                self.current_gif.finished.disconnect()
            except TypeError:
                pass
            try:
                self.current_gif.frameChanged.disconnect()
            except TypeError:
                pass
    
    def _on_animation_finished(self):
        action_name = self.current_animation_type
        print(f"动画播放完毕: {action_name}")
        
        self._disconnect_current_gif_signals()
        self.switch_to_static()
        self.start_random_movement_timer()

    def _check_gif_finished(self):
        if self.current_gif:
            frame_count = self.current_gif.frameCount()
            current_frame = self.current_gif.currentFrameNumber()
            
            if hasattr(self, 'previous_frame') and frame_count > 0:
                if not self.gif_played_once and (
                    current_frame == frame_count or 
                    (self.previous_frame > current_frame and self.previous_frame > 0)
                ):
                    self.gif_played_once = True
                    self._on_animation_finished()
            
            self.previous_frame = current_frame

    def execute_movement_action(self, action: ActionConfig):
        if self.state == PetState.IDLE:
            screen = QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry()

            direction = random.choice([-1, 1])
            print(f"随机移动方向: {direction}")

            config = action.config
            min_dist = config.get("min_distance", 30)
            max_dist = config.get("max_distance", 100)
            move_distance = random.randint(min_dist, max_dist)
            
            current_x = self.x()
            new_x = current_x + (direction * move_distance)

            pet_width = self.width()
            min_x = 0
            max_x = screen_geometry.width() - pet_width
            new_x = max(min_x, min(new_x, max_x))
            
            y = screen_geometry.height() - self.height()
            
            if direction < 0:
                self.switch_to_gif('left')
            else:
                self.switch_to_gif('right')

            self.start_smooth_move(current_x, new_x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.previous_pos = event.globalPosition().toPoint()
            self.state = PetState.DRAGGING
            self._press_time = event.timestamp()
            if hasattr(self, 'inertia_timer') and self.inertia_timer:
                self.inertia_timer.stop()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.is_dragging:
            new_x = event.globalPosition().toPoint().x() - self.drag_position.x()
            old_x = self.x()

            if new_x < old_x:
                self.switch_to_gif('left')
            elif new_x > old_x:
                self.switch_to_gif('right')

            self.move(event.globalPosition().toPoint() - self.drag_position)
            self.previous_pos = event.globalPosition().toPoint()
            event.accept()

    def snap_to_edge(self):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        pet_geometry = self.geometry()

        x = pet_geometry.x()
        width = pet_geometry.width()

        min_x = 0
        max_x = screen_geometry.width() - width
        x = max(min_x, min(x, max_x))

        y = screen_geometry.height() - pet_geometry.height()

        self.move(x, y)
        self.switch_to_static(self.regular_pixmap)
        self.state = PetState.IDLE

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            self.state = PetState.INERTIA

            press_time = getattr(self, '_press_time', 0)
            release_time = event.timestamp()
            click_duration = release_time - press_time
            is_click = click_duration < 200

            current_pos = event.globalPosition().toPoint()
            pos_diff = current_pos - self.previous_pos
            velocity_x = pos_diff.x() / 2
            velocity_y = pos_diff.y() / 2

            if is_click and self._click_detection_enabled:
                pet_pos = self.frameGeometry().topLeft()
                click_x = (current_pos.x() - pet_pos.x()) / self.width()
                click_y = (current_pos.y() - pet_pos.y()) / self.height()
                zone_name = self._detect_click_zone(click_x, click_y)
                if zone_name:
                    self._play_zone_animation(zone_name)
                    event.accept()
                    return

            self.start_inertia(velocity_x, velocity_y)

            if velocity_x < 0:
                self.switch_to_gif('left')
            elif velocity_x > 0:
                self.switch_to_gif('right')
            else:
                self.switch_to_static()

            event.accept()

    def contextMenuEvent(self, event):
        context_menu = QMenu(self)

        switch_pet_menu = QMenu('切换桌宠', self)
        available_pets = self.pet_loader.scan_pets()
        for pet in available_pets:
            pet_action = QAction(pet.meta.name, self)
            pet_action.triggered.connect(lambda checked, p=pet: self._switch_to_pet(p))
            switch_pet_menu.addAction(pet_action)
        context_menu.addMenu(switch_pet_menu)

        context_menu.addSeparator()

        motion_mode_menu = QMenu('运动模式', self)

        current_mode = self.motion_controller.get_mode()
        if current_mode == "random":
            switch_to_motion_action = QAction('切换到运动模式', self)
            switch_to_motion_action.triggered.connect(self._switch_to_motion_mode)
            motion_mode_menu.addAction(switch_to_motion_action)
        else:
            switch_to_random_action = QAction('切换到随机模式', self)
            switch_to_random_action.triggered.connect(self._switch_to_random_mode)
            motion_mode_menu.addAction(switch_to_random_action)

        open_control_panel_action = QAction('打开控制面板', self)
        open_control_panel_action.triggered.connect(self._open_motion_control_panel)
        motion_mode_menu.addAction(open_control_panel_action)

        motion_mode_menu.addSeparator()

        if self.api_server.is_running:
            stop_api_action = QAction('停止 API 服务器', self)
            stop_api_action.triggered.connect(self._stop_api_server)
            motion_mode_menu.addAction(stop_api_action)
        else:
            start_api_action = QAction('启动 API 服务器', self)
            start_api_action.triggered.connect(self._start_api_server)
            motion_mode_menu.addAction(start_api_action)

        context_menu.addMenu(motion_mode_menu)

        context_menu.addSeparator()

        action_manager_action = QAction('动作管理', self)
        action_manager_action.triggered.connect(self.open_action_manager)
        context_menu.addAction(action_manager_action)

        context_menu.addSeparator()

        exit_action = QAction('退出', self)
        exit_action.triggered.connect(self.exit_app)
        context_menu.addAction(exit_action)

        context_menu.exec(event.globalPos())

    def _switch_to_pet(self, pet_package: PetPackage) -> None:
        self.current_pet_package = pet_package
        self.pet_loader.set_current_pet(pet_package)
        self.config_manager.set_current_pet(pet_package.name)

        self._load_pet_animations()
        
        # 重新加载静态图片
        pet_config = self.config_manager.pet
        animations_dir = self.current_pet_package.animations_dir
        
        # 加载常规图片
        regular_image_name = self.current_pet_package.meta.regular_image
        regular_image_path = animations_dir / regular_image_name
        if not regular_image_path.exists():
            regular_image_path = self.assets_path / pet_config.regular_image
        
        img = Image.open(regular_image_path)
        # 使用资源包的 animations 目录保存临时文件
        temp_path = animations_dir / 'temp_fixed.png'
        img.save(temp_path, icc_profile=None)

        regular_pixmap = QPixmap(str(regular_image_path))
        self.regular_pixmap = regular_pixmap.scaled(
            pet_config.size, pet_config.size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        # 加载飞行图片
        flying_image_name = self.current_pet_package.meta.flying_image
        flying_image_path = animations_dir / flying_image_name
        if not flying_image_path.exists():
            flying_image_path = self.assets_path / pet_config.flying_image
        
        try:
            flying_img = Image.open(flying_image_path)
            # 使用资源包的 animations 目录保存临时文件
            temp_flying_path = animations_dir / 'temp_flying_fixed.png'
            flying_img.save(temp_flying_path, icc_profile=None)
            flying_pixmap = QPixmap(str(flying_image_path))
        except Exception:
            flying_pixmap = QPixmap(str(flying_image_path))
        self.flying_pixmap = flying_pixmap.scaled(
            pet_config.size, pet_config.size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()

        if self.idle_gif and self.idle_gif.isValid():
            self.label.setMovie(self.idle_gif)
            self.idle_gif.start()
            self.current_gif = self.idle_gif
        else:
            self.switch_to_static(self.regular_pixmap)

        print(f"已切换到桌宠: {pet_package.meta.name}")

    def open_action_manager(self):
        dialog = ActionManagerGUI(self.config_manager, self.current_pet_package, self)
        dialog.exec()

    def _switch_to_motion_mode(self):
        self.motion_controller.set_mode("motion")

    def _switch_to_random_mode(self):
        self.motion_controller.set_mode("random")

    def _on_set_mode_requested(self, mode: str):
        old_mode = self.motion_controller._mode
        self.motion_controller._mode = mode

        if mode == "random":
            self.movement_timer.stop()
            if self.current_gif and self.current_gif.state() == 1:
                self.current_gif.stop()
            self.switch_to_static()
            self.state = PetState.IDLE
            self.start_random_movement_timer()
        else:
            self.movement_timer.stop()
            self.state = PetState.MOTION_MODE

    def _on_move_to_requested(self, x: int, y: int):
        screen = self._get_screen_geometry()
        pet_width = self.width()
        pet_height = self.height()

        x = max(0, min(x, screen.width() - pet_width))
        y = max(0, min(y, screen.height() - pet_height))

        current_x = self.x()
        current_y = self.y()

        if x < current_x:
            self.switch_to_gif('left')
        elif x > current_x:
            self.switch_to_gif('right')

        self.start_smooth_move(current_x, x, y)

    def _on_move_by_requested(self, dx: int, dy: int):
        current_x = self.x()
        current_y = self.y()
        self._on_move_to_requested(current_x + dx, current_y + dy)

    def _on_move_to_edge_requested(self, edge: str):
        screen = self._get_screen_geometry()
        pet_width = self.width()
        current_y = self.y()

        if edge == "left":
            self._on_move_to_requested(0, current_y)
        elif edge == "right":
            self._on_move_to_requested(screen.width() - pet_width, current_y)

    def _on_play_animation_requested(self, name: str):
        action = self.current_pet_package.actions if self.current_pet_package else []
        found_action = None
        for a in action:
            if a.name == name:
                found_action = a
                break
        if found_action:
            self.play_animation_action(found_action)

    def _on_play_walk_requested(self, direction: str):
        screen = self._get_screen_geometry()
        current_x = self.x()
        pet_width = self.width()

        if direction == "left":
            target_x = 0
        else:
            target_x = screen.width() - pet_width

        self.switch_to_gif(direction)
        self.start_smooth_move(current_x, target_x, self.y())

    def _on_stop_animation_requested(self):
        if self.current_gif and self.current_gif.state() == 1:
            self.current_gif.stop()
        self.switch_to_static()
        self.state = PetState.MOTION_MODE

    def _open_motion_control_panel(self):
        panel = MotionControlPanel(self, self)
        panel.exec()

    def _start_api_server(self):
        if not self.api_server.is_running:
            import threading
            thread = threading.Thread(target=self._run_api_server_async, daemon=True)
            thread.start()

    def _run_api_server_async(self):
        self._api_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._api_loop)
        self._api_loop.run_until_complete(self.api_server.start())
        self._api_loop.run_forever()

    def _stop_api_server(self):
        if self.api_server.is_running:
            import threading
            thread = threading.Thread(target=self._run_api_server_stop_async, daemon=True)
            thread.start()

    def _run_api_server_stop_async(self):
        if self._api_loop and self._api_loop.is_running():
            self._api_loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.api_server.stop())
            )

    def exit_app(self):
        QApplication.quit()

    def _get_screen_geometry(self):
        screen = QApplication.primaryScreen()
        return screen.availableGeometry()

    @property
    def api(self):
        return self.motion_controller

    def eventFilter(self, obj, event):
        if obj == self.bubble_label and event.type() == event.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self.bubble_clicked(None)
                return True
        return super().eventFilter(obj, event)

    def start_inertia(self, velocity_x, velocity_y):
        self.inertia_velocity_x = velocity_x
        self.inertia_velocity_y = velocity_y

        if velocity_x < 0:
            self.switch_to_gif('left')
        else:
            self.switch_to_static()

        self.inertia_timer = QTimer()
        self.inertia_timer.timeout.connect(self.apply_inertia)
        self.inertia_timer.start(16)

    def apply_inertia(self):
        self.inertia_velocity_x *= 0.92
        self.inertia_velocity_y *= 0.92

        new_x = self.x() + int(self.inertia_velocity_x)
        new_y = self.y() + int(self.inertia_velocity_y)

        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        pet_width = self.width()
        pet_height = self.height()

        new_x = max(0, min(new_x, screen_geometry.width() - pet_width))
        new_y = max(0, min(new_y, screen_geometry.height() - pet_height))

        self.move(new_x, new_y)

        if abs(self.inertia_velocity_x) < 0.5 and abs(self.inertia_velocity_y) < 0.5:
            self.inertia_timer.stop()
            screen = QApplication.primaryScreen()
            if self.y() < screen.availableGeometry().height() / 2:
                self.start_gravity_fall()
            else:
                self.snap_to_edge()
                if self.state != PetState.FALLING:
                    self.state = PetState.IDLE
                    self.start_random_movement_timer()
        elif new_y >= screen_geometry.height() - pet_height and self.inertia_velocity_y > 0:
            self.inertia_timer.stop()
            self.switch_to_static(self.regular_pixmap)
            self.snap_to_edge()
            self.state = PetState.IDLE
            self.start_random_movement_timer()

    def start_gravity_fall(self):
        self.state = PetState.FALLING
        self.switch_to_static(self.flying_pixmap)

        self.gravity_timer = QTimer()
        self.gravity_timer.timeout.connect(self.apply_gravity)
        self.current_fall_speed = 1
        self.gravity_timer.start(30)

    def apply_gravity(self):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        current_y = self.y()
        new_y = current_y + self.current_fall_speed

        bottom_y = screen_geometry.height() - self.height()

        if new_y >= bottom_y:
            self.move(self.x(), bottom_y)
            self.gravity_timer.stop()
            self.switch_to_static(self.regular_pixmap)
            self.state = PetState.IDLE
        else:
            self.current_fall_speed = min(self.current_fall_speed + 0.5, 10)
            self.move(self.x(), int(new_y))

    def random_move(self):
        if self.state != PetState.IDLE:
            return

        if self.motion_controller.get_mode() == "motion":
            return

        if not self.current_pet_package:
            print("没有加载的桌宠资源包")
            return

        enabled_actions = [a for a in self.current_pet_package.actions if a.enabled]
        if not enabled_actions:
            print("没有可用的动作")
            return

        total_weight = sum(a.weight for a in enabled_actions)
        if total_weight <= 0:
            action = random.choice(enabled_actions)
        else:
            r = random.uniform(0, total_weight)
            current_weight = 0
            action = enabled_actions[-1]
            for a in enabled_actions:
                current_weight += a.weight
                if r <= current_weight:
                    action = a
                    break

        print(f"随机行为: {action.name}")

        if action.type == "movement":
            self.execute_movement_action_from_pet(action)
        elif action.type == "animation":
            self.play_animation_action_from_pet(action)
        else:
            print(f"未知动作类型: {action.type}")

    def execute_movement_action_from_pet(self, action):
        if self.state == PetState.IDLE:
            screen = QApplication.primaryScreen()
            screen_geometry = screen.availableGeometry()

            direction = random.choice([-1, 1])
            print(f"随机移动方向: {direction}")

            min_dist = action.config.get("min_distance", 30)
            max_dist = action.config.get("max_distance", 100)
            move_distance = random.randint(min_dist, max_dist)

            current_x = self.x()
            new_x = current_x + (direction * move_distance)

            pet_width = self.width()
            min_x = 0
            max_x = screen_geometry.width() - pet_width
            new_x = max(min_x, min(new_x, max_x))

            y = screen_geometry.height() - self.height()

            if direction < 0:
                self.switch_to_gif('left')
            else:
                self.switch_to_gif('right')

            self.start_smooth_move(current_x, new_x, y)

    def play_animation_action_from_pet(self, action):
        if self.state == PetState.REST_REMINDER:
            print("休息提醒状态下不执行动画")
            return

        self.movement_timer.stop()

        self._disconnect_current_gif_signals()

        if self.current_gif and self.current_gif.state() == QMovie.MovieState.Running:
            self.current_gif.stop()

        print(f"播放动画: {action.name}")

        movie = self._load_pet_animation(action.name)
        if movie and movie.isValid():
            print(f"显示动画GIF: {action.name}")
            self.label.setMovie(movie)

            self.current_animation_type = action.name
            self.current_action = action

            movie.finished.connect(self._on_animation_finished)
            movie.frameChanged.connect(self._check_gif_finished)

            self.previous_frame = -1
            self.gif_played_once = False

            movie.start()
            self.current_gif = movie
        else:
            print(f"动画GIF不存在，显示静态图像")
            self.switch_to_static()
            self.start_random_movement_timer()

    def start_smooth_move(self, start_x, end_x, y):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        y = screen_geometry.height() - self.height()

        self.animation_start_x = start_x
        self.animation_end_x = end_x
        self.animation_current_y = y

        distance = abs(end_x - start_x)
        pixels_per_step = 1

        if distance == 0:
            self.animation_total_steps = 1
        else:
            self.animation_total_steps = max(1, int(distance / pixels_per_step))

        self.animation_step = 0

        if not hasattr(self, 'animation_timer'):
            self.animation_timer = QTimer()
            self.animation_timer.timeout.connect(self.animate_move)
        self.animation_timer.start(20)

    def animate_move(self):
        if self.animation_step < self.animation_total_steps:
            progress = self.animation_step / self.animation_total_steps
            eased_progress = 1 - (1 - progress) ** 2
            current_x = self.animation_start_x + (self.animation_end_x - self.animation_start_x) * eased_progress
            self.move(int(current_x), self.animation_current_y)
            self.animation_step += 1
        else:
            self.animation_timer.stop()
            self.move(self.animation_end_x, self.animation_current_y)
            self.switch_to_static()
            self.state = PetState.IDLE
            self.start_random_movement_timer()
