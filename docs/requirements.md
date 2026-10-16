# Requirements matrix — Project 13 (INT8/FP8 accelerator)

| Requirement | Status | Evidence |
|---|---|---|
| Systolic GEMM array (parameterisable N) | VERIFIED | N = 8 and N = 4 pass all tests |
| INT8 GEMM with INT32 accumulation | VERIFIED | bit-exact vs model, extremes, partial tiles |
| INT8 requantisation (TFLite/gemmlowp) | VERIFIED | bit-exact incl. ReLU, zero point, bias |
| FP8 E4M3 and E5M2 (OCP) | VERIFIED | bit-exact incl. subnormals, NaN/inf, ties |
| Accuracy analysis | VERIFIED | `bench/accuracy.py`: 0.5 ULP vs 32 ULP (FP32) / overflow (FP16) |
| Performance model + measurement | VERIFIED | cycle-exact schedule; 90.5 % utilisation at K = 256 |
| Synthesis / area (FPGA-style, Yosys generic/ECP5) | VERIFIED | PE + post unit (`make synth`); whole 4×4 top in generic gates (`make synth-top`, 122,840 cells, CI) |
| ASIC synthesis, full top level (sky130hd) | VERIFIED (4×4, 8×8×16 scratchpads) | 100,606 cells, 0.863 mm²; [physical_design.md](physical_design.md), `flow/results/sky130hd_top_n4_p30/` |
| ASIC synthesis, nangate45 | PARTIAL | PE only (INT8 and FP8); the top level was not run on nangate45 |
| Floorplan + placement, full top level | VERIFIED | 49.3 % utilisation of 1.913 mm² core; post-placement WNS −4.04 ns at 30 ns (pre-CTS) |
| CTS + routing + STA sign-off + GDSII, full top level | BLOCKED | CTS runs killed by worker restarts / full disk; not completed |
| Full RTL-to-GDS flow (PE block) | VERIFIED | INT8 and FP8 PE, sky130hd and nangate45, 0 route DRC, routed STA; FP8 PE GDS sha256 in `flow/results/sky130hd_pe_fp8_p10/gds.sha256` |
| STA clock sweep | VERIFIED (PE) / PARTIAL (top) | sky130hd PE: INT8 closes at 8 ns, FP8 at 10 ns; top: placement-stage estimate only |
| Power estimate | VERIFIED (vectorless) | OpenROAD `report_power`, default activity; no VCD/SAIF |
| KLayout DRC / LVS | NOT IMPLEMENTED | not run; only OpenROAD detailed-route DRC (0 violations, PE) |
| Gate-level simulation vs reference model | VERIFIED (synthesised 4×4 top) | 8/8 bit-exact, `evidence/2026-10-15/gls_sky130hd_top_synth_netlist_icarus.log`; routed netlist not simulated |
| Formal equivalence (flow internal) | VERIFIED (PE) | kepler-formal: final FP8 PE netlist IDENTICAL to synthesis netlist |
| Golden model | VERIFIED | `model/npu_ref.py` + its own tests |
| Host interface | VERIFIED (simple port) | no AXI/DMA |
| CI | VERIFIED | `.github/workflows/int8-fp8-accelerator.yml` (run 38706023248 green, incl. `test-small`, `synth-top`) |
