#!/usr/bin/env bash
# Convert the SystemVerilog RTL to Verilog-2005 with sv2v, so that any Yosys
# (0.33 from Ubuntu, or the one inside the ORFS image) can read it.
# Usage: flow/scripts/sv2v.sh <top> <out.v> <extra .sv files...>
# sv2v v0.0.12 is downloaded once (sha256 pinned) into $SV2V_HOME.
set -euo pipefail
top=$1; out=$2; shift 2
here=$(cd "$(dirname "$0")/../.." && pwd)        # project root
SV2V_HOME=${SV2V_HOME:-$HOME/.cache/sv2v-0.0.12}
SV2V=$SV2V_HOME/sv2v-Linux/sv2v
if [ ! -x "$SV2V" ]; then
  mkdir -p "$SV2V_HOME"
  curl -sSL -o "$SV2V_HOME/sv2v.zip" https://github.com/zachjs/sv2v/releases/download/v0.0.12/sv2v-Linux.zip
  echo "ff8c9eea5bc029b372fb4953427625cddb7cf7e58c1240623ac9f260818d5a00  $SV2V_HOME/sv2v.zip" | sha256sum -c -
  (cd "$SV2V_HOME" && unzip -o -q sv2v.zip)
fi
mkdir -p "$(dirname "$out")"
"$SV2V" --top="$top" "$here/rtl/npu_pe.sv" "$here/rtl/npu_post.sv" "$here/rtl/npu_top.sv" "$@" > "$out"
echo "sv2v: wrote $out ($(wc -l < "$out") lines)"
