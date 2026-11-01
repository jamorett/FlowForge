# FlowForge pre-implementation hygiene — MANUAL cleanup (review before running!)
# These are UNTRACKED pip temp folders at the repo root (finding H1, CONFIRMED).
# They cannot be removed from the hygiene worktree; only you can delete them here.
# Nothing in this script touches tracked files. Run from the repo root in PowerShell.
# DRY RUN first: it only lists by default. Add -Apply to actually remove.

param([switch]$Apply)

$targets = @(
  "pip-build-tracker-jbygwmni",
  "pip-build-tracker-lnx60z05",
  "pip-ephem-wheel-cache-wuci0rio",
  "pip-ephem-wheel-cache-yi600nmi",
  "pip-install-pxjrlpdv",
  "pip-install-snl8b442",
  "pip-target-qyax1xzx"
)
# Untracked generated caches (also candidates; NOT removed by this script):
#   scratch\__pycache__\, runs\probe_s55\  (probe output; keep if you need it)

foreach ($t in $targets) {
  if (Test-Path $t) {
    if ($Apply) { Remove-Item -Recurse -Force $t; Write-Output "removed $t" }
    else { Write-Output "would remove $t (dry run; use -Apply)" }
  } else { Write-Output "absent $t" }
}
