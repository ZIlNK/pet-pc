# Pet Bubble Channel Plugin 实施文档

> 状态：🚧 实施中 · 简化方案 v0.4
> 创建：2026-06-17
> 更新：2026-06-17 — 简化链路（去掉文件钩子+PowerShell 桥接器，改为 httpx 直接 POST）
> 适用：解决桌宠气泡消息无法实时触发 OpenClaw session turn 的架构问题
> 目标读者：自己（按本文档照做即可）、未来要做类似接入的同事

---

## 0. 一句话总结

把桌宠气泡消息做成 OpenClaw 的**一个 channel**（和飞书、Telegram 平级），走标准 channel 路径触发 session turn。桌宠侧直接用 httpx POST 到 webhook，无需文件钩子和 PowerShell 桥接器。延迟 ~1-2 秒，干净隔离，长期受益。

---

## 1. 为什么需要这个

### 1.1 现状

桌宠 GUI（PyQt5）通过 `add_user_message()` 把用户气泡消息入队，**仅提供被动查询接口** `get_user_messages`。AI 必须主动轮询才知道有消息，**不能实时接收**。

### 1.2 已尝试方案及失败原因

| 方案 | 做法 | 结果 |
|------|------|------|
| **方案 C：文件钩子 + `system event`** | PowerShell 监听文件 → `openclaw system event --session-key <dashboard> --mode now` | 注入返回 `ok`，但 dashboard session **不触发 turn**（OpenClaw dashboard session 仅响应 webchat 客户端发来的 user prompt）。失败。 |
| **方案变体：`openclaw agent --session-key <dashboard>`** | 用 agent run 替代 system event | 同样不触发 turn。失败。 |
| **方案变体：`--deliver`** | 显式 deliver 到 webchat | 需要 `target <chatId|user:openId|chat:chatId>`，webchat 不是 messaging channel。失败。 |

**根本限制**：OpenClaw 的 dashboard session 是 webchat 客户端独占的入口，**外部进程无法直接给它加 turn**。`system event` 和 `agent --session-key` 都会"成功返回"，但不会真的唤醒。

### 1.3 真正的解：自定义 channel

OpenClaw 的 **channel plugin 架构**就是为这种场景设计的。飞书、Telegram、Discord 等 IM 平台就是按这套架构接入的——它们从 IM 平台收消息 → 转换为 OpenClaw envelope → 触发**独立 session turn**（不污染任何已有 session）。

**对桌宠来说**：把桌宠气泡消息当作"一个本地 IM 平台"来对待，就解决了所有限制。

---

## 2. 架构设计

### 2.1 整体流程（简化方案 v0.4）

```
┌─────────────┐  气泡输入   ┌──────────────────┐
│ 桌宠 GUI    │ ──────────> │  add_user_message │
│ (PyQt6)    │             │  (api_server.py)  │
└─────────────┘             └──────────┬─────────┘
                                       │ httpx.post() 直接 HTTP POST
                                       │ http://127.0.0.1:18789/pet-bubble-webhook
                                       │ Content-Type: application/json
                                       │ Body: {text, peer, timestamp, ...}
                                       ▼
┌──────────────────────────────────────────────────────────────┐
│  OpenClaw gateway (port 18789)                                │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  pet-bubble channel plugin                            │    │
│  │  - registerPluginHttpRoute(/pet-bubble-webhook)       │    │
│  │  - 解析 JSON body → InboundEnvelope                    │    │
│  │  - session route: pet-bubble:direct:<peer>            │    │
│  │  - 触发 turn                                         │    │
│  └──────────────────────────────────────────────────────┘    │
│                              ↓                                 │
│              ┌───────────────────────────┐                     │
│              │  新 turn                  │                     │
│              │  session: pet-bubble:     │                     │
│              │  direct:<peer>            │                     │
│              └───────────────────────────┘                     │
│                              ↓                                 │
│                       AI 收到消息                              │
│                              ↓                                 │
│              调 desktop-pet__show_message                      │
│              (桌宠 MCP 工具)                                   │
│                              ↓                                 │
│              ┌───────────────────────────┐                     │
│              │  桌宠 GUI 显示气泡回复     │                     │
│              └───────────────────────────┘                     │
└──────────────────────────────────────────────────────────────┘
```

**与原方案的关键差异**：去掉了 `$TEMP\pet_user_messages.jsonl` 文件钩子、FileSystemWatcher、PowerShell 桥接器三层中间件。桌宠 `add_user_message()` 直接用 httpx（已有依赖）POST 到 OpenClaw webhook。

### 2.2 链路延迟分解（简化方案）

| 环节 | 延迟 |
|------|------|
| 桌宠气泡提交 → add_user_message → httpx POST | < 50 ms |
| OpenClaw gateway 接收 + 解析 + session route | 50-100 ms |
| **小计（消息到 AI 看到）** | **~100-150 ms** |
| AI 模型响应 | 1-3 s（取决于模型） |
| AI 调 `show_message` → 桌宠 GUI 显示 | 100-500 ms |
| **总延迟** | **~1.5-4 秒** |

比原方案（文件钩子+PowerShell）减少 200-600ms 中间层延迟，且少 3 个故障点。

### 2.3 与方案 C 的关键差异

| 维度 | 方案 C（system event） | 路径 2（channel plugin） |
|------|------------------------|--------------------------|
| 链路 | 走 `system event` 命令 | 走 HTTP webhook |
| session 影响 | 注入 dashboard session（实际不触发） | 触发**独立 pet-bubble session** |
| 隔离 | 与 webchat 主对话混在一起 | 完全独立，不污染主对话 |
| 实时性 | 20 秒 + 经常失败 | ~1-2 秒 |
| 长期可维护 | 临时 hack | OpenClaw 原生机制 |
| 工作量 | 5 行代码 | ~400-500 行 |

---

## 3. Plugin 文件清单

实施 Pet Bubble Channel 需要 **1 个 npm package**（含 12 个文件）。代码全部在 `C:\Users\Ziink\openclaw-plugins\pet-bubble\` 下：

| 文件 | 作用 | 代码量 |
|------|------|--------|
| `package.json` | npm 包定义、依赖、plugin manifest | ~50 行 |
| `openclaw.plugin.json` | OpenClaw plugin 清单 | ~30 行 |
| `index.js` | plugin 入口（`defineBundledChannelEntry`） | ~30 行 |
| `channel-plugin-api.js` | 导出 `createChatChannelPlugin` 结果 | ~3 行（re-export） |
| `channel-main.js` | channel 核心实现：webhook 收消息 + 消息处理 | ~250 行 |
| `runtime-api.js` | runtime setter（plugin-sdk 注入 API） | ~30 行 |
| `secret-contract-api.js` | 密钥管理（本场景无密钥，给空实现） | ~10 行 |
| `account-inspect-api.js` | 账户检查（读 config 验证账户） | ~20 行 |
| `setup-entry.js` | 设置向导（可选，命令行交互） | ~80 行 |
| `channel-config-schema.js` | Zod schema 定义 account config | ~80 行 |
| `channel-inbound-handler.js` | HTTP webhook 处理函数 | ~80 行 |
| `README.md` | 本文档的精简版（仅 npm install + config） | ~30 行 |
| **小计** | — | **~700 行** |

**实际"业务逻辑"**：~300 行（channel-main.js + channel-inbound-handler.js），其余都是 OpenClaw 框架要求的 boilerplate。

---

## 4. 实施步骤

### Step 0：环境准备

```powershell
# 1. 创建 plugin 工作目录
mkdir C:\Users\Ziink\openclaw-plugins\pet-bubble
cd C:\Users\Ziink\openclaw-plugins\pet-bubble

# 2. 初始化 npm
npm init -y

# 3. 安装 OpenClaw plugin-sdk（devDependency）
# openclaw 是全局安装，链接到本地
npm link openclaw

# 4. 验证 link
node -e "import('openclaw/plugin-sdk/channel-core.js').then(m => console.log('OK:', Object.keys(m).slice(0, 5)))"
```

### Step 1：`package.json`

```json
{
  "name": "@local/pet-bubble",
  "version": "0.1.0",
  "description": "OpenClaw Pet Bubble channel — receives desktop pet chat messages",
  "type": "module",
  "main": "index.js",
  "exports": {
    ".": "./index.js"
  },
  "scripts": {
    "build": "echo 'No build step (pure ESM)'"
  },
  "peerDependencies": {
    "openclaw": ">=2026.6.1"
  },
  "openclaw": {
    "extensions": ["./index.js"],
    "setupEntry": "./setup-entry.js",
    "channel": {
      "id": "pet-bubble",
      "label": "Desktop Pet Bubble",
      "docsPath": "/channels/pet-bubble",
      "blurb": "Local channel for Desktop Pet GUI chat bubble messages."
    }
  }
}
```

### Step 2：`openclaw.plugin.json`

```json
{
  "id": "pet-bubble",
  "activation": {
    "onStartup": true
  },
  "channels": ["pet-bubble"],
  "channelEnvVars": {
    "pet-bubble": []
  },
  "configSchema": {
    "type": "object",
    "additionalProperties": false,
    "properties": {}
  },
  "channelConfigs": {
    "pet-bubble": {
      "schema": {
        "type": "object",
        "properties": {
          "webhookPath": {
            "type": "string",
            "default": "/pet-bubble-webhook"
          },
          "webhookHost": {
            "type": "string",
            "default": "127.0.0.1"
          },
          "webhookPort": {
            "type": "integer",
            "default": 0
          },
          "autoReply": {
            "type": "boolean",
            "default": true,
            "description": "Echo back AI replies to the pet GUI via MCP show_message"
          }
        }
      }
    }
  }
}
```

### Step 3：`index.js`（plugin 入口）

```javascript
// C:\Users\Ziink\openclaw-plugins\pet-bubble\index.js
import { defineBundledChannelEntry } from "openclaw/plugin-sdk/channel-entry-contract.js";
import { petBubbleChannelPlugin } from "./channel-main.js";

export default defineBundledChannelEntry({
  id: "pet-bubble",
  name: "Desktop Pet Bubble",
  description: "Local channel that receives desktop pet chat bubble messages via HTTP webhook",
  importMetaUrl: import.meta.url,
  plugin: {
    specifier: "./channel-plugin-api.js",
    exportName: "petBubbleChannelPlugin"
  },
  secrets: {
    specifier: "./secret-contract-api.js",
    exportName: "petBubbleChannelSecrets"
  },
  runtime: {
    specifier: "./runtime-api.js",
    exportName: "setPetBubbleRuntime"
  },
  accountInspect: {
    specifier: "./account-inspect-api.js",
    exportName: "inspectPetBubbleReadOnlyAccount"
  }
});
```

### Step 4：`channel-plugin-api.js`（re-export）

```javascript
// C:\Users\Ziink\openclaw-plugins\pet-bubble\channel-plugin-api.js
export { petBubbleChannelPlugin as default } from "./channel-main.js";
```

### Step 5：`channel-main.js`（核心：~250 行）

```javascript
// C:\Users\Ziink\openclaw-plugins\pet-bubble\channel-main.js
import { createChatChannelPlugin } from "openclaw/plugin-sdk/channel-core.js";
import { registerPluginHttpRoute, readJsonWebhookBodyOrReject } from "openclaw/plugin-sdk/webhook-ingress.js";
import { normalizePluginHttpPath } from "openclaw/plugin-sdk/http-path.js";
import { z } from "zod";

// ── 1. Account config schema (Zod) ──────────────────────
const AccountConfigSchema = z.object({
  webhookPath: z.string().default("/pet-bubble-webhook"),
  webhookHost: z.string().default("127.0.0.1"),
  webhookPort: z.number().int().min(0).max(65535).default(0),
  autoReply: z.boolean().default(true),
  // 单账户配置：固定 accountId = "default"
  accountId: z.string().default("default").optional(),
  name: z.string().optional()
});

// ── 2. Pet Bubble channel plugin ────────────────────────
export const petBubbleChannelPlugin = createChatChannelPlugin({
  base: {
    id: "pet-bubble",
    meta: {
      label: "Desktop Pet Bubble",
      blurb: "Local channel for desktop pet chat bubble messages",
      systemImage: "pet"
    },
    
    // 账户配置解析
    resolveAccount: ({ accountId, cfg }) => {
      const ch = cfg?.channels?.["pet-bubble"] ?? {};
      const accountCfg = accountId && accountId !== "default"
        ? ch.accounts?.[accountId]
        : ch;
      return AccountConfigSchema.parse({
        accountId: accountId ?? "default",
        ...accountCfg
      });
    },
    
    // ── 核心：注册 HTTP webhook 路由 ────────────────────
    setup: async ({ account, api, runtime }) => {
      const path = normalizePluginHttpPath(account.webhookPath);
      
      api.registerHttpRoute({
        path,
        handler: async (req, res) => {
          try {
            // 1. 解析 HTTP body（限制 64 KB，强制 JSON）
            const body = await readJsonWebhookBodyOrReject(req, res, {
              maxBytes: 64 * 1024,
              timeoutMs: 5000
            });
            
            // 2. 校验必要字段
            if (!body.text || typeof body.text !== "string") {
              res.statusCode = 400;
              res.end(JSON.stringify({ error: "Missing or invalid 'text' field" }));
              return;
            }
            
            const peer = body.peer || "default";  // 桌宠默认只有 1 个用户
            const timestamp = body.timestamp || new Date().toISOString();
            
            // 3. 构建 inbound envelope（OpenClaw 标准格式）
            const envelope = {
              channel: "pet-bubble",
              accountId: account.accountId ?? "default",
              chatType: "direct",          // 桌宠是点对点
              peer: { kind: "direct", id: peer },
              from: peer,                  // sender id
              to: "pet-bubble-bot",        // bot id
              messageId: `pet-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              timestamp,
              text: body.text,
              // 透传额外元数据
              metadata: body.metadata ?? {}
            };
            
            // 4. 路由到 OpenClaw 处理
            // （plugin-sdk 的 channel framework 会创建/复用 session 并触发 turn）
            runtime.channel.dispatch?.(envelope);
            
            // 5. 返回 200 OK
            res.statusCode = 200;
            res.end(JSON.stringify({ ok: true, messageId: envelope.messageId }));
            
          } catch (err) {
            runtime.log?.error("pet-bubble webhook error", err);
            res.statusCode = 500;
            res.end(JSON.stringify({ error: String(err) }));
          }
        }
      });
      
      api.log?.info?.(`pet-bubble webhook registered at ${path}`);
    }
  },
  
  // ── Outbound：把 AI 回复发回桌宠 ──────────────────────
  outbound: {
    // 不需要真正"发出去"——AI 通过 MCP 工具 show_message 把回复显示在桌宠 GUI
    // 这里只需返回成功，让 OpenClaw 知道"已发送"
    sendText: async (ctx) => {
      // ctx = { text, account, peer, ... }
      ctx.log?.info?.(`[pet-bubble outbound] ${ctx.text}`);
      // 实际显示：AI 已经在调 desktop-pet__show_message 显示了
      return { ok: true, channel: "pet-bubble", messageId: `out-${Date.now()}` };
    }
  }
});

export { AccountConfigSchema };
```

### Step 6：`runtime-api.js`（runtime setter）

```javascript
// C:\Users\Ziink\openclaw-plugins\pet-bubble\runtime-api.js
let currentRuntime = null;

export function setPetBubbleRuntime(runtime) {
  currentRuntime = runtime;
}

// 给 channel-main.js 用
export function getPetBubbleRuntime() {
  return currentRuntime;
}
```

### Step 7：`secret-contract-api.js`（无密钥，给空）

```javascript
// C:\Users\Ziink\openclaw-plugins\pet-bubble\secret-contract-api.js
export const petBubbleChannelSecrets = {
  // 桌宠是本地 channel，不需要 secret
  listSecretNames: () => [],
  resolveSecret: async () => null
};
```

### Step 8：`account-inspect-api.js`

```javascript
// C:\Users\Ziink\openclaw-plugins\pet-bubble\account-inspect-api.js
export const inspectPetBubbleReadOnlyAccount = {
  // OpenClaw 用这个列出所有 account 状态
  listAccounts: async (cfg) => {
    const ch = cfg?.channels?.["pet-bubble"];
    if (!ch) return [];
    return [{
      accountId: "default",
      enabled: ch.enabled !== false,
      name: ch.name ?? "Desktop Pet Bubble"
    }];
  }
};
```

### Step 9：`setup-entry.js`（可选：交互式安装）

```javascript
// C:\Users\Ziink\openclaw-plugins\pet-bubble\setup-entry.js
import { defineSetupPluginEntry } from "openclaw/plugin-sdk/setup.js";

export const petBubbleSetup = defineSetupPluginEntry({
  id: "pet-bubble",
  label: "Desktop Pet Bubble",
  runSetup: async ({ prompt, log }) => {
    const path = await prompt.text({
      message: "Webhook path",
      defaultValue: "/pet-bubble-webhook"
    });
    const autoReply = await prompt.confirm({
      message: "Auto-reply via MCP show_message?",
      defaultValue: true
    });
    return {
      channels: {
        "pet-bubble": {
          webhookPath: path,
          autoReply
        }
      }
    };
  }
});
```

### Step 10：OpenClaw 配置启用 channel

编辑 `C:\Users\Ziink\.openclaw\config.yaml`（或 `config.json`，看老板的实际配置）：

```yaml
channels:
  pet-bubble:
    enabled: true
    webhookPath: /pet-bubble-webhook
    autoReply: true
plugins:
  allow:
    - "@local/pet-bubble"  # 加入白名单
```

### Step 11：链接 + 安装 plugin

```powershell
# 1. 在 plugin 目录执行 npm link
cd C:\Users\Ziink\openclaw-plugins\pet-bubble
npm link

# 2. 在 OpenClaw 全局链接
# （OpenClaw 通过 npm global 安装，plugins 目录在 ~/.openclaw/npm/projects/）
mkdir C:\Users\Ziink\.openclaw\npm\projects\pet-bubble-<hash> -ErrorAction SilentlyContinue
cd C:\Users\Ziink\.openclaw\npm\projects\pet-bubble-<hash>
npm link @local/pet-bubble

# 3. 或用 openclaw plugins install（如果支持）
openclaw plugins install C:\Users\Ziink\openclaw-plugins\pet-bubble
```

### Step 12：重启 OpenClaw gateway

```powershell
# 重启 OpenClaw 让 plugin 生效
openclaw restart
# 或通过 OpenClaw UI
```

### Step 13：注册 plugin 到 OpenClaw plugin 列表

OpenClaw 会在 `~/.openclaw/npm/projects/` 自动发现 npm-link 的 plugin。验证：

```powershell
openclaw plugins list | Select-String "pet-bubble"
# 期望看到：@local/pet-bubble  enabled  ...
```

### Step 14：端到端联调

```powershell
# 1. 启动桌宠（源码模式）
cd D:\code\pet-pc
D:\code\pet-pc\.venv\Scripts\python.exe main.py --verbose

# 2. 启动 PowerShell 桥接器（之前方案 C 那个）
Start-Process powershell -ArgumentList "-ExecutionPolicy","Bypass","-File","D:\code\pet-pc\scripts\pet_to_openclaw_bridge.ps1"

# 3. 修改桥接器 inject 方式：从 system event 改为 HTTP POST
# 详见 §5 桥接器修改

# 4. 在桌宠气泡发消息
# 5. 观察 OpenClaw 是否有新 session turn
openclaw sessions list --active 5
# 期望看到 session key 类似 agent:pet-bubble:direct:default
```

---

## 5. 桌宠侧改动（简化方案）

**原方案**：`add_user_message` 写文件钩子 → PowerShell 桥接器监听 → HTTP POST。

**简化方案**：`add_user_message` 直接用 httpx POST 到 OpenClaw webhook。无需文件钩子、无需 PowerShell 桥接器。

### 5.1 修改 `api_server.py` 的 `add_user_message`

在 `src/desktop_pet/api_server.py` 中：

1. 删除 `USER_MESSAGE_HOOK_PATH` 常量和文件写入逻辑
2. 新增 `_forward_to_openclaw` 方法，用 httpx 异步 POST
3. `add_user_message` 调用 `_forward_to_openclaw`

```python
# 新增配置项（从 config 读取）
OPENCLAW_WEBHOOK_URL = "http://127.0.0.1:18789/pet-bubble-webhook"
OPENCLAW_PEER = "boss"

async def _forward_to_openclaw(self, text: str, timestamp: str) -> None:
    """将用户消息直接 POST 到 OpenClaw pet-bubble channel webhook"""
    body = {
        "text": text,
        "peer": self._openclaw_peer,
        "timestamp": timestamp,
        "metadata": {"source": "pet-bubble"}
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(self._openclaw_webhook_url, json=body)
            if resp.status_code == 200:
                logger.info(f"[OpenClaw] Message forwarded: {text[:50]}")
            else:
                logger.warning(f"[OpenClaw] Webhook returned {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.warning(f"[OpenClaw] Failed to forward message: {e}")

def add_user_message(self, text: str) -> None:
    """将用户消息添加到队列并转发到 OpenClaw"""
    msg = {"text": text, "timestamp": datetime.now().isoformat()}
    self._user_messages.append(msg)
    # 异步转发到 OpenClaw（不阻塞 UI）
    asyncio.ensure_future(
        self._forward_to_openclaw(text, msg["timestamp"]),
        loop=self._loop
    )
```

### 5.2 配置项

在 `config/default_config.json` 的 `mcp` 节下新增：

```json
{
  "mcp": {
    "openclaw_webhook_url": "http://127.0.0.1:18789/pet-bubble-webhook",
    "openclaw_peer": "boss"
  }
}
```

用户可在 `user_config.json` 中覆盖。

---

## 6. 关键 OpenClaw API 参考

| API | 来源 | 作用 |
|-----|------|------|
| `createChatChannelPlugin` | `openclaw/plugin-sdk/channel-core.js` | 工厂函数，返回一个完整 channel plugin |
| `defineBundledChannelEntry` | `openclaw/plugin-sdk/channel-entry-contract.js` | plugin 入口包装 |
| `registerPluginHttpRoute` | `openclaw/plugin-sdk/webhook-ingress.js` | 注册 HTTP 路由 |
| `readJsonWebhookBodyOrReject` | `openclaw/plugin-sdk/webhook-ingress.js` | 解析+校验 JSON body |
| `normalizePluginHttpPath` | `openclaw/plugin-sdk/http-path.js` | 路径规范化 |
| `defineSetupPluginEntry` | `openclaw/plugin-sdk/setup.js` | setup 向导 |

**详细类型定义位置**：
- `C:\Users\Ziink\AppData\Roaming\npm\node_modules\openclaw\dist\plugin-sdk\channel-core.d.ts`
- `C:\Users\Ziink\AppData\Roaming\npm\node_modules\openclaw\dist\plugin-sdk\webhook-ingress.d.ts`
- `C:\Users\Ziink\AppData\Roaming\npm\node_modules\openclaw\dist\plugin-sdk\core-B8oTXuCC.d.ts`

**强烈建议**：实施前先看飞书 plugin 的 `channel-DTfK2nVn.js`（2635 行）作为参考。`createChatChannelPlugin` 的所有字段飞书都用到了。

---

## 7. 验证清单

按顺序验证：

| # | 验证项 | 命令 | 期望结果 |
|---|--------|------|----------|
| 1 | plugin 加载 | `openclaw plugins list` | 看到 `@local/pet-bubble` |
| 2 | channel 注册 | `openclaw channels list --all` | 看到 `pet-bubble` |
| 3 | gateway 监听 webhook | `netstat -an \| findstr 18789` | 18789 端口在 LISTENING |
| 4 | webhook 路径生效 | `curl http://127.0.0.1:18789/pet-bubble-webhook -X POST -d '{}'` | 返回 400 + "Missing text" |
| 5 | 完整链路 | 桌宠发消息 → 桥接器 → HTTP POST → session turn | `openclaw sessions list --active 5` 出现新 session |
| 6 | AI 回复显示 | AI 调 `show_message` | 桌宠气泡显示回复 |
| 7 | session 隔离 | 看 `openclaw sessions tail --session-key <新 session>` | 只有桌宠对话历史，无 webchat 内容 |

---

## 8. 故障排查

| 现象 | 原因 | 解决方案 |
|------|------|---------|
| `openclaw plugins list` 看不到 pet-bubble | npm link 没成功 | 检查 `~/.openclaw/npm/projects/` 下有软链接 |
| `openclaw channels list` 看不到 pet-bubble | channel id 在 openclaw.plugin.json 写错 | 确认是 `pet-bubble`（小写连字符） |
| webhook 返回 404 | 路径不对 | 确认 `webhookPath` 和 curl 路径一致 |
| webhook 返回 500 | 内部异常 | 看 `~/.openclaw/logs/` 下的 gateway 日志 |
| 桌宠发消息，session list 没有变化 | 桥接器没触发 HTTP POST | 看 PowerShell 桥接器日志 `$env:TEMP\pet_to_openclaw_bridge.log` |
| session 创建了但 AI 不响应 | 提示词没告诉 AI 用 show_message | 在 system prompt 加"回复桌宠用 show_message 工具" |
| 桌宠发消息，但桌宠看不到 AI 回复 | AI 没调 show_message，或调了但 GUI 收不到 | 看 MCP 工具调用日志 |
| 多个桥接器进程导致重复触发 | 没杀干净 | 杀所有 pet_to_openclaw_bridge 进程后重启 |
| plugin 安装后 OpenClaw 启动报错 | package.json 配置错 | `openclaw plugins doctor` 看诊断 |
| `Invoke-RestMethod` 失败："远程服务器返回错误: (500)" | OpenClaw gateway 没启动或 webchat 主对话卡死 | 重启 OpenClaw：`openclaw restart` |

---

## 9. 关键设计决策

### 9.1 为什么不直接修改方案 C

方案 C 用 `system event` 注入到 dashboard session，**根因是 OpenClaw dashboard session 不接受外部 turn 触发**——这是 OpenClaw 的设计决策，不是 bug。绕开它的唯一方法是走"独立 session"路径，即 channel 机制。

### 9.2 为什么不用 `openclaw mcp serve`

`openclaw mcp serve` 是把 OpenClaw 自己的 channel **作为 MCP server 暴露**（让外部 MCP 客户端能调），**不是反向**——它不能"接收外部消息触发 OpenClaw session"。

### 9.3 为什么用 `peer: "boss"` 硬编码

桌宠是单用户本地应用（只服务老板一个人），不需要动态 peer discovery。固定 `"boss"` 简单可靠。

### 9.4 为什么 outbound 是 no-op

AI 回复通过 MCP 工具 `desktop-pet__show_message` 直接推回桌宠 GUI（已用方案 C 验证过这条路）。Channel 的 outbound 只返回成功，让 OpenClaw 框架的 reply 流程不报错。

**真正的"消息回环"**：
```
桌宠 → channel inbound → AI turn → MCP show_message → 桌宠
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
       不经过 channel outbound
```

如果将来需要让 channel outbound 也参与（例如发文件、发语音），再扩展 `sendMedia`。

### 9.5 为什么不开 LAN 监听

`webhookHost: "127.0.0.1"` 默认只本机访问。桌宠桥接器也在本机，安全考虑。如果将来要做远程桌宠连接，再加 token 鉴权 + 改 host。

---

## 10. 实施时间表

| 阶段 | 估计 | 备注 |
|------|------|------|
| 准备工作（npm init、链接 SDK） | 5 min | 一次性 |
| 写 12 个文件（按本文件清单） | 60-90 min | 主体工作 |
| npm link + OpenClaw 加载 | 10 min | 验证 plugin 注册 |
| PowerShell 桥接器改 HTTP | 5 min | 改 1 个函数 |
| 联调 + 修 bug | 30-60 min | 反复试 |
| 文档定稿 | 10 min | 复制本文件为 README.md |
| **总计** | **~2-3 小时** | — |

**风险点**：
- `createChatChannelPlugin` 的 `base` 字段是强类型的，部分字段是必填的。漏填会运行时才发现。
- OpenClaw plugin-sdk 的 `registerHttpRoute` 可能在不同版本有变化。实施前**先看飞书 plugin 的 call site**。
- `setup-entry.js` 可以**先不做**，plugin 直接用 config.yaml 启用。

---

## 11. 后续优化（v0.2+）

| 优化 | 价值 | 实施难度 |
|------|------|---------|
| **双向 SSE 推送**：channel outbound 走 SSE 让 AI 主动推送给桌宠 | 桌宠 UI 更丰富的交互 | ★★ |
| **群消息**：支持桌宠 + 多个 peer（家庭成员） | 多人桌宠 | ★ |
| **文件传输**：桌宠发图片、语音 | 多媒体对话 | ★★★ |
| **session 持久化**：桌宠 session 跨重启保留历史 | 长期记忆 | ★★ |
| **统一 webchat + 桌宠 session**：可选让 webchat 和桌宠共享 session | 老板同时用两边的体验 | ★★★ |
| **桌宠原生提示词模板**：为 pet-bubble session 定制 prompt | AI 角色化 | ★ |

---

## 12. 相关资源

| 资源 | 位置 |
|------|------|
| OpenClaw plugin-sdk 源码 | `C:\Users\Ziink\AppData\Roaming\npm\node_modules\openclaw\dist\plugin-sdk\` |
| 飞书 channel plugin 参考实现 | `C:\Users\Ziink\.openclaw\npm\projects\openclaw-feishu-*\node_modules\@openclaw\feishu\dist\` |
| Telegram channel plugin 参考实现 | `C:\Users\Ziink\AppData\Roaming\npm\node_modules\openclaw\dist\extensions\telegram\` |
| 桌宠项目源码 | `D:\code\pet-pc\` |
| 桌宠 MCP 配置指南（v0.1） | `C:\Users\Ziink\.openclaw\workspace\docs\desktop-pet-mcp-setup.md` |
| 桌宠桥接配置指南（方案 C，v0.2） | `C:\Users\Ziink\.openclaw\workspace\docs\desktop-pet-bridge-setup.md` |
| 本文档（方案 v0.3，channel plugin） | `C:\Users\Ziink\.openclaw\workspace\docs\pet-bubble-channel-plugin-implementation.md` |

---

## 13. 决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-06-17 | 方案 C（file hook + system event）失败，session 不触发 | OpenClaw dashboard session 不接受外部 turn |
| 2026-06-17 | 改用方案 2（自定义 channel plugin） | OpenClaw 原生 channel 机制，干净隔离 |
| 2026-06-17 | 用 HTTP webhook 而非 CLI | 性能更好、避免 CLI 阻塞问题 |
| 2026-06-17 | channel id 命名 `pet-bubble`（连字符） | 遵循 OpenClaw channel 命名规范 |
| 2026-06-17 | peer 硬编码 `boss` | 桌宠是单用户本地应用 |
| 2026-06-17 | webhook 只监听 127.0.0.1 | 本机安全，不暴露 LAN |

---

_本文档替代方案 C（系统事件注入）作为桌宠气泡实时接收的**正式长期方案**。方案 C 保留作为 fallback（如果 channel plugin 实施失败）。_
