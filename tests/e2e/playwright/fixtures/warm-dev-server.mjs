// Pre-compile the error pages of a fresh `next dev` server before tests run.
//
// The first time the dev proxy answers an unstubbed call with a 500, `next dev`
// compiles the pages-router `/_error` (a second client compiler) in the middle
// of a test, and the page being loaded can wait on that compile long enough to
// never hydrate or never reach `load`. Requesting the error paths up front
// moves that compile before the first test.
//
// `--all` also compiles every page route. That is only for machines with
// memory to spare: on an 8 GB host it pushed the dev server past 3 GB.
// Usage: node warm-dev-server.mjs http://127.0.0.1:3000 [--all]
import { readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const base = (process.argv[2] || "http://127.0.0.1:3000").replace(/\/+$/, "");
const appDir = join(dirname(fileURLToPath(import.meta.url)), "../../../../apps/web/app/[locale]");

/** Static page routes under app/[locale] (dynamic segments get a placeholder). */
function routes(dir, prefix = "") {
  const found = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (!statSync(full).isDirectory()) {
      if (name === "page.tsx") found.push(prefix || "/");
      continue;
    }
    const segment = name.startsWith("(") ? "" : name.startsWith("[") ? "/warmup" : `/${name}`;
    found.push(...routes(full, `${prefix}${segment}`));
  }
  return found;
}

const paths = process.argv.includes("--all") ? [...new Set(routes(appDir))].sort() : [];
// The error page (pages router) and the dev proxy's failure path.
const extra = ["/__dev-api/warmup", "/en/__warmup-not-found"];
let failed = 0;
for (const path of [...paths.map((route) => `/en${route === "/" ? "" : route}`), ...extra]) {
  const started = Date.now();
  try {
    const response = await fetch(`${base}${path}`, { redirect: "manual", signal: AbortSignal.timeout(180_000) });
    await response.arrayBuffer();
    process.stdout.write(`${response.status} ${path} ${Date.now() - started}ms\n`);
  } catch (error) {
    failed += 1;
    process.stdout.write(`ERR ${path} ${error}\n`);
  }
}
process.exit(failed > (paths.length + extra.length) / 2 ? 1 : 0);
