# Pet Bubble Channel Plugin 早期设计归档

> **状态：已被最终实现替代。** 请勿按本文件的旧方案部署。

当前文档：

- [接入指南](docs/openclaw-integration.md)
- [最终架构](docs/openclaw-architecture.md)
- [运维与排障](docs/openclaw-runbook.md)
- [变更摘要](docs/CHANGES.md)

本文件原先记录了 `pet-bubble` Channel 的探索性设计，其中包含已经废弃的假设：硬编码 peer、无操作 outbound、通过 Desktop Pet MCP `show_message/respond_as_pet` 回投、修改 `config/default_config.json` 等。

最终实现与早期设计的主要差异：

1. 使用 OpenClaw exact `bindings` 按 `pet_id` 路由到独立 Agent；
2. 使用 `per-channel-peer` 持久会话，不使用临时 Hook 任务作为正常入口；
3. Agent 只输出一个结构化最终回复，插件直接调用 `/api/pets/<pet_id>/respond`；
4. 正常聊天不需要 Desktop Pet MCP，MCP 仅保留为可选通用控制接口；
5. 长期记忆仅修改 Agent `MEMORY.md` 的桌宠受控区域；
6. 新默认值由代码提供并写入用户配置，不修改 `config/default_config.json`。

保留这个短归档仅用于解释历史决策；所有可执行配置、API 契约和排障步骤以 `docs/openclaw-*.md` 为准。
