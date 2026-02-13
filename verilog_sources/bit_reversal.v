module bit_reverse #(
    parameter MAX_N = 32,
    parameter WIDTH = $clog2(MAX_N)
)(
    input [WIDTH-1:0] in,
    output reg [WIDTH-1:0] out
);
    integer i;
    always @(*) begin
        for (i=0; i < WIDTH; i=i+1)
            out[i] = in[WIDTH-1-i];
    end
endmodule