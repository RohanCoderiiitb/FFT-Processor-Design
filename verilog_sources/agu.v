module dit_fft_agu_variable #(
    parameter MAX_N = 1024,
    parameter ADDR_WIDTH = $clog2(MAX_N)
)(
    input clk,
    input reset,
    input wire start, // Clears AGU for back-to-back FFT runs
    input wire [ADDR_WIDTH-1:0] N, //runtime N value
    input wire next_step, //pulse from core to advance one butterfly

    output [ADDR_WIDTH-1:0] idx_a, //address for input A into butterfly unit
    output [ADDR_WIDTH-1:0] idx_b, //address for input B into butterfly unit
    output [ADDR_WIDTH-1:0] k, //twiddle factor index
    output reg done_stage, //goes high when one stage is finished, used to swap banks
    output reg done_fft, //goes high when fft is done (all stages)
    output reg [ADDR_WIDTH-1:0] curr_stage, //current stage (0 to log2(MAX_N)-1)

    // Note: The floating twiddle_output has been removed to avoid missing PRECISION port errors 
    // since the core module instantiates its own twiddle ROM.
    output [15:0] twiddle_output 
);

    // Provide a safe default for the floating output
    assign twiddle_output = 16'h0000;

    reg [ADDR_WIDTH-1:0] total_stages;
    
    // Robust stage calculation to prevent 32-bit shift underflow deadlock
    always @(*) begin
        case (N)
            1024: total_stages = 10;
            512:  total_stages = 9;
            256:  total_stages = 8;
            128:  total_stages = 7;
            64:   total_stages = 6;
            32:   total_stages = 5;
            16:   total_stages = 4;
            8:    total_stages = 3;
            4:    total_stages = 2;
            2:    total_stages = 1;
            default: total_stages = 0;
        endcase
    end

    //implementing decimation in time (DIT) algorithm
    reg [ADDR_WIDTH-1:0] group;      
    reg [ADDR_WIDTH-1:0] butterfly;  
    reg [ADDR_WIDTH-1:0] stride;     

    wire [ADDR_WIDTH:0] group_size = (stride << 1); 
    wire [ADDR_WIDTH-1:0] group_offset = group * group_size;

    assign idx_a = group_offset + butterfly;
    assign idx_b = idx_a + stride;

    wire [ADDR_WIDTH-1:0] k_idx = butterfly * (N / group_size);
    assign k = k_idx; 

    wire [ADDR_WIDTH-1:0] num_groups = N >> (curr_stage + 1); 

    always @(posedge clk or negedge reset) begin
        if (!reset) begin
            curr_stage <= 0;
            group <= 0;
            butterfly <= 0;
            stride <= 1; 
            done_fft <= 0;
            done_stage <= 0;
        end
        else if (start) begin // Clean slate for consecutive test vectors
            curr_stage <= 0;
            group <= 0;
            butterfly <= 0;
            stride <= 1; 
            done_fft <= 0;
            done_stage <= 0;
        end
        else if (next_step && !done_fft) begin 
            done_stage <= 0; 

            if (butterfly < stride - 1) begin
                butterfly <= butterfly + 1;
            end else begin
                butterfly <= 0;

                if (group < num_groups - 1) begin 
                    group <= group + 1; 
                end else begin
                    group <= 0;
                    done_stage <= 1; 

                    if (curr_stage < total_stages - 1) begin
                        curr_stage <= curr_stage + 1;
                        stride <= stride << 1; 
                    end else begin
                        done_fft <= 1; 
                    end
                end
            end
        end else begin 
            done_stage <= 0;
        end
    end
endmodule