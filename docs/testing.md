# Verification

* **Golden model.** `model/npu_ref.py` is a bit-exact Python model. It uses only integer arithmetic for FP8: products and sums are exact Python integers scaled by 2³², followed by one explicit RNE rounding. It is checked by `model/tests/test_ref.py`:
  * the FP8 values given in the OCP spec (max, min subnormal, NaN and inf encodings);
  * an encode/decode round trip of every finite code;
  * FP32 rounding against NumPy on 20,000 random exact values, plus hand-made ties;
  * the gemmlowp primitives against their documented behaviour (saturation, round half away from zero).
* **RTL testbench.** `tb/test_npu.py` uses cocotb 1.9.2 on Verilator 5.020 and drives the real register and scratchpad interface. **Every output word is compared bit-for-bit** with the golden model. The 8 tests run for the 8×8 and the 4×4 configuration:

| Test | Covers |
|---|---|
| `int8_random_shapes` | 8×8×8, 1×1×1, 13×21×37, 3×64×5, 64×2×17, 9×9×200: partial tiles in both dimensions, K = 1 |
| `int8_extremes_and_bias` | −128 × −128 over K = 256 (largest magnitude); bias near INT32_MAX wrapping |
| `int8_requantisation` | 6 random configurations of multiplier, shift, zero point, ReLU and bias |
| `fp8_e4m3_random` | random E4M3 (including subnormals) up to 16×16×256; NaN inputs |
| `fp8_e5m2_random_and_specials` | random E5M2; inf, NaN, inf × 0, +inf + −inf, +inf alone |
| `fp8_exact_accumulation_and_ties` | (2¹⁵ + 1) − 2¹⁵ = 1 exactly; 1 + 2⁻²⁴ (tie to even); 1 + 2⁻²³; 1.25 + 2⁻²⁴ (tie, odd → up) |
| `bad_dimensions_set_error` | M = 0, M > 64, K > 256, INT8 output in FP8 mode → error bit; the accelerator works afterwards |
| `cycle_counts_match_the_schedule` | cycle counts equal K + 3N + 3 per tile exactly (also the utilisation numbers) |

* **Small physical configuration.** `tb/test_small.py` (`make test-small`) runs 8 bit-exact tests on N = 4 with 8×8×16 scratchpads, the configuration built by the ASIC flow. The same tests are the gate-level suite (`flow/scripts/gls.sh`).
* **Lint:** `verilator --lint-only -Wall` is clean.

## Not done

- No formal equivalence checks against the model.
- No coverage measurement.
- Gate-level simulation was run on the synthesised 4×4 sky130hd netlist only (8/8 bit-exact, see [physical_design.md](physical_design.md)); not on the routed netlist, and without timing (SDF).
- No testing of back-to-back runs racing host writes; host writes are ignored while busy, by design.
