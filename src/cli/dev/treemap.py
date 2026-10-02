# file: src/cli/dev/treemap.py
# Version: 3.0.0
"""Interactive dependency treemap.

Scans a project directory (respecting .gitignore), builds a rectangular D3
treemap sized by file bytes and coloured by GitHub Linguist language colours,
and overlays import dependencies (Python, JS/TS) for the hovered / pinned file.

Usage:
    python treemap.py [PROJECT_DIR] [-o OUTPUT.html] [--no-open]
"""

import argparse
import ast
import json
import posixpath
import re
import sys
import webbrowser
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Set, Tuple

try:
    import pathspec
except ImportError:
    print("[x] Required dependency 'pathspec' is missing.")
    print("    Install it via: pip install pathspec")
    sys.exit(1)

VERSION = "3.0.0"
OUTPUT_NAME = "dependency_treemap.html"

# --------------------------------------------------------------------------
# Language classification (GitHub Linguist colours, keyed by language)
# --------------------------------------------------------------------------

LANGUAGE_COLORS: Dict[str, str] = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Go": "#00ADD8", "Rust": "#dea584", "C": "#555555", "C++": "#f34b7d",
    "Java": "#b07219", "C#": "#178600", "Ruby": "#701516", "PHP": "#4F5D95",
    "Swift": "#F05138", "Kotlin": "#A97BFF", "Shell": "#89e051",
    "Batchfile": "#C1F12E", "PowerShell": "#012456", "Lua": "#000080",
    "HTML": "#e34c26", "CSS": "#563d7c", "SCSS": "#c6538c", "Vue": "#41b883",
    "Svelte": "#ff3e00", "JSON": "#292929", "YAML": "#cb171e",
    "TOML": "#9c4221", "XML": "#0060ac", "Markdown": "#083fa1",
    "SQL": "#e38c00", "INI": "#d1d1d1", "Dockerfile": "#384d54",
    "Makefile": "#427819",
}
OTHER_COLOR = "#8b949e"

_LANGUAGE_EXTENSIONS: Dict[str, List[str]] = {
    "Python": [".py", ".pyi", ".pyw"],
    "JavaScript": [".js", ".mjs", ".cjs", ".jsx"],
    "TypeScript": [".ts", ".mts", ".cts", ".tsx"],
    "Go": [".go"], "Rust": [".rs"],
    "C": [".c", ".h"],  # Linguist treats .h as C unless heuristics say C++
    "C++": [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"],
    "Java": [".java"], "C#": [".cs"], "Ruby": [".rb"], "PHP": [".php"],
    "Swift": [".swift"], "Kotlin": [".kt", ".kts"],
    "Shell": [".sh", ".bash", ".zsh"], "Batchfile": [".bat", ".cmd"],
    "PowerShell": [".ps1", ".psm1"], "Lua": [".lua"],
    "HTML": [".html", ".htm"], "CSS": [".css"], "SCSS": [".scss"],
    "Vue": [".vue"], "Svelte": [".svelte"],
    "JSON": [".json", ".jsonc"], "YAML": [".yaml", ".yml"],
    "TOML": [".toml"], "XML": [".xml"], "Markdown": [".md", ".markdown"],
    "SQL": [".sql"], "INI": [".ini"],
}
EXT_TO_LANGUAGE = {e: lang for lang, exts in _LANGUAGE_EXTENSIONS.items() for e in exts}
FILENAME_TO_LANGUAGE = {"dockerfile": "Dockerfile", "makefile": "Makefile"}


def classify(path: Path) -> Tuple[str, str]:
    lang = FILENAME_TO_LANGUAGE.get(path.name.lower()) or EXT_TO_LANGUAGE.get(path.suffix.lower())
    if lang:
        return lang, LANGUAGE_COLORS[lang]
    return "Other", OTHER_COLOR


# --------------------------------------------------------------------------
# Scanning
# --------------------------------------------------------------------------

DEFAULT_IGNORES = [
    ".git/", "__pycache__/", "*.pyc", "node_modules/", ".venv/", "venv/",
    ".mypy_cache/", ".pytest_cache/", "*.png", "*.jpg", "*.jpeg", "*.gif",
    "*.ico", OUTPUT_NAME,
]


def load_gitignore_spec(root_dir: Path) -> pathspec.PathSpec:
    patterns = list(DEFAULT_IGNORES)
    gitignore = root_dir / ".gitignore"
    if gitignore.is_file():
        try:
            patterns.extend(gitignore.read_text(encoding="utf-8").splitlines())
        except OSError as err:
            print(f"[!] Warning reading .gitignore: {err}")
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def scan_tree(root_dir: Path, spec: pathspec.PathSpec) -> Tuple[dict, Set[str]]:
    """Returns (hierarchy, set of posix relative file paths). Root id is ''."""
    files: Set[str] = set()

    def walk(path: Path) -> Optional[dict]:
        rel = path.relative_to(root_dir).as_posix()
        rel = "" if rel == "." else rel

        if path.is_file():
            try:
                size = path.stat().st_size
            except OSError:
                return None
            lang, color = classify(path)
            files.add(rel)
            return {"name": path.name, "id": rel, "value": max(1, size),
                    "color": color, "lang": lang}

        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            entries = []

        children = []
        for entry in entries:
            if entry.is_symlink():
                continue
            rel_entry = entry.relative_to(root_dir).as_posix()
            if spec.match_file(f"{rel_entry}/" if entry.is_dir() else rel_entry):
                continue
            child = walk(entry)
            if child:
                children.append(child)

        if not children and path != root_dir:
            return None  # drop empty directories
        return {"name": path.name if path != root_dir else root_dir.name,
                "id": rel, "children": children}

    return walk(root_dir), files


# --------------------------------------------------------------------------
# Dependency resolution
# --------------------------------------------------------------------------

def _module_file(parts: List[str], file_set: Set[str]) -> Optional[str]:
    base = "/".join(parts)
    candidates = (f"{base}.py", f"{base}/__init__.py") if parts else ("__init__.py",)
    return next((c for c in candidates if c in file_set), None)


def build_python_index(file_set: Set[str]) -> Dict[str, str]:
    """Dotted module name -> file. Supports src-layout style source roots."""
    py_files = sorted(f for f in file_set if f.endswith(".py"))
    roots = {""}
    for rel in py_files:
        parts = rel.split("/")
        if (len(parts) >= 3
                and f"{parts[0]}/__init__.py" not in file_set
                and f"{parts[0]}/{parts[1]}/__init__.py" in file_set):
            roots.add(parts[0])

    index: Dict[str, str] = {}
    for prefix in sorted(roots):  # "" first, so top-level layout wins
        for rel in py_files:
            if prefix:
                if not rel.startswith(prefix + "/"):
                    continue
                sub = rel[len(prefix) + 1:]
            else:
                sub = rel
            parts = sub[:-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            if parts:
                index.setdefault(".".join(parts), rel)
    return index


def python_targets(rel: str, path: Path, index: Dict[str, str], file_set: Set[str]) -> Set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, ValueError, OSError):
        return set()

    dir_parts = list(PurePosixPath(rel).parent.parts)
    targets: Set[str] = set()

    def lookup(dotted: str) -> Optional[str]:
        # Exact project module, else sibling of the importing file (script style).
        return index.get(dotted) or _module_file(dir_parts + dotted.split("."), file_set)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                hit = lookup(alias.name)
                if hit:
                    targets.add(hit)

        elif isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names if a.name != "*"]
            if node.level:  # relative import: resolve by file path
                up = node.level - 1
                if up > len(dir_parts):
                    continue
                base = dir_parts[:len(dir_parts) - up]
                mod_parts = node.module.split(".") if node.module else []
                subs = [h for n in names
                        if (h := _module_file(base + mod_parts + [n], file_set))]
                if subs:
                    targets.update(subs)
                else:
                    hit = _module_file(base + mod_parts, file_set)
                    if hit:
                        targets.add(hit)
            elif node.module:
                subs = [h for n in names if (h := lookup(f"{node.module}.{n}"))]
                if subs:
                    targets.update(subs)
                else:
                    hit = lookup(node.module)
                    if hit:
                        targets.add(hit)

    targets.discard(rel)
    return targets


JS_EXTS = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts")
JS_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"](\.{1,2}/[^'"]*|\.{1,2})['"]"""
)


def js_targets(rel: str, path: Path, file_set: Set[str]) -> Set[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()

    targets: Set[str] = set()
    for spec_str in JS_IMPORT_RE.findall(text):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(rel), spec_str))
        if base.startswith(".."):
            continue
        stem = re.sub(r"\.(?:m|c)?jsx?$", "", base)  # TS ESM style './a.js' -> a.ts
        candidates = [base]
        for ext in JS_EXTS:
            candidates += [base + ext, stem + ext, f"{base}/index{ext}"]
        hit = next((c for c in candidates if c in file_set), None)
        if hit and hit != rel:
            targets.add(hit)
    return targets


def resolve_dependencies(root_dir: Path, file_set: Set[str]) -> List[dict]:
    index = build_python_index(file_set)
    links: Set[Tuple[str, str]] = set()
    for rel in sorted(file_set):
        suffix = PurePosixPath(rel).suffix.lower()
        path = root_dir / rel
        if suffix in (".py", ".pyi", ".pyw"):
            found = python_targets(rel, path, index, file_set)
        elif suffix in JS_EXTS:
            found = js_targets(rel, path, file_set)
        else:
            continue
        links.update((rel, t) for t in found)
    return [{"source": s, "target": t} for s, t in sorted(links)]


# --------------------------------------------------------------------------
# HTML view
# --------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<style>
  :root { --out:#ff4d4f; --in:#40a9ff; --both:#d29922; --accent:#38edf8; }
  html, body { margin:0; height:100%; background:#05070a; color:#f0f6fc;
    font:12px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow:hidden; }
  svg { display:block; }
  rect { vector-effect:non-scaling-stroke; }

  .folder rect { stroke:#4b5a6b; stroke-width:1px; }
  .folder rect:hover { stroke:var(--accent); }
  .folder text { fill:#9fb0c3; font-size:11px; font-weight:600; pointer-events:none; }

  .leaf rect { stroke:rgba(255,255,255,.16); stroke-width:1px; cursor:pointer; }
  .leaf text { font-size:10px; pointer-events:none; }
  .leaf { transition:opacity .12s; }
  .leaf.dim { opacity:.28; }
  .leaf.sel rect  { stroke:#fff; stroke-width:2.5px; }
  .leaf.out rect  { stroke:var(--out); stroke-width:2.5px; }
  .leaf.in rect   { stroke:var(--in); stroke-width:2.5px; }
  .leaf.both rect { stroke:var(--both); stroke-width:2.5px; }

  .dep-link { fill:none; stroke-width:1.8px; vector-effect:non-scaling-stroke; pointer-events:none; opacity:.95; }
  .dep-link.out { stroke:var(--out); } .dep-dot.out { fill:var(--out); }
  .dep-link.in  { stroke:var(--in); }  .dep-dot.in  { fill:var(--in); }
  .dep-link.both{ stroke:var(--both);} .dep-dot.both{ fill:var(--both); }
  .dep-dot { pointer-events:none; }

  .panel { position:absolute; background:rgba(13,17,23,.94); border:1px solid #30363d;
    border-radius:8px; padding:10px 14px; pointer-events:none; z-index:10; }
  #info { top:12px; left:12px; max-width:440px; border-color:var(--accent);
    box-shadow:0 0 14px rgba(56,237,248,.18); }
  #title { font-size:13px; font-weight:600; color:#58a6ff; word-break:break-all; margin-bottom:4px; }
  #body div { color:#8b949e; word-break:break-all; line-height:1.5; }
  #body .h-out { color:var(--out); font-weight:600; margin-top:4px; }
  #body .h-in { color:var(--in); font-weight:600; margin-top:4px; }
  #body .h-both { color:var(--both); font-weight:600; margin-top:4px; }
  #body .item { padding-left:10px; color:#c9d1d9; }
  #legend { bottom:12px; left:12px; }
  #legend div { display:flex; align-items:center; gap:8px; color:#c9d1d9; line-height:1.7; }
  #legend i { width:10px; height:10px; border-radius:2px; display:inline-block; border:1px solid rgba(255,255,255,.2); }
  #legend span { color:#8b949e; margin-left:auto; padding-left:12px; }
</style>
</head>
<body>
<div id="info" class="panel"><div id="title"></div><div id="body"></div></div>
<div id="legend" class="panel"></div>
<svg id="canvas"></svg>

<script>
const payload = __DATA__;

const DEFAULT_TITLE = "Hover a file or folder";
const DEFAULT_HINT = "Click a file to pin its dependencies. Scroll to zoom, drag to pan, Esc to unpin.";
const MAX_LIST = 8;

const fmtBytes = n => {
  const u = ["B", "KB", "MB", "GB"]; let i = 0;
  while (n >= 1024 && i < 3) { n /= 1024; i++; }
  return (i ? n.toFixed(n < 10 ? 1 : 0) : n) + " " + u[i];
};
const fit = (s, w, charW) => {
  const n = Math.floor(w / charW);
  if (n <= 1) return "";
  return s.length > n ? s.slice(0, Math.max(1, n - 1)) + "…" : s;
};
const cx = n => (n.x0 + n.x1) / 2, cy = n => (n.y0 + n.y1) / 2;
const push = (m, k, v) => { if (!m.has(k)) m.set(k, []); m.get(k).push(v); };

const outMap = new Map(), inMap = new Map();
payload.links.forEach(l => { push(outMap, l.source, l.target); push(inMap, l.target, l.source); });

const svg = d3.select("#canvas");
const gRoot = svg.append("g");
const infoTitle = document.getElementById("title");
const infoBody = document.getElementById("body");

let transform = d3.zoomIdentity;
let hovered = null, pinnedId = null;
let byId = new Map(), leafSel = null, linkG = null;

const zoom = d3.zoom().scaleExtent([1, 80]).on("zoom", e => {
  transform = e.transform;
  gRoot.attr("transform", transform);
  linkG && linkG.selectAll("circle").attr("r", 3.5 / transform.k);
});
svg.call(zoom).on("dblclick.zoom", null);
svg.on("click", () => { pinnedId = null; refresh(); });
window.addEventListener("keydown", e => { if (e.key === "Escape") { pinnedId = null; refresh(); } });

function setInfo(title, rows) {
  infoTitle.textContent = title;
  infoBody.replaceChildren();
  rows.forEach(([text, cls]) => {
    const d = document.createElement("div");
    d.textContent = text;
    if (cls) d.className = cls;
    infoBody.appendChild(d);
  });
}

function curve(a, b) {
  const ax = cx(a), ay = cy(a), bx = cx(b), by = cy(b);
  const dx = bx - ax, dy = by - ay;
  const qx = (ax + bx) / 2 - dy * 0.12, qy = (ay + by) / 2 + dx * 0.12;
  return `M${ax},${ay}Q${qx},${qy} ${bx},${by}`;
}

function listRows(header, cls, ids) {
  const rows = [[`${header} (${ids.length})`, cls]];
  ids.slice(0, MAX_LIST).forEach(id => rows.push([id, "item"]));
  if (ids.length > MAX_LIST) rows.push([`+ ${ids.length - MAX_LIST} more`, "item"]);
  return rows;
}

function refresh() {
  const active = hovered || (pinnedId !== null ? byId.get(pinnedId) : null);
  const isLeaf = !!active && !active.children;
  const id = isLeaf ? active.data.id : null;

  const outs = isLeaf ? (outMap.get(id) || []) : [];
  const ins = isLeaf ? (inMap.get(id) || []) : [];
  const inSet = new Set(ins);
  const both = new Set(outs.filter(o => inSet.has(o)));
  const outOnly = new Set(outs.filter(o => !both.has(o)));
  const inOnly = new Set(ins.filter(i => !both.has(i)));

  leafSel.attr("class", d => {
    if (!isLeaf) return "leaf";
    if (d === active) return "leaf sel";
    const k = d.data.id;
    if (both.has(k)) return "leaf both";
    if (outOnly.has(k)) return "leaf out";
    if (inOnly.has(k)) return "leaf in";
    return "leaf dim";
  });

  linkG.selectAll("*").remove();
  if (isLeaf) {
    [...outOnly].map(k => [k, "out"]).concat([...inOnly].map(k => [k, "in"]),
      [...both].map(k => [k, "both"])).forEach(([k, type]) => {
      const o = byId.get(k);
      if (!o) return;
      linkG.append("path").attr("class", `dep-link ${type}`).attr("d", curve(active, o));
      linkG.append("circle").attr("class", `dep-dot ${type}`)
        .attr("cx", cx(o)).attr("cy", cy(o)).attr("r", 3.5 / transform.k);
    });
  }

  if (!active) {
    setInfo(DEFAULT_TITLE, [[DEFAULT_HINT]]);
  } else if (isLeaf) {
    const rows = [[`${active.data.lang} · ${fmtBytes(active.data.value)}`]];
    if (outs.length) rows.push(...listRows("→ imports", "h-out", outs));
    if (ins.length) rows.push(...listRows("← imported by", "h-in", ins));
    if (both.size) rows.push(...listRows("⟲ circular with", "h-both", [...both]));
    if (!outs.length && !ins.length) rows.push(["No resolved internal dependencies"]);
    if (pinnedId === id && hovered === null) rows.push(["Pinned — click empty space or press Esc to release"]);
    setInfo(id, rows);
  } else {
    const n = active.leaves().length;
    setInfo(active.data.id || active.data.name,
      [[`Directory · ${n} file${n === 1 ? "" : "s"} · ${fmtBytes(active.value)}`]]);
  }
}

function buildLegend(leaves) {
  const bytes = new Map(); let total = 0;
  leaves.forEach(l => {
    const k = l.data.lang;
    const e = bytes.get(k) || { color: l.data.color, v: 0 };
    e.v += l.data.value; total += l.data.value; bytes.set(k, e);
  });
  const el = document.getElementById("legend");
  el.replaceChildren();
  [...bytes.entries()].sort((a, b) => b[1].v - a[1].v).slice(0, 10).forEach(([name, e]) => {
    const row = document.createElement("div");
    const sw = document.createElement("i"); sw.style.background = e.color;
    const label = document.createElement("div"); label.textContent = name; label.style.display = "inline";
    const pct = document.createElement("span"); pct.textContent = (100 * e.v / total).toFixed(1) + "%";
    row.append(sw, label, pct);
    el.appendChild(row);
  });
}

function render() {
  const width = window.innerWidth, height = window.innerHeight;
  svg.attr("width", width).attr("height", height);
  gRoot.selectAll("*").remove();

  const root = d3.hierarchy(payload.hierarchy)
    .sum(d => d.children ? 0 : d.value)
    .sort((a, b) => b.value - a.value);

  d3.treemap()
    .size([width, height])
    .round(true)
    .paddingOuter(5)
    .paddingInner(3)
    .paddingTop(20)(root);

  byId = new Map();
  root.descendants().forEach(d => byId.set(d.data.id, d));

  const maxDepth = Math.max(1, d3.max(root.descendants().filter(d => d.children), d => d.depth));
  const folderFill = d3.interpolateRgb("#0d1117", "#26333f");
  const w = d => Math.max(0, d.x1 - d.x0), h = d => Math.max(0, d.y1 - d.y0);

  // Folders: opaque, bordered, darker at the top and lighter as they nest.
  const folders = gRoot.append("g").selectAll("g")
    .data(root.descendants().filter(d => d.children)).join("g")
    .attr("class", "folder")
    .attr("transform", d => `translate(${d.x0},${d.y0})`);
  folders.append("rect").attr("width", w).attr("height", h)
    .attr("fill", d => folderFill(d.depth / maxDepth));
  folders.append("text").attr("x", 6).attr("y", 14)
    .text(d => fit(d.data.name + "/", w(d) - 10, 6.6));
  folders
    .on("mouseover", (e, d) => { e.stopPropagation(); hovered = d; refresh(); })
    .on("mouseout", () => { hovered = null; refresh(); });

  // Files
  leafSel = gRoot.append("g").selectAll("g")
    .data(root.leaves()).join("g")
    .attr("class", "leaf")
    .attr("transform", d => `translate(${d.x0},${d.y0})`);
  leafSel.append("rect").attr("width", w).attr("height", h).attr("fill", d => d.data.color);
  leafSel.append("text").attr("x", 4).attr("y", 12)
    .attr("fill", d => d3.lab(d.data.color).l > 62 ? "#0d1117" : "#f0f6fc")
    .text(d => h(d) > 15 ? fit(d.data.name, w(d) - 8, 5.8) : "");
  leafSel
    .on("mouseover", (e, d) => { e.stopPropagation(); hovered = d; refresh(); })
    .on("mouseout", () => { hovered = null; refresh(); })
    .on("click", (e, d) => {
      e.stopPropagation();
      pinnedId = pinnedId === d.data.id ? null : d.data.id;
      refresh();
    });

  linkG = gRoot.append("g");
  buildLegend(root.leaves());
  hovered = null;
  refresh();
}

let resizeTimer = null;
window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(render, 150); });
render();
</script>
</body>
</html>
"""


def generate_html_view(data: dict, output_path: Path) -> None:
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html_content = (HTML_TEMPLATE
                    .replace("__TITLE__", f"Dependency Treemap v{VERSION}")
                    .replace("__DATA__", payload))
    output_path.write_text(html_content, encoding="utf-8")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an interactive dependency treemap.")
    parser.add_argument("path", nargs="?", default=".", help="project directory (default: cwd)")
    parser.add_argument("-o", "--output", help=f"output HTML (default: <path>/{OUTPUT_NAME})")
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = parser.parse_args()

    root_dir = Path(args.path).resolve()
    if not root_dir.is_dir():
        print(f"[x] Not a directory: {root_dir}")
        sys.exit(1)

    spec = load_gitignore_spec(root_dir)
    print(f" Scanning {root_dir.name}: file tree & static imports...")
    hierarchy, files = scan_tree(root_dir, spec)
    links = resolve_dependencies(root_dir, files)

    output_html = Path(args.output).resolve() if args.output else root_dir / OUTPUT_NAME
    generate_html_view({"hierarchy": hierarchy, "links": links}, output_html)

    print(f"[+] {len(files)} files, {len(links)} dependency links")
    print(f"[+] Treemap written to: {output_html}")
    if not args.no_open:
        webbrowser.open(output_html.as_uri())


if __name__ == "__main__":
    main()
