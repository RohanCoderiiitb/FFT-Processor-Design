"""
Mixed-Precision FFT Generator
Butterfly wrapper outputs 16-bit (matches actual butterfly modules)
Memory interface handles 24-bit ↔ 16-bit conversion
"""

import os
import math


class FFTTemplateGenerator:
    def __init__(self, fft_size):
        self.fft_size = fft_size
        self.num_stages = int(math.log2(fft_size))
        self.addr_width = self.num_stages          # log2(N) bits for addresses
        self.butterflies_per_stage = fft_size // 2
        self.total_butterflies = self.butterflies_per_stage * self.num_stages
        # Stage-level chromosome: 2 genes per stage
        self.chromosome_length = self.num_stages * 2

        print(f"FFTTemplateGenerator FFT-{fft_size}:")
        print(f"  Stages            : {self.num_stages}")
        print(f"  Butterflies/stage : {self.butterflies_per_stage}")
        print(f"  Chromosome length : {self.chromosome_length}")
    
    def get_chromosome_length(self):
        return self.chromosome_length
    
    def chromosome_to_config(self, chromosome):
        config = {
            'fft_size': self.fft_size,
            'num_stages': self.num_stages,
            'addr_width': self.addr_width,
            'stages': []
        }
        prev_out_prec = 0
        
        for stage in range(self.num_stages):
            idx = stage * 2
            mult_prec = chromosome[idx] if idx < len(chromosome) else 0
            add_prec = chromosome[idx + 1] if idx + 1 < len(chromosome) else 0
            output_prec = max(mult_prec, add_prec)
            
            config['stages'].append({
                'stage_num': stage,
                'mult_precision': mult_prec,
                'add_precision': add_prec,
                'output_precision': output_prec,
                'read_precision': prev_out_prec
            })
            prev_out_prec = output_prec
        
        return config
    
    def generate_verilog(self, chromosome, output_file):
        """Generate a single top-level Verilog file for the given chromosome."""
        config = self.chromosome_to_config(chromosome)
        os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)

        core_code = self._generate_core(config)
        with open(output_file, 'w') as f:
            f.write(core_code)

        return output_file
    
    def generate_complete_fft(self, chromosome, output_dir='./generated_designs'):
        config = self.chromosome_to_config(chromosome)
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate files
        core = self._generate_core(config)
        top = self._generate_top(config)
        
        base_name = f"mixed_fft_{self.fft_size}"
        
        with open(f"{output_dir}/{base_name}_core.v", 'w') as f:
            f.write(core)
        with open(f"{output_dir}/{base_name}_top.v", 'w') as f:
            f.write(top)
        
        print(f"✓ Generated: {base_name}_core.v")
        print(f"✓ Generated: {base_name}_top.v") 
        
        return f"{output_dir}/{base_name}_top.v"

    def analyze_chromosome_statistics(self, chromosome):
        """Return dict of precision distribution stats (used by objectiveEvaluationFFT)."""
        config = self._chromosome_to_config(chromosome)
        fp8_mult = sum(s['mult_precision'] for s in config['stages'])
        fp8_add  = sum(s['add_precision']  for s in config['stages'])
        fp4_mult = self.num_stages - fp8_mult
        fp4_add  = self.num_stages - fp8_add

        stage_stats = [
            {
                'stage'   : s['stage_num'],
                'fp8_mult': s['mult_precision'],
                'fp4_mult': 1 - s['mult_precision'],
                'fp8_add' : s['add_precision'],
                'fp4_add' : 1 - s['add_precision'],
            }
            for s in config['stages']
        ]

        return {
            'fp8_mult'   : fp8_mult,
            'fp4_mult'   : fp4_mult,
            'fp8_add'    : fp8_add,
            'fp4_add'    : fp4_add,
            'stage_stats': stage_stats,
        }
    
    def _stage_localparam_block(self, config):
        """Emit one set of localparams per stage."""
        lines = []
        for s in config['stages']:
            sn = s['stage_num']
            lines += [
                f"    localparam STAGE{sn}_MULT_PREC = {s['mult_precision']};",
                f"    localparam STAGE{sn}_ADD_PREC  = {s['add_precision']};",
                f"    localparam STAGE{sn}_OUT_PREC  = {s['output_precision']};",
                f"    localparam STAGE{sn}_RD_PREC   = {s['read_precision']};",
            ]
        return '\n'.join(lines)

    def _precision_mux_block(self, config):
        """
        Always-comb block that drives current_mult_prec, current_add_prec,
        memory_read_prec, and memory_write_prec from curr_stage.
        """
        cases = []
        ns = config['num_stages']
        stage_bits = max(1, math.ceil(math.log2(ns + 1)))  # enough bits for stages
        for s in config['stages']:
            sn = s['stage_num']
            cases.append(
                f"            {stage_bits}'d{sn}: begin\n"
                f"                current_mult_prec  = STAGE{sn}_MULT_PREC;\n"
                f"                current_add_prec   = STAGE{sn}_ADD_PREC;\n"
                f"                memory_read_prec   = STAGE{sn}_RD_PREC;\n"
                f"                memory_write_prec  = STAGE{sn}_OUT_PREC;\n"
                f"            end"
            )

        return (
            "    always @(*) begin\n"
            "        case (curr_stage)\n"
            + '\n'.join(cases) + "\n"
            "            default: begin\n"
            "                current_mult_prec = 0;\n"
            "                current_add_prec  = 0;\n"
            "                memory_read_prec  = 0;\n"
            "                memory_write_prec = 0;\n"
            "            end\n"
            "        endcase\n"
            "    end"
        )

    def _twiddle_generate_block(self, config, n, aw):
        """
        Single twiddle_factor_unified instance.  precision is now a runtime
        input port (not a parameter), so one instance covers all stages and
        both precisions.  current_mult_prec drives it directly.
        """
        lines = [
            "    // Single twiddle ROM instance — precision is a runtime input port.",
            "    // The ROM stores all twiddle factors in both precisions in each",
            "    // 24-bit entry; the precision input just selects the output slice.",
            "    wire [15:0] twiddle;",
            "",
            "    twiddle_factor_unified #(",
            f"        .MAX_N     ({n}),",
            f"        .ADDR_WIDTH({aw})",
            "    ) twiddle_inst (",
            "        .k           (k),",
            "        .n           (N),",
            "        .PRECISION   (current_mult_prec),  // driven by stage mux",
            "        .twiddle_out (twiddle)",
            "    );",
        ]
        return '\n'.join(lines)

    def _butterfly_generate_block(self, config, n, aw):
        """
        One butterfly_wrapper_16bit instance per stage, each with correct
        MULT_PRECISION and ADD_PRECISION from the chromosome.
        Input slicing from the 24-bit memory word also follows read_precision.

        butterfly ports (from butterfly.v):
          fp8_butterfly_generation_unit: A[15:0], B[15:0], W[15:0] → X[15:0], Y[15:0]
          fp4_butterfly_generation_unit: A[7:0],  B[7:0],  W[15:0] → X[7:0],  Y[7:0]
          butterfly_generation_unit_8add_4mul: A[15:0], B[7:0],  W[15:0] → X[15:0], Y[15:0]
          butterfly_generation_unit_4add_8mul: A[7:0],  B[15:0], W[15:0] → X[7:0],  Y[7:0]

        The wrapper (butterfly_wrapper_16bit, regenerated below) normalises to
        16-bit I/O so the core only ever handles [15:0] buses.
        """
        lines = ["    // Per-stage butterfly instances (precision set from chromosome)"]

        for s in config['stages']:
            sn = s['stage_num']
            mp = s['mult_precision']
            ap = s['add_precision']
            lines += [
                f"    wire [15:0] X_stage{sn}, Y_stage{sn};",
                f"    wire        fp8_out_stage{sn};",
            ]

        lines.append("")
        lines.append("    generate")
        for s in config['stages']:
            sn = s['stage_num']
            mp = s['mult_precision']
            ap = s['add_precision']
            lines += [
                f"        // Stage {sn}: mult={mp} add={ap}",
                f"        butterfly_wrapper #(",
                f"            .MULT_PRECISION({mp}),",
                f"            .ADD_PRECISION ({ap})",
                f"        ) bf_stage{sn}_inst (",
                f"            .A        (A_mem_24),",
                f"            .B        (B_mem_24),",
                f"            .W            (twiddle),",
                f"            .X            (X_stage{sn}),",
                f"            .Y            (Y_stage{sn}),",
                f"            .output_is_fp8(fp8_out_stage{sn})",
                f"        );",
                "",
            ]
        lines.append("    endgenerate")

        # Runtime mux: pick active stage outputs
        lines.append("")
        lines.append("    // Select active butterfly output based on curr_stage")
        lines.append("    reg [15:0] X_bf, Y_bf;")
        lines.append("    reg        bf_output_is_fp8;")
        lines.append("    always @(*) begin")
        lines.append("        case (curr_stage)")
        for s in config['stages']:
            sn = s['stage_num']
            lines += [
                f"            {sn}: begin",
                f"                X_bf            = X_stage{sn};",
                f"                Y_bf            = Y_stage{sn};",
                f"                bf_output_is_fp8 = fp8_out_stage{sn};",
                f"            end",
            ]
        lines.append("            default: begin X_bf = 0; Y_bf = 0; bf_output_is_fp8 = 0; end")
        lines.append("        endcase")
        lines.append("    end")

        return '\n'.join(lines)

    def _memory_read_expansion(self):
        """
        memory returns 16-bit (already precision-sliced inside mixed_memory_unified).
        Expand to 24-bit for the butterfly A_mem/B_mem bus:
          FP8 (memory_read_prec=1): data is [15:0] = [FP8_real | FP8_imag]
                → 24-bit = {data[15:0], 8'h00}  (upper 16 are real+imag FP8, lower 8 unused)
          FP4 (memory_read_prec=0): data is [7:0] = [FP4_real | FP4_imag] in bits [7:0]
                → 24-bit = {16'h0000, data[7:0]}
        The butterfly_wrapper_16bit already extracts the right slice from A_mem[23:0].
        """
        return """\
    // 16-bit memory read → 24-bit butterfly bus
    // mixed_memory_unified already applies rd_precision_0, returning 16 bits.
    // We re-pack into the 24-bit canonical format so butterfly_wrapper_16bit
    // can slice consistently: [23:8]=FP8 complex, [7:0]=FP4 complex.
    wire [15:0] mem_rd_16;   // raw 16-bit output of the memory
    assign mem_rd_16 = int_rd_data_16;  // driven by memory instance below

    // Expand to 24-bit for butterfly input
    // FP8 path: memory returns {fp8_real[7:0], fp8_imag[7:0]} in [15:0]
    //           → place in [23:8], pad [7:0] with 0
    // FP4 path: memory returns {8'h00, fp4_real[3:0], fp4_imag[3:0]} in [15:0]
    //           → only [7:0] matters; place in [7:0], pad [23:8] with 0
    wire [23:0] mem_rd_24;
    assign mem_rd_24 = memory_read_prec
                       ? {mem_rd_16[15:0], 8'h00}   // FP8: pack into [23:8]
                       : {16'h0000, mem_rd_16[7:0]}; // FP4: pack into [7:0]

    // A_mem_24 / B_mem_24 are what butterfly instances see
    reg [23:0] A_mem_24, B_mem_24;"""
    
    def _generate_core(self, config):
        n  = config['fft_size']
        aw = config['addr_width']
        ns = config['num_stages']
        stage_bits = max(1, math.ceil(math.log2(ns + 1)))

        lparams       = self._stage_localparam_block(config)
        prec_mux      = self._precision_mux_block(config)
        twiddle_gen   = self._twiddle_generate_block(config, n, aw)
        butterfly_gen = self._butterfly_generate_block(config, n, aw)
        mem_expand    = self._memory_read_expansion()

        return f"""\
// Mixed-Precision FFT Core – {n}-point
// Auto-generated by FFTTemplateGenerator
// Memory : 24-bit unified [23:16]=FP8_real [15:8]=FP8_imag [7:4]=FP4_real [3:0]=FP4_imag
// I/O bus: 16-bit per data point (FP8) or 8-bit (FP4) inside 16-bit zero-padded

`timescale 1ns/1ps

module mixed_fft_{n}_core #(
    parameter MAX_N     = {n},
    parameter ADDR_WIDTH = {aw}
)(
    input  wire clk,
    input  wire rst,
    input  wire start,
    input  wire [ADDR_WIDTH-1:0] N,
    output reg  done,
    output reg  error,

    // External write interface (load input samples)
    input  wire                  ext_wr_en,
    input  wire [ADDR_WIDTH-1:0] ext_wr_addr,
    input  wire [23:0]           ext_wr_data,
    input  wire                  ext_bank_sel,

    // External read interface (unload FFT results)
    input  wire [ADDR_WIDTH-1:0] ext_rd_addr,
    input  wire                  ext_reading,
    output wire [23:0]           rd_data_0       // full 24-bit for host
);

    // ----------------------------------------------------------------
    // State machine encoding
    // ----------------------------------------------------------------
    localparam IDLE    = 4'd0;
    localparam INIT    = 4'd1;
    localparam READ_A  = 4'd2;
    localparam WAIT_1  = 4'd3;
    localparam WAIT_A  = 4'd4;
    localparam READ_B  = 4'd5;
    localparam WAIT_2  = 4'd6;
    localparam WAIT_B  = 4'd7;
    localparam COMPUTE = 4'd8;
    localparam WRITE_X = 4'd9;
    localparam WRITE_Y = 4'd10;
    localparam DONE    = 4'd11;

    reg [3:0] state, next_state;

    // ----------------------------------------------------------------
    // Per-stage precision localparams (from chromosome)
    // ----------------------------------------------------------------
{lparams}

    // ----------------------------------------------------------------
    // Runtime precision control registers (set by combinational mux)
    // ----------------------------------------------------------------
    reg current_mult_prec;  // 0=FP4 1=FP8 – drives butterfly select
    reg current_add_prec;   // 0=FP4 1=FP8 – drives butterfly select
    reg memory_read_prec;   // precision to read FROM memory this stage
    reg memory_write_prec;  // precision that butterfly output is in

    // ----------------------------------------------------------------
    // AGU
    // ----------------------------------------------------------------
    reg agu_next_step;
    wire [ADDR_WIDTH-1:0] idx_a, idx_b, k;
    wire agu_done_stage, agu_done_fft;
    wire [{stage_bits}-1:0] curr_stage;

    dit_fft_agu_variable #(
        .MAX_N     (MAX_N),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) agu_inst (
        .clk          (clk),
        .reset        (rst),
        .N            (N),
        .next_step    (agu_next_step),
        .idx_a        (idx_a),
        .idx_b        (idx_b),
        .k            (k),
        .done_stage   (agu_done_stage),
        .done_fft     (agu_done_fft),
        .curr_stage   (curr_stage),
        .twiddle_output()
    );

    // ----------------------------------------------------------------
    // Precision mux: set *_prec regs from curr_stage
    // ----------------------------------------------------------------
{prec_mux}

    // ----------------------------------------------------------------
    // Memory signals
    // ----------------------------------------------------------------
    reg  [ADDR_WIDTH-1:0] int_rd_addr;
    wire [15:0]           int_rd_data_16;  // 16-bit from memory (precision-sliced)
    wire [23:0]           int_rd_data_24;  // 24-bit full read (for external host)
    reg  int_wr_en;
    reg  [ADDR_WIDTH-1:0] int_wr_addr;
    reg  [23:0]           int_wr_data;

    // Arbitrate between external and internal access
    wire final_wr_en                  = ext_wr_en | int_wr_en;
    wire [ADDR_WIDTH-1:0] final_wr_addr = ext_wr_en ? ext_wr_addr : int_wr_addr;
    wire [23:0]           final_wr_data = ext_wr_en ? ext_wr_data : int_wr_data;
    wire [ADDR_WIDTH-1:0] final_rd_addr = ext_reading ? ext_rd_addr : int_rd_addr;

    // Ping-pong bank control
    reg fft_bank_sel;
    wire active_bank_sel = ext_reading                               ? ext_bank_sel :
                           (state == IDLE)                           ? ext_bank_sel :
                           fft_bank_sel;

    // Unified memory (stores 24-bit; returns 16-bit slice via rd_precision_0)
    mixed_memory_unified #(
        .n         (MAX_N),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) memory_inst (
        .clk         (clk),
        .rst         (rst),
        .bank_sel    (active_bank_sel),
        .rd_addr_0   (final_rd_addr),
        .rd_precision_0(memory_read_prec),  // ← set by precision mux
        .rd_data_0   (int_rd_data_16),      // 16-bit sliced output
        .wr_en_1     (final_wr_en),
        .wr_addr_1   (final_wr_addr),
        .wr_data_1   (final_wr_data)        // 24-bit write (canonical format)
    );

    // Full 24-bit read for external host (re-read without precision slicing)
    // We expose the same 16-bit data zero-extended as 24-bit for the top module.
    assign int_rd_data_24 = memory_read_prec
                            ? {{int_rd_data_16, 8'h00}}
                            : {{16'h0000, int_rd_data_16[7:0]}};
    assign rd_data_0 = int_rd_data_24;

    // ----------------------------------------------------------------
    // Expand 16-bit memory read to 24-bit butterfly input bus
    // ----------------------------------------------------------------
{mem_expand}

    // ----------------------------------------------------------------
    // Per-stage twiddle ROM instances
    // ----------------------------------------------------------------
{twiddle_gen}

    // ----------------------------------------------------------------
    // Per-stage butterfly instances
    // ----------------------------------------------------------------
{butterfly_gen}

    // ----------------------------------------------------------------
    // FP4 ↔ FP8 conversion wires for write-back packing
    // ----------------------------------------------------------------
    // Convert the 16-bit butterfly output both ways so we can write
    // the canonical 24-bit word regardless of output precision.
    wire [7:0]  X_bf_fp4_real, X_bf_fp4_imag;
    wire [7:0]  Y_bf_fp4_real, Y_bf_fp4_imag;
    wire [15:0] X_bf_fp8_expanded, Y_bf_fp8_expanded;

    // FP8→FP4 conversion (used when output is FP8, to fill FP4 field)
    fp8_to_fp4_converter conv_x_fp8_to_fp4_real (.fp8_in(X_bf[15:8]), .fp4_out(X_bf_fp4_real[7:4]));
    fp8_to_fp4_converter conv_x_fp8_to_fp4_imag (.fp8_in(X_bf[7:0]),  .fp4_out(X_bf_fp4_real[3:0]));
    fp8_to_fp4_converter conv_y_fp8_to_fp4_real (.fp8_in(Y_bf[15:8]), .fp4_out(Y_bf_fp4_real[7:4]));
    fp8_to_fp4_converter conv_y_fp8_to_fp4_imag (.fp8_in(Y_bf[7:0]),  .fp4_out(Y_bf_fp4_real[3:0]));

    // FP4→FP8 conversion (used when output is FP4, to fill FP8 field)
    fp4_to_fp8_converter conv_x_fp4_to_fp8_real (.fp4_in(X_bf[7:4]), .fp8_out(X_bf_fp8_expanded[15:8]));
    fp4_to_fp8_converter conv_x_fp4_to_fp8_imag (.fp4_in(X_bf[3:0]), .fp8_out(X_bf_fp8_expanded[7:0]));
    fp4_to_fp8_converter conv_y_fp4_to_fp8_real (.fp4_in(Y_bf[7:4]), .fp8_out(Y_bf_fp8_expanded[15:8]));
    fp4_to_fp8_converter conv_y_fp4_to_fp8_imag (.fp4_in(Y_bf[3:0]), .fp8_out(Y_bf_fp8_expanded[7:0]));

    // ----------------------------------------------------------------
    // Registered butterfly results and output precision flag
    // ----------------------------------------------------------------
    reg [15:0] X_reg, Y_reg;
    reg        output_was_fp8;

    // ----------------------------------------------------------------
    // Stage completion (rising-edge detect on agu_done_stage)
    // ----------------------------------------------------------------
    reg prev_done_stage;
    wire stage_complete = agu_done_stage && !prev_done_stage;

    // ----------------------------------------------------------------
    // Main state machine – sequential
    // ----------------------------------------------------------------
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state          <= IDLE;
            done           <= 0;
            error          <= 0;
            A_mem_24       <= 0;
            B_mem_24       <= 0;
            X_reg          <= 0;
            Y_reg          <= 0;
            output_was_fp8 <= 0;
            int_rd_addr    <= 0;
            int_wr_en      <= 0;
            int_wr_addr    <= 0;
            int_wr_data    <= 0;
            agu_next_step  <= 0;
            fft_bank_sel   <= 0;
            prev_done_stage <= 0;
        end else begin
            state           <= next_state;
            int_wr_en       <= 0;
            agu_next_step   <= 0;
            prev_done_stage <= agu_done_stage;

            // Flip ping-pong bank on stage completion
            if (stage_complete && state != IDLE && state != DONE)
                fft_bank_sel <= ~fft_bank_sel;

            case (state)
                IDLE: begin
                    done  <= 0;
                    error <= 0;
                    fft_bank_sel <= 0;
                    if (start && (N > MAX_N || (N & (N - 1)) != 0))
                        error <= 1;
                end

                INIT: begin
                    // No operation; AGU will start from reset state
                end

                READ_A: begin
                    int_rd_addr <= idx_a;
                end

                WAIT_1: begin 
                end

                WAIT_A: begin
                    // Memory has 1-cycle read latency; data available next cycle
                end

                READ_B: begin
                    // Latch A from memory read port, start reading B
                    // Reconstruct 24-bit from the 16-bit memory output
                    A_mem_24    <= mem_rd_24;
                    int_rd_addr <= idx_b;
                end

                WAIT_2: begin 
                end

                WAIT_B: begin
                    // Waiting for B read to complete
                end

                COMPUTE: begin
                    // Latch B; butterfly combinationally computes X_bf, Y_bf
                    B_mem_24        <= mem_rd_24;
                    X_reg           <= X_bf;
                    Y_reg           <= Y_bf;
                    output_was_fp8  <= bf_output_is_fp8;
                end

                WRITE_X: begin
                    int_wr_en   <= 1;
                    int_wr_addr <= idx_a;
                    // Pack 24-bit canonical word from butterfly output
                    if (output_was_fp8) begin
                        // FP8 result: fill [23:8] with FP8 data, [7:0] with FP4 downcast
                        int_wr_data <= {{X_reg,          X_bf_fp4_real[7:4], X_bf_fp4_real[3:0]}};
                    end else begin
                        // FP4 result: fill [7:0] with FP4 data, [23:8] with FP8 upcast
                        int_wr_data <= {{X_bf_fp8_expanded, X_reg[7:0]}};
                    end
                end

                WRITE_Y: begin
                    int_wr_en   <= 1;
                    int_wr_addr <= idx_b;
                    if (output_was_fp8) begin
                        int_wr_data <= {{Y_reg,          Y_bf_fp4_real[7:4], Y_bf_fp4_real[3:0]}};
                    end else begin
                        int_wr_data <= {{Y_bf_fp8_expanded, Y_reg[7:0]}};
                    end
                    agu_next_step <= 1;
                end

                DONE: begin
                    done <= 1;
                end
            endcase
        end
    end

    // ----------------------------------------------------------------
    // Next-state logic
    // ----------------------------------------------------------------
    always @(*) begin
        next_state = state;
        case (state)
            IDLE   : if (start && !error) next_state = INIT;
            INIT   : next_state = READ_A;
            READ_A : next_state = WAIT_1;
            WAIT_1 : next_state = WAIT_A; 
            WAIT_A : next_state = READ_B;
            READ_B : next_state = WAIT_2;
            WAIT_2 : next_state = WAIT_B;
            WAIT_B : next_state = COMPUTE;
            COMPUTE: next_state = WRITE_X;
            WRITE_X: next_state = WRITE_Y;
            WRITE_Y: next_state = agu_done_fft ? DONE : READ_A;
            DONE   : next_state = IDLE;
            default: next_state = IDLE;
        endcase
    end

endmodule
"""
    
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
    gen = FFTTemplateGenerator(fft_size=8)
    
    chromosome = [0, 0, 1, 0, 1, 1]
    
    output_file = gen.generate_complete_fft(chromosome)
    print(f"\n✓ Complete FFT with 16-bit butterfly I/O generated!")
