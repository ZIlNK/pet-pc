# tests/test_alignment_processor.py
"""
对齐处理器测试模块
"""
import numpy as np
import pytest
from scripts.alignment_processor import AlignmentProcessor


class TestAlignmentProcessor:
    """对齐处理器测试"""

    def test_align_same_size_no_offset(self):
        """相同尺寸无偏移的对齐"""
        # 参考：200x159，锚点在底部中心
        ref_size = (200, 159)
        ref_anchor = (0.5, 1.0)  # 底部中心

        processor = AlignmentProcessor(ref_size, ref_anchor)

        # 源帧：同样 200x159，锚点也在底部中心
        src_frame = np.zeros((159, 200, 4), dtype=np.uint8)
        src_frame[50:100, 80:120, 3] = 255  # 添加一些不透明像素
        src_anchor = (0.5, 1.0)

        result = processor.align(src_frame, src_anchor)

        assert result.shape == (159, 200, 4)

    def test_align_smaller_to_larger(self):
        """小画布对齐到大画布"""
        ref_size = (200, 159)
        ref_anchor = (0.5, 1.0)

        processor = AlignmentProcessor(ref_size, ref_anchor)

        # 源帧：100x80
        src_frame = np.zeros((80, 100, 4), dtype=np.uint8)
        src_frame[:, :, 3] = 255  # 完全不透明
        src_anchor = (0.5, 1.0)

        result = processor.align(src_frame, src_anchor)

        assert result.shape == (159, 200, 4)
        # 检查边缘是否为透明（黑色 + alpha=0）
        assert np.all(result[0, 0, :3] == 0)  # 左上角应该是黑色

    def test_manual_offset(self):
        """手动微调偏移"""
        ref_size = (200, 159)
        ref_anchor = (0.5, 1.0)

        processor = AlignmentProcessor(ref_size, ref_anchor, manual_offset=(10, -5))

        src_frame = np.zeros((159, 200, 4), dtype=np.uint8)
        src_frame[50:100, 80:120, 3] = 255
        src_anchor = (0.5, 1.0)

        result_no_offset = AlignmentProcessor(ref_size, ref_anchor).align(src_frame, src_anchor)
        result_with_offset = processor.align(src_frame, src_anchor)

        # 有偏移的结果应该与无偏移的结果不同
        assert not np.array_equal(result_no_offset, result_with_offset)

    def test_align_frames(self):
        """测试多帧对齐"""
        ref_size = (200, 159)
        ref_anchor = (0.5, 1.0)

        processor = AlignmentProcessor(ref_size, ref_anchor)

        # 创建 3 帧源帧
        frames = [
            np.zeros((159, 200, 4), dtype=np.uint8) for _ in range(3)
        ]
        for i, frame in enumerate(frames):
            frame[50+i:100-i, 80:120, 3] = 255

        src_anchor = (0.5, 1.0)
        results = processor.align_frames(frames, src_anchor)

        assert len(results) == 3
        for result in results:
            assert result.shape == (159, 200, 4)

    def test_set_manual_offset(self):
        """测试动态设置手动偏移"""
        ref_size = (200, 159)
        ref_anchor = (0.5, 1.0)

        processor = AlignmentProcessor(ref_size, ref_anchor)

        assert processor.manual_dx == 0
        assert processor.manual_dy == 0

        processor.set_manual_offset(5, -10)

        assert processor.manual_dx == 5
        assert processor.manual_dy == -10

    def test_get_offset_info(self):
        """测试获取偏移信息"""
        ref_size = (200, 159)
        ref_anchor = (0.5, 1.0)
        manual_offset = (10, -5)

        processor = AlignmentProcessor(ref_size, ref_anchor, manual_offset)

        info = processor.get_offset_info()

        assert info['ref_size'] == (200, 159)
        assert info['ref_anchor'] == (0.5, 1.0)
        assert info['manual_offset'] == (10, -5)

    def test_align_larger_to_smaller(self):
        """大画布对齐到小画布"""
        ref_size = (100, 80)
        ref_anchor = (0.5, 1.0)

        processor = AlignmentProcessor(ref_size, ref_anchor)

        # 源帧：200x159
        src_frame = np.zeros((159, 200, 4), dtype=np.uint8)
        src_frame[:, :, 3] = 255
        src_anchor = (0.5, 1.0)

        result = processor.align(src_frame, src_anchor)

        assert result.shape == (80, 100, 4)

    def test_anchor_at_origin(self):
        """锚点在左上角 (0, 0)"""
        ref_size = (200, 159)
        ref_anchor = (0.0, 0.0)

        processor = AlignmentProcessor(ref_size, ref_anchor)

        src_frame = np.zeros((159, 200, 4), dtype=np.uint8)
        src_frame[50:100, 80:120, 3] = 255
        src_anchor = (0.0, 0.0)

        result = processor.align(src_frame, src_anchor)

        assert result.shape == (159, 200, 4)
        # 锚点对齐，内容应该在相同位置
        assert result[50:100, 80:120, 3].sum() > 0

    def test_anchor_at_center(self):
        """锚点在中心 (0.5, 0.5)"""
        ref_size = (200, 159)
        ref_anchor = (0.5, 0.5)

        processor = AlignmentProcessor(ref_size, ref_anchor)

        src_frame = np.zeros((159, 200, 4), dtype=np.uint8)
        src_frame[50:100, 80:120, 3] = 255
        src_anchor = (0.5, 0.5)

        result = processor.align(src_frame, src_anchor)

        assert result.shape == (159, 200, 4)
