// Per-column output conversion (combinational).
//
//   INT8 mode: acc[31:0] + bias, then either the raw INT32 or gemmlowp-style
//              requantisation to INT8 (SaturatingRoundingDoublingHighMul,
//              RoundingDivideByPOT, zero point, clamp, optional ReLU),
//              written sign-extended to 32 bits.
//   FP8 modes: the exact fixed-point sum (LSB 2^-32) is rounded once to FP32
//              with round-to-nearest-even. Flags give NaN / +-inf. Exact
//              zero -> +0. (No FP32 overflow or subnormal is possible for
//              FP8 inputs with K <= 4096.)
`default_nettype none

module npu_post #(
    parameter int ACC_W = 80
) (
    input  wire  [1:0]       mode,
    input  wire  [ACC_W-1:0] acc,
    input  wire  [2:0]       flags,
    input  wire  [31:0]      bias,
    input  wire              requant,
    input  wire  [31:0]      qmult,
    input  wire  [4:0]       qshift,
    input  wire  [31:0]      qzp,
    input  wire              relu,
    output logic [31:0]      out
);
    // ---------------------------------------------------------- INT path
    logic signed [31:0] acc32, srdhm, rdb, q;
    always_comb begin
        logic signed [63:0] ab, x, nx, xs;
        logic        [31:0] mask, rem, thr;
        logic signed [31:0] lo;
        acc32 = $signed(acc[31:0]) + $signed(bias);
        // SaturatingRoundingDoublingHighMul
        ab = $signed(acc32) * $signed(qmult);
        x = ab + (ab >= 0 ? 64'sd1073741824 : (64'sd1 - 64'sd1073741824));
        nx = -x;
        xs = (x >= 0) ? (x >>> 31) : -(nx >>> 31);  // C-style truncation toward zero
        if (acc32 == 32'sh8000_0000 && qmult == 32'h8000_0000) srdhm = 32'sh7FFF_FFFF;
        else srdhm = xs[31:0];
        // RoundingDivideByPOT
        mask = (32'd1 << qshift) - 32'd1;
        rem = srdhm & mask;
        thr = (mask >> 1) + (srdhm < 0 ? 32'd1 : 32'd0);
        rdb = (srdhm >>> qshift) + ((rem > thr) ? 32'sd1 : 32'sd0);
        q = rdb + $signed(qzp);
        lo = relu ? (($signed(qzp) > -32'sd128) ? $signed(qzp) : -32'sd128) : -32'sd128;
        if (q > 32'sd127) q = 32'sd127;
        else if (q < lo) q = lo;
    end

    // ----------------------------------------------------------- FP path
    logic [31:0] fp;
    always_comb begin
        logic             s;
        logic [ACC_W-1:0] mag;
        int               p;
        logic [23:0]      m;
        logic             guard, sticky;
        logic [24:0]      mr;
        int               e;
        logic [ACC_W-1:0] below, sh;
        int               eb;
        s = acc[ACC_W-1];
        mag = s ? (~acc + 1'b1) : acc;
        e = 0; m = '0; guard = 1'b0; sticky = 1'b0; mr = '0; below = '0; sh = '0; eb = 0;
        p = -1;
        for (int i = 0; i < ACC_W; i++) if (mag[i]) p = i;
        fp = 32'd0;
        if (flags[2] || (flags[1] && flags[0])) fp = 32'h7FC0_0000;
        else if (flags[1]) fp = 32'h7F80_0000;
        else if (flags[0]) fp = 32'hFF80_0000;
        else if (p >= 0) begin
            e = p - 32;
            if (p <= 23) begin
                sh = mag << (23 - p);
                m = sh[23:0];
                eb = e + 127;
                fp = {s, eb[7:0], m[22:0]};
            end else begin
                sh = mag >> (p - 23);
                m = sh[23:0];
                guard = mag[p - 24];
                below = mag & ((80'd1 << (p - 24)) - 80'd1);
                sticky = |below;
                mr = {1'b0, m} + ((guard && (sticky || m[0])) ? 25'd1 : 25'd0);
                if (mr[24]) begin
                    mr = mr >> 1;
                    e = e + 1;
                end
                eb = e + 127;
                fp = {s, eb[7:0], mr[22:0]};
            end
        end
    end

    assign out = (mode != 2'd0) ? fp : (requant ? q : acc32);
endmodule

`default_nettype wire
