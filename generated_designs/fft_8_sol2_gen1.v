// Auto-generated Mixed-Precision FFT
// FFT Size: 8
// Uses unified twiddle ROM with runtime precision selection
// Total Butterflies: 12

module mixed_fft_8 (
    input clk,
    input rst,
    input start,
    input [15:0] data_in_real [7:0],
    input [15:0] data_in_imag [7:0],
    output reg [15:0] data_out_real [7:0],
    output reg [15:0] data_out_imag [7:0],
    output reg done
);

    // Stage interconnects
    wire [15:0] stage0_real [7:0];
    wire [15:0] stage0_imag [7:0];
    wire [15:0] stage1_real [7:0];
    wire [15:0] stage1_imag [7:0];
    wire [15:0] stage2_real [7:0];
    wire [15:0] stage2_imag [7:0];
    wire [15:0] stage3_real [7:0];
    wire [15:0] stage3_imag [7:0];

    // Twiddle factor wires
    wire [15:0] twiddle [7:0];

    // Twiddle ROM instances (unified, runtime precision-selectable)
    // Note: Twiddle precision matches multiplier precision per butterfly

    // Input assignment
    assign stage0_real[0] = data_in_real[0];
    assign stage0_imag[0] = data_in_imag[0];
    assign stage0_real[1] = data_in_real[1];
    assign stage0_imag[1] = data_in_imag[1];
    assign stage0_real[2] = data_in_real[2];
    assign stage0_imag[2] = data_in_imag[2];
    assign stage0_real[3] = data_in_real[3];
    assign stage0_imag[3] = data_in_imag[3];
    assign stage0_real[4] = data_in_real[4];
    assign stage0_imag[4] = data_in_imag[4];
    assign stage0_real[5] = data_in_real[5];
    assign stage0_imag[5] = data_in_imag[5];
    assign stage0_real[6] = data_in_real[6];
    assign stage0_imag[6] = data_in_imag[6];
    assign stage0_real[7] = data_in_real[7];
    assign stage0_imag[7] = data_in_imag[7];

    // ===== Stage 0 =====
    // 4 butterflies in parallel

    // Butterfly 0: Mult=FP4, Add=FP4
    wire [15:0] twiddle_s0_bf0;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(0)  // Use multiplier precision for twiddle
    ) twiddle_rom_s0_bf0 (
        .k(0),
        .n(8),
        .twiddle_out(twiddle_s0_bf0)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(0),
        .ADD_PRECISION(0)
    ) bf_s0_g0_b0 (
        .A({stage0_real[0], stage0_imag[0]}),
        .B({stage0_real[1], stage0_imag[1]}),
        .W(twiddle_s0_bf0),
        .X({stage1_real[0], stage1_imag[0]}),
        .Y({stage1_real[1], stage1_imag[1]})
    );

    // Butterfly 1: Mult=FP4, Add=FP4
    wire [15:0] twiddle_s0_bf1;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(0)  // Use multiplier precision for twiddle
    ) twiddle_rom_s0_bf1 (
        .k(0),
        .n(8),
        .twiddle_out(twiddle_s0_bf1)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(0),
        .ADD_PRECISION(0)
    ) bf_s0_g1_b0 (
        .A({stage0_real[2], stage0_imag[2]}),
        .B({stage0_real[3], stage0_imag[3]}),
        .W(twiddle_s0_bf1),
        .X({stage1_real[2], stage1_imag[2]}),
        .Y({stage1_real[3], stage1_imag[3]})
    );

    // Butterfly 2: Mult=FP4, Add=FP4
    wire [15:0] twiddle_s0_bf2;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(0)  // Use multiplier precision for twiddle
    ) twiddle_rom_s0_bf2 (
        .k(0),
        .n(8),
        .twiddle_out(twiddle_s0_bf2)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(0),
        .ADD_PRECISION(0)
    ) bf_s0_g2_b0 (
        .A({stage0_real[4], stage0_imag[4]}),
        .B({stage0_real[5], stage0_imag[5]}),
        .W(twiddle_s0_bf2),
        .X({stage1_real[4], stage1_imag[4]}),
        .Y({stage1_real[5], stage1_imag[5]})
    );

    // Butterfly 3: Mult=FP4, Add=FP4
    wire [15:0] twiddle_s0_bf3;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(0)  // Use multiplier precision for twiddle
    ) twiddle_rom_s0_bf3 (
        .k(0),
        .n(8),
        .twiddle_out(twiddle_s0_bf3)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(0),
        .ADD_PRECISION(0)
    ) bf_s0_g3_b0 (
        .A({stage0_real[6], stage0_imag[6]}),
        .B({stage0_real[7], stage0_imag[7]}),
        .W(twiddle_s0_bf3),
        .X({stage1_real[6], stage1_imag[6]}),
        .Y({stage1_real[7], stage1_imag[7]})
    );

    // ===== Stage 1 =====
    // 4 butterflies in parallel

    // Butterfly 0: Mult=FP8, Add=FP8
    wire [15:0] twiddle_s1_bf0;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(1)  // Use multiplier precision for twiddle
    ) twiddle_rom_s1_bf0 (
        .k(0),
        .n(8),
        .twiddle_out(twiddle_s1_bf0)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(1),
        .ADD_PRECISION(1)
    ) bf_s1_g0_b0 (
        .A({stage1_real[0], stage1_imag[0]}),
        .B({stage1_real[2], stage1_imag[2]}),
        .W(twiddle_s1_bf0),
        .X({stage2_real[0], stage2_imag[0]}),
        .Y({stage2_real[2], stage2_imag[2]})
    );

    // Butterfly 1: Mult=FP8, Add=FP8
    wire [15:0] twiddle_s1_bf1;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(1)  // Use multiplier precision for twiddle
    ) twiddle_rom_s1_bf1 (
        .k(2),
        .n(8),
        .twiddle_out(twiddle_s1_bf1)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(1),
        .ADD_PRECISION(1)
    ) bf_s1_g0_b1 (
        .A({stage1_real[1], stage1_imag[1]}),
        .B({stage1_real[3], stage1_imag[3]}),
        .W(twiddle_s1_bf1),
        .X({stage2_real[1], stage2_imag[1]}),
        .Y({stage2_real[3], stage2_imag[3]})
    );

    // Butterfly 2: Mult=FP8, Add=FP8
    wire [15:0] twiddle_s1_bf2;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(1)  // Use multiplier precision for twiddle
    ) twiddle_rom_s1_bf2 (
        .k(0),
        .n(8),
        .twiddle_out(twiddle_s1_bf2)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(1),
        .ADD_PRECISION(1)
    ) bf_s1_g1_b0 (
        .A({stage1_real[4], stage1_imag[4]}),
        .B({stage1_real[6], stage1_imag[6]}),
        .W(twiddle_s1_bf2),
        .X({stage2_real[4], stage2_imag[4]}),
        .Y({stage2_real[6], stage2_imag[6]})
    );

    // Butterfly 3: Mult=FP8, Add=FP8
    wire [15:0] twiddle_s1_bf3;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(1)  // Use multiplier precision for twiddle
    ) twiddle_rom_s1_bf3 (
        .k(2),
        .n(8),
        .twiddle_out(twiddle_s1_bf3)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(1),
        .ADD_PRECISION(1)
    ) bf_s1_g1_b1 (
        .A({stage1_real[5], stage1_imag[5]}),
        .B({stage1_real[7], stage1_imag[7]}),
        .W(twiddle_s1_bf3),
        .X({stage2_real[5], stage2_imag[5]}),
        .Y({stage2_real[7], stage2_imag[7]})
    );

    // ===== Stage 2 =====
    // 4 butterflies in parallel

    // Butterfly 0: Mult=FP8, Add=FP8
    wire [15:0] twiddle_s2_bf0;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(1)  // Use multiplier precision for twiddle
    ) twiddle_rom_s2_bf0 (
        .k(0),
        .n(8),
        .twiddle_out(twiddle_s2_bf0)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(1),
        .ADD_PRECISION(1)
    ) bf_s2_g0_b0 (
        .A({stage2_real[0], stage2_imag[0]}),
        .B({stage2_real[4], stage2_imag[4]}),
        .W(twiddle_s2_bf0),
        .X({stage3_real[0], stage3_imag[0]}),
        .Y({stage3_real[4], stage3_imag[4]})
    );

    // Butterfly 1: Mult=FP8, Add=FP8
    wire [15:0] twiddle_s2_bf1;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(1)  // Use multiplier precision for twiddle
    ) twiddle_rom_s2_bf1 (
        .k(1),
        .n(8),
        .twiddle_out(twiddle_s2_bf1)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(1),
        .ADD_PRECISION(1)
    ) bf_s2_g0_b1 (
        .A({stage2_real[1], stage2_imag[1]}),
        .B({stage2_real[5], stage2_imag[5]}),
        .W(twiddle_s2_bf1),
        .X({stage3_real[1], stage3_imag[1]}),
        .Y({stage3_real[5], stage3_imag[5]})
    );

    // Butterfly 2: Mult=FP8, Add=FP8
    wire [15:0] twiddle_s2_bf2;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(1)  // Use multiplier precision for twiddle
    ) twiddle_rom_s2_bf2 (
        .k(2),
        .n(8),
        .twiddle_out(twiddle_s2_bf2)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(1),
        .ADD_PRECISION(1)
    ) bf_s2_g0_b2 (
        .A({stage2_real[2], stage2_imag[2]}),
        .B({stage2_real[6], stage2_imag[6]}),
        .W(twiddle_s2_bf2),
        .X({stage3_real[2], stage3_imag[2]}),
        .Y({stage3_real[6], stage3_imag[6]})
    );

    // Butterfly 3: Mult=FP8, Add=FP8
    wire [15:0] twiddle_s2_bf3;
    twiddle_factor_unified #(
        .MAX_N(1024),
        .PRECISION(1)  // Use multiplier precision for twiddle
    ) twiddle_rom_s2_bf3 (
        .k(3),
        .n(8),
        .twiddle_out(twiddle_s2_bf3)
    );

    butterfly_wrapper #(
        .MULT_PRECISION(1),
        .ADD_PRECISION(1)
    ) bf_s2_g0_b3 (
        .A({stage2_real[3], stage2_imag[3]}),
        .B({stage2_real[7], stage2_imag[7]}),
        .W(twiddle_s2_bf3),
        .X({stage3_real[3], stage3_imag[3]}),
        .Y({stage3_real[7], stage3_imag[7]})
    );

    // Output assignment
    always @(posedge clk) begin
        if (rst) begin
            done <= 0;
            data_out_real[0] <= 16'h0;
            data_out_imag[0] <= 16'h0;
            data_out_real[1] <= 16'h0;
            data_out_imag[1] <= 16'h0;
            data_out_real[2] <= 16'h0;
            data_out_imag[2] <= 16'h0;
            data_out_real[3] <= 16'h0;
            data_out_imag[3] <= 16'h0;
            data_out_real[4] <= 16'h0;
            data_out_imag[4] <= 16'h0;
            data_out_real[5] <= 16'h0;
            data_out_imag[5] <= 16'h0;
            data_out_real[6] <= 16'h0;
            data_out_imag[6] <= 16'h0;
            data_out_real[7] <= 16'h0;
            data_out_imag[7] <= 16'h0;
        end else if (start) begin
            data_out_real[0] <= stage3_real[0];
            data_out_imag[0] <= stage3_imag[0];
            data_out_real[1] <= stage3_real[1];
            data_out_imag[1] <= stage3_imag[1];
            data_out_real[2] <= stage3_real[2];
            data_out_imag[2] <= stage3_imag[2];
            data_out_real[3] <= stage3_real[3];
            data_out_imag[3] <= stage3_imag[3];
            data_out_real[4] <= stage3_real[4];
            data_out_imag[4] <= stage3_imag[4];
            data_out_real[5] <= stage3_real[5];
            data_out_imag[5] <= stage3_imag[5];
            data_out_real[6] <= stage3_real[6];
            data_out_imag[6] <= stage3_imag[6];
            data_out_real[7] <= stage3_real[7];
            data_out_imag[7] <= stage3_imag[7];
            done <= 1;
        end
    end

endmodule
