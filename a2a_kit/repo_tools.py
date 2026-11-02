"""Deterministic repository inspection tools (stdlib + httpx) wrapped by every framework in its own style."""
from __future__ import annotations

import ast
import json
import re
import tomllib
from collections import Counter
from pathlib import Path

import httpx

SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".tox", ".mypy_cache", ".pytest_cache"}
SECRETS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "generic_secret": re.compile(r"(?i)(?:api[_-]?key|secret|passwd|password|token)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
}
COPYLEFT = ("GPL", "AGPL", "LGPL", "MPL", "EUPL", "SSPL", "CC-BY-SA")


def _files(repo: Path, suffixes: set[str] | None = None):
    for p in repo.rglob("*"):
        if p.is_file() and not (set(p.relative_to(repo).parts) & SKIP) and (not suffixes or p.suffix.lower() in suffixes):
            yield p


def quality_report(repo: Path) -> dict:
    loc: Counter = Counter()
    long_funcs, complex_funcs, todos, test_loc, code_loc = [], [], 0, 0, 0
    for p in _files(repo, {".py", ".js", ".ts", ".go", ".java", ".rs"}):
        text = p.read_text(encoding="utf-8", errors="ignore")
        n = len(text.splitlines())
        loc[p.suffix] += n
        todos += len(re.findall(r"TODO|FIXME|HACK|XXX", text))
        is_test = p.name.startswith("test_") or "tests" in p.parts or p.name.endswith(("_test.py", ".test.js", ".spec.ts"))
        test_loc, code_loc = (test_loc + n, code_loc) if is_test else (test_loc, code_loc + n)
        if p.suffix == ".py":
            try:
                for node in ast.walk(ast.parse(text)):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        length = (node.end_lineno or node.lineno) - node.lineno + 1
                        branches = sum(isinstance(x, (ast.If, ast.For, ast.While, ast.Try, ast.BoolOp, ast.ExceptHandler))
                                       for x in ast.walk(node))
                        rel = f"{p.relative_to(repo)}:{node.name}"
                        if length > 60:
                            long_funcs.append((rel, length))
                        if branches > 12:
                            complex_funcs.append((rel, branches))
            except SyntaxError:
                pass
    return {"lines_by_extension": dict(loc.most_common()), "todo_markers": todos,
            "functions_over_60_lines": sorted(long_funcs, key=lambda x: -x[1])[:10],
            "functions_with_12plus_branches": sorted(complex_funcs, key=lambda x: -x[1])[:10],
            "test_loc": test_loc, "code_loc": code_loc,
            "test_to_code_ratio": round(test_loc / code_loc, 2) if code_loc else 0.0}


def security_scan(repo: Path) -> dict:
    secrets, dangerous = [], []
    for p in _files(repo):
        if p.stat().st_size > 1_000_000:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(p.relative_to(repo))
        for kind, rx in SECRETS.items():
            if rx.search(text):
                secrets.append({"file": rel, "kind": kind})       # never include the secret itself
        if p.suffix == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = ast.unparse(node.func)
                    bad = (name in {"eval", "exec", "os.system", "pickle.loads", "pickle.load", "hashlib.md5", "hashlib.sha1"}
                           or (name == "yaml.load" and not any(k.arg == "Loader" for k in node.keywords))
                           or (name.startswith("subprocess.") and any(k.arg == "shell" and getattr(k.value, "value", False) is True
                                                                       for k in node.keywords)))
                    if bad:
                        dangerous.append({"file": rel, "line": node.lineno, "call": name})
    env_files = [str(p.relative_to(repo)) for p in _files(repo) if p.name == ".env"]
    reqs = list(repo.glob("requirements*.txt"))
    unpinned = sum(1 for r in reqs for line in r.read_text(errors="ignore").splitlines()
                   if line.strip() and not line.startswith(("#", "-")) and "==" not in line)
    return {"possible_secrets": secrets[:25], "dangerous_calls": dangerous[:25], "committed_env_files": env_files,
            "unpinned_requirements": unpinned}


def docs_check(repo: Path) -> dict:
    readme = next((repo / n for n in ("README.md", "README.rst", "README.txt", "README") if (repo / n).exists()), None)
    text = readme.read_text(encoding="utf-8", errors="ignore") if readme else ""
    low = text.lower()
    sections = {s: bool(re.search(rf"^#+\s.*{s}", low, re.M)) for s in ("install", "usage", "license", "contribut", "test")}
    broken = []
    for target in re.findall(r"\]\((?!https?://|#|mailto:)([^)\s#]+)", text):
        if not (repo / target).exists():
            broken.append(target)
    public = documented = 0
    for p in _files(repo, {".py"}):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not node.name.startswith("_"):
                public += 1
                documented += ast.get_docstring(node) is not None
    return {"readme": str(readme.relative_to(repo)) if readme else None, "readme_words": len(text.split()),
            "sections_present": sections, "broken_relative_links": broken[:15],
            "changelog": any((repo / n).exists() for n in ("CHANGELOG.md", "CHANGES.md", "HISTORY.md")),
            "public_symbols": public, "documented_public_symbols": documented,
            "docstring_coverage_pct": round(100 * documented / public, 1) if public else None}


def _pypi_license(name: str) -> dict:
    try:
        r = httpx.get(f"https://pypi.org/pypi/{name}/json", timeout=15)
        if r.status_code != 200:
            return {"license": "unknown (not on PyPI)"}
        info = r.json()["info"]
        classifiers = [c.split("::")[-1].strip() for c in info.get("classifiers", []) if c.startswith("License ::")]
        lic = info.get("license_expression") or (info.get("license") or "")[:60] or ", ".join(classifiers) or "unknown"
        return {"license": lic}
    except (httpx.HTTPError, ValueError):
        return {"license": "lookup failed"}


def license_check(repo: Path) -> dict:
    lic_file = next((p for p in repo.iterdir() if p.name.upper().startswith(("LICENSE", "COPYING"))), None)
    own = "none"
    if lic_file:
        t = lic_file.read_text(errors="ignore").lower()
        own = next((n for n, k in (("MIT", "permission is hereby granted"), ("Apache-2.0", "apache license"),
                                   ("GPL", "gnu general public"), ("BSD", "redistribution and use"),
                                   ("MPL", "mozilla public")) if k in t), "unrecognised")
    names: set[str] = set()
    for r in repo.glob("requirements*.txt"):
        for line in r.read_text(errors="ignore").splitlines():
            m = re.match(r"\s*([A-Za-z0-9_.\-]+)", line)
            if m and not line.strip().startswith(("#", "-")):
                names.add(m.group(1))
    pp = repo / "pyproject.toml"
    if pp.exists():
        try:
            for dep in tomllib.loads(pp.read_text()).get("project", {}).get("dependencies", []):
                names.add(re.match(r"[A-Za-z0-9_.\-]+", dep).group(0))
        except (tomllib.TOMLDecodeError, AttributeError):
            pass
    deps = {n: _pypi_license(n) for n in sorted(names)[:25]}
    flagged = {n: v["license"] for n, v in deps.items() if any(c in v["license"].upper() for c in COPYLEFT)}
    unknown = [n for n, v in deps.items() if v["license"].startswith(("unknown", "lookup"))]
    return {"project_license_file": lic_file.name if lic_file else None, "detected_project_license": own,
            "dependencies_checked": len(deps), "copyleft_dependencies": flagged, "unknown_license_dependencies": unknown,
            "all": {n: v["license"] for n, v in deps.items()}}


TOOLS = {"quality": quality_report, "security": security_scan, "docs": docs_check, "licenses": license_check}


def as_json(fn, repo_path: str) -> str:
    return json.dumps(fn(Path(repo_path)), indent=1, default=str)
