import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeHtml } from "./htmlNormalize.js";

test("strips script/style/comment/canonical/og:url, collapses whitespace", () => {
  const html = `<html><head>
    <link rel="canonical" href="https://x.tld/p?color=red">
    <meta property="og:url" content="https://x.tld/p?color=red">
    <style>.a{color:red}</style></head>
    <body><!-- built 12:03:59 --><h1>Perceuse</h1>
    <script>window.__NONCE__="abc123"</script></body></html>`;
  const out = normalizeHtml(html);
  assert.ok(out.includes("Perceuse"));
  assert.ok(!out.includes("canonical"));
  assert.ok(!out.includes("og:url"));
  assert.ok(!out.includes("__NONCE__"));
  assert.ok(!out.includes("color:red"));
  assert.ok(!out.includes("<!--"));
});

test("same body, different script nonce → equal", () => {
  const a = `<body><h1>Hi</h1><script>var t=1699999999</script></body>`;
  const b = `<body><h1>Hi</h1><script>var t=1700000042</script></body>`;
  assert.equal(normalizeHtml(a), normalizeHtml(b));
});

test("different body text → different", () => {
  assert.notEqual(normalizeHtml("<body>A</body>"), normalizeHtml("<body>B</body>"));
});

test("empty/undefined → empty string", () => {
  assert.equal(normalizeHtml(""), "");
  assert.equal(normalizeHtml(undefined as unknown as string), "");
});
