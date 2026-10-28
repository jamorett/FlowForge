"""FlowForge audit gate checker (stdlib only). Exit 0 iff all checks pass.

Strict by design (reviewed in the verifier round):
- verifies round-1 AND the final round phase JSONs;
- recomputes the main-checkout fingerprint and compares it to
  audit/evidence/tree-before.txt (excluding audit/ and .muse/);
- requires verdict rows for every pre-audit finding;
- requires the hygiene report to carry the branch name and two exit codes.
Run: python audit/check_audit.py
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
FAILURES = []
VALID = {"VERIFIED", "PRESENT_UNTESTED", "SKELETON", "MISSING",
         "BLOCKED_BY_ENV", "DECISION_NEEDED"}
VERDICTS = {"CONFIRMED", "REFUTED", "UNVERIFIABLE", "DECISION_NEEDED"}


def fail(msg):
    FAILURES.append(msg)


def rounds():
    out = []
    for d in ROOT.glob("round-*"):
        m = re.fullmatch(r"round-(\d+)", d.name)
        if m and d.is_dir():
            out.append((int(m.group(1)), d))
    return sorted(out)  # numeric, not lexicographic (L2)


def check_phase_jsons(rdir, label):
    for x in range(7):
        p = rdir / f"phase-{x}.json"
        if not p.exists():
            fail(f"{label} phase-{x}: missing {p.relative_to(ROOT)}")
            continue
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"{label} phase-{x}: unparsable JSON: {exc}")
            continue
        if not isinstance(rows, list) or not rows:
            fail(f"{label} phase-{x}: expected non-empty list")
            continue
        seen = set()
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                fail(f"{label} phase-{x} row {i}: not an object")
                continue
            for key in ("id", "requirement", "status", "evidence", "gap"):
                if not str(r.get(key, "")).strip():
                    fail(f"{label} phase-{x} row {i}: missing/empty {key}")
            if r.get("id") in seen:
                fail(f"{label} phase-{x}: duplicate id {r.get('id')!r}")
            seen.add(r.get("id"))
            if r.get("status") not in VALID:
                fail(f"{label} phase-{x} row {i}: bad status {r.get('status')!r}")
            ev = str(r.get("evidence", ""))
            if len(ev) < 30 or not re.search(r"(\.py|\.md|\.yaml|\.txt|\.json|exit|::|:)\S*", ev):
                fail(f"{label} phase-{x} row {i}: evidence too weak (L1)")
            if r.get("status") == "VERIFIED" and "exit 0" not in ev and "exit=0" not in ev:
                fail(f"{label} phase-{x} row {i}: VERIFIED without observed exit 0 (L1)")
        md = rdir / f"phase-{x}.md"
        if not md.exists():
            fail(f"{label} phase-{x}: missing signed account .md")
        elif "Signed account" not in md.read_text(encoding="utf-8"):
            fail(f"{label} phase-{x}.md: no 'Signed account'")


def git(*args):
    cmd = ["git", "-c", f"safe.directory={REPO.as_posix()}", *args]
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout


def fingerprint():
    rc1, status = git("status", "--porcelain")
    rc2, diff = git("diff")
    rc3, staged = git("diff", "--cached")
    rc4, untracked = git("ls-files", "--others", "--exclude-standard")
    if 0 not in (rc1, rc2, rc3, rc4) or any(rc != 0 for rc in (rc1, rc2, rc3, rc4)):
        fail(f"fingerprint: git failed rc={rc1},{rc2},{rc3},{rc4} (L3)")

    def keep(line):
        p = line[3:] if len(line) > 3 and line[2] == " " else line
        return not (p.startswith("audit/") or p.startswith(".muse/"))

    status_f = "\n".join(l for l in status.splitlines() if keep(l))
    untracked_f = "\n".join(l for l in untracked.splitlines()
                            if not (l.startswith("audit/") or l.startswith(".muse/")))
    h = hashlib.sha256()
    for name in [l for l in untracked_f.splitlines() if l]:
        fp = REPO / name
        if fp.is_file():
            h.update(name.encode())
            h.update(fp.read_bytes())
    return (status_f, hashlib.sha256(diff.encode()).hexdigest(),
            hashlib.sha256(staged.encode()).hexdigest(), untracked_f, h.hexdigest())


def main():
    if not (ROOT / "GATE.md").exists():
        fail("GATE.md missing")
    for ev in ("git-status.txt", "git-ls-files.txt", "tree.txt", "stub-scan.txt",
               "pytest-collect.txt", "pytest-run.txt", "import-smoke.txt",
               "versions-env.json", "tree-before.txt", "gate-logic-probe.txt"):
        if not (ROOT / "evidence" / ev).exists():
            fail(f"evidence/{ev} missing")

    rs = rounds()
    if not rs:
        fail("no round-* directories")
    else:
        check_phase_jsons(rs[0][1], f"round-{rs[0][0]}")
        if rs[-1][1] != rs[0][1]:
            check_phase_jsons(rs[-1][1], f"round-{rs[-1][0]} (final)")

    for x in range(7):
        t = ROOT / "tasks" / f"phase-{x}.md"
        if not t.exists() or t.stat().st_size == 0:
            fail(f"tasks/phase-{x}.md missing/empty")

    # pre-audit findings verdicts (final round findings.json)
    required = ([f"H{i}" for i in range(1, 7)] + ["C1", "C2", "C3"]
                + [f"D{i}" for i in range(1, 7)] + [f"P{i}" for i in range(1, 5)])
    if rs:
        fp = rs[-1][1] / "findings.json"
        if not fp.exists():
            fail("final round findings.json missing")
        else:
            try:
                rows = json.loads(fp.read_text(encoding="utf-8"))
                ids = [r.get("id") for r in rows if isinstance(r, dict)]
                if len(ids) != len(set(ids)):
                    fail("findings.json: duplicate ids (L5)")
                by_id = {r.get("id"): r for r in rows if isinstance(r, dict)}
            except Exception as exc:
                fail(f"findings.json unparsable: {exc}")
                by_id = {}
            for fid in required:
                r = by_id.get(fid)
                if r is None:
                    fail(f"findings: no verdict row for {fid}")
                elif r.get("status") not in VERDICTS and r.get("verdict") not in VERDICTS:
                    fail(f"findings {fid}: verdict not in {sorted(VERDICTS)}")
                elif not str(r.get("evidence", "")).strip():
                    fail(f"findings {fid}: empty evidence")

    # verifier: zero unresolved in last challenges Verdict, or three rounds run
    if rs:
        last = rs[-1][1] / "challenges.md"
        if not last.exists():
            fail("final round challenges.md missing")
        else:
            txt = last.read_text(encoding="utf-8")
            verdict = txt.split("## 6. Verdict")[-1] if "## 6. Verdict" in txt else txt[-2000:]
            clean = any("Zero unresolved challenges" in l and "not" not in l.lower().split("zero")[0]
                        for l in verdict.splitlines())
            if not clean and len(rs) < 3:
                fail("challenges: unresolved remain and fewer than three rounds ran")

    hr = ROOT / "hygiene" / "REPORT.md"
    if not hr.exists():
        fail("hygiene/REPORT.md missing")
    else:
        text = hr.read_text(encoding="utf-8")
        if "chore/pre-implementation-hygiene" not in text:
            fail("hygiene REPORT: branch name missing")
        if len(re.findall(r"exit code\D*\d+", text, re.I)) < 2:
            fail("hygiene REPORT: before/after test exit codes missing")

    # fingerprint exact equality (excluding audit/ and .muse/) v2 (L3)
    tb = ROOT / "evidence" / "tree-before.txt"
    if tb.exists():
        before = tb.read_text(encoding="utf-8")
        status_f, digest, staged_digest, untracked_f, content_digest = fingerprint()
        for label, pat, cur in (
            ("diff", r"git_diff_sha256=([0-9a-f]{64})", digest),
            ("cached", r"git_diff_cached_sha256=([0-9a-f]{64})", staged_digest),
            ("untracked-content", r"untracked_content_sha256=([0-9a-f]{64})", content_digest),
        ):
            m = re.search(pat, before)
            if not m or m.group(1) != cur:
                fail(f"fingerprint: {label} hash differs from tree-before.txt")
        stored_status = before.split("[status]", 1)[-1].split("git_diff_sha256=")[0].strip()
        if stored_status != status_f.strip():
            fail("fingerprint: status set differs exactly from tree-before.txt")
        stored_untracked = before.split("[untracked]", 1)[-1].split("untracked_content_sha256=")[0].strip()
        if stored_untracked != untracked_f.strip():
            fail("fingerprint: untracked set differs exactly from tree-before.txt")

    rep = ROOT / "REPORT.md"
    if not rep.exists():
        fail("REPORT.md missing")
    else:
        text = rep.read_text(encoding="utf-8").lower()
        for section in ("gate decision", "state of the project", "per-phase",
                        "pre-audit findings", "skeleton", "task plan",
                        "decisions", "commands", "open disagreements"):
            if section not in text:
                fail(f"REPORT.md: section {section!r} missing")

    if FAILURES:
        print("AUDIT CHECK: FAIL")
        for f in FAILURES:
            print(f" - {f}")
        return 1
    print("AUDIT CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
