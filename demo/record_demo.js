// Recorded Playwright demo of the Orchard visual tool search.
//
//   npm run demo   →  demo/orchard_demo.webm (+ demo/orchard_demo.mp4 if ffmpeg is on PATH)
//
// Story: 457 tools → query intent → reject a region → switch to the Function
// partition → include the login cluster → Go (commit) → back to Domain →
// pick amazon.login → Go → inspect. Every interaction is a real mouse/keyboard
// action on the UI; window.orchard is used only to look up node ids and to read
// state for assertions and the on-screen numbers (never hardcoded).
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { startServer, openApp, state, nodeId, expectScope } = require("./lib");

const VIEWPORT = { width: 1440, height: 900 };
const TMP_DIR = path.join(__dirname, ".video-tmp");
const OUT_WEBM = path.join(__dirname, "orchard_demo.webm");
const OUT_MP4 = path.join(__dirname, "orchard_demo.mp4");

// ── demo-only overlay: visible cursor, click ripple, captions ──────────
// Injected by the recorder; nothing here ships in the product page.
const OVERLAY_SCRIPT = () => {
  window.addEventListener("DOMContentLoaded", () => {
    const css = document.createElement("style");
    css.textContent = `
      .tooltip { display: none !important; }
      #demo-cursor { position: fixed; z-index: 99999; width: 22px; height: 22px; margin: -11px 0 0 -11px;
        border-radius: 50%; background: rgba(255,224,64,0.35); border: 2px solid #ffe040;
        box-shadow: 0 0 12px rgba(255,224,64,0.6); pointer-events: none; left: 720px; top: 450px;
        transition: transform 0.12s ease; }
      #demo-cursor.down { transform: scale(0.7); }
      .demo-ripple { position: fixed; z-index: 99998; width: 16px; height: 16px; margin: -8px 0 0 -8px;
        border-radius: 50%; border: 3px solid #ffe040; pointer-events: none;
        animation: demo-ripple 0.6s ease-out forwards; }
      .demo-ripple.right { border-color: #ff5555; }
      .demo-ripple.include { border-color: #00ff88; }
      @keyframes demo-ripple { to { transform: scale(4); opacity: 0; } }
      .demo-callout { position: fixed; z-index: 99997; pointer-events: none; transform: translate(-50%, -50%);
        background: rgba(6,9,13,0.92); border: 2px solid #00d8ff; border-radius: 8px;
        color: #fff; font: 800 30px Inter, 'Segoe UI', sans-serif; padding: 16px 28px; white-space: nowrap;
        box-shadow: 0 8px 40px rgba(0,0,0,0.6); opacity: 0; transition: opacity 0.35s ease; }
      .demo-callout small { display: block; font-size: 16px; font-weight: 600; color: #7aaccc; margin-top: 6px; }
      .demo-callout.show { opacity: 1; }
      .demo-key { position: fixed; z-index: 99999; pointer-events: none; background: #ffe040; color: #000;
        font: 800 13px Inter, 'Segoe UI', sans-serif; padding: 4px 9px; border-radius: 4px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.5); opacity: 0; transition: opacity 0.2s ease; }
      .demo-key.show { opacity: 1; }`;
    document.head.appendChild(css);
    const cursor = document.createElement("div");
    cursor.id = "demo-cursor";
    document.body.appendChild(cursor);
    window.__demoRipple = "";
    document.addEventListener("mousemove", e => {
      cursor.style.left = e.clientX + "px"; cursor.style.top = e.clientY + "px";
    }, true);
    document.addEventListener("mousedown", e => {
      cursor.classList.add("down");
      const r = document.createElement("div");
      r.className = "demo-ripple " + (window.__demoRipple || (e.button === 2 ? "right" : ""));
      r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px";
      document.body.appendChild(r);
      setTimeout(() => r.remove(), 700);
    }, true);
    document.addEventListener("mouseup", () => cursor.classList.remove("down"), true);
  });
};

// ── pacing ─────────────────────────────────────────────
const SHORT = 500, MAJOR = 1300, HOLD = 2600;
const pause = (page, ms) => page.waitForTimeout(ms);

// ── mouse helpers (semantic targets → coordinates) ─────
async function rectOf(page, selector) {
  const b = await page.locator(selector).first().boundingBox();
  if (!b) throw new Error(`Not visible: ${selector}`);
  return b;
}
const blockSel = id => `[data-testid=tm-node][data-level=block][data-node-id="${id}"] > rect`;
const tileSel = id => `[data-testid=tm-node][data-level=tile][data-node-id="${id}"] > rect`;

async function glideTo(page, x, y) {
  await page.mouse.move(x, y, { steps: 30 });
  await pause(page, 220); // brief settle before clicking, like a human would
}

async function blockHeader(page, id) {
  const b = await rectOf(page, blockSel(id));
  return { x: b.x + Math.min(b.width / 2, 120), y: b.y + 11 }; // the header strip above its tiles
}
async function tileCenter(page, id) {
  const b = await rectOf(page, tileSel(id));
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}
async function elementCenter(page, selector) {
  const b = await rectOf(page, selector);
  return { x: b.x + b.width / 2, y: b.y + b.height / 2 };
}

async function leftClick(page, pt) {
  await glideTo(page, pt.x, pt.y);
  await page.mouse.click(pt.x, pt.y);
}
async function rightClick(page, pt, { shift = false, ripple = "" } = {}) {
  await glideTo(page, pt.x, pt.y);
  if (shift) await keyHint(page, "⇧ Shift + right-click  =  exclude", pt);
  else if (ripple === "include") await keyHint(page, "right-click  =  include", pt);
  await page.evaluate(r => { window.__demoRipple = r; }, ripple);
  if (shift) await page.keyboard.down("Shift");
  await page.mouse.click(pt.x, pt.y, { button: "right" });
  if (shift) await page.keyboard.up("Shift");
  await page.evaluate(() => { window.__demoRipple = ""; });
}

// Small keycap label next to the cursor (the viewer can't see the keyboard).
async function keyHint(page, text, pt) {
  await page.evaluate(([t, x, y]) => {
    const k = document.createElement("div");
    k.className = "demo-key"; k.textContent = t;
    k.style.left = (x + 18) + "px"; k.style.top = (y + 16) + "px";
    document.body.appendChild(k);
    requestAnimationFrame(() => k.classList.add("show"));
    setTimeout(() => { k.classList.remove("show"); setTimeout(() => k.remove(), 300); }, 1500);
  }, [text, pt.x, pt.y]);
  await pause(page, 450);
}

// Large caption centred over the treemap; fades out automatically.
async function callout(page, title, sub = "", ms = 2300) {
  await page.evaluate(([t, s, d]) => {
    const tm = document.getElementById("treemapView").getBoundingClientRect();
    const c = document.createElement("div");
    c.className = "demo-callout";
    c.textContent = t;
    if (s) { const sm = document.createElement("small"); sm.textContent = s; c.appendChild(sm); }
    c.style.left = (tm.left + tm.width / 2) + "px";
    c.style.top = (tm.top + tm.height / 2) + "px";
    document.body.appendChild(c);
    requestAnimationFrame(() => c.classList.add("show"));
    setTimeout(() => { c.classList.remove("show"); setTimeout(() => c.remove(), 400); }, d);
  }, [title, sub, ms]);
}

const pctGone = (from, to, digits = 0) => `${((1 - to / from) * 100).toFixed(digits)}%`;

// ── the demo ───────────────────────────────────────────
async function runDemo(page) {
  // Scene 0 — the full tool space
  let s = await expectScope(page, { working: 457, base: 457 }, "start");
  await page.mouse.move(VIEWPORT.width / 2, VIEWPORT.height / 2);
  await callout(page, `${s.corpus_count} tools in scope`, "Task: log a user into their Amazon account", 2600);
  await pause(page, 3000);

  // Scene 1 — start from intent, not a tool name
  await leftClick(page, await elementCenter(page, "#searchInput"));
  await page.locator("#searchInput").pressSequentially("user account", { delay: 85 });
  await pause(page, SHORT);
  await leftClick(page, await elementCenter(page, "header button:has-text('Parse')"));
  s = await expectScope(page, { working: 69, base: 457 }, "query 'user account'");
  await pause(page, MAJOR);

  // Scene 2 — most of the space is no longer interesting
  await callout(page, `${s.base_count} → ${s.working_count} candidates`,
    `${pctGone(s.base_count, s.working_count)} of the tool space set aside — red regions`);
  await pause(page, 2800);

  // Scene 3 — look closer, then explicitly reject an adjacent-but-wrong region
  const identity = await nodeId(page, "User identity, profile, subscription management", "domain");
  await leftClick(page, await blockHeader(page, identity));
  await expectScope(page, { working: 69 }, "drill into identity");
  await pause(page, MAJOR);
  const profile = await nodeId(page, "Profile, Credential, Address, and Friend Management", "domain");
  const before = s.working_count;
  await rightClick(page, await blockHeader(page, profile), { shift: true });
  s = await expectScope(page, { working: 59 }, "exclude profile/credential mgmt");
  await pause(page, SHORT);
  await callout(page, `Rejected: profile & credential management`,
    `${before} → ${s.working_count} — a decision about where NOT to search`);
  await pause(page, 2800);

  // Scene 4 — same remaining tools, different partition
  await leftClick(page, await elementCenter(page, "#btnFunction"));
  s = await expectScope(page, { working: 59 }, "switch to Function tree");
  await pause(page, SHORT);
  await callout(page, `Same ${s.working_count} candidates — now partitioned by function`,
    "Domain: what is it about?   →   Function: what does it do?", 2800);
  await pause(page, 3300);

  // Scene 5 — drill into the authentication region and include the login cluster
  const auth = await nodeId(page, "Authentication and code dispatch", "function");
  await leftClick(page, await blockHeader(page, auth));
  await expectScope(page, { working: 59 }, "drill into authentication");
  await pause(page, MAJOR);
  const access = await nodeId(page, "Account Access Validation", "function");
  await rightClick(page, await blockHeader(page, access), { ripple: "include" });
  s = await expectScope(page, { working: 9 }, "include Account Access Validation");
  await pause(page, MAJOR);

  // Scene 6 — Go commits the reduction: it becomes the new search universe
  const baseBefore = s.base_count;
  await leftClick(page, await elementCenter(page, "#goBtn"));
  s = await expectScope(page, { working: 9, base: 9 }, "Go (commit)");
  await callout(page, `Committed: ${baseBefore} → ${s.base_count} tools`,
    "the reduced scope is now the whole search space", 2600);
  await pause(page, 3000);

  // Scene 7 — back to Domain: same login tools, organized by domain
  await leftClick(page, await elementCenter(page, "#btnDomain"));
  s = await expectScope(page, { working: 9, base: 9 }, "switch to Domain tree");
  await pause(page, SHORT);
  await callout(page, `Same ${s.base_count} login tools — now by domain`, "one per app", 2200);
  await pause(page, 2700);

  // Scene 8 — isolate the Amazon login and commit again
  const amazonLogin = await nodeId(page, "amazon.login", "domain");
  await rightClick(page, await tileCenter(page, amazonLogin), { ripple: "include" });
  s = await expectScope(page, { working: 1, base: 9 }, "include amazon.login");
  await pause(page, MAJOR);
  await leftClick(page, await elementCenter(page, "#goBtn"));
  s = await expectScope(page, { working: 1, base: 1 }, "Go (commit)");
  await pause(page, MAJOR);

  // Scene 9 — inspect the tool
  await leftClick(page, await tileCenter(page, amazonLogin));
  await pause(page, 700);
  await leftClick(page, await elementCenter(page, `[data-testid=tm-doc][data-doc-id="amazon.login"] > rect`));
  await page.waitForSelector("#previewPanel.open");
  const title = await page.locator("#pvTitle").textContent();
  if (title !== "amazon.login") throw new Error(`Preview shows "${title}", expected amazon.login`);
  console.log("  ✓ preview open: amazon.login");
  await page.mouse.move(VIEWPORT.width - 60, VIEWPORT.height - 60, { steps: 20 });
  s = await state(page);
  await callout(page, `${s.corpus_count} tools → ${s.base_count}`,
    `search space reduced ${pctGone(s.corpus_count, s.base_count, 1)}`, 60000);
  await pause(page, HOLD + 800);
}

async function main() {
  fs.rmSync(TMP_DIR, { recursive: true, force: true });
  const { server, url } = await startServer();
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
    recordVideo: { dir: TMP_DIR, size: VIEWPORT },
  });
  await context.addInitScript(OVERLAY_SCRIPT);
  const page = await context.newPage();
  const started = Date.now();
  let failed = null, videoPath = null;
  try {
    console.log("Recording Orchard demo…");
    await openApp(page, url);
    await page.evaluate(() => window.orchard.reset());
    await runDemo(page);
  } catch (e) {
    failed = e;
  } finally {
    await context.close(); // finalizes the video file
    videoPath = await page.video().path();
    await browser.close();
    server.close();
  }
  if (failed) {
    console.error(`\nDemo FAILED: ${failed.message}`);
    console.error(`Partial recording left in ${TMP_DIR}`);
    process.exit(1);
  }

  fs.copyFileSync(videoPath, OUT_WEBM);
  fs.rmSync(TMP_DIR, { recursive: true, force: true });
  console.log(`\nSaved ${path.relative(process.cwd(), OUT_WEBM)} (${((Date.now() - started) / 1000).toFixed(1)}s run)`);

  try {
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", OUT_WEBM,
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-movflags", "+faststart", OUT_MP4]);
    console.log(`Saved ${path.relative(process.cwd(), OUT_MP4)}`);
  } catch (e) {
    console.log(`MP4 skipped (${e.code === "ENOENT" ? "ffmpeg not on PATH" : e.message.split("\n")[0]})`);
  }
}

main();
