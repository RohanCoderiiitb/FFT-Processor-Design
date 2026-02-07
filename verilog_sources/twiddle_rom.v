module twiddle_factor_unified #(
    parameter MAX_N = 1024,
    parameter ADDR_WIDTH = 10, // $clog2(1024)
    parameter PRECISION = 0    // 0 for FP4 and 1 for FP8
)(
    input [ADDR_WIDTH-1:0] k,   // Index k
    input [ADDR_WIDTH:0] n,     // Current FFT size N
    output reg [15:0] twiddle_out
);

    // --------------------------------------------------------
    // 1. ROM Declaration (1024 entries)
    // --------------------------------------------------------
    // The file contains 1024 lines:
    // Lines 0-511:    FP8 Twiddle Factors
    // Lines 512-1023: FP4 Twiddle Factors
    reg [15:0] rom [0:1023];

    initial begin
        // Read the binary file containing both precision formats
        $readmemb("twiddles_1024.txt", rom);
    end

    // Define the offset based on PRECISION parameter
    // If FP8 (1), start at 0. If FP4 (0), start at 512.
    wire [9:0] base_offset;
    assign base_offset = (PRECISION == 1) ? 10'd0 : 10'd512;

    // --------------------------------------------------------
    // 2. Dynamic Scaling Logic
    // --------------------------------------------------------
    reg [ADDR_WIDTH-1:0] scaled_k;

    always @(*) begin
        case (n)
            1024: scaled_k = k;
            512:  scaled_k = {k, 1'b0};      // k * 2
            256:  scaled_k = {k, 2'b00};     // k * 4
            128:  scaled_k = {k, 3'b000};    // k * 8
            64:   scaled_k = {k, 4'b0000};   // k * 16
            32:   scaled_k = {k, 5'b00000};  // k * 32
            16:   scaled_k = {k, 6'b000000}; // k * 64
            8:    scaled_k = {k, 7'b0000000};// k * 128
            4:    scaled_k = {k, 8'b00000000};// k * 256
            2:    scaled_k = {k, 9'b000000000};// k * 512
            default: scaled_k = 10'd0;
        endcase
    end

    // --------------------------------------------------------
    // 3. Symmetry Logic & Fetch
    // --------------------------------------------------------
    reg use_conjugate;
    reg [9:0] rom_addr_base; // Address within the 0-511 block
    reg is_midpoint;

    always @(*) begin
        is_midpoint = 1'b0;

        if (scaled_k == 512) begin
            // 180 degrees (Index 512) is a boundary case
            is_midpoint = 1'b1;
            rom_addr_base = 0; 
            use_conjugate = 1'b0;
        end 
        else if (scaled_k > 511) begin
            // Second half (180 < angle < 360) -> Symmetry
            rom_addr_base = 1024 - scaled_k;
            use_conjugate = 1'b1;
        end 
        else begin
            // First half (0 <= angle < 180)
            rom_addr_base = scaled_k;
            use_conjugate = 1'b0;
        end
    end

    // --------------------------------------------------------
    // 4. Output Generation
    // --------------------------------------------------------
    reg [15:0] raw_data;

    always @(*) begin
        if (is_midpoint) begin
            // Hardcoded -1.0 value
            if (PRECISION == 1) 
                raw_data = 16'hB800; // FP8 (-1.0)
            else 
                raw_data = 16'h00A0; // FP4 (-1.0 approx)
        end else begin
            // Read from ROM with offset applied
            // FP8 reads from [0 + index], FP4 reads from [512 + index]
            raw_data = rom[base_offset + rom_addr_base];
        end

        twiddle_out = raw_data;

        // Apply Conjugate (Flip sign of imaginary part)
        if (use_conjugate) begin
            if (PRECISION == 1) begin
                // FP8: [7:0] is Imaginary
                if (twiddle_out[7:0] != 8'h00) 
                    twiddle_out[7:0] = {~twiddle_out[7], twiddle_out[6:0]};
            end else begin
                // FP4: [3:0] is Imaginary
                if (twiddle_out[3:0] != 4'h0) 
                    twiddle_out[3:0] = {~twiddle_out[3], twiddle_out[2:0]};
            end
        end
    end

endmodule