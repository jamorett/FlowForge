# Step 0 evidence — collection status (shell unavailable)

Every shell-backed collection below was ATTEMPTED and FAILED: all
`muse.powershell` calls in this session errored (powershell.exe spawn
failure; escalated retry → "program not found"). No `git`, `pytest`,
`ruff`, `mypy`, `docker`, `uv`, `python`, or `node` command produced an
exit code. This file records the failure honestly instead of inventing
outputs.

- git branch / status / last-20-commits / ls-files: NOT COLLECTED
  (needs shell). Retry: `git branch --show-current; git status
  --porcelain; git log --oneline -20; git ls-files`.
- Real file tree (excl. ui/node_modules): NOT COLLECTED. Partial
  reconstruction from reads exists in phase files; unlisted files remain.
  Retry: `python audit/probes/tree.py` (to be written) or
  `Get-ChildItem -Recurse -Force | Where-Object { $_.FullName -notmatch
  'node_modules' }`.
- Stub scan: PARTIAL via file reads (not a repo-wide grep). Hits found by
  reading: `raise NotImplementedError` in
  tests/integration/test_identity.py:52 and test_oracle.py:74 (both in
  @pytest.mark.skip solver tests); `return []` placeholder in
  agents/tools/registry.py:19; `SystemExit` offline-stop in
  download_data.py:53-56; toy fixture parser in literature/harvester.py.
  TODO/FIXME/XXX/HACK repo-wide: UNKNOWN (needs rg). Retry: `rg -n
  "NotImplementedError|TODO|FIXME|XXX|HACK|skip|xfail" --glob '!audit/*'`.
- pytest --collect-only / offline run: NOT RUN. Retry:
  `python -m pytest --collect-only -q` then
  `python -m pytest tests/unit -x -q` (both with 120s timeout wrapper).
- ruff/mypy: configured (pyproject [tool.ruff], [tool.mypy]) but NOT RUN.
  Retry: `ruff check .` and `mypy flowforge`.
- Import smoke of every flowforge module: NOT RUN. Retry:
  `python -c "import importlib, pkgutil, flowforge; ..."`.
- Versions (python/uv/docker/node): UNKNOWN. Retry:
  `python --version; uv --version; docker --version; node --version`.
- Env var names: UNKNOWN (values never printed by rule). Retry:
  `[Environment]::GetEnvironmentVariables().Keys` and report names only
  (MODEL_API_KEY presence, FLOWFORGE_REPLAY, etc.).
- .env contents: NOT READ (forbidden by guardrail 3).
- data/locked/: NOT OPENED (forbidden by guardrail 3).
