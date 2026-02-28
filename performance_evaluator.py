"""
Performance Evaluation Module
Calculates SQNR and MAE by comparing approximate FFT output with golden reference.

Fixes vs original:
  - iverilog glob: './verilog_sources/*.v' was passed as a literal string to
    subprocess (no shell expansion). Now expanded with Python glob.
  - Testbench instantiates the TOP module (e.g. fft_8_sol0_gen1_top) using its
    actual port interface, not a phantom design_name module with wrong ports.
  - Vivado stderr is now captured and logged so failures aren't silent.
  - rst polarity fixed: core uses active-low reset (negedge rst), so testbench
    must drive rst=0 to hold reset, then rst=1 to release.
  - Test vectors written to file before simulation; readmemh uses fp8 hex.
"""

import numpy as np
import subprocess
import os
import glob as glob_module
import struct


class PerformanceEvaluator:
    def __init__(self, fft_size):
        self.fft_size = fft_size
        self.verilog_sources_dir = './verilog_sources'
        self.test_vectors   = self._generate_test_vectors()
        self.golden_outputs = self._compute_golden_outputs()

    # ------------------------------------------------------------------
    # Test vector generation
    # ------------------------------------------------------------------
    def _generate_test_vectors(self, num_vectors=10):
        """Generate test input vectors (kept small for simulation speed)."""
        np.random.seed(42)
        test_vectors = []

        for _ in range(num_vectors):
            real = np.random.randn(self.fft_size)
            imag = np.random.randn(self.fft_size)
            test_vectors.append(real + 1j * imag)

        # DC
        test_vectors.append(np.ones(self.fft_size) + 0j)
        # Single frequency
        test_vectors.append(np.exp(2j * np.pi * np.arange(self.fft_size) / self.fft_size))
        # Impulse
        imp = np.zeros(self.fft_size, dtype=complex)
        imp[0] = 1.0
        test_vectors.append(imp)

        return test_vectors

    def _compute_golden_outputs(self):
        return [np.fft.fft(v) for v in self.test_vectors]

    # ------------------------------------------------------------------
    # Float ↔ FP conversion helpers
    # ------------------------------------------------------------------
    def float_to_fp8_e4m3(self, val):
        """Quantise a float to FP8 E4M3 and return the 8-bit integer code."""
        if val == 0.0:
            return 0
        sign = 1 if val < 0 else 0
        val = abs(val)
        # Find exponent
        import math
        exp_unbiased = math.floor(math.log2(val)) if val >= 1.0 else math.floor(math.log2(val))
        exp_biased = exp_unbiased + 7          # bias = 7
        exp_biased = max(1, min(14, exp_biased))  # clamp to normal range
        mant_f = val / (2 ** (exp_biased - 7)) - 1.0
        mant = min(7, round(mant_f * 8))       # 3-bit mantissa
        return (sign << 7) | (exp_biased << 3) | mant

    def fp8_to_float(self, fp8_val):
        """FP8 E4M3 → float."""
        if fp8_val == 0:
            return 0.0
        sign = (fp8_val >> 7) & 0x1
        exp  = (fp8_val >> 3) & 0xF
        mant =  fp8_val       & 0x7
        if exp == 0:
            value = mant / 8.0
        elif exp == 15:
            return float('inf') if mant == 0 else float('nan')
        else:
            value = (1.0 + mant / 8.0) * (2 ** (exp - 7))
        return -value if sign else value

    def fp4_to_float(self, fp4_val):
        """FP4 E2M1 → float."""
        if fp4_val == 0:
            return 0.0
        sign = (fp4_val >> 3) & 0x1
        exp  = (fp4_val >> 1) & 0x3
        mant =  fp4_val       & 0x1
        if exp == 0:
            value = mant * 0.5
        else:
            value = (1.0 + mant * 0.5) * (2 ** (exp - 1))
        return -value if sign else value

    # ------------------------------------------------------------------
    # Test-vector file writer
    # ------------------------------------------------------------------
    def _write_test_vectors(self):
        """
        Write all test vectors as hex FP8 values into ./sim/test_vectors_real.hex
        and ./sim/test_vectors_imag.hex (one entry per line, N lines per test).
        """
        os.makedirs('./sim', exist_ok=True)
        real_lines = []
        imag_lines = []
        for vec in self.test_vectors:
            for sample in vec:
                real_lines.append(f"{self.float_to_fp8_e4m3(sample.real):02x}")
                imag_lines.append(f"{self.float_to_fp8_e4m3(sample.imag):02x}")
        with open('./sim/test_vectors_real.hex', 'w') as f:
            f.write('\n'.join(real_lines))
        with open('./sim/test_vectors_imag.hex', 'w') as f:
            f.write('\n'.join(imag_lines))

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def run_verilog_simulation(self, verilog_file, design_name):
        """
        Compile and simulate the generated FFT design with iverilog/vvp.
        Returns array of complex outputs, or None on failure.
        """
        self._write_test_vectors()
        tb_file = self._generate_testbench(verilog_file, design_name)

        os.makedirs('./sim', exist_ok=True)

        # Expand the glob NOW in Python — subprocess does NOT expand globs
        lib_sources = sorted(glob_module.glob(
            os.path.join(self.verilog_sources_dir, '*.v')
        ))

        if not lib_sources:
            print(f"ERROR: No .v files found in {self.verilog_sources_dir}")
            return None

        # Top file lives next to the core file
        top_file = verilog_file.replace('.v', '_top.v')
        extra = [top_file] if os.path.exists(top_file) else []

        compile_cmd = (
            ['iverilog',
             '-o', f'./sim/{design_name}.vvp',
             '-I', self.verilog_sources_dir,
             '-g2012',            # SystemVerilog/Verilog-2012 mode
             tb_file,
             verilog_file]        # core
            + extra               # top (if present)
            + lib_sources         # fully-expanded library files
        )

        try:
            result = subprocess.run(
                compile_cmd, capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"iverilog compile failed for {design_name}:\n"
                      f"  stdout: {result.stdout}\n"
                      f"  stderr: {result.stderr}")
                return None

            sim_result = subprocess.run(
                ['vvp', f'./sim/{design_name}.vvp'],
                capture_output=True, text=True, timeout=120
            )
            if sim_result.returncode != 0:
                print(f"vvp simulation failed for {design_name}:\n"
                      f"  {sim_result.stderr}")
                return None

            return self._parse_simulation_output(f'./sim/{design_name}_output.txt')

        except subprocess.TimeoutExpired:
            print(f"Simulation timeout for {design_name}")
            return None
        except Exception as e:
            print(f"Simulation error for {design_name}: {e}")
            return None

    # ------------------------------------------------------------------
    # Testbench generator
    # ------------------------------------------------------------------
    def _generate_testbench(self, dut_file, design_name):
        """
        Generate a testbench that instantiates the TOP module.

        Top module ports (from _generate_top):
            clk, rst, data_in_valid, data_in [23:0],
            fft_ready, data_out_valid, data_out [23:0], done, error

        Input samples are packed as 24-bit unified format:
            [23:16] FP8 real   [15:8] FP8 imag   [7:4] FP4 real   [3:0] FP4 imag
        We fill FP8 fields from our quantised test vectors; FP4 fields = 0.
        """
        top_module = f"{design_name}_top"
        num_tests  = len(self.test_vectors)
        total_samples = num_tests * self.fft_size

        tb_code = f"""\
`timescale 1ns/1ps

module tb_{design_name};

    // ----------------------------------------------------------------
    // DUT signals
    // ----------------------------------------------------------------
    reg         clk;
    reg         rst;
    reg         data_in_valid;
    reg  [23:0] data_in;
    wire        fft_ready;
    wire        data_out_valid;
    wire [23:0] data_out;
    wire        done;
    wire        error;

    // ----------------------------------------------------------------
    // Test-vector storage
    // ----------------------------------------------------------------
    reg [7:0] tv_real [{total_samples-1}:0];
    reg [7:0] tv_imag [{total_samples-1}:0];

    integer i, test_idx, sample_idx;
    integer out_file;
    integer sent, received;

    // ----------------------------------------------------------------
    // DUT instantiation
    // ----------------------------------------------------------------
    {top_module} #(
        .MAX_N     ({self.fft_size}),
        .ADDR_WIDTH({self.num_stages})
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

    // ----------------------------------------------------------------
    // Clock
    // ----------------------------------------------------------------
    initial clk = 0;
    always  #5 clk = ~clk;

    // ----------------------------------------------------------------
    // Stimulus
    // ----------------------------------------------------------------
    initial begin : STIM
        out_file = $fopen("./sim/{design_name}_output.txt", "w");

        // Load test vectors
        $readmemh("./sim/test_vectors_real.hex", tv_real);
        $readmemh("./sim/test_vectors_imag.hex", tv_imag);

        // Active-low reset: assert rst=0, then release rst=1
        rst           = 0;
        data_in_valid = 0;
        data_in       = 0;
        repeat(4) @(posedge clk);
        rst = 1;
        repeat(2) @(posedge clk);

        // ---- Run each test vector ----
        for (test_idx = 0; test_idx < {num_tests}; test_idx = test_idx + 1) begin

            // Wait for FFT to be ready
            while (!fft_ready) @(posedge clk);

            // Feed N samples
            for (sample_idx = 0; sample_idx < {self.fft_size}; sample_idx = sample_idx + 1) begin
                @(posedge clk);
                data_in_valid = 1;
                // Pack: [23:16]=FP8_real [15:8]=FP8_imag [7:0]=0 (FP4 unused)
                data_in = {{tv_real[test_idx*{self.fft_size} + sample_idx],
                           tv_imag[test_idx*{self.fft_size} + sample_idx],
                           8'h00}};
            end
            @(posedge clk);
            data_in_valid = 0;

            // Collect N output samples
            received = 0;
            while (received < {self.fft_size}) begin
                @(posedge clk);
                if (data_out_valid) begin
                    $fwrite(out_file, "%06h\\n", data_out);
                    received = received + 1;
                end
            end
        end

        $fclose(out_file);
        $display("Simulation complete: %0d tests run", {num_tests});
        $finish;
    end

    // ----------------------------------------------------------------
    // Timeout watchdog
    // ----------------------------------------------------------------
    initial begin
        #({self.fft_size * num_tests * 200});
        $display("ERROR: Simulation timeout for {design_name}!");
        $finish;
    end

endmodule
"""
        tb_file = f'./sim/tb_{design_name}.v'
        os.makedirs('./sim', exist_ok=True)
        with open(tb_file, 'w') as f:
            f.write(tb_code)
        return tb_file

    @property
    def num_stages(self):
        import math
        return int(math.log2(self.fft_size))

    # ------------------------------------------------------------------
    # Output parser
    # ------------------------------------------------------------------
    def _parse_simulation_output(self, output_file):
        """
        Parse simulation output.
        Each line is a 6-hex-digit 24-bit word: [23:16]=FP8_real [15:8]=FP8_imag
        """
        outputs = []
        try:
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    word = int(line, 16) & 0xFFFFFF
                    real_fp8 = (word >> 16) & 0xFF
                    imag_fp8 = (word >>  8) & 0xFF
                    outputs.append(self.fp8_to_float(real_fp8)
                                   + 1j * self.fp8_to_float(imag_fp8))
        except Exception as e:
            print(f"Error parsing simulation output {output_file}: {e}")
            return None

        return np.array(outputs) if outputs else None

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    def calculate_sqnr(self, golden, approximate):
        signal_power = np.mean(np.abs(golden) ** 2)
        noise_power  = np.mean(np.abs(golden - approximate) ** 2)
        if noise_power == 0:
            return float('inf')
        return 10 * np.log10(signal_power / noise_power)

    def calculate_mean_error(self, golden, approximate):
        return float(np.mean(np.abs(golden - approximate)))

    # ------------------------------------------------------------------
    # Top-level entry point
    # ------------------------------------------------------------------
    def evaluate_design(self, verilog_file, design_name):
        """
        Run simulation and return (avg_sqnr_dB, avg_mae).
        """
        sim_outputs = self.run_verilog_simulation(verilog_file, design_name)

        if sim_outputs is None or len(sim_outputs) == 0:
            return -100.0, 1e6

        num_tests   = len(self.test_vectors)
        total_sqnr  = 0.0
        total_mae   = 0.0
        valid_tests = 0

        for i in range(min(num_tests, len(sim_outputs) // self.fft_size)):
            start = i * self.fft_size
            approx  = sim_outputs[start : start + self.fft_size]
            golden  = self.golden_outputs[i]

            sqnr = self.calculate_sqnr(golden, approx)
            mae  = self.calculate_mean_error(golden, approx)

            if not (np.isinf(sqnr) or np.isnan(sqnr)):
                total_sqnr += sqnr
                total_mae  += mae
                valid_tests += 1

        if valid_tests == 0:
            return -100.0, 1e6

        return total_sqnr / valid_tests, total_mae / valid_tests


# ---------------------------------------------------------------------------
def test_evaluator():
    evaluator = PerformanceEvaluator(fft_size=8)
    print(f"Test vectors : {len(evaluator.test_vectors)}")
    print(f"FFT size     : {evaluator.fft_size}")
    print(f"FP4 0b0101   → {evaluator.fp4_to_float(0b0101):.4f}  (expect 1.5)")
    print(f"FP8 0b01000011 → {evaluator.fp8_to_float(0b01000011):.4f}")


if __name__ == "__main__":
    test_evaluator()