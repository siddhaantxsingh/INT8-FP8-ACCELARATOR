#!/usr/bin/env bash
# Run OpenROAD-flow-scripts (ORFS) in the openroad/orfs Docker image.
# Usage: flow/scripts/orfs.sh <platform> <design> <tag> <clk_ns> [make targets/vars...]
#   e.g. flow/scripts/orfs.sh sky130hd npu_top_n4 p20 20 finish
# Run outputs (large) go to $ORFS_RUNS/<platform>/<design>/<tag> (default flow/runs, git-ignored).
# The image is pinned by digest in ORFS_IMAGE; override to try a newer ORFS.
set -euo pipefail
plat=$1; design=$2; tag=$3; clk=$4; shift 4
flow=$(cd "$(dirname "$0")/.." && pwd)
ORFS_IMAGE=${ORFS_IMAGE:-openroad/orfs@sha256:26aa080a55be1fe9ad5befeaa01d0ff6d72c24bdd6c949986ba4448543453dd5}
ORFS_RUNS=${ORFS_RUNS:-$flow/runs}
mkdir -p "$ORFS_RUNS/$plat/$design/$tag"
exec docker run --rm --name "orfs_${plat}_${design}_${tag}" \
  -v "$flow:/work" -v "$ORFS_RUNS:/runs" -e CLK_PERIOD_NS="$clk" \
  "$ORFS_IMAGE" bash -c "source /OpenROAD-flow-scripts/env.sh >/dev/null && \
    make -C /OpenROAD-flow-scripts/flow DESIGN_CONFIG=/work/designs/$plat/$design/config.mk \
      WORK_HOME=/runs/$plat/$design/$tag NUM_CORES=${NUM_CORES:-4} $*"
