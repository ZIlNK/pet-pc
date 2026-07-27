import { defineSetupPluginEntry } from "openclaw/plugin-sdk/channel-core";

export default defineSetupPluginEntry({
  id: "pet-bubble",
  label: "Desktop Pet Bubble",
  blurb: "Local channel for Desktop Pet GUI chat bubble messages.",
  setupWizard: async ({ prompt }) => {
    const webhookPath = await prompt.text({
      message: "Webhook path",
      defaultValue: "/pet-bubble-webhook"
    });
    const desktopApiBase = await prompt.text({
      message: "Desktop Pet API base URL",
      defaultValue: "http://127.0.0.1:8080/api"
    });
    const sharedSecret = await prompt.text({
      message: "Desktop Pet shared secret",
      defaultValue: ""
    });
    return {
      channels: {
        "pet-bubble": {
          webhookPath,
          desktopApiBase,
          sharedSecret,
          autoReply: true
        }
      }
    };
  }
});
