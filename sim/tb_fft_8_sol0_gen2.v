`timescale 1ns/1ps

module tb_fft_8_sol0_gen2;

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

    // Test-vector storage
    reg [7:0] tv_real [103:0];
    reg [7:0] tv_imag [103:0];

    // All integers at module scope (Verilog-2001)
    integer test_idx, sample_idx;
    integer out_file;
    integer received;
    integer wait_cnt;

    // DUT instantiation
    fft_8_sol0_gen2_top #(
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

    initial clk = 0;
    always  #5 clk = ~clk;

    initial begin : STIM
        out_file = $fopen("./sim/fft_8_sol0_gen2_output.txt", "w");
        $readmemh("./sim/test_vectors_real.hex", tv_real);
        $readmemh("./sim/test_vectors_imag.hex", tv_imag);
        rst           = 0;
        data_in_valid = 0;
        data_in       = 0;
        repeat(8) @(posedge clk);
        rst = 1;
        repeat(10) @(posedge clk);
        $display("INFO [fft_8_sol0_gen2]: reset released");
        for (test_idx = 0; test_idx < 13; test_idx = test_idx + 1) begin
            wait_cnt = 0;
            while (!fft_ready && wait_cnt < 12000) begin
                @(posedge clk); wait_cnt = wait_cnt + 1;
            end
            if (!fft_ready) begin
                $display("ERROR [fft_8_sol0_gen2]: fft_ready stuck low test %0d", test_idx);
                $fclose(out_file); $finish;
            end
            for (sample_idx = 0; sample_idx < 8; sample_idx = sample_idx + 1) begin
                @(posedge clk);
                data_in_valid = 1;
                data_in = {tv_real[test_idx*8+sample_idx],
                          tv_imag[test_idx*8+sample_idx],
                          8'h00};
            end
            @(posedge clk); data_in_valid = 0;
            received = 0; wait_cnt = 0;
            while (received < 8 && wait_cnt < 12000) begin
                @(posedge clk);
                if (data_out_valid) begin
                    $fwrite(out_file, "%06h\n", data_out);
                    received = received + 1;
                end
                wait_cnt = wait_cnt + 1;
            end
            if (received < 8)
                $display("WARN [fft_8_sol0_gen2]: got %0d/%0d outputs test %0d",
                         received, 8, test_idx);
        end
        $fclose(out_file);
        $display("INFO [fft_8_sol0_gen2]: done, %0d tests", 13);
        $finish;
    end

    initial begin
        #629000;
        $display("ERROR [fft_8_sol0_gen2]: watchdog!");
        $finish;
    end

endmodule
