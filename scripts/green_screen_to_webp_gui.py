#!/usr/bin/env python3
"""
绿幕视频转透明WebP工具 - GUI版本

提供可视化界面，支持实时预览、绿幕抠像、去除水印、底部裁切以及无缝循环。

使用方法:
    uv run python scripts/green_screen_to_webp_gui.py
"""

import sys
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QSpinBox, QDoubleSpinBox,
    QFileDialog, QGroupBox, QProgressBar, QMessageBox, QCheckBox,
    QFrame, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImage

# 添加脚本目录到路径以导入锚点检测模块
sys.path.insert(0, str(Path(__file__).parent))
from anchor_detector import AnchorDetector
from alignment_processor import AlignmentProcessor
from typing import Optional


def detect_green_screen_color(frame: np.ndarray) -> tuple[int, int, int]:
    h, w = frame.shape[:2]
    margin = min(h, w) // 10
    
    top_edge = frame[:margin, :]
    bottom_edge = frame[-margin:, :]
    left_edge = frame[:, :margin]
    right_edge = frame[:, -margin:]
    
    edge_pixels = np.vstack([
        top_edge.reshape(-1, 3),
        bottom_edge.reshape(-1, 3),
        left_edge.reshape(-1, 3),
        right_edge.reshape(-1, 3)
    ])
    
    median_color = np.median(edge_pixels, axis=0).astype(int)
    return tuple(median_color)


def remove_green_screen(
    frame: np.ndarray,
    green_color: tuple[int, int, int],
    tolerance: int = 30,
    softness: int = 10,
    watermark_regions: list = None
) -> np.ndarray:
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
    green_b, green_g, green_r = green_color
    
    lower_green = np.array([
        max(0, green_b - tolerance),
        max(0, green_g - tolerance),
        max(0, green_r - tolerance)
    ])
    upper_green = np.array([
        min(255, green_b + tolerance),
        min(255, green_g + tolerance),
        min(255, green_r + tolerance)
    ])
    
    mask = cv2.inRange(frame, lower_green, upper_green)
    
    if softness > 0:
        mask = cv2.GaussianBlur(mask, (softness * 2 + 1, softness * 2 + 1), 0)
        _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    
    mask_inv = 255 - mask
    
    if watermark_regions:
        for region in watermark_regions:
            x1, y1, x2, y2 = region
            # 直接将水印区域的透明度遮罩设为0（完全透明）
            mask_inv[y1:y2, x1:x2] = 0
    
    rgba = np.zeros((frame.shape[0], frame.shape[1], 4), dtype=np.uint8)
    rgba[:, :, :3] = frame_rgb
    rgba[:, :, 3] = mask_inv
    
    return rgba


def numpy_to_qpixmap(rgba: np.ndarray) -> QPixmap:
    h, w, ch = rgba.shape
    bytes_per_line = ch * w
    qimage = QImage(rgba.data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimage)


def draw_anchor_cross(
    rgba: np.ndarray,
    anchor_x_ratio: float,
    anchor_y_ratio: float,
    color: tuple = (255, 0, 0, 255),
    size: int = 10
) -> np.ndarray:
    """
    在帧上绘制锚点十字线

    Args:
        rgba: RGBA 帧
        anchor_x_ratio: 锚点 X 归一化坐标
        anchor_y_ratio: 锚点 Y 归一化坐标
        color: 十字线颜色 (R, G, B, A)
        size: 十字线臂长（像素）

    Returns:
        带十字线的帧副本
    """
    result = rgba.copy()
    h, w = result.shape[:2]

    anchor_x = int(anchor_x_ratio * w)
    anchor_y = int(anchor_y_ratio * h)

    # 绘制水平线
    x1, x2 = max(0, anchor_x - size), min(w, anchor_x + size)
    result[anchor_y, x1:x2] = color

    # 绘制垂直线
    y1, y2 = max(0, anchor_y - size), min(h, anchor_y + size)
    result[y1:y2, anchor_x] = color

    return result


class VideoProcessor(QThread):
    frame_ready = pyqtSignal(np.ndarray, np.ndarray)
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list, float)
    error = pyqtSignal(str)
    
    def __init__(self, video_path: str, params: dict):
        super().__init__()
        self.video_path = video_path
        self.params = params
        self.reference_info = params.get('reference_info', {})
        self.enable_alignment = params.get('enable_alignment', False)
        self._is_cancelled = False
    
    def cancel(self):
        self._is_cancelled = True
    
    def run(self):
        try:
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                self.error.emit(f"无法打开视频文件: {self.video_path}")
                return
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            original_fps = cap.get(cv2.CAP_PROP_FPS)
            original_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            original_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            green_color = self.params.get('green_color')
            auto_detect = self.params.get('auto_detect', True)
            tolerance = self.params.get('tolerance', 30)
            softness = self.params.get('softness', 5)
            width = self.params.get('width')
            height = self.params.get('height')
            scale = self.params.get('scale', 1.0)
            start_frame = self.params.get('start_frame', 0)
            end_frame = self.params.get('end_frame', total_frames)
            output_fps = self.params.get('fps', original_fps)
            watermark_regions = self.params.get('watermark_regions', [])
            crop_bottom = self.params.get('crop_bottom', 0)
            
            # 计算裁切后的实际工作高度
            if crop_bottom >= original_height:
                crop_bottom = 0
            working_height = original_height - crop_bottom
            
            if width is None and height is None:
                width = int(original_width * scale)
                height = int(working_height * scale)
            elif width is None:
                width = int(original_width * height / working_height)
            elif height is None:
                height = int(working_height * width / original_width)
            
            scale_x = width / original_width
            scale_y = height / working_height
            
            # 按比例缩放水印区域坐标
            scaled_watermarks = []
            for region in watermark_regions:
                x1, y1, x2, y2 = region
                scaled_watermarks.append((
                    int(x1 * scale_x), int(y1 * scale_y),
                    int(x2 * scale_x), int(y2 * scale_y)
                ))
            
            detected_green = None
            frames = []
            
            frame_skip_ratio = original_fps / output_fps if output_fps > 0 else 1.0
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            
            frame_count = 0
            next_sample_frame = 0.0
            
            while not self._is_cancelled:
                ret, frame = cap.read()
                if not ret:
                    break
                
                current_frame = start_frame + frame_count
                if current_frame >= end_frame:
                    break
                
                # 执行底部裁切 (在处理前直接切掉画面底部)
                if crop_bottom > 0:
                    frame = frame[:-crop_bottom, :]
                
                should_sample = frame_count >= next_sample_frame
                if should_sample:
                    next_sample_frame += frame_skip_ratio
                
                if auto_detect and detected_green is None and should_sample:
                    detected_green = detect_green_screen_color(frame)
                
                use_green = green_color if green_color else detected_green
                
                if should_sample:
                    rgba = remove_green_screen(frame, use_green, tolerance, softness, watermark_regions)
                    
                    if width != original_width or height != working_height:
                        rgba = cv2.resize(rgba, (width, height), interpolation=cv2.INTER_AREA)
                        # 原地处理水印区域（resize后无需再复制）
                        if scaled_watermarks:
                            for region in scaled_watermarks:
                                x1, y1, x2, y2 = region
                                rgba[y1:y2, x1:x2, 3] = 0

                    original_bgr = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

                    self.frame_ready.emit(original_bgr, rgba)
                    frames.append(rgba)  # 直接append，无需copy
                
                self.progress.emit(frame_count, min(end_frame - start_frame, total_frames - start_frame))
                frame_count += 1
            
            cap.release()

            if not self._is_cancelled:
                # 如果启用了锚点对齐，处理帧对齐
                if self.enable_alignment and self.reference_info and frames:
                    # 检测当前动画的锚点
                    detector = AnchorDetector()
                    src_anchor = detector.detect(frames)

                    # 创建对齐处理器
                    ref_size = (self.reference_info['width'], self.reference_info['height'])
                    ref_anchor = (self.reference_info['anchor_x'], self.reference_info['anchor_y'])
                    processor = AlignmentProcessor(ref_size, ref_anchor)

                    # 对齐所有帧
                    aligned_frames = processor.align_frames(frames, src_anchor)
                    frames = aligned_frames

                self.finished.emit(frames, output_fps)
                
        except Exception as e:
            self.error.emit(str(e))


class WebPPreviewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.frames = []
        self.current_frame = 0
        self.is_playing = False
        
        self._setup_ui()
        self._setup_timer()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(200, 200)
        # 用棋盘格背景更好地展示透明通道
        self.label.setStyleSheet("""
            background-color: #eee;
            background-image: linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc),
                              linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc);
            background-size: 20px 20px;
            background-position: 0 0, 10px 10px;
            border: 1px solid #555;
        """)
        layout.addWidget(self.label)
    
    def _setup_timer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self._next_frame)
    
    def set_frames(self, frames: list, fps: float = 10.0):
        self.frames = frames
        self.current_frame = 0
        if frames:
            self._show_frame(0)
            self.timer.setInterval(int(1000 / fps))
    
    def _show_frame(self, index: int):
        if 0 <= index < len(self.frames):
            rgba = self.frames[index]
            pixmap = numpy_to_qpixmap(rgba)
            self.label.setPixmap(pixmap.scaled(
                self.label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
    
    def _next_frame(self):
        if self.frames:
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            self._show_frame(self.current_frame)
    
    def play(self):
        if self.frames:
            self.is_playing = True
            self.timer.start()
    
    def stop(self):
        self.is_playing = False
        self.timer.stop()
    
    def clear(self):
        self.frames = []
        self.current_frame = 0
        self.label.clear()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("绿幕视频转动态 WebP 工具")
        self.setMinimumSize(1000, 750)
        
        self.video_path = None
        self.video_info = {}
        self.processor = None
        self.processed_frames = []
        self.output_fps = 30.0
        self.watermark_regions = []
        self.show_anchor_overlay = False  # 修复：定义未使用的变量
        self.reference_info = {}  # 修复：定义未初始化的变量

        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        left_panel = self._create_left_panel()
        splitter.addWidget(left_panel)
        
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([450, 550])
    
    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # --- 文件选择 ---
        file_group = QGroupBox("文件选择")
        file_layout = QVBoxLayout(file_group)
        self.file_label = QLabel("未选择文件")
        self.file_label.setWordWrap(True)
        file_layout.addWidget(self.file_label)
        self.select_btn = QPushButton("📂 选择视频文件")
        file_layout.addWidget(self.select_btn)
        layout.addWidget(file_group)
        
        # --- 参数设置 ---
        params_group = QGroupBox("抠像与尺寸参数")
        params_layout = QVBoxLayout(params_group)
        
        tolerance_layout = QHBoxLayout()
        tolerance_layout.addWidget(QLabel("绿幕容差:"))
        self.tolerance_spin = QSpinBox()
        self.tolerance_spin.setRange(1, 100); self.tolerance_spin.setValue(30)
        tolerance_layout.addWidget(self.tolerance_spin)
        params_layout.addLayout(tolerance_layout)
        
        softness_layout = QHBoxLayout()
        softness_layout.addWidget(QLabel("边缘柔和度:"))
        self.softness_spin = QSpinBox()
        self.softness_spin.setRange(0, 20); self.softness_spin.setValue(5)
        softness_layout.addWidget(self.softness_spin)
        params_layout.addLayout(softness_layout)
        
        crop_layout = QHBoxLayout()
        crop_layout.addWidget(QLabel("截掉底部区域 (像素):"))
        self.crop_bottom_spin = QSpinBox()
        self.crop_bottom_spin.setRange(0, 2000); self.crop_bottom_spin.setValue(0)
        crop_layout.addWidget(self.crop_bottom_spin)
        params_layout.addLayout(crop_layout)
        
        size_group = QGroupBox("输出尺寸")
        size_layout = QVBoxLayout(size_group)
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("缩放比例:"))
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.1, 2.0); self.scale_spin.setValue(1.0); self.scale_spin.setSingleStep(0.1)
        scale_layout.addWidget(self.scale_spin)
        size_layout.addLayout(scale_layout)
        custom_size_layout = QHBoxLayout()
        custom_size_layout.addWidget(QLabel("自定义宽高:"))
        self.width_spin = QSpinBox(); self.width_spin.setRange(0, 2000); self.width_spin.setSpecialValueText("自动")
        self.height_spin = QSpinBox(); self.height_spin.setRange(0, 2000); self.height_spin.setSpecialValueText("自动")
        custom_size_layout.addWidget(self.width_spin)
        custom_size_layout.addWidget(QLabel("x"))
        custom_size_layout.addWidget(self.height_spin)
        size_layout.addLayout(custom_size_layout)
        params_layout.addWidget(size_group)
        
        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("输出帧率:"))
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(1.0, 120.0); self.fps_spin.setValue(30.0) # WebP建议默认30帧
        fps_layout.addWidget(self.fps_spin)
        params_layout.addLayout(fps_layout)

        # --- WebP 压缩设置 ---
        compress_group = QGroupBox("文件压缩")
        compress_layout = QVBoxLayout(compress_group)

        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("压缩质量:"))
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(90)
        self.quality_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.quality_slider.setTickInterval(25)
        quality_layout.addWidget(self.quality_slider)
        self.quality_label = QLabel("90%")
        self.quality_label.setMinimumWidth(35)
        quality_layout.addWidget(self.quality_label)
        compress_layout.addLayout(quality_layout)

        # 连接质量滑块到标签更新
        self.quality_slider.valueChanged.connect(
            lambda v: self.quality_label.setText(f"{v}%")
        )

        target_size_layout = QHBoxLayout()
        target_size_layout.addWidget(QLabel("目标文件大小:"))
        self.target_size_spin = QSpinBox()
        self.target_size_spin.setRange(0, 10000)
        self.target_size_spin.setValue(0)
        self.target_size_spin.setSpecialValueText("不限制")
        target_size_layout.addWidget(self.target_size_spin)
        target_size_layout.addWidget(QLabel("KB"))
        compress_layout.addLayout(target_size_layout)

        compress_hint = QLabel("💡 降低质量或设置目标大小可减小文件")
        compress_hint.setStyleSheet("color: #666; font-size: 10pt;")
        compress_layout.addWidget(compress_hint)

        params_layout.addWidget(compress_group)

        loop_layout = QHBoxLayout()
        self.loop_check = QCheckBox("🔄 循环播放（添加反向帧）")
        self.loop_check.setChecked(True)
        loop_layout.addWidget(self.loop_check)
        params_layout.addLayout(loop_layout)
        
        layout.addWidget(params_group)
        
        # --- 水印去除 ---
        watermark_group = QGroupBox("局部透明化 (用于去水印)")
        watermark_layout = QVBoxLayout(watermark_group)
        
        self.remove_topleft_check = QCheckBox("去除左上角区域")
        watermark_layout.addWidget(self.remove_topleft_check)
        topleft_layout = QHBoxLayout()
        topleft_layout.addWidget(QLabel("尺寸: 宽"))
        self.topleft_width_spin = QSpinBox(); self.topleft_width_spin.setRange(0, 500); self.topleft_width_spin.setValue(100)
        topleft_layout.addWidget(self.topleft_width_spin)
        topleft_layout.addWidget(QLabel("高"))
        self.topleft_height_spin = QSpinBox(); self.topleft_height_spin.setRange(0, 500); self.topleft_height_spin.setValue(50)
        topleft_layout.addWidget(self.topleft_height_spin)
        watermark_layout.addLayout(topleft_layout)
        
        self.remove_bottomright_check = QCheckBox("去除右下角区域")
        watermark_layout.addWidget(self.remove_bottomright_check)
        bottomright_layout = QHBoxLayout()
        bottomright_layout.addWidget(QLabel("尺寸: 宽"))
        self.bottomright_width_spin = QSpinBox(); self.bottomright_width_spin.setRange(0, 500); self.bottomright_width_spin.setValue(100)
        bottomright_layout.addWidget(self.bottomright_width_spin)
        bottomright_layout.addWidget(QLabel("高"))
        self.bottomright_height_spin = QSpinBox(); self.bottomright_height_spin.setRange(0, 500); self.bottomright_height_spin.setValue(50)
        bottomright_layout.addWidget(self.bottomright_height_spin)
        watermark_layout.addLayout(bottomright_layout)
        
        layout.addWidget(watermark_group)
        
        # --- 帧范围 ---
        frame_group = QGroupBox("截取片段")
        frame_layout = QVBoxLayout(frame_group)
        range_layout = QHBoxLayout()
        range_layout.addWidget(QLabel("起始帧:"))
        self.start_frame_spin = QSpinBox(); self.start_frame_spin.setRange(0, 99999)
        range_layout.addWidget(self.start_frame_spin)
        range_layout.addWidget(QLabel("结束帧:"))
        self.end_frame_spin = QSpinBox(); self.end_frame_spin.setRange(0, 99999); self.end_frame_spin.setValue(99999)
        range_layout.addWidget(self.end_frame_spin)
        frame_layout.addLayout(range_layout)
        layout.addWidget(frame_group)
        
        # --- 执行与进度 ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        action_layout = QHBoxLayout()
        self.preview_btn = QPushButton("👁 预览提取效果")
        self.preview_btn.setEnabled(False)
        self.preview_btn.setMinimumHeight(35)
        self.export_btn = QPushButton("🚀 导出动态 WebP")
        self.export_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.export_btn.setEnabled(False)
        self.export_btn.setMinimumHeight(35)
        action_layout.addWidget(self.preview_btn)
        action_layout.addWidget(self.export_btn)
        layout.addLayout(action_layout)
        
        layout.addStretch()
        return panel
    
    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        preview_group = QGroupBox("画面预览")
        preview_layout = QVBoxLayout(preview_group)
        preview_splitter = QSplitter(Qt.Orientation.Vertical)
        
        original_container = QWidget()
        original_layout = QVBoxLayout(original_container)
        original_layout.setContentsMargins(0, 0, 0, 0)
        original_layout.addWidget(QLabel("原始画面:"))
        self.original_preview = QLabel()
        self.original_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.original_preview.setMinimumSize(200, 150)
        self.original_preview.setStyleSheet("background-color: #000000;")
        original_layout.addWidget(self.original_preview)
        preview_splitter.addWidget(original_container)
        
        processed_container = QWidget()
        processed_layout = QVBoxLayout(processed_container)
        processed_layout.setContentsMargins(0, 0, 0, 0)
        processed_layout.addWidget(QLabel("处理后 (透明背景 WebP 预览):"))
        self.processed_preview = WebPPreviewWidget()
        processed_layout.addWidget(self.processed_preview)
        preview_splitter.addWidget(processed_container)
        
        preview_layout.addWidget(preview_splitter)
        layout.addWidget(preview_group)
        
        control_layout = QHBoxLayout()
        self.play_btn = QPushButton("▶ 播放")
        self.play_btn.setEnabled(False)
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.play_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        self.info_label = QLabel("请选择视频文件开始")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_label)
        
        return panel
    
    def _connect_signals(self):
        self.select_btn.clicked.connect(self._select_file)
        self.preview_btn.clicked.connect(self._start_preview)
        self.export_btn.clicked.connect(self._export_webp)
        self.play_btn.clicked.connect(self._play_preview)
        self.stop_btn.clicked.connect(self._stop_preview)
    
    def _select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择视频文件",
            "",
            "视频文件 (*.mp4 *.avi *.mov *.mkv);;所有文件 (*)"
        )
        
        if file_path:
            self.video_path = file_path
            self.file_label.setText(Path(file_path).name)
            self._load_video_info()
            self.preview_btn.setEnabled(True)
            self.export_btn.setEnabled(False)
            self.processed_preview.clear()
            self.play_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
    
    def _load_video_info(self):
        cap = cv2.VideoCapture(self.video_path)
        if cap.isOpened():
            self.video_info = {
                'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                'fps': cap.get(cv2.CAP_PROP_FPS),
                'frames': int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            }
            cap.release()
            
            self.end_frame_spin.setValue(self.video_info['frames'])
            self.fps_spin.setValue(self.video_info['fps'])
            
            self.info_label.setText(
                f"视频信息: {self.video_info['width']}x{self.video_info['height']}, "
                f"{self.video_info['fps']:.1f} FPS, {self.video_info['frames']} 帧"
            )
    
    def _get_params(self) -> dict:
        width = self.width_spin.value() if self.width_spin.value() > 0 else None
        height = self.height_spin.value() if self.height_spin.value() > 0 else None
        crop_bottom = self.crop_bottom_spin.value()
        
        watermark_regions = []
        if self.video_info:
            video_w = self.video_info.get('width', 1920)
            video_h = self.video_info.get('height', 1080)
            
            # 计算裁切后的实际画面高度，保证右下角水印坐标对准真实的底边
            effective_h = video_h - crop_bottom if crop_bottom < video_h else video_h
            
            if self.remove_topleft_check.isChecked():
                w = self.topleft_width_spin.value()
                h = self.topleft_height_spin.value()
                watermark_regions.append((0, 0, w, h))
            
            if self.remove_bottomright_check.isChecked():
                w = self.bottomright_width_spin.value()
                h = self.bottomright_height_spin.value()
                watermark_regions.append((video_w - w, effective_h - h, video_w, effective_h))
        
        return {
            'tolerance': self.tolerance_spin.value(),
            'softness': self.softness_spin.value(),
            'scale': self.scale_spin.value(),
            'width': width,
            'height': height,
            'fps': self.fps_spin.value(),
            'start_frame': self.start_frame_spin.value(),
            'end_frame': self.end_frame_spin.value(),
            'crop_bottom': crop_bottom,
            'auto_detect': True,
            'watermark_regions': watermark_regions,
            'reference_info': getattr(self, 'reference_info', {}) if getattr(self, 'enable_alignment', False) else {},
            'enable_alignment': getattr(self, 'enable_alignment', False),
        }
    
    def _start_preview(self):
        if not self.video_path:
            return
        
        if self.processor and self.processor.isRunning():
            self.processor.cancel()
            self.processor.wait()
        
        self.processed_frames = []
        self.preview_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        params = self._get_params()
        self.output_fps = params['fps']
        
        self.processor = VideoProcessor(self.video_path, params)
        self.processor.frame_ready.connect(self._on_frame_ready)
        self.processor.progress.connect(self._on_progress)
        self.processor.finished.connect(self._on_processing_finished)
        self.processor.error.connect(self._on_error)
        self.processor.start()
    
    def _on_frame_ready(self, original: np.ndarray, processed: np.ndarray):
        # 显示原始帧
        original_rgb = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)
        original_pixmap = QPixmap.fromImage(QImage(
            original_rgb.data, original_rgb.shape[1], original_rgb.shape[0],
            original_rgb.strides[0], QImage.Format.Format_RGB888
        ))
        self.original_preview.setPixmap(original_pixmap.scaled(
            self.original_preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

        # 显示处理的帧（可选带锚点叠加）
        if self.show_anchor_overlay and self.reference_info:
            ref_anchor_x = self.reference_info.get('anchor_x', 0.5)
            ref_anchor_y = self.reference_info.get('anchor_y', 0.5)
            processed = draw_anchor_cross(processed, ref_anchor_x, ref_anchor_y)

        processed_rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
        processed_pixmap = QPixmap.fromImage(QImage(
            processed_rgb.data, processed_rgb.shape[1], processed_rgb.shape[0],
            processed_rgb.strides[0], QImage.Format.Format_RGB888
        ))
        self.processed_preview.label.setPixmap(processed_pixmap.scaled(
            self.processed_preview.label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
    
    def _on_progress(self, current: int, total: int):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
    
    def _on_processing_finished(self, frames: list, fps: float):
        self.processed_frames = frames
        self.output_fps = fps
        self.progress_bar.setVisible(False)
        self.preview_btn.setEnabled(True)
        self.export_btn.setEnabled(len(frames) > 0)
        self.play_btn.setEnabled(len(frames) > 0)
        self.stop_btn.setEnabled(False)
        
        if frames:
            self.processed_preview.set_frames(frames, fps)
            self.info_label.setText(f"处理完成: {len(frames)} 帧, {fps:.1f} FPS")
    
    def _on_error(self, message: str):
        self.progress_bar.setVisible(False)
        self.preview_btn.setEnabled(True)
        QMessageBox.critical(self, "错误", message)
    
    def _play_preview(self):
        self.processed_preview.play()
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
    
    def _stop_preview(self):
        self.processed_preview.stop()
        self.play_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
    
    def _export_webp(self):
        if not self.processed_frames:
            return
        
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存动态 WebP",
            "",
            "WebP文件 (*.webp)"
        )

        if not output_path:
            return

        from PIL import Image

        export_fps = self.output_fps
        frames = self.processed_frames
        original_count = len(frames)
        target_size_kb = self.target_size_spin.value()

        # 增加反向帧 (首尾相连循环)
        if self.loop_check.isChecked():
            reverse_frames = frames[::-1][1:]
            frames = frames + reverse_frames

        pil_frames = [Image.fromarray(f, mode='RGBA') for f in frames]

        duration = max(10, int(1000 / export_fps))
        actual_fps = 1000 / duration

        # 获取用户设置的质量值
        base_quality = self.quality_slider.value()

        # 如果设置了目标文件大小，进行迭代压缩
        final_quality = base_quality
        if target_size_kb > 0:
            # 初步保存以估算文件大小
            import tempfile
            import os

            # 使用较低质量快速估算
            test_quality = max(10, base_quality // 2)

            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as tmp:
                tmp_path = tmp.name

            try:
                # 第一次保存
                pil_frames[0].save(
                    tmp_path,
                    format='WebP',
                    append_images=pil_frames[1:],
                    save_all=True,
                    duration=duration,
                    loop=0,
                    lossless=False,
                    quality=test_quality,
                    method=4
                )

                file_size = os.path.getsize(tmp_path) / 1024  # KB

                # 如果文件太大，降低质量
                if file_size > target_size_kb:
                    # 计算需要的质量调整因子
                    ratio = target_size_kb / file_size
                    final_quality = max(5, min(100, int(test_quality * ratio)))
                    final_quality = max(5, min(base_quality, final_quality))
                else:
                    final_quality = base_quality
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

        print(f"导出 WebP 信息:")
        print(f"  原始帧数: {original_count}")
        print(f"  总帧数: {len(pil_frames)}")
        print(f"  设置帧率: {export_fps:.1f} FPS")
        print(f"  每帧时长: {duration} ms")
        print(f"  实际帧率: {actual_fps:.1f} FPS")
        print(f"  压缩质量: {final_quality}%")

        # 使用 Pillow 导出 WebP
        pil_frames[0].save(
            output_path,
            format='WebP',
            append_images=pil_frames[1:],
            save_all=True,
            duration=duration,
            loop=0,
            lossless=False,
            quality=final_quality,
            method=4
        )

        # 获取实际文件大小
        actual_size = os.path.getsize(output_path) / 1024

        QMessageBox.information(self, "成功",
            f"动态 WebP 已保存到:\n{output_path}\n"
            f"帧率: {actual_fps:.1f} FPS | 每帧: {duration}ms\n"
            f"压缩质量: {final_quality}% | 文件大小: {actual_size:.1f} KB"
        )
        self._show_config_dialog(output_path)
    
    def _show_config_dialog(self, output_path: str):
        from PyQt6.QtWidgets import QDialog, QTextEdit, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("动作配置")
        dialog.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("将以下配置添加到 config/user_config.json:"))
        
        config_text = QTextEdit()
        config_text.setReadOnly(True)
        
        h, w = self.processed_frames[0].shape[:2]
        
        import json
        config = {
            "actions": {
                "new_action": {
                    "enabled": True,
                    "weight": 1,
                    "type": "animation",
                    "description": "新动作动画",
                    "animations": [
                        {
                            "path": f"animations/new_action/{Path(output_path).name}",
                            "width": w,
                            "height": h
                        }
                    ]
                }
            }
        }
        config_text.setPlainText(json.dumps(config, indent=2, ensure_ascii=False))
        layout.addWidget(config_text)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        dialog.exec()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()