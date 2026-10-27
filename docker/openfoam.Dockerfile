FROM opencfd/openfoam-default:latest
# FlowForge: add compiled correctedKOmegaSST closure class during Phase 1.
# Placeholder scaffold - pin the ESI version closest to dataset v2006 at build time.
WORKDIR /workspace
