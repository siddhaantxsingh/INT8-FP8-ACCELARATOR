<div align="center">

# 🧮 INT8 / FP8 Systolic GEMM Accelerator

### A parameterisable N×N output-stationary systolic array in SystemVerilog for AI-inference matrix multiply, with exact FP8 accumulation, bit-exact verification, and a PE taken all the way to routed GDSII on sky130

**INT8 (TFLite/gemmlowp requantisation) · FP8 E4M3 · FP8 E5M2 (OCP OFP8) · correctly-rounded FP32 output**

<br/>

![SystemVerilog](https://img.shields.io/badge/SystemVerilog-RTL-1f6feb?style=for-the-badge)
![cocotb](https://img.shields.io/badge/cocotb-Verilator-e11d48?style=for-the-badge)
![OpenROAD](https://img.shields.io/badge/OpenROAD--flow--scripts-sky130hd_·_nangate45-0f766e?style=for-the-badge)
![Python](https://img.shields.io/badge/golden_model-Python-3776AB?style=for-the-badge&logo=python&logoColor=white)

![Bit-exact](https://img.shields.io/badge/every_output_word-bit--exact_vs_golden_model-16a34a?style=flat-square)
![FP8](https://img.shields.io/badge/FP8_error-≤_0.5_ULP_(correctly_rounded)-16a34a?style=flat-square)
![Util](https://img.shields.io/badge/MAC_utilisation-90.5%25_(8×8)-0891b2?style=flat-square)
![GDS](https://img.shields.io/badge/PE-routed_GDSII_@_100_MHz-0f766e?style=flat-square)
![GLS](https://img.shields.io/badge/gate--level_sim-100k--cell_netlist_8%2F8-7c3aed?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-64748b?style=flat-square)

[**Architecture**](#%EF%B8%8F-architecture) · [**Exact FP8**](#-why-exact-fp8-accumulation) · [**Verification**](#-verification) · [**Performance**](#-performance) · [**Physical design**](#-physical-design-rtl--gdsii) · [**Run it**](#-running-it)

</div>

---

## 📌 TL;DR

| | |
|---|---|
| 🧱 **Architecture** | N×N **output-stationary** systolic array · banked A/B/C scratchpads · skew networks · per-column post units · register-mapped controller |
| 🔢 **INT8 mode** | INT32 accumulation, then **TFLite/gemmlowp requantisation** (bias, `SaturatingRoundingDoublingHighMul`, `RoundingDivideByPOT`, zero point, clamp, ReLU), bit-identical to the reference |
| 🌗 **FP8 modes** | OCP OFP8 **E4M3** and **E5M2**, including subnormals, NaN/inf rules · products land in an **80-bit exact fixed-point accumulator** and are rounded **once** to FP32 (RNE) |
| 🎯 **Result** | FP8 GEMMs are **correctly rounded and independent of summation order**: ≤ 0.5 ULP, vs 32 ULP for FP32 accumulation and 26% error or overflow for FP16 |
| ✅ **Verified** | Every output word compared **bit for bit** with a Python golden model (cocotb + Verilator), on 8×8 and 4×4 arrays, and in **gate-level simulation** of the synthesised 100k-cell netlist |
| 🔬 **Silicon flow** | OpenROAD-flow-scripts on sky130hd + nangate45: **PE taken to routed GDSII** with STA and a clock sweep; full 4×4 top synthesised and placed |

---

## 🏗️ Architecture

```mermaid
flowchart LR
    HOST(["💻 Host<br/>config bus"]):::host --> REG["📋 Registers<br/>M · N · K · mode<br/>requant params"]:::reg
    REG --> CTRL{{"🎛️ Controller<br/>clear → feed K → flush → drain"}}:::ctrl

    HOST -- "A, Kᵀ-major" --> SA[("A scratchpad<br/>N banks (m mod N)")]:::mem
    HOST -- "B, row-major" --> SB[("B scratchpad<br/>N banks (n mod N)")]:::mem

    SA --> SKA["⏩ skew<br/>row r delayed r"]:::skew
    SB --> SKB["⏬ skew<br/>col c delayed c"]:::skew

    SKA --> ARR
    SKB --> ARR
    ARR["🧮 N × N PE array<br/>output-stationary<br/>INT8 · FP8 E4M3 · FP8 E5M2"]:::arr
    ARR -- "drain: shift down columns" --> POST["🎯 N post units<br/>FP32 RNE rounding<br/>INT8 requantisation"]:::post
    POST --> SC[("C scratchpad<br/>N banks")]:::mem
    SC --> HOST
    CTRL -.-> ARR

    classDef host fill:#475569,stroke:#0f172a,color:#ffffff
    classDef reg fill:#64748b,stroke:#0f172a,color:#ffffff
    classDef ctrl fill:#f59e0b,stroke:#92400e,color:#111827,stroke-width:2px
    classDef mem fill:#0891b2,stroke:#164e63,color:#ffffff
    classDef skew fill:#2563eb,stroke:#1e3a8a,color:#ffffff
    classDef arr fill:#7c3aed,stroke:#4c1d95,color:#ffffff,stroke-width:3px
    classDef post fill:#16a34a,stroke:#14532d,color:#ffffff,stroke-width:2px
```

### Output-stationary dataflow

```mermaid
flowchart TB
    subgraph BIN["B enters from the top, column c delayed by c cycles"]
        direction LR
        sp[" "]:::sp ~~~ b0(["B col 0 ↓"]):::b ~~~ b1(["B col 1 ↓"]):::b ~~~ b2(["B col 2 ↓"]):::b
    end
    subgraph R0[" "]
        direction LR
        a0(["A row 0 →"]):::a --> P00["PE 0,0"]:::pe --> P01["PE 0,1"]:::pe --> P02["PE 0,2"]:::pe
    end
    subgraph R1[" "]
        direction LR
        a1(["A row 1 → +1"]):::a --> P10["PE 1,0"]:::pe --> P11["PE 1,1"]:::pe --> P12["PE 1,2"]:::pe
    end
    subgraph R2[" "]
        direction LR
        a2(["A row 2 → +2"]):::a --> P20["PE 2,0"]:::pe --> P21["PE 2,1"]:::pe --> P22["PE 2,2"]:::pe
    end
    BIN ~~~ R0 ~~~ R1 ~~~ R2

    classDef a fill:#2563eb,stroke:#1e3a8a,color:#ffffff
    classDef b fill:#0891b2,stroke:#164e63,color:#ffffff
    classDef pe fill:#7c3aed,stroke:#4c1d95,color:#ffffff
    classDef sp fill:transparent,stroke:transparent
    style BIN fill:transparent,stroke:#0891b2,stroke-dasharray:4 3
    style R0 fill:transparent,stroke:transparent
    style R1 fill:transparent,stroke:transparent
    style R2 fill:transparent,stroke:transparent
```

<sub>A values flow right and B values flow down, one PE per cycle. With rows and columns skewed by r and c cycles, A[r][k] and B[k][c] meet in PE (r, c) at cycle k + r + c. Each PE owns one output element of the current N×N tile.</sub>

### Tile schedule (8×8 array, K = 256)

```mermaid
gantt
    title Cycles per tile = K + 3N + 3 (8×8, K = 256)
    dateFormat X
    axisFormat %s
    section Tile
    clear (1)          :done, c1, 0, 1s
    feed K (256)       :active, f1, after c1, 256s
    flush 2N+1 (17)    :crit, fl, after f1, 17s
    drain N (8)        :d1, after fl, 8s
    next (1)           :n1, after d1, 1s
```

<sub>Utilisation = K / (K + 3N + 3) = **90.5%** for 8×8 at K = 256 and **94.5%** for 4×4. Double-buffered accumulators that overlap drain with the next tile's feed are the documented next step.</sub>

---

## 🎯 Why exact FP8 accumulation?

```mermaid
flowchart LR
    subgraph PE["Inside each PE (FP8 mode)"]
        direction LR
        DA["decode A<br/>sign · ≤4-bit sig · exp"]:::dec --> MUL["≤ 8-bit product<br/>significand"]:::mul
        DB["decode B<br/>(E4M3: no inf, NaN = S.1111.111)"]:::dec --> MUL
        MUL --> SH["shift to exact position<br/>LSB = 2⁻³²"]:::sh --> ACC[("80-bit fixed-point<br/>EXACT accumulator<br/>+ sticky NaN/±inf flags")]:::acc
    end
    ACC --> RND["🎯 Post unit<br/>leading-one detect · guard + sticky<br/>ONE round-to-nearest-even → FP32"]:::post

    classDef dec fill:#2563eb,stroke:#1e3a8a,color:#ffffff
    classDef mul fill:#0891b2,stroke:#164e63,color:#ffffff
    classDef sh fill:#f59e0b,stroke:#92400e,color:#111827
    classDef acc fill:#7c3aed,stroke:#4c1d95,color:#ffffff,stroke-width:2px
    classDef post fill:#16a34a,stroke:#14532d,color:#ffffff,stroke-width:2px
    style PE fill:transparent,stroke:#7c3aed,stroke-width:2px,stroke-dasharray:6 4
```

The smallest E5M2 product is 2⁻³², and the largest possible sum (2³¹·⁸ × 4,096) fits in 80 bits, so **no bit of the dot product is ever lost**. Rounding happens exactly once, at the end.

| Accumulation, 32×256×32 GEMM | E4M3 max error | E5M2 max error |
|---|:---:|:---:|
| **Exact + one FP32 rounding (this design)** | **0.5 ULP** | **0.5 ULP** |
| Sequential FP32 | 32 ULP | 8 ULP |
| Sequential FP16 | 26% relative error | **overflow** |

**The trade-off, measured:** exact accumulation makes an FP8-capable PE **3.5× larger** than an INT8-only PE in sky130hd (24,642 vs 7,046 µm²). On ECP5 the LUT ratio looks like 21×, because the INT8 multiplier maps to a DSP block and the 80-bit shifter and adder don't. The README reports both figures and explains the difference.

---

## ✅ Verification

```mermaid
flowchart LR
    T["🧪 cocotb testbench<br/>drives the REAL register +<br/>scratchpad interface"]:::tb --> DUT["⚙️ RTL on Verilator<br/>8×8 and 4×4"]:::dut
    T --> GM["🐍 Golden model npu_ref.py<br/>pure integer arithmetic<br/>exact sums × 2³² + one RNE"]:::gm
    DUT --> CMP{{"EVERY output word<br/>compared bit-for-bit"}}:::cmp
    GM --> CMP
    T --> GLS["🔌 Gate-level sim<br/>synthesised sky130hd<br/>100,606-cell netlist"]:::gls --> CMP
    GM -. "self-tests" .-> ST["OCP spec values · every FP8 code<br/>round-trips · 20k RNE cases vs NumPy<br/>gemmlowp primitives"]:::st

    classDef tb fill:#e11d48,stroke:#881337,color:#ffffff
    classDef dut fill:#2563eb,stroke:#1e3a8a,color:#ffffff
    classDef gm fill:#3776AB,stroke:#1e3a5f,color:#ffffff
    classDef cmp fill:#16a34a,stroke:#14532d,color:#ffffff,stroke-width:2px
    classDef gls fill:#7c3aed,stroke:#4c1d95,color:#ffffff
    classDef st fill:#64748b,stroke:#0f172a,color:#ffffff
```

| Test | Covers |
|---|---|
| `int8_random_shapes` | 8×8×8, 1×1×1, 13×21×37, 3×64×5, 64×2×17, 9×9×200: partial tiles in both dimensions, K = 1 |
| `int8_extremes_and_bias` | −128 × −128 over K = 256 · bias near INT32_MAX wrapping |
| `int8_requantisation` | 6 random multiplier / shift / zero-point / ReLU / bias configurations |
| `fp8_e4m3_random` | random E4M3 incl. subnormals, up to 16×16×256 · NaN inputs |
| `fp8_e5m2_random_and_specials` | inf, NaN, inf × 0, +inf + −inf |
| `fp8_exact_accumulation_and_ties` | (2¹⁵ + 1) − 2¹⁵ = 1 **exactly** · 1 + 2⁻²⁴ ties to even · 1.25 + 2⁻²⁴ rounds up |
| `bad_dimensions_set_error` | illegal M/K/mode raise the error bit, and the accelerator still works afterwards |
| `cycle_counts_match_the_schedule` | **K + 3N + 3 per tile, cycle-exact** |

All 8 tests run on both array sizes. `verilator --lint-only -Wall` is clean, and ORFS's formal equivalence check reports the final routed FP8 PE netlist **IDENTICAL** to the synthesised one.

---

## 📈 Performance

| Array | GEMM (M×N×K) | Cycles | MAC utilisation |
|---|:---:|:---:|:---:|
| 8×8 | 8×8×256 | 283 | **90.5%** |
| 8×8 | 64×64×256 | 18,112 | **90.5%** |
| 8×8 | 16×16×64 | 364 | 70.3% |
| 4×4 | 4×4×256 | 271 | **94.5%** |
| 4×4 | 64×64×256 | 69,376 | **94.5%** |

<sub>INT8 and FP8 have identical cycle counts. Throughput = N² · f · utilisation MAC/s. All numbers come from cycle-exact RTL simulation.</sub>

---

## 🔬 Physical design: RTL → GDSII

```mermaid
flowchart LR
    RTL["📄 SystemVerilog"]:::a --> SV["sv2v"]:::a --> Y["Yosys 0.68<br/>synthesis"]:::b
    Y --> FP["floorplan"]:::c --> PL["global + detailed<br/>placement"]:::c
    PL --> CTS["CTS"]:::c --> RT["global + detailed<br/>routing"]:::c --> STA["parasitics · final STA<br/>power"]:::d --> GDS[("💎 GDSII")]:::gds

    Y -. "4×4 top: gate-level sim<br/>8/8 bit-exact" .-> GLS(["✅ GLS"]):::ok
    PL -. "4×4 top stops here<br/>(WNS −4.04 ns @ 30 ns)" .-> STOP(["⏸️ placed"]):::warn

    classDef a fill:#475569,stroke:#0f172a,color:#ffffff
    classDef b fill:#2563eb,stroke:#1e3a8a,color:#ffffff
    classDef c fill:#0f766e,stroke:#134e4a,color:#ffffff
    classDef d fill:#16a34a,stroke:#14532d,color:#ffffff
    classDef gds fill:#7c3aed,stroke:#4c1d95,color:#ffffff,stroke-width:3px
    classDef ok fill:#16a34a,stroke:#14532d,color:#ffffff
    classDef warn fill:#f59e0b,stroke:#92400e,color:#111827
```

<table>
<tr>
<td width="50%" align="center"><img src="flow/results/sky130hd_pe_fp8_p10/final_routing.png" alt="Routed INT8+FP8 PE on sky130hd"/><br/><sub><b>Routed INT8 + FP8 PE</b> · sky130hd · 10 ns · 0 DRC violations</sub></td>
<td width="50%" align="center"><img src="flow/results/sky130hd_pe_fp8_p10/final_placement.png" alt="Placement of INT8+FP8 PE on sky130hd"/><br/><sub><b>Final placement</b> · 24,642 µm² · 67% utilisation</sub></td>
</tr>
</table>

### PE clock sweep, sky130hd typical (full flow per point)

| PE | Period | Cell area | Setup WNS | Hold WNS | Route DRC | Power | Closes |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| INT8 only | 10 ns | 7,046 µm² | +1.19 ns | +0.50 ns | 0 | 1.48 mW | ✅ |
| INT8 only | **8 ns** | 7,965 µm² | +0.26 ns | +0.49 ns | 0 | 2.37 mW | ✅ **125 MHz** |
| INT8 only | 7 ns | 8,444 µm² | −0.17 ns | +0.49 ns | 0 | 2.86 mW | ❌ |
| INT8 + FP8 | **10 ns** | 24,642 µm² | +0.24 ns | +0.58 ns | 0 | 9.69 mW | ✅ **100 MHz** |
| INT8 + FP8 | 9 ns | 26,542 µm² | −0.35 ns | +0.58 ns | 0 | 11.93 mW | ❌ |

### Full 4×4 top level (sky130hd)

| Stage | Status | Result |
|---|:---:|---|
| Synthesis | ✅ | **100,606 cells**, 863,408 µm² (20% sequential) |
| Gate-level simulation of the synthesised netlist | ✅ | **8/8 tests bit-exact** |
| Floorplan + placement | ✅ | 1.913 mm² core, 49.3% utilisation |
| Timing after placement | ⚠️ | WNS −4.04 ns at 30 ns, so about **29–30 MHz** (pre-CTS estimate) |
| CTS · routing · sign-off · GDSII | ❌ | runs were killed by worker restarts on a shared machine |

**Critical path:** tile counter → bias index → combinational INT32 add + **32×32 requantisation multiplier** in `npu_post` → C scratchpad. Pipelining the post unit is the clear fix. Details: [`physical_design.md`](docs/physical_design.md) · flow: [`flow/README.md`](flow/README.md)

---

## 🚀 Running it

```bash
python3 -m venv .venv && .venv/bin/pip install cocotb==1.9.2 numpy pytest   # cocotb 2.x needs Verilator ≥ 5.036
PATH=$PWD/.venv/bin:$PATH make lint model-test test test-n4      # lint, golden model, 8×8 + 4×4 suites
make test-small                                                    # the 4×4 configuration built by the ASIC flow
make accuracy synth && python3 bench/report.py                     # FP8 accuracy study, area, docs/benchmarks.md
```

The register map is documented at the top of [`rtl/npu_top.sv`](rtl/npu_top.sv). The physical-design flow runs OpenROAD-flow-scripts in Docker ([`flow/README.md`](flow/README.md)), and gate-level simulation uses [`flow/scripts/gls.sh`](flow/scripts/gls.sh).

---

## ⚠️ Limitations

- **Partial, academic physical design.** Only the PE is routed to GDS; the 4×4 top stops at placement. There's one typical corner, vectorless power, and no KLayout DRC/LVS, tape-out or silicon.
- **The top-level clock is slow** (about 30 MHz), limited by the un-pipelined post unit. The default 48 KiB scratchpads would need SRAM macros.
- **Exact FP8 costs area** (3.5× per PE in sky130hd). A cheaper FP32-window PE wasn't built for comparison.
- **No drain/compute overlap** (3N + 3 cycles per tile). There's no DMA or AXI; the host writes scratchpads word by word.
- **Limits:** M, N ≤ 64 and K ≤ 256 per run (larger GEMMs are tiled by the host). Per-tensor requantisation only; FP8 outputs are raw FP32.
- **Simulation and open-PDK only.** No FPGA bring-up, no formal equivalence against the golden model, and no coverage metric.

Full list: [`limitations.md`](docs/limitations.md) · Architecture: [`architecture.md`](docs/architecture.md) · Benchmarks: [`benchmarks.md`](docs/benchmarks.md) · Testing: [`testing.md`](docs/testing.md)

---

## 📁 Repository layout

```text
INT8-FP8-ACCELARATOR/
├── rtl/       ⚙️  npu_pe.sv (PE) · npu_post.sv (FP32 rounding, requantisation) · npu_top.sv (array, scratchpads, controller)
├── model/     🐍  npu_ref.py bit-exact golden model + self-tests
├── tb/        🧪  cocotb testbenches (full + small/GLS configuration)
├── bench/     📊  FP8 accuracy study, perf results, report generator
├── synth/     🧱  Yosys area script + results
├── flow/      🔬  OpenROAD-flow-scripts configs (sky130hd, nangate45), GLS script, results + layout images
└── docs/      📖  architecture · physical design · benchmarks · testing · limitations
```

---

<div align="center">

**Every output word bit-exact. Every FP8 sum exact. One rounding, at the very end.**

<br/>

Built by **[Siddhant Singh](https://github.com/siddhaantxsingh)** · B.Tech ECE (VLSI Design & Technology), MIT Manipal · <sub>MIT License</sub>

</div>
