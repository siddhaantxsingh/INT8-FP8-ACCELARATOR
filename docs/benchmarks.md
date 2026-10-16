# Benchmarks

Rendered by `python3 bench/report.py` from `bench/results/` and `synth/results/`. Reproduce with `make test test-n4 accuracy synth`.

## Throughput (cycle-exact RTL simulation; INT8 and FP8 identical)

Utilisation = M·N·K / (cycles × N²). The testbench asserts that the cycle counts equal the schedule (K + 3N + 3 per tile) exactly.

| array | M×N×K | cycles | MAC utilisation |
|---|---|---|---|
| 8×8 | 8×8×16 | 43 | 37.2 % |
| 8×8 | 8×8×256 | 283 | 90.5 % |
| 8×8 | 16×16×64 | 364 | 70.3 % |
| 8×8 | 64×64×256 | 18,112 | 90.5 % |
| 4×4 | 4×4×16 | 31 | 51.6 % |
| 4×4 | 4×4×256 | 271 | 94.5 % |
| 4×4 | 8×8×64 | 316 | 81.0 % |
| 4×4 | 64×64×256 | 69,376 | 94.5 % |

At a clock of f MHz, an 8×8 array delivers 64·f·utilisation MAC/s. Timing comes from the open-PDK flow in [physical_design.md](physical_design.md): a single PE closes at 100 MHz (INT8 + FP8) or 125 MHz (INT8 only) in sky130hd typical; the 4×4 top level was only placed, with an estimated ~29-30 MHz limited by the un-pipelined post unit.

## Accuracy of FP8 accumulation (32×256×32, Gaussian data quantised per tensor)

| format | accumulation | max error (ULP of FP32) | mean error (ULP) | max relative error |
|---|---|---|---|---|
| E4M3 | exact + one FP32 rounding (this design) | 0.5 | 0.010 | 5.94e-08 |
| E4M3 | sequential FP32 | 32.0 | 0.081 | 1.97e-06 |
| E4M3 | sequential FP16 | 2,307,072.0 | 53,437.401 | 2.58e-01 |
| E5M2 | exact + one FP32 rounding (this design) | 0.5 | 0.010 | 5.80e-08 |
| E5M2 | sequential FP32 | 8.0 | 0.037 | 5.82e-07 |
| E5M2 | sequential FP16 | overflow | overflow | overflow |

FP8 quantisation itself costs 3.6 % (E4M3) and 7.6 % (E5M2) mean error relative to the float64 GEMM. Accumulation error comes on top of that; with FP16 accumulation it dominates.

## Area (Yosys 0.33; no timing)

| block | generic cells | ECP5 LUT4 | ECP5 FF | ECP5 carry (CCU2C) | DSP |
|---|---|---|---|---|---|
| PE, INT8 only (32-bit accumulator) | 815 | 49 | 52 | 16 | 1 |
| PE, INT8 + FP8 (80-bit exact accumulator) | 2,358 | 1,031 | 100 | 90 | 1 |
| post unit (FP32 rounding + INT32 requantisation), per column | 12,478 | — | — | — | — |

Exact FP8 accumulation makes each PE about 21× larger in LUTs than an INT8-only PE. The 80-bit barrel shifter and adder dominate. The full `npu_top` was not synthesised: its 48 KiB of scratchpad are behavioural arrays and would need BRAM macros.


## ASIC (sky130hd typical, OpenROAD-flow-scripts; academic PDK, no sign-off)

Details and the full sweep: [physical_design.md](physical_design.md).

| block | stage reached | cell area | fastest closed clock | power at 10 ns (vectorless) |
|---|---|---|---|---|
| PE, INT8 only | routed, GDS | 7,046 µm² (10 ns) | 125 MHz (8 ns) | 1.48 mW |
| PE, INT8 + FP8 | routed, GDS | 24,642 µm² (10 ns) | 100 MHz (10 ns) | 9.69 mW |
| top level 4×4, 8×8×16 scratchpads | detailed placement | 942,404 µm² placed (100,606 cells synthesised) | not closed; −4.04 ns at 30 ns before CTS | — |

In sky130hd the exact-FP8 PE costs 3.5× the area of the INT8-only PE (2.8× in nangate45), not 21× as the ECP5 LUT count suggests.
