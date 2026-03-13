// Auto-generated testbench for fft_8_sol4_gen1_top
// Mirrors tb_fft_test.v interface exactly.
`timescale 1ns/1ps

module tb_fft_8_sol4_gen1;

    reg        clk;
    reg        rst;
    reg        start;
    wire       done;

    reg        load_en;
    reg  [2:0]  load_addr;
    reg  [15:0] load_data;

    reg        unload_en;
    reg  [2:0]  unload_addr;
    wire [15:0] unload_data;

    integer i, ti, out_file;

    // Test vector storage: fp8 packed {real[7:0], imag[7:0]}
    reg [15:0] tv [31:0];

    // DUT
    fft_8_sol4_gen1_top dut (
        .clk        (clk),
        .rst        (rst),
        .start      (start),
        .done       (done),
        .load_en    (load_en),
        .load_addr  (load_addr),
        .load_data  (load_data),
        .unload_en  (unload_en),
        .unload_addr(unload_addr),
        .unload_data(unload_data)
    );

    // 100 MHz clock
    initial clk = 0;
    always  #5 clk = ~clk;

    // Watchdog
    initial begin
        #36240;
        $display("WATCHDOG TIMEOUT for fft_8_sol4_gen1");
        $finish;
    end

    initial begin : STIM
        integer wait_cnt;

        // Pre-load test vectors
        tv[0] = 16'h3800;
        tv[1] = 16'h0000;
        tv[2] = 16'h0000;
        tv[3] = 16'h0000;
        tv[4] = 16'h0000;
        tv[5] = 16'h0000;
        tv[6] = 16'h0000;
        tv[7] = 16'h0000;
        tv[8] = 16'h3800;
        tv[9] = 16'h3800;
        tv[10] = 16'h3800;
        tv[11] = 16'h3800;
        tv[12] = 16'h3800;
        tv[13] = 16'h3800;
        tv[14] = 16'h3800;
        tv[15] = 16'h3800;
        tv[16] = 16'h3800;
        tv[17] = 16'h3333;
        tv[18] = 16'h0038;
        tv[19] = 16'hb333;
        tv[20] = 16'hb800;
        tv[21] = 16'hb3b3;
        tv[22] = 16'h80b8;
        tv[23] = 16'h33b3;
        tv[24] = 16'h3800;
        tv[25] = 16'h0038;
        tv[26] = 16'hb800;
        tv[27] = 16'h80b8;
        tv[28] = 16'h3880;
        tv[29] = 16'h0038;
        tv[30] = 16'hb800;
        tv[31] = 16'h80b8;

        // Open output file
        out_file = $fopen("/home/fftacc/FFT-Hardware/FFT-Processor-Design/sim/fft_8_sol4_gen1_output.txt", "w");

        // Initialise signals
        rst        = 0;
        start      = 0;
        load_en    = 0;
        load_addr  = 0;
        load_data  = 0;
        unload_en  = 0;
        unload_addr= 0;

        // Hold reset for 8 cycles then release
        repeat(8) @(posedge clk);
        rst = 1;
        repeat(4) @(posedge clk);

        // Run each test vector
        for (ti = 0; ti < 4; ti = ti + 1) begin

            // --- Load phase ---
            @(posedge clk);
            load_en = 1;
            for (i = 0; i < 8; i = i + 1) begin
                load_addr = i[2:0];
                load_data = tv[ti*8 + i];
                @(posedge clk);
            end
            load_en = 0;

            @(posedge clk);

            // --- Run FFT ---
            start = 1;
            @(posedge clk);
            start = 0;

            // Wait for done
            wait_cnt = 0;
            while (!done && wait_cnt < 1384) begin
                @(posedge clk);
                wait_cnt = wait_cnt + 1;
            end
            if (!done)
                $display("WARN: done never asserted for test %0d, design fft_8_sol4_gen1", ti);

            @(posedge clk);

            // --- Unload phase ---
            // Memory has 2-cycle read latency.
            // For each sample: assert address, wait 3 posedge clk, sample data.
            unload_en = 1;
            for (i = 0; i < 8; i = i + 1) begin
                unload_addr = i[2:0];
                @(posedge clk);
                @(posedge clk);
                @(posedge clk);
                $fwrite(out_file, "%04h\n", unload_data);
            end
            unload_en = 0;

            @(posedge clk);
            @(posedge clk);

        end // for ti

        $fclose(out_file);
        $display("Simulation complete for fft_8_sol4_gen1. Results in /home/fftacc/FFT-Hardware/FFT-Processor-Design/sim/fft_8_sol4_gen1_output.txt");
        $finish;
    end

endmodule
