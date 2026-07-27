import { timingSafeEqual } from "node:crypto";
import { resolveChannelConfig } from "./plugin-config.js";
import { sendPetBubbleText } from "./outbound.js";
import {
  MemoryStoreError,
  addManagedMemory,
  clearManagedMemories,
  deleteManagedMemory,
  listManagedMemories
} from "./memory-store.js";

const IDENTIFIER_PATTERN = /^[A-Za-z0-9._-]{1,64}$/;
const REPLY_LENGTHS = new Set(["short", "normal", "detailed"]);
const INITIATIVE_LEVELS = new Set(["low", "normal", "high"]);
const MAX_MESSAGE_LENGTH = 10000;

function logPlugin(api, level, message) {
  const logger = api.log ?? api.logger;
  logger?.[level]?.(message);
}

export function readJsonBodyWithLimit(req, { maxBytes = 64 * 1024, timeoutMs = 5000 } = {}) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let received = 0;
    let settled = false;
    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      req.removeListener("data", onData);
      req.removeListener("end", onEnd);
      req.removeListener("error", onError);
      fn(value);
    };
    const timer = setTimeout(() => finish(reject, new MemoryStoreError("request body timeout", 408)), timeoutMs);
    const onData = (chunk) => {
      received += chunk.length;
      if (received > maxBytes) return finish(reject, new MemoryStoreError("request body too large", 413));
      chunks.push(chunk);
    };
    const onEnd = () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      if (!raw) return finish(resolve, {});
      try { finish(resolve, JSON.parse(raw)); }
      catch { finish(reject, new MemoryStoreError("invalid JSON body")); }
    };
    const onError = (error) => finish(reject, error);
    req.on("end", onEnd);
    req.on("error", onError);
    req.on("data", onData);
  });
}

function sendJson(res, status, payload) {
  res.statusCode = status;
  res.setHeader("content-type", "application/json");
  res.end(JSON.stringify(payload));
}

function secretMatches(actual, expected) {
  if (!actual || !expected) return false;
  const actualBuffer = Buffer.from(String(actual));
  const expectedBuffer = Buffer.from(String(expected));
  return actualBuffer.length === expectedBuffer.length && timingSafeEqual(actualBuffer, expectedBuffer);
}

function requireSharedSecret(req, cfg) {
  const account = resolveChannelConfig(cfg);
  if (!account.sharedSecret) {
    throw new MemoryStoreError("pet-bubble shared secret is not configured", 503);
  }
  const supplied = req.headers?.["x-pet-bubble-secret"];
  if (!secretMatches(Array.isArray(supplied) ? supplied[0] : supplied, account.sharedSecret)) {
    throw new MemoryStoreError("invalid pet-bubble shared secret", 403);
  }
  return account;
}

function resolveAgentWorkspace(api, agentId) {
  if (typeof agentId !== "string" || !IDENTIFIER_PATTERN.test(agentId)) {
    throw new MemoryStoreError("invalid agentId");
  }
  const agents = api.config?.agents?.list;
  if (!Array.isArray(agents) || !agents.some((agent) => agent?.id === agentId)) {
    throw new MemoryStoreError("unknown agentId", 404);
  }
  const resolver = api.runtime?.agent?.resolveAgentWorkspaceDir;
  if (typeof resolver !== "function") {
    throw new MemoryStoreError("OpenClaw workspace resolver is unavailable", 500);
  }
  return resolver(api.config, agentId);
}

function requireKnownAgent(api, agentId) {
  const agents = api.config?.agents?.list;
  if (!Array.isArray(agents) || !agents.some((agent) => agent?.id === agentId)) {
    throw new MemoryStoreError("unknown agentId", 404);
  }
}

export function validateInboundPayload(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new MemoryStoreError("JSON body must be an object");
  }
  const from = typeof body.from === "string" ? body.from.trim() : "";
  const agentId = typeof body.agentId === "string" ? body.agentId.trim() : "";
  const text = typeof body.text === "string" ? body.text.trim() : "";
  if (!IDENTIFIER_PATTERN.test(from)) throw new MemoryStoreError("invalid from");
  if (!IDENTIFIER_PATTERN.test(agentId)) throw new MemoryStoreError("invalid agentId");
  if (!text) throw new MemoryStoreError("missing or invalid text");
  if (text.length > MAX_MESSAGE_LENGTH) throw new MemoryStoreError("text is too long");
  if (body.chatType !== undefined && body.chatType !== "direct") {
    throw new MemoryStoreError("chatType must be direct");
  }
  const runtime = body.runtime && typeof body.runtime === "object" && !Array.isArray(body.runtime)
    ? body.runtime
    : {};
  const replyLength = runtime.replyLength ?? "normal";
  const initiative = runtime.initiative ?? "low";
  if (!REPLY_LENGTHS.has(replyLength)) throw new MemoryStoreError("invalid runtime.replyLength");
  if (!INITIATIVE_LEVELS.has(initiative)) throw new MemoryStoreError("invalid runtime.initiative");
  const parsedTimestamp = typeof body.timestamp === "number"
    ? body.timestamp
    : Date.parse(body.timestamp ?? "");
  return {
    from,
    agentId,
    text,
    replyLength,
    initiative,
    timestamp: Number.isFinite(parsedTimestamp) ? parsedTimestamp : Date.now()
  };
}

export function buildAgentMessage(payload) {
  return (
    `[DesktopPet pet_id=${payload.from}; reply_length=${payload.replyLength}; ` +
    `initiative=${payload.initiative}. Return exactly one final JSON object and no Markdown fences: ` +
    `{"text":"reply shown to the user","animation":null,"duration":15000}. ` +
    `Do not include pet_id and do not call respond_as_pet, get_pet_status, or any desktop-pet MCP tool. ` +
    `animation may be null or an animation name; duration must be an integer from 0 to 60000. ` +
    `Keep text within 1000 characters. Memory commands may only modify the ` +
    `desktop-pet-managed-memory block in MEMORY.md.]\n\nUser message: ${payload.text}`
  );
}

function requireChannelRuntime(api) {
  const runtime = api.runtime?.channel;
  if (!runtime?.routing?.resolveAgentRoute || !runtime?.inbound?.buildContext ||
      !runtime?.inbound?.dispatchReply || !runtime?.session?.resolveStorePath ||
      !runtime?.session?.recordInboundSession ||
      !runtime?.reply?.dispatchReplyWithBufferedBlockDispatcher) {
    throw new MemoryStoreError("OpenClaw channel runtime is unavailable", 500);
  }
  return runtime;
}

export async function dispatchPetBubbleInbound(api, account, payload, route, messageId) {
  const runtime = requireChannelRuntime(api);
  const ctxPayload = runtime.inbound.buildContext({
    channel: "pet-bubble",
    accountId: route.accountId,
    messageId,
    timestamp: payload.timestamp,
    from: `pet-bubble:${payload.from}`,
    sender: { id: payload.from, name: payload.from },
    conversation: {
      kind: "direct",
      id: payload.from,
      routePeer: { kind: "direct", id: payload.from }
    },
    route: {
      agentId: route.agentId,
      accountId: route.accountId,
      routeSessionKey: route.sessionKey
    },
    reply: { to: payload.from, originatingTo: payload.from },
    message: {
      rawBody: payload.text,
      body: payload.text,
      bodyForAgent: buildAgentMessage(payload)
    },
    access: {
      commands: { authorized: true },
      mentions: { canDetectMention: false, wasMentioned: false }
    }
  });
  const started = Date.now();
  await runtime.inbound.dispatchReply({
    cfg: api.config,
    channel: "pet-bubble",
    accountId: route.accountId,
    agentId: route.agentId,
    routeSessionKey: route.sessionKey,
    storePath: runtime.session.resolveStorePath(undefined, { agentId: route.agentId }),
    ctxPayload,
    recordInboundSession: runtime.session.recordInboundSession,
    dispatchReplyWithBufferedBlockDispatcher:
      runtime.reply.dispatchReplyWithBufferedBlockDispatcher,
    replyOptions: { disableBlockStreaming: true },
    delivery: {
      deliver: async (replyPayload, info = {}) => {
        const text = typeof replyPayload?.text === "string" ? replyPayload.text.trim() : "";
        if (!account.autoReply || !text || info.kind !== "final") {
          return { visibleReplySent: false };
        }
        const outboundStarted = Date.now();
        const outbound = await sendPetBubbleText({
          cfg: api.config,
          accountId: route.accountId,
          to: payload.from,
          text
        });
        logPlugin(api, "info",
          `[pet-bubble outbound] to=${payload.from} mode=${outbound.deliveryMode} ` +
          `structured=${outbound.structured} elapsedMs=${Date.now() - outboundStarted}`
        );
        return { visibleReplySent: true };
      }
    }
  });
  logPlugin(api, "info",
    `[pet-bubble dispatch] completed pet=${payload.from} elapsedMs=${Date.now() - started}`
  );
}

async function handleInbound(api, req, res) {
  try {
    if (req.method && req.method !== "POST") return sendJson(res, 405, { error: "method not allowed" });
    const account = requireSharedSecret(req, api.config);
    const payload = validateInboundPayload(await readJsonBodyWithLimit(req));
    requireKnownAgent(api, payload.agentId);
    const runtime = requireChannelRuntime(api);
    const peer = { kind: "direct", id: payload.from };
    const route = runtime.routing.resolveAgentRoute({
      cfg: api.config,
      channel: "pet-bubble",
      accountId: account.accountId ?? "default",
      peer
    });
    if (!route || route.agentId !== payload.agentId) {
      throw new MemoryStoreError(
        `agent binding mismatch: pet ${payload.from} routes to ${route?.agentId ?? "none"}`,
        409
      );
    }
    const messageId = `pet-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    logPlugin(api, "info",
      `[pet-bubble route] pet=${payload.from} agent=${route.agentId} sessionKey=${route.sessionKey}`
    );
    sendJson(res, 202, { accepted: true, messageId });
    logPlugin(api, "info",
      `[pet-bubble inbound] accepted pet=${payload.from} agent=${route.agentId} messageId=${messageId}`
    );
    void dispatchPetBubbleInbound(api, account, payload, route, messageId).catch((error) => {
      logPlugin(api, "error",
        `[pet-bubble dispatch] failed pet=${payload.from} agent=${route.agentId}: ${error?.message ?? error}`
      );
    });
  } catch (error) {
    logPlugin(api, "warn", `[pet-bubble inbound] rejected: ${error?.message ?? error}`);
    sendJson(res, error?.status ?? 400, { error: String(error?.message ?? error) });
  }
}

async function handleMemory(api, req, res) {
  try {
    requireSharedSecret(req, api.config);
    if (req.method === "GET") {
      const url = new URL(req.url, "http://127.0.0.1");
      const agentId = url.searchParams.get("agentId") ?? "";
      const workspace = resolveAgentWorkspace(api, agentId);
      const memories = await listManagedMemories(workspace);
      return sendJson(res, 200, { agentId, memories });
    }
    if (req.method !== "POST") return sendJson(res, 405, { error: "method not allowed" });
    const body = await readJsonBodyWithLimit(req);
    const workspace = resolveAgentWorkspace(api, body.agentId);
    let result;
    if (body.action === "add") result = await addManagedMemory(workspace, body.text);
    else if (body.action === "delete") result = await deleteManagedMemory(workspace, body.memoryId);
    else if (body.action === "clear") {
      if (body.confirm !== true) throw new MemoryStoreError("clear requires confirm=true");
      result = await clearManagedMemories(workspace);
    } else throw new MemoryStoreError("unsupported memory action");
    return sendJson(res, 200, { agentId: body.agentId, ...result });
  } catch (error) {
    sendJson(res, error?.status ?? 500, { error: String(error?.message ?? error) });
  }
}

export function registerPetBubbleRoutes(api) {
  const account = resolveChannelConfig(api.config);
  api.registerHttpRoute({
    path: account.webhookPath,
    auth: "plugin",
    match: "exact",
    replaceExisting: true,
    handler: async (req, res) => {
      await handleInbound(api, req, res);
      return true;
    }
  });
  api.registerHttpRoute({
    path: "/pet-bubble-memory",
    auth: "plugin",
    match: "exact",
    replaceExisting: true,
    handler: async (req, res) => {
      await handleMemory(api, req, res);
      return true;
    }
  });
  logPlugin(api, "info", `pet-bubble routes registered at ${account.webhookPath} and /pet-bubble-memory`);
}
