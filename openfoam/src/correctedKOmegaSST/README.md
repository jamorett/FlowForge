# correctedKOmegaSST (S2.1)

k-omega SST + two corrections: tau_corrected = tau_SST + 2k*aDelta,
Pk_corrected = min(G, 10*betaStar*k*omega) + dPk, clamped >= 0.
Mode A (fixed field): reads volSymmTensorField aDelta and volScalarField
PkDelta from the time directory (oracle/identity tests).
Mode B (compiled): inline C++ emitted by the SymPy compiler per candidate.
All denominators guarded with max(denom, 1e-6). C++ sources are written
against ESI headers in Docker; compile probe first (scratch/probe_wmake.sh).
If compile exceeds 90s or oracle fails Oct 27 EOD, frozen-RANS fallback.
