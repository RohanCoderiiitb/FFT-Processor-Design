module bit_reverse #(
    parameter MAX_N = 1024,
    parameter WIDTH = $clog2(MAX_N)
)(
    input  [WIDTH-1:0] in,
    input  [WIDTH-1:0] N,  // runtime N value needed to shift bits
    output reg [WIDTH-1:0] out
);
    reg [WIDTH-1:0] log2_N;
    reg [WIDTH-1:0] temp_out;
    integer i;
    
    always @(*) begin
        // Compute log2(N) using a robust case statement
        // to avoid 32-bit shift evaluation bugs in some simulators
        case (N)
            1024: log2_N = 10;
            512:  log2_N = 9;
            256:  log2_N = 8;
            128:  log2_N = 7;
            64:   log2_N = 6;
            32:   log2_N = 5;
            16:   log2_N = 4;
            8:    log2_N = 3;
            4:    log2_N = 2;
            2:    log2_N = 1;
            default: log2_N = 0;
        endcase
        
        // Full width bit reversal using a temporary variable
        // to avoid combinational feedback loops (out = out >> ...)
        temp_out = 0;
        for (i = 0; i < WIDTH; i = i + 1) begin
            temp_out[i] = in[WIDTH-1-i];
        end
        
        // Shift down to align the active bits to LSB
        out = temp_out >> (WIDTH - log2_N);
    end
endmodule