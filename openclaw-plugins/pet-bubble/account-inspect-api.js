export const inspectPetBubbleReadOnlyAccount = {
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
