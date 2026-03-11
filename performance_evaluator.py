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
    def _generate_test_vectors(self):
        """
        Generate a small set of deterministic test vectors for easier debugging.
        All vectors have magnitude 1 and are well within the dynamic range of FP8/FP4.
        """
        n = self.fft_size
        test_vectors = []
    
        # 1. Impulse at index 0
        impulse = np.zeros(n, dtype=complex)
        impulse[0] = 1.0
        test_vectors.append(impulse)
    
        # 2. DC constant (all ones)
        dc = np.ones(n, dtype=complex)
        test_vectors.append(dc)
    
        # 3. Single frequency: e^(j*2π*1*n/N)  (k = 1)
        k = 1
        n_arr = np.arange(n)
        sinusoid = np.exp(2j * np.pi * k * n_arr / n)
        test_vectors.append(sinusoid)
    
        # Optionally add a few more, e.g., k = 2 or a random but controlled signal
        # For variety, we can also include a signal with both real and imag parts non‑zero.
        # Here we add k = 2 as a simple extra check.
        k2 = 2
        sinusoid2 = np.exp(2j * np.pi * k2 * n_arr / n)
        test_vectors.append(sinusoid2)
    
        return test_vectors

    def _compute_golden_outputs(self):
        return [np.fft.fft(v) for v in self.test_vectors]

    # ------------------------------------------------------------------
    # Float ↔ FP conversion helpers
    # ------------------------------------------------------------------
    def float_to_fp4(self, val):
        """
        Convert a float to FP4 E2M1 format.
        Returns a 4-bit unsigned integer (0-15).
        Format: [sign(1)][exp(2)][mant(1)]
        """
        if val == 0.0:
            return 0

        sign = 0x8 if val < 0 else 0x0
        val = abs(val)

        # Simplified mapping (adjust as needed for your actual FP4 definition)
        if val < 0.5:
            # Subnormal or zero
            exp = 0
            mant = 1 if val >= 0.25 else 0
        else:
            # Normal: 1.mant * 2^(exp-1)
            exp = 1
            if val < 1.0:
                exp = 1
                mant = 0
            elif val < 1.5:
                exp = 1
                mant = 1
            elif val < 2.0:
                exp = 2
                mant = 0
            elif val < 3.0:
                exp = 2
                mant = 1
            else:
                exp = 3
                mant = 1  # max

        return (sign & 0x8) | ((exp & 0x3) << 1) | (mant & 0x1)

    def float_to_fp8_e4m3(self, val):
        """Quantise a float to FP8 E4M3 and return the 8-bit integer code."""
        import math
        if val == 0.0:
            return 0

        sign_bit = 0x80 if val < 0 else 0x00
        val = abs(val)

        # Underflow to zero for very small values
        if val < 2**(-6):
            return sign_bit  # signed zero

        exp_unbiased = math.floor(math.log2(val))
        exp_biased   = exp_unbiased + 7  # bias = 7

        # Clamp exponent to valid range [1, 14] for normal numbers
        if exp_biased < 1:
            # Subnormal: exponent field = 0, mantissa = val / 2^(-6)
            exp_biased = 0
            mant = min(7, round(val / (2 ** -6) * 8))
        elif exp_biased >= 15:
            # Saturate to max normal (no infinity in E4M3)
            return sign_bit | 0x7E  # max positive normal: 0_1110_111
        else:
            mant_f = val / (2 ** exp_unbiased) - 1.0
            mant   = min(7, round(mant_f * 8))
            # Handle mantissa overflow
            if mant >= 8:
                mant = 0
                exp_biased += 1
                if exp_biased >= 15:
                    return sign_bit | 0x7E

        return (sign_bit & 0x80) | ((exp_biased & 0x0F) << 3) | (mant & 0x07)

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
        os.makedirs('./sim', exist_ok=True)
        lines = []
        for vec in self.test_vectors:
            for sample in vec:
                fp8_real = self.float_to_fp8_e4m3(sample.real) & 0xFF
                fp8_imag = self.float_to_fp8_e4m3(sample.imag) & 0xFF
                fp4_real = self.float_to_fp4(sample.real) & 0x0F
                fp4_imag = self.float_to_fp4(sample.imag) & 0x0F
                word_24bit = (fp8_real << 16) | (fp8_imag << 8) | (fp4_real << 4) | fp4_imag
                lines.append(f"{word_24bit:06x}")
        with open('./sim/test_vectors.hex', 'w') as f:
            f.write('\n'.join(lines))

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

        sim_dir = os.path.abspath('./sim')
        os.makedirs(sim_dir, exist_ok=True)

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

        vvp_path  = os.path.join(sim_dir, f'{design_name}.vvp')
        # Output file must use an absolute path so vvp finds it regardless of cwd
        out_file  = os.path.join(sim_dir, f'{design_name}_output.txt')

        compile_cmd = (
            ['iverilog',
             '-o', vvp_path,
             '-I', os.path.abspath(self.verilog_sources_dir),
             '-g2012',
             tb_file,
             verilog_file]
            + extra
            + lib_sources
        )

        try:
            result = subprocess.run(
                compile_cmd, capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"iverilog compile FAILED for {design_name}:\n"
                      f"  stdout: {result.stdout[-2000:]}\n"
                      f"  stderr: {result.stderr[-2000:]}")
                return None

            sim_result = subprocess.run(
                ['vvp', vvp_path],
                capture_output=True, text=True, timeout=120,
                cwd=os.path.abspath('.')   # keep cwd consistent
            )
            if sim_result.returncode != 0:
                print(f"vvp simulation FAILED for {design_name}:\n"
                      f"  stdout: {sim_result.stdout[-2000:]}\n"
                      f"  stderr: {sim_result.stderr[-2000:]}")
                return None

            # Print any simulation $display output for debugging
            if sim_result.stdout:
                for line in sim_result.stdout.splitlines():
                    if any(kw in line for kw in ('ERROR', 'WARN', 'stuck', 'watchdog')):
                        print(f"SIM [{design_name}]: {line}")

            return self._parse_simulation_output(out_file)

        except FileNotFoundError as e:
            print(f"Simulator binary not found for {design_name}: {e}\n"
                  f"  Ensure 'iverilog' and 'vvp' are on your PATH.")
            return None
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
        Generate a Verilog-2001 compatible testbench for the TOP module.

        Key fixes vs original:
          - All integer variables declared at module scope (no declarations
            inside named begin..end blocks -- that requires SystemVerilog).
          - Unbounded while(!fft_ready) replaced with cycle-counted loop.
          - Reset held for 8 cycles, 10-cycle settle before stimulus.
          - Watchdog scaled to fft_size * num_tests * num_stages * 2000 ns.
          - fwrite newline uses single \\n (correct Verilog escape).
          - Diagnostics: $display on reset release, fft_ready timeout, output count.
          - $fopen / $readmemh use absolute paths so vvp can be run from any cwd.
        """
        top_module    = f"{design_name}_top"
        num_tests     = len(self.test_vectors)
        total_samples = num_tests * self.fft_size
        # Memory reset loops over MAX_N=1024 entries: budget >=1024 cycles before ready.
        # Each butterfly op takes ~12 pipeline states; FFT-N has (N/2)*log2(N) butterflies.
        butterflies      = (self.fft_size // 2) * self.num_stages
        per_test_cycles  = self.fft_size + butterflies * 12 + self.fft_size + 200
        ready_timeout    = 1024 + per_test_cycles          # cycles to wait for fft_ready
        output_timeout   = self.fft_size * 20 + 200        # cycles to collect N outputs
        watchdog_ns      = (1024 + num_tests * per_test_cycles + 500) * 10  # 10ns/cycle

        sim_dir    = os.path.abspath('./sim')
        out_path   = os.path.join(sim_dir, f'{design_name}_output.txt').replace('\\', '/')
        tvec_path  = os.path.join(sim_dir, 'test_vectors.hex').replace('\\', '/')

        # Build testbench using .format() so {{ }} are plain Verilog braces.
        tb_template = (
        '`timescale 1ns/1ps\n'
        '\n'
        'module tb_{dn};\n'
        '\n'
        '    // DUT signals\n'
        '    reg         clk;\n'
        '    reg         rst;\n'
        '    reg         data_in_valid;\n'
        '    reg  [23:0] data_in;\n'
        '    wire        fft_ready;\n'
        '    wire        data_out_valid;\n'
        '    wire [23:0] data_out;\n'
        '    wire        done;\n'
        '    wire        error;\n'
        '\n'
        '    // Debug signals\n'
        '    reg [31:0] cycle_count;\n'
        '\n'
        '    // Test-vector storage\n'
        '    reg [23:0] tv_24bit [{ts_m1}:0];\n'
        '\n'
        '    // All integers at module scope\n'
        '    integer test_idx, sample_idx;\n'
        '    integer out_file;\n'
        '    integer received;\n'
        '    integer wait_cnt;\n'
        '\n'
        '    // DUT instantiation\n'
        '    {top_mod} #(\n'
        '        .MAX_N     (1024),\n'
        '        .ADDR_WIDTH(10)\n'
        '    ) dut (\n'
        '        .clk           (clk),\n'
        '        .rst           (rst),\n'
        '        .N             (10\'d{fft_sz}),\n'
        '        .data_in_valid (data_in_valid),\n'
        '        .data_in       (data_in),\n'
        '        .fft_ready     (fft_ready),\n'
        '        .data_out_valid(data_out_valid),\n'
        '        .data_out      (data_out),\n'
        '        .done          (done),\n'
        '        .error         (error)\n'
        '    );\n'
        '\n'
        '    initial clk = 0;\n'
        '    always  #5 clk = ~clk;\n'
        '\n'
        '    // Cycle counter for debugging\n'
        '    always @(posedge clk) begin\n'
        '        cycle_count <= cycle_count + 1;\n'
        '    end\n'
        '\n'
        '    initial begin : STIM\n'
        '        out_file = $fopen("{out_path}", "w");\n'
        '        $readmemh("{tvec_path}", tv_24bit);\n'
        '        rst           = 0;\n'
        '        data_in_valid = 0;\n'
        '        data_in       = 0;\n'
        '        cycle_count   = 0;\n'
        '        repeat(8) @(posedge clk);\n'
        '        rst = 1;\n'
        '        repeat(10) @(posedge clk);\n'
        '        $display("INFO [%s]: reset released at cycle %0d", "{dn}", cycle_count);\n'
        '\n'
        '        for (test_idx = 0; test_idx < {nt}; test_idx = test_idx + 1) begin\n'
        '            $display("INFO [%s]: starting test %0d at cycle %0d", "{dn}", test_idx, cycle_count);\n'
        '            wait_cnt = 0;\n'
        '            while (!fft_ready && wait_cnt < 12000) begin\n'
        '                @(posedge clk); wait_cnt = wait_cnt + 1;\n'
        '                if (wait_cnt % 1000 == 0)\n'
        '                    $display("DEBUG [%s]: waiting for fft_ready... cycle %0d, fft_ready=%%b", "{dn}", cycle_count, fft_ready);\n'
        '            end\n'
        '            if (!fft_ready) begin\n'
        '                $display("ERROR [%s]: fft_ready stuck low after %%0d cycles test %%0d", "{dn}", wait_cnt, test_idx);\n'
        '                $display("DEBUG [%s]: done=%%b, error=%%b", "{dn}", done, error);\n'
        '                $fclose(out_file); $finish;\n'
        '            end\n'
        '            $display("INFO [%s]: fft_ready asserted at cycle %0d", "{dn}", cycle_count);\n'
        '\n'
        '            for (sample_idx = 0; sample_idx < {fft_sz}; sample_idx = sample_idx + 1) begin\n'
        '                @(posedge clk);\n'
        '                data_in_valid = 1;\n'
        '                data_in = {{tv_24bit[test_idx*{fft_sz}+sample_idx]}};\n'
        '                if (sample_idx == 0)\n'
        '                    $display("INFO [%s]: first sample at cycle %0d: %%h", "{dn}", cycle_count, data_in);\n'
        '            end\n'
        '            @(posedge clk); data_in_valid = 0;\n'
        '            $display("INFO [%s]: finished feeding samples at cycle %0d", "{dn}", cycle_count);\n'
        '\n'
        '            received = 0; wait_cnt = 0;\n'
        '            while (received < {fft_sz} && wait_cnt < {otmo}) begin\n'
        '                @(posedge clk);\n'
        '                if (data_out_valid) begin\n'
        '                    $fwrite(out_file, "%%06h\\n", data_out);\n'
        '                    received = received + 1;\n'
        '                    if (received == 1)\n'
        '                        $display("INFO [%s]: first output at cycle %0d: %%h", "{dn}", cycle_count, data_out);\n'
        '                end\n'
        '                wait_cnt = wait_cnt + 1;\n'
        '            end\n'
        '            if (received < {fft_sz})\n'
        '                $display("WARN [%s]: got %%0d/%%0d outputs test %%0d", "{dn}", received, {fft_sz}, test_idx);\n'
        '            else\n'
        '                $display("INFO [%s]: test %%0d complete, got %%0d outputs at cycle %0d", "{dn}", test_idx, received, cycle_count);\n'
        '        end\n'
        '        $fclose(out_file);\n'
        '        $display("INFO [%s]: all tests complete at cycle %0d", "{dn}", cycle_count);\n'
        '        $finish;\n'
        '    end\n'
        '\n'
        '    initial begin\n'
        '        #{wdog};\n'
        '        $display("ERROR [%s]: watchdog! cycle count = %%0d", "{dn}", cycle_count);\n'
        '        $finish;\n'
        '    end\n'
        '\n'
        'endmodule\n'
        )

        tb_code = tb_template.format(
            dn       = design_name,
            top_mod  = top_module,
            fft_sz   = self.fft_size,
            n_stg    = self.num_stages,
            ts_m1    = total_samples - 1,
            nt       = num_tests,
            rtmo     = ready_timeout,
            otmo     = output_timeout,
            wdog     = watchdog_ns,
            lcb      = '{',
            rcb      = '}',
            out_path = out_path,
            tvec_path= tvec_path,
        )

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
        Each line is a 6-hex-digit 24-bit word in the unified format:
          [23:16] = FP8 real
          [15:8]  = FP8 imag
          [7:4]   = FP4 real
          [3:0]   = FP4 imag

        We determine whether the sample is FP8 or FP4 by checking whether
        the upper 16 bits are non-zero (FP8 result stored there) or zero
        (FP4-only result stored in [7:0]).  This mirrors how the core packs
        write-back data in WRITE_X / WRITE_Y.
        """
        outputs = []
        try:
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    word = int(line, 16) & 0xFFFFFF
                    fp8_real = (word >> 16) & 0xFF
                    fp8_imag = (word >>  8) & 0xFF
                    fp4_real = (word >>  4) & 0x0F
                    fp4_imag =  word        & 0x0F

                    # If the upper 16 bits are both zero the butterfly wrote
                    # an FP4 result (packed into [7:0]); otherwise it's FP8.
                    if fp8_real == 0 and fp8_imag == 0:
                        real_val = self.fp4_to_float(fp4_real)
                        imag_val = self.fp4_to_float(fp4_imag)
                    else:
                        real_val = self.fp8_to_float(fp8_real)
                        imag_val = self.fp8_to_float(fp8_imag)

                    outputs.append(real_val + 1j * imag_val)
        except FileNotFoundError:
            print(f"Simulation output file not found: {output_file}")
            return None
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