#!/usr/bin/env bash
# Gate-level simulation of an ORFS netlist against the bit-exact reference
# model (tb/test_small.py, 8 cocotb tests, every output word compared).
#
# Usage: flow/scripts/gls.sh <netlist.v> <tag> <models>
#   models = lib       Icarus (or GLS_SIM=verilator) + functional models generated from the PDK
#                      Liberty file by Yosys read_liberty (sky130hd or nangate45).
#                      Needs LIB=<liberty file>.
#   models = skywater  Icarus Verilog + the official SkyWater sky130_fd_sc_hd
#                      functional models (UDP based; FUNCTIONAL, UNIT_DELAY=#1 on
#                      flip-flops only). Needs SKY130_HD=<checkout of
#                      google/skywater-pdk-libs-sky130_fd_sc_hd>.
# Zero-delay functional simulation: this checks logic, not timing (timing is
# signed off by OpenSTA in the flow).
set -euo pipefail
net=$(readlink -f "$1"); tag=$2; models=$3
root=$(cd "$(dirname "$0")/../.." && pwd)
work=$root/flow/build/gls_$tag
mkdir -p "$work"
# Cells used by the netlist (module names starting with the library prefix).
grep -oE '^\s*(sky130_fd_sc_hd__[a-z0-9_]+|[A-Z][A-Z0-9]*_X[0-9]+)\s' "$net" | awk '{print $1}' | sort -u > "$work/cells.txt"
echo "netlist uses $(wc -l < "$work/cells.txt") cell types"
case $models in
  lib)
    : "${LIB:?set LIB to the Liberty file}"
    yosys -q -p "read_liberty -ignore_miss_func -ignore_miss_dir $LIB; write_verilog -noattr $work/cells_lib.v"
    # physical-only cells (tap, fill, decap, antenna) have no function: keep them as empty modules
    missing=$(comm -23 "$work/cells.txt" <(grep -oE '^module [A-Za-z0-9_]+' "$work/cells_lib.v" | awk '{print $2}' | sort -u))
    : > "$work/cells_phys.v"
    for c in $missing; do
      case $c in
        *tap*|*fill*|*decap*|*FILL*|*TAP*|*diode*|*ANTENNA*) echo "module $c(); endmodule" >> "$work/cells_phys.v" ;;
        *) echo "ERROR: no functional model for $c" >&2; exit 1 ;;
      esac
    done
    if [ "${GLS_SIM:-icarus}" = verilator ]; then extra="-Wno-MULTIDRIVEN"; else extra=""; fi
    make -C "$root/tb" -f Makefile.small SIM="${GLS_SIM:-icarus}" SMALL_TAG="$tag" \
      SMALL_SRC="$net $work/cells_lib.v $work/cells_phys.v" SMALL_EXTRA="$extra"
    ;;
  skywater)
    : "${SKY130_HD:?set SKY130_HD to the sky130_fd_sc_hd checkout}"
    : > "$work/cells_sky.v"
    for c in $(cat "$work/cells.txt"); do
      base=${c#sky130_fd_sc_hd__}; base=${base%_*}
      f=$SKY130_HD/cells/$base/$c.v
      [ -f "$f" ] || { echo "ERROR: no model file $f" >&2; exit 1; }
      echo "\`include \"$f\"" >> "$work/cells_sky.v"
    done
    make -C "$root/tb" -f Makefile.small SIM=icarus SMALL_TAG="$tag" \
      SMALL_SRC="$work/cells_sky.v $net" \
      SMALL_EXTRA="-grelative-include -DFUNCTIONAL -DUNIT_DELAY=#1"
    ;;
  *) echo "models must be lib or skywater" >&2; exit 2 ;;
esac
