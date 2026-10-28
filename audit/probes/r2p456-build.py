import json, pathlib
base = pathlib.Path(__file__).resolve().parents[2]
r1 = base/"audit/round-1"; r2 = base/"audit/round-2"
def load(n): return json.loads((r1/n).read_text())
def save(n,data): (r2/n).write_text(json.dumps(data,indent=2)+"\n"); print(n, len(data))
p4=load('phase-4.json')
for row in p4:
 if row['id']=='P4-01':
  row['requirement']='S6.2 gated formula KERNEL ONLY (narrowed Round-2): a_comp=sigma(w.I+b)*M1+(1-sigma)*M2, sigma=sigmoid, scalar I broadcast (plan docs/plans/2026-10-26-flowforge-v2-implementation-plan.md:399 S6.2). Penalty-in-selection and all-flows scoring are NOT in this row (P4-05/P4-06).'
  row['status']='VERIFIED'
  row['evidence']='Round-2 probe audit/probes/r2p456-probe.py exit 0: compose(ones,zeros,[0,1],w=1,b=0)=[0.5,0.731059] matches independent sigmoid oracle; gates.py:16-18,25-48. Kernel held per challenges.md CH-06 held part.'
  row['gap']='Kernel only: scalar w,b and single scalar I, no vector w.I. Saturation clip-approximate. Downstream defects excluded from this narrowed verdict and carried in P4-05 (penalty dropped) and P4-06 (zip drops last flow).'
 if row['id']=='P4-02':
  row['requirement']='S6.2 +16 bits DL penalty RETURNED per active gate (narrowed Round-2 to return-value only; application in selection is P4-05) (plan S6.2, FORBIDDEN Free Gating).'
  row['status']='VERIFIED'
  row['evidence']='r2p456-probe.py exit 0: compose penalty=16.0; evaluate 3 modules dl_penalty_bits=32.0 n_gates=2; gates.py:13,20-22,48.'
  row['gap']='VERIFIED only as returned number. Penalty is computed then dropped before description_length/pick_champion (probe dl_params=[n_nodes,constants], dl_has_gate=False) - see P4-05 MISSING. Always charged even if w=0 makes gate constant.'
 if row['id']=='P4-06':
  row['evidence']=row['evidence']+' Round-2 r2p456-probe.py exit 0 re-proved zip bug: 3 zero modules targets [0,0,99] -> worst_error=0.0 best_single_worst=9801.0 beats_single=True dl=32.0 (evaluate.py:23 zip(preds,targets) drops last flow).'
  row['gap']=row['gap']+' CH-06 UPHELD: fix zip/comparand with last-flow regression test before any upgrade.'
 if row['id']=='P4-07':
  row['evidence']=row['evidence']+' Round-2 CH-12: kept PRESENT_UNTESTED, not upgraded (pytest exit 1 in r2p456-probe).'
 if row['id']=='P4-12':
  row['evidence']=row['evidence']+' Round-2 r2p456-probe pytest exit 1 No module named pytest; CH-12 kept PRESENT_UNTESTED.'
p4.append({'id':'P4-13','requirement':'OM-7 Phase-4 feature freeze as dated gate artefact (Nov 1 EOD freeze: no refactoring/new roles/algorithm changes after freeze; plan:445,459)','status':'MISSING','evidence':'r2p456-probe.py exit 0: feature-freeze hits only in docs/plans/2026-10-26-flowforge-v2-implementation-plan.md:445,459 (definition), no dated freeze artefact/tag/manifest in docs/configs/flowforge/scripts; round-1 had no OM-7 row (challenges.md OM-7).','gap':'No artefact proves freeze date, frozen commit/hash, or scope. Add dated freeze record (commit hash + date) at Phase-4 gate; until then gate cannot be audited.'})
save('phase-4.json',p4)
p5=load('phase-5.json')
for row in p5:
 if row['id']=='P5-05':
  row['status']='PRESENT_UNTESTED'
  row['requirement']='Stub-scan reconciliation: run_arms mock vs real - BOOKKEEPING-ONLY, NEVER REPORTABLE AS RESULTS (mock scores are len(arm)/seed formula; real returns [] + needs S1-S6)'
  row['evidence']='Round-2 r2p456-probe.py exit 0 via subprocess(timeout=120): --mock swarm mean6.0 runs[5,6,7], swarm_no_redteam 17.0, sparse_baseline 16.0; real mode all arms needs verified S1-S6. scripts/run_arms.py:29,33. Downgraded from round-1 VERIFIED per CH-03.'
  row['gap']='Justification for PRESENT_UNTESTED not SKELETON: summarize() bookkeeping (assert 3 seeds, mean/stdev) is real executable code re-executed here, so more than shape; but no pytest pass (pytest absent exit1), no candidate/case/solver/DNS content, mock numbers are formula artefacts and must never be quoted as results. Any results table citing them would be synthetic-as-real.'
 if row['id']=='P5-08':
  row['evidence']=row['evidence']+' Round-2 CH-12: kept PRESENT_UNTESTED, not upgraded.'
p5.append({'id':'P5-17','requirement':'OM-2 Agent-layer metrics tracked per prompt version: schema-valid rate, parse rate, duplicate rate, cost per round (spec Tests layer)','status':'MISSING','evidence':'r2p456-probe.py exit 0: metrics-keyword hits only docs/plans plan text and flowforge/agents/evals/thresholds.py:4 RESEARCH_MIN_PARSE_RATE=0.95 (a frozen threshold constant, not tracking). No per-prompt-version metric collection, storage, or report in flowforge/scripts; round-1 had no OM-2 row (challenges.md OM-2). Schemas exist (agents/schemas.py) but metrics do not.','gap':'No metric is computed per prompt version; cannot detect prompt regressions or cost drift. Add metrics emitter keyed by prompt version/hash before claiming agent-layer quality.'})
save('phase-5.json',p5)
p6=load('phase-6.json')
for row in p6:
 if row['id']=='P6-07':
  row['status']='PRESENT_UNTESTED'
  row['requirement']='Replay mode zero-token: FLOWFORGE_REPLAY=1 returns recorded responses, miss=error, no network (plan S4.4; client.py/event_logger.py) - full ModelRuntime path'
  row['evidence']='Round-2 r2p456-probe.py exit 0: EventLogger part HELD - replay_hit {text:world}, replay_miss RuntimeError live calls forbidden, replay_off None (event_logger.py:49-76). BUT ModelRuntime part never executed: tenacity_present=False, ModelRuntime import ModuleNotFoundError: No module named tenacity (client.py:17), so client.py:91-101 _complete_replay / complete_structured replay never ran. Downgraded VERIFIED->PRESENT_UNTESTED per CH-02.'
  row['gap']='Proof needed: with deps installed, FLOWFORGE_REPLAY=1 through ModelRuntime.complete_structured returns recorded response with zero network and miss raises. Until then only EventLogger lookup is verified, not the client replay path.'
save('phase-6.json',p6)
