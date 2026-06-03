/* dirplot interactive treemap — D3 v7 */
"use strict";

// ── Constants & globals ───────────────────────────────────────────────────

const TRANSITION_MS = 280;
const MIN_LABEL_W = 28;
const MIN_LABEL_H = 12;
const MIN_FONT = 6;
const CHAR_W = 0.60;   // char_width / font_size  (JetBrains Mono approximation)
const LINE_H = 1.35;   // line_height / font_size

const allowWrite = document.body.dataset.allowWrite === "true";

let _treeData = null;
let _zoomStack = [];
let _selection = new Set();  // paths of shift-selected nodes

// Current settings (defaults; overridden by /api/config)
const settings = {
  depth: null,        // null = unlimited
  darkMode: true,
  logScale: 4,   // 1 = off; 2–10 = logscale strength (default 4)
  fontSize: 12,
  colormap: "tab20",
  canvasW: null,      // null = auto
  canvasH: null,
  exclude: [],
  include: [],
  highlights: [],     // [{glob, color}]
};

// Colours that mirror render_png / svg_render dark/light logic
function theme() {
  return settings.darkMode
    ? { hdrBg: "#1c1c2e", hdrText: "#e0e0e0" }
    : { hdrBg: "#e8e8f0", hdrText: "#1c1c2e" };
}

// ── Helpers ───────────────────────────────────────────────────────────────

function darken(hex, amount = 0.12) {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.max(0, ((n >> 16) & 0xff) - Math.round(255 * amount));
  const g = Math.max(0, ((n >> 8) & 0xff) - Math.round(255 * amount));
  const b = Math.max(0, (n & 0xff) - Math.round(255 * amount));
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

function textColor(hex) {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 0xff, g = (n >> 8) & 0xff, b = n & 0xff;
  return (0.299 * r + 0.587 * g + 0.114 * b) > 140 ? "#111" : "#eee";
}

function findNode(root, path) {
  if (root.path === path) return root;
  for (const c of (root.children || [])) {
    const f = findNode(c, path);
    if (f) return f;
  }
  return null;
}

// ── Multi-selection ───────────────────────────────────────────────────────

function toggleSelection(path) {
  if (_selection.has(path)) _selection.delete(path);
  else _selection.add(path);
  updateSelectionOverlays();
}

function clearSelection() {
  if (_selection.size === 0) return;
  _selection.clear();
  updateSelectionOverlays();
}

function updateSelectionOverlays() {
  canvas.selectAll("rect.selection-overlay").remove();
  if (_selection.size === 0) return;
  canvas.selectAll("g.node").each(function(d) {
    if (!_selection.has(d.data.path)) return;
    const w = d.x1 - d.x0, h = d.y1 - d.y0;
    canvas.append("rect")
      .attr("class", "selection-overlay")
      .attr("x", d.x0).attr("y", d.y0)
      .attr("width", w).attr("height", h)
      .attr("fill", "rgba(124,124,255,0.22)")
      .attr("stroke", "#7c7cff")
      .attr("stroke-width", 2)
      .attr("rx", 1)
      .attr("pointer-events", "none");
  });
}

// ── Minimal glob matching (supports ** and *)
function globMatch(pattern, str) {
  const re = pattern
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*\*/g, "\x00")
    .replace(/\*/g, "[^/]*")
    .replace(/\x00/g, ".*");
  return new RegExp(`^${re}$`).test(str);
}

function headerH() { return settings.fontSize + 8; }

// Port of render_png._wrap — split at delimiters, hard-break if needed
function wrapText(name, maxW, fontSize) {
  const maxChars = Math.max(1, Math.floor(maxW / (fontSize * CHAR_W)));
  if (name.length <= maxChars) return [name];
  const lines = [];
  let rem = name;
  while (rem.length > 0) {
    if (rem.length <= maxChars) { lines.push(rem); break; }
    const chunk = rem.slice(0, maxChars);
    let split = -1;
    for (const d of [".", "_", "-", " "]) {
      const i = chunk.lastIndexOf(d);
      if (i > split) split = i;
    }
    if (split > 0) {
      lines.push(rem.slice(0, split));
      rem = rem.slice(split);
    } else {
      lines.push(chunk);
      rem = rem.slice(maxChars);
    }
  }
  return lines;
}

// Port of render_png._fit_font — largest font size where wrapped text fits maxW×maxH
function fitFont(name, maxW, maxH, maxSize) {
  if (maxW < 4 || maxH < MIN_FONT * LINE_H) return null;
  const textW = name.length * maxSize * CHAR_W;
  const nLines = Math.max(1, Math.ceil(textW / maxW));
  let fontSize = Math.max(MIN_FONT, Math.min(maxSize, Math.floor(maxH / (nLines * LINE_H))));
  for (let i = 0; i < 2; i++) {
    const lines = wrapText(name, maxW, fontSize);
    const actualH = lines.length * fontSize * LINE_H;
    if (actualH <= maxH) return { fontSize, lines };
    fontSize = Math.max(MIN_FONT, Math.floor(fontSize * maxH / actualH));
  }
  return { fontSize, lines: wrapText(name, maxW, fontSize) };
}

// Mirror render_png logic: try horizontal; for tall tiles (h >= 2w) also try vertical
function labelOrient(name, w, h, maxSize) {
  const hFit = fitFont(name, w - 4, h - 4, maxSize);
  let vFit = null;
  if (h >= w * 2) vFit = fitFont(name, h - 4, w - 4, maxSize);
  if (!hFit && !vFit) return null;
  if (vFit && hFit) {
    const hl = hFit.lines.length, vl = vFit.lines.length;
    if (vl < hl || (vl === hl && vFit.fontSize > hFit.fontSize))
      return { ...vFit, rotate: true };
  }
  if (vFit && !hFit) return { ...vFit, rotate: true };
  return { ...hFit, rotate: false };
}

// ── Layout ────────────────────────────────────────────────────────────────

function makeLayout(w, h) {
  return d3.treemap()
    .size([w, h])
    .tile(d3.treemapSquarify)
    .paddingTop(headerH() + 3)
    .paddingInner(1)
    .paddingLeft(2)
    .paddingRight(2)
    .paddingBottom(2)
    .round(true);
}

function buildHierarchy(data) {
  return d3.hierarchy(data, d => d.children)
    .sum(d => (!d.children || d.children.length === 0) ? Math.max(1, d.size) : 0)
    .sort((a, b) => b.value - a.value);
}

// ── Rendering ─────────────────────────────────────────────────────────────

const svg = d3.select("#treemap");

// Cushion gradient defs — defined once, reused by all tiles via objectBoundingBox
(function() {
  const defs = svg.append("defs");
  function makeCushion(id, hiAlpha, shAlpha) {
    const g = defs.append("linearGradient")
      .attr("id", id)
      .attr("x1", "0").attr("y1", "0")
      .attr("x2", "1").attr("y2", "1")
      .attr("gradientUnits", "objectBoundingBox");
    g.append("stop").attr("offset", "0%").attr("stop-color", "white").attr("stop-opacity", hiAlpha);
    g.append("stop").attr("offset", "50%").attr("stop-color", "black").attr("stop-opacity", 0);
    g.append("stop").attr("offset", "100%").attr("stop-color", "black").attr("stop-opacity", shAlpha);
  }
  makeCushion("cushion-file", 0.20, 0.20);  // full strength for file tiles
  makeCushion("cushion-dir",  0.10, 0.10);  // half strength for dir-level overlay
})();

const canvas = svg.append("g").attr("class", "canvas");

function containerSize() {
  const el = document.getElementById("treemap-container");
  const w = settings.canvasW || el.clientWidth;
  const h = settings.canvasH || el.clientHeight;
  return { w, h };
}

function applyCanvasSize() {
  const el = document.getElementById("treemap-container");
  if (settings.canvasW) {
    el.style.width = settings.canvasW + "px";
    el.style.overflow = "auto";
  } else {
    el.style.width = "";
    el.style.overflow = "";
  }
  if (settings.canvasH) {
    el.style.height = settings.canvasH + "px";
  } else {
    el.style.height = "";
  }
}

function highlightColorFor(path) {
  for (const { glob, color } of settings.highlights) {
    // match against path segments — try full path and basename
    const base = path.split("/").pop();
    if (globMatch(glob, path) || globMatch(glob, base)) return color;
  }
  return null;
}

function renderTreemap(data) {
  const { w, h } = containerSize();
  svg.attr("viewBox", `0 0 ${w} ${h}`)
     .attr("width", w)
     .attr("height", h);

  const layout = makeLayout(w, h);
  const root = buildHierarchy(data);
  layout(root);

  canvas.selectAll("*").remove();

  const hh = headerH();
  const fs = settings.fontSize;

  const nodes = canvas.selectAll("g.node")
    .data(root.descendants())
    .join("g")
      .attr("class", d => `node ${d.data.is_dir ? "dir" : "file"}`)
      .attr("data-path", d => d.data.path)
      .attr("data-ext", d => d.data.extension || "");

  const nw = d => d.x1 - d.x0;
  const nh = d => d.y1 - d.y0;

  // Background rect
  nodes.append("rect")
    .attr("class", "tile-bg")
    .attr("x", d => d.x0)
    .attr("y", d => d.y0)
    .attr("width", nw)
    .attr("height", nh)
    .attr("fill", d => d.data.color)
    .attr("rx", 1);

  // Directory header strip
  const t = theme();
  const dirs = nodes.filter(d => d.data.is_dir && nh(d) > hh);
  dirs.append("rect")
    .attr("class", "tile-header")
    .attr("x", d => d.x0 + 1)
    .attr("y", d => d.y0 + 1)
    .attr("width", d => Math.max(0, nw(d) - 2))
    .attr("height", hh - 1)
    .attr("fill", t.hdrBg);

  // Directory header label — adaptive font size within the strip height
  dirs.filter(d => nw(d) > MIN_LABEL_W).each(function(d) {
    const w = nw(d), availW = w - 8, availH = hh - 4;
    const fit = fitFont(d.data.name, availW, availH, Math.max(8, fs));
    if (!fit) return;
    const cx = d.x0 + w / 2, cy = d.y0 + hh / 2;
    const lh = fit.fontSize * LINE_H, n = fit.lines.length;
    const el = d3.select(this).append("text")
      .attr("x", cx).attr("y", cy)
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "middle")
      .attr("font-size", `${fit.fontSize}px`)
      .attr("font-weight", "600")
      .attr("fill", t.hdrText)
      .attr("pointer-events", "none");
    fit.lines.forEach((line, i) => {
      el.append("tspan").attr("x", cx).attr("dy", i === 0 ? -(n - 1) / 2 * lh : lh).text(line);
    });
  });

  // File labels — adaptive size + vertical rotation for tall narrow tiles
  nodes.filter(d => !d.data.is_dir && nw(d) > MIN_LABEL_W && nh(d) > MIN_LABEL_H)
    .each(function(d) {
      const w = nw(d), h = nh(d);
      const orient = labelOrient(d.data.name, w, h, fs);
      if (!orient) return;
      const cx = d.x0 + w / 2, cy = d.y0 + h / 2;
      const lh = orient.fontSize * LINE_H, n = orient.lines.length;
      const el = d3.select(this).append("text")
        .attr("text-anchor", "middle")
        .attr("dominant-baseline", "middle")
        .attr("font-size", `${orient.fontSize}px`)
        .attr("fill", textColor(d.data.color))
        .attr("pointer-events", "none");
      if (orient.rotate) {
        el.attr("transform", `translate(${cx},${cy}) rotate(-90)`);
        orient.lines.forEach((line, i) => {
          el.append("tspan").attr("x", 0).attr("dy", i === 0 ? -(n - 1) / 2 * lh : lh).text(line);
        });
      } else {
        el.attr("x", cx).attr("y", cy);
        orient.lines.forEach((line, i) => {
          el.append("tspan").attr("x", cx).attr("dy", i === 0 ? -(n - 1) / 2 * lh : lh).text(line);
        });
      }
    });

  // Highlight borders
  if (settings.highlights.length > 0) {
    nodes.each(function(d) {
      const color = highlightColorFor(d.data.path);
      if (!color) return;
      const g = d3.select(this);
      g.append("rect")
        .attr("x", d.x0 + 1)
        .attr("y", d.y0 + 1)
        .attr("width", Math.max(0, nw(d) - 2))
        .attr("height", Math.max(0, nh(d) - 2))
        .attr("fill", "none")
        .attr("stroke", color)
        .attr("stroke-width", 2)
        .attr("rx", 1)
        .attr("pointer-events", "none");
    });
  }

  // Cushion overlay — file tiles (full strength, drawn on top of labels)
  nodes.filter(d => !d.data.is_dir && nw(d) >= 4 && nh(d) >= 4)
    .append("rect")
    .attr("x", d => d.x0).attr("y", d => d.y0)
    .attr("width", nw).attr("height", nh)
    .attr("fill", "url(#cushion-file)")
    .attr("pointer-events", "none");

  // Cushion overlay — dir tiles (half strength, appended to canvas last so they
  // sit above all child nodes in SVG paint order)
  canvas.selectAll("g.node.dir").each(function(d) {
    const w = nw(d), h = nh(d);
    if (w < 4 || h < 4) return;
    canvas.append("rect")
      .attr("class", "dir-cushion")
      .attr("x", d.x0).attr("y", d.y0)
      .attr("width", w).attr("height", h)
      .attr("fill", "url(#cushion-dir)")
      .attr("pointer-events", "none");
  });

  // Interactions
  nodes.filter(d => !d.data.is_dir)
    .on("click", (event, d) => {
      event.stopPropagation();
      hideContextMenu();
      if (event.shiftKey) {
        toggleSelection(d.data.path);
      } else {
        clearSelection();
        showInfoPanel(d.data);
        if (_activeTab === "preview") previewFile(d.data);
      }
    })
    .on("contextmenu", (event, d) => { event.preventDefault(); showContextMenu(event.clientX, event.clientY, d.data); });

  dirs
    .on("click", (event, d) => {
      if (!event.shiftKey) return;
      event.stopPropagation();
      hideContextMenu();
      toggleSelection(d.data.path);
    })
    .on("dblclick", (event, d) => {
      event.stopPropagation();
      if (d.data.children && d.data.children.length > 0) zoomInto(d.data);
    })
    .on("contextmenu", (event, d) => { event.preventDefault(); showContextMenu(event.clientX, event.clientY, d.data); });

  svg.on("click", () => clearSelection());

  updateBreadcrumb();
  updateSelectionOverlays();
}

// ── Zoom ──────────────────────────────────────────────────────────────────

function pathChain(root, targetPath) {
  if (root.path === targetPath) return [root];
  for (const c of (root.children || [])) {
    const r = pathChain(c, targetPath);
    if (r) return [root, ...r];
  }
  return null;
}

function zoomInto(nodeData) {
  const chain = pathChain(_treeData, nodeData.path);
  // chain = [root, ...ancestors, target] — exclude root (index 0)
  _zoomStack = chain ? chain.slice(1).map(n => n.path) : [nodeData.path];
  const focused = findNode(_treeData, nodeData.path);
  if (focused) renderTreemap(focused);
}

function zoomOut() {
  _zoomStack.pop();
  const path = _zoomStack[_zoomStack.length - 1];
  const focused = path ? findNode(_treeData, path) : _treeData;
  if (focused) renderTreemap(focused);
}

// ── Breadcrumb ────────────────────────────────────────────────────────────

function updateBreadcrumb() {
  const nav = document.getElementById("breadcrumb-trail");
  nav.innerHTML = "";
  const crumbs = [{ label: _treeData ? _treeData.name : "root", path: null }];
  for (const p of _zoomStack) {
    const n = findNode(_treeData, p);
    if (n) crumbs.push({ label: n.name, path: p });
  }
  crumbs.forEach((c, i) => {
    if (i > 0) {
      const sep = document.createElement("span");
      sep.className = "sep";
      sep.textContent = " / ";
      nav.appendChild(sep);
    }
    const span = document.createElement("span");
    span.textContent = c.label;
    if (i < crumbs.length - 1) {
      span.addEventListener("click", () => {
        _zoomStack = _zoomStack.slice(0, i);
        const focused = c.path ? findNode(_treeData, c.path) : _treeData;
        if (focused) renderTreemap(focused);
      });
    }
    nav.appendChild(span);
  });
}

// ── Search ────────────────────────────────────────────────────────────────

function runSearch() {
  const raw = document.getElementById("search-input").value.trim();
  const useRegex = document.getElementById("search-regex").checked;
  const input = document.getElementById("search-input");
  let test;
  if (!raw) {
    test = () => true;
    input.classList.remove("search-invalid");
  } else if (useRegex) {
    try {
      const re = new RegExp(raw, "i");
      test = path => re.test(path);
      input.classList.remove("search-invalid");
    } catch {
      input.classList.add("search-invalid");
      return;
    }
  } else {
    const q = raw.toLowerCase();
    test = path => path.toLowerCase().includes(q);
    input.classList.remove("search-invalid");
  }
  document.querySelectorAll("g.node").forEach(n => {
    n.classList.toggle("dimmed", !test(n.dataset.path || ""));
  });
}

document.getElementById("search-input").addEventListener("input", runSearch);
document.getElementById("search-regex").addEventListener("change", runSearch);

// ── Context menu ──────────────────────────────────────────────────────────

const ctxMenu = document.getElementById("ctx-menu");
let _ctxTarget = null;

function showContextMenu(x, y, nodeData) {
  _ctxTarget = nodeData;
  const isMulti = _selection.size > 1 && _selection.has(nodeData.path);
  const n = _selection.size;

  // Single-item actions — visible only in single mode
  ctxMenu.querySelector("[data-action='info']").style.display = isMulti ? "none" : "";
  ctxMenu.querySelector("[data-action='delete']").style.display = isMulti ? "none" : "";
  ctxMenu.querySelector("[data-action='move']").style.display = isMulti ? "none" : "";

  // Multi-select actions
  const divider = document.getElementById("ctx-sel-divider");
  const delSel = ctxMenu.querySelector("[data-action='delete-selected']");
  const copyPaths = ctxMenu.querySelector("[data-action='copy-paths']");

  divider.style.display = isMulti ? "" : "none";
  copyPaths.style.display = isMulti ? "" : "none";
  // delete-selected respects write permission
  delSel.style.display = (isMulti && allowWrite) ? "" : "none";

  if (isMulti) {
    delSel.textContent = `Delete ${n} selected`;
    copyPaths.textContent = `Copy ${n} paths`;
  } else {
    ctxMenu.querySelector("[data-action='info']").textContent = nodeData.is_dir ? "Folder info" : "File info";
  }

  ctxMenu.style.left = `${x + 2}px`;
  ctxMenu.style.top = `${y + 2}px`;
  ctxMenu.classList.remove("hidden");
  requestAnimationFrame(() => {
    const r = ctxMenu.getBoundingClientRect();
    if (r.right > window.innerWidth) ctxMenu.style.left = `${x - r.width}px`;
    if (r.bottom > window.innerHeight) ctxMenu.style.top = `${y - r.height}px`;
  });
}

function hideContextMenu() { ctxMenu.classList.add("hidden"); _ctxTarget = null; }

document.addEventListener("click", () => hideContextMenu());
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { hideContextMenu(); hideInfoPanel(); clearSelection(); }
  if (e.key === "Backspace" && _zoomStack.length > 0 && document.activeElement === document.body) {
    e.preventDefault(); zoomOut();
  }
});

ctxMenu.addEventListener("click", async e => {
  const li = e.target.closest("li[data-action]");
  if (!li || !_ctxTarget) return;
  const action = li.dataset.action;
  const target = _ctxTarget;
  hideContextMenu();
  if (action === "info") {
    showInfoPanel(target);
  } else if (action === "delete") {
    if (!confirm(`Delete "${target.name}"? This cannot be undone.`)) return;
    const res = await apiOperation({ op: "delete", path: target.path });
    if (res.ok) await refreshTree(); else alert(`Error: ${res.message}`);
  } else if (action === "move") {
    const dest = prompt(`Move "${target.name}" to (absolute path):`);
    if (!dest) return;
    const res = await apiOperation({ op: "move", path: target.path, dest });
    if (res.ok) await refreshTree(); else alert(`Error: ${res.message}`);
  } else if (action === "delete-selected") {
    const paths = [..._selection];
    if (!confirm(`Delete ${paths.length} selected items? This cannot be undone.`)) return;
    const errors = [];
    for (const p of paths) {
      const res = await apiOperation({ op: "delete", path: p });
      if (!res.ok) errors.push(`${p}: ${res.message}`);
    }
    clearSelection();
    await refreshTree();
    if (errors.length) alert(`Some deletions failed:\n${errors.join("\n")}`);
  } else if (action === "copy-paths") {
    await navigator.clipboard.writeText([..._selection].join("\n"));
  }
});

async function apiOperation(body) {
  const resp = await fetch("/api/operation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return resp.json();
}

// ── Info panel ────────────────────────────────────────────────────────────

const infoPanel = document.getElementById("info-panel");
document.getElementById("info-close").addEventListener("click", hideInfoPanel);

function showInfoPanel(nodeData) {
  document.getElementById("info-name").textContent = nodeData.name;
  const dl = document.getElementById("info-details");
  dl.innerHTML = "";
  [
    ["Type", nodeData.is_dir ? "Directory" : `File (${nodeData.extension || "no ext"})`],
    ["Size", nodeData.display_size],
    ["Path", nodeData.path],
  ].forEach(([k, v]) => {
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); dd.textContent = v;
    dl.appendChild(dt); dl.appendChild(dd);
  });
  infoPanel.classList.remove("hidden");
}

function hideInfoPanel() { infoPanel.classList.add("hidden"); }

// ── Data fetching ─────────────────────────────────────────────────────────

function buildTreeUrl() {
  const p = new URLSearchParams();
  if (settings.depth !== null) p.set("depth", settings.depth);
  if (settings.logScale > 1) p.set("log_scale", String(settings.logScale));
  if (settings.colormap !== "tab20") p.set("colormap", settings.colormap);
  for (const e of settings.exclude) if (e.trim()) p.append("exclude", e.trim());
  for (const i of settings.include) if (i.trim()) p.append("include", i.trim());
  const qs = p.toString();
  return "/api/tree" + (qs ? "?" + qs : "");
}

function treeDepth(node, d = 0) {
  if (!node.children || node.children.length === 0) return d;
  return Math.max(...node.children.map(c => treeDepth(c, d + 1)));
}

let _knownMaxDepth = 0;  // highest depth ever seen; never shrinks

function syncDepthSlider(data) {
  const slider = document.getElementById("s-depth");
  _knownMaxDepth = Math.max(_knownMaxDepth, treeDepth(data));
  slider.max = _knownMaxDepth;
}

async function fetchTree() {
  const resp = await fetch(buildTreeUrl());
  return resp.json();
}

async function refreshTree() {
  document.getElementById("loading").classList.remove("hidden");
  try {
    const data = await fetchTree();
    _treeData = data;
    syncDepthSlider(data);
    // try to keep zoom if the path still exists
    while (_zoomStack.length > 0 && !findNode(_treeData, _zoomStack[_zoomStack.length - 1])) {
      _zoomStack.pop();
    }
    const focused = _zoomStack.length ? findNode(_treeData, _zoomStack[_zoomStack.length - 1]) : _treeData;
    renderTreemap(focused || _treeData);
  } finally {
    document.getElementById("loading").classList.add("hidden");
  }
}

// ── WebSocket live updates ────────────────────────────────────────────────

function setupWebSocket() {
  const wsUrl = `ws://${location.host}/ws`;
  let retryDelay = 1000;

  function connect() {
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => { retryDelay = 1000; };
    ws.onmessage = async () => { await refreshTree(); };
    ws.onclose = () => { setTimeout(() => { retryDelay = Math.min(retryDelay * 2, 10000); connect(); }, retryDelay); };
  }
  connect();
}

// ── Resize ────────────────────────────────────────────────────────────────

const _resizeObs = new ResizeObserver(() => {
  if (!_treeData) return;
  const focused = _zoomStack.length ? findNode(_treeData, _zoomStack[_zoomStack.length - 1]) : _treeData;
  renderTreemap(focused || _treeData);
});
_resizeObs.observe(document.getElementById("treemap-container"));

// ── Sidebar tabs ──────────────────────────────────────────────────────────

let _activeTab = "settings";
let _metricsLoaded = false;

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

function switchTab(name) {
  _activeTab = name;
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("hidden", p.id !== `tab-${name}`));
  if (name === "metrics" && !_metricsLoaded) loadMetrics();
}

// ── Metrics ───────────────────────────────────────────────────────────────

function fmtBytes(n) {
  for (const [u, t] of [["TB", 1e12], ["GB", 1e9], ["MB", 1e6], ["KB", 1e3]]) {
    if (n >= t) return (n / t).toFixed(1) + " " + u;
  }
  return n + " B";
}

async function loadMetrics() {
  const el = document.getElementById("metrics-content");
  el.innerHTML = '<span class="text-dim">Computing…</span>';
  try {
    const m = await fetch("/api/metrics").then(r => r.json());
    _metricsLoaded = true;
    el.innerHTML = renderMetricsHTML(m);
  } catch (e) {
    el.innerHTML = `<span class="text-dim">Error: ${e.message}</span>`;
  }
}

function renderMetricsHTML(m) {
  const kv = (k, v) => `<div class="metrics-kv"><span class="mk">${k}</span><span class="mv">${v}</span></div>`;
  const n = v => Number(v).toLocaleString();

  let html = `<div class="metrics-section">
    ${kv("Files", n(m.files))}
    ${kv("Dirs", n(m.dirs) + (m.empty_dirs ? ` <span style="opacity:.6">(${n(m.empty_dirs)} empty)</span>` : ""))}
    ${kv("Total size", fmtBytes(m.total_size_bytes))}
    ${kv("Depth", m.depth)}
    ${kv("Scan time", m.scan_time_s.toFixed(2) + "s")}
  </div>`;

  if (m.top_extensions?.length) {
    html += `<div class="metrics-section"><h3>Top extensions</h3>
      <table class="metrics-table">`;
    for (const e of m.top_extensions) {
      html += `<tr>
        <td>${e.ext || "(no ext)"}</td>
        <td class="num">${n(e.count)}</td>
        <td class="num">${fmtBytes(e.size_bytes)}</td>
      </tr>`;
    }
    html += `</table></div>`;
  }

  if (m.largest_files?.length) {
    html += `<div class="metrics-section"><h3>Largest files</h3>
      <table class="metrics-table">`;
    for (const f of m.largest_files) {
      const name = f.path.split("/").pop();
      html += `<tr>
        <td class="num">${fmtBytes(f.size_bytes)}</td>
        <td class="num" style="color:var(--text-dim)">${f.pct.toFixed(1)}%</td>
        <td title="${f.path}">${name}</td>
      </tr><tr><td colspan="3" class="mpath">${f.path}</td></tr>`;
    }
    html += `</table></div>`;
  }

  if (m.largest_dirs?.length) {
    html += `<div class="metrics-section"><h3>Largest dirs</h3>
      <table class="metrics-table">`;
    for (const d of m.largest_dirs) {
      html += `<tr>
        <td class="num">${fmtBytes(d.size_bytes)}</td>
        <td class="num" style="color:var(--text-dim)">${d.pct.toFixed(1)}%</td>
        <td class="mpath">${d.path}</td>
      </tr>`;
    }
    html += `</table></div>`;
  }

  return html;
}

// ── File preview ──────────────────────────────────────────────────────────

function _buildMetaTable(meta) {
  const table = document.createElement("table");
  table.className = "preview-meta";
  const order = ["Date", "Software", "Command", "Python", "OS", "URL"];
  const keys = [...order.filter(k => k in meta), ...Object.keys(meta).filter(k => !order.includes(k))];
  for (const key of keys) {
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.textContent = key;
    const td = document.createElement("td");
    td.textContent = meta[key];
    tr.appendChild(th);
    tr.appendChild(td);
    table.appendChild(tr);
  }
  return table;
}

async function previewFile(nodeData) {
  const header = document.getElementById("preview-header");
  const content = document.getElementById("preview-content");
  header.textContent = nodeData.path;
  header.classList.remove("hidden");
  content.innerHTML = '<span class="text-dim">Loading…</span>';

  try {
    const res = await fetch(`/api/file?path=${encodeURIComponent(nodeData.path)}`);
    const data = await res.json();
    if (data.error) {
      content.innerHTML = `<span class="text-dim">${data.error}</span>`;
    } else if (data.type === "image") {
      content.innerHTML = `<img src="data:${data.mime};base64,${data.data}" alt="${nodeData.name}">`;
      if (data.meta && Object.keys(data.meta).length > 0) content.appendChild(_buildMetaTable(data.meta));
    } else if (data.type === "video") {
      const vid = document.createElement("video");
      vid.controls = true;
      vid.src = `/api/file-stream?path=${encodeURIComponent(nodeData.path)}`;
      content.innerHTML = "";
      content.appendChild(vid);
      if (data.meta && Object.keys(data.meta).length > 0) content.appendChild(_buildMetaTable(data.meta));
    } else if (data.type === "pdf") {
      const iframe = document.createElement("iframe");
      iframe.src = `/api/file-stream?path=${encodeURIComponent(nodeData.path)}`;
      iframe.className = "preview-pdf";
      content.innerHTML = "";
      content.appendChild(iframe);
    } else if (data.type === "text") {
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = data.content;
      if (data.extension && typeof hljs !== "undefined") {
        const lang = hljs.getLanguage(data.extension.slice(1));
        if (lang) {
          code.className = `language-${data.extension.slice(1)}`;
          hljs.highlightElement(code);
        } else {
          hljs.highlightElement(code);
        }
      }
      pre.appendChild(code);
      content.innerHTML = "";
      content.appendChild(pre);
    } else if (data.type === "binary" && data.preview) {
      const pre = document.createElement("pre");
      pre.className = "binary-hex";
      pre.textContent = data.preview;
      content.innerHTML = "";
      if (data.truncated) {
        const note = document.createElement("div");
        note.className = "text-dim binary-truncated";
        note.textContent = "Showing first 1000 bytes.";
        content.appendChild(note);
      }
      content.appendChild(pre);
    } else {
      content.innerHTML = '<span class="text-dim">Binary file — no preview available.</span>';
    }
  } catch (e) {
    content.innerHTML = `<span class="text-dim">Error: ${e.message}</span>`;
  }
}

// Update hljs theme when dark/light mode changes
function syncHljsTheme() {
  const dark = settings.darkMode;
  document.getElementById("hljs-theme").href = dark
    ? "https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11/styles/atom-one-dark.min.css"
    : "https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11/styles/atom-one-light.min.css";
}

// ── Sidebar ───────────────────────────────────────────────────────────────

const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebarResizer = document.getElementById("sidebar-resizer");

const SIDEBAR_COLLAPSED_W = 32 + 4;  // toggle btn + resizer
let _sidebarW = 300;  // current expanded width (px)
let _sidebarCollapsed = true;

function setSidebarWidth(w) {
  sidebar.style.width = w + "px";
}

function reflow() {
  if (!_treeData) return;
  const focused = _zoomStack.length ? findNode(_treeData, _zoomStack[_zoomStack.length - 1]) : _treeData;
  renderTreemap(focused || _treeData);
}

// Initialise collapsed
setSidebarWidth(SIDEBAR_COLLAPSED_W);
sidebar.classList.add("collapsed");

sidebarToggle.addEventListener("click", () => {
  _sidebarCollapsed = !_sidebarCollapsed;
  sidebar.classList.toggle("collapsed", _sidebarCollapsed);
  sidebarToggle.setAttribute("aria-expanded", String(!_sidebarCollapsed));
  setSidebarWidth(_sidebarCollapsed ? SIDEBAR_COLLAPSED_W : _sidebarW);
  setTimeout(reflow, 240);  // after CSS transition
});

// ── Resizer drag ──────────────────────────────────────────────────────────

let _dragging = false, _dragStartX = 0, _dragStartW = 0;

sidebarResizer.addEventListener("mousedown", e => {
  e.preventDefault();
  _dragging = true;
  _dragStartX = e.clientX;
  _dragStartW = _sidebarCollapsed ? SIDEBAR_COLLAPSED_W : _sidebarW;
  sidebarResizer.classList.add("dragging");
  document.body.style.userSelect = "none";
  document.body.style.cursor = "col-resize";
});

document.addEventListener("mousemove", e => {
  if (!_dragging) return;
  const delta = _dragStartX - e.clientX;  // drag left = wider sidebar
  const newW = Math.max(180, Math.min(700, _dragStartW + delta));
  _sidebarW = newW;
  if (_sidebarCollapsed && newW > SIDEBAR_COLLAPSED_W + 20) {
    // auto-expand when dragged open
    _sidebarCollapsed = false;
    sidebar.classList.remove("collapsed");
    sidebarToggle.setAttribute("aria-expanded", "true");
  }
  if (!_sidebarCollapsed) setSidebarWidth(newW);
  reflow();
});

document.addEventListener("mouseup", () => {
  if (!_dragging) return;
  _dragging = false;
  sidebarResizer.classList.remove("dragging");
  document.body.style.userSelect = "";
  document.body.style.cursor = "";
});

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

async function _serverRefresh() {
  _zoomStack = []; _metricsLoaded = false;
  await refreshTree();
}
const _scheduleRefresh = debounce(_serverRefresh, 600);

// Slider live display
function bindSlider(id, valId, suffix, onChange) {
  const slider = document.getElementById(id);
  const display = document.getElementById(valId);
  slider.addEventListener("input", () => {
    display.textContent = slider.value + (suffix || "");
    if (onChange) onChange(Number(slider.value));
  });
}

bindSlider("s-depth", "s-depth-val", "", v => {
  settings.depth = v;
  _scheduleRefresh();
});
bindSlider("s-font-size", "s-font-size-val", "px", v => {
  settings.fontSize = v;
  if (_treeData) {
    const focused = _zoomStack.length ? findNode(_treeData, _zoomStack[_zoomStack.length - 1]) : _treeData;
    renderTreemap(focused || _treeData);
  }
});

// Depth "unlimited" button
document.getElementById("s-depth-reset").addEventListener("click", async () => {
  settings.depth = null;
  document.getElementById("s-depth-val").textContent = "∞";
  await _serverRefresh();
});

// Canvas reset
document.getElementById("s-canvas-reset").addEventListener("click", () => {
  settings.canvasW = null;
  settings.canvasH = null;
  document.getElementById("s-canvas-w").value = "";
  document.getElementById("s-canvas-h").value = "";
  applyCanvasSize();
  if (_treeData) {
    const focused = _zoomStack.length ? findNode(_treeData, _zoomStack[_zoomStack.length - 1]) : _treeData;
    renderTreemap(focused || _treeData);
  }
});

// Canvas inputs — client-side, re-render immediately
["s-canvas-w", "s-canvas-h"].forEach(id => {
  document.getElementById(id).addEventListener("change", () => {
    settings.canvasW = Number(document.getElementById("s-canvas-w").value) || null;
    settings.canvasH = Number(document.getElementById("s-canvas-h").value) || null;
    applyCanvasSize();
    if (_treeData) {
      const focused = _zoomStack.length ? findNode(_treeData, _zoomStack[_zoomStack.length - 1]) : _treeData;
      renderTreemap(focused || _treeData);
    }
  });
});

// Dark mode toggle — client-side only, re-render immediately
document.getElementById("s-dark-mode").addEventListener("change", e => {
  settings.darkMode = e.target.checked;
  document.body.classList.toggle("light", !settings.darkMode);
  syncHljsTheme();
  if (_treeData) {
    const focused = _zoomStack.length ? findNode(_treeData, _zoomStack[_zoomStack.length - 1]) : _treeData;
    renderTreemap(focused || _treeData);
  }
});

// Log scale slider — re-fetch on change
document.getElementById("s-log-scale").addEventListener("input", e => {
  const v = Number(e.target.value);
  settings.logScale = v;
  document.getElementById("s-log-scale-val").textContent = v === 1 ? "off" : String(v);
  _scheduleRefresh();
});

// Colormap — re-fetch immediately on change
document.getElementById("s-colormap").addEventListener("change", e => {
  settings.colormap = e.target.value;
  _serverRefresh();
});

// Parse highlight lines  e.g. "**/*.py@orange"
function parseHighlights(text) {
  return text.split("\n")
    .map(l => l.trim())
    .filter(l => l && l.includes("@"))
    .map(l => {
      const at = l.lastIndexOf("@");
      return { glob: l.slice(0, at).trim(), color: l.slice(at + 1).trim() };
    });
}

// Textareas — debounced re-fetch
document.getElementById("s-exclude").addEventListener("input", () => {
  settings.exclude = document.getElementById("s-exclude").value.split("\n").map(l => l.trim()).filter(Boolean);
  _scheduleRefresh();
});
document.getElementById("s-include").addEventListener("input", () => {
  settings.include = document.getElementById("s-include").value.split("\n").map(l => l.trim()).filter(Boolean);
  _scheduleRefresh();
});
document.getElementById("s-highlight").addEventListener("input", () => {
  settings.highlights = parseHighlights(document.getElementById("s-highlight").value);
  _scheduleRefresh();
});

// Reset all
document.getElementById("s-reset-all").addEventListener("click", async () => {
  settings.depth = _initialConfig.depth;
  settings.darkMode = true;
  settings.logScale = 4;
  settings.fontSize = 12;
  settings.colormap = _initialConfig.colormap;
  settings.canvasW = null;
  settings.canvasH = null;
  settings.exclude = [];
  settings.include = [];
  settings.highlights = [];

  // Reset form
  const depthVal = settings.depth || 6;
  document.getElementById("s-depth").value = depthVal;
  document.getElementById("s-depth-val").textContent = settings.depth || "∞";
  document.getElementById("s-dark-mode").checked = true;
  document.body.classList.remove("light");
  document.getElementById("s-log-scale").value = 4;
  document.getElementById("s-log-scale-val").textContent = "4";
  document.getElementById("s-font-size").value = 12;
  document.getElementById("s-font-size-val").textContent = "12px";
  document.getElementById("s-colormap").value = _initialConfig.colormap;
  document.getElementById("s-canvas-w").value = "";
  document.getElementById("s-canvas-h").value = "";
  document.getElementById("s-exclude").value = _initialConfig.exclude.join("\n");
  document.getElementById("s-include").value = "";
  document.getElementById("s-highlight").value = "";

  applyCanvasSize();
  _zoomStack = []; _metricsLoaded = false;
  await refreshTree();
});

// ── Init ──────────────────────────────────────────────────────────────────

let _initialConfig = { depth: null, colormap: "tab20", exclude: [] };

async function initSidebar(cfg) {
  _initialConfig = cfg;

  // Populate colormap dropdown
  const sel = document.getElementById("s-colormap");
  sel.innerHTML = "";
  for (const cm of cfg.colormaps) {
    const opt = document.createElement("option");
    opt.value = cm;
    opt.textContent = cm + (cm === "tab20" ? " (default)" : "");
    if (cm === cfg.colormap) opt.selected = true;
    sel.appendChild(opt);
  }

  // Seed settings from config
  settings.depth = cfg.depth;
  settings.colormap = cfg.colormap;
  settings.exclude = cfg.exclude;

  // Seed form
  const depthVal = cfg.depth || 6;
  document.getElementById("s-depth").value = depthVal;
  document.getElementById("s-depth-val").textContent = cfg.depth ? String(cfg.depth) : "∞";
  document.getElementById("s-exclude").value = cfg.exclude.join("\n");
}

(async () => {
  try {
    const [cfg, data] = await Promise.all([
      fetch("/api/config").then(r => r.json()),
      fetch(buildTreeUrl()).then(r => r.json()),
    ]);
    await initSidebar(cfg);
    _treeData = data;
    syncDepthSlider(data);
    document.getElementById("loading").classList.add("hidden");
    renderTreemap(_treeData);
    setupWebSocket();
  } catch (err) {
    document.getElementById("loading").textContent = `Error: ${err.message}`;
  }
})();
