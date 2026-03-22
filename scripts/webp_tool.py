#!/usr/bin/env python3
"""
WebP 动作锚点对齐与缩放工具 (GUI升级版)

功能：
1. 读取动态 WebP 文件。
2. **新增：设定素材缩放比例，统一不同素材的人物大小。**
3. 设定一个统一的目标画布尺寸。
4. 通过鼠标点击预览图拾取原始锚点，程序会自动处理缩放后的坐标映射。
5. 重新生成一个新的动态 WebP，将角色缩放并对齐到新画布的底部居中位置。
"""

import sys
from pathlib import Path
from PIL import Image, ImageSequence

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QDoubleSpinBox, QFileDialog, QGroupBox,
    QProgressBar, QMessageBox, QGridLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QCursor


class AnchorProcessorThread(QThread):
    """后台处理线程：负责执行图像缩放和锚点对齐操作"""
    progress_update = pyqtSignal(int)
    finished_success = pyqtSignal(str)
    finished_error = pyqtSignal(str)

    def __init__(self, input_path, output_path, target_w, target_h, anchor_x, anchor_y, scale_factor):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.target_w = target_w
        self.target_h = target_h
        # 原始图片上的锚点坐标
        self.orig_anchor_x = anchor_x
        self.orig_anchor_y = anchor_y
        # 缩放比例
        self.scale_factor = scale_factor

    def run(self):
        try:
            with Image.open(self.input_path) as im:
                n_frames = getattr(im, "n_frames", 1)
                loop_count = im.info.get("loop", 0)
                
                frames = []
                durations = []
                
                # 1. 计算缩放后的实际锚点坐标
                # 用户是在原图上点的，如果图片放大了，锚点坐标也要相应放大
                scaled_anchor_x = int(self.orig_anchor_x * self.scale_factor)
                scaled_anchor_y = int(self.orig_anchor_y * self.scale_factor)

                # 2. 计算新画布的目标锚点位置：底部居中
                target_center_x = self.target_w // 2
                target_bottom_y = self.target_h

                # 3. 计算粘贴坐标的核心公式：
                # 我们要让缩放后的 anchor 点重合到新画布的 target 点上
                paste_x = target_center_x - scaled_anchor_x
                paste_y = target_bottom_y - scaled_anchor_y

                print(f"处理开始: 总帧数 {n_frames}, 缩放: {self.scale_factor}")
                print(f"锚点映射: 原点({self.orig_anchor_x},{self.orig_anchor_y}) -> 缩放后({scaled_anchor_x},{scaled_anchor_y})")
                print(f"目标位置: 新画布底部居中({target_center_x},{target_bottom_y})")
                print(f"计算得出粘贴 TopLeft 坐标: ({paste_x},{paste_y})")

                # 遍历每一帧进行处理
                iterator = ImageSequence.Iterator(im)
                for i, frame in enumerate(iterator):
                    # A. 转换为 RGBA
                    frame_rgba = frame.convert("RGBA")

                    # B. 执行缩放 (如果比例不是 1.0)
                    if self.scale_factor != 1.0:
                        new_w = int(frame_rgba.width * self.scale_factor)
                        new_h = int(frame_rgba.height * self.scale_factor)
                        # 使用 Lanczos 滤镜保证高质量缩放
                        frame_rgba = frame_rgba.resize((new_w, new_h), Image.Resampling.LANCZOS)

                    # C. 创建全透明的新画布
                    canvas = Image.new("RGBA", (self.target_w, self.target_h), (0, 0, 0, 0))
                    
                    # D. 将缩放后的图贴到计算好的位置
                    canvas.paste(frame_rgba, (paste_x, paste_y), mask=frame_rgba)
                    
                    frames.append(canvas)
                    durations.append(frame.info.get('duration', 100))
                    
                    # 更新进度 (留一点给保存阶段)
                    self.progress_update.emit(int(((i + 1) / n_frames) * 95))

                if not frames:
                    raise Exception("未能提取到任何帧")

                self.progress_update.emit(98) # 准备保存

                # 4. 保存为新的动态 WebP (使用快速无损配置)
                frames[0].save(
                    self.output_path,
                    format='WebP',
                    save_all=True,
                    append_images=frames[1:],
                    duration=durations,
                    loop=loop_count,
                    lossless=True,  # 使用无损模式，速度快且适合桌宠素材
                    method=4        # 平衡速度和压缩率
                )
                self.progress_update.emit(100)
                self.finished_success.emit(self.output_path)

        except Exception as e:
            self.finished_error.emit(str(e))


class ClickableLabel(QLabel):
    """自定义 QLabel，支持鼠标点击信号发送，用于拾取坐标"""
    clicked = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.original_pixmap = None
        self.scale_factor = 1.0

    def set_original_pixmap(self, pixmap):
        self.original_pixmap = pixmap
        self.update_display()

    def update_display(self):
        if not self.original_pixmap or self.width() == 0 or self.height() == 0:
            return
        
        scaled_pixmap = self.original_pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(scaled_pixmap)
        # 计算显示缩放比例：显示宽度 / 原始宽度
        self.scale_factor = scaled_pixmap.width() / self.original_pixmap.width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_display()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.original_pixmap:
            click_pos = event.position()
            
            # 计算图片在 QLabel 中的偏移量（因为是居中显示的）
            label_w, label_h = self.width(), self.height()
            pix_w, pix_h = self.pixmap().width(), self.pixmap().height()
            offset_x = (label_w - pix_w) / 2
            offset_y = (label_h - pix_h) / 2

            rel_x = click_pos.x() - offset_x
            rel_y = click_pos.y() - offset_y

            if 0 <= rel_x < pix_w and 0 <= rel_y < pix_h:
                # 映射回原始分辨率的真实坐标
                real_x = int(rel_x / self.scale_factor)
                real_y = int(rel_y / self.scale_factor)
                self.clicked.emit(real_x, real_y)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WebP 动作锚点对齐与缩放工具")
        self.setMinimumSize(950, 650)
        self.input_path = None
        
        self._setup_ui()

    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        # Letf Panel: Controls
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        control_panel.setFixedWidth(340)

        # 1. 文件加载与缩放
        load_box = QGroupBox("1. 加载与缩放")
        load_layout = QGridLayout(load_box)
        self.btn_load = QPushButton("📂 打开动态 WebP 文件")
        self.btn_load.setFixedHeight(35)
        self.btn_load.clicked.connect(self.load_file)
        load_layout.addWidget(self.btn_load, 0, 0, 1, 2)
        
        self.lbl_file_info = QLabel("未加载文件")
        self.lbl_file_info.setStyleSheet("color: gray; font-size: 11px;")
        load_layout.addWidget(self.lbl_file_info, 1, 0, 1, 2)

        load_layout.addWidget(QLabel("素材缩放比例:"), 2, 0)
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(0.1, 5.0)
        self.spin_scale.setValue(1.0)
        self.spin_scale.setSingleStep(0.05)
        self.spin_scale.setSuffix(" x")
        self.spin_scale.setToolTip("如果这个素材里的人物比标准大小偏小，就设置大于1.0；偏大就设置小于1.0。")
        load_layout.addWidget(self.spin_scale, 2, 1)

        control_layout.addWidget(load_box)

        # 2. 目标尺寸设置
        target_box = QGroupBox("2. 设定统一画布大小 (重要)")
        target_layout = QGridLayout(target_box)
        target_layout.addWidget(QLabel("目标宽度:"), 0, 0)
        self.spin_target_w = QSpinBox(); self.spin_target_w.setRange(1, 9999); self.spin_target_w.setValue(500)
        target_layout.addWidget(self.spin_target_w, 0, 1)
        target_layout.addWidget(QLabel("目标高度:"), 1, 0)
        self.spin_target_h = QSpinBox(); self.spin_target_h.setRange(1, 9999); self.spin_target_h.setValue(500)
        target_layout.addWidget(self.spin_target_h, 1, 1)
        lbl_target_hint = QLabel("提示: 所有动作必须使用完全相同的画布大小，才能保证切换时不跳动。")
        lbl_target_hint.setStyleSheet("color: gray; font-size: 10px;")
        lbl_target_hint.setWordWrap(True)
        target_layout.addWidget(lbl_target_hint, 2, 0, 1, 2)
        control_layout.addWidget(target_box)

        # 3. 锚点拾取
        anchor_box = QGroupBox("3. 拾取锚点 (点击右侧原图)")
        anchor_layout = QGridLayout(anchor_box)
        anchor_layout.addWidget(QLabel("原始锚点 X:"), 0, 0)
        self.spin_anchor_x = QSpinBox(); self.spin_anchor_x.setRange(-9999, 9999); self.spin_anchor_x.setEnabled(False)
        anchor_layout.addWidget(self.spin_anchor_x, 0, 1)
        anchor_layout.addWidget(QLabel("原始锚点 Y:"), 1, 0)
        self.spin_anchor_y = QSpinBox(); self.spin_anchor_y.setRange(-9999, 9999); self.spin_anchor_y.setEnabled(False)
        anchor_layout.addWidget(self.spin_anchor_y, 1, 1)
        lbl_hint = QLabel("提示: 请在右图点击角色的'脚底中心'。程序会自动计算缩放后的位置并对齐到画布底部。")
        lbl_hint.setStyleSheet("color: #e65100; font-size: 11px; margin-top: 5px; font-weight: bold;")
        lbl_hint.setWordWrap(True)
        anchor_layout.addWidget(lbl_hint, 2, 0, 1, 2)
        control_layout.addWidget(anchor_box)

        # 4. 执行按钮和进度条
        control_layout.addStretch()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        control_layout.addWidget(self.progress_bar)
        self.btn_process = QPushButton("🚀 生成对齐后的 WebP")
        self.btn_process.setFixedHeight(50)
        self.btn_process.setStyleSheet("font-weight: bold; font-size: 14px; background-color: #4CAF50; color: white;")
        self.btn_process.setEnabled(False)
        self.btn_process.clicked.connect(self.start_processing)
        control_layout.addWidget(self.btn_process)

        layout.addWidget(control_panel)

        # Right Panel: Preview Image
        preview_panel = QGroupBox("第一帧预览 (在此点击拾取锚点)")
        preview_layout = QVBoxLayout(preview_panel)
        self.image_label = ClickableLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 设置棋盘格背景
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #eee;
                background-image: linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc),
                                  linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc);
                background-size: 20px 20px;
                background-position: 0 0, 10px 10px;
                border: 2px dashed #aaa;
            }
        """)
        self.image_label.clicked.connect(self.on_image_clicked)
        preview_layout.addWidget(self.image_label)
        layout.addWidget(preview_panel, stretch=1)

    def load_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 WebP 文件", "", "WebP Files (*.webp);;All Files (*)")
        if file_path:
            self.input_path = file_path
            try:
                with Image.open(self.input_path) as im:
                    frame0 = im.convert("RGBA")
                    qim = QImage(frame0.tobytes(), frame0.width, frame0.height, QImage.Format.Format_RGBA8888)
                    pixmap = QPixmap.fromImage(qim)
                    self.image_label.set_original_pixmap(pixmap)
                    
                    self.lbl_file_info.setText(f"文件: {Path(file_path).name} | 原始尺寸: {im.width}x{im.height}")
                    self.lbl_file_info.setStyleSheet("color: black; font-size: 11px;")
                    self.btn_process.setEnabled(True)
                    
                    # 重置一些状态
                    self.spin_anchor_x.setValue(0)
                    self.spin_anchor_y.setValue(0)
                    # 如果是第一次加载，设置一个推荐的画布大小
                    if self.spin_target_w.value() == 500:
                         self.spin_target_w.setValue(int(im.width * 1.2))
                         self.spin_target_h.setValue(int(im.height * 1.2))

            except Exception as e:
                QMessageBox.critical(self, "加载失败", str(e))

    def on_image_clicked(self, x, y):
        """当在图片上点击时触发，更新锚点坐标"""
        self.spin_anchor_x.setValue(x)
        self.spin_anchor_y.setValue(y)

    def start_processing(self):
        if not self.input_path: return
        if self.spin_anchor_x.value() == 0 and self.spin_anchor_y.value() == 0:
             QMessageBox.warning(self, "提示", "请先在右侧图片上点击角色的脚底来设置锚点！")
             return

        output_path, _ = QFileDialog.getSaveFileName(self, "保存对齐后的 WebP", self.input_path.replace(".webp", "_aligned.webp"), "WebP Files (*.webp)")
        if not output_path: return

        self.btn_process.setEnabled(False)
        self.btn_load.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.thread = AnchorProcessorThread(
            self.input_path,
            output_path,
            self.spin_target_w.value(),
            self.spin_target_h.value(),
            self.spin_anchor_x.value(),
            self.spin_anchor_y.value(),
            self.spin_scale.value() # 传入缩放比例
        )
        self.thread.progress_update.connect(self.progress_bar.setValue)
        self.thread.finished_success.connect(self.on_success)
        self.thread.finished_error.connect(self.on_error)
        self.thread.start()

    def on_success(self, output_path):
        self.reset_ui()
        QMessageBox.information(self, "成功", f"已生成!\n保存在: {output_path}\n\n画布大小: {self.spin_target_w.value()}x{self.spin_target_h.value()}\n缩放比例: {self.spin_scale.value()}x\n\n(现在进度条应该不会卡住了😉)")

    def on_error(self, msg):
        self.reset_ui()
        QMessageBox.critical(self, "处理失败", msg)

    def reset_ui(self):
        self.btn_process.setEnabled(True)
        self.btn_load.setEnabled(True)
        self.progress_bar.setVisible(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())