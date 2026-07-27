import test from "node:test";
import assert from "node:assert/strict";
import { parsePetBubbleReply, sendPetBubbleText } from "../outbound.js";

function config() {
  return { channels: { "pet-bubble": {
    desktopApiBase: "http://127.0.0.1:8080/api/",
    sharedSecret: "reply-secret"
  } } };
}

test("parses a structured final reply", () => {
  assert.deepEqual(parsePetBubbleReply(JSON.stringify({
    text: "hello",
    animation: "sit",
    duration: 3000,
    pet_id: "ignored"
  })), {
    text: "hello",
    animation: "sit",
    duration: 3000,
    structured: true
  });
});

test("accepts fenced JSON and normalizes optional fields", () => {
  assert.deepEqual(parsePetBubbleReply('```json\n{"text":" hello ","animation":" ","duration":0}\n```'), {
    text: "hello",
    animation: null,
    duration: 0,
    structured: true
  });
});

test("falls back to plain text for invalid structured replies", () => {
  assert.deepEqual(parsePetBubbleReply('{"text":"hello","duration":-1}'), {
    text: '{"text":"hello","duration":-1}',
    animation: null,
    duration: 15000,
    structured: false
  });
  assert.deepEqual(parsePetBubbleReply("plain reply"), {
    text: "plain reply",
    animation: null,
    duration: 15000,
    structured: false
  });
});

test("sendText posts structured replies directly to the target pet respond endpoint", async () => {
  let captured;
  const fetchImpl = async (url, options) => {
    captured = { url, options };
    return { ok: true, status: 200, text: async () => "" };
  };
  const result = await sendPetBubbleText({
    cfg: config(),
    accountId: "default",
    to: "pet 123",
    text: '{"text":"hello","animation":"sit","duration":3000}'
  }, fetchImpl);
  assert.equal(captured.url, "http://127.0.0.1:8080/api/pets/pet%20123/respond");
  assert.equal(captured.options.headers["X-HTTP-Channel-Secret"], "reply-secret");
  assert.deepEqual(JSON.parse(captured.options.body), {
    text: "hello",
    animation: "sit",
    duration: 3000
  });
  assert.equal(result.deliveryMode, "respond");
  assert.equal(result.structured, true);
});

test("sendText delivers plain final text without MCP", async () => {
  let captured;
  const result = await sendPetBubbleText({
    cfg: config(),
    to: "pet123",
    text: "plain reply"
  }, async (url, options) => {
    captured = { url, options };
    return { ok: true, status: 200, text: async () => "" };
  });
  assert.equal(captured.url, "http://127.0.0.1:8080/api/pets/pet123/respond");
  assert.deepEqual(JSON.parse(captured.options.body), {
    text: "plain reply",
    animation: null,
    duration: 15000
  });
  assert.equal(result.structured, false);
});

test("sendText keeps the legacy callback only for oversized plain text", async () => {
  let captured;
  const text = "x".repeat(1001);
  const result = await sendPetBubbleText({ cfg: config(), to: "pet123", text }, async (url, options) => {
    captured = { url, options };
    return { ok: true, status: 200, text: async () => "" };
  });
  assert.equal(captured.url, "http://127.0.0.1:8080/api/openclaw/reply");
  assert.equal(JSON.parse(captured.options.body).text, text);
  assert.equal(result.deliveryMode, "legacy_text");
});

test("sendText rejects empty targets and non-success callbacks", async () => {
  await assert.rejects(() => sendPetBubbleText({ cfg: {}, to: "", text: "hello" }), /target/);
  await assert.rejects(
    () => sendPetBubbleText({ cfg: {}, to: "pet", text: "hello" }, async () => ({
      ok: false,
      status: 404,
      text: async () => "missing pet"
    })),
    /404.*missing pet/
  );
});
