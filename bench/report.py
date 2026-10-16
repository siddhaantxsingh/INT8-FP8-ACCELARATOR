"""Render docs/benchmarks.md from bench/results/ and synth/results/."""
import json
import re

acc = json.load(open("bench/results/accuracy.json"))
perf = {n: [l.split() for l in open(f"bench/results/perf_n{n}.txt")] for n in (8, 4)}


def stat(f):
    t = open(f).read()
    t = t[t.index("Number of cells"):]
    return dict(re.findall(r"^\s+(\S+)\s+(\d+)$", t, re.M)), int(re.search(r"Number of cells:\s+(\d+)", t).group(1))


L = ["# Benchmarks\n", "Rendered by `python3 bench/report.py` from `bench/results/` and `synth/results/`. Reproduce with `make test test-n4 accuracy synth`.\n",
     "## Throughput (cycle-exact RTL simulation; INT8 and FP8 identical)\n",
     "Utilisation = M·N·K / (cycles × N²). The testbench asserts that the cycle counts equal the schedule (K + 3N + 3 per tile) exactly.\n",
     "| array | M×N×K | cycles | MAC utilisation |", "|---|---|---|---|"]
for n in (8, 4):
    for M, N, K, c, u in perf[n]:
        L.append(f"| {n}×{n} | {M}×{N}×{K} | {int(c):,} | {float(u) * 100:.1f} % |")
L += ["", "At a clock of f MHz, an 8×8 array delivers 64·f·utilisation MAC/s. There is no timing data, because no place-and-route was done.\n",
      "## Accuracy of FP8 accumulation (32×256×32, Gaussian data quantised per tensor)\n",
      "| format | accumulation | max error (ULP of FP32) | mean error (ULP) | max relative error |", "|---|---|---|---|---|"]
names = {"exact_fp32": "exact + one FP32 rounding (this design)", "seq_fp32": "sequential FP32", "seq_fp16": "sequential FP16"}
fmtv = lambda v, f: "overflow" if v is None else f.format(v)
for fmt in ("e4m3", "e5m2"):
    a = acc[fmt]
    for k, name in names.items():
        L.append(f"| {fmt.upper()} | {name} | {fmtv(a['max_ulp'][k], '{:,.1f}')} | {fmtv(a['mean_ulp'][k], '{:,.3f}')} | "
                 f"{fmtv(a['max_rel_error'][k], '{:.2e}')} |")
L += ["", f"FP8 quantisation itself costs {acc['e4m3']['quantisation_error_mean_rel_to_mean_abs'] * 100:.1f} % (E4M3) and "
      f"{acc['e5m2']['quantisation_error_mean_rel_to_mean_abs'] * 100:.1f} % (E5M2) mean error relative to the float64 GEMM. "
      "Accumulation error comes on top of that; with FP16 accumulation it dominates.\n",
      "## Area (Yosys 0.33; no timing)\n", "| block | generic cells | ECP5 LUT4 | ECP5 FF | ECP5 carry (CCU2C) | DSP |", "|---|---|---|---|---|---|"]
for name, g, e in (("PE, INT8 only (32-bit accumulator)", "pe_int8_only_generic", "pe_int8_only_ecp5"),
                   ("PE, INT8 + FP8 (80-bit exact accumulator)", "pe_int8_fp8_generic", "pe_int8_fp8_ecp5")):
    _, gc = stat(f"synth/results/{g}.txt")
    ec, _ = stat(f"synth/results/{e}.txt")
    L.append(f"| {name} | {gc:,} | {int(ec.get('LUT4', 0)):,} | {int(ec.get('TRELLIS_FF', 0)):,} | {int(ec.get('CCU2C', 0)):,} | {int(ec.get('MULT18X18D', 0))} |")
_, pc = stat("synth/results/post_generic.txt")
L += [f"| post unit (FP32 rounding + INT32 requantisation), per column | {pc:,} | — | — | — | — |", "",
      "Exact FP8 accumulation makes each PE about 21× larger in LUTs than an INT8-only PE. The 80-bit barrel shifter and adder "
      "dominate. The full `npu_top` was not synthesised: its 48 KiB of scratchpad are behavioural arrays and would need BRAM macros.\n"]
open("docs/benchmarks.md", "w").write("\n".join(L) + "\n")
