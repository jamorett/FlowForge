"""Shared agent runtime: model router, budget meter, retries, event-log writes.

All harnesses consume this runtime. They never reimplement auth, retries,
or cost accounting. Scaffold only.
"""
