"""Bit-exact tests for the small physical-design configuration.

The ORFS flow builds npu_top with N = 4, MAX_M = MAX_N = 8, MAX_K = 16
(flow/src/npu_top_pd.sv). This suite covers the same features as
test_npu.py with shapes that fit those scratchpads. It runs on:
  * the RTL wrapper (make -C tb small),
  * the synthesised and the post-route netlists with cell models
    (flow/scripts/gls.sh).
Every output word is compared bit-for-bit with model/npu_ref.py.
"""
import os
import random

import cocotb

import test_npu as base  # helpers only; module import keeps its tests out of this suite

N = int(os.environ.get("NPU_N", 4))
assert (base.MAX_M, base.MAX_N, base.MAX_K) == (8, 8, 16), "set NPU_MAX_M=8 NPU_MAX_N=8 NPU_MAX_K=16"


async def start(dut):
    npu = base.Npu(dut)
    npu.n = N
    await npu.reset()
    return npu


@cocotb.test()
async def small_int8_random_shapes(dut):
    npu = await start(dut)
    rng = random.Random(11)
    for M, Nn, K in [(4, 4, 4), (1, 1, 1), (7, 5, 13), (8, 8, 16), (3, 8, 5), (8, 2, 9)]:
        await base.check(npu, base.rand_int8(rng, M, K), base.rand_int8(rng, K, Nn), "int8")


@cocotb.test()
async def small_int8_extremes_and_bias(dut):
    npu = await start(dut)
    K = 16
    A = [[0x80] * K for _ in range(8)]
    B = [[0x80] * 8 for _ in range(K)]
    await base.check(npu, A, B, "int8")  # 16 * 16384
    B = [[0x7F] * 8 for _ in range(K)]
    await base.check(npu, A, B, "int8", bias=[(1 << 31) - 1 - 50000 * j for j in range(8)])  # INT32 wrap


@cocotb.test()
async def small_int8_requantisation(dut):
    npu = await start(dut)
    rng = random.Random(12)
    for trial in range(4):
        M, Nn, K = rng.randint(1, 8), rng.randint(1, 8), rng.randint(1, 16)
        kw = dict(outfmt="int8", mult=rng.randint(1 << 30, (1 << 31) - 1), shift=rng.randint(0, 12),
                  zp=rng.randint(-20, 20), relu=bool(trial % 2), bias=[rng.randint(-5000, 5000) for _ in range(Nn)])
        await base.check(npu, base.rand_int8(rng, M, K), base.rand_int8(rng, K, Nn), "int8", **kw)


@cocotb.test()
async def small_fp8_e4m3(dut):
    npu = await start(dut)
    rng = random.Random(13)
    for M, Nn, K in [(8, 8, 16), (5, 7, 11)]:
        await base.check(npu, base.rand_fp8(rng, M, K, "e4m3"), base.rand_fp8(rng, K, Nn, "e4m3"), "e4m3")
    await base.check(npu, base.rand_fp8(rng, 8, 8, "e4m3", specials=0.05),
                     base.rand_fp8(rng, 8, 8, "e4m3", specials=0.05), "e4m3")


@cocotb.test()
async def small_fp8_e5m2_and_specials(dut):
    npu = await start(dut)
    rng = random.Random(14)
    await base.check(npu, base.rand_fp8(rng, 8, 8, "e5m2"), base.rand_fp8(rng, 8, 8, "e5m2"), "e5m2")
    await base.check(npu, base.rand_fp8(rng, 8, 8, "e5m2", specials=0.1),
                     base.rand_fp8(rng, 8, 8, "e5m2", specials=0.1), "e5m2")
    A = [[0x7C, 0x00], [0x7C, 0xFC], [0x7C, 0x3C], [0x00, 0x00]]  # inf,0 | inf,-inf | inf,1 | 0,0
    await base.check(npu, A, [[0x3C], [0x3C]], "e5m2")
    await base.check(npu, A, [[0x00], [0x3C]], "e5m2")


@cocotb.test()
async def small_fp8_exact_accumulation_and_ties(dut):
    npu = await start(dut)
    e = lambda x: base.ref.float_to_fp8(x, "e5m2")
    one, big, tiny = e(1.0), e(32768.0), e(2.0 ** -12)
    A = [[big, one, e(-32768.0)], [one, tiny, e(0.0)], [one, tiny, tiny], [e(1.25), tiny, e(0.0)]]
    B = [[one], [tiny], [one]]
    await base.check(npu, A, B, "e5m2")


@cocotb.test()
async def small_bad_dimensions_set_error(dut):
    npu = await start(dut)
    for M, Nn, K, mode, outfmt in [(0, 4, 4, "int8", 0), (9, 4, 4, "int8", 0), (4, 4, 17, "int8", 0),
                                   (4, 4, 4, "e4m3", 1)]:
        st, _ = await npu.run(M, Nn, K, mode, outfmt=outfmt)
        assert st & 4, f"no error for M={M} N={Nn} K={K} mode={mode} outfmt={outfmt}"
    rng = random.Random(15)
    await base.check(npu, base.rand_int8(rng, 4, 4), base.rand_int8(rng, 4, 4), "int8")


@cocotb.test()
async def small_cycle_counts(dut):
    npu = await start(dut)
    rng = random.Random(16)
    for M, Nn, K in [(4, 4, 16), (8, 8, 16), (5, 3, 7)]:
        cycles = await base.check(npu, base.rand_int8(rng, M, K), base.rand_int8(rng, K, Nn), "int8")
        assert cycles == base.expected_cycles(M, Nn, K, N), f"{M}x{Nn}x{K}: {cycles} cycles"
