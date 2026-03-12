`timescale 1ns / 1ps

// ============================================================================
// TOP LEVEL: 8-Point FFT Core
// ============================================================================
module fft_8_point_top (
    input  wire        clk,
    input  wire        reset,
    
    // Control interface
    input  wire        start,
    output reg         done,
    
    // Input loading interface (load_en = 1 writes to memory)
    // Note: Provide input sequentially; it writes to memory bit-reversed internally.
    input  wire        load_en,
    input  wire [2:0]  load_addr,
    input  wire [15:0] load_data, // FP8 format {real[7:0], imag[7:0]}
    
    // Output unloading interface (2 cycle read latency!)
    input  wire        unload_en,
    input  wire [2:0]  unload_addr,
    output wire [15:0] unload_data
);

    // ------------------------------------------------------------------------
    // FSM State Definitions
    // ------------------------------------------------------------------------
    localparam IDLE           = 4'd0,
               START_AGU      = 4'd1,
               WAIT_AGU_START = 4'd2,
               READ_A         = 4'd3,
               READ_B         = 4'd4,
               WAIT_A         = 4'd5,
               WAIT_B         = 4'd6,
               WRITE_X        = 4'd7,
               WRITE_Y        = 4'd8,
               WAIT_AGU       = 4'd9,
               EVAL_AGU       = 4'd10,
               DONE_STATE     = 4'd11;

    reg [3:0] state;
    
    // Control registers
    reg start_agu_reg;
    reg next_step_reg;
    reg bank_sel;
    
    // Pipeline registers for butterfly data
    reg [15:0] A_reg;
    reg [15:0] B_reg;

    // ------------------------------------------------------------------------
    // AGU Instantiation
    // ------------------------------------------------------------------------
    wire [9:0] idx_a, idx_b, k;
    wire done_stage, done_fft;
    
    dit_fft_agu_variable #(
        .MAX_N(8),
        .ADDR_WIDTH(10)
    ) agu (
        .clk(clk),
        .reset(reset),
        .start(start_agu_reg),
        .N(10'd8),
        .next_step(next_step_reg),
        .idx_a(idx_a),
        .idx_b(idx_b),
        .k(k),
        .done_stage(done_stage),
        .done_fft(done_fft),
        .curr_stage(),
        .twiddle_output()
    );

    // ------------------------------------------------------------------------
    // Bit Reversal for Loading Data
    // ------------------------------------------------------------------------
    wire [9:0] load_addr_rev;
    
    bit_reverse #(
        .MAX_N(1024),
        .WIDTH(10)
    ) br (
        .in({7'b0, load_addr}), // Pad to 10 bits
        .N(10'd8),
        .out(load_addr_rev)
    );

    // ------------------------------------------------------------------------
    // Twiddle ROM Instantiation
    // ------------------------------------------------------------------------
    wire [15:0] w_factor;
    
    twiddle_factor_unified #(
        .MAX_N(8),
        .ADDR_WIDTH(10)
    ) twiddle_rom (
        .k(k),
        .n(10'd8),
        .PRECISION(1'b1), // FP8
        .twiddle_out(w_factor)
    );

    // ------------------------------------------------------------------------
    // Butterfly Generation Unit
    // ------------------------------------------------------------------------
    wire [15:0] bfly_X, bfly_Y;
    
    butterfly_wrapper #(
        .MULT_PRECISION(1), // FP8
        .ADD_PRECISION(1)   // FP8
    ) bfly (
        .A({A_reg, 8'h00}), // Pad from 16-bit to 24-bit for wrapper
        .B({B_reg, 8'h00}),
        .W(w_factor),
        .X(bfly_X),
        .Y(bfly_Y),
        .output_is_fp8()
    );

    // ------------------------------------------------------------------------
    // Unified Memory
    // ------------------------------------------------------------------------
    wire [15:0] rd_data;
    
    // Muxing memory input signals based on FSM state
    wire [9:0] mem_rd_addr = (state == IDLE && unload_en) ? {7'b0, unload_addr} :
                             (state == READ_A)            ? idx_a :
                             (state == READ_B)            ? idx_b : 10'd0;

    wire       mem_wr_en   = (state == IDLE && load_en)   ? 1'b1 :
                             (state == WRITE_X || state == WRITE_Y) ? 1'b1 : 1'b0;

    wire [9:0] mem_wr_addr = (state == IDLE && load_en)   ? load_addr_rev :
                             (state == WRITE_X)           ? idx_a :
                             (state == WRITE_Y)           ? idx_b : 10'd0;

    wire [23:0] mem_wr_data = (state == IDLE && load_en)  ? {load_data, 8'h00} :
                              (state == WRITE_X)          ? {bfly_X, 8'h00} :
                              (state == WRITE_Y)          ? {bfly_Y, 8'h00} : 24'd0;

    mixed_memory_unified #(
        .n(8),
        .ADDR_WIDTH(10)
    ) mem (
        .clk(clk),
        .rst(reset),
        .bank_sel(bank_sel),
        .rd_addr_0(mem_rd_addr),
        .rd_precision_0(1'b1), // Constant FP8 Read
        .rd_data_0(rd_data),
        .wr_en_1(mem_wr_en),
        .wr_addr_1(mem_wr_addr),
        .wr_data_1(mem_wr_data)
    );

    assign unload_data = rd_data;

    // ------------------------------------------------------------------------
    // FSM Control Logic
    // ------------------------------------------------------------------------
    always @(posedge clk or negedge reset) begin
        if (!reset) begin
            state         <= IDLE;
            start_agu_reg <= 1'b0;
            next_step_reg <= 1'b0;
            bank_sel      <= 1'b1; // Default to 1 so loading writes to Bank 0
            done          <= 1'b0;
            A_reg         <= 16'd0;
            B_reg         <= 16'd0;
        end else begin
            case (state)
                IDLE: begin
                    done <= 1'b0;
                    if (start) begin
                        bank_sel <= 1'b0; // Stage 0 reads Bank 0, writes Bank 1
                        state    <= START_AGU;
                    end else begin
                        bank_sel <= 1'b1; // Ready for external loading
                    end
                end
                
                START_AGU: begin
                    start_agu_reg <= 1'b1;
                    state         <= WAIT_AGU_START;
                end
                
                WAIT_AGU_START: begin
                    start_agu_reg <= 1'b0;
                    state         <= READ_A;
                end
                
                // --- 2-Cycle Memory Read Sequence ---
                READ_A: begin
                    // mem_rd_addr is idx_a. Next cycle it's registered.
                    state <= READ_B;
                end
                
                READ_B: begin
                    // mem_rd_addr is idx_b.
                    state <= WAIT_A;
                end
                
                WAIT_A: begin
                    // Data A is now available on rd_data port
                    A_reg <= rd_data;
                    state <= WAIT_B;
                end
                
                WAIT_B: begin
                    // Data B is now available on rd_data port
                    B_reg <= rd_data;
                    state <= WRITE_X;
                end
                // ------------------------------------

                WRITE_X: begin
                    // Butterfly computes combinationally; A_reg/B_reg are stable
                    state <= WRITE_Y;
                end
                
                WRITE_Y: begin
                    next_step_reg <= 1'b1;
                    state         <= WAIT_AGU;
                end
                
                WAIT_AGU: begin
                    next_step_reg <= 1'b0;
                    state         <= EVAL_AGU;
                end
                
                EVAL_AGU: begin
                    if (done_fft) begin
                        state    <= DONE_STATE;
                        bank_sel <= 1'b1; // End of stage 2 wrote to Bank 1. So we read from Bank 1.
                    end else if (done_stage) begin
                        bank_sel <= ~bank_sel; // Ping-pong banks!
                        state    <= READ_A;
                    end else begin
                        state    <= READ_A;
                    end
                end
                
                DONE_STATE: begin
                    done <= 1'b1;
                    if (!start) state <= IDLE; // Stay until start lowers
                end
                
                default: state <= IDLE;
            endcase
        end
    end

endmodule