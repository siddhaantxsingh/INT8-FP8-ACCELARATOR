# Architecture

```
 host (cfg bus) ──► registers ──► controller (tile loop: clear → feed K → flush → drain)
        │                              │
        ├─► A scratchpad, N banks (m mod N) ──► skew (row r delayed r) ──►┐
        ├─► B scratchpad, N banks (n mod N) ──► skew (col c delayed c) ──►│  N × N PE array
        │                                                                  │  (output-stationary)
        └─◄ C scratchpad, N banks (n mod N) ◄── N × post units ◄── drain (shift down columns)
```

`rtl/npu_pe.sv` is the processing element, `rtl/npu_post.sv` the output conversion and `rtl/npu_top.sv` the array, scratchpads, controller and registers. The register map is at the top of `npu_top.sv`.

## Dataflow

* **Output stationary.** PE (r, c) owns C[tm + r][tn + c] for the current N×N tile.
  * Each cycle, A values move right and B values move down, one PE per cycle.
  * Row r of A and column c of B enter skewed by r and c cycles, so A[r][k] and B[k][c] meet in PE (r, c) at cycle k + r + c.
* **Scratchpads are banked** so the array gets N A-values and N B-values per cycle, and the drain writes N C-values per cycle.
  * A is stored K-major (Aᵀ): one host word holds 4 consecutive rows of one column.
  * B is stored row-major.
  * Either way, a 32-bit host write hits 4 different banks.
* **Schedule per tile.** Clear (1), feed (K), flush (2N + 1), drain (N), next (1): **K + 3N + 3 cycles**, checked cycle-exactly by the testbench. Utilisation is K / (K + 3N + 3): **90.5 %** for an 8×8 array at K = 256, **94.5 %** for 4×4. Fill and drain are not overlapped with the next tile; double-buffered accumulators would remove most of the 3N + 3 overhead.

## Arithmetic

* **INT8.** A signed 8×8 product is added into the accumulator. Results are exact INT32 for K ≤ 4,096, and a 32-bit bias wraps like INT32. Requantisation follows gemmlowp / TFLite exactly:
  * `SaturatingRoundingDoublingHighMul`, with truncating division and saturation of INT_MIN × INT_MIN;
  * `RoundingDivideByPOT`, which rounds half away from zero;
  * then the zero point, a clamp to [-128, 127], and optional ReLU.
* **FP8 (OCP OFP8 E4M3 / E5M2).**
  * Each operand decodes to (sign, significand ≤ 4 bits, exponent of its LSB); E4M3 has no infinities, and its NaN is S.1111.111.
  * The product significand (≤ 8 bits) is shifted to its exact position in an **80-bit fixed-point accumulator whose LSB is 2⁻³²**. The smallest E5M2 product is 2⁻³², and the largest sum (2³¹·⁸ × 4,096) fits in 80 bits.
  * The whole dot product is therefore **exact**. The post unit rounds it once to FP32 with round-to-nearest-even, using leading-one detection and guard and sticky bits.
  * NaN, +inf and −inf are sticky flags: NaN inputs, inf × 0 and +inf + −inf give the canonical NaN.
  * Results are bit-identical to `model/npu_ref.py` and independent of summation order.
* **Why exact accumulation?** On 32×256×32 GEMMs of quantised Gaussian data (`bench/accuracy.py`):
  * this design is within 0.5 ULP of the exact result (correctly rounded);
  * sequential FP32 accumulation is off by up to 32 ULP (E4M3) or 8 ULP (E5M2);
  * FP16 accumulation reaches 26 % relative error (E4M3) and overflows (E5M2).
* **The cost** is area: an FP8-capable PE has about 21× the LUTs of an INT8-only PE ([benchmarks.md](benchmarks.md)), almost all of it in the 80-bit shifter and adder. A production design would accumulate in FP32 with a narrower aligned window, or share one wide accumulator per column.
