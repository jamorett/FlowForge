"""Agent layer: runtime, tools, harnesses, evals.

runtime/ is the shared model router, budget meter, and retries.
tools/ is the typed tool registry. harness/ holds the four capability
loops (research, physics, symbolic, solver). evals/ holds versioned
regression sets with thresholds fixed before runs.
"""
