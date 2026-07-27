import assert from "node:assert/strict";
import test from "node:test";

import {
  startPetBubbleAccount,
  waitUntilAbort
} from "../channel-lifecycle.js";

test("waitUntilAbort remains pending until the signal aborts", async () => {
  const controller = new AbortController();
  let settled = false;
  const pending = waitUntilAbort(controller.signal).then(() => {
    settled = true;
  });

  await Promise.resolve();
  assert.equal(settled, false);

  controller.abort();
  await pending;
  assert.equal(settled, true);
});

test("startPetBubbleAccount reports ready and stops on abort", async () => {
  const controller = new AbortController();
  const messages = [];
  const pending = startPetBubbleAccount({
    accountId: "default",
    abortSignal: controller.signal,
    log: { info: (message) => messages.push(message) }
  });

  await Promise.resolve();
  assert.deepEqual(messages, ["[pet-bubble:default] channel ready"]);

  controller.abort();
  await pending;
  assert.deepEqual(messages, [
    "[pet-bubble:default] channel ready",
    "[pet-bubble:default] channel stopped"
  ]);
});
