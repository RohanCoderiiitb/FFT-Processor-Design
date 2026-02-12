// Butterfly modules for 24-bit unified memory format
// Memory format: [23:16] FP8 Real, [15:8] FP8 Imag, [7:4] FP4 Real, [3:0] FP4 Imag

module fp8_butterfly_generation_unit(
    input [23:0] A,
    input [23:0] B,
    input [15:0] W,
    output [23:0] X,
    output [23:0] Y
);
    //step 1: extract FP8 data from unified format [23:8]
    wire [15:0] A_fp8 = A[23:8];
    wire [15:0] B_fp8 = B[23:8];
    
    //step 2: complex multiplication
    wire [15:0] wb_product;
    
    fp8_cmul cmul_inst(
          .a(B_fp8[15:8]), //real part of B
          .b(B_fp8[7:0]),  //imag part of B
          .c(W[15:8]),     //real part of W
          .d(W[7:0]),      //imag part of W
          .out_real(wb_product[15:8]),
          .out_imag(wb_product[7:0])
    );
    
    //step 3: complex addition
    wire [15:0] X_fp8;
    fp8_complex_add_sub adder_inst(
          .a(A_fp8),
          .b(wb_product),
          .sub(1'b0),
          .out(X_fp8)
    );
    
    //step 4: complex subtraction
    wire [15:0] Y_fp8;
    fp8_complex_add_sub sub_inst(
          .a(A_fp8),
          .b(wb_product),
          .sub(1'b1),
          .out(Y_fp8)
    );
    
    //step 5: pack results into unified 24-bit format (FP8 in upper bits, zero lower bits)
    assign X = {X_fp8, 8'h00};
    assign Y = {Y_fp8, 8'h00};
endmodule

module fp4_butterfly_generation_unit(
    input [23:0] A,
    input [23:0] B,
    input [7:0] W,
    output [23:0] X,
    output [23:0] Y
);
    //step 1: extract FP4 data from unified format [7:0]
    wire [7:0] A_fp4 = A[7:0];
    wire [7:0] B_fp4 = B[7:0];

    //step 2: complex multiplication
    wire [7:0] wb_product;

    fp4_cmul complex_mult_inst(
        .a(B_fp4[7:4]), //real part of B
        .b(B_fp4[3:0]), //imag part of B
        .c(W[7:4]),     //real part of W
        .d(W[3:0]),     //imag part of W
        .out_real(wb_product[7:4]),
        .out_imag(wb_product[3:0])
    );

    //step 3: complex addition
    wire [7:0] X_fp4;
    fp4_complex_add_sub add_inst(
        .a(A_fp4),
        .b(wb_product),
        .sub(1'b0),
        .out(X_fp4)
    );

    //step 4: complex subtraction
    wire [7:0] Y_fp4;
    fp4_complex_add_sub sub_inst(
        .a(A_fp4),
        .b(wb_product),
        .sub(1'b1),
        .out(Y_fp4)
    );
    
    //step 5: pack results into unified 24-bit format (FP4 in lower bits, zero upper bits)
    assign X = {16'h0000, X_fp4};
    assign Y = {16'h0000, Y_fp4};
endmodule

module butterfly_generation_unit_8add_4mul(
    input [23:0] A,
    input [23:0] B,
    input [15:0] W,
    output [23:0] X,
    output [23:0] Y
);
    //step 1: extract FP8 data for multiplication
    wire [15:0] A_fp8 = A[23:8];
    wire [15:0] B_fp8 = B[23:8];

    //step 2: complex multiplication in FP8
    wire [15:0] wb_product_fp8;

    fp8_cmul complex_mult_inst(
        .a(B_fp8[15:8]), //real part of B
        .b(B_fp8[7:0]),  //imag part of B
        .c(W[15:8]),     //real part of W
        .d(W[7:0]),      //imag part of W
        .out_real(wb_product_fp8[15:8]),
        .out_imag(wb_product_fp8[7:0])
    );
    
    //step 3: convert multiplication result from FP8 to FP4 for addition
    wire [7:0] wb_product_fp4;
    complex_fp8_to_fp4 conv_wb(
        .complex_fp8(wb_product_fp8),
        .complex_fp4(wb_product_fp4)
    );
    
    //step 4: convert A from FP8 to FP4 for addition
    wire [7:0] A_fp4;
    complex_fp8_to_fp4 conv_a(
        .complex_fp8(A_fp8),
        .complex_fp4(A_fp4)
    );

    //step 5: complex addition in FP4
    wire [7:0] X_fp4;
    fp4_complex_add_sub add_inst(
        .a(A_fp4),
        .b(wb_product_fp4),
        .sub(1'b0),
        .out(X_fp4)
    );

    //step 6: complex subtraction in FP4
    wire [7:0] Y_fp4;
    fp4_complex_add_sub sub_inst(
        .a(A_fp4),
        .b(wb_product_fp4),
        .sub(1'b1),
        .out(Y_fp4)
    );
    
    //step 7: pack results into unified 24-bit format (FP4 in lower bits)
    assign X = {16'h0000, X_fp4};
    assign Y = {16'h0000, Y_fp4};
endmodule

module butterfly_generation_unit_4add_8mul(
    input [23:0] A,
    input [23:0] B,
    input [7:0] W,
    output [23:0] X,
    output [23:0] Y
);
    //step 1: extract FP4 data for multiplication
    wire [7:0] A_fp4 = A[7:0];
    wire [7:0] B_fp4 = B[7:0];

    //step 2: complex multiplication in FP4
    wire [7:0] wb_product_fp4;

    fp4_cmul complex_mult_inst(
        .a(B_fp4[7:4]), //real part of B
        .b(B_fp4[3:0]), //imag part of B
        .c(W[7:4]),     //real part of W
        .d(W[3:0]),     //imag part of W
        .out_real(wb_product_fp4[7:4]),
        .out_imag(wb_product_fp4[3:0])
    );
    
    //step 3: convert multiplication result from FP4 to FP8 for addition
    wire [15:0] wb_product_fp8;
    complex_fp4_to_fp8 conv_wb(
        .complex_fp4(wb_product_fp4),
        .complex_fp8(wb_product_fp8)
    );
    
    //step 4: convert A from FP4 to FP8 for addition
    wire [15:0] A_fp8;
    complex_fp4_to_fp8 conv_a(
        .complex_fp4(A_fp4),
        .complex_fp8(A_fp8)
    );

    //step 5: complex addition in FP8
    wire [15:0] X_fp8;
    fp8_complex_add_sub add_inst(
        .a(A_fp8),
        .b(wb_product_fp8),
        .sub(1'b0),
        .out(X_fp8)
    );

    //step 6: complex subtraction in FP8
    wire [15:0] Y_fp8;
    fp8_complex_add_sub sub_inst(
        .a(A_fp8),
        .b(wb_product_fp8),
        .sub(1'b1),
        .out(Y_fp8)
    );
    
    //step 7: pack results into unified 24-bit format (FP8 in upper bits)
    assign X = {X_fp8, 8'h00};
    assign Y = {Y_fp8, 8'h00};
endmodule