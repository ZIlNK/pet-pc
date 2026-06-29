import {
  createChatChannelPlugin,
  createChannelPluginBase
} from "openclaw/plugin-sdk/channel-core";

// ── 0. Small helpers (no internal SDK subpaths) ───────────
//
// We intentionally do not import from `openclaw/plugin-sdk/webhook-ingress`
// or `openclaw/plugin-sdk/http-path`. Those subpaths are internal-only — they
// exist in the OpenClaw monorepo dev workspace but are not exposed via
// `openclaw/package.json#exports`, so they fail to resolve when the plugin is
// loaded from a `npm link`'d install path. Re-implement the minimal behavior
// we need on top of Node built-ins.

function normalizePluginHttpPath(rawPath) {
  const fallback = "/pet-bubble-webhook";
  if (typeof rawPath !== "string" || rawPath.length === 0) return fallback;
  const trimmed = rawPath.trim();
  if (trimmed.length === 0) return fallback;
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

function readJsonBodyWithLimit(req, res, { maxBytes = 64 * 1024, timeoutMs = 5000 } = {}) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let received = 0;
    let settled = false;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try { req.removeListener("data", onData); req.removeListener("end", onEnd); req.removeListener("error", onError); } catch {}
      fn(value);
    };
    const timer = setTimeout(() => finish(reject, new Error("request body timeout")), timeoutMs);
    const onData = (chunk) => {
      received += chunk.length;
      if (received > maxBytes) {
        if (res && !res.headersSent) {
          res.statusCode = 413;
          res.setHeader("content-type", "application/json");
        }
        return finish(reject, new Error(`request body exceeds ${maxBytes} bytes`));
      }
      chunks.push(chunk);
    };
    const onEnd = () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      if (!raw) return finish(resolve, {});
      try {
        finish(resolve, JSON.parse(raw));
      } catch (err) {
        finish(reject, new Error(`invalid JSON body: ${err.message}`));
      }
    };
    const onError = (err) => finish(reject, err);
    req.on("data", onData);
    req.on("end", onEnd);
    req.on("error", onError);
  });
}

// ── 1. Account config parser (plain JS, no zod) ──────────
//
// We intentionally avoid zod here — adding a runtime dependency just for two
// defaults (`webhookPath`, `autoReply`) is not worth the install footprint.
// `parseAccountConfig` mirrors the same shape and defaults the previous zod
// schema produced.
function parseAccountConfig(input) {
  const src = input && typeof input === "object" ? input : {};
  const webhookPath =
    typeof src.webhookPath === "string" && src.webhookPath.length > 0
      ? src.webhookPath
      : "/pet-bubble-webhook";
  const webhookHost =
    typeof src.webhookHost === "string" && src.webhookHost.length > 0
      ? src.webhookHost
      : "127.0.0.1";
  const webhookPortRaw = src.webhookPort;
  const webhookPort =
    Number.isInteger(webhookPortRaw) && webhookPortRaw >= 0 && webhookPortRaw <= 65535
      ? webhookPortRaw
      : 0;
  const autoReply = src.autoReply === false ? false : true;
  const accountId =
    typeof src.accountId === "string" && src.accountId.length > 0
      ? src.accountId
      : undefined;
  const name =
    typeof src.name === "string" && src.name.length > 0 ? src.name : undefined;
  const out = { webhookPath, webhookHost, webhookPort, autoReply };
  if (accountId !== undefined) out.accountId = accountId;
  if (name !== undefined) out.name = name;
  return out;
}

// ── 2. Pet Bubble channel plugin ────────────────────────
const petBubbleBase = createChannelPluginBase({
  id: "pet-bubble",
  meta: {
    label: "Desktop Pet Bubble",
    blurb: "Local channel for desktop pet chat bubble messages",
    systemImage: "pet"
  },

  // Config helpers exposed on `plugin.config` — the registry
  // (`registry-BVye-IRt.js`) requires `listAccountIds` and `resolveAccount`
  // to live here as functions.
  config: {
    // No multi-account support for the desktop pet bubble channel; we
    // always surface a single implicit "default" account.
    listAccountIds: () => ["default"],
    resolveAccount: ({ accountId, cfg }) => {
      const ch = cfg?.channels?.["pet-bubble"] ?? {};
      const accountCfg = accountId && accountId !== "default"
        ? ch.accounts?.[accountId]
        : ch;
      return parseAccountConfig({
        accountId: accountId ?? "default",
        ...accountCfg
      });
    },
    inspectAccount: (cfg) => {
      const ch = cfg?.channels?.["pet-bubble"] ?? {};
      return {
        enabled: true,
        configured: Boolean(ch.webhookPath ?? true),
        tokenStatus: "unavailable"
      };
    }
  },

  // Core: register HTTP webhook route ────────────────────
  setup: async ({ account, api, runtime }) => {
    // [DIAGNOSTIC 2026-06-24] Verify setup hook is actually invoked.
    console.log("[PET_BUBBLE_SETUP_CALLED] webhookPath=" + (account?.webhookPath ?? "<undefined>"));
    api.log?.info?.("[PET_BUBBLE_SETUP_CALLED] webhookPath=" + (account?.webhookPath ?? "<undefined>"));
    const path = normalizePluginHttpPath(account.webhookPath);

    console.log("[PET_BUBBLE_BEFORE_REGISTER] path=" + path + " auth=plugin match=exact");
    api.registerHttpRoute({
      path,
      auth: "plugin",
      match: "exact",
      handler: async (req, res) => {
        console.log("[PET_BUBBLE_ROUTE_HIT] path=" + req.url);
        try {
          // 1. Parse HTTP body (limit 64 KB, force JSON)
          const body = await readJsonBodyWithLimit(req, res, {
            maxBytes: 64 * 1024,
            timeoutMs: 5000
          });

          // 2. Validate required fields
          if (!body.text || typeof body.text !== "string") {
            res.statusCode = 400;
            res.end(JSON.stringify({ error: "Missing or invalid 'text' field" }));
            return;
          }

          const peer = body.peer || "default";
          const timestamp = body.timestamp || new Date().toISOString();

          // 3. Build inbound envelope (OpenClaw standard format)
          const envelope = {
            channel: "pet-bubble",
            accountId: account.accountId ?? "default",
            chatType: "direct",
            peer: { kind: "direct", id: peer },
            from: peer,
            to: "pet-bubble-bot",
            messageId: `pet-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            timestamp,
            text: body.text,
            metadata: body.metadata ?? {}
          };

          // 4. Route into OpenClaw
          runtime.channel.dispatch?.(envelope);

          // 5. Return 200 OK
          res.statusCode = 200;
          res.end(JSON.stringify({ ok: true, messageId: envelope.messageId }));
        } catch (err) {
          runtime.log?.error("pet-bubble webhook error", err);
          if (!res.headersSent) {
            res.statusCode = 400;
          }
          res.end(JSON.stringify({ error: String(err.message ?? err) }));
        }
      }
    });

    api.log?.info?.(`pet-bubble webhook registered at ${path}`);

    // [C1f DIAGNOSTIC 2026-06-26] Probe AFTER registerHttpRoute returns.
    // Per OpenClaw dist/registry-BVye-IRt.js:3131-3139: when `auth` is
    // missing/invalid, registerHttpRoute silently returns (pushes a
    // diagnostic, but does not throw). Without an after-probe we cannot
    // tell whether the call returned normally (route accepted) or
    // returned early (route rejected).
    console.log("[PET_BUBBLE_AFTER_REGISTER] path=" + path + " (if no further logs from setup, check whether route hit /pet-bubble-webhook via curl)");
    api.log?.info?.("[PET_BUBBLE_AFTER_REGISTER] path=" + path);

    // [C1f DIAGNOSTIC 2026-06-26] Probe setup function END.
    // If this log fires, setup ran to completion without throwing.
    // If it does NOT fire, setup threw between BEFORE_REGISTER and here.
    console.log("[PET_BUBBLE_SETUP_END] account=" + (account?.accountId ?? "<undefined>"));
    api.log?.info?.("[PET_BUBBLE_SETUP_END] account=" + (account?.accountId ?? "<undefined>"));
  }
});

export const petBubbleChannelPlugin = createChatChannelPlugin({
  base: petBubbleBase,

  // Outbound: send AI replies back to the desktop pet ──────────────────────
  // The AI uses MCP tool `show_message` to render its reply in the pet GUI.
  // Here we only return success so OpenClaw knows the send was accepted.
  outbound: {
    sendText: async (ctx) => {
      ctx.log?.info?.(`[pet-bubble outbound] ${ctx.text}`);
      return { ok: true, channel: "pet-bubble", messageId: `out-${Date.now()}` };
    }
  }
});