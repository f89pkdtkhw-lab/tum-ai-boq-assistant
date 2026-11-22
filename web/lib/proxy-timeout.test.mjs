// Run: node --test web/lib/proxy-timeout.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import nextConfig from "../next.config.mjs";

test("the /backend rewrite proxy waits at least the Grok Bot timeout plus a buffer", () => {
  const ms = nextConfig.experimental?.proxyTimeout;
  assert.equal(typeof ms, "number");
  assert.ok(ms >= 960_000, `expected proxyTimeout >= 960000 ms, got ${ms}`);
});
