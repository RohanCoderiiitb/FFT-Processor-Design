import math

def float_to_fp8(val):
    """
    Custom FP8 (E4M3) encoding.
    Bias 7. 1 bit sign, 4 bits exponent, 3 bits mantissa.
    """
    if val == 0: return 0x00
    
    sign = 0x80 if val < 0 else 0x00
    val = abs(val)
    
    # Round very small numbers to zero
    if val < 0.01: return sign 
    
    exponent_unbiased = math.floor(math.log2(val))
    exponent_stored = exponent_unbiased + 7
    
    # Clamp exponent (0 to 15)
    if exponent_stored < 0: exponent_stored = 0
    if exponent_stored > 15: exponent_stored = 15
    
    # Mantissa (3 bits) -> normalize to 1.xxx
    mantissa_float = (val / (2**exponent_unbiased)) - 1.0
    mantissa_int = int(round(mantissa_float * 8)) 
    
    if mantissa_int == 8: # Handle rounding overflow to next exponent
        mantissa_int = 0
        exponent_stored += 1
        
    return sign | ((exponent_stored & 0x0F) << 3) | (mantissa_int & 0x07)

def float_to_fp4(val):
    """
    Custom FP4 (E2M1) encoding.
    Bias = 1. Format: [Sign(1b), Mag(3b)]
    """
    sign = 0x8 if val < 0 else 0x0
    val = abs(val)
    
    # Simple magnitude lookup based on 0.5 step increments
    if val < 0.25: mag = 0   # 0.0
    elif val < 0.75: mag = 1 # 0.5
    elif val < 1.25: mag = 2 # 1.0
    else: mag = 3            # 1.5
    
    return sign | mag

def generate_twiddles(filename="twiddles_1024.txt", n_points=1024):
    """
    Generates binary twiddle factors for FFT.
    Section 1: FP8 (8-bit Real, 8-bit Imag) = 16 bits total
    Section 2: FP4 (4-bit Real, 4-bit Padding, 4-bit Imag, 4-bit Padding) = 16 bits total
    """
    with open(filename, "w") as f:
        # --- FP8 SECTION ---
        # Format per line: RRRRRRRRIIIIIIII (16 bits)
        for k in range(n_points // 2):
            angle = -2 * math.pi * k / n_points
            real_part = math.cos(angle)
            imag_part = math.sin(angle)
            
            r_bin = float_to_fp8(real_part)
            i_bin = float_to_fp8(imag_part)
            
            line = f"{r_bin:08b}{i_bin:08b}"
            f.write(line + "\n")

        # --- FP4 SECTION ---
        # Format per line: RRRR0000IIII0000 (16 bits)
        # Bits [15:12]=Real, [11:8]=Pad, [7:4]=Imag, [3:0]=Pad
        for k in range(n_points // 2):
            angle = -2 * math.pi * k / n_points
            real_part = math.cos(angle)
            imag_part = math.sin(angle)
            
            r_val = float_to_fp4(real_part)
            i_val = float_to_fp4(imag_part)
            
            real_bits = f"{r_val:04b}"
            imag_bits = f"{i_val:04b}"
            padding   = "0000"
            
            line = f"{real_bits}{padding}{imag_bits}{padding}"
            f.write(line + "\n")
            
    print(f"File '{filename}' generated successfully.")
    print(f"Total lines: {n_points}")
    print(f"FP8 format: [Real_8b][Imag_8b]")
    print(f"FP4 format: [Real_4b][0000][Imag_4b][0000]")

if __name__ == "__main__":
    generate_twiddles()