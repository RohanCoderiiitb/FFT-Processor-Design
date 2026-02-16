// Wrapper modules to choose the precision

module butterfly_wrapper #(
    parameter MULT_PRECISION = 0, // 0 for FP4, 1 for FP8
    parameter ADD_PRECISION = 0   // 0 for FP4, 1 for FP8
)(
    input [23:0] A, B,  // 24-bit unified format inputs
    input [15:0] W,     // twiddle factor (16-bit for FP8, only [7:0] used for FP4)
    output [15:0] X, Y  // 24-bit unified format outputs
);
    generate
        if (MULT_PRECISION == 0 && ADD_PRECISION == 0) begin : USE_PURE_FP4
            fp4_butterfly_generation_unit fp4_butterfly_inst(.A(A[7:0]), .B(B[7:0]), .W(W), .X({8'h00, X[7:0]}), .Y({8'h00, Y[7:0]}));
        end else if (MULT_PRECISION == 1 && ADD_PRECISION == 1) begin : USE_PURE_FP8
            fp8_butterfly_generation_unit fp8_butterfly_inst(.A(A[23:8]), .B(B[23:8]), .W(W), .X(X), .Y(Y));
        end else if (MULT_PRECISION == 0 && ADD_PRECISION == 1) begin: USE_FP8add_FP4mul
            butterfly_generation_unit_8add_4mul fp4mul_fp8add_inst(.A(A[23:8]), .B(B[7:0]), .W(W), .X(X), .Y(Y));
        end else if (MULT_PRECISION == 1 && ADD_PRECISION == 0) begin: USE_FP8mul_FP4add
            butterfly_generation_unit_4add_8mul fp8mul_fp4add_inst(.A(A[7:0]), .B(B[23:8]), .W(W), .X({8'h00, X[7:0]}), .Y({8'h00, Y[7:0]}));
        end
    endgenerate
endmodule

module cmul_wrapper #(
    parameter PRECISION = 0 // DEFAULT 0 for FP4 and 1 for FP8
)(
    input [7:0] a,
    input [7:0] b,
    input [7:0] c,
    input [7:0] d,
    output [7:0] out_real,
    output [7:0] out_imag
); 
    generate
        if (PRECISION == 0) begin: USE_FP4
           wire [3:0] r4, i4;
           fp4_cmul inst_fp4 (
               .a(a[3:0]), 
               .b(b[3:0]), 
               .c(c[3:0]), 
               .d(d[3:0]), 
               .out_real(r4), 
               .out_imag(i4)
           );
           assign out_real = {4'b0000, r4};
           assign out_imag = {4'b0000, i4};
        end
        else begin: USE_FP8
           fp8_cmul inst_fp8 (
               .a(a), 
               .b(b), 
               .c(c), 
               .d(d), 
               .out_real(out_real), 
               .out_imag(out_imag)
           );
        end
    endgenerate
endmodule