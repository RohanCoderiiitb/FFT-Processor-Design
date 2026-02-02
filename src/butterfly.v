module butterfly_generation_unit(
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