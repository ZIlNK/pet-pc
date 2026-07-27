import {
  createChatChannelPlugin,
  createChannelPluginBase
} from "openclaw/plugin-sdk/channel-core";
import { parseAccountConfig } from "./plugin-config.js";
import { sendPetBubbleText } from "./outbound.js";
import { startPetBubbleAccount, stopPetBubbleAccount } from "./channel-lifecycle.js";

const petBubbleBase = createChannelPluginBase({
  id: "pet-bubble",
  meta: {
    label: "Desktop Pet Bubble",
    selectionLabel: "Desktop Pet Bubble (plugin)",
    docsPath: "/channels/pet-bubble",
    blurb: "Local channel for desktop pet chat bubble messages",
    systemImage: "pet"
  },
  config: {
    listAccountIds: () => ["default"],
    resolveAccount: ({ accountId, cfg }) => {
      const channel = cfg?.channels?.["pet-bubble"] ?? {};
      const accountConfig = accountId && accountId !== "default"
        ? channel.accounts?.[accountId]
        : channel;
      return parseAccountConfig({ accountId: accountId ?? "default", ...accountConfig });
    },
    inspectAccount: (cfg) => {
      const channel = cfg?.channels?.["pet-bubble"] ?? {};
      return {
        enabled: true,
        configured: true,
        tokenStatus: channel.sharedSecret ? "available" : "missing"
      };
    }
  }
});

export const petBubbleChannelPlugin = createChatChannelPlugin({
  base: {
    ...petBubbleBase,
    gateway: {
      startAccount: startPetBubbleAccount,
      stopAccount: stopPetBubbleAccount
    }
  },
  outbound: {
    sendText: async (ctx) => {
      ctx.log?.info?.(`[pet-bubble outbound] to=${ctx.to ?? ""}`);
      return sendPetBubbleText(ctx);
    }
  }
});
