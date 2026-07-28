import { describe, expect, it, vi } from "vitest";

vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ connected: true, api_running: true }), { status: 200, headers: { "Content-Type": "application/json" } })));

import { api } from "./api";

describe("control-center API client", () => {
  it("uses the loopback control-center health endpoint", async () => {
    await expect(api.health()).resolves.toEqual({ connected: true, api_running: true });
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("127.0.0.1"), undefined);
  });
});
