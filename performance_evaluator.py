"""
Performance Evaluation Module
==============================
Calculates SQNR and MAE by running iverilog/vvp simulation of generated
mixed-precision FFT designs and comparing against an FP32 NumPy reference.

Testbench interface matches the generated top module:
  - load_en / load_addr / load_data   (input loading, FP8 16-bit)
  - start / done                      (FFT trigger / completion)
  - unload_en / unload_addr / unload_data (result readout, 16-bit)

This mirrors fft_test.v / tb_fft_test.v exactly.

Key design decisions
--------------------
* Active-low async reset: tb drives rst=0 for reset, rst=1 to release.
* 2-cycle memory read latency: unload loop waits 3 @posedge per sample
  (address issued → 2 register stages → data stable).
* Input packed as FP8: load_data = {fp8_real[7:0], fp8_imag[7:0]}.
* Output parsed as FP8 from unload_data[15:0].
* One twiddles file is generated per simulation run in ./sim/.
"""

import numpy as np
import subprocess
import os
import glob as glob_module
import math


class PerformanceEvaluator:
    def __init__(self, fft_size):
        self.fft_size          = fft_size
        self.num_stages        = int(math.log2(fft_size))
        self.verilog_sources_dir = './verilog_sources'
        self.test_vectors      = self._generate_test_vectors()
        self.golden_outputs    = self._compute_golden_outputs()

    # ==================================================================
    # Test vectors
    # ==================================================================
    def _generate_test_vectors(self):
        n     = self.fft_size
        n_arr = np.arange(n)
        vecs  = []

        # 1. Impulse at index 0  → FFT = all-ones
        v = np.zeros(n, dtype=complex); v[0] = 1.0
        vecs.append(v)

        # 2. DC constant (all ones) → FFT = N at bin 0, else 0
        vecs.append(np.ones(n, dtype=complex))

        # 3. Single frequency k=1
        vecs.append(np.exp(2j * np.pi * 1 * n_arr / n))

        # 4. Single frequency k=2
        vecs.append(np.exp(2j * np.pi * 2 * n_arr / n))

        return vecs

    def _compute_golden_outputs(self):
        return [np.fft.fft(v) for v in self.test_vectors]

    # ==================================================================
    # Float ↔ FP conversion helpers
    # ==================================================================
    def float_to_fp8_e4m3(self, val):
        """Quantise a float to FP8 E4M3 (bias=7); returns 8-bit integer."""
        if val == 0.0:
            return 0
        sign_bit = 0x80 if val < 0 else 0x00
        val = abs(val)
        if val < 2 ** (-6):
            return sign_bit
        exp_u = math.floor(math.log2(val))
        exp_b = exp_u + 7
        if exp_b < 1:
            exp_b = 0
            mant  = min(7, round(val / (2 ** -6) * 8))
        elif exp_b >= 15:
            return sign_bit | 0x7E
        else:
            mant_f = val / (2 ** exp_u) - 1.0
            mant   = min(7, round(mant_f * 8))
            if mant >= 8:
                mant = 0
                exp_b += 1
                if exp_b >= 15:
                    return sign_bit | 0x7E
        return (sign_bit & 0x80) | ((exp_b & 0x0F) << 3) | (mant & 0x07)

    def fp8_to_float(self, fp8_val):
        """FP8 E4M3 (bias=7) → float."""
        fp8_val &= 0xFF
        if fp8_val == 0:
            return 0.0
        sign = (fp8_val >> 7) & 0x1
        exp  = (fp8_val >> 3) & 0xF
        mant =  fp8_val       & 0x7
        if exp == 0:
            value = mant / 8.0 * (2 ** -6)
        elif exp == 15:
            return float('nan')
        else:
            value = (1.0 + mant / 8.0) * (2 ** (exp - 7))
        return -value if sign else value

    def float_to_fp4(self, val):
        """Quantise a float to FP4 E2M1 (bias=1); returns 4-bit integer."""
        if val == 0.0:
            return 0
        sign = 0x8 if val < 0 else 0x0
        val  = abs(val)
        if val < 0.5:
            exp = 0; mant = 1 if val >= 0.25 else 0
        elif val < 1.0:
            exp = 1; mant = 0
        elif val < 1.5:
            exp = 1; mant = 1
        elif val < 2.0:
            exp = 2; mant = 0
        elif val < 3.0:
            exp = 2; mant = 1
        else:
            exp = 3; mant = 1
        return (sign & 0x8) | ((exp & 0x3) << 1) | (mant & 0x1)

    def fp4_to_float(self, fp4_val):
        """FP4 E2M1 (bias=1) → float."""
        fp4_val &= 0xF
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

    # ==================================================================
    # Twiddle file generator
    # ==================================================================
    def _write_twiddle_file(self, sim_dir):
        """
        Write twiddles_1024.txt in binary format for $readmemb.
        Format per line: 24 binary digits  (MSB first)
          [23:16] FP8 real
          [15:8]  FP8 imag
          [7:4]   FP4 real
          [3:0]   FP4 imag
        Only the first 512 entries are used (symmetry handles the rest).
        """
        path = os.path.join(sim_dir, 'twiddles_1024.txt')
        with open(path, 'w') as f:
            for idx in range(512):
                angle = -2.0 * math.pi * idx / 1024.0
                re    = math.cos(angle)
                im    = math.sin(angle)

                fp8_re = self.float_to_fp8_e4m3(re) & 0xFF
                fp8_im = self.float_to_fp8_e4m3(im) & 0xFF
                fp4_re = self.float_to_fp4(re)       & 0x0F
                fp4_im = self.float_to_fp4(im)       & 0x0F

                word = (fp8_re << 16) | (fp8_im << 8) | (fp4_re << 4) | fp4_im
                f.write(f"{word:024b}\n")
        return path

    # ==================================================================
    # Test-vector file writer  (for reference; not used by this TB)
    # ==================================================================
    def _write_test_vectors_hex(self, sim_dir):
        path = os.path.join(sim_dir, 'test_vectors.hex')
        with open(path, 'w') as f:
            for vec in self.test_vectors:
                for sample in vec:
                    fp8_re = self.float_to_fp8_e4m3(sample.real) & 0xFF
                    fp8_im = self.float_to_fp8_e4m3(sample.imag) & 0xFF
                    f.write(f"{fp8_re:02x}{fp8_im:02x}\n")
        return path

    # ==================================================================
    # Testbench generator
    # ==================================================================
    def _generate_testbench(self, dut_file, design_name):
        design_name = self._sanitize_name(design_name)
        """
        Generate a Verilog-2001 compatible testbench that exercises the
        generated TOP module using the same interface as tb_fft_test.v:

            load_en / load_addr / load_data
            start / done
            unload_en / unload_addr / unload_data

        Outputs FP8 hex pairs (real, imag) one per line to sim/<dn>_output.txt.
        """
        n          = self.fft_size
        addr_bits  = int(math.log2(n))
        num_tests  = len(self.test_vectors)
        top_module = f"{design_name}_top"

        # Timing budgets
        butterflies     = (n // 2) * self.num_stages
        cycles_per_fft  = n + butterflies * 10 + n * 4 + 200
        ready_timeout   = 1024 + cycles_per_fft   # wait-for-done budget
        unload_cycles   = n * 5                    # 3 cycles latency + margin
        watchdog_ns     = (1024 + num_tests * (cycles_per_fft + n * 5) + 1000) * 10

        sim_dir  = os.path.abspath('./sim')
        out_path = os.path.join(sim_dir, f'{design_name}_output.txt').replace('\\', '/')

        # Build per-test input load lines and expected-output comments
        # Encode all test vectors as Verilog parameter arrays
        vec_hex_lines = []
        for ti, vec in enumerate(self.test_vectors):
            for si, sample in enumerate(vec):
                fp8_re = self.float_to_fp8_e4m3(sample.real) & 0xFF
                fp8_im = self.float_to_fp8_e4m3(sample.imag) & 0xFF
                word   = (fp8_re << 8) | fp8_im
                vec_hex_lines.append(f"        tv[{ti*n + si}] = 16'h{word:04x};")
        vec_init = '\n'.join(vec_hex_lines)

        tb = f"""\
// Auto-generated testbench for {top_module}
// Mirrors tb_fft_test.v interface exactly.
`timescale 1ns/1ps

module tb_{design_name};

    reg        clk;
    reg        rst;
    reg        start;
    wire       done;

    reg        load_en;
    reg  [{addr_bits-1}:0]  load_addr;
    reg  [15:0] load_data;

    reg        unload_en;
    reg  [{addr_bits-1}:0]  unload_addr;
    wire [15:0] unload_data;

    integer i, ti, out_file;

    // Test vector storage: fp8 packed {{real[7:0], imag[7:0]}}
    reg [15:0] tv [{num_tests*n - 1}:0];

    // DUT
    {top_module} dut (
        .clk        (clk),
        .rst        (rst),
        .start      (start),
        .done       (done),
        .load_en    (load_en),
        .load_addr  (load_addr),
        .load_data  (load_data),
        .unload_en  (unload_en),
        .unload_addr(unload_addr),
        .unload_data(unload_data)
    );

    // 100 MHz clock
    initial clk = 0;
    always  #5 clk = ~clk;

    // Watchdog
    initial begin
        #{watchdog_ns};
        $display("WATCHDOG TIMEOUT for {design_name}");
        $finish;
    end

    initial begin : STIM
        integer wait_cnt;

        // Pre-load test vectors
{vec_init}

        // Open output file
        out_file = $fopen("{out_path}", "w");

        // Initialise signals
        rst        = 0;
        start      = 0;
        load_en    = 0;
        load_addr  = 0;
        load_data  = 0;
        unload_en  = 0;
        unload_addr= 0;

        // Hold reset for 8 cycles then release
        repeat(8) @(posedge clk);
        rst = 1;
        repeat(4) @(posedge clk);

        // Run each test vector
        for (ti = 0; ti < {num_tests}; ti = ti + 1) begin

            // --- Load phase ---
            @(posedge clk);
            load_en = 1;
            for (i = 0; i < {n}; i = i + 1) begin
                load_addr = i[{addr_bits-1}:0];
                load_data = tv[ti*{n} + i];
                @(posedge clk);
            end
            load_en = 0;

            @(posedge clk);

            // --- Run FFT ---
            start = 1;
            @(posedge clk);
            start = 0;

            // Wait for done
            wait_cnt = 0;
            while (!done && wait_cnt < {ready_timeout}) begin
                @(posedge clk);
                wait_cnt = wait_cnt + 1;
            end
            if (!done)
                $display("WARN: done never asserted for test %0d, design {design_name}", ti);

            @(posedge clk);

            // --- Unload phase ---
            // Memory has 2-cycle read latency.
            // For each sample: assert address, wait 3 posedge clk, sample data.
            unload_en = 1;
            for (i = 0; i < {n}; i = i + 1) begin
                unload_addr = i[{addr_bits-1}:0];
                @(posedge clk);
                @(posedge clk);
                @(posedge clk);
                $fwrite(out_file, "%04h\\n", unload_data);
            end
            unload_en = 0;

            @(posedge clk);
            @(posedge clk);

        end // for ti

        $fclose(out_file);
        $display("Simulation complete for {design_name}. Results in {out_path}");
        $finish;
    end

endmodule
"""
        tb_file = f'./sim/tb_{design_name}.v'
        os.makedirs('./sim', exist_ok=True)
        with open(tb_file, 'w') as f:
            f.write(tb)
        return tb_file

    # ==================================================================
    # Simulation runner
    # ==================================================================
    @staticmethod
    def _sanitize_name(name):
        """Replace characters invalid in Verilog identifiers."""
        import re
        return re.sub(r'[^A-Za-z0-9_]', '_', name)

    def run_verilog_simulation(self, verilog_file, design_name):
        design_name = self._sanitize_name(design_name)
        """
        Compile with iverilog and simulate with vvp.
        verilog_file  = path to the *core* .v file
        The matching *_top.v must sit in the same directory.
        Returns list of complex outputs, or None on failure.
        """
        sim_dir = os.path.abspath('./sim')
        os.makedirs(sim_dir, exist_ok=True)

        # Write twiddle ROM file into sim dir so $readmemb finds it
        self._write_twiddle_file(sim_dir)

        tb_file = self._generate_testbench(verilog_file, design_name)

        # Expand glob for RTL library sources.
        # Exclude fft_test.v and tb_fft_test.v — these are reference designs
        # with conflicting module names, not library primitives.
        _exclude = {'fft_test.v', 'tb_fft_test.v'}
        lib_sources = sorted(
            f for f in glob_module.glob(
                os.path.join(self.verilog_sources_dir, '*.v')
            )
            if os.path.basename(f) not in _exclude
        )
        if not lib_sources:
            print(f"ERROR: No .v files found in {self.verilog_sources_dir}")
            return None

        # Top file lives next to the core file
        top_file = verilog_file.replace('.v', '_top.v')
        extra    = [top_file] if os.path.exists(top_file) else []

        vvp_path = os.path.join(sim_dir, f'{design_name}.vvp')

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
            result = subprocess.run(compile_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"iverilog FAILED for {design_name}:\n"
                      f"  stdout: {result.stdout[-3000:]}\n"
                      f"  stderr: {result.stderr[-3000:]}")
                return None

            sim_result = subprocess.run(
                ['vvp', vvp_path],
                capture_output=True, text=True,
                timeout=300,
                cwd=sim_dir   # run from sim dir so $fopen relative paths work
            )
            if sim_result.returncode != 0:
                print(f"vvp FAILED for {design_name}:\n"
                      f"  stdout: {sim_result.stdout[-3000:]}\n"
                      f"  stderr: {sim_result.stderr[-3000:]}")
                return None

            # Print notable simulation messages
            for line in sim_result.stdout.splitlines():
                if any(kw in line for kw in ('ERROR', 'WARN', 'WATCHDOG', 'TIMEOUT')):
                    print(f"SIM [{design_name}]: {line}")

            return self._parse_simulation_output(
                os.path.join(sim_dir, f'{design_name}_output.txt')
            )

        except FileNotFoundError as e:
            print(f"Simulator not found: {e}\n  Ensure iverilog/vvp are on PATH.")
            return None
        except subprocess.TimeoutExpired:
            print(f"Simulation timeout for {design_name}")
            return None
        except Exception as e:
            print(f"Simulation error for {design_name}: {e}")
            return None

    # ==================================================================
    # Output parser
    # ==================================================================
    def _parse_simulation_output(self, output_file):
        """
        Parse 4-hex-digit lines written by the testbench.
        Each line is: {fp8_real[7:0], fp8_imag[7:0]}  (16-bit = 4 hex chars).
        """
        outputs = []
        try:
            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    word     = int(line, 16) & 0xFFFF
                    fp8_real = (word >> 8) & 0xFF
                    fp8_imag =  word       & 0xFF
                    outputs.append(
                        self.fp8_to_float(fp8_real) + 1j * self.fp8_to_float(fp8_imag)
                    )
        except FileNotFoundError:
            print(f"Simulation output file not found: {output_file}")
            return None
        except Exception as e:
            print(f"Error parsing {output_file}: {e}")
            return None
        return np.array(outputs) if outputs else None

    # ==================================================================
    # Metrics
    # ==================================================================
    def calculate_sqnr(self, golden, approximate):
        sig_power   = np.mean(np.abs(golden) ** 2)
        noise_power = np.mean(np.abs(golden - approximate) ** 2)
        if noise_power == 0:
            return float('inf')
        return 10 * np.log10(sig_power / noise_power)

    def calculate_mean_error(self, golden, approximate):
        return float(np.mean(np.abs(golden - approximate)))

    # ==================================================================
    # Top-level entry point
    # ==================================================================
    def evaluate_design(self, verilog_file, design_name):
        """
        Run simulation and return (avg_sqnr_dB, avg_mae).
        On failure returns (-100.0, 1e6).
        """
        design_name = self._sanitize_name(design_name)
        sim_outputs = self.run_verilog_simulation(verilog_file, design_name)
        if sim_outputs is None or len(sim_outputs) == 0:
            return -100.0, 1e6

        n          = self.fft_size
        num_tests  = len(self.test_vectors)
        total_sqnr = 0.0
        total_mae  = 0.0
        valid      = 0

        for i in range(min(num_tests, len(sim_outputs) // n)):
            approx = sim_outputs[i * n : (i + 1) * n]
            golden = self.golden_outputs[i]

            sqnr = self.calculate_sqnr(golden, approx)
            mae  = self.calculate_mean_error(golden, approx)

            if not (math.isinf(sqnr) or math.isnan(sqnr)):
                total_sqnr += sqnr
                total_mae  += mae
                valid      += 1

        if valid == 0:
            return -100.0, 1e6
        return total_sqnr / valid, total_mae / valid


# =============================================================================
# Quick smoke-test
# =============================================================================
def test_evaluator():
    ev = PerformanceEvaluator(fft_size=8)
    print(f"Test vectors : {len(ev.test_vectors)}")
    print(f"FFT size     : {ev.fft_size}")
    print(f"FP4 0b0101   → {ev.fp4_to_float(0b0101):.4f}  (expect 1.5)")
    print(f"FP8 0b01000011 → {ev.fp8_to_float(0b01000011):.6f}  (expect ~1.375)")
    print(f"FP8(1.0) encode → 0x{ev.float_to_fp8_e4m3(1.0):02x}  (expect 0x38)")
    print(f"FP8(0.0) encode → 0x{ev.float_to_fp8_e4m3(0.0):02x}  (expect 0x00)")


if __name__ == "__main__":
    test_evaluator()