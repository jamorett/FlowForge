"""Versioned regression sets per harness capability.

Each set holds one positive control, one negative control, and the
threshold fixed before runs. Changing a threshold requires a new set
version; never tune it after seeing scores. Scaffold only.
"""
