import json, pathlib
out = []
for x in range(7):
    rows = json.loads(pathlib.Path(f"audit/round-1/phase-{x}.json").read_text(encoding="utf-8"))
    for r in rows:
        if r["status"] in ("VERIFIED", "PRESENT_UNTESTED"):
            out.append(" | ".join([r["id"], r["status"], r["requirement"][:90], r["evidence"][:220]]))
pathlib.Path("audit/evidence/verified-rows.txt").write_text("\n".join(out), encoding="utf-8")
print(len(out))
