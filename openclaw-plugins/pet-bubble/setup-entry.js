import { defineSetupPluginEntry } from "openclaw/plugin-sdk/channel-core";

// [DIAGNOSTIC 2026-06-24] Confirm setup-entry module is evaluated.
console.log("[PET_BUBBLE_SETUP_ENTRY_LOADED]");

// `defineSetupPluginEntry` returns just `{ plugin }` with no runtime wiring.
// OpenClaw loads this instead of the full entry when a channel is disabled,
// unconfigured, or when deferred loading is enabled (see docs:
// /plugins/sdk-entrypoints#definesetuppluginentry).
//
// We accept the plugin object but only return the bare metadata so read-only
// command paths (status / channels list / SecretRef scans) can surface this
// plugin without importing the heavy channel-main runtime module.
export default defineSetupPluginEntry({
  id: "pet-bubble",
  label: "Desktop Pet Bubble",
  blurb: "Local channel for Desktop Pet GUI chat bubble messages.",
  setupWizard: async ({ prompt }) => {
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
