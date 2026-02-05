module dit_fft_agu_variable #(
    parameter MAX_N = 32,
    parameter ADDR_WIDTH = $clog2(MAX_N)
)(
    input clk,
    input reset,
    input wire [ADDR_WIDTH:0] N, //runtime N value
    input wire next_step, //pulse from core to advance one butterfly

    output [ADDR_WIDTH-1:0] idx_a, //address for input A into butterfly unit
    output [ADDR_WIDTH-1:0] idx_b, //address for input B into butterfly unit
    output [ADDR_WIDTH-1:0] k, //twiddle factor index
    output reg done_stage, //goes high when one stage is finished, used to swap banks
    output reg done_fft, //goes high when fft is done (all stages)
    output reg [2:0] curr_stage, //current stage (0 to 4 for N=32)

    output [7:0] twiddle_output //output for twiddle ROM
);

    //calculate number of stages based on N
    //we do this combinationally since N is fixed during FFT execution
    reg [2:0] total_stages;
    always @(*) begin
        case(N)
            6'd4:  total_stages = 3'd2;
            6'd8:  total_stages = 3'd3;
            6'd16: total_stages = 3'd4;
            6'd32: total_stages = 3'd5;
            default: total_stages = 3'd0; //invalid
        endcase
    end

    //implementing decimation in time (DIT) algorithm
    reg [ADDR_WIDTH-1:0] group;      //tracks which block we are in
    reg [ADDR_WIDTH-1:0] butterfly;  //pair index inside the current block
    reg [ADDR_WIDTH-1:0] stride;     //DIT: starts at 1, goes 1->2->4->8->16

    //address calculation:
    //stride = distance b/w butterfly legs
    //groups have a group offset = stride * 2 between them
    wire [ADDR_WIDTH:0] group_size = (stride << 1); //stride * 2
    wire [ADDR_WIDTH-1:0] group_offset = group * group_size;

    assign idx_a = group_offset + butterfly;
    assign idx_b = idx_a + stride;

    //twiddle logic:
    //DIT twiddle depends on the stage
    //k_factor scales the loop counter 'butterfly' to the full N range
    //k = butterfly * (N / (2 * stride))
    wire [ADDR_WIDTH-1:0] k_idx = butterfly * (N / group_size);

    assign k = k_idx; //assign internal wire to output port

    twiddle_factor #(
        .MAX_N(MAX_N),
        .ADDR_WIDTH(ADDR_WIDTH)
    ) tw_rom (
        .k(k_idx),
        .n(N), //use runtime N value
        .twiddle_out(twiddle_output)
    );

    //calculate number of groups for current stage
    //num_groups = N / group_size = N / (stride * 2)
    wire [ADDR_WIDTH-1:0] num_groups = N >> (curr_stage + 1); //divide by 2^(stage+1)

    //fsm:
    //two nested loops, inner one for butterfly operation and outer one for group
    //we want one butterfly operation for every element of the stride
    //the group loop - once a small group is finished, it moves to the next block in the memory
    //every stage doubles the stride
    always @(posedge clk or negedge reset) begin
        if (!reset) begin
            curr_stage <= 0;
            group <= 0;
            butterfly <= 0;
            stride <= 1; //DIT starts with a distance of 1
            done_fft <= 0;
            done_stage <= 0;
        end
        else if (next_step && !done_fft) begin //if next step pulses high and fft is not done
            done_stage <= 0; //default low

            //1. butterfly loop (innermost)
            //need to iterate from 0 to stride-1, so check butterfly < stride-1 before incrementing
            if (butterfly < stride - 1) begin
                butterfly <= butterfly + 1;
            end else begin
                //end of butterflies in this group, reset butterfly counter
                butterfly <= 0;

                //2. group loop
                //now we increment the group
                if (group < num_groups - 1) begin //if group index < total groups
                    group <= group + 1; //advance to next group
                end else begin
                    //end of stage, reset group
                    group <= 0;
                    done_stage <= 1; //pulse done_stage for bank swap

                    //3. stage loop
                    //if all groups in this stage have been exhausted, advance to the next stage 
                    if (curr_stage < total_stages - 1) begin
                        //every stage, the group size and hence stride double
                        curr_stage <= curr_stage + 1;
                        stride <= stride << 1; //double stride by left shifting
                    end else begin
                        done_fft <= 1; //all stages finished
                    end
                end
            end
        end else begin 
            done_stage <= 0;
        end
    end
endmodule