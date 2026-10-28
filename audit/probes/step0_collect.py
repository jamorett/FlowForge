"""Step 0 preflight collector (stdlib only). Writes audit/evidence/*.
Every external command runs via subprocess.run(timeout=120). No installs,
no network, no Docker, no solver. Env values are never printed: names only.
Run: python audit/probes/step0_collect.py
"""
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "audit" / "evidence"
EV.mkdir(parents=True, exist_ok=True)
GIT = ["git", "-c", f"safe.directory={ROOT.as_posix()}"]


def run(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError as e:
        return 127, f"FileNotFoundError: {e}"
    except subprocess.TimeoutExpired as e:
        return 124, f"TimeoutExpired after {timeout}s: {e}"


def write(name, text):
    (EV / name).write_text(text, encoding="utf-8")


def main():
    log = []

    # --- git ---
    for label, cmd, fname in [
        ("branch", GIT + ["branch", "--show-current"], "git-branch.txt"),
        ("status", GIT + ["status", "--porcelain"], "git-status.txt"),
        ("log20", GIT + ["log", "--oneline", "-20"], "git-log20.txt"),
        ("ls-files", GIT + ["ls-files"], "git-ls-files.txt"),
    ]:
        rc, out = run(cmd)
        write(fname, f"$ {' '.join(cmd)}\nexit={rc}\n{out}")
        log.append(f"git {label}: exit={rc} lines={len(out.splitlines())}")

    # fingerprint: tree-before.txt (exclude audit/ and .muse/)
    rc_s, status = run(GIT + ["status", "--porcelain"])
    rc_d, diff = run(GIT + ["diff"])
    rc_u, untracked = run(GIT + ["ls-files", "--others", "--exclude-standard"])
    def keep(line):
        p = line[3:] if len(line) > 3 and line[2] == " " else line
        return not (p.startswith("audit/") or p.startswith("audit\\")
                    or p.startswith(".muse/") or p.startswith(".muse\\"))
    status_f = "\n".join(l for l in status.splitlines() if keep(l))
    untracked_f = "\n".join(l for l in untracked.splitlines()
                            if not (l.startswith("audit/") or l.startswith(".muse/")))
    digest = hashlib.sha256(diff.encode("utf-8", "replace")).hexdigest()
    write("tree-before.txt",
          "# tree-before fingerprint (excludes audit/ and .muse/)\n"
          f"git_status_porcelain_exit={rc_s}\n{status_f}\n"
          f"git_diff_sha256={digest}\n"
          f"git_diff_exit={rc_d}\n"
          f"untracked_exclude_standard_exit={rc_u}\n{untracked_f}\n")
    log.append(f"fingerprint: status_lines={len(status_f.splitlines())} "
               f"diff_sha256={digest[:12]} untracked={len(untracked_f.splitlines())}")

    # --- real tree (exclude ui/node_modules, .git, audit) ---
    tree_lines = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = Path(dirpath).relative_to(ROOT)
        dirnames[:] = [d for d in sorted(dirnames)
                       if not (rel / d).as_posix().startswith("ui/node_modules")
                       and d not in (".git", "node_modules")]
        if rel.as_posix().startswith("ui/node_modules"):
            continue
        for f in sorted(filenames):
            p = (rel / f).as_posix()
            if p.startswith("ui/node_modules"):
                continue
            tree_lines.append(p)
    write("tree.txt", "\n".join(tree_lines) + "\n")
    log.append(f"tree: {len(tree_lines)} files (excl ui/node_modules,.git)")

    # --- stub scan (python; rg unavailable) ---
    pats = {
        "NotImplementedError": re.compile(r"NotImplementedError"),
        "TODO_FIXME_XXX_HACK": re.compile(r"\b(TODO|FIXME|XXX|HACK)\b"),
        "pass_only": re.compile(r"^\s*pass\s*$"),
        "ellipsis_only": re.compile(r"^\s*\.\.\.\s*$"),
        "mock_synthetic": re.compile(r"\b(mock|Mock|synthetic|fake|placeholder|stub)\b", re.I),
        "skip_xfail": re.compile(r"pytest\.mark\.(skip|xfail)|@skip|unittest\.skip"),
        "hardcoded_return": re.compile(r"^\s*return\s+(\[\]|\{\}|None|0|True|False|\"\"|'')\s*$"),
    }
    hits = []
    scan_roots = [ROOT / d for d in ("flowforge", "tests", "scripts", "openfoam", "configs", "prompts", "ui/src") if (ROOT / d).exists()]
    for base in scan_roots:
        for fp in sorted(base.rglob("*")):
            if fp.is_file() and fp.suffix in (".py", ".ts", ".tsx", ".yaml", ".yml", ".C", ".H") \
               and "node_modules" not in fp.parts:
                try:
                    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
                except OSError:
                    continue
                for i, line in enumerate(lines, 1):
                    for name, pat in pats.items():
                        if pat.search(line):
                            hits.append(f"{fp.relative_to(ROOT).as_posix()}:{i}: [{name}] {line.strip()[:160]}")
    write("stub-scan.txt", "\n".join(hits) + "\n")
    log.append(f"stub-scan: {len(hits)} hits")

    # --- pytest collect + offline run (expected to fail: pytest not installed) ---
    for label, cmd, fname in [
        ("collect", [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], "pytest-collect.txt"),
        ("run", [sys.executable, "-m", "pytest", "tests/unit", "tests/integration", "-q", "-p", "no:cacheprovider"], "pytest-run.txt"),
        ("ruff", [sys.executable, "-m", "ruff", "check", "."], "ruff.txt"),
        ("mypy", [sys.executable, "-m", "mypy", "flowforge"], "mypy.txt"),
    ]:
        rc, out = run(cmd)
        write(fname, f"$ {' '.join(cmd)}\nexit={rc}\n{out[-8000:]}")
        log.append(f"{label}: exit={rc}")

    # --- import smoke of every flowforge module ---
    results = {}
    pkg_root = ROOT / "flowforge"
    mods = []
    for fp in sorted(pkg_root.rglob("*.py")):
        rel = fp.relative_to(ROOT).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            mods.append(".".join(parts))
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    code = (
        "import importlib, json, sys\n"
        f"mods={mods!r}\n"
        "out={}\n"
        "for m in mods:\n"
        "    try:\n"
        "        importlib.import_module(m); out[m]='OK'\n"
        "    except Exception as e:\n"
        "        out[m]=type(e).__name__+': '+str(e)[:200]\n"
        "print(json.dumps(out, indent=1, sort_keys=True))\n"
    )
    try:
        p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True,
                           text=True, timeout=120, env=env)
        write("import-smoke.txt", f"exit={p.returncode}\n{p.stdout}\n{p.stderr[-4000:]}")
        try:
            results = json.loads(p.stdout)
        except Exception:
            results = {}
        log.append(f"import-smoke: exit={p.returncode} ok={sum(1 for v in results.values() if v=='OK')}/{len(mods)}")
    except subprocess.TimeoutExpired:
        write("import-smoke.txt", "exit=124 TimeoutExpired")
        log.append("import-smoke: TIMEOUT")

    # --- versions + env names (values never printed) ---
    versions = {"python": sys.version.split()[0], "executable": sys.executable}
    for name, cmd in [("uv", ["uv", "--version"]), ("docker", ["docker", "--version"]),
                      ("node", ["node", "--version"]), ("rg", ["rg", "--version"])]:
        rc, out = run(cmd, timeout=30)
        versions[name] = f"exit={rc} {out.strip().splitlines()[0][:80] if out.strip() else ''}"
    versions["env_names"] = sorted(os.environ.keys())
    for probe in ("MODEL_API_KEY", "OPENAI_API_KEY", "FLOWFORGE_REPLAY", "KAGGLE_USERNAME", "KAGGLE_KEY"):
        versions[f"{probe}_set"] = probe in os.environ
    versions["uv_lock_exists"] = (ROOT / "uv.lock").exists()
    versions["venv_exists"] = (ROOT / ".venv").exists()
    versions["data_locked_opened"] = False
    write("versions-env.json", json.dumps(versions, indent=1))
    log.append(f"versions: {versions['uv']} | {versions['docker']} | {versions['node']}")

    write("step0-summary.txt", "\n".join(log) + "\n")
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
