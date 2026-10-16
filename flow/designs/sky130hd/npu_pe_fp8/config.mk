# ORFS design config: one processing element, INT8 + FP8 (80-bit exact accumulator)
export DESIGN_NAME     = npu_pe_fp8
export DESIGN_NICKNAME = npu_pe_fp8
export PLATFORM        = sky130hd
export VERILOG_FILES = /work/build/npu_pe_fp8.v
export SDC_FILE      = /work/designs/common/constraint.sdc
export CORE_UTILIZATION ?= 45
export PLACE_DENSITY    ?= 0.65
export TNS_END_PERCENT  = 100
