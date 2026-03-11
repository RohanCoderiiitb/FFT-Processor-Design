`timescale 1ns/1ps

module tb_fft_8_sol0_gen1;

    // DUT signals
    reg         clk;
    reg         rst;
    reg         data_in_valid;
    reg  [23:0] data_in;
    wire        fft_ready;
    wire        data_out_valid;
    wire [23:0] data_out;
    wire        done;
    wire        error;

    // Debug signals
    reg [31:0] cycle_count;

    // Test-vector storage
    reg [23:0] tv_24bit [31:0];

    // All integers at module scope
    integer test_idx, sample_idx;
    integer out_file;
    integer received;
    integer wait_cnt;

    // DUT instantiation
    fft_8_sol0_gen1_top #(
        .MAX_N     (1024),
        .ADDR_WIDTH(10)
    ) dut (
        .clk           (clk),
        .rst           (rst),
        .N             (10'd8),
        .data_in_valid (data_in_valid),
        .data_in       (data_in),
        .fft_ready     (fft_ready),
        .data_out_valid(data_out_valid),
        .data_out      (data_out),
        .done          (done),
        .error         (error)
    );

    initial clk = 0;
    always  #5 clk = ~clk;

    // Cycle counter for debugging
    always @(posedge clk) begin
        cycle_count <= cycle_count + 1;
    end

    initial begin : STIM
        out_file = $fopen("/home/fftacc/FFT-Hardware/FFT-Processor-Design/sim/fft_8_sol0_gen1_output.txt", "w");
        $readmemh("/home/fftacc/FFT-Hardware/FFT-Processor-Design/sim/test_vectors.hex", tv_24bit);
        rst           = 0;
        data_in_valid = 0;
        data_in       = 0;
        cycle_count   = 0;
        repeat(8) @(posedge clk);
        rst = 1;
        repeat(10) @(posedge clk);
        $display("INFO [%s]: reset released at cycle %0d", "fft_8_sol0_gen1", cycle_count);

        for (test_idx = 0; test_idx < 4; test_idx = test_idx + 1) begin
            $display("INFO [%s]: starting test %0d at cycle %0d", "fft_8_sol0_gen1", test_idx, cycle_count);
            wait_cnt = 0;
            while (!fft_ready && wait_cnt < 12000) begin
                @(posedge clk); wait_cnt = wait_cnt + 1;
                if (wait_cnt % 1000 == 0)
                    $display("DEBUG [%s]: waiting for fft_ready... cycle %0d, fft_ready=%%b", "fft_8_sol0_gen1", cycle_count, fft_ready);
            end
            if (!fft_ready) begin
                $display("ERROR [%s]: fft_ready stuck low after %%0d cycles test %%0d", "fft_8_sol0_gen1", wait_cnt, test_idx);
                $display("DEBUG [%s]: done=%%b, error=%%b", "fft_8_sol0_gen1", done, error);
                $fclose(out_file); $finish;
            end
            $display("INFO [%s]: fft_ready asserted at cycle %0d", "fft_8_sol0_gen1", cycle_count);

            for (sample_idx = 0; sample_idx < 8; sample_idx = sample_idx + 1) begin
                @(posedge clk);
                data_in_valid = 1;
                data_in = {tv_24bit[test_idx*8+sample_idx]};
                if (sample_idx == 0)
                    $display("INFO [%s]: first sample at cycle %0d: %%h", "fft_8_sol0_gen1", cycle_count, data_in);
            end
            @(posedge clk); data_in_valid = 0;
            $display("INFO [%s]: finished feeding samples at cycle %0d", "fft_8_sol0_gen1", cycle_count);

            received = 0; wait_cnt = 0;
            while (received < 8 && wait_cnt < 360) begin
                @(posedge clk);
                if (data_out_valid) begin
                    $fwrite(out_file, "%%06h\n", data_out);
                    received = received + 1;
                    if (received == 1)
                        $display("INFO [%s]: first output at cycle %0d: %%h", "fft_8_sol0_gen1", cycle_count, data_out);
                end
                wait_cnt = wait_cnt + 1;
            end
            if (received < 8)
                $display("WARN [%s]: got %%0d/%%0d outputs test %%0d", "fft_8_sol0_gen1", received, 8, test_idx);
            else
                $display("INFO [%s]: test %%0d complete, got %%0d outputs at cycle %0d", "fft_8_sol0_gen1", test_idx, received, cycle_count);
        end
        $fclose(out_file);
        $display("INFO [%s]: all tests complete at cycle %0d", "fft_8_sol0_gen1", cycle_count);
        $finish;
    end

    initial begin
        #29640;
        $display("ERROR [%s]: watchdog! cycle count = %%0d", "fft_8_sol0_gen1", cycle_count);
        $finish;
    end

endmodule
