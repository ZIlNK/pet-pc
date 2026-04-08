# tests/test_anchor_detector.py
import numpy as np
import pytest
import sys
import os

# 添加 scripts 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from anchor_detector import AnchorDetector


class TestAnchorDetector:
    """锚点检测器测试"""

    def test_detect_center_on_empty_frames(self):
        """空帧列表应返回中心点"""
        detector = AnchorDetector()
        result = detector.detect([])
        assert result == (0.5, 0.5)

    def test_detect_center_on_fully_transparent(self):
        """完全透明的帧应返回中心点"""
        detector = AnchorDetector()
        # 创建完全透明的 RGBA 帧
        transparent_frame = np.zeros((100, 100, 4), dtype=np.uint8)
        transparent_frame[:, :, 3] = 0  # Alpha = 0

        result = detector.detect([transparent_frame])
        assert result == (0.5, 0.5)

    def test_detect_bottom_center_on_rectangle(self):
        """矩形应检测到中心点"""
        detector = AnchorDetector()
        # 创建一个 100x100 的帧，中间有 50x50 的不透明矩形
        frame = np.zeros((100, 100, 4), dtype=np.uint8)
        frame[25:75, 25:75] = [255, 0, 0, 255]  # 红色不透明矩形

        result = detector.detect([frame])
        # 锚点应该在矩形底部中心：x=50, y=74
        assert abs(result[0] - 0.5) < 0.1  # x ≈ 0.5
        assert abs(result[1] - 0.74) < 0.1  # y ≈ 0.74

    def test_detect_from_file_single_frame(self):
        """从单帧图片文件检测"""
        detector = AnchorDetector()
        # 使用项目中的 idle.png 作为测试
        # worktree 中 pets 目录可能不存在，使用固定的项目根目录
        project_root = "D:/code/pet-pc"
        idle_path = os.path.join(project_root, "pets", "default", "animations", "idle.png")
        result = detector.detect_from_file(idle_path)
        assert len(result) == 4  # (x_ratio, y_ratio, width, height)
        assert 0 <= result[0] <= 1  # x_ratio in [0, 1]
        assert 0 <= result[1] <= 1  # y_ratio in [0, 1]
        assert result[2] > 0  # width > 0
        assert result[3] > 0  # height > 0
