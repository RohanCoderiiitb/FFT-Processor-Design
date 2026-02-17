//mixed-precision FFT core for 8-point FFT
//16-bit butterfly I/O with 24-bit memory

module mixed_fft_8_core #(
    parameter MAX_N = 8,
    parameter ADDR_WIDTH = 3
)(
    input wire clk,
    input wire rst,
    input wire start,
    input wire [ADDR_WIDTH-1:0] N,
    output reg done,
    output reg error,
    
    //external write interface
    input wire ext_wr_en,
    input wire [ADDR_WIDTH-1:0] ext_wr_addr,
    input wire [23:0] ext_wr_data,
    input wire ext_bank_sel,
    
    //external read interface
    input wire [ADDR_WIDTH-1:0] ext_rd_addr,
    input wire ext_reading,
    output wire [23:0] rd_data_0
);

    //state machine
    localparam IDLE = 4'd0;
    localparam INIT = 4'd1;
    localparam READ_A = 4'd2;
    localparam WAIT_A = 4'd3;
    localparam READ_B = 4'd4;
    localparam WAIT_B = 4'd5;
    localparam COMPUTE = 4'd6;
    localparam WRITE_X = 4'd7;
    localparam WRITE_Y = 4'd8;
    localparam DONE = 4'd9;
    
    reg [3:0] state, next_state;
    
    //stage precision configuration
    localparam STAGE0_MULT_PREC = 0;
    localparam STAGE0_ADD_PREC = 0;
    localparam STAGE0_OUT_PREC = 0;
    localparam STAGE1_MULT_PREC = 1;
    localparam STAGE1_ADD_PREC = 0;
    localparam STAGE1_OUT_PREC = 1;
    localparam STAGE2_MULT_PREC = 1;
    localparam STAGE2_ADD_PREC = 1;
    localparam STAGE2_OUT_PREC = 1;

    
    //precision control
    reg current_mult_prec;
    reg current_add_prec;
    reg memory_read_prec;
    reg memory_write_prec;
    
    always @(*) begin
        case (curr_stage)
            3'd0: begin
                current_mult_prec = STAGE0_MULT_PREC;
                current_add_prec = STAGE0_ADD_PREC;
                memory_read_prec = STAGE0_MULT_PREC;
                memory_write_prec = STAGE0_OUT_PREC;
            end
            3'd1: begin
                current_mult_prec = STAGE1_MULT_PREC;
                current_add_prec = STAGE1_ADD_PREC;
                memory_read_prec = STAGE0_OUT_PREC;
                memory_write_prec = STAGE1_OUT_PREC;
            end
            3'd2: begin
                current_mult_prec = STAGE2_MULT_PREC;
                current_add_prec = STAGE2_ADD_PREC;
                memory_read_prec = STAGE1_OUT_PREC;
                memory_write_prec = STAGE2_OUT_PREC;
            end
            default: begin
                current_mult_prec = 0;
                current_add_prec = 0;
                memory_read_prec = 0;
                memory_write_prec = 0;
            end
        endcase
    end
    
    //AGU signals
    reg agu_next_step;
    wire [ADDR_WIDTH-1:0] idx_a, idx_b, k;
    wire agu_done_stage, agu_done_fft;
    wire [2:0] curr_stage;
    
    //butterfly I/O (16-bit)
    reg [23:0] A_mem, B_mem;  // From memory (24-bit)
    wire [15:0] X_bf, Y_bf;   // From butterfly (16-bit)
    wire bf_output_is_fp8;    // Which precision butterfly output
    reg [15:0] X_reg, Y_reg;
    reg output_was_fp8;
    
    //memory control
    reg [ADDR_WIDTH-1:0] int_rd_addr;
    wire [23:0] int_rd_data;
    reg int_wr_en;
    reg [ADDR_WIDTH-1:0] int_wr_addr;
    reg [23:0] int_wr_data;
    
    //memory multiplexing
    wire final_wr_en = ext_wr_en | int_wr_en;
    wire [ADDR_WIDTH-1:0] final_wr_addr = ext_wr_en ? ext_wr_addr : int_wr_addr;
    wire [23:0] final_wr_data = ext_wr_en ? ext_wr_data : int_wr_data;
    wire [ADDR_WIDTH-1:0] final_rd_addr = ext_reading ? ext_rd_addr : int_rd_addr;
    
    //ping-pong bank control
    reg fft_bank_sel;
    wire active_bank_sel = ext_reading ? ext_bank_sel :
                          (state == IDLE) ? ext_bank_sel :
                          fft_bank_sel;
    
    //AGU
    dit_fft_agu_variable #(
        .MAX_N(MAX_N),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) agu_inst (
        .clk(clk),
        .reset(rst),
        .N(N),
        .next_step(agu_next_step),
        .idx_a(idx_a),
        .idx_b(idx_b),
        .k(k),
        .done_stage(agu_done_stage),
        .done_fft(agu_done_fft),
        .curr_stage(curr_stage),
        .twiddle_output()
    );
    
    //twiddle ROM
    wire [15:0] twiddle;
    twiddle_factor_unified #(
        .MAX_N(MAX_N),
        .PRECISION(0)  //will be controlled by stage
    ) twiddle_rom (
        .k(k),
        .n(N),
        .twiddle_out(twiddle)
    );
    
    //TODO: Add mux or generate block to select twiddle ROM precision
    //based on current_mult_prec
    
    //butterfly wrapper with 16-bit I/O
    butterfly_wrapper_16bit #(
        .MULT_PRECISION(0),  //will be controlled by stage
        .ADD_PRECISION(0)
    ) butterfly_inst (
        .A_mem(A_mem),
        .B_mem(B_mem),
        .W(twiddle),
        .X(X_bf),
        .Y(Y_bf),
        .output_is_fp8(bf_output_is_fp8)
    );
    
    //TODO: Add mux or generate block to select butterfly precision
    //based on current_mult_prec and current_add_prec
    
    //unified memory
    mixed_memory_unified #(
        .n(MAX_N),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) memory_inst (
        .clk(clk),
        .rst(rst),
        .bank_sel(active_bank_sel),
        .rd_addr_0(final_rd_addr),
        .rd_precision_0(memory_read_prec),
        .rd_data_0(int_rd_data[15:0]),
        .wr_en_1(final_wr_en),
        .wr_addr_1(final_wr_addr),
        .wr_data_1(final_wr_data)
    );
    
    //convert 16-bit memory read to 24-bit for butterfly
    assign int_rd_data[23:16] = memory_read_prec ? int_rd_data[15:8] : 8'h00;
    assign rd_data_0 = int_rd_data;
    
    //convert 16-bit butterfly output to 24-bit for memory write
    //handled in WRITE_X and WRITE_Y states directly
    
    //stage completion detection
    reg prev_done_stage;
    wire stage_complete = agu_done_stage && !prev_done_stage;
    
    //state machine
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state <= IDLE;
            done <= 0;
            error <= 0;
            A_mem <= 0;
            B_mem <= 0;
            X_reg <= 0;
            Y_reg <= 0;
            output_was_fp8 <= 0;
            int_rd_addr <= 0;
            int_wr_en <= 0;
            int_wr_addr <= 0;
            agu_next_step <= 0;
            fft_bank_sel <= 0;
            prev_done_stage <= 0;
        end else begin
            state <= next_state;
            int_wr_en <= 0;
            agu_next_step <= 0;
            prev_done_stage <= agu_done_stage;
            
            if (stage_complete && state != IDLE && state != DONE) begin
                fft_bank_sel <= ~fft_bank_sel;
            end
            
            case (state)
                IDLE: begin
                    done <= 0;
                    error <= 0;
                    fft_bank_sel <= 0;
                    if (start && (N != MAX_N || (N & (N-1)) != 0)) begin
                        error <= 1;
                    end
                end
                
                INIT: begin
                end
                
                READ_A: begin
                    int_rd_addr <= idx_a;
                end
                
                WAIT_A: begin
                end
                
                READ_B: begin
                    A_mem <= int_rd_data;
                    int_rd_addr <= idx_b;
                end
                
                WAIT_B: begin
                end
                
                COMPUTE: begin
                    B_mem <= int_rd_data;
                    X_reg <= X_bf;
                    Y_reg <= Y_bf;
                    output_was_fp8 <= bf_output_is_fp8;
                end
                
                WRITE_X: begin
                    int_wr_en <= 1;
                    int_wr_addr <= idx_a;
                    // int_wr_data set by combinational block above
                    if (output_was_fp8) begin
                        int_wr_data <= {X_reg, 8'h00};
                    end else begin
                        int_wr_data <= {16'h0000, X_reg[7:0]};
                    end
                end
                
                WRITE_Y: begin
                    int_wr_en <= 1;
                    int_wr_addr <= idx_b;
                    if (output_was_fp8) begin
                        int_wr_data <= {Y_reg, 8'h00};
                    end else begin
                        int_wr_data <= {16'h0000, Y_reg[7:0]};
                    end
                    agu_next_step <= 1;
                end
                
                DONE: begin
                    done <= 1;
                end
            endcase
        end
    end
    
    //next state logic
    always @(*) begin
        next_state = state;
        case (state)
            IDLE: if (start && !error) next_state = INIT;
            INIT: next_state = READ_A;
            READ_A: next_state = WAIT_A;
            WAIT_A: next_state = READ_B;
            READ_B: next_state = WAIT_B;
            WAIT_B: next_state = COMPUTE;
            COMPUTE: next_state = WRITE_X;
            WRITE_X: next_state = WRITE_Y;
            WRITE_Y: begin
                if (agu_done_fft) next_state = DONE;
                else next_state = READ_A;
            end
            DONE: next_state = IDLE;
        endcase
    end

endmodule
