//note that each number is represented as an 8-bit value, with the real part in the upper 4 bits and the imaginary part in the lower 4 bits
module twiddle_factor_fp4 #(
    parameter MAX_N = 32,
    parameter ADDR_WIDTH = $clog2(MAX_N)
)(
    input [ADDR_WIDTH-1:0] k, //index to select the twiddle factor
    input [ADDR_WIDTH:0] n,     //total number of points in the DFT
    output reg [7:0] twiddle_out //8-bit output representing the complex twiddle factor, upper 4 bits are real part, lower 4 bits are imaginary part
);
    // compute normalized angle: theta = 2*pi*k/N
    // for runtime computation, we use a lookup table indexed by k
    // The actual twiddle factor W_N^k depends on N, but we can
    // compute it as W_MaxN^(k*MaxN/N) to use a fixed-size table

    //precomputed twiddle factors for N=32
    //for a given N, the twiddle factor W_N^k = cos(2*pi*k/N) - j*sin(2*pi*k/N)
    //the values are quantized to FP4 format
    //we can select the appropriate twiddle factor based on the index input i.e k%N

    //wire [ADDR_WIDTH-1:0] scaled_k = (k*MAX_N)/n; //scale k based on actual N (won't work because of division in Verilog synthesis tools limitations)

    reg [ADDR_WIDTH-1:0] scaled_k;

    always @(*) begin
        // Since MAX_N is 32, we shift based on how much smaller n is
        // For N=32: k=0..31 -> use directly (no shift)
        // For N=16: k=0..15 -> multiply by 2 (shift left by 1)
        // For N=8:  k=0..7  -> multiply by 4 (shift left by 2)
        // For N=4:  k=0..3  -> multiply by 8 (shift left by 3)
        // For N=2:  k=0..1  -> multiply by 16 (shift left by 4)
        case (n)
            32: scaled_k = k;            // No shift
            16: scaled_k = {k, 1'b0};    // Multiply by 2 (shift left 1)
            8:  scaled_k = {k, 2'b00};   // Multiply by 4 (shift left 2)
            4:  scaled_k = {k, 3'b000};  // Multiply by 8 (shift left 3)
            2:  scaled_k = {k, 4'b0000}; // Multiply by 16 (shift left 4)
            default: scaled_k = 5'd0;    // Handle invalid input safely
        endcase
    end

    // Use symmetry of twiddle factors: W_N^(N-k) = conj(W_N^k)
    // This allows us to use the first half of the table and get conjugate for second half
    reg use_conjugate;
    reg [ADDR_WIDTH-1:0] table_index;
    
    always @(*) begin
        // Handle case where scaled_k might be > 15 (need to use conjugate symmetry)
        if (scaled_k[4] == 1'b1) begin  // If scaled_k >= 16 (in 5-bit representation, bit 4 indicates >= 16)
            use_conjugate = 1'b1;
            table_index = 5'd31 - scaled_k;  // Use 31-scaled_k to index into first half and take conjugate
        end else begin
            use_conjugate = 1'b0;
            table_index = scaled_k;
        end
    end

    always @(*) begin
        // First, get the base twiddle factor from the table
        // The table contains values for angles 0 to 15 (0 to 180 degrees)
        // Values for angles 16 to 31 are obtained by taking conjugate of values for angles 31 down to 16
        case(table_index) 
            // Base twiddle factors (angles 0-15)
            5'd0: begin twiddle_out = 8'b00100000; end // 1 + j0
            5'd1: begin twiddle_out = 8'b00100000; end // 0.98 - j0.19 -> approx 1 + j0
            5'd2: begin twiddle_out = 8'b00101001; end // 0.92 - j0.38 -> approx 1 - 0.5j
            5'd3: begin twiddle_out = 8'b00101001; end // 0.83 - j0.55 -> approx 1 - 0.5j
            5'd4: begin twiddle_out = 8'b00011001; end // 0.71 - j0.71 -> approx 0.5 - 0.5j
            5'd5: begin twiddle_out = 8'b00011010; end // 0.55 - j0.83 -> approx 0.5 - 1j
            5'd6: begin twiddle_out = 8'b00011010; end // 0.38 - j0.92 -> approx 0.5 - 1j
            5'd7: begin twiddle_out = 8'b00001010; end // 0.19 - j0.98 -> approx 0 - 1j
            5'd8: begin twiddle_out = 8'b00000010; end // 0 - j1
            5'd9: begin twiddle_out = 8'b00001010; end // 0.19 + j0.98 -> approx 0 + 1j (conjugate of angle 7)
            5'd10: begin twiddle_out = 8'b00011010; end // 0.38 + j0.92 -> approx 0.5 + 1j (conjugate of angle 6)
            5'd11: begin twiddle_out = 8'b00011010; end // 0.55 + j0.83 -> approx 0.5 + 1j (conjugate of angle 5)
            5'd12: begin twiddle_out = 8'b00011001; end // 0.71 + j0.71 -> approx 0.5 + 0.5j (conjugate of angle 4)
            5'd13: begin twiddle_out = 8'b00101001; end // 0.83 + j0.55 -> approx 1 + 0.5j (conjugate of angle 3)
            5'd14: begin twiddle_out = 8'b00101001; end // 0.92 + j0.38 -> approx 1 + 0.5j (conjugate of angle 2)
            5'd15: begin twiddle_out = 8'b00100000; end // 0.98 + j0.19 -> approx 1 + j0 (conjugate of angle 1)
            // For table_index > 15 (shouldn't happen with our logic, but just in case)
            default: begin twiddle_out = 8'b00000000; end //default case
        endcase
        
        // If we need the conjugate (for angles > 180 degrees), flip the sign of the imaginary part
        if (use_conjugate) begin
            // To get conjugate: keep real part same, flip sign of imaginary part
            // In our 8-bit format: [7:4] = real, [3:0] = imaginary
            // Flip sign by: if imag != 0, change the sign bit (MSB of the 4-bit imaginary part)
            if (twiddle_out[3:0] != 4'b0000) begin
                twiddle_out[3:0] = {~twiddle_out[3], twiddle_out[2:0]}; // Flip sign bit of imaginary part
            end 
        end
    end
endmodule

//note that each number is represented as an 16-bit value, with the real part in the upper 8 bits and the imaginary part in the lower 8 bits
module twiddle_factor_fp8 #(
    parameter MAX_N = 32,
    parameter ADDR_WIDTH = $clog2(MAX_N)
)(
    input [ADDR_WIDTH-1:0] k, //index to select the twiddle factor
    input [ADDR_WIDTH:0] n,     //total number of points in the DFT
    output reg [15:0] twiddle_out //16-bit output representing the complex twiddle factor, upper 8 bits are real part, lower 8 bits are imaginary part
);
    // compute normalized angle: theta = 2*pi*k/N
    // for runtime computation, we use a lookup table indexed by k
    // The actual twiddle factor W_N^k depends on N, but we can
    // compute it as W_MaxN^(k*MaxN/N) to use a fixed-size table

    //precomputed twiddle factors for N=32
    //for a given N, the twiddle factor W_N^k = cos(2*pi*k/N) - j*sin(2*pi*k/N)
    //the values are quantized to FP8 format
    //we can select the appropriate twiddle factor based on the index input i.e k%N

    //wire [ADDR_WIDTH-1:0] scaled_k = (k*MAX_N)/n; //scale k based on actual N (won't work because of division in Verilog synthesis tools limitations)

    reg [ADDR_WIDTH-1:0] scaled_k;

    always @(*) begin
        // Since MAX_N is 32, we shift based on how much smaller n is
        // For N=32: k=0..31 -> use directly (no shift)
        // For N=16: k=0..15 -> multiply by 2 (shift left by 1)
        // For N=8:  k=0..7  -> multiply by 4 (shift left by 2)
        // For N=4:  k=0..3  -> multiply by 8 (shift left by 3)
        // For N=2:  k=0..1  -> multiply by 16 (shift left by 4)
        case (n)
            32: scaled_k = k;            // No shift
            16: scaled_k = {k, 1'b0};    // Multiply by 2 (shift left 1)
            8:  scaled_k = {k, 2'b00};   // Multiply by 4 (shift left 2)
            4:  scaled_k = {k, 3'b000};  // Multiply by 8 (shift left 3)
            2:  scaled_k = {k, 4'b0000}; // Multiply by 16 (shift left 4)
            default: scaled_k = 5'd0;    // Handle invalid input safely
        endcase
    end

    // Use symmetry of twiddle factors: W_N^(N-k) = conj(W_N^k)
    // This allows us to use the first half of the table and get conjugate for second half
    reg use_conjugate;
    reg [ADDR_WIDTH-1:0] table_index;
    
    always @(*) begin
        // Handle case where scaled_k might be > 15 (need to use conjugate symmetry)
        if (scaled_k[4] == 1'b1) begin  // If scaled_k >= 16 (in 5-bit representation, bit 4 indicates >= 16)
            use_conjugate = 1'b1;
            table_index = 5'd31 - scaled_k;  // Use 31-scaled_k to index into first half and take conjugate
        end else begin
            use_conjugate = 1'b0;
            table_index = scaled_k;
        end
    end

    always @(*) begin
        // First, get the base twiddle factor from the table
        // The table contains values for angles 0 to 15 (0 to 180 degrees)
        // Values for angles 16 to 31 are obtained by taking conjugate of values for angles 31 down to 16
        case(table_index) 
            // Base twiddle factors (angles 0-15)
            5'd0: begin twiddle_out = {8'h38, 8'h00}; end // 1 + j0
            5'd1: begin twiddle_out = {8'h38, 8'hA4}; end // 0.98 - j0.19 -> approx 1 + j0
            5'd2: begin twiddle_out = {8'h37, 8'hAC}; end // 0.92 - j0.38 -> approx 1 - 0.5j
            5'd3: begin twiddle_out = {8'h35, 8'hB1}; end // 0.83 - j0.55 -> approx 1 - 0.5j
            5'd4: begin twiddle_out = {8'h33, 8'hB3}; end // 0.71 - j0.71 -> approx 0.5 - 0.5j
            5'd5: begin twiddle_out = {8'h31, 8'hB5}; end // 0.55 - j0.83 -> approx 0.5 - 1j
            5'd6: begin twiddle_out = {8'h2C, 8'hB7}; end // 0.38 - j0.92 -> approx 0.5 - 1j
            5'd7: begin twiddle_out = {8'h24, 8'hB8}; end // 0.19 - j0.98 -> approx 0 - 1j
            5'd8: begin twiddle_out = {8'h00, 8'hB8}; end // 0 - j1
            5'd9: begin twiddle_out = {8'hA4, 8'hB8}; end // 0.19 + j0.98 -> approx 0 + 1j (conjugate of angle 7)
            5'd10: begin twiddle_out ={8'hAC, 8'hB7}; end // 0.38 + j0.92 -> approx 0.5 + 1j (conjugate of angle 6)
            5'd11: begin twiddle_out ={8'hB1, 8'hB5}; end // 0.55 + j0.83 -> approx 0.5 + 1j (conjugate of angle 5)
            5'd12: begin twiddle_out ={8'hB3, 8'hB3}; end // 0.71 + j0.71 -> approx 0.5 + 0.5j (conjugate of angle 4)
            5'd13: begin twiddle_out ={8'hB5, 8'hB1}; end // 0.83 + j0.55 -> approx 1 + 0.5j (conjugate of angle 3)
            5'd14: begin twiddle_out ={8'hB7, 8'hAC}; end // 0.92 + j0.38 -> approx 1 + 0.5j (conjugate of angle 2)
            5'd15: begin twiddle_out ={8'hB8, 8'hA4}; end // 0.98 + j0.19 -> approx 1 + j0 (conjugate of angle 1)
            default: begin twiddle_out = 16'h0000; end //default case
        endcase
        
        // If we need the conjugate (for angles > 180 degrees), flip the sign of the imaginary part
        if (use_conjugate) begin
            // To get conjugate: keep real part same, flip sign of imaginary part
            // In our 16-bit format: [15:8] = real, [7:0] = imaginary
            // Flip sign by: if imag != 0, change the sign bit (MSB of the 8-bit imaginary part)
            if (twiddle_out[7:0] != 8'h00) begin
                twiddle_out[7:0] = {~twiddle_out[7], twiddle_out[6:0]}; // Flip sign bit of imaginary part
            end 
        end
    end
endmodule