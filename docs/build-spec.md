# FlowForge v2: build spec

Oct 24, 2026 · @Juan

## System architecture

**FlowForge v2 is one Python system that runs agent research groups against a local OpenFOAM farm, with a React UI on top; only the model calls leave your machines.**

&#91;embedded content: System layers · local machines plus the Meta Model API\]

- **Orchestrator** is the heart: it runs rounds, enforces token and solver budgets, writes every event to an append-only log, and can replay a recorded session without calling the API.
- **Agent runtime** wraps the Meta Model API: role prompts, structured outputs, retries, cost tracking.
- **Evaluation ladder** turns a candidate closure into scores, cheap rungs first.
- **OpenFOAM farm** runs cases in Docker through foamlib, which runs many cases at once without oversubscribing CPUs and reads and writes OpenFOAM files from Python ([foamlib](https://pypi.org/project/foamlib)).
- **Red team generator** creates new flow cases and runs physics attacks on candidates.
- **Storage** keeps state in SQLite, fields in Zarr, and every artifact under a content hash, so identical runs are never repeated. The locked test data lives apart and is readable only by the evaluator.

**Machine plan:** one laptop is the farm host (orchestrator plus workers sized to cores minus one). The second is for development, and later runs a separate experiment arm, such as the no-red-team ablation. Splitting by experiment rather than distributing one farm avoids networking work.

## Languages, tools and environment

**Python for almost everything, C++ for exactly one OpenFOAM class, TypeScript for the UI.**

| Layer | Choice | Why |
| --- | --- | --- |
| Core language | Python 3.12 | NumPy, SciPy, SymPy, foamlib and async orchestration in one language |
| Environment | uv with pyproject.toml; ruff, mypy, pre-commit | Reproducible installs for two people in minutes |
| Solver | OpenFOAM ESI line (openfoam.com), recent release, in the official OpenCFD Docker image | The curated dataset was built with ESI v2006, and the data-driven turbulence community recommends the ESI line ([example repo](https://github.com/mthsmcd/MachineLearningTurbulenceModels)) |
| Closure inside the solver | One C++ template class: k-omega SST plus the two corrections. SymPy generates the correction code for each candidate that passes rung 1; compiling it should take about a minute (measure it), cached by hash. A fixed-field mode serves the oracle test | Corrections are re-evaluated every iteration from the current flow, which keeps the model consistent with the solver. Fallback: an outer loop where Python recomputes correction fields between short solver runs |
| Solver control | foamlib (async) | Parallel runs, field I/O as Python objects |
| Math | NumPy, SciPy, scikit-learn (elastic net), SymPy | Fitting, sparse regression, parsing, simplification, LaTeX and fast compiled expressions |
| Data | Zarr for fields, Parquet for metric tables, SQLite for state, DuckDB for analysis | Simple, file-based, no servers |
| Rendering | PyVista off-screen to PNG | Error maps for SAM 3.1 and the UI |
| Models | Meta Model API through the OpenAI Python SDK (the API accepts OpenAI and Anthropic request formats); pydantic schemas; tenacity retries | Standard tooling works unchanged |
| Vision | SAM 3.1 through Meta Model API | Segment error regions; confirm the endpoint in the docs at kickoff |
| API server | FastAPI with uvicorn and websockets | Async, typed, streams events to the UI |
| UI | Vite, React, TypeScript, Plotly.js, KaTeX, TanStack Query, Tailwind | Heatmaps, profiles and equations with little custom code |
| Coding agent | Muse Code (Contributor tier if you accept its data terms) | Cheapest way to write the code with Meta's stack |
| CI | GitHub Actions: lint, unit tests, one tiny case in the OpenFOAM container | Breakage shows up per push |

**Accounts to create before kickoff:** GitHub repo, Kaggle (for the dataset download token), Meta Model API (once approved).

## Folder structure

One monorepo; data and run outputs stay out of git.

```
flowforge/
├── README.md
├── pyproject.toml              # uv, Python 3.12
├── docker/
│   ├── openfoam.Dockerfile     # OpenFOAM ESI + compiled closure class
│   └── compose.yaml            # api, workers, ui
├── configs/
│   ├── experiments/            # baseline.yaml, swarm.yaml, swarm_no_redteam.yaml, sparse_baseline.yaml
│   ├── budgets.yaml            # token and solver caps per role and group
│   └── cases.yaml              # case registry with train / validation / locked split
├── data/                       # git-ignored
│   ├── raw/                    # downloads as-is + manifest with SHA-256 and license
│   ├── processed/              # one Zarr store per case: fields, features, targets
│   ├── locked/                 # held-out test, read only by the evaluator
│   └── literature/             # metadata, abstracts, closure cards
├── openfoam/
│   ├── src/correctedKOmegaSST/ # the one C++ class
│   ├── templates/              # periodicHill, squareDuct, channel, flatPlate, bump
│   └── meshing/                # parametric geometry and blockMesh generators
├── flowforge/                  # Python package
│   ├── dsl/                    # closure grammar, parser, SymPy compile, complexity
│   ├── physics/                # invariants, tensor basis, realizability, frozen-RANS targets
│   ├── data/                   # ingestion, schemas, splits, lock enforcement
│   ├── solver/                 # foamlib wrappers, job runner, field I/O
│   ├── ladder/                 # rungs, successive halving, scoring
│   ├── redteam/                # flow generator, attacks, permanent attack suite
│   ├── elegance/               # rung-0 checks, description length, constant snapping, champion rule
│   ├── composer/               # gated composition, gate fitting
│   ├── agents/                 # roles, schemas, tools, model router, budget meter
│   ├── orchestrator/           # rounds, board logic, event log, replay
│   ├── literature/             # API clients, card extraction, retrieval
│   ├── render/                 # PyVista renders, SAM 3.1 client, region masks
│   └── api/                    # FastAPI app and websocket stream
├── library/                    # in git: modules/, attacks/, rejected/, findings/
├── prompts/                    # versioned prompt files per role
├── ui/src/{pages,components,state,api}/
├── runs/                       # git-ignored: one folder per session (events.jsonl, candidates, fields)
├── notebooks/                  # analysis and figures
├── scripts/                    # download_data.py, run_experiment.py, export_demo.py
└── tests/{unit,integration,science}/
```

## Data ingestion and handling

**Four sources, one canonical format, and a test set the agents can never touch.**

| Source | What it has | Used for | How to get it |
| --- | --- | --- | --- |
| [Curated turbulence dataset](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8484471/) (Kaggle) | RANS runs with matching DNS/LES for periodic hills, square duct, bumps, converging-diverging channel and curved step; OpenFOAM case files, meshes and NumPy arrays | Training and validation features, targets, ready-made cases | Kaggle API with your account token |
| [Closure Challenge](https://github.com/rmcconke/closure-challenge-benchmark) | Standardized training data including mean velocity gradients; test cases (periodic hills, square duct, NASA wall-mounted hump); evaluation code | Locked test set and the official metric | git clone; read its README for submission format before day 1 |
| Periodic hills of parameterized slope ([Xiao et al.](https://arxiv.org/pdf/1910.01264)) | DNS across hill steepness | Already inside the curated set; its slope parameterization drives red-team geometry | Included |
| [NASA Turbulence Modeling Resource](https://tmbwg.github.io/turbmodels/) | Model equations, verification cases such as the zero-pressure-gradient flat plate, grids | Canonical regression suite and literature cards | Download the listed files |

**Pipeline** (scripts/download\_data.py, then flowforge/data):

1. **Fetch:** download as-is into data/raw; record SHA-256, source URL and license in a manifest.
2. **Convert:** read OpenFOAM fields with foamlib into one Zarr store per case: coordinates, cell volumes, wall distance, U, p, k, omega, velocity gradient; plus DNS Reynolds stress and k where available.
3. **Derive:** normalized strain and rotation tensors, scalar invariants, the tensor basis, anisotropy, and frozen-RANS targets (anisotropy correction and production correction).
4. **Validate:** schema checks; anisotropy symmetric and trace-free; DNS stresses realizable; recomputed features match the dataset's own features within tolerance.
5. **Register:** add the case to configs/cases.yaml with its split and a short data card.

**Handling rules:**

- **Splits are fixed before any agent runs.** The locked test lives in data/locked, is read only by the evaluator process, and every access is logged with a reason. Limit locked evaluations to three milestones; repeated peeking leaks information even as aggregates.
- **Content addressing:** a candidate's ID is the hash of its canonical expression and constants; a run's ID is the hash of candidate, case, mesh and solver settings. Same hash means cached result.
- **Append-only event log** (runs/\<session>/events.jsonl) stores every prompt version, model response, run and score; replay mode re-feeds recorded responses so UI work costs no tokens.
- **Size is small:** each periodic-hill case is about 15,000 points ([example](https://arxiv.org/pdf/2201.01710)), so everything fits on a laptop.
- **Licenses:** keep raw data out of the repo and record each source's terms in the manifest.

## Literature collection (scraping)

**Use official APIs instead of scraping pages, and store your own extracted cards rather than other people's text.**

1. **Query:** arXiv API (physics.flu-dyn), OpenAlex and Semantic Scholar APIs, with terms such as curvature correction, pressure-gradient sensitized, explicit algebraic Reynolds stress model, secondary flow, non-equilibrium. Add the NASA Turbulence Modeling Resource model pages for exact equations.
2. **Filter:** a cheap model call rates relevance from title and abstract.
3. **Extract:** for open-access papers only, pull text with pdfplumber; Muse Spark fills a closure card: mechanism, model form (must parse in SymPy), variables, assumptions, flows it was calibrated on, known failures, DOI.
4. **Check:** reject cards whose equation fails to parse; the physics owner reviews the top 30 by hand.
5. **Serve:** cards are small, so the board and theorists receive the whole relevant subset in context (Muse Spark has a 1M-token window). No vector database needed.

**Etiquette:** rate-limit, cache every response, send an identifying user agent, follow each site's robots.txt and terms, keep PDFs local and never republish them. This is a one-time cost of a few dollars.

## AI workflows

**Agents never write free-form physics; they write candidates in a small, checkable language, and every claim is decided by a run.**

### Candidate format (the closure language)

Following the k-corrective frozen-RANS approach (SpaRTA), a candidate defines two corrections to k-omega SST:

- **Anisotropy correction:** a sum over tensor-basis terms, each multiplied by a scalar function of the invariants.
- **Production correction:** the same form, contracted with the velocity gradient and scaled by k, added to the k equation.
- **Optional gate:** a sigmoid of invariant features that switches a module on only where its mechanism appears.

The grammar allows the invariants plus a few dataset features, constants to be fitted, and only smooth operations: +, −, ×, division by strictly positive expressions, integer powers, square roots of strictly positive expressions, exp and tanh. Complexity is the expression-tree node count, capped at about 25. SymPy parses and simplifies every candidate, compiles it to NumPy for fitting, and renders it to LaTeX for the UI.

### Roles

| Role | Model | Gets | Returns | Tools |
| --- | --- | --- | --- | --- |
| Research board | Muse Spark 1.3, high reasoning | Baseline error summary, findings board, scores, budget left | Round plan: mechanisms, group staffing, budget split | read\_findings, read\_scores |
| Theorist | Muse Spark 1.3 | Mechanism brief, relevant closure cards, group history | 1 to 3 candidates in the closure language, rationale, predicted effect | search\_cards |
| Coder | Contributor tier, or Spark if declined | A candidate | Fitted constants and a priori metrics, or a repaired parse | fit\_constants, eval\_apriori |
| Analyst | Muse Spark 1.3 with images | Error maps, SAM region masks, velocity profiles | Where and why it fails; next hypothesis | render\_error\_map, sam\_segment |
| Skeptic | Muse Spark 1.3, separate context | Candidate plus all its evidence | Objections and extra tests to run | request\_test |
| Red team lead | Muse Spark 1.3 | Current champions, attack suite, generator parameters | New flow specs and attacks | generate\_flow, run\_attack |
| Composer | Muse Spark 1.3 plus gate fitting | Surviving modules, regime features | Gated composition | fit\_gates |

### One round

1. Board reads the findings board and scores, then staffs groups and splits the solver budget.
2. Each theorist proposes candidates; rung 0, the elegance gate, rejects any that fail the symbolic checks; the coder fits constants on training targets, then snaps them to simple values where accuracy allows.
3. Rung 1, a priori: evaluate both corrections on precomputed features and compare them to the frozen-RANS targets; no solver, seconds per case. The bottom half is dropped.
4. Rung 2, short run: generate and compile the candidate's C++, then a coarse, time-capped RANS solve to catch divergence and check the flow moves toward DNS. The bottom half is dropped again.
5. Rung 3, full RANS: converged solves on every training case, then the physics checks.
6. Analyst diagnoses the errors; skeptic objects or requests tests; the group posts findings.
7. Red team generates new flows and attacks the survivors; anything broken goes back with an attack report.
8. Composer combines surviving modules with gates and scores the composition.
9. Board dissolves failed groups, merges ideas, and starts the next round.

### Guardrails

- Every output is validated against a pydantic schema, with one repair retry.
- Candidates must parse and fall under the complexity cap; a re-proposed expression hash is rejected.
- Token caps per role, solver-run caps per round, and a session dollar limit that pauses the run.
- Prompt files are versioned and their hash is logged with each call; replay mode reproduces any session.
- Agents cannot read data/locked or its scores; only the board sees milestone results.

### Selection score

Candidates must pass every elegance filter and every physics check on all training and generated flows. Among those within 3% of the best worst-case error against DNS, the champion is the one with the shortest description length (see Elegance).

### Memory across sessions

**Agents are stateless; what the swarm learns lives in a versioned library on disk, and only verified knowledge is reusable.**

| Store | Contents | Lifecycle |
| --- | --- | --- |
| Module library (library/modules/) | One small file per module: canonical expression, constants, gate, scope (flows and regimes where it was verified), provenance (session, parent modules, prompt and model versions), evidence (run hashes and scores) | candidate, then verified, then champion; demoted if a later attack breaks it |
| Attack suite (library/attacks/) | Every attack that ever broke a candidate, with its flow spec | Only grows; every new attack is re-run against all verified modules |
| Negative results (library/rejected/) | Expression hashes that failed and why | Dedup across sessions, so no session re-proposes a known failure |
| Findings (library/findings/) | Plain-language lessons, each linked to the runs behind it | Treated as hypotheses, never as facts; pruned when their evidence is invalidated |

**How it carries over:**

- **New session:** the board receives a summary of the library; theorists can reuse verified modules as building blocks; the red team starts from the full attack suite.
- **Across machines:** the library is plain text in git. IDs are content hashes, so the same module discovered on both laptops merges as one entry. Large fields stay out of git and are re-run on demand from their hash.
- **When anything changes** (solver version, mesh, case set): evidence whose run hash no longer matches is marked stale, and those modules are re-verified automatically before reuse.
- **Across model versions:** modules are equations, not model weights, so a future Muse Spark, a different model or a human engineer can read and use them unchanged.

## Elegance: the simplest law that explains the physics

**Among closures that are correct and nearly as accurate as the best, FlowForge picks the shortest, cleanest one.** Elegance here means few terms and constants; every term tied to a named mechanism; simple constants and exponents; symmetries and dimensional consistency built in; the right limits; one unified form instead of a patchwork; and smooth behavior. It is also a bet on generalization: simpler laws tend to transfer better than fitted ones.

### Hard filters (rung 0, before any data is used)

| Check | How it is automated |
| --- | --- |
| Invariance | The grammar only allows tensor-basis forms; a numerical rotation test confirms it |
| Dimensional consistency | The grammar admits only dimensionless inputs, so every term is dimensionless by construction |
| Correct limits | SymPy evaluates the correction at reference states (zero strain, and the equilibrium log-layer state where SST is already right); it must vanish or stay below a small tolerance |
| Smoothness | The grammar contains only smooth operations; a gradient check on training data rejects near-singular behavior |
| Complexity cap | At most about 25 expression-tree nodes |

Rung 0 uses no data and no solver time, so it runs on every proposal.

### Elegance score: description length

**One principled number: the bits needed to write the closure down.** That is bits for its structure (operations and variables) plus bits for each constant at the precision accuracy actually needs, following the minimum description length principle. Shorter formulas, simpler constants and fewer gates all lower it. Whether each term names a physical mechanism is judged by the skeptic and used only as a tie-breaker, because an AI judgment is too noisy to rank on.

### Constant snapping

1. For each fitted constant, try the nearest simple values (0, ±1, ±2, ±½, ±⅓, 3/2 and so on), cheapest to describe first.
2. Snap the constant whose rounding costs the least accuracy, then refit the others.
3. Keep the snap if worst-case error rises by less than 1%; repeat until no snap qualifies.

Snapping to 0 deletes a term, so pruning comes free. A Muse Spark simplifier also proposes algebraic rewrites; SymPy confirms each is equivalent, or the rewrite is re-scored like any candidate.

### Champion rule

Among candidates that pass every hard filter and physics check, take those whose worst-case error is within 3% of the best, then choose the shortest description length, with interpretability as the tie-breaker. The margin and scoring are fixed before experiments start. This is the formula-level version of the one-standard-error rule in statistics.

**What agents are told:** theorists must justify every term with a mechanism; the skeptic critiques elegance as well as correctness; the composer pays in description length for every gate it adds.

## Techniques and algorithms

| Technique | Role in the system |
| --- | --- |
| Tensor-basis representation (Pope's integrity basis) | Invariance by construction: closures depend only on frame-independent quantities |
| k-corrective frozen RANS (SpaRTA) | Computes correction targets from DNS fields, so most fitting is cheap and offline |
| Sparse least squares (elastic net) | Fits constants and prunes terms that don't earn their place |
| Successive halving | Spends expensive solver runs only on candidates that survive cheap rungs |
| Worst-case (minimax) selection | The core rule: rank by the worst flow, not the average |
| Realizability on the barycentric map | Rejects predicted stresses that are physically impossible |
| Canonical regression suite | Channel flow against public channel DNS and the flat plate against NASA reference results, so known-good flows stay good |
| Sigmoid gates on invariant features | Switch modules on only where their mechanism is present |
| PyVista renders plus SAM 3.1 | Segment error regions (bubble, reattachment, shear layer) and map pixel masks back to mesh cells |
| Content-addressed caching | Never pay twice for the same run |

## UI/UX: the Model Lab

**A read-only cockpit where every number is one click from its evidence; the only controls are starting, pausing and replaying sessions.** Desktop-first (1440 px), data-dense, neutral palette with one accent reserved for the red team.

1. **Session control.** Pick an experiment config, set budgets, start or pause. A live meter shows dollars spent, tokens by role, and solver hours.
2. **Mission control (home).** One card per research group: mechanism, members and what each is doing, the latest candidate as an equation, and its ladder rung. Beside it, a live red-team attack feed and a strip of current champions.
3. **Generalization matrix.** Rows are the top candidates; columns are flows grouped as training, generated and locked. Cells show normalized error, or a pass/fail glyph for physics checks. Locked columns stay grey until a milestone. Clicking a cell opens the inspector. A companion Elegance view plots worst-case accuracy against description length and marks the champion chosen by the elegance rule, which you can override.
4. **Candidate inspector.** The equation in KaTeX with its lineage, each term labeled with its mechanism and snapped constants marked; velocity profiles at standard stations against DNS and baseline SST; the error map with SAM regions overlaid; predicted stresses on the barycentric map; a map of where each gated module is active; and the attack history.
5. **Vault.** Milestone results on the locked test, with the access log.
6. **Replay.** Scrub through a recorded session's timeline; this is what the demo video is cut from.

**Data flow:** the API streams events over websockets; the UI keeps a client cache with TanStack Query and never computes physics itself.

## Tests and validation

**Three test layers protect the code, and a fourth, the scientific protocol, protects the claim.**

| Layer | Test | Pass criterion |
| --- | --- | --- |
| Unit | Closure language round trip (parse, simplify, compile, LaTeX) | Identical values before and after |
| Unit | Invariance: rotate the inputs | Outputs rotate consistently to numerical precision |
| Unit | Tensor basis and anisotropy properties | Symmetric and trace-free |
| Unit | Realizability check on known good and bad tensors | Classifies all correctly |
| Unit | Feature recomputation vs dataset features | Within a set tolerance |
| Integration | Baseline SST in the container vs the dataset's RANS fields | Matches within tolerance |
| Integration | Zero correction injected | Identical to baseline |
| Integration | Oracle: DNS-derived corrections injected | Velocity clearly closer to DNS than baseline; this proves the injection pipeline works |
| Integration | One full round on a tiny mesh with recorded responses | Completes and logs every event |
| Numerical | Mesh refinement on one case for the final champion | Key metrics change less than a set tolerance |
| Agent | Schema-valid rate, parse rate, duplicate rate, cost per round, on recorded responses | Tracked per prompt version |
| Leakage | Agent tools attempting to read data/locked | Refused and logged |
| Science | Locked test: at most three milestone evaluations with the metric fixed in advance; each experiment arm run with at least three seeds; baselines SST, a priori-only best, and classical sparse regression at the same budget | Report mean and spread, wins and losses alike |

**Elegance tests:** the limits check passes on a known-good closure (zero correction) and fails on a deliberately wrong one; snapping never raises worst-case error beyond its 1% tolerance; description length is identical for algebraically equivalent expressions after canonicalization.

CI runs the unit layer and one tiny integration case on every push.

## Research paths

**One main question, four supporting ones, and a decision for each outcome.**

| Path | Question | If yes | If no |
| --- | --- | --- | --- |
| RP1 (main) | Does red-team training improve held-out generalization? | Headline result | Report as a negative finding; lean on RP5 |
| RP2 | Do LLM-proposed structures beat classical sparse regression at the same solver budget? | Evidence the agents add value | The red team may still help classical search; report that |
| RP3 | Does adding the production correction help, beyond anisotropy alone? | Keep both | Ship anisotropy-only; simpler and more stable |
| RP4 | Do gated compositions beat a single closure on canonical flows? | Composer stays central | Drop gates and submit the best single closure |
| RP5 | Which physics attacks actually separate good closures from bad? | Rank attacks; this becomes the audit product | Physics-only grading is too weak; say so |

**RP6:** does the elegance rule (simplest within 3% of the best) generalize better on the locked test than simply picking the most accurate candidate? If yes, that is evidence for the principle; if no, report what elegance cost.

**After the hackathon:** the NASA wall-mounted hump and 3D cases, then the same engine for heat-transfer correlations.

## Phases and tasks until done

**Seven phases, each ending in a gate you can test; don't start a phase until the previous gate passes.** A owns physics and OpenFOAM; B owns agents, API and UI.

### Phase 0: setup (Oct 24 to 25)

- Both: apply before Oct 25, 11:59 PM ET; create GitHub, Kaggle and (once approved) Meta Model API accounts.
- A: build the OpenFOAM Docker image; download the curated dataset; run baseline SST on one periodic hill.
- B: repo skeleton from the folder structure; uv environment; CI with lint and an empty test.
- **Gate:** baseline SST on periodic hills runs in the container from one command.

### Phase 1: foundations (Oct 26 to 27)

- A: write the C++ template class (fixed-field mode for the oracle, generated-code mode for candidates); compile one generated candidate and time it; run the zero-correction and oracle tests.
- B: closure language and its unit tests; data ingestion to Zarr with validation; Model API client with budget meter, event log and replay.
- **Gate:** the oracle test passes, and one hand-written candidate goes from text to an a priori score end to end. If the oracle fails by end of day 2, switch to frozen-RANS-only evaluation.

### Phase 2: ladder and groups (Oct 28 to 29)

- A: short-run and full RANS rungs; physics checks; canonical cases (channel, flat plate).
- B: role prompts and schemas; the round loop with the board; selection score; FastAPI server streaming events.
- **Gate:** one research group completes a full round unattended and every step appears in the event log.

### Phase 3: red team and UI (Oct 30 to 31)

- A: red-team flow generator (hill slopes beyond the data, Reynolds sweeps, bumps) with scripted meshing; attack suite; PyVista renders and the SAM 3.1 client.
- B: Mission control, generalization matrix and candidate inspector, live from the stream.
- **Gate:** the red team breaks at least one candidate and the attack is visible in the UI.

### Phase 4: composer and freeze (Nov 1)

- A and B: composer with gate fitting; a first full multi-group session; fix what it breaks.
- **Gate:** a composed closure is scored on all training flows. Feature freeze at the end of the day.

### Phase 5: experiments (Nov 2 to 3)

- Run the arms in parallel on the two machines: full swarm, swarm without red team, classical sparse-regression baseline; three seeds each.
- Milestone evaluations on the locked test; mesh check on the champion; figures from the notebooks.
- **Gate:** the results table is complete, wins and losses included.

### Phase 6: ship (Nov 4)

- Cut the demo video from Replay around the three demo moments; write the README with how to reproduce each result; submit by early afternoon, well before 9:00 PM.
- **Gate:** submitted.
