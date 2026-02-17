// Butterfly Wrapper with 16-bit I/O
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
