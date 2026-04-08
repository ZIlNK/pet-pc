#!/usr/bin/env python3
"""
锚点检测模块

用于检测动画帧中的锚点位置，支持锚点对齐功能。
锚点定义：人物脚底中心点（最底部非透明像素行的水平中点）
"""

import numpy as np
from pathlib import Path
from typing import Tuple, Optional


class AnchorDetector:
    """锚点检测器

    检测动画的脚底中心锚点位置。
    """

    def __init__(self, fallback_to_center: bool = True):
        """
        Args:
            fallback_to_center: 当无法检测到脚底时，是否回退到几何中心
        """
        self.fallback_to_center = fallback_to_center

    def detect(self, frames: list[np.ndarray]) -> Tuple[float, float]:
        """
        检测动画的锚点位置

        Args:
            frames: RGBA 帧列表，每帧 shape 为 (H, W, 4)

        Returns:
            (anchor_x_ratio, anchor_y_ratio): 归一化坐标 (0-1)
                - anchor_x_ratio: 锚点 X 位置 / 画布宽度
                - anchor_y_ratio: 锚点 Y 位置 / 画布高度
        """
        if not frames:
            return (0.5, 0.5)

        # 合并所有帧的 alpha 通道，找到整体非透明区域
        all_alpha = np.zeros(frames[0].shape[:2], dtype=np.uint8)

        for frame in frames:
            if frame.shape[2] == 4:  # RGBA
                alpha = frame[:, :, 3]
                binary = (alpha > 127).astype(np.uint8)
                all_alpha = np.maximum(all_alpha, binary)

        return self._find_anchor_from_mask(all_alpha)

    def _find_anchor_from_mask(self, mask: np.ndarray) -> Tuple[float, float]:
        """
        从二值掩码中找到锚点位置

        策略：从底部向上扫描，找到第一个非透明行，计算该行的水平中心
        """
        h, w = mask.shape

        # 找到所有非透明像素的坐标
        coords = np.column_stack(np.where(mask > 0))

        if len(coords) == 0:
            return (0.5, 0.5)  # 完全透明，返回中心

        # 找到最底部的行
        bottom_y = coords[:, 0].max()

        # 找到该行所有非透明像素的 X 坐标
        bottom_row_pixels = coords[coords[:, 0] == bottom_y, 1]

        if len(bottom_row_pixels) > 0:
            # 计算水平中心
            center_x = int(np.median(bottom_row_pixels))
            return (center_x / w, bottom_y / h)

        # 回退：使用几何中心
        if self.fallback_to_center:
            y_coords = coords[:, 0]
            x_coords = coords[:, 1]
            center_y = (y_coords.min() + y_coords.max()) / 2
            center_x = (x_coords.min() + x_coords.max()) / 2
            return (center_x / w, center_y / h)

        return (0.5, 0.5)

    def detect_from_file(self, image_path: str) -> Tuple[float, float, int, int]:
        """
        从图片文件中检测锚点

        Args:
            image_path: 图片路径（支持 PNG, WebP 等）

        Returns:
            (anchor_x_ratio, anchor_y_ratio, width, height)
        """
        from PIL import Image

        img = Image.open(image_path)

        # 如果是动态图，提取所有帧
        frames = []
        try:
            frame_idx = 0
            while True:
                img.seek(frame_idx)
                frame = img.convert('RGBA')
                frames.append(np.array(frame))
                frame_idx += 1
        except EOFError:
            # 单帧图片
            frames = [np.array(img.convert('RGBA'))]

        anchor = self.detect(frames)
        return (anchor[0], anchor[1], frames[0].shape[1], frames[0].shape[0])
