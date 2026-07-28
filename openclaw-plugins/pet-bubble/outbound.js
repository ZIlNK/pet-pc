import { resolveChannelConfig } from "./plugin-config.js";

const DEFAULT_DURATION = 10000;
const MAX_TEXT_LENGTH = 1000;

function unwrapJsonFence(text) {
  const match = text.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  return match ? match[1].trim() : text;
}

export function parsePetBubbleReply(rawText) {
  const raw = typeof rawText === "string" ? rawText.trim() : "";
  if (!raw) throw new Error("desktop pet reply text is empty");

  const candidate = unwrapJsonFence(raw);
  try {
    const parsed = JSON.parse(candidate);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("reply JSON must be an object");
    }
    const text = typeof parsed.text === "string" ? parsed.text.trim() : "";
    const duration = parsed.duration ?? DEFAULT_DURATION;
    const animation = parsed.animation == null
      ? null
      : typeof parsed.animation === "string"
        ? parsed.animation.trim() || null
        : undefined;
    if (!text || text.length > MAX_TEXT_LENGTH || !Number.isInteger(duration) ||
        duration < 0 || duration > 60000 || animation === undefined) {
      throw new Error("invalid structured desktop pet reply");
    }
    return { text, animation, duration, structured: true };
  } catch {
    return {
      text: raw,
      animation: null,
      duration: DEFAULT_DURATION,
      structured: false
    };
  }
}

async function postDesktopPet(fetchImpl, url, headers, body) {
  const response = await fetchImpl(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(5000)
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(
      `desktop pet reply callback failed (${response.status})${detail ? `: ${detail}` : ""}`
    );
  }
}

export async function sendPetBubbleText(ctx, fetchImpl = globalThis.fetch) {
  if (typeof fetchImpl !== "function") throw new Error("fetch is unavailable");
  const account = resolveChannelConfig(ctx.cfg, ctx.accountId ?? "default");
  const to = typeof ctx.to === "string" ? ctx.to.trim() : "";
  if (!to) throw new Error("desktop pet target is empty");

  const reply = parsePetBubbleReply(ctx.text);
  const headers = { "content-type": "application/json" };
  if (account.sharedSecret) headers["X-HTTP-Channel-Secret"] = account.sharedSecret;

  if (reply.text.length <= MAX_TEXT_LENGTH) {
    await postDesktopPet(
      fetchImpl,
      `${account.desktopApiBase}/pets/${encodeURIComponent(to)}/respond`,
      headers,
      {
        text: reply.text,
        animation: reply.animation,
        duration: reply.duration
      }
    );
    return {
      ok: true,
      channel: "pet-bubble",
      messageId: `out-${Date.now()}`,
      deliveryMode: "respond",
      structured: reply.structured
    };
  }

  await postDesktopPet(fetchImpl, `${account.desktopApiBase}/openclaw/reply`, headers, {
    channel: "pet-bubble",
    accountId: account.accountId ?? "default",
    to,
    text: reply.text,
    timestamp: new Date().toISOString()
  });
  return {
    ok: true,
    channel: "pet-bubble",
    messageId: `out-${Date.now()}`,
    deliveryMode: "legacy_text",
    structured: false
  };
}
