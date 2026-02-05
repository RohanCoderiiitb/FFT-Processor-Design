// Wrapper modules to choose the precision

module butterfly_wrapper #(
    parameter PRECISION = 0 // 0 for FP4, 1 for FP8
)(
    input [15:0] A, B, W, 
    output [15:0] X, Y
);
    generate
        if (PRECISION == 0) begin : USE_FP4
            wire [7:0] x_8bit, y_8bit;
            fp4_butterfly_generation_unit fp4_butterfly_inst(.A(A[7:0]), .B(B[7:0]), .W(W[7:0]), .X(x_8bit), .Y(y_8bit));
            assign Y = {8'b0, y_8bit};
            assign X = {8'b0, x_8bit};
        end else begin : USE_FP8
            fp8_butterfly_generation_unit fp8_butterfly_inst(.A(A), .B(B), .W(W), .X(X), .Y(Y));
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