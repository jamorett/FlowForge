"""Solver harness: foamlib, Docker, field I/O via the ladder.

Pass requires exit code 0, convergence, recorded field hashes, and
logged time and cost. A solver failure is a signal, never swallowed.
Positive control: baseline SST on periodic hills. Negative control:
diverged run; must be scored as failure, not retried silently.
"""
