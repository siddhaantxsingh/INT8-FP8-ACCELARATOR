// PE wrapper for the INT8+FP8 vs INT8-only datapath comparison (FP8, 80-bit exact accumulator).
`default_nettype none
module npu_pe_fp8 (
    input wire clk, input wire [1:0] mode, input wire clear, input wire shift, input wire valid_in,
    input wire [7:0] a_in, input wire [7:0] b_in, output wire valid_out, output wire [7:0] a_out,
    output wire [7:0] b_out, input wire [79:0] acc_in, input wire [2:0] flags_in,
    output wire [79:0] acc, output wire [2:0] flags);
    npu_pe #(.ACC_W(80), .FP8_EN(1'b1)) u (.*);
endmodule
`default_nettype wire
