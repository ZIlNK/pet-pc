import { defineChannelPluginEntry } from "openclaw/plugin-sdk/channel-core";
import petBubbleChannelPlugin from "./channel-plugin-api.js";
import { registerPetBubbleRoutes } from "./plugin-routes.js";
import { setPetBubbleRuntime } from "./runtime-api.js";

export default defineChannelPluginEntry({
  id: "pet-bubble",
  name: "Desktop Pet Bubble",
  description:
    "Local channel that receives desktop pet messages and returns Agent replies to the originating pet",
  plugin: petBubbleChannelPlugin,
  setRuntime: setPetBubbleRuntime,
  registerFull(api) {
    registerPetBubbleRoutes(api);
  }
});
