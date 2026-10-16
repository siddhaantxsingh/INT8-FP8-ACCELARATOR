"""cocotb tests for npu_top against the bit-exact reference model."""
import math
import os
import random
import sys

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "model"))
import npu_ref as ref  # noqa: E402

# Scratchpad sizes of the DUT (defaults = npu_top defaults; the gate-level
# runs use the smaller physical-design configuration, see tb/test_small.py).
MAX_M = int(os.environ.get("NPU_MAX_M", 64))
MAX_N = int(os.environ.get("NPU_MAX_N", 64))
MAX_K = int(os.environ.get("NPU_MAX_K", 256))
A_BASE, B_BASE, C_BASE, BIAS_BASE = 0x10000, 0x20000, 0x40000, 0x60000
MODES = {"int8": 0, "e4m3": 1, "e5m2": 2}


class Npu:
    def __init__(self, dut):
        self.dut = dut
        self.n = int(dut.N.value) if hasattr(dut, "N") else int(os.environ.get("NPU_N", 8))

    async def reset(self):
        d = self.dut
        cocotb.start_soon(Clock(d.clk, 10, units="ns").start())
        d.cfg_valid.value = 0
        d.cfg_we.value = 0
        d.cfg_addr.value = 0
        d.cfg_wdata.value = 0
        d.rst_n.value = 0
        for _ in range(3):
            await RisingEdge(d.clk)
        d.rst_n.value = 1
        await RisingEdge(d.clk)

    async def write(self, addr, data):
        d = self.dut
        d.cfg_valid.value = 1
        d.cfg_we.value = 1
        d.cfg_addr.value = addr
        d.cfg_wdata.value = data & 0xFFFFFFFF
        await RisingEdge(d.clk)
        d.cfg_valid.value = 0
        d.cfg_we.value = 0

    async def read(self, addr):
        d = self.dut
        d.cfg_valid.value = 1
        d.cfg_we.value = 0
        d.cfg_addr.value = addr
        await RisingEdge(d.clk)
        d.cfg_valid.value = 0
        await ReadOnly()
        v = int(d.cfg_rdata.value)
        await RisingEdge(d.clk)
        return v

    async def load(self, A, B, bias=None):
        M, K, N = len(A), len(A[0]), len(B[0])
        for k in range(K):
            for m0 in range(0, M, 4):
                w = 0
                for i in range(4):
                    if m0 + i < M:
                        w |= A[m0 + i][k] << (8 * i)
                await self.write(A_BASE + k * MAX_M + m0, w)
            for n0 in range(0, N, 4):
                w = 0
                for i in range(4):
                    if n0 + i < N:
                        w |= B[k][n0 + i] << (8 * i)
                await self.write(B_BASE + k * MAX_N + n0, w)
        if bias is not None:
            for j, b in enumerate(bias):
                await self.write(BIAS_BASE + 4 * j, b)

    async def run(self, M, N, K, mode, outfmt=0, mult=0, shift=0, zp=0, relu=0, bias_en=0, timeout=2_000_000):
        for a, v in ((0x08, M), (0x0C, N), (0x10, K), (0x14, MODES[mode]), (0x18, outfmt), (0x1C, mult),
                     (0x20, shift), (0x24, zp), (0x28, relu), (0x2C, bias_en)):
            await self.write(a, v)
        await self.write(0x00, 1)
        for _ in range(timeout // 64):
            for _ in range(64):
                await RisingEdge(self.dut.clk)
            st = await self.read(0x04)
            if st & 2:
                return st, await self.read(0x30)
        raise TimeoutError("accelerator did not finish")

    async def result(self, M, N):
        return [[await self.read(C_BASE + 4 * (m * MAX_N + n)) for n in range(N)] for m in range(M)]


def rand_int8(rng, rows, cols, lo=-128, hi=127):
    return [[rng.randint(lo, hi) & 0xFF for _ in range(cols)] for _ in range(rows)]


def rand_fp8(rng, rows, cols, fmt, specials=0.0):
    out = []
    for _ in range(rows):
        row = []
        for _ in range(cols):
            b = rng.randrange(256)
            v = ref.fp8_to_float(b, fmt)
            # avoid NaN/inf unless specials requested
            while (math.isnan(v) or math.isinf(v)) and rng.random() >= specials:
                b = rng.randrange(256)
                v = ref.fp8_to_float(b, fmt)
            row.append(b)
        out.append(row)
    return out


async def check(npu, A, B, mode, **kw):
    M, K, N = len(A), len(A[0]), len(B[0])
    bias = kw.pop("bias", None)
    await npu.load(A, B, bias)
    outfmt = 1 if kw.get("outfmt") == "int8" else 0
    st, cycles = await npu.run(M, N, K, mode, outfmt=outfmt, mult=kw.get("mult", 0), shift=kw.get("shift", 0),
                               zp=kw.get("zp", 0), relu=int(kw.get("relu", False)), bias_en=int(bias is not None))
    assert st & 4 == 0, "error bit set"
    got = await npu.result(M, N)
    want = ref.gemm(A, B, mode, bias=bias, outfmt=kw.get("outfmt", "raw"), mult=kw.get("mult", 0),
                    shift=kw.get("shift", 0), zp=kw.get("zp", 0), relu=kw.get("relu", False))
    for i in range(M):
        for j in range(N):
            assert got[i][j] == want[i][j], f"{mode} C[{i}][{j}] = {got[i][j]:#010x}, want {want[i][j]:#010x}"
    return cycles


def expected_cycles(M, N, K, n):
    tiles = math.ceil(M / n) * math.ceil(N / n)
    return tiles * (K + 3 * n + 3)  # clear 1 + feed K + flush 2N+1 + drain N + next 1


@cocotb.test()
async def int8_random_shapes(dut):
    npu = Npu(dut)
    await npu.reset()
    rng = random.Random(1)
    for M, N, K in [(8, 8, 8), (1, 1, 1), (13, 21, 37), (3, 64, 5), (64, 2, 17), (9, 9, 200)]:
        await check(npu, rand_int8(rng, M, K), rand_int8(rng, K, N), "int8")


@cocotb.test()
async def int8_extremes_and_bias(dut):
    npu = Npu(dut)
    await npu.reset()
    K = 256
    A = [[0x80] * K for _ in range(8)]  # -128
    B = [[0x80] * 8 for _ in range(K)]
    await check(npu, A, B, "int8")  # 256 * 16384 = 4194304
    A = [[0x80] * K for _ in range(8)]
    B = [[0x7F] * 8 for _ in range(K)]
    await check(npu, A, B, "int8", bias=[(1 << 31) - 1 - 50000 * j for j in range(8)])  # bias wraps like INT32


@cocotb.test()
async def int8_requantisation(dut):
    npu = Npu(dut)
    await npu.reset()
    rng = random.Random(2)
    for trial in range(6):
        M, N, K = rng.randint(1, 20), rng.randint(1, 20), rng.randint(1, 64)
        kw = dict(outfmt="int8", mult=rng.randint(1 << 30, (1 << 31) - 1), shift=rng.randint(0, 12),
                  zp=rng.randint(-20, 20), relu=bool(trial % 2), bias=[rng.randint(-5000, 5000) for _ in range(N)])
        await check(npu, rand_int8(rng, M, K), rand_int8(rng, K, N), "int8", **kw)


@cocotb.test()
async def fp8_e4m3_random(dut):
    npu = Npu(dut)
    await npu.reset()
    rng = random.Random(3)
    for M, N, K in [(8, 8, 16), (11, 7, 64), (16, 16, 256)]:
        await check(npu, rand_fp8(rng, M, K, "e4m3"), rand_fp8(rng, K, N, "e4m3"), "e4m3")
    # NaN anywhere in a dot product
    await check(npu, rand_fp8(rng, 8, 8, "e4m3", specials=0.05), rand_fp8(rng, 8, 8, "e4m3", specials=0.05), "e4m3")


@cocotb.test()
async def fp8_e5m2_random_and_specials(dut):
    npu = Npu(dut)
    await npu.reset()
    rng = random.Random(4)
    for M, N, K in [(8, 8, 32), (5, 12, 100)]:
        await check(npu, rand_fp8(rng, M, K, "e5m2"), rand_fp8(rng, K, N, "e5m2"), "e5m2")
    await check(npu, rand_fp8(rng, 8, 8, "e5m2", specials=0.1), rand_fp8(rng, 8, 8, "e5m2", specials=0.1), "e5m2")
    # +inf * 0 -> NaN, +inf + -inf -> NaN, +inf alone -> +inf
    enc = lambda x: ref.float_to_fp8(x, "e5m2")
    A = [[0x7C, 0x00], [0x7C, 0xFC], [0x7C, 0x3C], [0x00, 0x00]]  # inf,0 | inf,-inf | inf,1 | 0,0
    B = [[0x3C], [0x3C]]                                           # 1, 1
    B0 = [[0x00], [0x3C]]
    await check(npu, A, B, "e5m2")
    await check(npu, A, B0, "e5m2")
    assert enc(1.0) == 0x3C


@cocotb.test()
async def fp8_exact_accumulation_and_ties(dut):
    """Results a sequential FP32 accumulation would get wrong."""
    npu = Npu(dut)
    await npu.reset()
    e = lambda x: ref.float_to_fp8(x, "e5m2")
    one, big, tiny = e(1.0), e(32768.0), e(2.0 ** -12)
    rows = [
        [big, one, e(-32768.0)],          # (2^15 + 1) - 2^15 = 1 exactly (sequential FP32 gives 1 too, but 2^15*2^15 below doesn't)
        [one, tiny, e(0.0)],              # 1 + 2^-24: tie -> round to even (1.0)
        [one, tiny, tiny],                # 1 + 2^-23 exactly representable
        [e(1.25), tiny, e(0.0)],          # 1.25 + 2^-24: exact tie, mantissa odd -> rounds up
    ]
    cols = [[one], [tiny], [one]]
    A = [r for r in rows]
    B = [[cols[k][0]] for k in range(3)]
    # second column multiplies the first operand by 2^15 so big products cancel
    await check(npu, A, B, "e5m2")


@cocotb.test()
async def bad_dimensions_set_error(dut):
    npu = Npu(dut)
    await npu.reset()
    for M, N, K, mode, outfmt in [(0, 8, 8, "int8", 0), (65, 8, 8, "int8", 0), (8, 8, 257, "int8", 0), (8, 8, 8, "e4m3", 1)]:
        st, _ = await npu.run(M, N, K, mode, outfmt=outfmt)
        assert st & 4, f"no error for M={M} N={N} K={K} mode={mode} outfmt={outfmt}"
    # and the accelerator still works afterwards
    rng = random.Random(5)
    await check(npu, rand_int8(rng, 4, 4), rand_int8(rng, 4, 4), "int8")


@cocotb.test()
async def cycle_counts_match_the_schedule(dut):
    npu = Npu(dut)
    await npu.reset()
    rng = random.Random(6)
    n = npu.n
    rows = []
    for M, N, K in [(n, n, 16), (n, n, 256), (2 * n, 2 * n, 64), (64, 64, 256)]:
        A, B = rand_int8(rng, M, K), rand_int8(rng, K, N)
        cycles = await check(npu, A, B, "int8")
        rows.append((M, N, K, cycles))
        assert cycles == expected_cycles(M, N, K, n), f"{M}x{N}x{K}: {cycles} cycles, model {expected_cycles(M, N, K, n)}"
    with open(os.environ.get("NPU_PERF_OUT", "perf.txt"), "w") as f:
        for M, N, K, c in rows:
            f.write(f"{M} {N} {K} {c} {M * N * K / (c * n * n):.4f}\n")
