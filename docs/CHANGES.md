# 项目变更摘要

## 2026-07-27 — Desktop Pet × OpenClaw 持久化 Channel 集成

- 为每个桌宠实例增加独立 OpenClaw Agent 配置，并校验 Agent ID 格式与重复绑定。
- 增加 `pet-bubble` 标准 Channel 入站链路，使用 OpenClaw exact bindings 和 `per-channel-peer` 持久会话。
- 将正常聊天从 `/hooks/agent` 临时任务切换为 `/pet-bubble-webhook`；Hooks 保留为手动兼容和回滚模式。
- 定义单一结构化最终回复协议，由插件直接调用 `/api/pets/<pet_id>/respond`，原子完成文字气泡和可选动画。
- 正常 OpenClaw 聊天链路不再需要 Desktop Pet MCP；MCP 仅保留给通用运动、状态和实例管理等可选工具场景。
- 增加 `/api/openclaw/reply` 兼容回调、按 `to` 的多宠物投递、无效目标拒绝和短期回复指纹去重。
- 增加 Agent `MEMORY.md` 受控区域、原子写入、工作区锁、安全边界、记忆管理 API 与桌宠管理 UI。
- 增加 Channel/Hook 全局设置、宠物实例 AI Agent 设置以及长期记忆管理对话框。
- 完成端到端验证：Channel 接收、持久会话、结构化动画回复、无 MCP 工具调用和正确宠物回投。
- 验证时自动测试基线为 Python `317 passed`；Node 插件 `26 passed, 1 skipped`，跳过项为 Windows 符号链接权限场景。
