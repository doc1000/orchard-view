// Shared helpers for the Orchard demo recording and the headless agent walkthrough.
const http = require("http");
const fs = require("fs");
const path = require("path");

const APP_DIR = path.resolve(__dirname, "..", "artifacts", "appworld", "standalone",
  "orchard_view_appworld_202615081315");
const APP_PAGE = "visual_search_appworld.html";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
};

// Tiny static server for the standalone app folder on an ephemeral port.
function startServer(root = APP_DIR) {
  const server = http.createServer((req, res) => {
    const urlPath = decodeURIComponent(new URL(req.url, "http://x").pathname);
    const file = path.join(root, urlPath === "/" ? APP_PAGE : urlPath);
    if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404); res.end("not found"); return;
    }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise(resolve => server.listen(0, "127.0.0.1", () => {
    const { port } = server.address();
    resolve({ server, url: `http://127.0.0.1:${port}/${APP_PAGE}` });
  }));
}

async function openApp(page, url) {
  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto(url);
  await page.waitForFunction(() => window.orchard && document.querySelector("[data-testid=tm-node]"));
  if (errors.length) throw new Error(`Page errors on load: ${errors.join("; ")}`);
  return errors;
}

// ── orchard API passthroughs ─────────────────────────
const state = page => page.evaluate(() => window.orchard.getState());

async function nodeId(page, label, tree) {
  const hits = await page.evaluate(([l, t]) => window.orchard.findNodes(l, t), [label, tree]);
  const exact = hits.filter(h => h.label === label);
  const pick = exact.length ? exact : hits;
  if (pick.length !== 1) throw new Error(`Expected one ${tree} node labelled "${label}", got ${pick.length}`);
  return pick[0].id;
}

async function expectScope(page, { working, base }, step) {
  const s = await state(page);
  const bad = (working !== undefined && s.working_count !== working) ||
              (base !== undefined && s.base_count !== base);
  if (bad) {
    throw new Error(`[${step}] expected working=${working} base=${base}, ` +
      `got working=${s.working_count} base=${s.base_count}`);
  }
  console.log(`  ✓ ${step}: ${s.base_count} base → ${s.working_count} working (${s.tree})`);
  return s;
}

module.exports = { APP_DIR, startServer, openApp, state, nodeId, expectScope };
