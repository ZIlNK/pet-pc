"""宠物状态机管理模块

集中管理宠物状态转换，提供清晰的状态流转接口。
"""
import logging
from .states import PetState

logger = logging.getLogger(__name__)


class PetStateMachine:
    """宠物状态机 - 集中管理状态转换"""

    # 有效的状态转换映射
    VALID_TRANSITIONS = {
        PetState.IDLE: [PetState.DRAGGING, PetState.MOVING, PetState.REST_REMINDER,
                        PetState.MOTION_MODE, PetState.ANIMATING],
        PetState.DRAGGING: [PetState.INERTIA, PetState.IDLE],
        PetState.INERTIA: [PetState.FALLING, PetState.IDLE],
        PetState.FALLING: [PetState.IDLE],
        PetState.MOVING: [PetState.IDLE, PetState.ANIMATING],
        PetState.REST_REMINDER: [PetState.IDLE, PetState.MOTION_MODE, PetState.ANIMATING],
        PetState.MOTION_MODE: [PetState.IDLE, PetState.ANIMATING],
        PetState.ANIMATING: [PetState.IDLE, PetState.MOTION_MODE],
    }

    def __init__(self, pet):
        self._pet = pet
        self._state = PetState.IDLE

    @property
    def state(self) -> PetState:
        """获取当前状态"""
        return self._state

    def can_transition_to(self, target_state: PetState) -> bool:
        """检查是否可以转换到目标状态"""
        if self._state not in self.VALID_TRANSITIONS:
            return True  # 未知状态允许转换
        return target_state in self.VALID_TRANSITIONS[self._state]

    def transition_to(self, target_state: PetState, force: bool = False) -> bool:
        """
        转换到目标状态

        Args:
            target_state: 目标状态
            force: 是否强制转换（跳过验证）

        Returns:
            是否转换成功
        """
        if not force and not self.can_transition_to(target_state):
            logger.warning(f"Invalid state transition: {self._state.value} -> {target_state.value}")
            return False

        old_state = self._state
        self._state = target_state

        # 记录状态转换日志
        logger.debug(f"State transition: {old_state.value} -> {target_state.value}")
        return True

    # === 便捷方法 ===

    def start_dragging(self) -> bool:
        """开始拖拽"""
        return self.transition_to(PetState.DRAGGING)

    def start_inertia(self) -> bool:
        """开始惯性滑动"""
        return self.transition_to(PetState.INERTIA)

    def start_falling(self) -> bool:
        """开始下落"""
        return self.transition_to(PetState.FALLING)

    def start_moving(self) -> bool:
        """开始移动"""
        return self.transition_to(PetState.MOVING)

    def start_animation(self) -> bool:
        """开始动画"""
        return self.transition_to(PetState.ANIMATING)

    def start_rest_reminder(self) -> bool:
        """开始休息提醒"""
        return self.transition_to(PetState.REST_REMINDER)

    def start_motion_mode(self) -> bool:
        """开始运动模式"""
        return self.transition_to(PetState.MOTION_MODE)

    def return_to_idle(self, force: bool = True) -> bool:
        """返回空闲状态"""
        return self.transition_to(PetState.IDLE, force=force)

    def is_idle(self) -> bool:
        """是否空闲状态"""
        return self._state == PetState.IDLE

    def is_animating(self) -> bool:
        """是否动画状态"""
        return self._state == PetState.ANIMATING

    def is_moving(self) -> bool:
        """是否移动状态"""
        return self._state == PetState.MOVING

    def is_dragging(self) -> bool:
        """是否拖拽状态"""
        return self._state == PetState.DRAGGING