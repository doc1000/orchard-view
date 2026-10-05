// ════════════════════════════════════════════════════
// ORCHARD API — programmatic control surface over the visual search UI
// ════════════════════════════════════════════════════
//
// Thin wrapper over the page's existing functions and stores (BASE, LEDGER,
// WORKING_SCOPE, go(), parseQuery(), switchTree(), …). It adds no search logic
// of its own: every mutator routes through the same code path a click would,
// then returns getState() — plain JSON an agent can reason over without pixels.
//
// Must load after the main script (relies on its top-level globals).
//
// Three levels of the Orchard model, as surfaced here:
//   base_count     — the committed search universe (BASE)
//   working_count  — tentative result of current decisions (WORKING_SCOPE)
//   commitScope()  — Go: working scope becomes the new base
(function () {
  const _switchTree = switchTree;

  // ── lookups ──────────────────────────────────────
  function treeOf(nodeId) {
    if (findNode(nodeId, DOMAIN_TREE)) return "domain";
    if (findNode(nodeId, FUNCTION_TREE)) return "function";
    return null;
  }

  function requireNode(nodeId) {
    const tree = treeOf(nodeId);
    if (!tree || nodeId === "root") throw new Error(`Unknown node id: ${nodeId}`);
    return { tree, node: findNode(nodeId, TREES[tree]) };
  }

  function nodeSummary(node) {
    return {
      id: node.id,
      label: node.label,
      is_tool: !node.children || node.children.length === 0,
      base_count: nodeBaseCount(node.id),
      working_count: nodeWorkingCount(node.id),
      polarity: getNodeLedgerPolarity(node.id),
    };
  }

  // Nodes with nothing left in the committed base are hidden by the UI too.
  function liveChildren(node) {
    return (node.children || [])
      .filter(c => nodeBaseCount(c.id) > 0)
      .map(nodeSummary);
  }

  function labelOf(nodeId) {
    const n = findNode(nodeId, DOMAIN_TREE) || findNode(nodeId, FUNCTION_TREE);
    return n ? n.label : nodeId;
  }

  // ── read-only state ──────────────────────────────
  function getActiveDecisions() {
    return getActiveLedgerChips().map(e => ({
      target_type: e.target_type,
      target_id: e.target_id,
      label: e.target_type === "node" ? labelOf(e.target_id) : e.target_id,
      polarity: e.polarity,
      source: e.source,
    }));
  }

  function getCandidateTools() { return WORKING_SCOPE.map(d => d.id); }
  function getCandidateCount() { return WORKING_SCOPE.length; }
  function getScope() {
    return {
      corpus_count: CORPUS.length,
      base_count: BASE.length,
      working_count: WORKING_SCOPE.length,
    };
  }

  function getState() {
    const decisions = getActiveDecisions();
    const focus = treemapFocusNode();
    return {
      tree: S.treeMode,
      ...getScope(),
      focus_path: S.drillPath.map(n => ({ id: n.id, label: n.label })),
      included_nodes: decisions.filter(d => d.target_type === "node" && d.polarity === "include")
        .map(d => ({ id: d.target_id, label: d.label })),
      excluded_nodes: decisions.filter(d => d.target_type === "node" && d.polarity === "exclude")
        .map(d => ({ id: d.target_id, label: d.label })),
      terms: decisions.filter(d => d.target_type === "term")
        .map(d => ({ term: d.target_id, polarity: d.polarity })),
      children: liveChildren(focus),
      candidate_tools: WORKING_SCOPE.length <= 50 ? getCandidateTools() : null,
      commits: SESSION_HISTORY.map(h => h.label),
      preview: S.previewDoc ? S.previewDoc.id : null,
    };
  }

  // ── navigation ───────────────────────────────────
  function findNodes(labelSubstring, tree) {
    const needle = String(labelSubstring).toLowerCase();
    const out = [];
    for (const mode of tree ? [tree] : ["domain", "function"]) {
      (function walk(node, depth) {
        if (node.id !== "root" && node.label.toLowerCase().includes(needle)) {
          out.push({ id: node.id, label: node.label, tree: mode, depth });
        }
        for (const c of node.children || []) walk(c, depth + 1);
      })(TREES[mode], 0);
    }
    return out;
  }

  function getChildren(nodeId) {
    const node = nodeId ? requireNode(nodeId).node : treemapFocusNode();
    return liveChildren(node);
  }

  function renderDrill() { renderTreemap(); renderTreemapBreadcrumb(); }

  function drillInto(nodeId) {
    const path = pathToNode(currentTree(), nodeId);
    if (!path) throw new Error(`Node ${nodeId} is not in the current (${S.treeMode}) tree`);
    S.drillPath = path.slice(1).map(id => findNode(id, currentTree()));
    renderDrill();
    return getState();
  }
  function drillUp() { S.drillPath = S.drillPath.slice(0, -1); renderDrill(); return getState(); }
  function drillToRoot() { S.drillPath = []; renderDrill(); return getState(); }

  // ── mutators (each returns getState()) ───────────
  function search(query) {
    document.getElementById("searchInput").value = query;
    parseQuery();
    return getState();
  }

  function setTree(mode) {
    if (mode !== "domain" && mode !== "function") throw new Error(`Unknown tree: ${mode}`);
    _switchTree(mode);
    return getState();
  }

  function setPolarity(nodeId, polarity) {
    const { tree } = requireNode(nodeId);
    setNodePolarity(nodeId, polarity, `api_${tree}_tree`);
    return getState();
  }

  function commitScope() {
    if (WORKING_SCOPE.length === 0) throw new Error("Cannot commit an empty working scope");
    go();
    return getState();
  }

  function reset() {
    resetAll();
    closePreview();
    _switchTree("domain");
    return getState();
  }

  function inspectTool(toolId) {
    const doc = CORPUS.find(d => String(d.id) === String(toolId));
    if (!doc) throw new Error(`Unknown tool: ${toolId}`);
    openPreview(doc);
    return {
      id: doc.id,
      title: doc.title,
      path: doc.path,
      body: doc.body,
      in_working_scope: WORKING_SCOPE.some(d => d.id === doc.id),
    };
  }

  window.orchard = {
    // state
    getState, getScope, getCandidateCount, getCandidateTools, getActiveDecisions,
    // lookup / navigation
    findNodes, getChildren, drillInto, drillUp, drillToRoot,
    // decisions
    search,
    switchTree: setTree,
    includeNode: id => setPolarity(id, "include"),
    excludeNode: id => setPolarity(id, "exclude"),
    clearNode:   id => setPolarity(id, "neutral"),
    commitScope,
    inspectTool,
    reset,
  };
})();
