module fp4_add_sub(
    //module for addition and subtraction of two FP4 numbers
    //format: [sign][exp:2bits][mantissa:1bit]
    //normal numbers: value = (-1)^sign × 1.mantissa × 2^(exp-1)
    input [3:0] a,
    input [3:0] b,
    input sub, //sub=0 for addition, sub=1 for subtraction
    output [3:0] out
);

    //unpack the input numbers into sign, exponent, mantissa
    wire sign_a = a[3];
    wire [1:0] exp_a = a[2:1];
    wire mant_a = a[0];
    wire sign_b = b[3];
    wire [1:0] exp_b = b[2:1];
    wire mant_b = b[0];
    
    //if we're subtracting, flip the sign of b
    //this turns subtraction into addition with opposite sign
    wire sign_b_eff = sub ? ~sign_b : sign_b;
    
    //figure out which number has larger magnitude
    //compare exponents first, then mantissas if exponents are equal
    wire a_larger = (exp_a > exp_b) || 
                    ((exp_a == exp_b) && (mant_a >= mant_b));
    
    //assign larger and smaller numbers
    //we always align the smaller to the larger
    wire sign_l = a_larger ? sign_a : sign_b_eff;
    wire [1:0] exp_l = a_larger ? exp_a : exp_b;
    wire mant_l = a_larger ? mant_a : mant_b;
    wire sign_s = a_larger ? sign_b_eff : sign_a;
    wire [1:0] exp_s = a_larger ? exp_b : exp_a;
    wire mant_s = a_larger ? mant_b : mant_a;
    
    //calculate how much we need to shift the smaller number
    wire [1:0] exp_diff = exp_l - exp_s;
    
    //add the hidden bit to both mantissas
    //for normal numbers (exp != 00), the full value is 1.mantissa (the '1' is implicit)
    //for subnormal numbers (exp == 00), the full value is 0.mantissa (the '1' becomes '0')
    //so we create a 3-bit value: [overflow_bit][hidden_bit][mantissa_bit]
    wire hidden_l = (exp_l != 2'b00);  //hidden bit is 1 for normal, 0 for subnormal
    wire hidden_s = (exp_s != 2'b00);
    wire [2:0] sig_l = {1'b0, hidden_l, mant_l};
    wire [2:0] sig_s_unaligned = {1'b0, hidden_s, mant_s};
    
    //align the smaller number by shifting it right based on exponent difference
    //if exp_diff=0, no shift needed
    //if exp_diff=1, shift right by 1 position
    //if exp_diff=2, shift right by 2 positions
    //if exp_diff>=3, number becomes too small, treat as zero
    wire [2:0] sig_s = (exp_diff == 2'd0) ? sig_s_unaligned :
                       (exp_diff == 2'd1) ? {1'b0, sig_s_unaligned[2:1]} :
                       (exp_diff == 2'd2) ? {2'b00, sig_s_unaligned[2]} :
                       3'b000;
    
    //determine if we need to add or subtract based on signs
    //if signs are different, we subtract, otherwise we add
    wire do_sub = (sign_l != sign_s);
    
    //perform the actual addition or subtraction
    //result can be up to 4 bits if overflow happens
    wire [3:0] sig_result_raw = do_sub ? 
                                (sig_l - sig_s) : 
                                (sig_l + sig_s);
    
    //normalize the result so the hidden bit is always 1 for normal numbers
    //the 3-bit sig value has binary point between bit[1] and bit[0]
    //so it represents: [overflow].[hidden][mantissa]
    //we need to shift and adjust exponent so result is always 1.x for normals
    //for subnormals (exp=00), we keep 0.x format
    reg [1:0] exp_norm;
    reg [2:0] sig_norm;
    reg sign_out;
    
    always @(*) begin
        //result sign is same as larger operand
        sign_out = sign_l;
        
        //case 1: bit 3 set, result >= 8.0 (11.xx or higher in fixed-point)
        //this means we overflowed by a lot, shift right by 2
        if (sig_result_raw[3]) begin
            sig_norm = {1'b0, sig_result_raw[3:2]};  //shift right by 2
            exp_norm = exp_l + 2'd2;                  //increment exponent by 2
        end
        //case 2: bit 2 set, result is 4.0-7.99 (10.xx in fixed-point)
        //this means we overflowed by 1, shift right by 1
        else if (sig_result_raw[2]) begin
            sig_norm = {1'b0, sig_result_raw[2:1]};  //shift right by 1
            exp_norm = exp_l + 2'd1;                  //increment exponent by 1
        end
        //case 3: bit 1 set, result is 2.0-3.99 (01.xx in fixed-point)
        //this is already normalized (hidden bit is 1), no shift needed
        else if (sig_result_raw[1]) begin
            sig_norm = {1'b0, sig_result_raw[1:0]};  //take as is
            //special case: if we started with subnormal (exp_l=00) and got normalized result
            //we need to bump up to exp=01 (smallest normal exponent)
            if (exp_l == 2'b00) begin
                exp_norm = 2'b01;  //transition from subnormal to normal
            end else begin
                exp_norm = exp_l;  //exponent stays same
            end
        end
        //case 4: only bit 0 set, result is 1.0-1.99 (00.1x in fixed-point)
        //this needs normalization for normal numbers, but might be subnormal
        else if (sig_result_raw[0]) begin
            if (exp_l == 2'b01) begin
                //shifting left would make exp=00, so result is subnormal
                //keep as is: 00.1x becomes subnormal 0.1x at exp=00
                sig_norm = {1'b0, sig_result_raw[1:0]};  //keep as 00.1x
                exp_norm = 2'b00;                         //subnormal exponent
            end else begin
                //can normalize: shift left and decrement exponent
                sig_norm = {sig_result_raw[0], 2'b00};   //shift left: 00.1x -> 10.0x
                exp_norm = exp_l - 2'd1;
            end
        end
        //case 5: result is exactly zero
        else begin
            sig_norm = 3'b000;
            exp_norm = 2'b00;
            sign_out = 1'b0;  //zero is always positive
        end
    end
    
    //extract the mantissa bit (the LSB after the hidden bit)
    wire mant_out = sig_norm[0];
    
    //handle special cases: zero, infinity, underflow
    reg [3:0] result;
    always @(*) begin
        //if normalized result is zero, output zero
        if (sig_norm == 3'b000) begin
            result = 4'b0000;
        end
        //if exponent overflows (exp=11 and mant=1), output infinity
        else if (exp_norm[1] && exp_norm[0] && mant_out) begin
            result = {sign_out, 2'b11, 1'b1};
        end
        //if exponent underflows to zero, flush result to zero
        else if (exp_norm == 2'b00) begin
            result = 4'b0000;
        end
        //normal case: pack sign, exponent, and mantissa
        else begin
            result = {sign_out, exp_norm, mant_out};
        end
    end
    
    assign out = result;

endmodule

module fp4_complex_add_sub(
    input [7:0] a,
    input [7:0] b,
    input sub, //sub=0 for addition, sub=1 for subtraction
    output [7:0] out
);
    //split real and imaginary parts
    wire [3:0] a_real = a[7:4];
    wire [3:0] a_imag = a[3:0];
    wire [3:0] b_real = b[7:4];
    wire [3:0] b_imag = b[3:0];
    
    //instantiate two fp4 adders for real and imaginary parts
    wire [3:0] out_real;
    wire [3:0] out_imag;
    
    fp4_add_sub adder_real (
        .a(a_real),
        .b(b_real),
        .sub(sub),
        .out(out_real)
    );
    
    fp4_add_sub adder_imag (
        .a(a_imag),
        .b(b_imag),
        .sub(sub),
        .out(out_imag)
    );
    
    //combine results back into 8-bit complex number
    assign out = {out_real, out_imag};

endmodule

module fp8_add_sub(
    //module for addition and subtraction of two FP8 E5M2 numbers
    //format: [sign][exp:5bits][mantissa:2bits]
    //normal numbers: value = (-1)^sign × 1.mantissa × 2^(exp-15)
    //bias = 15
    input [7:0] a,
    input [7:0] b,
    input sub, //sub=0 for addition, sub=1 for subtraction
    output [7:0] out
);
    
    //unpack numbers
    wire sign_a = a[7];
    wire [4:0] exp_a = a[6:2];
    wire [1:0] mant_a = a[1:0];
    
    wire sign_b = b[7];
    wire [4:0] exp_b = b[6:2];
    wire [1:0] mant_b = b[1:0];

    //if we're subtracting, flip the sign of b
    //this turns subtraction into addition with opposite sign
    wire sign_b_eff = sub ? ~sign_b : sign_b;

    //figure out which number has larger magnitude
    //compare exponents first, then mantissas if exponents are equal
    wire a_larger = (exp_a > exp_b) || 
                    ((exp_a == exp_b) && (mant_a >= mant_b));

    //assign larger and smaller numbers
    //we always align the smaller to the larger
    wire sign_l = a_larger ? sign_a : sign_b_eff;
    wire [4:0] exp_l = a_larger ? exp_a : exp_b;
    wire [1:0] mant_l = a_larger ? mant_a : mant_b;
    wire sign_s = a_larger ? sign_b_eff : sign_a;
    wire [4:0] exp_s = a_larger ? exp_b : exp_a;
    wire [1:0] mant_s = a_larger ? mant_b : mant_a;
    
    //calculate how much we need to shift the smaller number
    wire [4:0] exp_diff = exp_l - exp_s;

    //add the hidden bit to both mantissas
    //for normal numbers (exp != 00000), the full value is 1.mantissa (the '1' is implicit)
    //for subnormal numbers (exp == 00000), the full value is 0.mantissa (the '1' becomes '0')
    //so we create a 5-bit value: [overflow_bits][hidden_bit][mantissa_bits]
    wire hidden_l = (exp_l != 5'b00000);  //hidden bit is 1 for normal, 0 for subnormal
    wire hidden_s = (exp_s != 5'b00000);
    wire [4:0] sig_l = {2'b00, hidden_l, mant_l};
    wire [4:0] sig_s_unaligned = {2'b00, hidden_s, mant_s};
    
    //align the smaller number by shifting it right based on exponent difference
    //if exp_diff=0, no shift needed
    //if exp_diff=1, shift right by 1 position
    //if exp_diff=2, shift right by 2 positions
    //if exp_diff=3, shift right by 3 positions
    //if exp_diff=4, shift right by 4 positions
    //if exp_diff>=5, number becomes too small, treat as zero
    wire [4:0] sig_s;
    assign sig_s = (exp_diff == 5'd0) ? sig_s_unaligned :
                   (exp_diff == 5'd1) ? {1'b0, sig_s_unaligned[4:1]} :
                   (exp_diff == 5'd2) ? {2'b00, sig_s_unaligned[4:2]} :
                   (exp_diff == 5'd3) ? {3'b000, sig_s_unaligned[4:3]} :
                   (exp_diff == 5'd4) ? {4'b0000, sig_s_unaligned[4]} :
                   5'b00000;
    
    //determine if we need to add or subtract based on signs
    //if signs are different, we subtract, otherwise we add
    wire do_sub = (sign_l != sign_s);
    
    //perform the actual addition or subtraction
    //result can be up to 6 bits if overflow happens
    wire [5:0] sig_result_raw = do_sub ? 
                                ({1'b0, sig_l} - {1'b0, sig_s}) : 
                                ({1'b0, sig_l} + {1'b0, sig_s});
    
    //normalize the result so the hidden bit is always 1 for normal numbers
    //the 5-bit sig value has binary point between bit[2] and bit[1]
    //so it represents: [overflow_bits].[hidden][mantissa]
    //we need to shift and adjust exponent so result is always 1.xx for normals
    //for subnormals (exp=00000), we keep 0.xx format
    reg [4:0] exp_norm;
    reg [4:0] sig_norm;
    reg sign_out;
    
    always @(*) begin
        //result sign is same as larger operand
        sign_out = sign_l;
        
        //case 1: bit 5 set, result >= 32.0 (100.xxx in fixed-point)
        //this means we overflowed by a lot, shift right by 3
        if (sig_result_raw[5]) begin
            sig_norm = {2'b00, sig_result_raw[5:3]};  //shift right by 3
            exp_norm = exp_l + 5'd3;                  //increment exponent by 3
        end
        //case 2: bit 4 set, result is 16.0-31.99 (010.xxx in fixed-point)
        //this means we overflowed by 2, shift right by 2
        else if (sig_result_raw[4]) begin
            sig_norm = {2'b00, sig_result_raw[4:2]};  //shift right by 2
            exp_norm = exp_l + 5'd2;                  //increment exponent by 2
        end
        //case 3: bit 3 set, result is 8.0-15.99 (001.xxx in fixed-point)
        //this means we overflowed by 1, shift right by 1
        else if (sig_result_raw[3]) begin
            sig_norm = {2'b00, sig_result_raw[3:1]};  //shift right by 1
            exp_norm = exp_l + 5'd1;                  //increment exponent by 1
        end
        //case 4: bit 2 set, result is 4.0-7.99 (0001.xx in fixed-point)
        //this is already normalized (hidden bit is 1), no shift needed
        else if (sig_result_raw[2]) begin
            sig_norm = {2'b00, sig_result_raw[2:0]};  //take as is
            //special case: if we started with subnormal (exp_l=00000) and got normalized result
            //we need to bump up to exp=00001 (smallest normal exponent)
            if (exp_l == 5'b00000) begin
                exp_norm = 5'b00001;  //transition from subnormal to normal
            end else begin
                exp_norm = exp_l;  //exponent stays same
            end
        end
        //case 5: bit 1 set, result is 2.0-3.99 (00001.x in fixed-point)
        //this needs normalization for normal numbers, but might be subnormal
        else if (sig_result_raw[1]) begin
            if (exp_l == 5'b00001) begin
                //shifting left would make exp=00000, so result is subnormal
                //keep as is: 00001.x becomes subnormal 0.0001x at exp=00000
                sig_norm = {2'b00, sig_result_raw[2:0]};  //keep as is
                exp_norm = 5'b00000;                      //subnormal exponent
            end else if (exp_l == 5'b00000) begin
                //already subnormal, keep as is
                sig_norm = {2'b00, sig_result_raw[2:0]};
                exp_norm = 5'b00000;
            end else begin
                //can normalize: shift left by 1 and decrement exponent
                sig_norm = {1'b0, sig_result_raw[1:0], 2'b00};  //shift left: 00001.x -> 0001x.00
                exp_norm = exp_l - 5'd1;
            end
        end
        //case 6: bit 0 set, result is 1.0-1.99 (000001.0 in fixed-point)
        //this needs normalization by shifting left by 2
        else if (sig_result_raw[0]) begin
            if (exp_l <= 5'b00010) begin
                //shifting left by 2 would make exp<=00000, so result is subnormal or underflows
                sig_norm = {2'b00, sig_result_raw[2:0]};
                exp_norm = 5'b00000;  //subnormal exponent
            end else begin
                //can normalize: shift left by 2 and decrement exponent by 2
                sig_norm = {sig_result_raw[0], 4'b0000};  //shift left: 000001 -> 100000
                exp_norm = exp_l - 5'd2;
            end
        end
        //case 7: result is exactly zero
        else begin
            sig_norm = 5'b00000;
            exp_norm = 5'b00000;
            sign_out = 1'b0;  //zero is always positive
        end
    end
    
    //extract the mantissa bits (the 2 LSBs after the hidden bit)
    wire [1:0] mant_out = sig_norm[1:0];
    
    //handle special cases: zero, infinity, underflow
    reg [7:0] result;
    always @(*) begin
        //if normalized result is zero, output zero
        if (sig_norm == 5'b00000) begin
            result = 8'b00000000;
        end
        //if exponent overflows (exp >= 31), output infinity
        else if (exp_norm >= 5'd31) begin
            result = {sign_out, 5'b11111, 2'b00};  //infinity
        end
        //normal case: pack sign, exponent, and mantissa
        else begin
            result = {sign_out, exp_norm, mant_out};
        end
    end
    
    assign out = result;

endmodule

module fp8_complex_add_sub(
    input [15:0] a,
    input [15:0] b,
    input sub, //sub=0 for addition, sub=1 for subtraction
    output [15:0] out
);
    //split real and imaginary parts
    wire [7:0] a_real = a[15:8];
    wire [7:0] a_imag = a[7:0];
    wire [7:0] b_real = b[15:8];
    wire [7:0] b_imag = b[7:0];
    
    //instantiate two fp8 adders for real and imaginary parts
    wire [7:0] out_real;
    wire [7:0] out_imag;
    
    fp8_add_sub adder_real (
        .a(a_real),
        .b(b_real),
        .sub(sub),
        .out(out_real)
    );
    
    fp8_add_sub adder_imag (
        .a(a_imag),
        .b(b_imag),
        .sub(sub),
        .out(out_imag)
    );
    
    //combine results back into 16-bit complex number
    assign out = {out_real, out_imag};
endmodule
