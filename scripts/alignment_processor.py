# scripts/alignment_processor.py
"""
对齐处理器模块 - 将源动画对齐到参考动画的尺寸和锚点
"""
import numpy as np
from typing import Tuple


class AlignmentProcessor:
    """
    对齐处理器 - 将源动画对齐到参考动画的尺寸和锚点
    """

    def __init__(
        self,
        ref_size: Tuple[int, int],
        ref_anchor: Tuple[float, float],
        manual_offset: Tuple[int, int] = (0, 0)
    ):
        """
        Args:
            ref_size: 参考动画尺寸 (width, height)
            ref_anchor: 参考锚点归一化坐标 (x_ratio, y_ratio)
            manual_offset: 手动微调偏移 (dx, dy) 像素
        """
        self.ref_width, self.ref_height = ref_size
        self.ref_anchor_x, self.ref_anchor_y = ref_anchor
        self.manual_dx, self.manual_dy = manual_offset

    def align(self, frame: np.ndarray, src_anchor: Tuple[float, float]) -> np.ndarray:
        """
        将单帧对齐到参考尺寸和锚点

        Args:
            frame: 源帧 (RGBA)
            src_anchor: 源锚点归一化坐标 (x_ratio, y_ratio)

        Returns:
            对齐后的帧，尺寸为 (ref_height, ref_width, 4)
        """
        src_height, src_width = frame.shape[:2]
        src_anchor_x, src_anchor_y = src_anchor

        # 计算源锚点的实际像素位置
        src_anchor_px_x = int(src_anchor_x * src_width)
        src_anchor_px_y = int(src_anchor_y * src_height)

        # 计算参考锚点的实际像素位置
        ref_anchor_px_x = int(self.ref_anchor_x * self.ref_width)
        ref_anchor_px_y = int(self.ref_anchor_y * self.ref_height)

        # 计算需要的偏移量（对齐锚点 + 手动微调）
        dx = ref_anchor_px_x - src_anchor_px_x + self.manual_dx
        dy = ref_anchor_px_y - src_anchor_px_y + self.manual_dy

        # 创建目标画布
        result = np.zeros((self.ref_height, self.ref_width, 4), dtype=np.uint8)

        # 计算源帧在目标画布中的位置
        dst_x = max(0, dx)
        dst_y = max(0, dy)

        # 计算需要从源帧中截取的区域
        src_x = max(0, -dx)
        src_y = max(0, -dy)

        # 计算重叠区域的尺寸
        overlap_width = min(src_width - src_x, self.ref_width - dst_x)
        overlap_height = min(src_height - src_y, self.ref_height - dst_y)

        if overlap_width > 0 and overlap_height > 0:
            result[dst_y:dst_y+overlap_height, dst_x:dst_x+overlap_width] = \
                frame[src_y:src_y+overlap_height, src_x:src_x+overlap_width]

        return result

    def align_frames(
        self,
        frames: list[np.ndarray],
        src_anchor: Tuple[float, float]
    ) -> list[np.ndarray]:
        """
        对齐所有帧

        Args:
            frames: 源帧列表
            src_anchor: 源锚点归一化坐标

        Returns:
            对齐后的帧列表
        """
        return [self.align(frame, src_anchor) for frame in frames]

    def set_manual_offset(self, dx: int, dy: int):
        """设置手动微调偏移"""
        self.manual_dx = dx
        self.manual_dy = dy

    def get_offset_info(self) -> dict:
        """获取偏移信息"""
        return {
            'ref_size': (self.ref_width, self.ref_height),
            'ref_anchor': (self.ref_anchor_x, self.ref_anchor_y),
            'manual_offset': (self.manual_dx, self.manual_dy)
        }
