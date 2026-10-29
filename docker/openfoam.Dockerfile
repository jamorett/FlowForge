# FlowForge OpenFOAM farm image (S1). Build once the Docker daemon runs:
#   docker build -f docker/openfoam.Dockerfile -t flowforge-openfoam:local .
# Then point the runner at it:
#   FLOWFORGE_OPENFOAM_IMAGE=flowforge-openfoam:local
# The base tag is pinned at build time: pick the ESI release closest to the
# dataset's v2006 from the available opencfd/openfoam-default tags
# (list them with `docker search` / Hub tags when the daemon is up) and
# replace `latest` below. The runner default moves with it via
# FLOWFORGE_OPENFOAM_IMAGE; keep the two in sync.
ARG OPENFOAM_TAG=latest
FROM opencfd/openfoam-default:${OPENFOAM_TAG}
# FlowForge: compile the correctedKOmegaSST closure class into the image.
WORKDIR /workspace
COPY openfoam/src/correctedKOmegaSST /workspace/openfoam/src/correctedKOmegaSST
# Verified against opencfd/openfoam-default (ESI v2512):
#   bashrc at /usr/lib/openfoam/openfoam2512/etc/bashrc,
#   wmake/blockMesh/simpleFoam only on PATH after sourcing it.
RUN . /usr/lib/openfoam/openfoam2512/etc/bashrc && cd /workspace/openfoam/src/correctedKOmegaSST && wmake libso
# Farm workers idle until given a case; the runner invokes:
#   docker run --rm -v <case>:/case <image> bash -lc "cd /case && blockMesh && simpleFoam"
CMD ["sleep", "infinity"]
