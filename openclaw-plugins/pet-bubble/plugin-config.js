export const DEFAULT_WEBHOOK_PATH = "/pet-bubble-webhook";
export const DEFAULT_DESKTOP_API_BASE = "http://127.0.0.1:8080/api";

export function normalizePluginHttpPath(rawPath) {
  if (typeof rawPath !== "string" || rawPath.trim().length === 0) {
    return DEFAULT_WEBHOOK_PATH;
  }
  const trimmed = rawPath.trim();
  return trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
}

export function parseAccountConfig(input) {
  const src = input && typeof input === "object" ? input : {};
  const webhookPath = normalizePluginHttpPath(src.webhookPath);
  const webhookHost =
    typeof src.webhookHost === "string" && src.webhookHost.trim()
      ? src.webhookHost.trim()
      : "127.0.0.1";
  const webhookPort =
    Number.isInteger(src.webhookPort) && src.webhookPort >= 0 && src.webhookPort <= 65535
      ? src.webhookPort
      : 0;
  const desktopApiBase =
    typeof src.desktopApiBase === "string" && src.desktopApiBase.trim()
      ? src.desktopApiBase.trim().replace(/\/+$/, "")
      : DEFAULT_DESKTOP_API_BASE;
  const sharedSecret = typeof src.sharedSecret === "string" ? src.sharedSecret : "";
  const out = {
    webhookPath,
    webhookHost,
    webhookPort,
    autoReply: src.autoReply !== false,
    desktopApiBase,
    sharedSecret
  };
  if (typeof src.accountId === "string" && src.accountId) out.accountId = src.accountId;
  if (typeof src.name === "string" && src.name) out.name = src.name;
  return out;
}

export function resolveChannelConfig(cfg, accountId = "default") {
  const channel = cfg?.channels?.["pet-bubble"] ?? {};
  const accountConfig = accountId && accountId !== "default"
    ? channel.accounts?.[accountId]
    : channel;
  return parseAccountConfig({ accountId, ...accountConfig });
}
