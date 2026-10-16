// Processing element of the output-stationary systolic array.
//
// Each cycle with valid_in it multiplies a_in x b_in and adds the product to
// an ACC_W-bit two's-complement accumulator:
//   * INT8:  signed 8x8 product, added at bit 0 (exact INT32 sum for K <= 4096)
//   * FP8 (OCP E4M3 / E5M2): the product significand (<= 8 bits) is shifted
//     to its exact binary position (accumulator LSB = 2^-32), so the whole dot
//     product is accumulated *exactly*; rounding happens once, later.
//   NaN / +inf / -inf are tracked in sticky flags (E5M2 inf x 0 = NaN).
// a and b move one PE right / down per cycle (registered).
// Drain: with shift=1 the accumulator loads the value of the PE above,
// so a column shifts out through its bottom PE in N cycles.
`default_nettype none

module npu_pe #(
    parameter int ACC_W = 80,
    parameter bit FP8_EN = 1'b1  // 0: INT8-only PE (for area comparison)
) (
    input  wire              clk,
    input  wire  [1:0]       mode,     // 0 int8, 1 e4m3, 2 e5m2
    input  wire              clear,
    input  wire              shift,
    input  wire              valid_in,
    input  wire  [7:0]       a_in,
    input  wire  [7:0]       b_in,
    output logic             valid_out,
    output logic [7:0]       a_out,
    output logic [7:0]       b_out,
    input  wire  [ACC_W-1:0] acc_in,
    input  wire  [2:0]       flags_in,  // {nan, pinf, ninf}
    output logic [ACC_W-1:0] acc,
    output logic [2:0]       flags
);
    // ------------------------------------------------------------ decode
    // value = (-1)^s * sig * 2^exp; exp is the unbiased exponent of the
    // significand's LSB.
    function automatic void decode(input logic [7:0] x, input logic [1:0] md,
                                   output logic s, output logic [3:0] sig, output logic signed [6:0] ex,
                                   output logic nan, output logic inf);
        s = x[7];
        nan = 1'b0;
        inf = 1'b0;
        if (md == 2'd1) begin  // E4M3: bias 7, no inf, NaN = S.1111.111
            if (x[6:3] == 4'hF && x[2:0] == 3'h7) nan = 1'b1;
            if (x[6:3] == 4'h0) begin sig = {1'b0, x[2:0]}; ex = 7'sd1 - 7'sd10; end
            else begin sig = {1'b1, x[2:0]}; ex = $signed({3'b000, x[6:3]}) - 7'sd10; end
        end else begin         // E5M2: bias 15, IEEE-like
            if (x[6:2] == 5'h1F) begin
                if (x[1:0] == 2'b00) inf = 1'b1; else nan = 1'b1;
            end
            if (x[6:2] == 5'h00) begin sig = {2'b00, x[1:0]}; ex = 7'sd1 - 7'sd17; end
            else begin sig = {2'b01, x[1:0]}; ex = $signed({2'b00, x[6:2]}) - 7'sd17; end
        end
    endfunction

    logic              sa, sb, nana, nanb, infa, infb;
    logic [3:0]        siga, sigb;
    logic signed [6:0] exa, exb;
    always_comb begin
        decode(a_in, mode, sa, siga, exa, nana, infa);
        decode(b_in, mode, sb, sigb, exb, nanb, infb);
    end

    // ------------------------------------------------------------ product
    logic [ACC_W-1:0] term;
    logic [2:0]       newflags;
    always_comb begin
        logic [7:0]       psig;
        logic signed [7:0] sh;
        logic [ACC_W-1:0] mag;
        logic             ps;
        logic signed [15:0] prod16;
        term = '0;
        newflags = 3'b000;
        psig = '0; sh = '0; mag = '0; ps = 1'b0; prod16 = '0;
        if (mode == 2'd0) begin
            prod16 = $signed(a_in) * $signed(b_in);
            term = {{(ACC_W-16){1'b0}}, prod16};
            if (term[15]) term[ACC_W-1:16] = '1;  // sign-extend the 16-bit product
        end else if (FP8_EN) begin
            ps = sa ^ sb;
            psig = siga * sigb;
            sh = {exa[6], exa} + {exb[6], exb} + 8'sd32;  // 0 .. 58 for finite operands
            mag = {{(ACC_W-8){1'b0}}, psig} << sh[6:0];
            if (nana || nanb) newflags = 3'b100;
            else if (infa || infb) begin
                // inf x 0 (the zero is a finite operand with significand 0) -> NaN
                if ((!infa && siga == 4'd0) || (!infb && sigb == 4'd0)) newflags = 3'b100;
                else newflags = ps ? 3'b001 : 3'b010;
            end else begin
                term = ps ? (~mag + 1'b1) : mag;
            end
        end
    end

    always_ff @(posedge clk) begin
        a_out <= a_in;
        b_out <= b_in;
        valid_out <= valid_in;
        if (clear) begin
            acc <= '0;
            flags <= '0;
        end else if (shift) begin
            acc <= acc_in;
            flags <= flags_in;
        end else if (valid_in) begin
            acc <= acc + term;
            flags <= flags | newflags;
        end
    end
endmodule

`default_nettype wire
