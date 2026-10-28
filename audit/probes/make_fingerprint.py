"""Regenerate audit/evidence/tree-before.txt in structured exact-compare format.
Main checkout outside audit/ has not changed since Step 0 (git status proved),
so this is the same fingerprint with a stricter encoding."""
import hashlib, subprocess
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]

def git(*a):
    p = subprocess.run(["git", "-c", f"safe.directory={REPO.as_posix()}", *a],
                       cwd=REPO, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, (a, p.stderr)
    return p.stdout

def keep(line):
    p = line[3:] if len(line) > 3 and line[2] == " " else line
    return not (p.startswith("audit/") or p.startswith(".muse/"))

status = "\n".join(l for l in git("status", "--porcelain").splitlines() if keep(l))
diff = git("diff")
staged = git("diff", "--cached")
untracked = "\n".join(l for l in git("ls-files", "--others", "--exclude-standard").splitlines()
                      if not (l.startswith("audit/") or l.startswith(".muse/")))
h = hashlib.sha256()
for name in [l for l in untracked.splitlines() if l]:
    fp = REPO / name
    if fp.is_file():
        h.update(name.encode()); h.update(fp.read_bytes())
text = (
    "# tree-before fingerprint (excludes audit/ and .muse/) v2 exact\n"
    "[status]\n" + status + "\n"
    f"git_diff_sha256={hashlib.sha256(diff.encode()).hexdigest()}\n"
    f"git_diff_cached_sha256={hashlib.sha256(staged.encode()).hexdigest()}\n"
    "[untracked]\n" + untracked + "\n"
    f"untracked_content_sha256={h.hexdigest()}\n"
)
(REPO / "audit/evidence/tree-before.txt").write_text(text, encoding="utf-8")
print(text)
