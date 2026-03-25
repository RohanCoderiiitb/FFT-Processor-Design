// Auto-generated testbench for fft_16_sol5_gen1_top
// Mirrors tb_fft_test.v interface exactly.
`timescale 1ns/1ps

module tb_fft_16_sol5_gen1;

    reg        clk;
    reg        rst;
    reg        start;
    wire       done;

    reg        load_en;
    reg  [3:0]  load_addr;
    reg  [15:0] load_data;

    reg        unload_en;
    reg  [3:0]  unload_addr;
    wire [15:0] unload_data;

    integer i, ti, out_file;

    // Test vector storage: fp8 packed {real[7:0], imag[7:0]}
    reg [15:0] tv [127:0];

    // DUT
    fft_16_sol5_gen1_top dut (
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
        #74640;
        $display("WATCHDOG TIMEOUT for fft_16_sol5_gen1");
        $finish;
    end

    initial begin : STIM
        integer wait_cnt;

        // Pre-load test vectors
        tv[0] = 16'h3600;
        tv[1] = 16'h0000;
        tv[2] = 16'h0000;
        tv[3] = 16'h0000;
        tv[4] = 16'h0000;
        tv[5] = 16'h0000;
        tv[6] = 16'h0000;
        tv[7] = 16'h0000;
        tv[8] = 16'h0000;
        tv[9] = 16'h0000;
        tv[10] = 16'h0000;
        tv[11] = 16'h0000;
        tv[12] = 16'h0000;
        tv[13] = 16'h0000;
        tv[14] = 16'h0000;
        tv[15] = 16'h0000;
        tv[16] = 16'h3600;
        tv[17] = 16'h3200;
        tv[18] = 16'h0000;
        tv[19] = 16'hb200;
        tv[20] = 16'hb600;
        tv[21] = 16'hb200;
        tv[22] = 16'h8000;
        tv[23] = 16'h3200;
        tv[24] = 16'h3600;
        tv[25] = 16'h3200;
        tv[26] = 16'h0000;
        tv[27] = 16'hb200;
        tv[28] = 16'hb600;
        tv[29] = 16'hb200;
        tv[30] = 16'h8000;
        tv[31] = 16'h3200;
        tv[32] = 16'h3600;
        tv[33] = 16'h0031;
        tv[34] = 16'h8080;
        tv[35] = 16'h8027;
        tv[36] = 16'h8000;
        tv[37] = 16'h0027;
        tv[38] = 16'h8080;
        tv[39] = 16'h0031;
        tv[40] = 16'hb600;
        tv[41] = 16'h80b1;
        tv[42] = 16'h0000;
        tv[43] = 16'h80a7;
        tv[44] = 16'h8000;
        tv[45] = 16'h80a7;
        tv[46] = 16'h0080;
        tv[47] = 16'h80b1;
        tv[48] = 16'h3600;
        tv[49] = 16'h3623;
        tv[50] = 16'h3232;
        tv[51] = 16'ha336;
        tv[52] = 16'hb600;
        tv[53] = 16'h23b6;
        tv[54] = 16'h3232;
        tv[55] = 16'hb6a3;
        tv[56] = 16'h3680;
        tv[57] = 16'hb6a3;
        tv[58] = 16'h3232;
        tv[59] = 16'h23b6;
        tv[60] = 16'hb600;
        tv[61] = 16'ha336;
        tv[62] = 16'h3232;
        tv[63] = 16'h3623;
        tv[64] = 16'h3600;
        tv[65] = 16'h0036;
        tv[66] = 16'hb600;
        tv[67] = 16'h80b6;
        tv[68] = 16'h3680;
        tv[69] = 16'h0036;
        tv[70] = 16'hb600;
        tv[71] = 16'h80b6;
        tv[72] = 16'h3680;
        tv[73] = 16'h0036;
        tv[74] = 16'hb600;
        tv[75] = 16'h80b6;
        tv[76] = 16'h3680;
        tv[77] = 16'h8036;
        tv[78] = 16'hb600;
        tv[79] = 16'h80b6;
        tv[80] = 16'h2022;
        tv[81] = 16'haead;
        tv[82] = 16'h2a2c;
        tv[83] = 16'h2c8a;
        tv[84] = 16'hb59a;
        tv[85] = 16'hb1a9;
        tv[86] = 16'h1530;
        tv[87] = 16'ha098;
        tv[88] = 16'h80a3;
        tv[89] = 16'haba1;
        tv[90] = 16'h2c26;
        tv[91] = 16'h2a22;
        tv[92] = 16'h0e23;
        tv[93] = 16'h2f23;
        tv[94] = 16'h2436;
        tv[95] = 16'haba3;
        tv[96] = 16'h3600;
        tv[97] = 16'h3600;
        tv[98] = 16'h3600;
        tv[99] = 16'h3600;
        tv[100] = 16'h3600;
        tv[101] = 16'h3600;
        tv[102] = 16'h3600;
        tv[103] = 16'h3600;
        tv[104] = 16'hb600;
        tv[105] = 16'hb600;
        tv[106] = 16'hb600;
        tv[107] = 16'hb600;
        tv[108] = 16'hb600;
        tv[109] = 16'hb600;
        tv[110] = 16'hb600;
        tv[111] = 16'hb600;
        tv[112] = 16'h0000;
        tv[113] = 16'h0000;
        tv[114] = 16'h0000;
        tv[115] = 16'h1200;
        tv[116] = 16'h1f00;
        tv[117] = 16'h2900;
        tv[118] = 16'h3100;
        tv[119] = 16'h3500;
        tv[120] = 16'h3600;
        tv[121] = 16'h3500;
        tv[122] = 16'h3100;
        tv[123] = 16'h2900;
        tv[124] = 16'h1f00;
        tv[125] = 16'h1200;
        tv[126] = 16'h0000;
        tv[127] = 16'h0000;

        // Open output file
        out_file = $fopen("/home/fftacc/FFT-Hardware/FFT-Processor-Design/sim/fft_16_sol5_gen1_output.txt", "w");

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
        for (ti = 0; ti < 8; ti = ti + 1) begin

            // --- Load phase ---
            @(posedge clk);
            load_en = 1;
            for (i = 0; i < 16; i = i + 1) begin
                load_addr = i[3:0];
                load_data = tv[ti*16 + i];
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
            while (!done && wait_cnt < 1624) begin
                @(posedge clk);
                wait_cnt = wait_cnt + 1;
            end
            if (!done)
                $display("WARN: done never asserted for test %0d, design fft_16_sol5_gen1", ti);

            @(posedge clk);

            // --- Unload phase ---
            // Memory has 2-cycle read latency.
            // For each sample: assert address, wait 3 posedge clk, sample data.
            unload_en = 1;
            for (i = 0; i < 16; i = i + 1) begin
                unload_addr = i[3:0];
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
        $display("Simulation complete for fft_16_sol5_gen1. Results in /home/fftacc/FFT-Hardware/FFT-Processor-Design/sim/fft_16_sol5_gen1_output.txt");
        $finish;
    end

endmodule
