# file: src/lib/project_graph.py
# description: builds a machine-readable map of a project -- every tracked
# file, the project files each one imports (and who imports it), third-party
# packages used, and the signatures of its functions/classes without their
# bodies. Pure functions, no I/O besides reading the project; shared by the
# code_map watcher and anything else (treemap, live viewer) that needs the
# project's wiring, so there is one import resolver instead of several.
#
# Output is plain JSON (see SCHEMA_VERSION): flat "files" map keyed by
# project-relative POSIX path (the extension in the key is the file type).
# ABSENCE MEANS EMPTY: a file entry only has the fields that have content, so
# an unanalyzed file (css, md, png...) is just `{}` and a missing "imports"
# means "imports nothing". Readers should use `entry.imports ?? []`.
#
# Per-file fields: size (bytes), doc, entry (true for runnable scripts:
# `__main__` guard or __main__.py), imports / imported_by (project files),
# external (third-party packages), symbols. Python is parsed with `ast` (exact). JS/TS/HTML use
# regexes -- good for imports and top-level declarations, not a parser.
#
# Symbols are public-only by default and compact: "sig" already carries
# params/returns/bases, so those structured fields appear only with
# detail=True. Constants are kept only when another file imports them by name
# (or they are in __all__). Private symbols (include_private=True) are marked
# "private": true instead of carrying a "public" flag.
#
# Rebuilding is cheap: pass the same `cache` dict on every call and only
# files whose mtime/size changed are re-parsed.

from __future__ import annotations

import ast
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path


_IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


SCHEMA_VERSION = 1

# Folders on PYTHONPATH: "src/cli/x.py" is imported as "cli.x".
SOURCE_ROOTS = ("src",)
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build"}

LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".html": "html", ".css": "css",
    ".md": "markdown", ".json": "json", ".bat": "batch", ".txt": "text",
}
ANALYZED = {"python", "javascript", "typescript", "html"}
JS_EXTS = (".js", ".mjs", ".jsx", ".ts", ".tsx")
_STDLIB = getattr(sys, "stdlib_module_names", frozenset())


# --------------------------------------------------------------------------
# File listing
# --------------------------------------------------------------------------

def list_project_files(root: Path) -> list[str]:
    """Sorted project-relative paths: committed + untracked-but-not-ignored
    (what `git status` cares about). Falls back to a plain walk without git."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, text=True, check=True, encoding="utf-8",
        )
        paths = [p for p in result.stdout.split("\0") if p and (root / p).is_file()]
        if paths:
            return sorted(paths)
    except (OSError, subprocess.CalledProcessError):
        pass
    found = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if path.is_file() and not any(part in SKIP_DIRS for part in rel.parts):
            found.append(rel.as_posix())
    return sorted(found)


# --------------------------------------------------------------------------
# Shared text helpers
# --------------------------------------------------------------------------

def _first_sentence(text: str, limit: int = 240) -> str:
    text = " ".join(text.split())
    m = re.search(r"(?<=[.!?])\s", text)
    if m:
        text = text[:m.start()]
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _header_description(lines: list[str], prefix: str) -> str | None:
    """First sentence of the "<prefix> description: ..." comment block at the
    top of a file (this project's convention), or None."""
    out: list[str] = []
    started = False
    for line in lines[:80]:
        s = line.strip()
        if not s.startswith(prefix):
            if not s and not started:
                continue
            break
        body = s[len(prefix):].strip()
        if not started:
            if body.lower().startswith("description:"):
                started = True
                out.append(body[len("description:"):].strip())
            continue
        if not body:
            break
        out.append(body)
    return _first_sentence(" ".join(out)) if out else None


def _is_public(name: str) -> bool:
    return not name.startswith("_") or name == "__init__"


# --------------------------------------------------------------------------
# Python
# --------------------------------------------------------------------------

def _param(arg: ast.arg, default: ast.expr | None, star: str | None = None) -> dict:
    p: dict = {"name": arg.arg}
    if star:
        p["star"] = star
    if arg.annotation is not None:
        p["type"] = ast.unparse(arg.annotation)
    if default is not None:
        p["default"] = ast.unparse(default)
    return p


def _params(args: ast.arguments) -> list[dict]:
    out = []
    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    for a, d in zip(positional, defaults):
        out.append(_param(a, d))
    if args.vararg:
        out.append(_param(args.vararg, None, "*"))
    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        out.append(_param(a, d))
    if args.kwarg:
        out.append(_param(args.kwarg, None, "**"))
    return out


def _doc_line(node: ast.AST) -> str | None:
    doc = ast.get_docstring(node)  # type: ignore[arg-type]
    if doc and doc.strip():
        return doc.strip().splitlines()[0].strip()
    return None


def _function_symbol(node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> dict:
    args_src = ast.unparse(node.args)
    params = _params(node.args)
    if kind == "method":
        if params and params[0]["name"] in ("self", "cls") and "star" not in params[0]:
            params = params[1:]
        args_src = re.sub(r"^(self|cls)\s*(,\s*|$)", "", args_src)
    returns = ast.unparse(node.returns) if node.returns is not None else None
    sym: dict = {
        "name": node.name,
        "kind": kind,
        "line": node.lineno,
        "public": _is_public(node.name),
        "sig": f"{node.name}({args_src})" + (f" -> {returns}" if returns else ""),
        "params": params,
    }
    if returns:
        sym["returns"] = returns
    if isinstance(node, ast.AsyncFunctionDef):
        sym["async"] = True
    decorators = [ast.unparse(d) for d in node.decorator_list]
    if decorators:
        sym["decorators"] = decorators
    doc = _doc_line(node)
    if doc:
        sym["doc"] = doc
    return sym


def _class_symbol(node: ast.ClassDef) -> dict:
    bases = [ast.unparse(b) for b in node.bases]
    sym: dict = {
        "name": node.name,
        "kind": "class",
        "line": node.lineno,
        "public": _is_public(node.name),
        "sig": f"class {node.name}" + (f"({', '.join(bases)})" if bases else ""),
    }
    if bases:
        sym["bases"] = bases
    doc = _doc_line(node)
    if doc:
        sym["doc"] = doc
    sym["members"] = [
        _function_symbol(n, "method")
        for n in node.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return sym


def _top_level(body: list[ast.stmt]):
    """Top-level statements, descending into if/try so conditional or
    fallback definitions (e.g. under `except ImportError:`) are seen."""
    for node in body:
        yield node
        if isinstance(node, ast.If):
            yield from _top_level(node.body)
            yield from _top_level(node.orelse)
        elif isinstance(node, ast.Try):
            yield from _top_level(node.body)
            for handler in node.handlers:
                yield from _top_level(handler.body)
            yield from _top_level(node.orelse)
            yield from _top_level(node.finalbody)


def _python_symbols(tree: ast.Module) -> list[dict]:
    symbols: list[dict] = []
    seen: set[tuple[str, str]] = set()
    all_names: set[str] | None = None

    def add(sym: dict) -> None:
        key = (sym["name"], sym["kind"])
        if key not in seen:
            seen.add(key)
            symbols.append(sym)

    for node in _top_level(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(_function_symbol(node, "function"))
        elif isinstance(node, ast.ClassDef):
            add(_class_symbol(node))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            for t in targets:
                if not isinstance(t, ast.Name):
                    continue
                if t.id == "__all__" and isinstance(value, (ast.List, ast.Tuple)):
                    all_names = {e.value for e in value.elts
                                 if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                elif re.fullmatch(r"[A-Z][A-Z0-9_]*", t.id):
                    sym = {"name": t.id, "kind": "const", "line": node.lineno,
                           "public": _is_public(t.id)}
                    if value is not None:
                        v = ast.unparse(value)
                        if len(v) <= 60 and "\n" not in v:
                            sym["value"] = v
                    add(sym)

    if all_names is not None:
        for sym in symbols:
            sym["public"] = sym["name"] in all_names
            sym["listed"] = sym["public"]  # internal: explicitly exported via __all__
    return sorted(symbols, key=lambda s: s["line"])


def _python_raw_imports(tree: ast.Module) -> list[dict]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append({"level": 0, "module": a.name, "names": []})
        elif isinstance(node, ast.ImportFrom):
            out.append({"level": node.level, "module": node.module,
                        "names": [a.name for a in node.names]})
    return out


def _is_entry(tree: ast.Module) -> bool:
    """True if the module has a top-level `if __name__ == "__main__":`."""
    for node in tree.body:
        test = node.test if isinstance(node, ast.If) else None
        if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in test.comparators)):
            return True
    return False


def _parse_python(text: str) -> dict | None:
    """Parsed facts about a Python file, or None on a syntax error (files are
    often mid-edit; the caller keeps the last good parse)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    doc = _header_description(text.splitlines(), "#")
    if not doc:
        module_doc = ast.get_docstring(tree)
        doc = _first_sentence(module_doc) if module_doc else None
    return {"lang": "python", "doc": doc, "raw": _python_raw_imports(tree),
            "symbols": _python_symbols(tree), "entry": _is_entry(tree)}


def _python_modules(py_paths: list[str]) -> tuple[dict[str, str], dict[str, tuple[str, bool]]]:
    """index: dotted module name -> file; module_of: file -> (dotted, is_package)."""
    index: dict[str, str] = {}
    module_of: dict[str, tuple[str, bool]] = {}
    for p in py_paths:
        parts = p[:-3].split("/")
        is_pkg = parts[-1] == "__init__"
        if is_pkg:
            parts = parts[:-1]
        if not parts:
            continue
        stripped = parts[1:] if parts[0] in SOURCE_ROOTS and len(parts) > 1 else parts
        module_of[p] = (".".join(stripped), is_pkg)
        index.setdefault(".".join(stripped), p)
        index.setdefault(".".join(parts), p)
    return index, module_of


def _longest_prefix(dotted: str, lookup) -> str | None:
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        hit = lookup(".".join(parts[:i]))
        if hit:
            return hit
    return None


def _resolve_python(raw: list[dict], own: str, index: dict[str, str],
                    module_of: dict[str, tuple[str, bool]],
                    files: set[str]) -> tuple[set[str], set[str], dict[str, set[str]]]:
    """(project files imported, third-party top-level packages imported,
    {file: names imported from it by `from x import name`}).

    `from pkg import a, b` links to the submodules a/b when they are files;
    only otherwise does it link to pkg itself (its __init__.py).
    """
    internal: set[str] = set()
    external: set[str] = set()
    used: dict[str, set[str]] = {}
    project_tops = {m.split(".")[0] for m in index}  # unresolved but project-local names
    own_mod, own_is_pkg = module_of.get(own, ("", False))
    own_dir = own.split("/")[:-1]

    def absolute_lookup(dotted: str) -> str | None:
        """Scripts started by path can import their neighbours: look in the
        module index first, then relative to the importing file's folder."""
        hit = index.get(dotted)
        if hit or not dotted:
            return hit
        base = "/".join(own_dir + dotted.split("."))
        return next((c for c in (f"{base}.py", f"{base}/__init__.py") if c in files), None)

    for imp in raw:
        level, module, names = imp["level"], imp["module"], imp["names"]
        if level:
            pkg = own_mod.split(".") if own_mod else []
            if not own_is_pkg and pkg:
                pkg = pkg[:-1]
            pkg = pkg[: max(len(pkg) - (level - 1), 0)]
            base = ".".join(pkg + (module.split(".") if module else []))
        else:
            base = module or ""
        lookup = index.get if level else absolute_lookup
        subs = []
        for n in names:
            hit = lookup(f"{base}.{n}" if base else n)
            if hit:
                subs.append(hit)
        if subs:
            internal.update(subs)
            continue
        target = _longest_prefix(base, lookup) if base else None
        if target:
            internal.add(target)
            used.setdefault(target, set()).update(n for n in names if n != "*")
        elif level == 0 and base:
            top = base.split(".")[0]
            if top not in _STDLIB and top not in project_tops:
                external.add(top)
    internal.discard(own)
    return internal, external, used


# --------------------------------------------------------------------------
# JavaScript / TypeScript / HTML (regex-based)
# --------------------------------------------------------------------------

_JS_IMPORT_RES = [
    re.compile(r"""\bimport\s+(?:[\w$*{}\s,]+?\s+from\s+)?["']([^"']+)["']"""),
    re.compile(r"""\bexport\s+(?:\*|\{[^}]*\})\s*(?:as\s+[\w$]+\s*)?from\s+["']([^"']+)["']"""),
    re.compile(r"""\brequire\(\s*["']([^"']+)["']\s*\)"""),
    re.compile(r"""\bimport\(\s*["']([^"']+)["']\s*\)"""),
]
_HTML_REFS = [
    re.compile(r"""<script\b[^>]*?\bsrc=["']([^"']+)["']""", re.I),
    re.compile(r"""<link\b[^>]*?\bhref=["']([^"']+)["']""", re.I),
]
_JS_FUNC = re.compile(
    r"^(?P<export>export\s+(?:default\s+)?)?(?P<async>async\s+)?function\s*\*?\s*"
    r"(?P<name>[A-Za-z_$][\w$]*)\s*(?:<[^>(]*>)?\s*\((?P<params>[^)]*)\)", re.M)
_JS_CLASS = re.compile(
    r"^(?P<export>export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)"
    r"(?:\s+extends\s+(?P<base>[\w$.]+))?", re.M)
_JS_ARROW = re.compile(
    r"^(?P<export>export\s+)?(?:const|let)\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*"
    r"(?P<async>async\s+)?(?:\((?P<params>[^)]*)\)|(?P<single>[A-Za-z_$][\w$]*))\s*(?::[^=]+)?=>", re.M)


def _split_commas(s: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in s:
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _js_param(piece: str) -> dict:
    name_part, _, default = piece.partition("=")
    name, _, typ = name_part.partition(":")
    p: dict = {"name": name.strip()}
    if typ.strip():
        p["type"] = typ.strip()
    if default.strip():
        p["default"] = default.strip()
    return p


def _js_function(match: re.Match, text: str, raw_params: str) -> dict:
    name = match.group("name")
    sym = {
        "name": name,
        "kind": "function",
        "line": text.count("\n", 0, match.start()) + 1,
        "public": bool(match.groupdict().get("export")),
        "sig": f"{name}({' '.join(raw_params.split())})",
        "params": [_js_param(p) for p in _split_commas(raw_params)],
    }
    if match.groupdict().get("async"):
        sym["async"] = True
    return sym


def _js_symbols(text: str) -> list[dict]:
    symbols = []
    for m in _JS_FUNC.finditer(text):
        symbols.append(_js_function(m, text, m.group("params")))
    for m in _JS_ARROW.finditer(text):
        symbols.append(_js_function(m, text, m.group("params") or m.group("single") or ""))
    for m in _JS_CLASS.finditer(text):
        base = m.group("base")
        sym = {
            "name": m.group("name"), "kind": "class",
            "line": text.count("\n", 0, m.start()) + 1,
            "public": bool(m.group("export")),
            "sig": f"class {m.group('name')}" + (f" extends {base}" if base else ""),
        }
        if base:
            sym["bases"] = [base]
        symbols.append(sym)
    return sorted(symbols, key=lambda s: s["line"])


def _parse_js(text: str, lang: str) -> dict:
    specs = []
    for rx in _JS_IMPORT_RES:
        specs.extend(rx.findall(text))
    doc = _header_description(text.splitlines(), "//")
    return {"lang": lang, "doc": doc, "raw": specs, "symbols": _js_symbols(text)}


def _parse_html(text: str) -> dict:
    specs = []
    for rx in _HTML_REFS:
        specs.extend(rx.findall(text))
    return {"lang": "html", "doc": None, "raw": specs, "symbols": []}


def _resolve_relative(spec: str, own: str, files: set[str]) -> str | None:
    spec = spec.split("?")[0].split("#")[0]
    base = posixpath.normpath(posixpath.join(posixpath.dirname(own), spec))
    candidates = [base]
    candidates += [base + e for e in JS_EXTS]
    candidates += [f"{base}/index{e}" for e in JS_EXTS]
    if base.endswith(".js"):  # TS projects import "./x.js" for x.ts
        candidates.append(base[:-3] + ".ts")
    return next((c for c in candidates if c in files), None)


def _resolve_js(specs: list[str], own: str, files: set[str], is_html: bool) -> tuple[set[str], set[str]]:
    internal: set[str] = set()
    external: set[str] = set()
    for spec in specs:
        if re.match(r"^(?:[a-z][a-z0-9+.-]*:|//)", spec, re.I):  # http:, data:, //cdn...
            continue
        if spec.startswith(".") or is_html:
            hit = _resolve_relative(spec, own, files)
            if hit:
                internal.add(hit)
        elif spec.startswith("/"):
            continue
        else:
            parts = spec.split("/")
            external.add("/".join(parts[:2]) if spec.startswith("@") else parts[0])
    internal.discard(own)
    return internal, external


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def _parse(lang: str, text: str) -> dict | None:
    if lang == "python":
        return _parse_python(text)
    if lang == "html":
        return _parse_html(text)
    return _parse_js(text, lang)


_DETAIL_KEYS = {"params", "returns", "bases"}  # already spelled out in "sig"


def _emit_symbol(sym: dict, detail: bool) -> dict:
    """Compact output form of a symbol: no internal keys, "public" folded into
    an optional "private": true, structured signature parts only on request."""
    out = {k: v for k, v in sym.items()
           if k not in ("public", "listed", "members") and (detail or k not in _DETAIL_KEYS)}
    if not sym["public"]:
        out["private"] = True
    return out


def _visible(symbols: list[dict], include_private: bool, detail: bool, used: set[str]) -> list[dict]:
    out = []
    for s in symbols:
        if not include_private:
            if not s["public"]:
                continue
            if s["kind"] == "const" and not (s.get("listed") or s["name"] in used):
                continue
        emitted = _emit_symbol(s, detail)
        members = [_emit_symbol(m, detail) for m in s.get("members", [])
                   if include_private or m["public"]]
        if members:
            emitted["members"] = members
        out.append(emitted)
    return out


def build_map(root: Path, cache: dict | None = None, include_private: bool = False,
              exclude: set[str] | None = None, detail: bool = False) -> dict:
    """Build the project map. Pass the same `cache` dict on every call to
    re-parse only changed files. `exclude`: relative paths to leave out
    (e.g. the map's own output file). `detail`: also emit structured
    params/returns/bases (redundant with "sig"; for richer viewers)."""
    cache = cache if cache is not None else {}
    exclude = exclude or set()
    paths = [p for p in list_project_files(root) if p not in exclude]
    files = set(paths)

    parsed: dict[str, dict] = {}
    sizes: dict[str, int] = {}
    for rel in paths:
        lang = LANG_BY_EXT.get(Path(rel).suffix.lower(), "other")
        full = root / rel
        try:
            st = full.stat()
        except OSError:
            continue
        sizes[rel] = st.st_size
        if lang not in ANALYZED:
            parsed[rel] = {"lang": lang}
            continue
        stamp = (st.st_mtime_ns, st.st_size)
        hit = cache.get(rel)
        if hit and hit[0] == stamp:
            parsed[rel] = hit[1]
            continue
        try:
            result = _parse(lang, full.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            result = None
        if result is None:  # unreadable / mid-edit syntax error: keep last good parse
            result = hit[1] if hit else {"lang": lang, "doc": None, "raw": [], "symbols": []}
        cache[rel] = (stamp, result)
        parsed[rel] = result
    for stale in set(cache) - files:
        del cache[stale]

    py_paths = [p for p in paths if p in parsed and parsed[p].get("lang") == "python"]
    index, module_of = _python_modules(py_paths)

    imports: dict[str, set[str]] = {}
    external: dict[str, set[str]] = {}
    imported_by: dict[str, set[str]] = {p: set() for p in paths}
    used_names: dict[str, set[str]] = {}
    for rel, info in parsed.items():
        if "raw" not in info:
            continue
        if info["lang"] == "python":
            imports[rel], external[rel], used = _resolve_python(info["raw"], rel, index, module_of, files)
            for target, names in used.items():
                used_names.setdefault(target, set()).update(names)
        else:
            imports[rel], external[rel] = _resolve_js(info["raw"], rel, files, info["lang"] == "html")
        for target in imports[rel]:
            imported_by[target].add(rel)

    out_files: dict[str, dict] = {}
    for rel in paths:
        info = parsed.get(rel)
        if info is None:
            continue
        entry: dict = {}
        if sizes.get(rel):
            entry["size"] = sizes[rel]
        if "raw" in info:
            if info.get("doc"):
                entry["doc"] = info["doc"]
            if info.get("entry") or rel.rsplit("/", 1)[-1] == "__main__.py":
                entry["entry"] = True
            for key, value in (
                ("imports", sorted(imports[rel])),
                ("imported_by", sorted(imported_by[rel])),
                ("external", sorted(external[rel])),
                ("symbols", _visible(info["symbols"], include_private, detail, used_names.get(rel, set()))),
            ):
                if value:
                    entry[key] = value
        out_files[rel] = entry
    return {"schema": SCHEMA_VERSION, "root": root.name, "files": out_files}


# def dumps(code_map: dict) -> str:
#     """Valid JSON, one file per line: compact for LLMs, diffable for humans."""
#     head = json.dumps({k: v for k, v in code_map.items() if k != "files"}, ensure_ascii=False)[:-1]
#     lines = [
#         f"  {json.dumps(path, ensure_ascii=False)}: {json.dumps(entry, ensure_ascii=False, separators=(',', ':'))}"
#         for path, entry in code_map["files"].items()
#     ]
#     return head + ',\n "files": {\n' + ",\n".join(lines) + "\n }\n}\n"



def _format_js_key(key: str) -> str:
    """Format an object key without double-quotes if it is a valid JS identifier."""
    if _IDENT_RE.match(key):
        return key
    return json.dumps(key)


def dumps(code_map: dict) -> str:
    """JS-compatible JSON object, one file per line, omitted quotes on safe keys."""

    def stringify_js(obj):
        if isinstance(obj, dict):
            items = [f"{_format_js_key(k)}:{stringify_js(v)}" for k, v in obj.items()]
            return "{" + ",".join(items) + "}"
        return json.dumps(obj, separators=(",", ":"))

    meta_parts = [
        f'  "{k}": {stringify_js(v)}'
        if not _IDENT_RE.match(k)
        else f"  {k}: {stringify_js(v)}"
        for k, v in code_map.items()
        if k != "files"
    ]
    head = "{\n" + ",\n".join(meta_parts) if meta_parts else "{"

    lines = [
        f"  {json.dumps(k)}: {stringify_js(v)}"
        for k, v in code_map.get("files", {}).items()
    ]

    return head + ',\n  files: {\n' + ",\n".join(lines) + "\n }\n}\n"