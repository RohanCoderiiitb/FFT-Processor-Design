"""
Performance Evaluation Module
Calculates SQNR (Signal-to-Quantization-Noise Ratio) and Mean Error
by comparing approximate FFT output with golden reference
"""

import numpy as np
import subprocess
import os
import struct


class PerformanceEvaluator:
    def __init__(self, fft_size):
        """
        Initialize performance evaluator
        Args:
            fft_size: FFT size (power of 2)
        """
        self.fft_size = fft_size
        self.test_vectors = self._generate_test_vectors()
        self.golden_outputs = self._compute_golden_outputs()
    
    def _generate_test_vectors(self, num_vectors=100):
        """Generate test input vectors for FFT"""
        np.random.seed(42)  # For reproducibility
        test_vectors = []
        
        # Generate diverse test cases
        for _ in range(num_vectors):
            # Random complex signal
            real = np.random.randn(self.fft_size)
            imag = np.random.randn(self.fft_size)
            test_vectors.append(real + 1j * imag)
        
        # Add specific test cases
        # 1. DC component
        dc_signal = np.ones(self.fft_size) + 0j
        test_vectors.append(dc_signal)
        
        # 2. Single frequency
        freq_signal = np.exp(2j * np.pi * np.arange(self.fft_size) / self.fft_size)
        test_vectors.append(freq_signal)
        
        # 3. Impulse
        impulse = np.zeros(self.fft_size, dtype=complex)
        impulse[0] = 1 + 0j
        test_vectors.append(impulse)
        
        return test_vectors
    
    def _compute_golden_outputs(self):
        """Compute golden reference FFT outputs using NumPy"""
        golden = []
        for vec in self.test_vectors:
            fft_result = np.fft.fft(vec)
            golden.append(fft_result)
        return golden
    
    def fp4_to_float(self, fp4_val):
        """
        Convert FP4 (E2M1) to floating point
        Format: [sign:1][exp:2][mant:1]
        """
        if fp4_val == 0:
            return 0.0
        
        sign = (fp4_val >> 3) & 0x1
        exp = (fp4_val >> 1) & 0x3
        mant = fp4_val & 0x1
        
        if exp == 0:
            # Subnormal
            value = 0.0 + mant * 0.5
        else:
            # Normal: value = 1.mantissa × 2^(exp-1)
            value = (1.0 + mant * 0.5) * (2 ** (exp - 1))
        
        return -value if sign else value
    
    def fp8_to_float(self, fp8_val):
        """
        Convert FP8 (E4M3) to floating point
        Format: [sign:1][exp:4][mant:3]
        """
        if fp8_val == 0:
            return 0.0
        
        sign = (fp8_val >> 7) & 0x1
        exp = (fp8_val >> 3) & 0xF
        mant = fp8_val & 0x7
        
        if exp == 0:
            # Subnormal
            value = 0.0 + mant / 8.0
        elif exp == 15:
            # Infinity/NaN
            return float('inf') if mant == 0 else float('nan')
        else:
            # Normal: value = 1.mantissa × 2^(exp-7)
            value = (1.0 + mant / 8.0) * (2 ** (exp - 7))
        
        return -value if sign else value
    
    def run_verilog_simulation(self, verilog_file, design_name):
        """
        Run Verilog simulation using Icarus Verilog or ModelSim
        Returns: List of FFT outputs for test vectors
        """
        # Create testbench
        tb_file = self._generate_testbench(verilog_file, design_name)
        
        # Compile and simulate using Icarus Verilog
        try:
            # Compile
            compile_cmd = [
                'iverilog',
                '-o', f'./sim/{design_name}.vvp',
                '-I', './verilog_sources',
                tb_file,
                verilog_file,
                './verilog_sources/*.v'
            ]
            subprocess.run(compile_cmd, check=True, capture_output=True)
            
            # Simulate
            sim_cmd = ['vvp', f'./sim/{design_name}.vvp']
            result = subprocess.run(sim_cmd, check=True, capture_output=True, text=True)
            
            # Parse output
            outputs = self._parse_simulation_output(f'./sim/{design_name}_output.txt')
            return outputs
            
        except subprocess.CalledProcessError as e:
            print(f"Simulation failed: {e}")
            return None
    
    def _generate_testbench(self, dut_file, design_name):
        """Generate Verilog testbench"""
        tb_code = f"""
`timescale 1ns/1ps

module tb_{design_name};
    reg clk;
    reg rst;
    reg start;
    reg [15:0] data_in_real [{self.fft_size-1}:0];
    reg [15:0] data_in_imag [{self.fft_size-1}:0];
    wire [15:0] data_out_real [{self.fft_size-1}:0];
    wire [15:0] data_out_imag [{self.fft_size-1}:0];
    wire done;
    
    integer i, test_num;
    integer out_file;
    
    // Instantiate DUT
    {design_name} dut (
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
        out_file = $fopen("./sim/{design_name}_output.txt", "w");
        
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
        for (i = 0; i < {self.fft_size}; i = i + 1) begin
            $fwrite(out_file, "%h %h\\n", data_out_real[i], data_out_imag[i]);
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
"""
        tb_file = f'./sim/tb_{design_name}.v'
        os.makedirs('./sim', exist_ok=True)
        with open(tb_file, 'w') as f:
            f.write(tb_code)
        return tb_file
    
    def _parse_simulation_output(self, output_file):
        """Parse simulation output file"""
        outputs = []
        try:
            with open(output_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 2:
                        real_hex = int(parts[0], 16)
                        imag_hex = int(parts[1], 16)
                        
                        # Convert to float based on precision (auto-detect)
                        real_val = self.fp8_to_float(real_hex & 0xFF)
                        imag_val = self.fp8_to_float(imag_hex & 0xFF)
                        
                        outputs.append(real_val + 1j * imag_val)
        except Exception as e:
            print(f"Error parsing output: {e}")
            return None
        
        return np.array(outputs) if outputs else None
    
    def calculate_sqnr(self, golden, approximate):
        """
        Calculate Signal-to-Quantization-Noise Ratio
        SQNR = 10 * log10(P_signal / P_noise)
        """
        signal_power = np.mean(np.abs(golden) ** 2)
        noise = golden - approximate
        noise_power = np.mean(np.abs(noise) ** 2)
        
        if noise_power == 0:
            return float('inf')
        
        sqnr_db = 10 * np.log10(signal_power / noise_power)
        return sqnr_db
    
    def calculate_mean_error(self, golden, approximate):
        """Calculate mean absolute error"""
        mae = np.mean(np.abs(golden - approximate))
        return mae
    
    def evaluate_design(self, verilog_file, design_name):
        """
        Evaluate a mixed-precision FFT design
        Returns: (SQNR, Mean Error)
        """
        # Run simulation to get outputs
        sim_outputs = self.run_verilog_simulation(verilog_file, design_name)
        
        if sim_outputs is None:
            # Simulation failed - return worst possible metrics
            return -100.0, 1e6
        
        # Reshape outputs to match test vectors
        num_tests = len(self.test_vectors)
        
        total_sqnr = 0.0
        total_mae = 0.0
        valid_tests = 0
        
        # Evaluate each test vector
        for i in range(min(num_tests, len(sim_outputs) // self.fft_size)):
            start_idx = i * self.fft_size
            end_idx = start_idx + self.fft_size
            
            approx_output = sim_outputs[start_idx:end_idx]
            golden_output = self.golden_outputs[i]
            
            sqnr = self.calculate_sqnr(golden_output, approx_output)
            mae = self.calculate_mean_error(golden_output, approx_output)
            
            if not np.isinf(sqnr) and not np.isnan(sqnr):
                total_sqnr += sqnr
                total_mae += mae
                valid_tests += 1
        
        if valid_tests == 0:
            return -100.0, 1e6
        
        avg_sqnr = total_sqnr / valid_tests
        avg_mae = total_mae / valid_tests
        
        return avg_sqnr, avg_mae


# Quick test function
def test_evaluator():
    evaluator = PerformanceEvaluator(fft_size=8)
    print(f"Generated {len(evaluator.test_vectors)} test vectors")
    print(f"FFT size: {evaluator.fft_size}")
    
    # Test FP conversion
    fp4_val = 0b0101  # Should be ~1.5
    print(f"FP4 0b0101 -> {evaluator.fp4_to_float(fp4_val)}")
    
    fp8_val = 0b01000011  # Test FP8 conversion
    print(f"FP8 0b01000011 -> {evaluator.fp8_to_float(fp8_val)}")


if __name__ == "__main__":
    test_evaluator()
