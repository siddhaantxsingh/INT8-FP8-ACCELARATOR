// npu_top: N x N output-stationary systolic GEMM accelerator, C = A x B.
//
// Host interface: a simple synchronous memory-mapped port (cfg_*), byte
// addresses, 32-bit data, one access per cycle; reads return data the next
// cycle (cfg_rvalid).
//
//   0x00000 CTRL     write 1: start (ignored while busy)
//   0x00004 STATUS   bit0 busy, bit1 done (cleared by start), bit2 error (bad dimensions)
//   0x00008 M        0x0000C N         0x00010 K
//   0x00014 MODE     0 INT8, 1 FP8 E4M3, 2 FP8 E5M2
//   0x00018 OUTFMT   0 raw (INT32 / FP32), 1 INT8 requantised (INT8 mode only)
//   0x0001C QMULT    0x00020 QSHIFT   0x00024 QZP   0x00028 RELU   0x0002C BIAS_EN
//   0x00030 CYCLES   cycles taken by the last run (start to done)
//   0x10000 A        A stored K-major: byte k*MAX_M + m holds A[m][k]
//   0x20000 B        byte k*MAX_N + n holds B[k][n]
//   0x40000 C        word (m*MAX_N + n) holds C[m][n] (read-only)
//   0x60000 BIAS     word n holds bias[n] (INT32, INT8 mode)
//
// A and B are written 32 bits at a time (4 consecutive m, resp. n values);
// the scratchpads are banked by m mod N (A), n mod N (B, C) so the array
// reads one A element per row and one B element per column every cycle,
// and the drain writes one C value per column every cycle.
//
// Schedule per N x N output tile: clear accumulators (1 cycle), stream K
// steps (A rows and B columns enter skewed by row / column index), wait
// 2(N-1)+2 cycles for the wavefront to reach the last PE, then drain the
// accumulators in N cycles (column-parallel conversion and write-back).
// Cycles per tile = 1 (clear) + K (feed) + 2N+1 (flush) + N (drain) + 1 (next)
// = K + 3N + 3; peak = N*N MACs per cycle.
`default_nettype none

module npu_top #(
    parameter int N     = 8,
    parameter int MAX_M = 64,
    parameter int MAX_N = 64,
    parameter int MAX_K = 256,
    parameter int ACC_W = 80
) (
    input  wire         clk,
    input  wire         rst_n,
    input  wire         cfg_valid,
    input  wire         cfg_we,
    input  wire  [19:0] cfg_addr,
    input  wire  [31:0] cfg_wdata,
    output logic [31:0] cfg_rdata,
    output logic        cfg_rvalid,
    output logic        irq_done
);
    localparam int AW = $clog2(MAX_K * MAX_M / N);  // A/B bank address width
    localparam int CW = $clog2(MAX_M * MAX_N / N);  // C bank address width

    // ------------------------------------------------------------ registers
    logic [31:0] r_m, r_n, r_k, r_qmult, r_qzp, r_cycles;
    logic [1:0]  r_mode;
    logic        r_outfmt, r_relu, r_bias_en, busy, done, err;
    logic [4:0]  r_qshift;
    logic [31:0] bias [MAX_N];

    // ------------------------------------------------------------ scratchpads
    logic [7:0]  amem [N][MAX_K * MAX_M / N];
    logic [7:0]  bmem [N][MAX_K * MAX_N / N];
    logic [31:0] cmem [N][MAX_M * MAX_N / N];

    wire sel_a = cfg_addr[19:16] == 4'h1;
    wire sel_b = cfg_addr[19:16] == 4'h2;
    wire sel_c = cfg_addr[19:16] == 4'h4;
    wire sel_bias = cfg_addr[19:16] == 4'h6;
    wire host_wr = cfg_valid && cfg_we && !busy;  // memories are locked while running

    // A/B host writes: 4 bytes to 4 consecutive banks
    always_ff @(posedge clk) begin
        if (host_wr && (sel_a || sel_b)) begin
            for (int i = 0; i < 4; i++) begin
                automatic int lin = int'(cfg_addr[15:0]) + i;           // k*MAX + idx
                automatic int idx = sel_a ? (lin % MAX_M) : (lin % MAX_N);
                automatic int kk  = sel_a ? (lin / MAX_M) : (lin / MAX_N);
                automatic int bank = idx % N;
                automatic int addr = kk * ((sel_a ? MAX_M : MAX_N) / N) + idx / N;
                if (sel_a) amem[bank][addr] <= cfg_wdata[8*i +: 8];
                else       bmem[bank][addr] <= cfg_wdata[8*i +: 8];
            end
        end
    end

    // ------------------------------------------------------------ controller
    typedef enum logic [2:0] {S_IDLE, S_CLEAR, S_FEED, S_FLUSH, S_DRAIN, S_NEXT} state_t;
    state_t st;
    logic [31:0] tm, tn, k, cnt;   // tile origin (rows / cols), k step, counter
    logic        feed_v;            // a read was issued this cycle (data valid next cycle)
    logic        clear, shift;

    // bank read addresses for step k
    logic [7:0] a_rd [N];
    logic [7:0] b_rd [N];
    logic       rd_v;
    always_ff @(posedge clk) begin
        for (int r = 0; r < N; r++) begin
            automatic int m = int'(tm) + r;
            automatic int a_addr = int'(k) * (MAX_M / N) + m / N;
            a_rd[r] <= (m < int'(r_m)) ? amem[m % N][a_addr] : 8'd0;
        end
        for (int c = 0; c < N; c++) begin
            automatic int n = int'(tn) + c;
            automatic int b_addr = int'(k) * (MAX_N / N) + n / N;
            b_rd[c] <= (n < int'(r_n)) ? bmem[n % N][b_addr] : 8'd0;
        end
        rd_v <= feed_v;
    end

    // ------------------------------------------------------------ array
    logic [7:0]       a_skew [N][N];  // a_skew[r][i]: row r delayed i+1 cycles
    logic [7:0]       b_skew [N][N];
    logic             v_skew [N][N];
    logic [7:0]       a_in   [N][N];
    logic [7:0]       b_in   [N][N];
    logic             v_in   [N][N];
    logic [7:0]       a_out  [N][N];
    logic [7:0]       b_out  [N][N];
    logic             v_out  [N][N];
    logic [ACC_W-1:0] acc    [N][N];
    logic [2:0]       flg    [N][N];

    always_ff @(posedge clk) begin
        for (int r = 0; r < N; r++) begin
            a_skew[r][0] <= a_rd[r];
            v_skew[r][0] <= rd_v;
            b_skew[r][0] <= b_rd[r];
            for (int i = 1; i < N; i++) begin
                a_skew[r][i] <= a_skew[r][i-1];
                v_skew[r][i] <= v_skew[r][i-1];
                b_skew[r][i] <= b_skew[r][i-1];
            end
        end
    end

    genvar gr, gc;
    generate
        for (gr = 0; gr < N; gr++) begin : row
            for (gc = 0; gc < N; gc++) begin : col
                if (gc == 0) begin : left
                    // row gr enters after gr cycles of skew
                    if (gr == 0) begin : nod
                        assign a_in[gr][gc] = a_rd[gr];
                        assign v_in[gr][gc] = rd_v;
                    end else begin : d
                        assign a_in[gr][gc] = a_skew[gr][gr-1];
                        assign v_in[gr][gc] = v_skew[gr][gr-1];
                    end
                end else begin : inner
                    assign a_in[gr][gc] = a_out[gr][gc-1];
                    assign v_in[gr][gc] = v_out[gr][gc-1];
                end
                if (gr == 0) begin : top
                    if (gc == 0) begin : nod
                        assign b_in[gr][gc] = b_rd[gc];
                    end else begin : d
                        assign b_in[gr][gc] = b_skew[gc][gc-1];
                    end
                end else begin : down
                    assign b_in[gr][gc] = b_out[gr-1][gc];
                end
                npu_pe #(.ACC_W(ACC_W)) pe (
                    .clk(clk), .mode(r_mode), .clear(clear), .shift(shift),
                    .valid_in(v_in[gr][gc]), .a_in(a_in[gr][gc]), .b_in(b_in[gr][gc]),
                    .valid_out(v_out[gr][gc]), .a_out(a_out[gr][gc]), .b_out(b_out[gr][gc]),
                    .acc_in(gr == 0 ? {ACC_W{1'b0}} : acc[gr-1][gc]), .flags_in(gr == 0 ? 3'b000 : flg[gr-1][gc]),
                    .acc(acc[gr][gc]), .flags(flg[gr][gc])
                );
            end
        end
    endgenerate

    // ------------------------------------------------------------ drain / post
    logic [31:0] post [N];
    generate
        for (gc = 0; gc < N; gc++) begin : pp
            npu_post #(.ACC_W(ACC_W)) u (
                .mode(r_mode), .acc(acc[N-1][gc]), .flags(flg[N-1][gc]),
                .bias((r_bias_en && r_mode == 2'd0 && (tn + gc) < MAX_N) ? bias[(tn + gc) % MAX_N] : 32'd0),
                .requant(r_outfmt && r_mode == 2'd0), .qmult(r_qmult), .qshift(r_qshift), .qzp(r_qzp), .relu(r_relu),
                .out(post[gc])
            );
        end
    endgenerate

    // drain cycle cnt (0..N-1) outputs row tm + N-1-cnt
    always_ff @(posedge clk) begin
        if (st == S_DRAIN) begin
            for (int c = 0; c < N; c++) begin
                automatic int m = int'(tm) + N - 1 - int'(cnt);
                automatic int n = int'(tn) + c;
                if (m < int'(r_m) && n < int'(r_n))
                    cmem[n % N][m * (MAX_N / N) + n / N] <= post[c];
            end
        end
    end

    // ------------------------------------------------------------ FSM
    wire dims_ok = r_m >= 1 && r_m <= MAX_M && r_n >= 1 && r_n <= MAX_N && r_k >= 1 && r_k <= MAX_K &&
                   r_mode <= 2'd2 && !(r_outfmt && r_mode != 2'd0);
    assign clear = st == S_CLEAR;
    assign shift = st == S_DRAIN;
    assign feed_v = st == S_FEED;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st <= S_IDLE; busy <= 1'b0; done <= 1'b0; err <= 1'b0;
            tm <= '0; tn <= '0; k <= '0; cnt <= '0; r_cycles <= '0;
            r_m <= '0; r_n <= '0; r_k <= '0; r_mode <= '0; r_outfmt <= 1'b0; r_relu <= 1'b0; r_bias_en <= 1'b0;
            r_qmult <= '0; r_qshift <= '0; r_qzp <= '0;
            irq_done <= 1'b0;
        end else begin
            irq_done <= 1'b0;
            if (busy) r_cycles <= r_cycles + 32'd1;
            // register writes
            if (cfg_valid && cfg_we && cfg_addr[19:16] == 4'h0 && !busy) begin
                unique case (cfg_addr[7:0])
                    8'h00: if (cfg_wdata[0]) begin
                        done <= 1'b0;
                        r_cycles <= '0;
                        if (dims_ok) begin
                            busy <= 1'b1; err <= 1'b0; st <= S_CLEAR; tm <= '0; tn <= '0;
                        end else begin
                            err <= 1'b1; done <= 1'b1;
                        end
                    end
                    8'h08: r_m <= cfg_wdata;
                    8'h0C: r_n <= cfg_wdata;
                    8'h10: r_k <= cfg_wdata;
                    8'h14: r_mode <= cfg_wdata[1:0];
                    8'h18: r_outfmt <= cfg_wdata[0];
                    8'h1C: r_qmult <= cfg_wdata;
                    8'h20: r_qshift <= cfg_wdata[4:0];
                    8'h24: r_qzp <= cfg_wdata;
                    8'h28: r_relu <= cfg_wdata[0];
                    8'h2C: r_bias_en <= cfg_wdata[0];
                    default: ;
                endcase
            end
            unique case (st)
                S_IDLE: ;
                S_CLEAR: begin st <= S_FEED; k <= '0; end
                S_FEED: begin
                    if (k == r_k - 1) begin st <= S_FLUSH; cnt <= '0; end
                    else k <= k + 32'd1;
                end
                S_FLUSH: begin
                    // read latency (1) + skew (N-1) + propagation (N-1) + accumulate (1)
                    if (cnt == 32'(2 * N)) begin st <= S_DRAIN; cnt <= '0; end
                    else cnt <= cnt + 32'd1;
                end
                S_DRAIN: begin
                    if (cnt == 32'(N - 1)) st <= S_NEXT;
                    else cnt <= cnt + 32'd1;
                end
                S_NEXT: begin
                    if (tn + 32'(N) < r_n) begin tn <= tn + 32'(N); st <= S_CLEAR; end
                    else if (tm + 32'(N) < r_m) begin tm <= tm + 32'(N); tn <= '0; st <= S_CLEAR; end
                    else begin st <= S_IDLE; busy <= 1'b0; done <= 1'b1; irq_done <= 1'b1; end
                end
                default: st <= S_IDLE;
            endcase
        end
    end

    // bias writes
    always_ff @(posedge clk) begin
        if (host_wr && sel_bias) bias[cfg_addr[2 +: $clog2(MAX_N)]] <= cfg_wdata;
    end

    // ------------------------------------------------------------ reads
    always_ff @(posedge clk) begin
        cfg_rvalid <= cfg_valid && !cfg_we;
        cfg_rdata <= 32'd0;
        if (cfg_valid && !cfg_we) begin
            if (sel_c) begin
                automatic int w = int'(cfg_addr[15:2]);
                automatic int m = w / MAX_N;
                automatic int n = w % MAX_N;
                cfg_rdata <= cmem[n % N][m * (MAX_N / N) + n / N];
            end else if (cfg_addr[19:16] == 4'h0) begin
                unique case (cfg_addr[7:0])
                    8'h04: cfg_rdata <= {29'd0, err, done, busy};
                    8'h08: cfg_rdata <= r_m;
                    8'h0C: cfg_rdata <= r_n;
                    8'h10: cfg_rdata <= r_k;
                    8'h14: cfg_rdata <= {30'd0, r_mode};
                    8'h30: cfg_rdata <= r_cycles;
                    default: cfg_rdata <= 32'd0;
                endcase
            end
        end
    end
endmodule

`default_nettype wire
