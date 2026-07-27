# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **本项目规则手册统一维护在 [AGENTS.md](AGENTS.md)**。本文件仅列对 Claude Code 工作流最关键的速查项；任何架构、API、组件细节以 AGENTS.md 为准。

## 项目速查

**项目类型**：PyQt6 多桌宠平台（已从单桌宠应用升级为多实例平台架构）。

## Commands

```bash
uv run desktop-pet                    # 运行应用
uv run python -m desktop_pet          # 等价入口
uv sync                               # 安装依赖
uv sync --group dev                   # 含绿幕工具开发依赖
uv run pytest                         # 运行测试套件
uv run pytest tests/ --tb=short -q    # 简短回溯
```

## 关键红线

- `config/default_config.json` **禁止修改**——用户覆盖请编辑 `config/user_config.json`。
- 实例配置运行时由 `InstancesStore` 写入 `config/instances.json`；**不要手动编辑**该文件。
- 跨线程 UI 操作必须用 `QTimer.singleShot(0, lambda: ...)` 调度到主线程；**不要用** `QMetaObject.invokeMethod`（Python 方法未注册到 Qt 元对象系统）。
- `ApiServer` 在子线程 asyncio loop 中运行；从 async handler 操作 widget 必须走 `_run_in_main_thread` 或 PyQt signal + QueuedConnection。
- OpenClaw 普通聊天固定走 `pet-bubble` 持久化 Channel 和结构化 final → `/api/pets/<pet_id>/respond`；不要为该链路启用 Desktop Pet MCP。

## 关键文件位置

- 平台核心：`src/desktop_pet/pet_platform.py`（多实例生命周期入口）
- 实例配置模型：`src/desktop_pet/pet_instance.py`（`PetInstanceConfig` dataclass）
- 实例持久化：`src/desktop_pet/instances_store.py`（CRUD + 向后兼容迁移）
- 全局配置：`src/desktop_pet/config_manager.py`（`GlobalConfigManager` 仅管全局字段）
- 启动入口：`src/desktop_pet/__main__.py`
- HTTP API、OpenClaw 回调与可选 MCP 工具定义：`src/desktop_pet/api_server.py`
- OpenClaw Channel 插件：`openclaw-plugins/pet-bubble/`

## 深入文档

完整项目约定见 [AGENTS.md](AGENTS.md)。OpenClaw 部署、架构和排障分别见 [接入指南](docs/openclaw-integration.md)、[架构说明](docs/openclaw-architecture.md) 和 [运维手册](docs/openclaw-runbook.md)。
