# Owner actions

Steps only the owner can do, or that need more machine time than the
development session had. Each step says what to run, what to expect and what
to save.

## 1. Re-run the physical design flow locally

Needs Docker, about 10 GB of free disk and 4+ cores. Times are for a shared
4-vCPU machine; a quiet 8-core laptop is faster.

```bash
cd int8-fp8-accelerator
docker pull openroad/orfs@sha256:26aa080a55be1fe9ad5befeaa01d0ff6d72c24bdd6c949986ba4448543453dd5
flow/scripts/sv2v.sh npu_top_pd flow/build/npu_top_pd.v flow/src/npu_top_pd.sv
flow/scripts/orfs.sh sky130hd npu_top_n4 p30 30 finish      # synthesis ~35 min, placement ~25 min, CTS/route not measured
python3 flow/scripts/collect.py flow/runs/sky130hd/npu_top_n4/p30 sky130hd npu_top_n4 30
```

Expected: synthesis and placement metrics close to
`flow/results/sky130hd_top_n4_p30/` (100,606 cells; WNS about −4 ns at
30 ns after placement). **CTS, routing and GDSII of the top level were never
completed in the development session**, so there is no reference for the
final numbers; expect the 30 ns target to fail after routing unless the post
unit is pipelined (try 40 ns). Free at least 5 GB of disk first. Save the JSON line, `6_report.json`,
`6_finish.rpt` and `final_routing.webp.png` under
`docs/evidence/<date>/`.

Then the gate-level simulation of the routed netlist:

```bash
python3 -m venv .venv && .venv/bin/pip install cocotb==1.9.2 numpy pytest
docker run --rm -v $PWD/flow/build:/out openroad/orfs@sha256:26aa080a... \
  cp flow/platforms/sky130hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib /out/
PATH=$PWD/.venv/bin:$PATH LIB=flow/build/sky130_fd_sc_hd__tt_025C_1v80.lib \
  flow/scripts/gls.sh flow/runs/sky130hd/npu_top_n4/p30/results/sky130hd/npu_top_n4/base/6_final.v route lib
```

Expected: `TESTS=8 PASS=8 FAIL=0`.

## 2. Things that were not done here and need more time or tools

* **Multi-corner timing.** ORFS ships only the typical sky130hd library.
  For ss/ff corners, install the full PDK with
  `pip install volare && volare enable --pdk sky130 <version>` and add the
  `ss_100C_1v60` and `ff_n40C_1v95` Liberty files to a custom platform
  config, or use OpenLane 2 (which has multi-corner STA built in).
* **The full 8×8 array with 64×64×256 scratchpads.** This needs SRAM macros
  (OpenRAM, or the `sky130_sram_*` macros used on Efabless shuttles) instead
  of 48 KiB of flip-flops, and a macro-placement step.
* **Pipelining the post unit.** The critical path runs from the bottom PE
  accumulator through the combinational FP32 rounding / requantisation unit
  into the C scratchpad. One or two pipeline stages there would roughly
  double the clock.

## 3. What a shuttle (Efabless chipIgnite-style, or a successor programme) would need

There is no tape-out in this project. A real shuttle submission would also need:

1. **The harness.** Shuttles wrap the user design in a fixed SoC harness
   (for Efabless: the Caravel harness with a fixed user area of about
   2.9 mm × 3.5 mm, Wishbone and logic-analyser ports, and fixed pad
   ring). The `cfg_*` port would become a Wishbone slave.
2. **The sign-off flow the shuttle accepts.** Efabless used OpenLane with
   the full sky130 PDK: Magic and KLayout DRC with the foundry decks,
   Netgen LVS, antenna checks, and multi-corner STA (ss/tt/ff, RC corners).
   The ORFS run here uses only the typical corner and the platform's open
   KLayout decks.
3. **Precheck.** The shuttle's precheck tool (`mpw_precheck` for Caravel)
   must pass: GDS consistency, DRC, LVS, XOR against the harness, documentation.
4. **Gate-level simulation with timing** (SDF back-annotation) at least at
   the harness level.
5. **Money and dates.** Shuttle slots are paid and scheduled by the
   organiser; Efabless stopped operating in 2025, so check which
   open-MPW programmes are currently running (for example IHP's open
   SG13G2 shuttles or Tiny Tapeout) before planning.

Nothing in this repository has been submitted anywhere.
