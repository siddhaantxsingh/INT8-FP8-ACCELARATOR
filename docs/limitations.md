# Limitations

* **Physical design is partial and academic.** See [physical_design.md](physical_design.md). The full top level was built only in a reduced configuration (4×4 array, 8×8×16 flip-flop scratchpads) and only up to detailed placement on sky130hd; CTS, routing, final STA and GDSII were completed for the PE alone. Only the typical corner exists in the flow's libraries. Power is vectorless. No KLayout DRC/LVS. No tape-out, no silicon.
* **Slow clock at the top level.** After placement the 4×4 top misses 30 ns by 4 ns: the critical path runs through the combinational post unit (INT32 bias add, 32×32 requantisation multiplier) into the C scratchpad. It needs pipelining. The default 48 KiB scratchpads would need SRAM macros.
* **Exact FP8 accumulation is expensive:** about 21× the PE LUTs of INT8-only. This is a deliberate, documented trade (correctly rounded, order-independent results). A cheaper FP32-accumulating PE was not built for comparison.
* **No overlap of drain and compute:** 3N + 3 cycles of overhead per tile. Double-buffered accumulators would fix this.
* **Fixed maxima:** M, N ≤ 64 and K ≤ 256 (scratchpad parameters), with K ≤ 4,096 for the exactness proof. Larger GEMMs must be tiled by the host. There is no DMA or AXI interface; the host writes the scratchpads word by word through a simple port.
* **FP8 bias / scaling is not supported.** FP8 outputs are raw FP32. INT8 requantisation is per tensor (no per-channel multipliers).
* **Simulation only:** no FPGA bring-up.
