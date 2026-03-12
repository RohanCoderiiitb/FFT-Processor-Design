"""
Mixed-Precision FFT Generator
Produces per-solution *core* file  (mixed_fft_<N>_<design_name>_core.v)
and a *shared* top file            (mixed_fft_<N>_top.v, written once).

Butterfly wrapper outputs 16-bit; memory interface handles 24-bit ↔ 16-bit.
"""

import os
import math


class FFTTemplateGenerator:
    def __init__(self, fft_size):
        self.fft_size = fft_size
        self.num_stages = int(math.log2(fft_size))
        self.addr_width = 10         # log2(N) bits for addresses
        self.butterflies_per_stage = fft_size // 2
        self.total_butterflies = self.butterflies_per_stage * self.num_stages
        # Stage-level chromosome: 2 genes per stage
        self.chromosome_length = self.num_stages * 2
        self.MAX_N_HW = 1024

        print(f"FFTTemplateGenerator FFT-{fft_size}:")
        print(f"  Stages            : {self.num_stages}")
        print(f"  Butterflies/stage : {self.butterflies_per_stage}")
        print(f"  Chromosome length : {self.chromosome_length}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_chromosome_length(self):
        return self.chromosome_length

    def chromosome_to_config(self, chromosome):
        config = {
            'fft_size':   self.fft_size,
            'num_stages': self.num_stages,
            'addr_width': self.addr_width,
            'stages':     [],
            'MAX_N_HW': self.MAX_N_HW
        }
        prev_out_prec = 0

        for stage in range(self.num_stages):
            idx = stage * 2
            mult_prec  = int(chromosome[idx])     if idx     < len(chromosome) else 0
            add_prec   = int(chromosome[idx + 1]) if idx + 1 < len(chromosome) else 0
            output_prec = max(mult_prec, add_prec)

            config['stages'].append({
                'stage_num':        stage,
                'mult_precision':   mult_prec,
                'add_precision':    add_prec,
                'output_precision': output_prec,
                'read_precision':   prev_out_prec
            })
            prev_out_prec = output_prec

        return config

    def generate_verilog(self, chromosome, output_file):
        """
        Generate the per-solution core Verilog file.
        The core module is named  mixed_fft_<N>_<design_name>_core
        where <design_name> is derived from the output_file stem.

        Also generates the shared top file (once) in the same directory.

        Returns: (core_file_path, top_file_path)
        """
        config = self.chromosome_to_config(chromosome)

        out_dir = os.path.dirname(os.path.abspath(output_file))
        os.makedirs(out_dir, exist_ok=True)

        stem             = os.path.splitext(os.path.basename(output_file))[0]
        core_module_name = f"{stem}_core"
        top_module_name  = f"{stem}_top"

        core_code = self._generate_core(config, core_module_name=core_module_name)
        with open(output_file, 'w') as f:
            f.write(core_code)

        top_file = os.path.join(out_dir, f"{stem}_top.v")
        top_code = self._generate_top(config,
                                       core_module_name=core_module_name,
                                       top_module_name=top_module_name)
        with open(top_file, 'w') as f:
            f.write(top_code)

        return output_file, top_file

    def generate_complete_fft(self, chromosome, output_dir='./generated_designs'):
        """
        Convenience wrapper: writes <base>_core.v and <base>_top.v.
        Returns the path to the top file.
        """
        config = self.chromosome_to_config(chromosome)
        os.makedirs(output_dir, exist_ok=True)

        base_name        = f"mixed_fft_{self.fft_size}"
        core_module_name = f"{base_name}_core"
        top_module_name  = f"{base_name}_top"

        core = self._generate_core(config, core_module_name=core_module_name)
        top  = self._generate_top(config,  core_module_name=core_module_name,
                                            top_module_name=top_module_name)

        core_file = f"{output_dir}/{base_name}_core.v"
        top_file  = f"{output_dir}/{base_name}_top.v"

        with open(core_file, 'w') as f:
            f.write(core)
        with open(top_file, 'w') as f:
            f.write(top)

        print(f"✓ Generated: {base_name}_core.v")
        print(f"✓ Generated: {base_name}_top.v")

        return top_file

    def analyze_chromosome_statistics(self, chromosome):
        """Return dict of precision distribution stats (used by objectiveEvaluationFFT)."""
        config = self.chromosome_to_config(chromosome)
        fp8_mult = sum(s['mult_precision'] for s in config['stages'])
        fp8_add  = sum(s['add_precision']  for s in config['stages'])
        fp4_mult = self.num_stages - fp8_mult
        fp4_add  = self.num_stages - fp8_add

        stage_stats = [
            {
                'stage':    s['stage_num'],
                'fp8_mult': s['mult_precision'],
                'fp4_mult': 1 - s['mult_precision'],
                'fp8_add':  s['add_precision'],
                'fp4_add':  1 - s['add_precision'],
            }
            for s in config['stages']
        ]

        return {
            'fp8_mult':    fp8_mult,
            'fp4_mult':    fp4_mult,
            'fp8_add':     fp8_add,
            'fp4_add':     fp4_add,
            'stage_stats': stage_stats,
        }

    # ------------------------------------------------------------------
    # Private helpers – Verilog snippet generators
    # ------------------------------------------------------------------

    def _stage_localparam_block(self, config):
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
        ns = config['num_stages']
        stage_bits = max(1, math.ceil(math.log2(ns + 1)))
        cases = []
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
        lines = [
            "    // Single twiddle ROM — precision is a runtime input port.",
            "    wire [15:0] twiddle;",
            "",
            "    twiddle_factor_unified #(",
            f"        .MAX_N     ({1024}),",
            f"        .ADDR_WIDTH({aw})",
            "    ) twiddle_inst (",
            "        .k           (k),",
            "        .n           (N),",
            "        .PRECISION   (current_mult_prec),",
            "        .twiddle_out (twiddle)",
            "    );",
        ]
        return '\n'.join(lines)

    def _butterfly_generate_block(self, config, n, aw):
        lines = ["    // Per-stage butterfly instances (precision baked-in from chromosome)"]

        for s in config['stages']:
            sn = s['stage_num']
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

        lines += [
            "",
            "    // Select active butterfly output based on curr_stage",
            "    reg [15:0] X_bf, Y_bf;",
            "    reg        bf_output_is_fp8;",
            "    always @(*) begin",
            "        case (curr_stage)",
        ]
        for s in config['stages']:
            sn = s['stage_num']
            lines += [
                f"            {sn}: begin",
                f"                X_bf             = X_stage{sn};",
                f"                Y_bf             = Y_stage{sn};",
                f"                bf_output_is_fp8 = fp8_out_stage{sn};",
                f"            end",
            ]
        lines += [
            "            default: begin X_bf = 0; Y_bf = 0; bf_output_is_fp8 = 0; end",
            "        endcase",
            "    end",
        ]
        return '\n'.join(lines)

    def _memory_read_expansion(self):
        return """\
    // 16-bit memory read → 24-bit butterfly input bus
    wire [15:0] mem_rd_16;
    assign mem_rd_16 = int_rd_data_16;

    wire [23:0] mem_rd_24;
    assign mem_rd_24 = memory_read_prec
                       ? {mem_rd_16[15:0], 8'h00}   // FP8: [23:8]
                       : {16'h0000, mem_rd_16[7:0]}; // FP4: [7:0]

    reg [23:0] A_mem_24, B_mem_24;"""

    # ------------------------------------------------------------------
    # Core module generator
    # ------------------------------------------------------------------

    def _generate_core(self, config, core_module_name=None):
        n  = config['fft_size']
        aw = config['addr_width']
        ns = config['num_stages']
        MAXn = config['MAX_N_HW']
        stage_bits = 10

        if core_module_name is None:
            core_module_name = f"mixed_fft_{n}_core"

        lparams       = self._stage_localparam_block(config)
        prec_mux      = self._precision_mux_block(config)
        twiddle_gen   = self._twiddle_generate_block(config, n, aw)
        butterfly_gen = self._butterfly_generate_block(config, n, aw)
        mem_expand    = self._memory_read_expansion()

        return f"""\
// Mixed-Precision FFT Core – {n}-point
// Auto-generated by FFTTemplateGenerator
// Core module : {core_module_name}

`timescale 1ns/1ps

module {core_module_name} #(
    parameter MAX_N     = {MAXn},
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
    output wire [23:0]           rd_data_0
);

    // ----------------------------------------------------------------
    // State machine encoding
    // ----------------------------------------------------------------
    localparam IDLE     = 4'd0;
    localparam INIT     = 4'd1;
    localparam READ_A   = 4'd2;
    localparam WAIT_1   = 4'd3;
    localparam WAIT_A   = 4'd4;
    localparam READ_B   = 4'd5;
    localparam WAIT_2   = 4'd6;
    localparam WAIT_B   = 4'd7;
    localparam COMPUTE  = 4'd8;
    localparam WRITE_X  = 4'd9;
    localparam WRITE_Y  = 4'd10;
    localparam WAIT_AGU = 4'd11;
    localparam EVAL_AGU = 4'd12;
    localparam DONE     = 4'd13;

    reg [3:0] state, next_state;

    // ----------------------------------------------------------------
    // Per-stage precision localparams (baked in from chromosome)
    // ----------------------------------------------------------------
{lparams}

    // ----------------------------------------------------------------
    // Runtime precision control registers
    // ----------------------------------------------------------------
    reg current_mult_prec;
    reg current_add_prec;
    reg memory_read_prec;
    reg memory_write_prec;

    // ----------------------------------------------------------------
    // AGU
    // ----------------------------------------------------------------
    reg agu_next_step;
    wire [ADDR_WIDTH-1:0] idx_a, idx_b, k;
    wire agu_done_stage, agu_done_fft;
    wire [{stage_bits}-1:0] curr_stage;

    dit_fft_agu_variable #(
        .MAX_N     ({MAXn}),
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
    // Precision mux: drive *_prec regs from curr_stage
    // ----------------------------------------------------------------
{prec_mux}

    // ----------------------------------------------------------------
    // Memory signals
    // ----------------------------------------------------------------
    reg  [ADDR_WIDTH-1:0] int_rd_addr;
    wire [15:0]           int_rd_data_16;
    wire [23:0]           int_rd_data_24;
    reg  int_wr_en;
    reg  [ADDR_WIDTH-1:0] int_wr_addr;
    reg  [23:0]           int_wr_data;

    wire final_wr_en                    = ext_wr_en | int_wr_en;
    wire [ADDR_WIDTH-1:0] final_wr_addr = ext_wr_en   ? ext_wr_addr : int_wr_addr;
    wire [23:0]           final_wr_data = ext_wr_en   ? ext_wr_data : int_wr_data;
    wire [ADDR_WIDTH-1:0] final_rd_addr = ext_reading ? ext_rd_addr : int_rd_addr;

    reg fft_bank_sel;
    wire active_bank_sel = ext_reading          ? ext_bank_sel :
                           (state == IDLE)       ? ext_bank_sel :
                           fft_bank_sel;

    mixed_memory_unified #(
        .n         ({MAXn}),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) memory_inst (
        .clk         (clk),
        .rst         (rst),
        .bank_sel    (active_bank_sel),
        .rd_addr_0   (final_rd_addr),
        .rd_precision_0(memory_read_prec),
        .rd_data_0   (int_rd_data_16),
        .wr_en_1     (final_wr_en),
        .wr_addr_1   (final_wr_addr),
        .wr_data_1   (final_wr_data)
    );

    assign int_rd_data_24 = memory_read_prec
                            ? {{int_rd_data_16, 8'h00}}
                            : {{16'h0000, int_rd_data_16[7:0]}};
    assign rd_data_0 = int_rd_data_24;

    // ----------------------------------------------------------------
    // Expand 16-bit memory read to 24-bit butterfly input bus
    // ----------------------------------------------------------------
{mem_expand}

    // ----------------------------------------------------------------
    // Twiddle ROM
    // ----------------------------------------------------------------
{twiddle_gen}

    // ----------------------------------------------------------------
    // Per-stage butterfly instances
    // ----------------------------------------------------------------
{butterfly_gen}

    // ----------------------------------------------------------------
    // FP4 ↔ FP8 conversion wires for write-back packing
    // ----------------------------------------------------------------
    wire [7:0]  X_bf_fp4_conv, Y_bf_fp4_conv;
    wire [15:0] X_bf_fp8_expanded, Y_bf_fp8_expanded;

    fp8_to_fp4_converter conv_x_real (.fp8_in(X_bf[15:8]), .fp4_out(X_bf_fp4_conv[7:4]));
    fp8_to_fp4_converter conv_x_imag (.fp8_in(X_bf[7:0]),  .fp4_out(X_bf_fp4_conv[3:0]));
    fp8_to_fp4_converter conv_y_real (.fp8_in(Y_bf[15:8]), .fp4_out(Y_bf_fp4_conv[7:4]));
    fp8_to_fp4_converter conv_y_imag (.fp8_in(Y_bf[7:0]),  .fp4_out(Y_bf_fp4_conv[3:0]));

    fp4_to_fp8_converter conv_x_fp4r (.fp4_in(X_bf[7:4]), .fp8_out(X_bf_fp8_expanded[15:8]));
    fp4_to_fp8_converter conv_x_fp4i (.fp4_in(X_bf[3:0]), .fp8_out(X_bf_fp8_expanded[7:0]));
    fp4_to_fp8_converter conv_y_fp4r (.fp4_in(Y_bf[7:4]), .fp8_out(Y_bf_fp8_expanded[15:8]));
    fp4_to_fp8_converter conv_y_fp4i (.fp4_in(Y_bf[3:0]), .fp8_out(Y_bf_fp8_expanded[7:0]));

    // ----------------------------------------------------------------
    // Registered butterfly results
    // ----------------------------------------------------------------
    reg [15:0] X_reg, Y_reg;
    reg        output_was_fp8;

    // ----------------------------------------------------------------
    // Stage completion detect
    // ----------------------------------------------------------------
    reg prev_done_stage;
    wire stage_complete = agu_done_stage && !prev_done_stage;

    // ----------------------------------------------------------------
    // Main state machine – sequential
    // ----------------------------------------------------------------
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            state           <= IDLE;
            done            <= 0;
            error           <= 0;
            A_mem_24        <= 0;
            B_mem_24        <= 0;
            X_reg           <= 0;
            Y_reg           <= 0;
            output_was_fp8  <= 0;
            int_rd_addr     <= 0;
            int_wr_en       <= 0;
            int_wr_addr     <= 0;
            int_wr_data     <= 0;
            agu_next_step   <= 0;
            fft_bank_sel    <= 0;
            prev_done_stage <= 0;
        end else begin
            state           <= next_state;
            int_wr_en       <= 0;
            agu_next_step   <= 0;
            prev_done_stage <= agu_done_stage;

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

                INIT: begin end

                READ_A: begin
                    int_rd_addr <= idx_a;
                end

                WAIT_1: begin end

                WAIT_A: begin end

                READ_B: begin
                    A_mem_24    <= mem_rd_24;
                    int_rd_addr <= idx_b;
                end

                WAIT_2: begin end

                WAIT_B: begin end

                COMPUTE: begin
                    B_mem_24       <= mem_rd_24;
                    X_reg          <= X_bf;
                    Y_reg          <= Y_bf;
                    output_was_fp8 <= bf_output_is_fp8;
                end

                WRITE_X: begin
                    int_wr_en   <= 1;
                    int_wr_addr <= idx_a;
                    if (output_was_fp8)
                        int_wr_data <= {{X_reg, X_bf_fp4_conv}};
                    else
                        int_wr_data <= {{X_bf_fp8_expanded, X_reg[7:0]}};
                end

                WRITE_Y: begin
                    int_wr_en   <= 1;
                    int_wr_addr <= idx_b;
                    if (output_was_fp8)
                        int_wr_data <= {{Y_reg, Y_bf_fp4_conv}};
                    else
                        int_wr_data <= {{Y_bf_fp8_expanded, Y_reg[7:0]}};
                    agu_next_step <= 1;
                end
                
                WAIT_AGU: begin 
                    // Do nothing wait for AGU to push done_fft flag correctly 
                end 
                
                EVAL_AGU: begin 
                end 

                DONE: begin
                    done <= 1'b1;
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
            IDLE    : if (start && !error) next_state = INIT;
            INIT    : next_state = READ_A;
            READ_A  : next_state = WAIT_1;
            WAIT_1  : next_state = WAIT_A;
            WAIT_A  : next_state = READ_B;
            READ_B  : next_state = WAIT_2;
            WAIT_2  : next_state = WAIT_B;
            WAIT_B  : next_state = COMPUTE;
            COMPUTE : next_state = WRITE_X;
            WRITE_X : next_state = WRITE_Y;
            WRITE_Y : next_state = WAIT_AGU;
            WAIT_AGU: next_state = EVAL_AGU;
            EVAL_AGU: next_state = agu_done_fft ? DONE : READ_A;
            DONE    : next_state = IDLE;
            default : next_state = IDLE;
        endcase
    end

endmodule
"""

    # ------------------------------------------------------------------
    # Top module generator
    # ------------------------------------------------------------------

    def _generate_top(self, config, core_module_name=None, top_module_name=None):
        n  = config['fft_size']
        aw = config['addr_width']
        MAXn = config['MAX_N_HW']

        if core_module_name is None:
            core_module_name = f"mixed_fft_{n}_core"
        if top_module_name is None:
            top_module_name = f"mixed_fft_{n}_top"

        return f"""\
// Mixed-precision FFT TOP – {n}-point
// Instantiates: {core_module_name}
// Auto-generated by FFTTemplateGenerator

`timescale 1ns/1ps

module {top_module_name} #(
    parameter MAX_N      = {MAXn},
    parameter ADDR_WIDTH = {aw}
)(
    input  wire        clk,
    input  wire        rst,
    input wire [ADDR_WIDTH-1:0] N,
    // Input interface
    input  wire        data_in_valid,
    input  wire [23:0] data_in,
    output reg         fft_ready,

    // Output interface
    output reg         data_out_valid,
    output reg  [23:0] data_out,

    // Status
    output wire        done,
    output wire        error
);

    reg [ADDR_WIDTH-1:0] wr_addr, rd_addr;
    reg                  wr_en;
    wire [23:0]          rd_data;
    wire                 fft_done;

    // Bit-reversal on write address
    wire [ADDR_WIDTH-1:0] wr_addr_reversed;
    bit_reverse #(
        .MAX_N({MAXn}),
        .WIDTH(ADDR_WIDTH)
    ) bit_rev (
        .in (wr_addr),
        .N  (N),     // FIXED: Wired up missing runtime N port
        .out(wr_addr_reversed)
    );

    // State machine
    localparam MEM_IDLE    = 2'd0;
    localparam MEM_WRITE   = 2'd1;
    localparam MEM_PROCESS = 2'd2;
    localparam MEM_READ    = 2'd3;

    reg [1:0]            mem_state, mem_next_state;
    reg [ADDR_WIDTH-1:0] input_count, output_count;
    reg [ADDR_WIDTH-1:0] rd_addr_count; // tracks addresses issued to memory
    reg                  fft_start, fft_start_issued;
    reg                  ext_reading;
    reg                  read_bank_sel;

    localparam NUM_STAGES = {self.num_stages};

    wire core_bank_sel = (mem_state == MEM_READ)  ? read_bank_sel :
                         (mem_state == MEM_WRITE ||
                          mem_state == MEM_IDLE)  ? 1'b1 : 1'b0;

    // FFT core (precision baked-in per chromosome)
    {core_module_name} #(
        .MAX_N     (MAX_N),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) fft_core (
        .clk        (clk),
        .rst        (rst),
        .start      (fft_start),
        .N          (N),
        .done       (fft_done),
        .error      (error),
        .ext_wr_en  (wr_en),
        .ext_wr_addr(wr_addr_reversed),
        .ext_wr_data(data_in),
        .ext_bank_sel(core_bank_sel),
        .ext_rd_addr (rd_addr),
        .ext_reading (ext_reading),
        .rd_data_0   (rd_data)
    );

    // Next-state logic
    always @(*) begin
        mem_next_state = mem_state;
        case (mem_state)
            MEM_IDLE:    if (data_in_valid)                          mem_next_state = MEM_WRITE;
            MEM_WRITE:   if (input_count >= N)                       mem_next_state = MEM_PROCESS;
            MEM_PROCESS: if (fft_done)                               mem_next_state = MEM_READ;
            MEM_READ:    if (output_count >= N && rd_addr_count >= N) mem_next_state = MEM_IDLE;
        endcase
    end

    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            mem_state        <= MEM_IDLE;
            input_count      <= 0;
            output_count     <= 0;
            rd_addr_count    <= 0;
            wr_en            <= 0;
            wr_addr          <= 0;
            rd_addr          <= 0;
            fft_ready        <= 1;
            data_out_valid   <= 0;
            data_out         <= 0;
            fft_start        <= 0;
            fft_start_issued <= 0;
            read_bank_sel    <= 0;
            ext_reading      <= 0;
        end else begin
            mem_state <= mem_next_state;
            fft_start <= 0;

            case (mem_state)
                MEM_IDLE: begin
                    fft_ready        <= 1;
                    input_count      <= 0;
                    output_count     <= 0;
                    rd_addr_count    <= 0;
                    data_out_valid   <= 0;
                    fft_start_issued <= 0;
                    ext_reading      <= 0;
                    if (data_in_valid) begin
                        wr_en       <= 1;
                        wr_addr     <= 0;
                        input_count <= 1;
                        fft_ready   <= 0;
                    end else begin
                        wr_en <= 0;
                    end
                end

                MEM_WRITE: begin
                    if (input_count < N && data_in_valid) begin
                        wr_en       <= 1;
                        wr_addr     <= input_count;
                        input_count <= input_count + 1;
                    end else if (input_count >= N) begin
                        wr_en <= 0;
                        if (!fft_start_issued) begin
                            fft_start        <= 1;
                            fft_start_issued <= 1;
                        end
                    end else begin
                        wr_en <= 0;
                    end
                end

                MEM_PROCESS: begin
                    wr_en       <= 0;
                    ext_reading <= 0;  // core owns memory; external reads not active
                    if (fft_done) begin
                        output_count  <= 0;
                        rd_addr_count <= 0;
                        // After NUM_STAGES ping-pong flips, result is in bank NUM_STAGES[0]
                        read_bank_sel <= NUM_STAGES[0];
                    end
                end

                MEM_READ: begin
                    ext_reading <= 1;

                    // Phase 1: keep issuing next read address while more to fetch
                    if (rd_addr_count < N) begin
                        rd_addr       <= rd_addr_count;
                        rd_addr_count <= rd_addr_count + 1;
                    end

                    // Phase 2: FIXED. Wait 3 cycles for the data to be fully stable in rd_data
                    //   (Cycle 1: address updates, Cycle 2: memory fetches data, Cycle 3: sliced to port)
                    if (rd_addr_count >= 3 && output_count < N) begin
                        data_out       <= rd_data;
                        data_out_valid <= 1;
                        output_count   <= output_count + 1;
                    end else begin
                        data_out_valid <= 0;
                    end

                    // Stop driving ext_reading once all addresses issued
                    if (rd_addr_count >= N && output_count >= N)
                        ext_reading <= 0;
                end
            endcase
        end
    end

    assign done = fft_done;

endmodule
"""


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    gen = FFTTemplateGenerator(fft_size=8)
    chromosome = [0, 0, 1, 0, 1, 1]
    core_f, top_f = gen.generate_verilog(chromosome, "./generated_designs/fft_8_test_sol0.v")
    print(f"Core : {core_f}")
    print(f"Top  : {top_f}")