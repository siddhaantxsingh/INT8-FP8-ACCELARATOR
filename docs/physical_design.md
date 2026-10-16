# Physical design (open-PDK, academic flow)

**Scope warning.** This is an open-source flow (OpenROAD-flow-scripts) on
academic PDKs: SkyWater sky130hd and Nangate45. There is no tape-out and no
silicon. Only one timing corner was available per platform. Power numbers are
vectorless estimates. Read every number as "what this RTL roughly costs", not
as sign-off.

How to run it: [`../flow/README.md`](../flow/README.md). Raw outputs:
[`../flow/results/`](../flow/results/). Logs: [`evidence/`](evidence/).

## Tools

| tool | version |
|---|---|
| ORFS image | `openroad/orfs@sha256:26aa080a55be1fe9ad5befeaa01d0ff6d72c24bdd6c949986ba4448543453dd5` (pulled 2026-10-14 as `latest`) |
| Yosys (inside ORFS) | 0.68 |
| sv2v | v0.0.12 (zip sha256 `ff8c9eea…5a00`) |
| Gate-level sim | Icarus Verilog + cocotb 1.9.2 (host) |
| Timing library | sky130hd `tt_025C_1v80` only; nangate45 `typical` only |

The machine was a shared 4-vCPU VM. Load averages reached 19-43 during the
runs, and the worker was restarted three times, killing running jobs.

## Configuration that was built

The default `npu_top` (8×8 array, 64×64×256 scratchpads = 48 KiB) cannot be
built from flip-flops in reasonable time. The flow builds
`flow/src/npu_top_pd.sv`:

* **N = 4** (4×4 PEs), **MAX_M = MAX_N = 8, MAX_K = 16**, ACC_W = 80 (exact FP8 kept).
* Storage as flip-flops: A 128 B, B 128 B, C 256 B, bias 32 B.
* Same port list and register map as `npu_top`.

`tb/test_small.py` (8 bit-exact cocotb tests, every word compared with
`model/npu_ref.py`) passes on this configuration's RTL (`make test-small`,
also in CI).

## Results: full top level (4×4) on sky130hd

| stage | status | numbers |
|---|---|---|
| Synthesis (Yosys 0.68 / ABC) | VERIFIED | 100,606 cells, 863,408 µm² cell area (20 % sequential); 36 min under load |
| Gate-level sim of the synthesised netlist | VERIFIED | 8/8 tests bit-exact (Icarus, Liberty-derived cell models), 11 min 56 s |
| Floorplan (30 ns target) | VERIFIED | core 1.913 mm², 45 % target utilisation; floorplan-stage WNS +0.015 ns (no wire parasitics yet) |
| Global + detailed placement | VERIFIED | 126,152 cells (incl. tap/buffers), 942,404 µm², **utilisation 49.3 %**; **WNS −4.04 ns, TNS −7,056 ns** at 30 ns (ideal clock, before CTS and post-placement repair) |
| CTS, routing, STA sign-off, GDSII | **NOT COMPLETED** | CTS was started twice; both runs were killed by worker restarts (once also by a full disk). Not re-run because of the time budget |
| KLayout DRC / LVS | NOT RUN | |
| Gate-level sim of the routed netlist | NOT RUN | no routed netlist |

**Critical path after placement** (reg to reg, 33.85 ns arrival): the tile
column counter `tn` → bias index `bias[(tn + c) % MAX_N]` → the
combinational INT32 add, 32×32 requantisation multiplier and rounding in
`npu_post` → C scratchpad write. At the 30 ns target this suggests the 4×4
top level runs at about **29-30 MHz** in sky130hd typical. That number is a
pre-CTS estimate, not a closed timing result. Pipelining `npu_post` (or
registering the bias read) is the obvious fix.

Earlier synthesis point: at a 20 ns target, the floorplan-stage WNS was
−7.94 ns (evidence `evidence/2026-10-14/sky130hd_top_n4_synth_p20/`).

## Results: one PE, INT8-only vs INT8 + exact FP8 (full RTL-to-GDS)

The PE is small enough for the whole flow, so these runs went through
synthesis, floorplan, placement, CTS, global and detailed routing, parasitic
extraction, final STA, power and GDSII. Clock sweep: one full flow per
period. "Closes" = setup and hold WNS ≥ 0 after routing and 0 detailed-route
DRC violations.

### sky130hd (tt_025C_1v80)

| PE | period (ns) | cell area (µm²) | utilisation | setup WNS (ns) | hold WNS (ns) | route DRC | power (mW) | closes |
|---|---|---|---|---|---|---|---|---|
| INT8 only | 10 | 7,046 | 58 % | +1.19 | +0.50 | 0 | 1.48 | yes |
| INT8 only | 8 | 7,965 | 66 % | +0.26 | +0.49 | 0 | 2.37 | **yes (fastest)** |
| INT8 only | 7 | 8,444 | 70 % | −0.17 | +0.49 | 0 | 2.86 | no |
| INT8 only | 6 | 8,786 | 73 % | −1.04 | +0.49 | 0 | 3.57 | no |
| INT8 only | 5 | 8,984 | 74 % | −1.81 | +0.50 | 0 | 4.28 | no |
| INT8 + FP8 | 10 | 24,642 | 67 % | +0.24 | +0.58 | 0 | 9.69 | **yes (fastest)** |
| INT8 + FP8 | 9 | 26,542 | 72 % | −0.35 | +0.58 | 0 | 11.93 | no |

* **Highest clock that closed:** INT8-only PE 125 MHz (8 ns); INT8 + FP8 PE 100 MHz (10 ns).
* **Area:** the exact-FP8 PE is **3.5×** the INT8-only PE at 10 ns (24,642 vs 7,046 µm²).
  The earlier ECP5 LUT ratio (21×) overstated the ASIC cost because the INT8
  multiplier maps to a DSP block on the FPGA.
* **Formal check:** ORFS's equivalence check (kepler-formal) reports the final
  FP8 PE netlist (10 ns) IDENTICAL to the synthesised netlist.
* GDSII of the FP8 PE at 10 ns: 3,811,132 bytes, sha256
  `cea5631221865e19a7476131ace00ea3c60918d8835831b328fddf951b16cd47`
  (not committed). Placement and routing screenshots:
  `flow/results/sky130hd_pe_fp8_p10/final_placement.png`, `final_routing.png`.

### nangate45 (typical), second data point

| PE | period (ns) | cell area (µm²) | setup WNS (ns) | hold WNS (ns) | route DRC | power (mW) | closes |
|---|---|---|---|---|---|---|---|
| INT8 only | 4 | 1,288 | +1.75 | +0.11 | 0 | 0.81 | yes |
| INT8 only | 3 | 1,287 | +0.95 | +0.11 | 0 | 1.07 | yes |
| INT8 + FP8 | 5 | 3,646 | +1.91 | +0.11 | 0 | 3.30 | yes |
| INT8 + FP8 | 4 | 3,644 | +1.12 | +0.11 | 0 | 4.10 | yes |

Every nangate45 point closed, so the tightest periods tried (3 ns INT8, 4 ns
FP8) are lower bounds on the maximum clock, not the maximum. Area ratio FP8 /
INT8: 2.8×.

## Power

All power numbers are OpenROAD `report_power` after routing with **default
(vectorless) switching activity**, typical corner, at the stated clock. No
VCD/SAIF from simulation was fed in. They are useful for comparing INT8 with
FP8 at the same clock, not as absolute power.

## Utilisation re-check

* **MAC utilisation:** the gate-level simulation of the synthesised 4×4
  netlist runs `small_cycle_counts`, which asserts cycle counts equal to the
  schedule K + 3N + 3 per tile. It passes, so the cycle model (and the
  utilisation numbers in `benchmarks.md`) hold for the synthesised gates.
* **Placement utilisation:** 49.3 % of a 1.913 mm² core for the 4×4 top;
  58-74 % for the PE runs.

## Gate-level simulation method

`flow/scripts/gls.sh` simulates a netlist with cocotb and `tb/test_small.py`.
Cell models are generated from the sky130hd Liberty file with
`yosys read_liberty` (functional, zero delay; flip-flops use non-blocking
assignments, so buffered clocks do not race). The script can also use the
official SkyWater `sky130_fd_sc_hd` functional (UDP) models with Icarus; that
path was set up but **not run to completion** on the 100k-cell netlist.
