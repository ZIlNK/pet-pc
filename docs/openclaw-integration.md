# Desktop Pet 接入 OpenClaw 指南

本文面向第一次部署 Desktop Pet × OpenClaw 的开发者和使用者。当前推荐链路是持久化 `pet-bubble` Channel；普通聊天、性格、上下文、长期记忆、文字气泡和动画回复均不需要 Desktop Pet MCP Server。

> 当前实现已在 OpenClaw `2026.6.11` 上完成端到端验证。插件包声明 `openclaw >= 2026.6.1`，但实际兼容性取决于 OpenClaw Channel Runtime API；升级 OpenClaw 后应重新运行插件测试和端到端验证。

## 1. 最终链路

```text
Desktop Pet 聊天气泡
  → POST /pet-bubble-webhook
  → OpenClaw 精确 binding 选择 Agent
  → 持久化 direct session
  → Agent 输出一个结构化最终回复
  → pet-bubble 插件解析回复
  → POST /api/pets/<pet_id>/respond
  → 原桌宠显示文字并可选播放动画
```

职责边界：

- **OpenClaw 是大脑**：Agent、模型、`SOUL.md`、`IDENTITY.md`、`USER.md`、会话上下文和 `MEMORY.md`。
- **Desktop Pet 是身体**：宠物实例、聊天气泡、动画、配置 UI 和本地 HTTP API。
- 每只启用独立 AI 的宠物绑定一个唯一 Agent。路由权威是 OpenClaw 的精确 `bindings`，客户端请求中的 `agentId` 只用于交叉校验。

## 2. 前置条件

- Python 3.10+、`uv`，并已安装 OpenClaw。
- Desktop Pet API 和 OpenClaw Gateway 均只监听本机回环地址。
- OpenClaw 中已创建目标 Agent；本项目首版不负责创建或删除 Agent。
- 确认 Gateway 端口，本文使用默认示例 `127.0.0.1:18789`。

安装项目依赖：

```powershell
Set-Location D:\code\pet-pc
uv sync
```

启动 Desktop Pet：

```powershell
uv run desktop-pet
```

在全局设置中启用本地 HTTP API，推荐：

```text
Host: 127.0.0.1
Port: 8080
```

确认 API 可用：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/status
Invoke-RestMethod http://127.0.0.1:8080/api/instances
```

记录要接入的 `pet_id`。也可以在主程序运行后执行：

```powershell
uv run desktop-pet list
```

## 3. 创建并准备 OpenClaw Agent

通过 OpenClaw 自己的 CLI、UI 或配置方式创建 Agent，例如 `pet_razor`。最终必须满足：

- `agents.list` 中真实存在该 `id`；
- Agent 有独立工作区；
- 不同独立桌宠不要复用同一个 Agent ID；
- Agent 工作区可按需要维护：
  - `SOUL.md`：性格与行为原则；
  - `IDENTITY.md`：名字、身份和自我认知；
  - `USER.md`：用户偏好；
  - `MEMORY.md`：长期记忆。

桌宠不会复制这些人格文件，也不会在本地创建第二套向量数据库。

## 4. 生成共享密钥

Channel 入站、记忆管理和兼容 `/api/openclaw/reply` 回调使用同一个 `sharedSecret`。结构化正常回复会携带同名回调头，但当前 `/api/pets/<pet_id>/respond` 主要依赖 loopback 与 Desktop Pet API IP 白名单。不要把真实密钥提交到仓库。

PowerShell 生成 32 字节随机十六进制密钥：

```powershell
$bytes = [byte[]]::new(32)
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$secret = ($bytes | ForEach-Object { $_.ToString('x2') }) -join ''
$secret
```

将结果同时填入：

- OpenClaw：`channels.pet-bubble.sharedSecret`；
- Desktop Pet：`mcp.openclaw_secret_token`，或设置页中的 **OpenClaw callback secret**。

Hooks Bearer Token 是另一套凭据，只在兼容模式使用，不要与该密钥复用。

## 5. 加载 `pet-bubble` 插件

将以下片段合并进 OpenClaw 配置。不要整份覆盖现有 `agents`、`plugins`、`channels` 或 `bindings`。

```json
{
  "plugins": {
    "entries": {
      "pet-bubble": {
        "enabled": true
      }
    },
    "load": {
      "paths": [
        "D:\\code\\pet-pc\\openclaw-plugins\\pet-bubble"
      ]
    }
  },
  "channels": {
    "pet-bubble": {
      "enabled": true,
      "webhookPath": "/pet-bubble-webhook",
      "webhookHost": "127.0.0.1",
      "desktopApiBase": "http://127.0.0.1:8080/api",
      "sharedSecret": "<generate-a-random-shared-secret>",
      "autoReply": true
    }
  }
}
```

插件是纯 ESM，无构建步骤。通过 `plugins.load.paths` 直接加载源码；修改插件后必须重启 Gateway。

## 6. 配置精确 Agent binding 和持久会话

为每只独立桌宠增加一条 `pet_id → agentId` 精确 binding：

```json
{
  "bindings": [
    {
      "agentId": "pet_razor",
      "match": {
        "channel": "pet-bubble",
        "accountId": "default",
        "peer": {
          "kind": "direct",
          "id": "<pet_id>"
        }
      }
    }
  ],
  "session": {
    "dmScope": "per-channel-peer"
  },
  "messages": {
    "queue": {
      "mode": "steer",
      "debounceMsByChannel": {
        "pet-bubble": 0
      }
    }
  }
}
```

关键规则：

- `peer.id` 必须与 Desktop Pet 实例的 `pet_id` 完全一致；
- binding 选择出的 Agent 必须与桌宠实例配置中的 Agent ID 一致，否则插件返回 `409`；
- 同一桌宠的会话键形如 `agent:<agent_id>:pet-bubble:direct:<pet_id>`；
- `dmScope=per-channel-peer` 使同一桌宠复用上下文，不同桌宠隔离会话；
- 新增宠物时必须新增对应 binding，并重启或按 OpenClaw 支持方式重新加载配置。

仓库中的 [`../openclaw-e2e.patch.json5`](../openclaw-e2e.patch.json5) 是不含真实密钥的合并示例。

## 7. 配置 Desktop Pet 全局设置

打开 **设置中心 → 全局设置 → MCP 设置**。这里的分组名称沿用历史命名，但推荐 Channel 聊天并不要求启用 MCP Server。

填写：

| 设置项 | 值 |
|---|---|
| 独立 Agent 传输 | `Pet Bubble Channel` |
| Pet Bubble Channel URL | `http://127.0.0.1:18789/pet-bubble-webhook` |
| OpenClaw callback secret | 与 `channels.pet-bubble.sharedSecret` 相同 |
| OpenClaw Hooks URL | 保持指向同一 Gateway，例如 `http://127.0.0.1:18789/hooks/agent`；记忆管理 UI 也据此推导 `/pet-bubble-memory` 地址 |
| Hooks Bearer Token | Channel 模式可留空 |
| 启用 MCP 服务 | 当前聊天链路不要求启用 |

保存后配置写入 `config/user_config.json`。代码默认值仍以 `hooks` 保持旧配置兼容，因此新部署必须显式选择 `Pet Bubble Channel`。

## 8. 配置桌宠实例

打开目标宠物的配置页，在 **AI Agent** 分组中：

1. 勾选 **启用独立 OpenClaw Agent**；
2. 填入与 binding 相同的 Agent ID，例如 `pet_razor`；
3. 选择回复长度：`short`、`normal` 或 `detailed`；
4. 选择主动性：`low`、`normal` 或 `high`；
5. 保存配置。

会话标识由系统生成并只读。Channel 模式不把这个 Hook session key 发送给 OpenClaw；持久会话键由 OpenClaw binding 和 session scope 生成。

启用独立 AI 的不同宠物不能绑定同一个 Agent ID。点击 **管理长期记忆** 可以管理该 Agent 的受控 `MEMORY.md` 区域。

## 9. 启动顺序

建议使用两个终端：

终端 A：

```powershell
Set-Location D:\code\pet-pc
uv run desktop-pet --verbose
```

终端 B：

```powershell
openclaw gateway
```

如果 OpenClaw 安装方式生成了 Windows 启动脚本，也可以运行对应脚本，例如 `~/.openclaw/gateway.cmd`；这不是所有环境都存在的通用命令。

Gateway 是常驻进程，命令不会自行退出。首次启动或插件、鉴权预热可能持续 60～90 秒，不要因为终端持续占用就重复启动第二个 Gateway。

## 10. 端到端验证

1. 在目标桌宠聊天气泡中发送一条短消息。
2. Desktop Pet 应快速记录 Channel 转发成功。
3. Gateway 应依次出现类似日志：

```text
[pet-bubble route] pet=<pet_id> agent=<agent_id> sessionKey=...
[pet-bubble inbound] accepted pet=<pet_id> agent=<agent_id> messageId=...
[pet-bubble outbound] to=<pet_id> mode=respond structured=true elapsedMs=...
[pet-bubble dispatch] completed pet=<pet_id> elapsedMs=...
```

4. 回复应只显示一次，并回到原桌宠。
5. 连续发送至少五轮，确认 Agent 能记住上一轮上下文。
6. 检查会话轨迹时，当前推荐链路应没有 Desktop Pet MCP 工具调用：

```text
toolMetas=[]
startedCount=0
completedCount=0
```

Agent 的最终输出协议是：

```json
{
  "text": "回复内容",
  "animation": "sit",
  "duration": 15000
}
```

`animation` 可以为 `null`。插件从可信 Channel 路由取得 `pet_id`，模型不得输出 `pet_id`。结构不合法时降级为纯文字；动画不存在时桌宠降级为文字回复。

## 11. MCP 什么时候才需要

当前 OpenClaw 聊天链路不需要运行 `desktop-pet-mcp`，也不需要在 OpenClaw 中添加 Desktop Pet MCP Server。

仅当 Agent 需要聊天之外的通用控制能力时再配置 MCP，例如：

- 查询桌宠状态或可用动画；
- 主动移动、行走或播放动画；
- 创建、列举或删除桌宠实例；
- 让其他 MCP 客户端控制 Desktop Pet。

可选 OpenClaw 配置使用当前结构 `mcp.servers`：

```json
{
  "mcp": {
    "servers": {
      "desktop-pet": {
        "command": "uv",
        "args": [
          "--directory",
          "D:\\code\\pet-pc",
          "run",
          "desktop-pet-mcp"
        ]
      }
    }
  }
}
```

MCP Server 从 `/api/tools` 动态发现工具。不要把 MCP 加回普通桌宠回复链路，否则会增加 Runtime 和工具打包开销，并重新引入两条回复路径。

## 12. 下一步

- 架构和信任边界：[`openclaw-architecture.md`](openclaw-architecture.md)
- 启停、日志、时延和故障排查：[`openclaw-runbook.md`](openclaw-runbook.md)
- 本次能力汇总：[`CHANGES.md`](CHANGES.md)
