"""Accuracy of FP8 GEMM accumulation strategies (writes bench/results/accuracy.json).

Inputs: Gaussian A (64x256) and B (256x64) quantised to FP8 with a per-tensor
scale (OCP saturating RNE). Reference: the exact dot product of the
*quantised* inputs (Python integers). Compared:
  * exact accumulation + one FP32 rounding  (this accelerator)
  * sequential FP32 accumulation of exact products (typical simple MAC)
  * sequential FP16 accumulation
Error unit: ULPs of the exact result in FP32, and relative error.
Also reports the quantisation error itself (FP8 inputs vs float64 inputs)."""
import json
import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "model"))
import npu_ref as ref  # noqa: E402

rng = np.random.default_rng(0)
M, K, N = 32, 256, 32
out = {}
for fmt, maxv in (("e4m3", 448.0), ("e5m2", 57344.0)):
    A = rng.standard_normal((M, K))
    B = rng.standard_normal((K, N))
    sa, sb = maxv / np.abs(A).max() / 4, maxv / np.abs(B).max() / 4
    table = {}
    def q(x):
        return ref.float_to_fp8(float(x), fmt)
    # vectorised quantisation through a lookup on all 256 codes
    codes = np.array([c for c in range(256) if math.isfinite(ref.fp8_to_float(c, fmt))])
    vals = np.array([ref.fp8_to_float(int(c), fmt) for c in codes])
    order = np.argsort(vals)
    codes, vals = codes[order], vals[order]
    def quant(X):
        idx = np.clip(np.searchsorted(vals, X), 1, len(vals) - 1)
        lo, hi = vals[idx - 1], vals[idx]
        pick = np.where(np.abs(X - lo) <= np.abs(hi - X), idx - 1, idx)
        return codes[pick]
    Aq, Bq = quant(A * sa), quant(B * sb)
    Af = np.vectorize(lambda c: ref.fp8_to_float(int(c), fmt))(Aq)
    Bf = np.vectorize(lambda c: ref.fp8_to_float(int(c), fmt))(Bq)
    ulps = {"exact_fp32": [], "seq_fp32": [], "seq_fp16": []}
    rel = {k: [] for k in ulps}
    for i in range(M):
        for j in range(N):
            hw = ref.bits_to_f32(ref.fp8_dot([int(x) for x in Aq[i]], [int(x) for x in Bq[:, j]], fmt))
            # exact value (Python ints scaled by 2^32 inside fp8_dot); recompute as float64 sum of exact products via fsum
            exact = math.fsum(float(a) * float(b) for a, b in zip(Af[i], Bf[:, j]))
            s32 = np.float32(0)
            s16 = np.float16(0)
            for a, b in zip(Af[i], Bf[:, j]):
                p = a * b
                s32 = np.float32(s32 + np.float32(p))
                s16 = np.float16(s16 + np.float16(p))
            ulp = np.spacing(np.float32(abs(exact))) if exact != 0 else np.float32(1e-45)
            for k, v in (("exact_fp32", hw), ("seq_fp32", float(s32)), ("seq_fp16", float(s16))):
                ulps[k].append(abs(v - exact) / float(ulp))
                rel[k].append(abs(v - exact) / max(abs(exact), 1e-30))
    qerr = np.abs(Af @ Bf / (sa * sb) - A @ B) / np.abs(A @ B).mean()
    out[fmt] = {
        "shape": [M, K, N],
        "max_ulp": {k: float(np.max(v)) for k, v in ulps.items()},
        "mean_ulp": {k: float(np.mean(v)) for k, v in ulps.items()},
        "max_rel_error": {k: float(np.max(v)) for k, v in rel.items()},
        "quantisation_error_mean_rel_to_mean_abs": float(qerr.mean()),
    }
os.makedirs(os.path.join(os.path.dirname(__file__), "results"), exist_ok=True)
def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, float) and not math.isfinite(o):
        return None  # FP16 accumulation overflowed to inf/NaN
    return o


out = clean(out)
json.dump(out, open(os.path.join(os.path.dirname(__file__), "results", "accuracy.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
