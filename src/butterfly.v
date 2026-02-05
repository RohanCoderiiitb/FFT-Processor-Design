module fp8_butterfly_generation_unit(
    input [15:0] A,
    input [15:0] B,
    input [15:0] W,
    output [15:0] X,
    output [15:0] Y
);
    wire [15:0] wb_product;
    
    fp8_cmul cmul_inst(
          .a(B[15:8]),
          .b(B[7:0]),
          .c(W[15:8]),
          .d(W[7:0]),
          .out_real(wb_product[15:8]),
          .out_imag(wb_product[7:0])
    );
    
    fp8_complex_add_sub adder_inst(
          .a(A),
          .b(wb_product),
          .sub(1'b0),
          .out(X)
    );
    
    fp8_complex_add_sub sub_inst(
          .a(A),
          .b(wb_product),
          .sub(1'b1),
          .out(Y)
    );      
endmodule

module fp4_butterfly_generation_unit(
    input [7:0] A,
    input [7:0] B,
    input [7:0] W,
    output [7:0] X,
    output [7:0] Y
);
    //step 1: complex multiplication

    wire [7:0] wb_product;

    fp4_cmul complex_mult_inst(
        .a(B[7:4]), //real part of B
        .b(B[3:0]), //imag part of B
        .c(W[7:4]), //real part of W
        .d(W[3:0]), //imag part of W
        .out_real(wb_product[7:4]),
        .out_imag(wb_product[3:0])
    );

    //step 2: complex addition
    fp4_complex_add_sub add_inst(
        .a(A),
        .b(wb_product),
        .sub(1'b0),
        .out(X)
    );

    //step 3: complex subtraction
    fp4_complex_add_sub sub_inst(
        .a(A),
        .b(wb_product),
        .sub(1'b1),
        .out(Y)
    );

endmodule

// Wrapper module to choose the precision
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