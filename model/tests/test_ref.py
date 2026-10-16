"""Checks of the reference model against independent definitions."""
import math
import os
import random
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import npu_ref as ref  # noqa: E402


def test_fp8_decode_matches_ocp_spec_values():
    f = ref.fp8_to_float
    assert f(0x7E, "e4m3") == 448.0 and f(0xFE, "e4m3") == -448.0
    assert f(0x01, "e4m3") == 2.0 ** -9 and f(0x08, "e4m3") == 2.0 ** -6 and f(0x38, "e4m3") == 1.0
    assert math.isnan(f(0x7F, "e4m3")) and math.isnan(f(0xFF, "e4m3"))
    assert f(0x7B, "e5m2") == 57344.0 and f(0x01, "e5m2") == 2.0 ** -16 and f(0x3C, "e5m2") == 1.0
    assert f(0x7C, "e5m2") == math.inf and f(0xFC, "e5m2") == -math.inf and math.isnan(f(0x7D, "e5m2"))
    # every finite E4M3 / E5M2 value round-trips through the encoder
    for fmt in ("e4m3", "e5m2"):
        for b in range(256):
            v = f(b, fmt)
            if math.isfinite(v) and not (v == 0 and b & 0x80):
                assert ref.float_to_fp8(v, fmt) == b, (fmt, hex(b))


def f32bits(x):
    return struct.unpack("<I", struct.pack("<f", x))[0]


def test_round_to_fp32_matches_numpy_rne():
    rng = random.Random(0)
    for _ in range(20000):
        m = rng.getrandbits(rng.randint(1, 52)) * rng.choice([1, -1])
        n = m << rng.randint(0, 25)  # exact as a float64: m * 2^s * 2^-32
        exact = float(n) * 2.0 ** -32
        assert ref.round_to_fp32(n) == f32bits(np.float32(exact)), n
    # ties: 1 + 2^-24 -> 1.0, 1 + 3*2^-24 -> 1 + 2^-22
    one = 1 << 32
    assert ref.round_to_fp32(one + (one >> 24)) == f32bits(1.0)
    assert ref.round_to_fp32(one + 3 * (one >> 24)) == f32bits(1.0 + 2.0 ** -22)


def test_gemmlowp_primitives():
    assert ref.srdhm(-(1 << 31), -(1 << 31)) == (1 << 31) - 1
    assert ref.srdhm(1 << 30, 1 << 30) == 1 << 29
    assert ref.srdhm(-(1 << 30), 1 << 30) == -(1 << 29)
    # round half away from zero
    assert ref.rdbpot(5, 1) == 3 and ref.rdbpot(-5, 1) == -3 and ref.rdbpot(4, 1) == 2 and ref.rdbpot(-4, 1) == -2
    assert ref.rdbpot(7, 0) == 7
    assert ref.requantize(10 ** 9, (1 << 31) - 1, 0, 0, False) == 127
    assert ref.requantize(-(10 ** 9), (1 << 31) - 1, 0, 5, True) == 5


def test_fp8_dot_specials():
    e = lambda x: ref.float_to_fp8(x, "e5m2")
    assert ref.fp8_dot([0x7C, e(1)], [e(0), e(1)], "e5m2") == 0x7FC00000  # inf * 0
    assert ref.fp8_dot([0x7C, 0xFC], [e(1), e(1)], "e5m2") == 0x7FC00000  # inf - inf
    assert ref.fp8_dot([0x7C, e(5)], [e(1), e(1)], "e5m2") == 0x7F800000
    assert ref.fp8_dot([e(1), e(-1)], [e(1), e(1)], "e5m2") == 0  # exact zero -> +0
