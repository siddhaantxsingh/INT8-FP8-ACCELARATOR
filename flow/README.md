# Open-PDK physical design flow (ORFS in Docker)

This folder takes the RTL through synthesis, floorplan, placement, clock tree
synthesis, routing, static timing analysis, power estimation and GDSII with
[OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)
(ORFS). It targets open, academic PDKs: **sky130hd** (SkyWater 130 nm) as the
main platform and **nangate45** (a 45 nm predictive library) as a second data
point.

**This is not a tape-out.** No foundry sign-off decks, no multi-corner
sign-off, no silicon. Results show that the RTL can be implemented and roughly
what it costs. They are not production numbers.

Results for this project are in [`results/`](results/) and are explained in
[`../docs/physical_design.md`](../docs/physical_design.md).

## Layout

```
flow/
  src/                 wrappers that fix the parameters of the physical configuration
  designs/<platform>/<design>/config.mk   ORFS design configs
  designs/common/constraint.sdc           one SDC; clock period from $CLK_PERIOD_NS
  scripts/sv2v.sh      SystemVerilog -> Verilog-2005 (sv2v v0.0.12, sha256 pinned)
  scripts/orfs.sh      runs ORFS `make` inside the openroad/orfs image (pinned by digest)
  scripts/sweep.sh     clock sweep: full flow per period, one JSON line per point
  scripts/collect.py   reads ORFS metric JSON files into one summary line
  scripts/gls.sh       gate-level simulation of a netlist with cell models (cocotb)
  results/             small committed outputs (metrics, reports, PNGs, hashes)
  build/, runs/        generated, git-ignored (runs/ holds GBs of .odb files)
```

## Requirements

* Docker, about 7 GB for the image and 1-3 GB per full run of a 100k-cell design.
* The image `openroad/orfs@sha256:26aa080a55be1fe9ad5befeaa01d0ff6d72c24bdd6c949986ba4448543453dd5`
  (pulled from Docker Hub on 2026-10-14 as `openroad/orfs:latest`; Yosys 0.68,
  OpenROAD, KLayout inside). Set `ORFS_IMAGE` to use another tag.
* For gate-level simulation on the host: Verilator 5.020, Icarus Verilog,
  Yosys (0.33 works), Python with cocotb 1.9.2.

## Steps

```bash
# 1. Convert the RTL (the ORFS Yosys reads plain Verilog most reliably).
flow/scripts/sv2v.sh npu_top_pd flow/build/npu_top_pd.v flow/src/npu_top_pd.sv

# 2. Full flow at one clock period (ns). Stages: synth floorplan place cts route finish.
flow/scripts/orfs.sh sky130hd npu_top_n4 p30 30 finish
#    Optional sign-off style checks after finish (KLayout):
flow/scripts/orfs.sh sky130hd npu_top_n4 p30 30 drc lvs

# 3. Summarise.
python3 flow/scripts/collect.py flow/runs/sky130hd/npu_top_n4/p30 sky130hd npu_top_n4 30

# 4. Clock sweep (small blocks): full flow per period, intermediates deleted.
flow/scripts/sweep.sh sky130hd npu_pe_fp8 10 9 8 7

# 5. Gate-level simulation of the routed netlist against the reference model.
LIB=<sky130_fd_sc_hd__tt_025C_1v80.lib> flow/scripts/gls.sh \
  flow/runs/sky130hd/npu_top_n4/p30/results/sky130hd/npu_top_n4/base/6_final.v route lib
SKY130_HD=<skywater-pdk-libs-sky130_fd_sc_hd checkout> flow/scripts/gls.sh <6_final.v> route_sky skywater
```

Run outputs land in `flow/runs/<platform>/<design>/<tag>/{logs,reports,results}/<platform>/<design>/base/`.
The useful files are:

| file | content |
|---|---|
| `logs/.../6_report.json` | final metrics: setup/hold WNS and TNS, fmax, area, utilisation, power |
| `logs/.../5_2_route.json` | detailed-route DRC violation count |
| `reports/.../6_finish.rpt` | OpenSTA report: worst paths, slew/cap checks, power |
| `reports/.../final_*.webp.png` | layout screenshots (placement, routing, clocks, IR drop) |
| `results/.../6_final.v`, `6_final.gds`, `6_final.spef` | routed netlist, GDSII, parasitics |
| `logs/.../6_final_lec_check.log` | formal equivalence of the final netlist (kepler-formal) |

## Reusing this for another design (for example a RISC-V core)

1. Copy `scripts/` and `designs/common/constraint.sdc`. Nothing in them is
   specific to this accelerator except `sv2v.sh`, which lists the RTL files:
   edit that list.
2. Write a wrapper in `src/` if the top level has parameters, so the
   physical configuration is explicit and simulable.
3. Add `designs/<platform>/<name>/config.mk` with `DESIGN_NAME`,
   `DESIGN_NICKNAME`, `VERILOG_FILES=/work/build/<name>.v`,
   `SDC_FILE=/work/designs/common/constraint.sdc`, `CORE_UTILIZATION`
   (start at 40-50) and `PLACE_DENSITY` (0.6-0.65).
4. Memories: flip-flop arrays work for a few KiB at most. Larger memories need
   macros (nangate45 has `fakeram45_*` models; sky130 needs OpenRAM or the
   sky130 SRAM macros) and `ADDITIONAL_LEF/LIB/GDS` in `config.mk`.
5. Start with a relaxed clock, read the floorplan-stage WNS in
   `2_1_floorplan.json`, then sweep. Measured here on a shared 4-vCPU VM: a
   100k-cell sky130hd design took 36 min to synthesise, 5 min to floorplan
   and ~25 min to place (CTS and routing were not completed); a 3k-cell PE
   ran the whole flow in about 10-15 min. Each ORFS stage writes a 70-150 MB
   .odb for a 100k-cell design, so keep several GB of disk free.
6. Gate-level simulation: `scripts/gls.sh` needs a cocotb test whose top
   level matches the netlist's top. Clock-to-Q delay comes from the SkyWater
   models' `UNIT_DELAY`; everything else is zero delay, so this checks logic,
   not timing.

## Known limits of this flow

* One timing corner per platform: ORFS ships only `tt_025C_1v80` for
  sky130hd and `typical` for nangate45. No slow/fast corner sign-off.
* Power is a vectorless estimate (default switching activity in OpenROAD),
  not based on a simulation trace.
* KLayout DRC/LVS decks in ORFS are the platform's open decks, not foundry
  sign-off decks.
