# INT8 / FP8 systolic GEMM accelerator

`npu_top` is a parameterisable N×N output-stationary systolic array in SystemVerilog that computes C = A·B in three modes:

- **INT8**, accumulating in INT32, with **TFLite/gemmlowp requantisation** (bias, zero point, ReLU);
- **FP8 E4M3**;
- **FP8 E5M2**.

Both FP8 formats follow the OCP OFP8 spec. FP8 dot products are accumulated **exactly** in an 80-bit fixed-point accumulator and rounded once to FP32, so the results are correctly rounded and independent of summation order. Every output is verified bit-for-bit against a Python golden model with cocotb on Verilator.

**Status:**
- **Done:** verified in RTL simulation (8×8 and 4×4 arrays). Open-PDK ASIC flow (OpenROAD-flow-scripts, sky130hd + nangate45): one PE taken to routed GDSII with STA and a clock sweep; the whole 4×4 top level synthesised (100,606 cells) and placed; the synthesised top-level netlist passes the bit-exact tests in gate-level simulation. See [physical_design.md](docs/physical_design.md).
- **Not done:** CTS/routing/GDSII of the top level, multi-corner sign-off, KLayout DRC/LVS, FPGA, tape-out or silicon. See [limitations](docs/limitations.md).

## Results ([docs/benchmarks.md](docs/benchmarks.md))

| | |
|---|---|
| Verification | 8 cocotb tests × 2 array sizes, every word bit-exact; model self-tests; lint clean |
| Utilisation (8×8, K = 256) | 90.5 % of peak MACs; cycle count = K + 3N + 3 per tile, cycle-exact |
| FP8 accuracy (32×256×32) | **≤ 0.5 ULP** (correctly rounded), against 32 ULP for sequential FP32 and overflow / 26 % error for FP16 accumulation |
| Cost of exact FP8 | PE grows from 49 to 1,031 ECP5 LUT4s (≈ 21×); in sky130hd 7,046 → 24,642 µm² (3.5×) |
| ASIC timing (sky130hd tt, routed PE) | INT8-only PE closes at 125 MHz, INT8 + FP8 PE at 100 MHz; 4×4 top only placed (~29-30 MHz estimate) |

## Layout and use

```
rtl/    npu_pe.sv (PE), npu_post.sv (FP32 rounding, requantisation), npu_top.sv (array, scratchpads, controller)
model/  npu_ref.py: bit-exact golden model, plus tests
tb/     cocotb testbench (test_npu.py) and Makefile
bench/  accuracy study, perf results, report generator
synth/  Yosys area script and results
flow/   open-PDK physical design flow (ORFS in Docker), configs, scripts, small results
```

```bash
python3 -m venv .venv && .venv/bin/pip install cocotb==1.9.2 numpy pytest   # cocotb 2.x needs Verilator >= 5.036
PATH=$PWD/.venv/bin:$PATH make lint model-test test test-n4
make accuracy synth && python3 bench/report.py
```

The register map is documented at the top of `rtl/npu_top.sv`; the dataflow and arithmetic are in [docs/architecture.md](docs/architecture.md). Physical design is in [docs/physical_design.md](docs/physical_design.md) and [flow/README.md](flow/README.md); the scorecard is [docs/scorecard.md](docs/scorecard.md). Verification is described in [docs/testing.md](docs/testing.md), and the requirements matrix is in [docs/requirements.md](docs/requirements.md).
