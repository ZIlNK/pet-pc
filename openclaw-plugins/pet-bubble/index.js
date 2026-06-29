import { defineChannelPluginEntry } from "openclaw/plugin-sdk/channel-core";
import petBubbleChannelPlugin from "./channel-plugin-api.js";
import { setPetBubbleRuntime } from "./runtime-api.js";

// `defineChannelPluginEntry` is the standard, public-facing entry point for
// external channel plugins (see OpenClaw docs: /plugins/sdk-entrypoints).
// It wraps `definePluginEntry` and handles the cli-metadata / discovery /
// setup-only / setup-runtime / full registration-mode split automatically,
// including `api.registerChannel({ plugin })`.
export default defineChannelPluginEntry({
  id: "pet-bubble",
  name: "Desktop Pet Bubble",
  description:
    "Local channel that receives desktop pet chat bubble messages via HTTP webhook",
  plugin: petBubbleChannelPlugin,
  setRuntime: setPetBubbleRuntime,
  registerFull(api) {
    // [DIAGNOSTIC 2026-06-24] Verify which registration mode is active.
    api.log?.info?.("[PET_BUBBLE_REGISTER_FULL_CALLED] registrationMode=" + api.registrationMode);
    console.log("[PET_BUBBLE_REGISTER_FULL_CALLED] registrationMode=" + api.registrationMode);

    // [B1 FIX 2026-06-26] Move `api.registerHttpRoute(...)` from
    // `channel-main.js#setup` (which never runs in `full` registrationMode;
    // see docs/pet-bubble-fix-2026-06-25.md section 6.14.2) into
    // `registerFull(api)` (which DOES run in full mode).
    //
    // Handler is intentionally minimal for this round — its job is only to
    // prove the HTTP route is actually mounted on gateway 18789. The full
    // envelope dispatch (readJsonBodyWithLimit, channel-main handler) will
    // be ported in the next pass after this round confirms 200 via curl.
    console.log("[PET_BUBBLE_BEFORE_REGISTER] path=/pet-bubble-webhook auth=plugin match=exact");
    api.log?.info?.("[PET_BUBBLE_BEFORE_REGISTER] path=/pet-bubble-webhook auth=plugin match=exact");
    api.registerHttpRoute({
      path: "/pet-bubble-webhook",
      auth: "plugin",
      match: "exact",
      handler: async (req, res) => {
        console.log("[PET_BUBBLE_ROUTE_HIT] path=" + req.url);
        // Minimal ack — envelope dispatch comes next pass.
        res.statusCode = 200;
        res.setHeader("content-type", "application/json");
        res.end(JSON.stringify({ ok: true, note: "B1 minimal handler — envelope dispatch comes next pass" }));
      }
    });
    console.log("[PET_BUBBLE_AFTER_REGISTER] path=/pet-bubble-webhook (if curl returns 200, route is mounted)");
    api.log?.info?.("[PET_BUBBLE_AFTER_REGISTER] path=/pet-bubble-webhook");

    console.log("[PET_BUBBLE_REGISTER_FULL_END] (full activation complete)");
    api.log?.info?.("[PET_BUBBLE_REGISTER_FULL_END] (full activation complete)");
  }
});
