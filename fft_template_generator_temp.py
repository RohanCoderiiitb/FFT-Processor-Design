"""
Mixed-Precision FFT Generator
Butterfly wrapper outputs 16-bit (matches actual butterfly modules)
Memory interface handles 24-bit ↔ 16-bit conversion
"""

import os
import math


class CorrectedMixedPrecisionFFTGenerator:
    def __init__(self, fft_size):
        self.fft_size = fft_size
        self.num_stages = int(math.log2(fft_size))
        self.addr_width = int(math.log2(fft_size))
        self.chromosome_length = self.num_stages * 2
        
        print(f"FFT-{fft_size} Configuration:")
        print(f"  Stages: {self.num_stages}")
        print(f"  Chromosome length: {self.chromosome_length}")
    
    def get_chromosome_length(self):
        return self.chromosome_length
    
    def chromosome_to_config(self, chromosome):
        config = {
            'fft_size': self.fft_size,
            'num_stages': self.num_stages,
            'addr_width': self.addr_width,
            'stages': []
        }
        
        for stage in range(self.num_stages):
            idx = stage * 2
            mult_prec = chromosome[idx] if idx < len(chromosome) else 0
            add_prec = chromosome[idx + 1] if idx + 1 < len(chromosome) else 0
            output_prec = max(mult_prec, add_prec)
            
            config['stages'].append({
                'stage_num': stage,
                'mult_precision': mult_prec,
                'add_precision': add_prec,
                'output_precision': output_prec
            })
        
        return config
    
    def generate_complete_fft(self, chromosome, output_dir='./generated_designs'):
        config = self.chromosome_to_config(chromosome)
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate files
        core = self._generate_core(config)
        top = self._generate_top(config)
        wrapper = self._generate_wrapper()
        
        base_name = f"mixed_fft_{self.fft_size}"
        
        with open(f"{output_dir}/{base_name}_core.v", 'w') as f:
            f.write(core)
        with open(f"{output_dir}/{base_name}_top.v", 'w') as f:
            f.write(top)
        with open(f"{output_dir}/butterfly_wrapper_16bit.v", 'w') as f:
            f.write(wrapper)
        
        print(f"✓ Generated: {base_name}_core.v")
        print(f"✓ Generated: {base_name}_top.v") 
        print(f"✓ Generated: butterfly_wrapper_16bit.v")
        
        return f"{output_dir}/{base_name}_top.v"
    
    def _generate_wrapper(self):
        """Generate butterfly wrapper with 16-bit outputs"""
        return '''// Butterfly Wrapper with 16-bit I/O
// Handles conversion between 24-bit memory format and butterfly I/O

module butterfly_wrapper_16bit #(
    parameter MULT_PRECISION = 0,  // 0=FP4, 1=FP8
    parameter ADD_PRECISION = 0    // 0=FP4, 1=FP8
)(
    input [23:0] A_mem, B_mem,  // 24-bit from memory
    input [15:0] W,              // 16-bit twiddle
    output [15:0] X, Y,          // 16-bit to memory interface
    output output_is_fp8         // flag: 0=FP4, 1=FP8
);

    generate
        if (MULT_PRECISION == 0 && ADD_PRECISION == 0) begin : USE_PURE_FP4
            // Pure FP4: 8-bit butterfly
            wire [7:0] X_fp4, Y_fp4;
            
            fp4_butterfly_generation_unit fp4_bf (
                .A(A_mem[7:0]),
                .B(B_mem[7:0]),
                .W(W),
                .X(X_fp4),
                .Y(Y_fp4)
            );
            
            // Zero-extend to 16-bit
            assign X = {8'h00, X_fp4};
            assign Y = {8'h00, Y_fp4};
            assign output_is_fp8 = 0;
            
        end else if (MULT_PRECISION == 1 && ADD_PRECISION == 1) begin : USE_PURE_FP8
            // Pure FP8: 16-bit butterfly
            
            fp8_butterfly_generation_unit fp8_bf (
                .A(A_mem[23:8]),
                .B(B_mem[23:8]),
                .W(W),
                .X(X),
                .Y(Y)
            );
            
            assign output_is_fp8 = 1;
            
        end else if (MULT_PRECISION == 1 && ADD_PRECISION == 0) begin : USE_FP8mul_FP4add
            // FP8 mult, FP4 add: outputs 8-bit (FP4)
            wire [7:0] X_fp4, Y_fp4;
            
            butterfly_generation_unit_8add_4mul mixed_bf (
                .A(A_mem[23:8]),  // FP8 input
                .B(B_mem[23:8]),  // FP8 input
                .W(W),            // FP8 twiddle
                .X(X_fp4),
                .Y(Y_fp4)
            );
            
            // Zero-extend to 16-bit
            assign X = {8'h00, X_fp4};
            assign Y = {8'h00, Y_fp4};
            assign output_is_fp8 = 0;
            
        end else if (MULT_PRECISION == 0 && ADD_PRECISION == 1) begin : USE_FP4mul_FP8add
            // FP4 mult, FP8 add: outputs 16-bit (FP8)
            
            butterfly_generation_unit_4add_8mul mixed_bf (
                .A(A_mem[7:0]),   // FP4 input
                .B(B_mem[7:0]),   // FP4 input
                .W(W),            // FP4 twiddle
                .X(X),
                .Y(Y)
            );
            
            assign output_is_fp8 = 1;
        end
    endgenerate

endmodule
'''
    
    def _generate_core(self, config):
        n = config['fft_size']
        aw = config['addr_width']
        
        # Generate stage parameters
        stage_params = ""
        for stage in config['stages']:
            s = stage['stage_num']
            m = stage['mult_precision']
            a = stage['add_precision']
            o = stage['output_precision']
            stage_params += f"    localparam STAGE{s}_MULT_PREC = {m};\n"
            stage_params += f"    localparam STAGE{s}_ADD_PREC = {a};\n"
            stage_params += f"    localparam STAGE{s}_OUT_PREC = {o};\n"
        
        # Generate stage case statements
        stage_cases = ""
        for stage in config['stages']:
            s = stage['stage_num']
            if s == 0:
                read_prec = f"STAGE{s}_MULT_PREC"
            else:
                read_prec = f"STAGE{s-1}_OUT_PREC"
            
            stage_cases += f"""            3'd{s}: begin
                current_mult_prec = STAGE{s}_MULT_PREC;
                current_add_prec = STAGE{s}_ADD_PREC;
                memory_read_prec = {read_prec};
                memory_write_prec = STAGE{s}_OUT_PREC;
            end
"""
        
        return f'''//mixed-precision FFT core for {n}-point FFT
//16-bit butterfly I/O with 24-bit memory

module mixed_fft_{n}_core #(
    parameter MAX_N = {n},
    parameter ADDR_WIDTH = {aw}
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
{stage_params}
    
    //precision control
    reg current_mult_prec;
    reg current_add_prec;
    reg memory_read_prec;
    reg memory_write_prec;
    
    always @(*) begin
        case (curr_stage)
{stage_cases}            default: begin
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

    wire [15:0] X_bf_fp8;
    wire [15:0] Y_bf_fp8;
    reg [15:0] X_bf_fp8_reg;
    reg [15:0] Y_bf_fp8_reg;

    fp4_to_fp8_converter fp4_to_fp8_converter_real_inst1(
        .fp4_in(X_bf[7:4]),
        .fp8_out(X_bf_fp8[15:8])
    );

    fp4_to_fp8_converter fp4_to_fp8_converter_imag_inst1(
        .fp4_in(X_bf[3:0]),
        .fp8_out(X_bf_fp8[7:0])
    );

    fp4_to_fp8_converter fp4_to_fp8_converter_real_inst2(
        .fp4_in(Y_bf[7:4]),
        .fp8_out(Y_bf_fp8[15:8])
    );

    fp4_to_fp8_converter fp4_to_fp8_converter_imag_inst2(
        .fp4_in(Y_bf[3:0]),
        .fp8_out(Y_bf_fp8[7:0])
    );

    wire [15:0] X_bf_fp4;
    wire [15:0] Y_bf_fp4;
    reg [15:0] X_bf_fp4_reg;
    reg [15:0] Y_bf_fp4_reg;

    fp8_to_fp4_converter fp8_to_fp4_converter_real_inst1(
        .fp8_in(X_bf[15:8]),
        .fp4_out(X_bf_fp4[7:4])
    );

    fp8_to_fp4_converter fp8_to_fp4_converter_imag_inst1(
        .fp8_in(X_bf[7:0]),
        .fp4_out(X_bf_fp4[3:0])
    );

    fp8_to_fp4_converter fp8_to_fp4_converter_real_inst2(
        .fp8_in(Y_bf[15:8]),
        .fp4_out(Y_bf_fp4[7:4])
    );

    fp8_to_fp4_converter fp8_to_fp4_converter_imag_inst2(
        .fp8_in(Y_bf[7:0]),
        .fp4_out(Y_bf_fp4[3:0])
    );

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
                        int_wr_data <= {{X_reg, X_reg_fp4}};
                    end else begin
                        int_wr_data <= {{X_reg_fp8, X_reg[7:0]}};
                    end
                end
                
                WRITE_Y: begin
                    int_wr_en <= 1;
                    int_wr_addr <= idx_b;
                    if (output_was_fp8) begin
                        int_wr_data <= {{Y_reg, Y_reg_fp4}};
                    end else begin
                        int_wr_data <= {{Y_reg_fp8, Y_reg[7:0]}};
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
'''
    
    def _generate_top(self, config):
        n = config['fft_size']
        aw = config['addr_width']
        
        return f'''//mixed-precision FFT TOP module for {n}-point FFT

module mixed_fft_{n}_top #(
    parameter MAX_N = {n},
    parameter ADDR_WIDTH = {aw}
)(
    input wire clk,
    input wire rst,
    
    //input interface
    input wire data_in_valid,
    input wire [23:0] data_in,
    output reg fft_ready,
    
    //output interface
    output reg data_out_valid,
    output reg [23:0] data_out,
    
    //status
    output wire done,
    output wire error
);

    //internal signals
    reg [ADDR_WIDTH-1:0] wr_addr, rd_addr;
    reg wr_en;
    wire [23:0] rd_data;
    wire fft_done;
    
    //bit reversal
    wire [ADDR_WIDTH-1:0] wr_addr_reversed;
    bit_reverse #(
        .MAX_N(MAX_N),
        .WIDTH(ADDR_WIDTH)
    ) bit_rev (
        .in(wr_addr),
        .out(wr_addr_reversed)
    );
    
    //state machine
    localparam MEM_IDLE = 2'd0;
    localparam MEM_WRITE = 2'd1;
    localparam MEM_PROCESS = 2'd2;
    localparam MEM_READ = 2'd3;
    
    reg [1:0] mem_state, mem_next_state;
    reg [ADDR_WIDTH-1:0] input_count, output_count;
    reg fft_start, fft_start_issued;
    reg ext_reading;
    reg read_bank_sel;
    
    wire [2:0] num_stages = $clog2(MAX_N);
    wire core_bank_sel = (mem_state == MEM_READ) ? read_bank_sel :
                        (mem_state == MEM_WRITE || mem_state == MEM_IDLE) ? 1'b1 :
                        1'b0;
    
    //FFT core
    mixed_fft_{n}_core #(
        .MAX_N(MAX_N),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) fft_core (
        .clk(clk),
        .rst(rst),
        .start(fft_start),
        .N(MAX_N),
        .done(fft_done),
        .error(error),
        .ext_wr_en(wr_en),
        .ext_wr_addr(wr_addr_reversed),
        .ext_wr_data(data_in),
        .ext_bank_sel(core_bank_sel),
        .ext_rd_addr(rd_addr),
        .ext_reading(ext_reading),
        .rd_data_0(rd_data)
    );
    
    //state machine
    always @(*) begin
        mem_next_state = mem_state;
        case (mem_state)
            MEM_IDLE: if (data_in_valid) mem_next_state = MEM_WRITE;
            MEM_WRITE: if (input_count >= MAX_N) mem_next_state = MEM_PROCESS;
            MEM_PROCESS: if (fft_done) mem_next_state = MEM_READ;
            MEM_READ: if (output_count >= MAX_N) mem_next_state = MEM_IDLE;
        endcase
    end
    
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            mem_state <= MEM_IDLE;
            input_count <= 0;
            output_count <= 0;
            wr_en <= 0;
            wr_addr <= 0;
            rd_addr <= 0;
            fft_ready <= 1;
            data_out_valid <= 0;
            data_out <= 0;
            fft_start <= 0;
            fft_start_issued <= 0;
            read_bank_sel <= 0;
            ext_reading <= 0;
        end else begin
            mem_state <= mem_next_state;
            fft_start <= 0;
            
            case (mem_state)
                MEM_IDLE: begin
                    fft_ready <= 1;
                    input_count <= 0;
                    output_count <= 0;
                    data_out_valid <= 0;
                    fft_start_issued <= 0;
                    ext_reading <= 0;
                    
                    if (data_in_valid) begin
                        wr_en <= 1;
                        wr_addr <= 0;
                        input_count <= 1;
                        fft_ready <= 0;
                    end else begin
                        wr_en <= 0;
                    end
                end
                
                MEM_WRITE: begin
                    if (input_count < MAX_N && data_in_valid) begin
                        wr_en <= 1;
                        wr_addr <= input_count;
                        input_count <= input_count + 1;
                    end else if (input_count >= MAX_N) begin
                        wr_en <= 0;
                        if (!fft_start_issued) begin
                            fft_start <= 1;
                            fft_start_issued <= 1;
                        end
                    end else begin
                        wr_en <= 0;
                    end
                end
                
                MEM_PROCESS: begin
                    wr_en <= 0;
                    if (fft_done) begin
                        output_count <= 0;
                        read_bank_sel <= num_stages[0];
                        ext_reading <= 1;
                    end else begin
                        ext_reading <= 0;
                    end
                end
                
                MEM_READ: begin
                    ext_reading <= 1;
                    if (output_count == 0) begin
                        rd_addr <= 0;
                        data_out_valid <= 0;
                        output_count <= output_count + 1;
                    end else if (output_count <= MAX_N) begin
                        data_out <= rd_data;
                        data_out_valid <= 1;
                        rd_addr <= rd_addr + 1;
                        output_count <= output_count + 1;
                    end else begin
                        data_out_valid <= 0;
                        ext_reading <= 0;
                    end
                end
            endcase
        end
    end
    
    assign done = fft_done;

endmodule
'''

# Test
if __name__ == "__main__":
    gen = CorrectedMixedPrecisionFFTGenerator(fft_size=8)
    
    chromosome = [0, 0, 1, 0, 1, 1]
    
    output_file = gen.generate_complete_fft(chromosome)
    print(f"\n✓ Complete FFT with 16-bit butterfly I/O generated!")