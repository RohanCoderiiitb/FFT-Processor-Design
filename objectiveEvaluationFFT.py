"""
Objective Evaluation for Mixed-Precision FFT Optimization
Integrates Vivado synthesis and performance evaluation.

Key fix: each solution generates its own *core* Verilog file.
The TCL script receives BOTH the core file and the shared top file
so Vivado only synthesises those two files plus the base library —
it never incorrectly picks up a stale core from verilog_sources.
"""

import numpy as np
import subprocess
import os
import csv
import hashlib
from pymoo.core.problem import Problem
from concurrent.futures import ThreadPoolExecutor, as_completed
from globalVariablesMixedFFT import *
from fft_template_generator import FFTTemplateGenerator
from performance_evaluator import PerformanceEvaluator


class MixedPrecisionFFTProblem(Problem):
    """
    Multi-objective FFT optimisation problem for NSGA-II.

    Objectives  (all minimised):
        1. Power       (W)
        2. Area        (LUTs)
        3. Perf error  1/(SQNR+1) + MAE

    Constraints (≤0 → feasible):
        1. power  − MAX_POWER_W
        2. area   − MAX_AREA_LUTS
        3. MIN_SQNR_DB − SQNR
    """

    def __init__(self, fft_size=8, **kwargs):
        self.fft_size     = fft_size
        self.template_gen = FFTTemplateGenerator(fft_size)
        self.perf_eval    = PerformanceEvaluator(fft_size)

        chrom_length = self.template_gen.get_chromosome_length()

        super().__init__(
            n_var=chrom_length,
            n_obj=OBJECTIVES,
            n_ieq_constr=3,
            xl=[0] * chrom_length,
            xu=[1] * chrom_length,
            vtype=int,
            elementwise_evaluation=False,
            **kwargs
        )

        log_message(f"Initialized FFT-{fft_size} optimisation problem")
        log_message(f"Chromosome length : {chrom_length}")
        log_message(f"Number of stages  : {self.template_gen.num_stages}")
        log_message(f"Total butterflies : {self.template_gen.total_butterflies}")

    # ------------------------------------------------------------------
    def _evaluate(self, X, out, *args, **kwargs):
        global CURRENT_GEN

        log_message(f"=== Generation {CURRENT_GEN} ===", level='GEN')
        with open('generation.txt', 'w') as f:
            f.write(str(CURRENT_GEN))
        CURRENT_GEN += 1

        F = [None] * len(X)
        G = [None] * len(X)

        with ThreadPoolExecutor(max_workers=SOLUTION_THREADS) as executor:
            futures = {
                executor.submit(self.evaluate_solution, X[i], i): i
                for i in range(len(X))
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    f_vals, g_vals = future.result()
                    F[idx] = f_vals
                    G[idx] = g_vals
                except Exception as e:
                    log_message(f"Solution {idx} failed: {e}", level='ERROR')
                    F[idx] = [MAX_POWER_W * 2, MAX_AREA_LUTS * 2, 1e6]
                    G[idx] = [MAX_POWER_W, MAX_AREA_LUTS, -MIN_SQNR_DB]

        out["F"] = np.array(F)
        out["G"] = np.array(G)
        log_message(f"Generation {CURRENT_GEN-1} complete")

    # ------------------------------------------------------------------
    def evaluate_solution(self, chromosome, sol_id):
        """Evaluate a single chromosome; returns (objectives, constraints)."""
        log_message(f"Evaluating solution {sol_id}: {list(chromosome)}")

        chrom_hash = self._hash_chromosome(chromosome)
        if ENABLE_RESULT_CACHE and chrom_hash in RESULT_CACHE:
            log_message(f"Solution {sol_id} found in cache")
            return self._compute_objectives_and_constraints(RESULT_CACHE[chrom_hash])

        design_name = f"fft_{self.fft_size}_sol{sol_id}_gen{CURRENT_GEN}"

        # ── Step 1: generate per-solution Verilog ──────────────────────
        core_file = os.path.join(GENERATED_DESIGNS_DIR, f"{design_name}.v")
        core_file, top_file = self.template_gen.generate_verilog(chromosome, core_file)
        log_message(f"Generated Verilog core : {core_file}")
        log_message(f"Generated Verilog top  : {top_file}")

        # ── Step 2: Vivado synthesis ───────────────────────────────────
        power, area = self._run_vivado_synthesis(design_name, core_file, top_file)

        # ── Step 3: performance evaluation ────────────────────────────
        sqnr, mae = self._run_performance_evaluation(core_file, design_name)

        results = {'power': power, 'area': area, 'sqnr': sqnr, 'mae': mae}
        RESULT_CACHE[chrom_hash] = results
        self._save_solution_result(sol_id, chromosome, results)

        stats      = self.template_gen.analyze_chromosome_statistics(chromosome)
        num_stages = self.template_gen.num_stages
        log_message(
            f"Solution {sol_id}: Power={power:.4f}W, Area={area} LUTs, "
            f"SQNR={sqnr:.2f}dB, MAE={mae:.6f} | "
            f"FP8_mult={stats['fp8_mult']}/{num_stages} "
            f"({stats['fp8_mult']/num_stages*100:.1f}%), "
            f"FP8_add={stats['fp8_add']}/{num_stages} "
            f"({stats['fp8_add']/num_stages*100:.1f}%)"
        )

        return self._compute_objectives_and_constraints(results)

    # ------------------------------------------------------------------
    def _hash_chromosome(self, chromosome):
        return hashlib.md5(''.join(map(str, chromosome)).encode()).hexdigest()

    # ------------------------------------------------------------------
    def _run_vivado_synthesis(self, design_name, core_file, top_file):
        """
        Invoke Vivado in batch mode with the TCL template.

        tclargs order (must match vivado_synthesis.tcl):
            1  design_name
            2  csv_output
            3  clock_period
            4  core_file      ← per-solution generated core
            5  top_file       ← shared top for this FFT size
            6  verilog_dir    ← base library sources
        """
        log_message(f"Running Vivado synthesis for {design_name}")

        csv_output  = os.path.join(REPORTS_DIR, f"{design_name}_metrics.csv")
        verilog_dir = os.path.abspath(VERILOG_SOURCES_DIR)
        core_abs    = os.path.abspath(core_file)
        top_abs     = os.path.abspath(top_file)

        cmd = [
            VIVADO_PATH,
            '-mode',    'batch',
            '-source',  './vivado_synthesis.tcl',
            '-tclargs',
            design_name,
            csv_output,
            str(CLOCK_PERIOD),
            core_abs,
            top_abs,
            verilog_dir
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                # Log the actual error — previously stderr was swallowed silently
                err_snippet = (result.stderr or result.stdout or "no output")[-2000:]
                log_message(
                    f"Vivado failed for {design_name} (rc={result.returncode}):\n{err_snippet}",
                    level='ERROR'
                )
                return MAX_POWER_W * 2, MAX_AREA_LUTS * 2
            return self._parse_vivado_metrics(csv_output)

        except subprocess.TimeoutExpired:
            log_message(f"Vivado timeout for {design_name}", level='ERROR')
            return MAX_POWER_W * 2, MAX_AREA_LUTS * 2
        except Exception as e:
            log_message(f"Vivado error for {design_name}: {e}", level='ERROR')
            return MAX_POWER_W * 2, MAX_AREA_LUTS * 2

    # ------------------------------------------------------------------
    def _parse_vivado_metrics(self, csv_file):
        power = MAX_POWER_W * 2
        area  = MAX_AREA_LUTS * 2
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['Metric'] == 'total_power_w':
                        power = float(row['Value'])
                    elif row['Metric'] == 'lut_count':
                        area = int(row['Value'])
        except Exception as e:
            log_message(f"Error parsing Vivado metrics from {csv_file}: {e}", level='ERROR')
        return power, area

    # ------------------------------------------------------------------
    def _run_performance_evaluation(self, verilog_file, design_name):
        log_message(f"Running performance evaluation for {design_name}")
        try:
            return self.perf_eval.evaluate_design(verilog_file, design_name)
        except Exception as e:
            log_message(
                f"Performance evaluation failed for {design_name}: {e}",
                level='ERROR'
            )
            return -100.0, 1e6

    # ------------------------------------------------------------------
    def _compute_objectives_and_constraints(self, results):
        power = results['power']
        area  = results['area']
        sqnr  = results['sqnr']
        mae   = results['mae']

        sqnr_clamped      = max(sqnr, 0.0)
        performance_error = (1.0 / (sqnr_clamped + 1.0)) + mae

        objectives = [
            power * WEIGHT_POWER,
            area  * WEIGHT_AREA,
            performance_error * WEIGHT_PERFORMANCE
        ]
        constraints = [
            power - MAX_POWER_W,
            area  - MAX_AREA_LUTS,
            MIN_SQNR_DB - sqnr
        ]
        return objectives, constraints

    # ------------------------------------------------------------------
    def _save_solution_result(self, sol_id, chromosome, results):
        result_file = os.path.join(RESULTS_DIR, f"gen{CURRENT_GEN}_sol{sol_id}.txt")
        stats      = self.template_gen.analyze_chromosome_statistics(chromosome)
        num_stages = self.template_gen.num_stages

        with open(result_file, 'w') as f:
            f.write(f"FFT Size          : {self.fft_size}\n")
            f.write(f"Generation        : {CURRENT_GEN}\n")
            f.write(f"Solution ID       : {sol_id}\n")
            f.write(f"Num Stages        : {num_stages}\n")
            f.write(f"Chromosome Length : {len(chromosome)}\n")
            f.write(f"Chromosome        : {list(chromosome)}\n")
            f.write(f"\nResults:\n")
            f.write(f"  Power  : {results['power']:.6f} W\n")
            f.write(f"  Area   : {results['area']} LUTs\n")
            f.write(f"  SQNR   : {results['sqnr']:.2f} dB\n")
            f.write(f"  MAE    : {results['mae']:.6f}\n")
            f.write(f"\nOverall Precision Distribution:\n")
            f.write(f"  FP4 Multipliers: {stats['fp4_mult']} ({stats['fp4_mult']/num_stages*100:.1f}%)\n")
            f.write(f"  FP8 Multipliers: {stats['fp8_mult']} ({stats['fp8_mult']/num_stages*100:.1f}%)\n")
            f.write(f"  FP4 Adders     : {stats['fp4_add']} ({stats['fp4_add']/num_stages*100:.1f}%)\n")
            f.write(f"  FP8 Adders     : {stats['fp8_add']} ({stats['fp8_add']/num_stages*100:.1f}%)\n")
            f.write(f"\nPer-Stage Breakdown:\n")
            f.write(f"{'Stage':<8} {'FP4 Mult':<12} {'FP8 Mult':<12} {'FP4 Add':<12} {'FP8 Add':<12}\n")
            f.write('-' * 60 + '\n')
            for ss in stats['stage_stats']:
                f.write(
                    f"{ss['stage']:<8} {ss['fp4_mult']:<12} {ss['fp8_mult']:<12} "
                    f"{ss['fp4_add']:<12} {ss['fp8_add']:<12}\n"
                )


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------
def test_problem():
    problem = MixedPrecisionFFTProblem(fft_size=8)
    test_chromosome = np.array([0, 0, 1, 0, 1, 1])
    print(f"Testing with chromosome: {test_chromosome}")
    objectives, constraints = problem.evaluate_solution(test_chromosome, 0)
    print(f"Objectives  : {objectives}")
    print(f"Constraints : {constraints}")


if __name__ == "__main__":
    test_problem()