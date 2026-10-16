// Physical-design configuration of npu_top (used by the ORFS flow and the
// gate-level simulation). The full default configuration (8x8 array, 64x64x256
// scratchpads = 48 KiB of flip-flop storage) is far too large for a
// flip-flop-only open-PDK flow on this machine, so the flow builds:
//   N = 4 (4x4 PE array), MAX_M = MAX_N = 8, MAX_K = 16, ACC_W = 80 (exact FP8).
// The port list is identical to npu_top. Storage: A 128 B, B 128 B, C 256 B,
// bias 32 B, all as flip-flops (no SRAM macros).
`default_nettype none
module npu_top_pd (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        cfg_valid,
    input  wire        cfg_we,
    input  wire [19:0] cfg_addr,
    input  wire [31:0] cfg_wdata,
    output wire [31:0] cfg_rdata,
    output wire        cfg_rvalid,
    output wire        irq_done
);
    npu_top #(.N(4), .MAX_M(8), .MAX_N(8), .MAX_K(16), .ACC_W(80)) u_npu (
        .clk(clk), .rst_n(rst_n), .cfg_valid(cfg_valid), .cfg_we(cfg_we), .cfg_addr(cfg_addr),
        .cfg_wdata(cfg_wdata), .cfg_rdata(cfg_rdata), .cfg_rvalid(cfg_rvalid), .irq_done(irq_done)
    );
endmodule
`default_nettype wire
