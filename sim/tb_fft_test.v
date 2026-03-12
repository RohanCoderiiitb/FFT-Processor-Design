// ============================================================================
// TESTBENCH
// ============================================================================
module tb_fft_8_point();

    reg clk;
    reg reset;
    reg start;
    wire done;
    
    reg load_en;
    reg [2:0] load_addr;
    reg [15:0] load_data;
    
    reg unload_en;
    reg [2:0] unload_addr;
    wire [15:0] unload_data;
    
    integer i, fd;

    // Instantiate Top Module
    fft_8_point_top uut (
        .clk(clk),
        .reset(reset),
        .start(start),
        .done(done),
        .load_en(load_en),
        .load_addr(load_addr),
        .load_data(load_data),
        .unload_en(unload_en),
        .unload_addr(unload_addr),
        .unload_data(unload_data)
    );

    // 100MHz Clock
    always #5 clk = ~clk;

    initial begin
        // Generate Dummy "twiddles_1024.txt" to prevent missing file errors
        // N=8 only uses indices 0, 128, 256, 384
        fd = $fopen("twiddles_1024.txt", "w");
        for (i = 0; i < 512; i = i + 1) begin
            if (i == 0)      $fdisplay(fd, "001110000000000000000000"); // 1 + j0 (FP8 0x3800 extended to 24-bit)
            else if (i == 128) $fdisplay(fd, "001100111011001100000000"); // 0.707 - j0.707 (FP8 0x33B3)
            else if (i == 256) $fdisplay(fd, "000000001011100000000000"); // 0 - j1 (FP8 0x00B8)
            else if (i == 384) $fdisplay(fd, "101100111011001100000000"); // -0.707 - j0.707 (FP8 0xB3B3)
            else             $fdisplay(fd, "000000000000000000000000"); // 0
        end
        $fclose(fd);
    
        // Initialize
        clk = 0;
        reset = 0;
        start = 0;
        load_en = 0;
        load_addr = 0;
        load_data = 0;
        unload_en = 0;
        unload_addr = 0;

        #20;
        reset = 1; // Release reset
        #20;

        // --- Load Phase: Impulse ---
        // An impulse signal (1 at index 0, 0 elsewhere)
        // Expected FFT Result: All 1.0 + j0.0 (FP8: 0x3800)
        
        load_en = 1;
        for (i = 0; i < 8; i = i + 1) begin
            load_addr = i;
            if (i == 0) load_data = 16'h3800; // 1.0 + j0.0
            else        load_data = 16'h0000; // 0.0 + j0.0
            #10;
        end
        load_en = 0;
        
        #20;
        
        // --- Run FFT Phase ---
        start = 1;
        @(posedge done); // Wait until FSM signals completion
        start = 0;
        
        #20;
        
        // --- Unload & Verify Phase ---
        // Memory has a 2-cycle read latency!
        unload_en = 1;
        for (i = 0; i < 8; i = i + 1) begin
            unload_addr = i;
            // Wait 2 cycles for data to flow out of mixed_memory_unified
            @(posedge clk); 
            @(posedge clk); 
            // Sample on 3rd cycle edge
            @(posedge clk);
            
            $display("FFT Output[%0d] = %h (Expected: 3800)", i, unload_data);
            if (unload_data !== 16'h3800)
                $display("   --> MISMATCH WARNING!");
            else
                $display("   --> MATCH OK!");
        end
        
        unload_en = 0;
        #50;
        $display("Simulation Complete.");
        $finish;
    end

endmodule