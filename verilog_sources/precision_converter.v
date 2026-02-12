// Mixed-Precision Butterfly Module with Independent Multiplier and Adder Precision
// Supports all 4 combinations:
// - FP4 mult + FP4 add
// - FP4 mult + FP8 add
// - FP8 mult + FP4 add  
// - FP8 mult + FP8 add

// Helper Module: FP4 to FP8 Converter
module fp4_to_fp8_converter(
    input [3:0] fp4_in,
    output [7:0] fp8_out
);
    // FP4 format: [sign:1][exp:2][mant:1]
    // FP8 format: [sign:1][exp:4][mant:3]
    
    wire sign = fp4_in[3];
    wire [1:0] exp_fp4 = fp4_in[2:1];
    wire mant_fp4 = fp4_in[0];
    
    reg [3:0] exp_fp8;
    reg [2:0] mant_fp8;
    
    always @(*) begin
        if (exp_fp4 == 2'b00) begin
            // Subnormal FP4 or zero
            if (mant_fp4 == 1'b0) begin
                // Zero
                exp_fp8 = 4'b0000;
                mant_fp8 = 3'b000;
            end else begin
                // Subnormal: 0.1 × 2^(-1) in FP4
                // In FP8: Need to represent as subnormal
                exp_fp8 = 4'b0000;
                mant_fp8 = 3'b100; // Shift mantissa
            end
        end else begin
            // Normal FP4: 1.mant × 2^(exp-1)
            // FP4 exponent bias = 1, range: 2^(-1) to 2^2
            // FP8 exponent bias = 7, range: 2^(-6) to 2^8
            // Convert: exp_fp8 = exp_fp4 - 1 + 7 = exp_fp4 + 6
            exp_fp8 = {2'b00, exp_fp4} + 4'd6;
            // Extend mantissa: FP4 has 1 bit, FP8 has 3 bits
            // Shift left to fill higher bits
            mant_fp8 = {mant_fp4, 2'b00};
        end
    end
    
    assign fp8_out = {sign, exp_fp8, mant_fp8};
endmodule

// Helper Module: FP8 to FP4 Converter (with rounding)
module fp8_to_fp4_converter(
    input [7:0] fp8_in,
    output [3:0] fp4_out
);
    // FP8 format: [sign:1][exp:4][mant:3]
    // FP4 format: [sign:1][exp:2][mant:1]
    
    wire sign = fp8_in[7];
    wire [3:0] exp_fp8 = fp8_in[6:3];
    wire [2:0] mant_fp8 = fp8_in[2:0];
    
    reg [1:0] exp_fp4;
    reg mant_fp4;
    
    always @(*) begin
        if (exp_fp8 == 4'b0000) begin
            // Zero or subnormal FP8
            exp_fp4 = 2'b00;
            mant_fp4 = 1'b0;
        end else if (exp_fp8 < 4'd6) begin
            // Too small for FP4 range, underflow to zero
            exp_fp4 = 2'b00;
            mant_fp4 = 1'b0;
        end else if (exp_fp8 > 4'd9) begin
            // Too large for FP4 range, overflow to max
            exp_fp4 = 2'b11;
            mant_fp4 = 1'b1;
        end else begin
            // Normal range: exp_fp4 = exp_fp8 - 6
            exp_fp4 = exp_fp8[1:0] - 2'd2; // Subtract 6, but we already checked range
            // Round mantissa from 3 bits to 1 bit
            // Take MSB and round based on lower bits
            mant_fp4 = mant_fp8[2] | (mant_fp8[1] & mant_fp8[0]); // Round to nearest
        end
    end
    
    assign fp4_out = {sign, exp_fp4, mant_fp4};
endmodule

// Helper Module: Complex FP4 to FP8 Converter
module complex_fp4_to_fp8(
    input [7:0] complex_fp4,   // {real[3:0], imag[3:0]}
    output [15:0] complex_fp8  // {real[7:0], imag[7:0]}
);
    fp4_to_fp8_converter conv_real(
        .fp4_in(complex_fp4[7:4]),
        .fp8_out(complex_fp8[15:8])
    );
    
    fp4_to_fp8_converter conv_imag(
        .fp4_in(complex_fp4[3:0]),
        .fp8_out(complex_fp8[7:0])
    );
endmodule

// Helper Module: Complex FP8 to FP4 Converter
module complex_fp8_to_fp4(
    input [15:0] complex_fp8,  // {real[7:0], imag[7:0]}
    output [7:0] complex_fp4   // {real[3:0], imag[3:0]}
);
    fp8_to_fp4_converter conv_real(
        .fp8_in(complex_fp8[15:8]),
        .fp4_out(complex_fp4[7:4])
    );
    
    fp8_to_fp4_converter conv_imag(
        .fp8_in(complex_fp8[7:0]),
        .fp4_out(complex_fp4[3:0])
    );
endmodule