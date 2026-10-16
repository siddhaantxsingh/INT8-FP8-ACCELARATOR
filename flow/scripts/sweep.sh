#!/usr/bin/env bash
# Clock sweep: run the full ORFS flow (synth -> finish) at each period and
# append one JSON line per run to flow/results/sweep_<platform>_<design>.jsonl.
# Large intermediate files (.odb, .gds, .def, .spef) are deleted after each
# point unless KEEP=1; logs, reports and the final netlist are kept.
# Usage: flow/scripts/sweep.sh <platform> <design> <period_ns>...
set -uo pipefail
plat=$1; design=$2; shift 2
flow=$(cd "$(dirname "$0")/.." && pwd)
runs=${ORFS_RUNS:-$flow/runs}
mkdir -p "$flow/results"
for p in "$@"; do
  tag=p$p
  "$flow/scripts/orfs.sh" "$plat" "$design" "$tag" "$p" finish > "$runs/${plat}_${design}_$tag.log" 2>&1
  echo "make exit $? for $plat $design $p ns" >&2
  python3 "$flow/scripts/collect.py" "$runs/$plat/$design/$tag" "$plat" "$design" "$p" >> "$flow/results/sweep_${plat}_${design}.jsonl"
  if [ "${KEEP:-0}" != 1 ]; then
    find "$runs/$plat/$design/$tag" \( -name '*.odb' -o -name '*.gds' -o -name '*.def' -o -name '*.spef' -o -name '*.rtlil' -o -name 'route.guide' \) -delete
  fi
done
