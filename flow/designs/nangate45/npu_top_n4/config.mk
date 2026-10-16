# ORFS design config: npu_top, 4x4 array, 8x8x16 scratchpads (see flow/src/npu_top_pd.sv)
export DESIGN_NAME     = npu_top_pd
export DESIGN_NICKNAME = npu_top_n4
export PLATFORM        = nangate45

# Verilog-2005 produced by flow/scripts/sv2v.sh (mounted at /work in the container)
export VERILOG_FILES = /work/build/npu_top_pd.v
export SDC_FILE      = /work/designs/common/constraint.sdc

export CORE_UTILIZATION ?= 45
export PLACE_DENSITY    ?= 0.60
export TNS_END_PERCENT  = 100
