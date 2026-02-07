//ping-pong operation: read from one bank, write to the OTHER bank
//this allows simultaneous read and write without conflicts
//bank_sel controls which bank to READ from
//writes always go to the OPPOSITE bank (~bank_sel)
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
    //when bank_sel=0: we read from bank0, so write to bank1
    //when bank_sel=1: we read from bank1, so write to bank0
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            for (i = 0; i < n; i = i + 1) begin
                bank0_mem[i] <= 8'b0;
                bank1_mem[i] <= 8'b0;
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
    reg [7:0] rd_data_reg;
    always @(posedge clk or negedge rst) begin
        if (!rst) 
            rd_data_reg <= 8'b0;
        else 
            rd_data_reg <= bank_sel ? bank1_mem[rd_addr_0] : bank0_mem[rd_addr_0];
    end

    assign rd_data_0 = rd_data_reg;

endmodule


//implementation as two separate memory banks:

//ping-pong operation: read from one bank, write to the OTHER bank
//this allows simultaneous read and write without conflicts
//bank_sel controls which bank to READ from
//writes always go to the OPPOSITE bank (~bank_sel)
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
    //when bank_sel=0: we read from bank0, so write to bank1
    //when bank_sel=1: we read from bank1, so write to bank0
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            for (i = 0; i < n; i = i + 1) begin
                bank0_mem[i] <= 16'b0;
                bank1_mem[i] <= 16'b0;
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
    reg [15:0] rd_data_reg;
    always @(posedge clk or negedge rst) begin
        if (!rst) 
            rd_data_reg <= 16'b0;
        else 
            rd_data_reg <= bank_sel ? bank1_mem[rd_addr_0] : bank0_mem[rd_addr_0];
    end

    assign rd_data_0 = rd_data_reg;

endmodule


//implementation as a unified memory bank, where:
//fp8 -> 16 bit register width, upper 8 are real and lower 8 are imag
//fp4 -> 16 bit register which stores 2 fp4 values: [15:12] real0, [11:8] imag0, [7:4] real1, [3:0] imag1
//format_mode: 0 = fp4 mode, 1 = fp8 mode

module mixed_memory_reg #(
    parameter n = 1024,
    parameter ADDR_WIDTH = $clog2(n)
)(
    input wire clk,
    input wire rst,
    input wire bank_sel,
    input wire format_mode,  //0 = fp4, 1 = fp8
    
    //port 0: read from bank selected by bank_sel
    input wire [ADDR_WIDTH-1:0] rd_addr_0,
    output wire [15:0] rd_data_0,
    output wire rd_format_0,  //outputs the format of the data read
    
    //port 1: write to opposite bank (~bank_sel for ping-pong operation)
    input wire wr_en_1,
    input wire [ADDR_WIDTH-1:0] wr_addr_1,
    input wire [15:0] wr_data_1
);

    reg [15:0] bank0_mem [0:n-1];
    reg [15:0] bank1_mem [0:n-1];
    
    //format tracking arrays: 0 = fp4, 1 = fp8
    reg bank0_format [0:n-1];
    reg bank1_format [0:n-1];

    integer i;
    
    //write logic with reset
    //when bank_sel=0: we read from bank0, so write to bank1
    //when bank_sel=1: we read from bank1, so write to bank0
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            for (i = 0; i < n; i = i + 1) begin
                bank0_mem[i] <= 16'b0;
                bank1_mem[i] <= 16'b0;
                bank0_format[i] <= 1'b0;  //default to fp4
                bank1_format[i] <= 1'b0;  //default to fp4
            end
        end else begin
            if (wr_en_1) begin
                if (bank_sel == 0) begin
                    //reading from bank0, so write to bank1
                    bank1_mem[wr_addr_1] <= wr_data_1;
                    bank1_format[wr_addr_1] <= format_mode;
                end else begin
                    //reading from bank1, so write to bank0
                    bank0_mem[wr_addr_1] <= wr_data_1;
                    bank0_format[wr_addr_1] <= format_mode;
                end
            end
        end
    end

    //read logic: read from the bank selected by bank_sel
    //synchronous read (1-cycle latency)
    reg [15:0] rd_data_reg;
    reg rd_format_reg;
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            rd_data_reg <= 16'b0;
            rd_format_reg <= 1'b0;
        end else begin
            rd_data_reg <= bank_sel ? bank1_mem[rd_addr_0] : bank0_mem[rd_addr_0];
            rd_format_reg <= bank_sel ? bank1_format[rd_addr_0] : bank0_format[rd_addr_0];
        end
    end

    assign rd_data_0 = rd_data_reg;
    assign rd_format_0 = rd_format_reg;

endmodule