# Scorecard (2026-10-15)

| dimension | score | why not higher |
|---|---|---|
| Fresher-portfolio strength | 8 / 10 | Strong verified RTL and an open-PDK flow, but the full top level never reached routing or GDSII. |
| Engineering maturity | 7 / 10 | Bit-exact tests in CI and gate-level sim of the synthesised top; no routed-netlist GLS, no SDF timing sim, no coverage, single corner. |
| Deployment readiness | 2 / 10 | Not on FPGA or silicon; the top level misses timing at 30 ns before CTS and its scratchpads need SRAM macros. |
| Completion of intended scope | 6 / 10 | Reference, array, buffers, synthesis, placement and PE-level PnR/STA/GDS done; top-level CTS/route/GDS, DRC/LVS and VCD-based power not done. |
