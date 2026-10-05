// Headless agent walkthrough: the same decision path as the recorded demo,
// driven only through window.orchard (no clicks, no pixels). Prints the
// structured state after every step — the shape an agent tool would return.
//
//   npm run demo:agent            compact trace
//   npm run demo:agent -- --full  full JSON state per step
const { chromium } = require("playwright");
const { startServer, openApp, nodeId } = require("./lib");

const FULL = process.argv.includes("--full");

async function main() {
  const { server, url } = await startServer();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await openApp(page, url);

    const call = (expr, arg) => page.evaluate(expr, arg);
    const log = (step, s) => {
      if (FULL) { console.log(`\n## ${step}\n${JSON.stringify(s, null, 2)}`); return; }
      const extra = s.candidate_tools && s.candidate_tools.length <= 10
        ? `  ${JSON.stringify(s.candidate_tools)}` : "";
      console.log(`${step.padEnd(52)} ${s.tree.padEnd(8)} base=${String(s.base_count).padStart(3)} ` +
        `working=${String(s.working_count).padStart(3)}${extra}`);
    };

    log("reset()", await call(() => orchard.reset()));
    log('search("user account")', await call(q => orchard.search(q), "user account"));

    const profile = await nodeId(page, "Profile, Credential, Address, and Friend Management", "domain");
    log("excludeNode(<Profile, Credential, Address…>)", await call(id => orchard.excludeNode(id), profile));

    log('switchTree("function")', await call(() => orchard.switchTree("function")));
    const auth = await nodeId(page, "Authentication and code dispatch", "function");
    const s = await call(id => orchard.drillInto(id), auth);
    log("drillInto(<Authentication and code dispatch>)", s);
    if (FULL) console.log("children:", s.children.map(c => `${c.label} ${c.working_count}/${c.base_count}`));

    const access = await nodeId(page, "Account Access Validation", "function");
    log("includeNode(<Account Access Validation>)", await call(id => orchard.includeNode(id), access));
    log("commitScope()", await call(() => orchard.commitScope()));

    log('switchTree("domain")', await call(() => orchard.switchTree("domain")));
    const amazonLogin = await nodeId(page, "amazon.login", "domain");
    log("includeNode(<amazon.login>)", await call(id => orchard.includeNode(id), amazonLogin));
    const final = await call(() => orchard.commitScope());
    log("commitScope()", final);

    const tool = await call(id => orchard.inspectTool(id), final.candidate_tools[0]);
    console.log("\ninspectTool →", JSON.stringify(tool));

    if (final.working_count !== 1 || final.candidate_tools[0] !== "amazon.login") {
      throw new Error(`Expected exactly amazon.login, got ${JSON.stringify(final.candidate_tools)}`);
    }
    console.log(`\nOK: ${final.corpus_count} tools → 1 (${final.commits.join(" | ")})`);
  } finally {
    await browser.close();
    server.close();
  }
}

main().catch(e => { console.error(e); process.exit(1); });
