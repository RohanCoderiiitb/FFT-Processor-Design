//mixed-precision FFT TOP module for 8-point FFT

module mixed_fft_8_top #(
    parameter MAX_N = 8,
    parameter ADDR_WIDTH = 3
)(
    input wire clk,
    input wire rst,
    
    //input interface
    input wire data_in_valid,
    input wire [23:0] data_in,
    output reg fft_ready,
    
    //output interface
    output reg data_out_valid,
    output reg [23:0] data_out,
    
    //status
    output wire done,
    output wire error
);

    //internal signals
    reg [ADDR_WIDTH-1:0] wr_addr, rd_addr;
    reg wr_en;
    wire [23:0] rd_data;
    wire fft_done;
    
    //bit reversal
    wire [ADDR_WIDTH-1:0] wr_addr_reversed;
    bit_reverse #(
        .MAX_N(MAX_N),
        .WIDTH(ADDR_WIDTH)
    ) bit_rev (
        .in(wr_addr),
        .out(wr_addr_reversed)
    );
    
    //state machine
    localparam MEM_IDLE = 2'd0;
    localparam MEM_WRITE = 2'd1;
    localparam MEM_PROCESS = 2'd2;
    localparam MEM_READ = 2'd3;
    
    reg [1:0] mem_state, mem_next_state;
    reg [ADDR_WIDTH-1:0] input_count, output_count;
    reg fft_start, fft_start_issued;
    reg ext_reading;
    reg read_bank_sel;
    
    wire [2:0] num_stages = $clog2(MAX_N);
    wire core_bank_sel = (mem_state == MEM_READ) ? read_bank_sel :
                        (mem_state == MEM_WRITE || mem_state == MEM_IDLE) ? 1'b1 :
                        1'b0;
    
    //FFT core
    mixed_fft_8_core #(
        .MAX_N(MAX_N),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) fft_core (
        .clk(clk),
        .rst(rst),
        .start(fft_start),
        .N(MAX_N),
        .done(fft_done),
        .error(error),
        .ext_wr_en(wr_en),
        .ext_wr_addr(wr_addr_reversed),
        .ext_wr_data(data_in),
        .ext_bank_sel(core_bank_sel),
        .ext_rd_addr(rd_addr),
        .ext_reading(ext_reading),
        .rd_data_0(rd_data)
    );
    
    //state machine
    always @(*) begin
        mem_next_state = mem_state;
        case (mem_state)
            MEM_IDLE: if (data_in_valid) mem_next_state = MEM_WRITE;
            MEM_WRITE: if (input_count >= MAX_N) mem_next_state = MEM_PROCESS;
            MEM_PROCESS: if (fft_done) mem_next_state = MEM_READ;
            MEM_READ: if (output_count >= MAX_N) mem_next_state = MEM_IDLE;
        endcase
    end
    
    always @(posedge clk or negedge rst) begin
        if (!rst) begin
            mem_state <= MEM_IDLE;
            input_count <= 0;
            output_count <= 0;
            wr_en <= 0;
            wr_addr <= 0;
            rd_addr <= 0;
            fft_ready <= 1;
            data_out_valid <= 0;
            data_out <= 0;
            fft_start <= 0;
            fft_start_issued <= 0;
            read_bank_sel <= 0;
            ext_reading <= 0;
        end else begin
            mem_state <= mem_next_state;
            fft_start <= 0;
            
            case (mem_state)
                MEM_IDLE: begin
                    fft_ready <= 1;
                    input_count <= 0;
                    output_count <= 0;
                    data_out_valid <= 0;
                    fft_start_issued <= 0;
                    ext_reading <= 0;
                    
                    if (data_in_valid) begin
                        wr_en <= 1;
                        wr_addr <= 0;
                        input_count <= 1;
                        fft_ready <= 0;
                    end else begin
                        wr_en <= 0;
                    end
                end
                
                MEM_WRITE: begin
                    if (input_count < MAX_N && data_in_valid) begin
                        wr_en <= 1;
                        wr_addr <= input_count;
                        input_count <= input_count + 1;
                    end else if (input_count >= MAX_N) begin
                        wr_en <= 0;
                        if (!fft_start_issued) begin
                            fft_start <= 1;
                            fft_start_issued <= 1;
                        end
                    end else begin
                        wr_en <= 0;
                    end
                end
                
                MEM_PROCESS: begin
                    wr_en <= 0;
                    if (fft_done) begin
                        output_count <= 0;
                        read_bank_sel <= num_stages[0];
                        ext_reading <= 1;
                    end else begin
                        ext_reading <= 0;
                    end
                end
                
                MEM_READ: begin
                    ext_reading <= 1;
                    if (output_count == 0) begin
                        rd_addr <= 0;
                        data_out_valid <= 0;
                        output_count <= output_count + 1;
                    end else if (output_count <= MAX_N) begin
                        data_out <= rd_data;
                        data_out_valid <= 1;
                        rd_addr <= rd_addr + 1;
                        output_count <= output_count + 1;
                    end else begin
                        data_out_valid <= 0;
                        ext_reading <= 0;
                    end
                end
            endcase
        end
    end
    
    assign done = fft_done;

endmodule
