# FlowForge OpenFOAM farm image (S1). Build once the Docker daemon runs:
#   docker build -f docker/openfoam.Dockerfile -t flowforge-openfoam:local .
# flowforge-openfoam:local is the runner's default image
# (FLOWFORGE_OPENFOAM_IMAGE overrides it).
# The base tag is pinned to ESI v2512: the RUN line below hard-codes the
# openfoam2512 bashrc path, so `latest` breaks the build as soon as a new
# release is tagged. Bump both together.
ARG OPENFOAM_TAG=2512
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
