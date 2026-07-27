import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { Readable } from "node:stream";
import { mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import {
  buildAgentMessage,
  dispatchPetBubbleInbound,
  readJsonBodyWithLimit,
  registerPetBubbleRoutes,
  validateInboundPayload
} from "../plugin-routes.js";

function responseCapture() {
  return {
    statusCode: 0,
    headers: {},
    body: "",
    setHeader(name, value) { this.headers[name] = value; },
    end(value = "") { this.body += value; }
  };
}

function request(method, url, body, headers = {}) {
  const req = Readable.from(body === undefined ? [] : [Buffer.from(JSON.stringify(body))]);
  req.method = method;
  req.url = url;
  req.headers = headers;
  return req;
}

async function call(route, req) {
  const res = responseCapture();
  const handled = await route.handler(req, res);
  return { handled, status: res.statusCode, body: JSON.parse(res.body) };
}

function channelApi({ routedAgent = "healer-cat", sessionKey = "agent:healer-cat:pet-bubble:direct:pet-a" } = {}) {
  const routes = [];
  const captured = {};
  const route = { agentId: routedAgent, accountId: "default", sessionKey };
  const api = {
    config: {
      channels: { "pet-bubble": { sharedSecret: "channel-secret" } },
      agents: { list: [{ id: "healer-cat" }, { id: "other-agent" }] }
    },
    runtime: {
      channel: {
        routing: { resolveAgentRoute(input) { captured.routeInput = input; return route; } },
        inbound: {
          buildContext(input) { captured.contextInput = input; return { built: input }; },
          async dispatchReply(input) { captured.dispatchInput = input; }
        },
        session: {
          resolveStorePath(_path, options) { captured.storeAgent = options.agentId; return "/sessions"; },
          recordInboundSession() {}
        },
        reply: { dispatchReplyWithBufferedBlockDispatcher() {} }
      }
    },
    registerHttpRoute(value) { routes.push(value); },
    logger: { info() {}, warn() {}, error() {} }
  };
  return { api, routes, captured, route };
}

test("reads a buffered body when data starts flowing immediately", async () => {
  class ImmediateRequest extends EventEmitter {
    on(event, listener) {
      super.on(event, listener);
      if (event === "data") {
        this.emit("data", Buffer.from('{"action":"add"}'));
        this.emit("end");
      }
      return this;
    }
  }

  const body = await readJsonBodyWithLimit(new ImmediateRequest(), { timeoutMs: 50 });
  assert.deepEqual(body, { action: "add" });
});

test("rejects oversized and timed-out request bodies", async () => {
  await assert.rejects(
    () => readJsonBodyWithLimit(request("POST", "/", { text: "too large" }), { maxBytes: 2 }),
    (error) => error.status === 413
  );
  await assert.rejects(
    () => readJsonBodyWithLimit(new EventEmitter(), { timeoutMs: 5 }),
    (error) => error.status === 408
  );
});

test("validates and normalizes direct inbound payloads", () => {
  const payload = validateInboundPayload({
    from: " pet-a ",
    agentId: "healer-cat",
    text: " hello ",
    chatType: "direct",
    timestamp: "2026-07-24T12:30:25Z",
    runtime: { replyLength: "short", initiative: "high" }
  });
  assert.equal(payload.from, "pet-a");
  assert.equal(payload.text, "hello");
  assert.equal(payload.replyLength, "short");
  assert.equal(payload.initiative, "high");
  assert.ok(Number.isFinite(payload.timestamp));
});

test("rejects invalid inbound payload fields", () => {
  const cases = [
    [{ from: "../pet", agentId: "healer-cat", text: "hi" }, /invalid from/],
    [{ from: "pet-a", agentId: "bad agent", text: "hi" }, /invalid agentId/],
    [{ from: "pet-a", agentId: "healer-cat", text: " " }, /text/],
    [{ from: "pet-a", agentId: "healer-cat", text: "x".repeat(10001) }, /too long/],
    [{ from: "pet-a", agentId: "healer-cat", text: "hi", chatType: "group" }, /direct/],
    [{ from: "pet-a", agentId: "healer-cat", text: "hi", runtime: { replyLength: "huge" } }, /replyLength/],
    [{ from: "pet-a", agentId: "healer-cat", text: "hi", runtime: { initiative: "always" } }, /initiative/]
  ];
  for (const [body, expected] of cases) assert.throws(() => validateInboundPayload(body), expected);
});

test("builds a compact Agent-visible runtime message", () => {
  const message = buildAgentMessage({
    from: "pet-a", text: "hello", replyLength: "normal", initiative: "low"
  });
  assert.match(message, /pet_id=pet-a/);
  assert.match(message, /exactly one final JSON object/);
  assert.match(message, /duration/);
  assert.match(message, /Do not include pet_id/);
  assert.match(message, /do not call respond_as_pet/);
  assert.match(message, /User message: hello/);
  assert.doesNotMatch(message, /SECURITY NOTICE|Job ID/);
});

test("registers authenticated inbound and memory routes", () => {
  const { api, routes } = channelApi();
  registerPetBubbleRoutes(api);
  assert.deepEqual(routes.map((route) => route.path), ["/pet-bubble-webhook", "/pet-bubble-memory"]);
  assert.ok(routes.every((route) => route.auth === "plugin" && route.match === "exact"));
});

test("inbound route rejects missing shared secret", async () => {
  const { api, routes } = channelApi();
  registerPetBubbleRoutes(api);
  const result = await call(routes[0], request("POST", "/pet-bubble-webhook", {
    from: "pet-a", agentId: "healer-cat", text: "hello"
  }));
  assert.equal(result.status, 403);
});

test("inbound route resolves the binding and dispatches a persistent Channel turn", async () => {
  const { api, routes, captured, route } = channelApi();
  registerPetBubbleRoutes(api);
  const result = await call(routes[0], request("POST", "/pet-bubble-webhook", {
    from: "pet-a",
    agentId: "healer-cat",
    text: "hello",
    runtime: { replyLength: "short", initiative: "low" }
  }, { "x-pet-bubble-secret": "channel-secret" }));
  assert.equal(result.handled, true);
  assert.equal(result.status, 202);
  assert.equal(result.body.accepted, true);
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(captured.routeInput.peer, { kind: "direct", id: "pet-a" });
  assert.equal(captured.contextInput.message.rawBody, "hello");
  assert.match(captured.contextInput.message.bodyForAgent, /exactly one final JSON object/);
  assert.match(captured.contextInput.message.bodyForAgent, /do not call respond_as_pet/);
  assert.equal(captured.contextInput.reply.to, "pet-a");
  assert.equal(captured.dispatchInput.agentId, "healer-cat");
  assert.equal(captured.dispatchInput.routeSessionKey, route.sessionKey);
  assert.equal(captured.storeAgent, "healer-cat");
});

test("inbound route rejects an unknown Agent and a binding mismatch", async () => {
  const first = channelApi();
  registerPetBubbleRoutes(first.api);
  const unknown = await call(first.routes[0], request("POST", "/pet-bubble-webhook", {
    from: "pet-a", agentId: "missing", text: "hello"
  }, { "x-pet-bubble-secret": "channel-secret" }));
  assert.equal(unknown.status, 404);

  const second = channelApi({ routedAgent: "other-agent" });
  registerPetBubbleRoutes(second.api);
  const mismatch = await call(second.routes[0], request("POST", "/pet-bubble-webhook", {
    from: "pet-a", agentId: "healer-cat", text: "hello"
  }, { "x-pet-bubble-secret": "channel-secret" }));
  assert.equal(mismatch.status, 409);
});

test("same peer route reuses its session key and different peers can be isolated", async () => {
  const same = channelApi({ sessionKey: "stable-session" });
  registerPetBubbleRoutes(same.api);
  for (let index = 0; index < 2; index += 1) {
    const result = await call(same.routes[0], request("POST", "/pet-bubble-webhook", {
      from: "pet-a", agentId: "healer-cat", text: `message ${index}`
    }, { "x-pet-bubble-secret": "channel-secret" }));
    assert.equal(result.status, 202);
  }
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(same.captured.dispatchInput.routeSessionKey, "stable-session");

  const other = channelApi({ sessionKey: "other-session" });
  registerPetBubbleRoutes(other.api);
  const result = await call(other.routes[0], request("POST", "/pet-bubble-webhook", {
    from: "pet-b", agentId: "healer-cat", text: "hello"
  }, { "x-pet-bubble-secret": "channel-secret" }));
  assert.equal(result.status, 202);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(other.captured.dispatchInput.routeSessionKey, "other-session");
});

test("dispatch only delivers final replies to the originating pet", async () => {
  const { api, captured, route } = channelApi();
  const originalFetch = globalThis.fetch;
  const callbacks = [];
  globalThis.fetch = async (url, options) => {
    callbacks.push({ url, options });
    return { ok: true, status: 200, text: async () => "" };
  };
  api.runtime.channel.inbound.dispatchReply = async (input) => {
    captured.dispatchInput = input;
    assert.deepEqual(await input.delivery.deliver({ text: "partial" }, { kind: "block" }), {
      visibleReplySent: false
    });
    assert.deepEqual(await input.delivery.deliver({
      text: '{"text":"final reply","animation":"sit","duration":3000}'
    }, { kind: "final" }), {
      visibleReplySent: true
    });
  };
  try {
    await dispatchPetBubbleInbound(api, { autoReply: true }, {
      from: "pet-a",
      agentId: "healer-cat",
      text: "hello",
      replyLength: "normal",
      initiative: "low",
      timestamp: Date.now()
    }, route, "message-1");
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(callbacks.length, 1);
  assert.equal(callbacks[0].url, "http://127.0.0.1:8080/api/pets/pet-a/respond");
  assert.deepEqual(JSON.parse(callbacks[0].options.body), {
    text: "final reply", animation: "sit", duration: 3000
  });
});

test("memory route validates secret and explicit agent list", async (t) => {
  const root = await mkdtemp(path.join(process.cwd(), ".pet-route-test-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const routes = [];
  const api = {
    config: {
      channels: { "pet-bubble": { sharedSecret: "memory-secret" } },
      agents: { list: [{ id: "healer-cat" }] }
    },
    runtime: { agent: { resolveAgentWorkspaceDir(_cfg, agentId) {
      assert.equal(agentId, "healer-cat");
      return root;
    } } },
    registerHttpRoute(route) { routes.push(route); }
  };
  registerPetBubbleRoutes(api);
  const memoryRoute = routes[1];
  const denied = await call(memoryRoute, request("GET", "/pet-bubble-memory?agentId=healer-cat"));
  assert.equal(denied.handled, true);
  assert.equal(denied.status, 403);
  const headers = { "x-pet-bubble-secret": "memory-secret" };
  const added = await call(memoryRoute, request("POST", "/pet-bubble-memory", {
    action: "add", agentId: "healer-cat", text: "likes tea"
  }, headers));
  assert.equal(added.handled, true);
  assert.equal(added.status, 200);
  const listed = await call(memoryRoute, request("GET", "/pet-bubble-memory?agentId=healer-cat", undefined, headers));
  assert.deepEqual(listed.body.memories, [{ id: added.body.id, text: "likes tea" }]);
  const unknown = await call(memoryRoute, request("GET", "/pet-bubble-memory?agentId=other", undefined, headers));
  assert.equal(unknown.status, 404);
});
