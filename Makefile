# int8-fp8-accelerator entry points (see README.md and flow/README.md)
.PHONY: lint test test-n4 test-small model-test accuracy synth synth-top
lint:
	verilator --lint-only -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM \
	  rtl/npu_pe.sv rtl/npu_post.sv rtl/npu_top.sv --top-module npu_top
model-test:
	python3 -m pytest -q model/tests
test:
	NPU_PERF_OUT=$(CURDIR)/bench/results/perf_n8.txt $(MAKE) -C tb NPU_N=8
test-n4:
	NPU_PERF_OUT=$(CURDIR)/bench/results/perf_n4.txt $(MAKE) -C tb NPU_N=4
# physical-design configuration (N=4, 8x8x16 scratchpads), RTL
test-small:
	$(MAKE) -C tb -f Makefile.small
accuracy:
	python3 bench/accuracy.py
synth:
	mkdir -p synth/results && yosys -q -s synth/area.ys
# whole top level of the physical configuration, generic gates (sv2v + Yosys)
synth-top:
	flow/scripts/sv2v.sh npu_top_pd flow/build/npu_top_pd.v flow/src/npu_top_pd.sv
	mkdir -p synth/results && yosys -q -p "read_verilog flow/build/npu_top_pd.v; synth -top npu_top_pd -flatten; tee -o synth/results/top_n4_generic.txt stat"
