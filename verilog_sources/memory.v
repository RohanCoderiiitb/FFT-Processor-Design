//ping-pong operation: read from one bank, write to the OTHER bank
//this allows simultaneous read and write without conflicts
//bank_sel controls which bank to READ from
//writes always go to the OPPOSITE bank (~bank_sel)

// Unified Mixed-Precision Memory with 24-bit format
// Format: [23:16] FP8 Real, [15:8] FP8 Imag, [7:4] FP4 Real, [3:0] FP4 Imag
module mixed_memory_unified #(
    parameter n = 1024,
    parameter ADDR_WIDTH = $clog2(n)
)(
    input wire clk,
    input wire rst,
    input wire bank_sel,
    
    //port 0: read from bank selected by bank_sel
    input wire [ADDR_WIDTH-1:0] rd_addr_0,
    input wire rd_precision_0,  // 0 = FP4, 1 = FP8
    output wire [15:0] rd_data_0,
    
    //port 1: write to opposite bank (~bank_sel for ping-pong operation)
    input wire wr_en_1,
    input wire [ADDR_WIDTH-1:0] wr_addr_1,
    input wire [23:0] wr_data_1  // Full 24-bit write
);

    // 24-bit memory banks
    // Format: [23:16] FP8 Real, [15:8] FP8 Imag, [7:4] FP4 Real, [3:0] FP4 Imag
    reg [23:0] bank0_mem [0:n-1];
    reg [23:0] bank1_mem [0:n-1];

    integer i;
    
    //write logic with reset
    //when bank_sel=0: we read from bank0, so write to bank1
    //when bank_sel=1: we read from bank1, so write to bank0
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            for (i = 0; i < n; i = i + 1) begin
                bank0_mem[i] <= 24'b0;
                bank1_mem[i] <= 24'b0;
            end
        end else begin
            if (wr_en_1) begin
                if (bank_sel == 0) begin
                    //reading from bank0, so write to bank1
                    bank1_mem[wr_addr_1] <= wr_data_1;
                end else begin
                    //reading from bank1, so write to bank0
                    bank0_mem[wr_addr_1] <= wr_data_1;
                end
            end
        end
    end

    //read logic: read from the bank selected by bank_sel
    //synchronous read (1-cycle latency)
    //precision selection happens during read
    reg [23:0] rd_data_full;
    reg [15:0] rd_data_reg;
    reg rd_precision_reg;
    
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            rd_data_full <= 24'b0;
            rd_data_reg <= 16'b0;
            rd_precision_reg <= 1'b0;
        end else begin
            // Read full 24-bit data
            rd_data_full <= bank_sel ? bank1_mem[rd_addr_0] : bank0_mem[rd_addr_0];
            rd_precision_reg <= rd_precision_0;
            
            // Select precision on next cycle
            if (rd_precision_reg == 1) begin
                // FP8: Extract bits [23:8]
                rd_data_reg <= rd_data_full[23:8];
            end else begin
                // FP4: Extract bits [7:0] and zero-extend
                rd_data_reg <= {8'h00, rd_data_full[7:0]};
            end
        end
    end

    assign rd_data_0 = rd_data_reg;

endmodule


// Backward-compatible FP4 memory (uses lower 8 bits of unified format)
module fp4_fft_memory_reg #(
    parameter n = 1024,
    parameter ADDR_WIDTH = $clog2(n)
)(
    input wire clk,
    input wire rst,
    input wire bank_sel,
    
    //port 0: read from bank selected by bank_sel
    input wire [ADDR_WIDTH-1:0] rd_addr_0,
    output wire [7:0] rd_data_0,
    
    //port 1: write to opposite bank (~bank_sel for ping-pong operation)
    input wire wr_en_1,
    input wire [ADDR_WIDTH-1:0] wr_addr_1,
    input wire [7:0] wr_data_1
);

    reg [7:0] bank0_mem [0:n-1];
    reg [7:0] bank1_mem [0:n-1];

    integer i;
    
    //write logic with reset
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            for (i = 0; i < n; i = i + 1) begin
                bank0_mem[i] <= 8'b0;
                bank1_mem[i] <= 8'b0;
            end
        end else begin
            if (wr_en_1) begin
                if (bank_sel == 0) begin
                    bank1_mem[wr_addr_1] <= wr_data_1;
                end else begin
                    bank0_mem[wr_addr_1] <= wr_data_1;
                end
            end
        end
    end

    //read logic: read from the bank selected by bank_sel
    //synchronous read (1-cycle latency)
    reg [7:0] rd_data_reg;
    always @(posedge clk or negedge rst) begin
        if (!rst) 
            rd_data_reg <= 8'b0;
        else 
            rd_data_reg <= bank_sel ? bank1_mem[rd_addr_0] : bank0_mem[rd_addr_0];
    end

    assign rd_data_0 = rd_data_reg;

endmodule


// Backward-compatible FP8 memory (uses upper 16 bits of unified format)
module fp8_fft_memory_reg #(
    parameter n = 1024,
    parameter ADDR_WIDTH = $clog2(n)
)(
    input wire clk,
    input wire rst,
    input wire bank_sel,
    
    //port 0: read from bank selected by bank_sel
    input wire [ADDR_WIDTH-1:0] rd_addr_0,
    output wire [15:0] rd_data_0,
    
    //port 1: write to opposite bank (~bank_sel for ping-pong operation)
    input wire wr_en_1,
    input wire [ADDR_WIDTH-1:0] wr_addr_1,
    input wire [15:0] wr_data_1
);

    reg [15:0] bank0_mem [0:n-1];
    reg [15:0] bank1_mem [0:n-1];

    integer i;
    
    //write logic with reset
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            for (i = 0; i < n; i = i + 1) begin
                bank0_mem[i] <= 16'b0;
                bank1_mem[i] <= 16'b0;
            end
        end else begin
            if (wr_en_1) begin
                if (bank_sel == 0) begin
                    bank1_mem[wr_addr_1] <= wr_data_1;
                end else begin
                    bank0_mem[wr_addr_1] <= wr_data_1;
                end
            end
        end
    end

    //read logic: read from the bank selected by bank_sel
    //synchronous read (1-cycle latency)
    reg [15:0] rd_data_reg;
    always @(posedge clk or negedge rst) begin
        if (!rst) 
            rd_data_reg <= 16'b0;
        else 
            rd_data_reg <= bank_sel ? bank1_mem[rd_addr_0] : bank0_mem[rd_addr_0];
    end

    assign rd_data_0 = rd_data_reg;

endmodule