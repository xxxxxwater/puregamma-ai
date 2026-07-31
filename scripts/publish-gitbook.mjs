/**
 * Publish docs/gitbook/** to a GitBook space via the GitBook API.
 *
 * Usage:
 *   GITBOOK_TOKEN=gb_api_xxx node scripts/publish-gitbook.mjs [--space <spaceId>]
 *
 * Without --space a new space titled "PureGamma AI 使用手册" is created in the
 * puregamma.ai organization. Prints the space id and published URL when done.
 * The token is read from the environment only and never written to disk.
 */

import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "docs", "gitbook");
const ORG_ID = "wtgESGImeSsLv3qH6Mqw";
const API = "https://api.gitbook.com/v1";
const TOKEN = process.env.GITBOOK_TOKEN;
if (!TOKEN) {
  console.error("GITBOOK_TOKEN env var is required");
  process.exit(1);
}

// Page tree: [title, emoji, file, children[]]
const TREE = [
  { title: "快速上手", emoji: "🚀", file: "getting-started.md" },
  {
    title: "功能指南",
    emoji: "📖",
    file: "features/README.md",
    children: [
      { title: "仪表盘与每日简报", emoji: "📊", file: "features/dashboard-reports.md" },
      { title: "Agent 对话", emoji: "🤖", file: "features/agent-chat.md" },
      { title: "私人秘书(语音)", emoji: "🎙️", file: "features/secretary-voice.md" },
      { title: "期权研究", emoji: "📈", file: "features/options-research.md" },
      { title: "回测实验室", emoji: "🧪", file: "features/backtest-lab.md" },
      { title: "组合与连接", emoji: "💼", file: "features/portfolio-nav.md" },
      { title: "通知与 iMessage", emoji: "🔔", file: "features/notifications.md" },
    ],
  },
  { title: "订阅与 Credits", emoji: "💳", file: "billing-credits.md" },
  { title: "账户与安全", emoji: "🔐", file: "account-security.md" },
  { title: "移动应用", emoji: "📱", file: "mobile-apps.md" },
  { title: "常见问题", emoji: "❓", file: "faq.md" },
  { title: "产品路线图", emoji: "🗺️", file: "roadmap.md" },
  {
    title: "English",
    emoji: "🌐",
    file: "english/README.md",
    children: [
      { title: "Getting Started", emoji: "🚀", file: "english/getting-started.md" },
      { title: "Feature Guide", emoji: "📖", file: "english/features.md" },
      { title: "Billing & Credits", emoji: "💳", file: "english/billing-credits.md" },
      { title: "FAQ & Roadmap", emoji: "❓", file: "english/faq-roadmap.md" },
    ],
  },
];

async function call(method, path, body) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!res.ok) {
    throw new Error(`${method} ${path} -> ${res.status}: ${text.slice(0, 400)}`);
  }
  return data;
}

const read = (file) => readFile(path.join(ROOT, file), "utf8");

async function main() {
  const spaceArg = process.argv.indexOf("--space");
  let spaceId = spaceArg > -1 ? process.argv[spaceArg + 1] : null;

  if (!spaceId) {
    const space = await call("POST", `/orgs/${ORG_ID}/spaces`, {
      title: "PureGamma AI 使用手册",
      visibility: "private",
    });
    spaceId = space.id;
    console.log("created space:", spaceId);
  }

  const cr = await call("POST", `/spaces/${spaceId}/change-requests`, {
    subject: "Publish full product documentation",
  });
  console.log("change request:", cr.id);

  // Find the default root page of the new space to receive README content.
  const pages = await call("GET", `/spaces/${spaceId}/change-requests/${cr.id}/content/pages`);
  const rootPage = (pages.pages || []).find((p) => !p.parentId) || (pages.pages || [])[0];
  if (!rootPage) throw new Error("no root page found in change request");

  const readme = await read("README.md");
  const batch1 = [
    { operation: "update_page", page: rootPage.id, document: { markdown: readme } },
  ];
  for (let i = 0; i < TREE.length; i++) {
    const node = TREE[i];
    batch1.push({
      operation: "insert_page",
      title: node.title,
      emoji: node.emoji,
      at: i + 1,
      document: { markdown: await read(node.file) },
    });
  }
  await call("POST", `/spaces/${spaceId}/change-requests/${cr.id}/content`, { changes: batch1 });
  console.log("batch 1 applied:", batch1.length, "changes");

  // Resolve ids of the freshly inserted group pages for nested children.
  const pagesAfter = await call("GET", `/spaces/${spaceId}/change-requests/${cr.id}/content/pages`);
  const byTitle = new Map((pagesAfter.pages || []).map((p) => [p.title, p.id]));

  const batch2 = [];
  for (const node of TREE) {
    if (!node.children) continue;
    const parentId = byTitle.get(node.title);
    if (!parentId) throw new Error(`parent page id not found for ${node.title}`);
    for (let i = 0; i < node.children.length; i++) {
      const child = node.children[i];
      batch2.push({
        operation: "insert_page",
        into: parentId,
        title: child.title,
        emoji: child.emoji,
        at: i,
        document: { markdown: await read(child.file) },
      });
    }
  }
  await call("POST", `/spaces/${spaceId}/change-requests/${cr.id}/content`, { changes: batch2 });
  console.log("batch 2 applied:", batch2.length, "changes");

  const merged = await call("POST", `/spaces/${spaceId}/change-requests/${cr.id}/merge`);
  console.log("merged:", merged.id || "ok");

  const space = await call("GET", `/spaces/${spaceId}`);
  console.log("space title:", space.title);
  console.log("published url:", space.urls?.published || "(not published yet)");
  console.log("SPACE_ID=" + spaceId);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
