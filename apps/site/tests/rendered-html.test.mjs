import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the PureGamma commercial preview", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<html lang="zh-CN">/i);
  assert.match(html, /<title>PureGamma AI — 研究、组合与受控执行<\/title>/i);
  assert.match(html, /Research Agent/);
  assert.match(html, /Portfolio Intelligence/);
  assert.match(html, /EXECUTION<\/small><strong>PAPER/);
  assert.match(html, /申请首批访问/);
  assert.match(html, /非投资建议，不承诺收益/);
  assert.match(html, /mailto:hello@puregamma\.ai/);
  assert.doesNotMatch(html, /Codex is working|Your site is taking shape|react-loading-skeleton/i);
});

test("keeps launch claims and metadata aligned with the current product", async () => {
  const [page, layout, packageJson] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(page, /Nautilus paper mode/);
  assert.match(page, /Stripe production keys", "PENDING/);
  assert.match(page, /实盘、转账与提现能力默认关闭/);
  assert.match(page, /非投资建议，不承诺收益/);
  assert.doesNotMatch(page, /guaranteed return|保证收益|codex-preview|SkeletonPreview/i);
  assert.match(layout, /generateMetadata/);
  assert.match(layout, /summary_large_image/);
  assert.match(packageJson, /"test": "npm run build && node --test tests\/rendered-html\.test\.mjs"/);
});
