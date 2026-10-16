"""Bit-exact reference model of the accelerator (used as the golden model).

Arithmetic contract:

* INT8 mode: C[i][j] = sum_k A[i][k] * B[k][j] (+ bias[j]) as exact INT32
  (K <= 4096 keeps the sum inside 32 bits). Optional requantisation to INT8
  with the TFLite / gemmlowp fixed-point scheme (per-tensor multiplier and
  shift, zero point, optional ReLU).
* FP8 modes (OCP OFP8 E4M3 or E5M2 inputs): every product is exact, the dot
  product is accumulated *exactly* (as an integer multiple of 2^-32), and
  the result is rounded once to FP32 with round-to-nearest-even. NaN inputs
  (and, for E5M2, inf * 0 or +inf + -inf) give the canonical NaN
  0x7FC00000; infinities propagate. An exact zero gives +0.
"""
from __future__ import annotations

import math
import struct

ACC_LSB_EXP = -32  # accumulator LSB weight 2^-32


# ------------------------------------------------------------------ FP8
def fp8_decode(byte: int, fmt: str):
    """Return ('nan'|'inf'|'num', sign, significand int, exponent) where
    value = (-1)^sign * sig * 2^exp for numbers."""
    s = (byte >> 7) & 1
    if fmt == "e4m3":
        e, m = (byte >> 3) & 0xF, byte & 7
        if e == 0xF and m == 7:
            return ("nan", s, 0, 0)
        if e == 0:
            return ("num", s, m, 1 - 7 - 3)
        return ("num", s, 8 + m, e - 7 - 3)
    if fmt == "e5m2":
        e, m = (byte >> 2) & 0x1F, byte & 3
        if e == 0x1F:
            return ("inf", s, 0, 0) if m == 0 else ("nan", s, 0, 0)
        if e == 0:
            return ("num", s, m, 1 - 15 - 2)
        return ("num", s, 4 + m, e - 15 - 2)
    raise ValueError(fmt)


def fp8_to_float(byte: int, fmt: str) -> float:
    kind, s, sig, e = fp8_decode(byte, fmt)
    if kind == "nan":
        return math.nan
    if kind == "inf":
        return -math.inf if s else math.inf
    v = math.ldexp(sig, e)
    return -v if s else v


def float_to_fp8(x: float, fmt: str) -> int:
    """Round-to-nearest-even encode, saturating to the largest finite value
    (the OCP 'saturate' conversion mode); NaN -> NaN."""
    best, best_err = None, None
    if math.isnan(x):
        return 0x7F if fmt == "e4m3" else 0x7F
    for b in range(256):
        v = fp8_to_float(b, fmt)
        if math.isnan(v) or math.isinf(v):
            continue
        err = abs(v - x)
        if best is None or err < best_err or (err == best_err and (b & 1) == 0 and (best & 1) == 1):
            best, best_err = b, err
    return best


# ------------------------------------------------------------- FP32 RNE
def round_to_fp32(n: int) -> int:
    """Round the exact value n * 2^-32 to FP32 bits (round to nearest even)."""
    if n == 0:
        return 0
    sign = 1 if n < 0 else 0
    mag = -n if n < 0 else n
    p = mag.bit_length() - 1  # position of the leading one
    exp = p + ACC_LSB_EXP
    if p <= 23:
        mant = mag << (23 - p)
    else:
        sh = p - 23
        mant = mag >> sh
        rem = mag & ((1 << sh) - 1)
        half = 1 << (sh - 1)
        if rem > half or (rem == half and (mant & 1)):
            mant += 1
            if mant == 1 << 24:
                mant >>= 1
                exp += 1
    biased = exp + 127
    assert 0 < biased < 255, "out of FP32 normal range (cannot happen for FP8 inputs)"
    return (sign << 31) | (biased << 23) | (mant & 0x7FFFFF)


def bits_to_f32(b: int) -> float:
    return struct.unpack("<f", struct.pack("<I", b))[0]


def fp8_dot(a_bytes, b_bytes, fmt: str) -> int:
    """Exact FP8 dot product rounded once to FP32; returns FP32 bits."""
    acc, nan, pinf, ninf = 0, False, False, False
    for x, y in zip(a_bytes, b_bytes):
        ka, sa, ma, ea = fp8_decode(x, fmt)
        kb, sb, mb, eb = fp8_decode(y, fmt)
        s = sa ^ sb
        if ka == "nan" or kb == "nan":
            nan = True
        elif ka == "inf" or kb == "inf":
            other_zero = (ka == "num" and ma == 0) or (kb == "num" and mb == 0)
            if other_zero:
                nan = True
            elif s:
                ninf = True
            else:
                pinf = True
        else:
            v = (ma * mb) << (ea + eb - ACC_LSB_EXP)
            acc += -v if s else v
    if nan or (pinf and ninf):
        return 0x7FC00000
    if pinf:
        return 0x7F800000
    if ninf:
        return 0xFF800000
    return round_to_fp32(acc)


# ---------------------------------------------------------------- INT8
def int8(b: int) -> int:
    return b - 256 if b >= 128 else b


def srdhm(a: int, b: int) -> int:
    """gemmlowp SaturatingRoundingDoublingHighMul (int32 x int32 -> int32)."""
    if a == b == -(1 << 31):
        return (1 << 31) - 1
    ab = a * b
    nudge = (1 << 30) if ab >= 0 else 1 - (1 << 30)
    q = ab + nudge
    # C integer division by 2^31 truncates toward zero
    return q // (1 << 31) if q >= 0 else -((-q) // (1 << 31))


def rdbpot(x: int, exponent: int) -> int:
    """gemmlowp RoundingDivideByPOT."""
    mask = (1 << exponent) - 1
    remainder = x & mask
    threshold = (mask >> 1) + (1 if x < 0 else 0)
    return (x >> exponent) + (1 if remainder > threshold else 0)


def requantize(acc: int, mult: int, shift: int, zp: int, relu: bool) -> int:
    v = rdbpot(srdhm(acc, mult), shift) + zp
    lo = max(-128, zp) if relu else -128
    return max(lo, min(127, v))


def wrap32(x: int) -> int:
    return ((x + (1 << 31)) % (1 << 32)) - (1 << 31)


def gemm(A, B, mode: str, bias=None, outfmt="raw", mult=0, shift=0, zp=0, relu=False):
    """A: M x K bytes, B: K x N bytes (lists of lists of ints 0..255).
    Returns M x N list of 32-bit words as the hardware writes them."""
    M, K, N = len(A), len(A[0]), len(B[0])
    out = [[0] * N for _ in range(M)]
    for i in range(M):
        for j in range(N):
            if mode == "int8":
                acc = sum(int8(A[i][k]) * int8(B[k][j]) for k in range(K))
                if bias is not None:
                    acc += bias[j]
                acc = wrap32(acc)
                if outfmt == "int8":
                    out[i][j] = requantize(acc, mult, shift, zp, relu) & 0xFFFFFFFF
                else:
                    out[i][j] = acc & 0xFFFFFFFF
            else:
                out[i][j] = fp8_dot([A[i][k] for k in range(K)], [B[k][j] for k in range(K)], mode)
    return out
