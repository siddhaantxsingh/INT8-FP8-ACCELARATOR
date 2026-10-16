# cocotb 1.9 + Verilator 5.020. Usage: make -C tb [NPU_N=8]
SIM ?= verilator
TOPLEVEL_LANG = verilog
NPU_N ?= 8
VERILOG_SOURCES = $(PWD)/../rtl/npu_pe.sv $(PWD)/../rtl/npu_post.sv $(PWD)/../rtl/npu_top.sv
TOPLEVEL = npu_top
MODULE = test_npu
EXTRA_ARGS += -GN=$(NPU_N) -Wno-fatal --x-assign unique --x-initial unique
SIM_BUILD = sim_build_n$(NPU_N)
include $(shell cocotb-config --makefiles)/Makefile.sim
