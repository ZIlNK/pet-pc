export function waitUntilAbort(abortSignal, onAbort) {
  if (!abortSignal || abortSignal.aborted) {
    onAbort?.();
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    const finish = () => {
      abortSignal.removeEventListener("abort", finish);
      onAbort?.();
      resolve();
    };
    abortSignal.addEventListener("abort", finish, { once: true });
  });
}

export async function startPetBubbleAccount(ctx) {
  ctx.log?.info?.(`[pet-bubble:${ctx.accountId}] channel ready`);
  return waitUntilAbort(ctx.abortSignal, () => {
    ctx.log?.info?.(`[pet-bubble:${ctx.accountId}] channel stopped`);
  });
}

export async function stopPetBubbleAccount(ctx) {
  ctx.log?.info?.(`[pet-bubble:${ctx.accountId}] stop requested`);
}
