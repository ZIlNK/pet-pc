# Desktop Pet × OpenClaw 运维与排障手册

本文针对当前推荐的持久化 `pet-bubble` Channel 链路。完整配置步骤见 [`openclaw-integration.md`](openclaw-integration.md)，数据流见 [`openclaw-architecture.md`](openclaw-architecture.md)。

## 1. 启动与停止

建议在两个独立终端运行常驻进程。

Desktop Pet：

```powershell
Set-Location D:\code\pet-pc
uv run desktop-pet --verbose
```

OpenClaw Gateway：

```powershell
openclaw gateway
```

如果安装程序生成了专用脚本，可以使用实际脚本启动；例如部分 Windows 环境存在 `~/.openclaw/gateway.cmd`。不要把该路径当作跨环境固定命令。

### “命令卡住”是否正常

两条命令都启动常驻服务，正常情况下不会自动返回提示符。Gateway 首次启动、插件加载或鉴权预热可能持续 60～90 秒。判断启动状态应看日志和端口，不要因为终端被占用就重复启动第二个 Gateway。

检查端口：

```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -In 18789,8080
```

检查 Desktop Pet API：

```powershell
Invoke-RestMethod http://127.0.0.1:8080/api/status
```

停止时在各自终端按 `Ctrl+C`，或通过应用正常退出。不要用不加区分的批量杀进程命令。

## 2. 日志来源

### Desktop Pet

Desktop Pet 默认把日志输出到启动终端；`--verbose` 开启 DEBUG 级别。重点过滤：

```text
[ChatBubble]
[OpenClaw]
[OpenClaw Reply]
desktop_pet.api_server
```

Channel 接收成功时通常能看到：

```text
[OpenClaw] Message forwarded via channel to http://127.0.0.1:18789/pet-bubble-webhook for pet <pet_id>
```

### OpenClaw Gateway

优先查看 Gateway 启动终端。OpenClaw 还可能在用户目录的 `.openclaw/logs` 下维护运行日志，具体文件名由安装和服务方式决定。

关键结构化日志：

```text
[pet-bubble route] pet=<pet_id> agent=<agent_id> sessionKey=...
[pet-bubble inbound] accepted pet=<pet_id> agent=<agent_id> messageId=...
[pet-bubble outbound] to=<pet_id> mode=respond structured=true elapsedMs=...
[pet-bubble dispatch] completed pet=<pet_id> elapsedMs=...
```

错误会区分：鉴权、请求体、未知 Agent、binding 不匹配、Agent dispatch、桌宠回调等阶段。

## 3. 用日志定位时延

一次请求可拆为四段：

| 阶段 | 观察方式 | 含义 |
|---|---|---|
| Desktop Pet → Gateway 接收 | 桌宠转发日志到 `inbound accepted` | 本地 HTTP、鉴权和请求校验 |
| Route | `route` 日志 | binding 和 session key 解析 |
| Agent dispatch | `inbound accepted` 到 `dispatch completed` | Agent Runtime、插件/技能准备、模型调用、重试和最终回复 |
| Gateway → Desktop Pet | `outbound elapsedMs` | 结构解析和本地 `/respond` HTTP |

判断方法：

- `202 Accepted` 在数百毫秒内，但 `dispatch completed` 约 60 秒：瓶颈在 Gateway Agent Runtime、模型服务或上游 socket 重试，不在 Desktop Pet HTTP。
- `outbound elapsedMs` 只有几十毫秒：桌宠回调和 UI 调度不是主要耗时。
- `route` 很慢或没有出现：检查 Gateway 是否完成启动、插件是否加载、binding 是否可解析。
- `inbound accepted` 出现但没有 `outbound`：检查 Agent 执行错误、模型超时、会话日志以及是否生成 final 回复。
- `outbound` 出现但桌宠无气泡：检查 `desktopApiBase`、API 端口、共享密钥和目标 `pet_id`。

推荐分别记录：

```text
accept latency
route/session latency
runtime preparation latency
model first-token / completion latency
outbound callback latency
full dispatch latency
```

不要只用“用户等待总时长”判断是哪一层慢。

### 当前链路不应有 MCP 开销

普通聊天不应启动 `desktop-pet-mcp`，会话轨迹中应看到：

```text
toolMetas=[]
startedCount=0
completedCount=0
```

也不应出现 `desktop-pet__respond_as_pet`。如果出现，说明 Agent 工具集或旧提示仍把 MCP 带回聊天链路，应移除该 MCP Server 或工具授权后重启 Gateway。

## 4. 无回复排查顺序

按以下顺序停止在第一个异常阶段：

1. **Desktop Pet 是否记录用户消息**
   - 应出现 `[ChatBubble] User sent message`。
2. **是否使用 Channel**
   - 应记录 `forwarded via channel`，不应是 `/hooks/agent`。
3. **Gateway 是否返回 202**
   - `401/403`：共享密钥不一致；
   - `404`：插件未加载或 URL 错误；
   - `409`：请求 Agent 与 exact binding 不一致；
   - `500`：Channel Runtime API 不可用或插件内部错误。
4. **是否出现 `pet-bubble route`**
   - 检查 `channel=pet-bubble`、`accountId=default`、`peer.id=<pet_id>` 的 binding。
5. **是否出现 `pet-bubble outbound`**
   - 没有：继续看 Agent/模型/dispatch 错误；
   - 有：继续检查回调。
6. **Desktop Pet 是否收到 `/respond`**
   - 确认 `desktopApiBase=http://127.0.0.1:8080/api`；
   - 确认 API 正在监听；
   - 确认目标实例仍在运行；
   - 当前 `/respond` 主要依赖 loopback 和 Desktop API IP 白名单；若走兼容 `/api/openclaw/reply`，再确认 `X-HTTP-Channel-Secret` 与 `openclaw_secret_token` 一致。

## 5. 回复来自 Hook 还是 Channel

正常推荐链路只有 Channel：

```text
POST /pet-bubble-webhook
→ [pet-bubble inbound/outbound]
→ POST /api/pets/<pet_id>/respond
```

如果仍看到 `/hooks/agent`：

- 全局设置中的 **独立 Agent 传输** 仍为 `Hooks（兼容模式）`；
- 新配置尚未保存或桌宠未重启；
- 目标实例没有启用独立 Agent，因此走了旧全局 webhook；
- 同时运行了旧 `openclaw-http-channel` 或其他桥接器。

稳定验证后应禁用功能重叠的旧 Channel 插件，避免两条相似链路同时接收消息。

## 6. 重复回复

当前正常路径是“一个结构化 final → 一次 `/respond`”。出现重复气泡时检查：

- 是否同时启用了 Hooks 和 Channel 的外部转发；
- 是否有旧插件仍回调 `/api/openclaw/reply`；
- Agent 是否仍调用 `respond_as_pet` MCP 工具；
- 客户端超时后是否被人为再次发送；
- 是否启动了两个 Gateway 实例。

Desktop Pet 保留 10 秒文字指纹去重，但它只是兼容保护，不应代替修复重复链路。

## 7. 结构化回复异常

期望日志：

```text
mode=respond structured=true
```

如果是 `structured=false`：

- Agent 没有只输出一个 JSON 对象；
- 回复被 Markdown 之外的说明文字包围；
- `text` 为空或超过 1000 字符；
- `duration` 不是 0～60000 的整数；
- `animation` 类型非法。

插件会降级为纯文字，不会因为 JSON 解析失败丢失回复。若文本超过 `/respond` 限制，则使用兼容 `/api/openclaw/reply` 路径。

动画名不存在时 Desktop Pet 仍显示文字，这是设计内降级，不是请求失败。

## 8. 上下文不连续

检查：

- `session.dmScope` 是否为 `per-channel-peer`；
- 同一宠物多轮日志中的 `sessionKey` 是否稳定；
- binding 中 `peer.id` 是否等于真实 `pet_id`；
- 是否误切回 `/hooks/agent`；
- 是否重建、删除或切换了 Agent 工作区；
- 是否存在多个 `pet_id` 绑定到同一 Agent 并混用人格。

Channel 模式不会使用实例配置中的 `hook:pet:<pet_id>` 作为会话键。该字段只为 Hooks 兼容保留。

## 9. 记忆管理故障

| 现象 | 原因/处理 |
|---|---|
| `403` | `X-Pet-Bubble-Secret` 错误或缺失 |
| `404 unknown agentId` | Agent 不在 OpenClaw `agents.list` |
| `409` | `MEMORY.md` 受控标记重复、缺失一半、顺序错误或未独占一行 |
| 连接失败 | Gateway 未启动、Hooks URL 指向了错误的 Gateway 基址、端口错误或插件未加载 |
| 清空后人工内容消失 | 不应发生；停止写入并从备份恢复，检查是否绕过了插件接口 |

受控区域标记：

```text
<!-- desktop-pet-managed-memory:start -->
<!-- desktop-pet-managed-memory:end -->
```

不要在 UI 外手动复制或重复这些标记。结构损坏时插件会拒绝写入，而不是自动重写整份文件。记忆 UI 当前从全局 **OpenClaw Hooks URL** 推导 Gateway 基址，因此即使使用 Channel，也应让该 URL 指向同一个 Gateway。

## 10. Gateway 启动锁

Gateway 异常退出后，临时目录可能留下 `gateway.*.lock`。只有在确认锁记录的 PID 已不存在时才能删除。

安全检查流程：

```powershell
$locks = Get-ChildItem "$env:TEMP\openclaw" -Filter 'gateway.*.lock' -File
$locks | Select-Object FullName,Length,LastWriteTime
Get-Content -LiteralPath '<exact-lock-path>'
Get-Process -Id <pid-from-lock>
```

- 如果 PID 仍存在，不要删除锁，也不要启动第二个 Gateway；
- 如果 PID 明确不存在，重新核对解析后的绝对路径位于 `$env:TEMP\openclaw`，再只删除该文件：

```powershell
Remove-Item -LiteralPath '<exact-verified-lock-path>'
```

禁止对临时目录执行递归或通配删除。

## 11. 回滚到 Hooks

仅在 Channel 与当前 OpenClaw 版本不兼容时手动回滚：

1. 在 OpenClaw 开启 `hooks.enabled`；
2. 配置独立 Hooks Bearer Token；
3. 允许请求 session key，并限制前缀为 `hook:pet:`；
4. 将允许调用的 Agent ID 加入 `hooks.allowedAgentIds`；
5. Desktop Pet 全局设置把传输改为 `Hooks（兼容模式）`；
6. 填写 Hooks URL 和 Bearer Token；
7. 重启 Desktop Pet。

示意配置：

```json
{
  "hooks": {
    "enabled": true,
    "token": "<separate-hooks-bearer-token>",
    "allowRequestSessionKey": true,
    "allowedSessionKeyPrefixes": ["hook:pet:"],
    "allowedAgentIds": ["pet_razor"]
  }
}
```

Hooks 回滚不需要迁移 `MEMORY.md`，但可能恢复临时任务初始化、额外安全包装和较弱的短期上下文体验。不要配置 Channel 请求失败后自动补发 Hook。

## 12. 发布前检查

```powershell
Set-Location D:\code\pet-pc
uv run pytest
Set-Location D:\code\pet-pc\openclaw-plugins\pet-bubble
npm test
```

然后执行至少五轮真实会话，验证：

- 只出现 `pet-bubble inbound/outbound`；
- 同一宠物 session key 稳定；
- 回复回到正确宠物且只显示一次；
- `structured=true`；
- 上下文连续；
- 记忆增删不影响 `MEMORY.md` 受控区域外内容；
- 没有 `desktop-pet-mcp` 进程和工具调用。
