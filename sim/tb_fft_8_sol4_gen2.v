`timescale 1ns/1ps

module tb_fft_8_sol4_gen2;

    // ----------------------------------------------------------------
    // DUT signals
    // ----------------------------------------------------------------
    reg         clk;
    reg         rst;
    reg         data_in_valid;
    reg  [23:0] data_in;
    wire        fft_ready;
    wire        data_out_valid;
    wire [23:0] data_out;
    wire        done;
    wire        error;

    // ----------------------------------------------------------------
    // Test-vector storage
    // ----------------------------------------------------------------
    reg [7:0] tv_real [103:0];
    reg [7:0] tv_imag [103:0];

    integer i, test_idx, sample_idx;
    integer out_file;
    integer sent, received;

    // ----------------------------------------------------------------
    // DUT instantiation
    // ----------------------------------------------------------------
    fft_8_sol4_gen2_top #(
        .MAX_N     (8),
        .ADDR_WIDTH(3)
    ) dut (
        .clk           (clk),
        .rst           (rst),
        .data_in_valid (data_in_valid),
        .data_in       (data_in),
        .fft_ready     (fft_ready),
        .data_out_valid(data_out_valid),
        .data_out      (data_out),
        .done          (done),
        .error         (error)
    );

    // ----------------------------------------------------------------
    // Clock
    // ----------------------------------------------------------------
    initial clk = 0;
    always  #5 clk = ~clk;

    // ----------------------------------------------------------------
    // Stimulus
    // ----------------------------------------------------------------
    initial begin : STIM
        out_file = $fopen("./sim/fft_8_sol4_gen2_output.txt", "w");

        // Load test vectors
        $readmemh("./sim/test_vectors_real.hex", tv_real);
        $readmemh("./sim/test_vectors_imag.hex", tv_imag);

        // Active-low reset: assert rst=0, then release rst=1
        rst           = 0;
        data_in_valid = 0;
        data_in       = 0;
        repeat(4) @(posedge clk);
        rst = 1;
        repeat(2) @(posedge clk);

        // ---- Run each test vector ----
        for (test_idx = 0; test_idx < 13; test_idx = test_idx + 1) begin

            // Wait for FFT to be ready
            while (!fft_ready) @(posedge clk);

            // Feed N samples
            for (sample_idx = 0; sample_idx < 8; sample_idx = sample_idx + 1) begin
                @(posedge clk);
                data_in_valid = 1;
                // Pack: [23:16]=FP8_real [15:8]=FP8_imag [7:0]=0 (FP4 unused)
                data_in = {tv_real[test_idx*8 + sample_idx],
                           tv_imag[test_idx*8 + sample_idx],
                           8'h00};
            end
            @(posedge clk);
            data_in_valid = 0;

            // Collect N output samples
            received = 0;
            while (received < 8) begin
                @(posedge clk);
                if (data_out_valid) begin
                    $fwrite(out_file, "%06h\n", data_out);
                    received = received + 1;
                end
            end
        end

        $fclose(out_file);
        $display("Simulation complete: %0d tests run", 13);
        $finish;
    end

    // ----------------------------------------------------------------
    // Timeout watchdog
    // ----------------------------------------------------------------
    initial begin
        #(20800);
        $display("ERROR: Simulation timeout for fft_8_sol4_gen2!");
        $finish;
    end

endmodule
