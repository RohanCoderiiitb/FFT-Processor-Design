
`timescale 1ns/1ps

module tb_fft_8_sol0_gen2;
    reg clk;
    reg rst;
    reg start;
    reg [15:0] data_in_real [7:0];
    reg [15:0] data_in_imag [7:0];
    wire [15:0] data_out_real [7:0];
    wire [15:0] data_out_imag [7:0];
    wire done;
    
    integer i, test_num;
    integer out_file;
    
    // Instantiate DUT
    fft_8_sol0_gen2 dut (
        .clk(clk),
        .rst(rst),
        .start(start),
        .data_in_real(data_in_real),
        .data_in_imag(data_in_imag),
        .data_out_real(data_out_real),
        .data_out_imag(data_out_imag),
        .done(done)
    );
    
    // Clock generation
    initial begin
        clk = 0;
        forever #5 clk = ~clk;
    end
    
    // Test stimulus
    initial begin
        out_file = $fopen("./sim/fft_8_sol0_gen2_output.txt", "w");
        
        // Initialize
        rst = 1;
        start = 0;
        #20 rst = 0;
        
        // Read test vectors from file
        $readmemh("./sim/test_vectors.txt", data_in_real);
        $readmemh("./sim/test_vectors.txt", data_in_imag);
        
        // Run test
        #10 start = 1;
        #10 start = 0;
        
        // Wait for done
        wait(done);
        #10;
        
        // Write outputs
        for (i = 0; i < 8; i = i + 1) begin
            $fwrite(out_file, "%h %h\n", data_out_real[i], data_out_imag[i]);
        end
        
        $fclose(out_file);
        $finish;
    end
    
    // Timeout
    initial begin
        #100000;
        $display("ERROR: Simulation timeout!");
        $finish;
    end
endmodule
