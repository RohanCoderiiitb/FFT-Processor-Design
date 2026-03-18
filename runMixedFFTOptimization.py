"""
Main Script for Mixed-Precision FFT Optimization
Orchestrates the complete NSGA-II optimization flow with Vivado integration
"""

import numpy as np
import os
import shutil
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.operators.sampling.rnd import IntegerRandomSampling
from pymoo.termination import get_termination
from pymoo.optimize import minimize

from globalVariablesMixedFFT import *
from objectiveEvaluationFFT import MixedPrecisionFFTProblem
from optimizationUtils import (
    MyCallback,
    SmartInitialSampling,
    BlockwiseMutation,
    StagewiseCrossover
)


def setup_verilog_sources():
    """
    Copy Verilog source files to the working directory
    """
    log_message("Setting up Verilog source files")

    # Source files to copy
    source_files = [
        '../verilog_sources/adder.v',
        '../verilog_sources/multiplier.v',
        '../verilog_sources/mixed_precision_wrappers.v',
        '../verilog_sources/twiddle_rom.v',
        '../verilog_sources/agu.v',
        '../verilog_sources/memory.v'
    ]

    # Copy wrapper file from current directory
    wrapper_src = '../verilog_sources/mixed_precision_wrappers.v'
    wrapper_dst = os.path.join(VERILOG_SOURCES_DIR, 'mixed_precision_wrappers.v')
    if os.path.exists(wrapper_src):
        shutil.copy(wrapper_src, wrapper_dst)
        log_message("Copied wrapper file")


def run_optimization_for_fft_size(fft_size):
    """
    Run NSGA-II optimization for a specific FFT size

    Args:
        fft_size: FFT size (power of 2)

    Returns:
        result: Optimization result object
    """
    import globalVariablesMixedFFT
    globalVariablesMixedFFT.CURRENT_FFT_SIZE = fft_size

    log_message(f"\n{'='*60}")
    log_message(f"Starting optimization for {fft_size}-point FFT")
    log_message(f"{'='*60}\n")

    # Create problem instance
    problem = MixedPrecisionFFTProblem(fft_size=fft_size)

    # Create callback for tracking evolution
    callback = MyCallback()

    # Configure NSGA-II algorithm with structure-aware operators
    algorithm = NSGA2(
        pop_size=POPULATION,
        sampling=SmartInitialSampling(),
        crossover=StagewiseCrossover(fft_size=fft_size, prob=CROSSOVER_RATE),
        mutation=BlockwiseMutation(fft_size=fft_size)
    )

    # Define termination criterion
    termination = get_termination("n_gen", GENERATIONS)

    log_message(f"NSGA-II Configuration:")
    log_message(f"  Population size: {POPULATION}")
    log_message(f"  Generations: {GENERATIONS}")
    log_message(f"  Crossover rate: {CROSSOVER_RATE}")
    log_message(f"  Mutation rate: {MUTATION_RATE}")
    log_message(f"  Objectives: {OBJECTIVES}")
    log_message(f"  Parallel threads: {SOLUTION_THREADS}")

    # Run optimization
    log_message("Starting NSGA-II evolution...")
    result = minimize(
        problem,
        algorithm,
        termination,
        save_history=False,
        callback=callback,
        seed=SEED,
        verbose=VERBOSE
    )

    log_message(f"Optimization complete for {fft_size}-point FFT")

    # Save results
    save_optimization_results(result, callback, fft_size)

    return result


def _unscale_objectives(pareto_objectives):
    """
    Convert weighted objective values back to raw hardware metrics.

    NSGA-II minimises:
        obj[0] = power_W  * WEIGHT_POWER
        obj[1] = lut_count * WEIGHT_AREA
        obj[2] = (1/(psnr+1)) * WEIGHT_PERFORMANCE

    This function inverts those multiplications so that the summary
    report shows the actual hardware numbers, not the optimizer-internal
    scaled values.

    Returns:
        raw_power  : ndarray (n,)  – power in Watts
        raw_area   : ndarray (n,)  – area in LUTs
        raw_perf   : ndarray (n,)  – performance error 1/(psnr+1)
        psnr_approx: ndarray (n,)  – PSNR in dB (re-derived from raw_perf)
    """
    raw_power = pareto_objectives[:, 0] / WEIGHT_POWER
    raw_area  = pareto_objectives[:, 1] / WEIGHT_AREA
    raw_perf  = pareto_objectives[:, 2] / WEIGHT_PERFORMANCE

    # Invert  perf_error = 1/(psnr+1)  →  psnr = 1/perf_error - 1
    psnr_approx = np.where(raw_perf > 0, 1.0 / raw_perf - 1.0, np.inf)

    return raw_power, raw_area, raw_perf, psnr_approx


def save_optimization_results(result, callback, fft_size):
    """
    Save optimization results to files.

    Handles the case where all solutions violated constraints and pymoo
    returns result.X = None / result.F = None (no feasible Pareto front).
    In that case we fall back to the least-infeasible solutions from the
    final population (result.pop), so the run still produces useful output
    and does not crash.

    NOTE: result.F contains *weighted* objectives.  All values written to
    the summary are unscaled back to real hardware units via _unscale_objectives().
    """
    log_message("Saving optimization results...")

    results_subdir = os.path.join(RESULTS_DIR, f"fft_{fft_size}")
    os.makedirs(results_subdir, exist_ok=True)

    # ── Determine Pareto front (or fallback to least-infeasible pop) ──
    pareto_objectives = result.F   # None when no feasible solution exists
    pareto_solutions  = result.X   # None when no feasible solution exists
    feasible = pareto_solutions is not None

    if not feasible:
        log_message(
            "WARNING: No feasible solutions found — all solutions violated "
            "constraints. Saving least-infeasible population as fallback.",
            level='WARN'
        )
        pop = result.pop
        if pop is not None and len(pop) > 0:
            pareto_objectives = pop.get("F")
            pareto_solutions  = pop.get("X")
            cv_vals           = pop.get("CV")
            if cv_vals is not None:
                order = np.argsort(cv_vals.ravel())
                pareto_objectives = pareto_objectives[order]
                pareto_solutions  = pareto_solutions[order]
        else:
            pareto_objectives = np.empty((0, OBJECTIVES))
            pareto_solutions  = np.empty((0,), dtype=int)

    # ── Persist raw weighted arrays (for downstream analysis) ───────────
    np.save(os.path.join(results_subdir, 'pareto_objectives.npy'), pareto_objectives)
    np.save(os.path.join(results_subdir, 'pareto_solutions.npy'),  pareto_solutions)

    fitness_data = callback.data
    np.savez(os.path.join(results_subdir, 'fitness_history.npz'), *fitness_data)

    # ── Unscale objectives for human-readable reporting ──────────────────
    if len(pareto_objectives) > 0:
        raw_power, raw_area, raw_perf, psnr_approx = _unscale_objectives(pareto_objectives)
    else:
        raw_power = raw_area = raw_perf = psnr_approx = np.array([])

    # ── Summary report ──────────────────────────────────────────────────
    summary_file = os.path.join(results_subdir, 'summary.txt')
    with open(summary_file, 'w') as f:
        f.write("Mixed-Precision FFT Optimization Results\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"FFT Size: {fft_size}\n")
        f.write(f"Population: {POPULATION}\n")
        f.write(f"Generations: {GENERATIONS}\n")
        f.write(f"Objectives: {OBJECTIVES}\n")
        f.write(f"Weights: Power={WEIGHT_POWER}, Area={WEIGHT_AREA}, "
                f"Performance={WEIGHT_PERFORMANCE}\n\n")

        if not feasible:
            f.write("*** WARNING: No feasible solutions found. ***\n")
            f.write("All solutions violated at least one constraint.\n")
            f.write("Results below are the least-infeasible solutions from the "
                    "final population.\n")
            f.write("Root cause: check Verilog simulation (iverilog/vvp) and "
                    "SQNR evaluation — SQNR=-100 dB indicates simulation failure.\n\n")

        f.write(f"{'Pareto' if feasible else 'Fallback'} Front Solutions: "
                f"{len(pareto_solutions)}\n\n")

        if len(pareto_solutions) == 0:
            f.write("No solutions to report.\n")
            log_message(f"Results saved to {results_subdir} (no solutions)")
            return

        # ── Pareto front table (raw hardware units) ──────────────────────
        f.write(f"{'Pareto' if feasible else 'Fallback'} Front (Objectives):\n")
        f.write(f"{'ID':<5} {'Power(W)':<12} {'Area(LUTs)':<12} "
                f"{'Perf Error':<12} {'PSNR(dB)':<12}\n")
        f.write('-' * 55 + '\n')
        for i in range(len(pareto_objectives)):
            f.write(f"{i:<5} "
                    f"{raw_power[i]:<12.6f} "
                    f"{raw_area[i]:<12.0f} "
                    f"{raw_perf[i]:<12.6f} "
                    f"{psnr_approx[i]:<12.2f}\n")

        f.write("\n\nBest Solutions by Objective:\n")
        f.write('-' * 50 + '\n')

        # Best power (lowest raw power)
        best_power_idx = np.argmin(raw_power)
        f.write(f"\nBest Power:\n")
        f.write(f"  Solution ID  : {best_power_idx}\n")
        f.write(f"  Power        : {raw_power[best_power_idx]:.6f} W\n")
        f.write(f"  Area         : {raw_area[best_power_idx]:.0f} LUTs\n")
        f.write(f"  Perf Error   : {raw_perf[best_power_idx]:.6f}\n")
        f.write(f"  PSNR         : {psnr_approx[best_power_idx]:.2f} dB\n")
        f.write(f"  Chromosome   : {pareto_solutions[best_power_idx]}\n")

        # Best area (lowest raw LUT count)
        best_area_idx = np.argmin(raw_area)
        f.write(f"\nBest Area:\n")
        f.write(f"  Solution ID  : {best_area_idx}\n")
        f.write(f"  Power        : {raw_power[best_area_idx]:.6f} W\n")
        f.write(f"  Area         : {raw_area[best_area_idx]:.0f} LUTs\n")
        f.write(f"  Perf Error   : {raw_perf[best_area_idx]:.6f}\n")
        f.write(f"  PSNR         : {psnr_approx[best_area_idx]:.2f} dB\n")
        f.write(f"  Chromosome   : {pareto_solutions[best_area_idx]}\n")

        # Best performance (lowest perf error = highest PSNR)
        best_perf_idx = np.argmin(raw_perf)
        f.write(f"\nBest Performance:\n")
        f.write(f"  Solution ID  : {best_perf_idx}\n")
        f.write(f"  Power        : {raw_power[best_perf_idx]:.6f} W\n")
        f.write(f"  Area         : {raw_area[best_perf_idx]:.0f} LUTs\n")
        f.write(f"  Perf Error   : {raw_perf[best_perf_idx]:.6f}\n")
        f.write(f"  PSNR         : {psnr_approx[best_perf_idx]:.2f} dB\n")
        f.write(f"  Chromosome   : {pareto_solutions[best_perf_idx]}\n")

        # Best balanced (lowest sum of normalised raw objectives)
        # Normalise each axis to [0,1] across the Pareto front before summing
        # so no single axis dominates the balance score.
        norm_power = (raw_power - raw_power.min()) / (raw_power.ptp() + 1e-12)
        norm_area  = (raw_area  - raw_area.min())  / (raw_area.ptp()  + 1e-12)
        norm_perf  = (raw_perf  - raw_perf.min())  / (raw_perf.ptp()  + 1e-12)
        best_bal_idx = np.argmin(norm_power + norm_area + norm_perf)
        f.write(f"\nBest Balanced (equal-weight normalised):\n")
        f.write(f"  Solution ID  : {best_bal_idx}\n")
        f.write(f"  Power        : {raw_power[best_bal_idx]:.6f} W\n")
        f.write(f"  Area         : {raw_area[best_bal_idx]:.0f} LUTs\n")
        f.write(f"  Perf Error   : {raw_perf[best_bal_idx]:.6f}\n")
        f.write(f"  PSNR         : {psnr_approx[best_bal_idx]:.2f} dB\n")
        f.write(f"  Chromosome   : {pareto_solutions[best_bal_idx]}\n")

    log_message(f"Results saved to {results_subdir}")
    log_message(f"{'Pareto' if feasible else 'Fallback'} front has "
                f"{len(pareto_solutions)} solutions")


def run_full_optimization_sweep():
    """
    Run optimization for all FFT sizes defined in FFT_SIZES
    """
    log_message("\n" + "="*60)
    log_message("Mixed-Precision FFT Optimization Framework")
    log_message("="*60 + "\n")

    setup_verilog_sources()

    all_results = {}

    for fft_size in FFT_SIZES:
        try:
            global CURRENT_GEN
            CURRENT_GEN = 0

            result = run_optimization_for_fft_size(fft_size)
            all_results[fft_size] = result

        except Exception as e:
            log_message(
                f"ERROR: Optimization failed for {fft_size}-point FFT: {e}",
                level='ERROR'
            )
            continue

    generate_comprehensive_summary(all_results)

    log_message("\n" + "="*60)
    log_message("Optimization sweep complete!")
    log_message("="*60)


def generate_comprehensive_summary(all_results):
    """
    Generate a comprehensive summary across all FFT sizes.
    All values are unscaled back to raw hardware units.
    """
    summary_file = os.path.join(RESULTS_DIR, 'comprehensive_summary.txt')

    with open(summary_file, 'w') as f:
        f.write("Mixed-Precision FFT Optimization - Comprehensive Summary\n")
        f.write("="*70 + "\n\n")

        for fft_size, result in all_results.items():
            f.write(f"\nFFT Size: {fft_size}\n")
            f.write("-" * 70 + "\n")

            if result is None:
                f.write("  Optimization failed\n")
                continue

            pareto_front = result.F
            if pareto_front is None or len(pareto_front) == 0:
                f.write("  No Pareto front available\n")
                continue

            # Unscale to raw hardware units
            raw_power, raw_area, raw_perf, psnr_approx = _unscale_objectives(pareto_front)

            f.write(f"  Pareto front size: {len(pareto_front)}\n")
            f.write(f"  Power range  : {raw_power.min():.6f} – {raw_power.max():.6f} W\n")
            f.write(f"  Area range   : {raw_area.min():.0f} – {raw_area.max():.0f} LUTs\n")
            f.write(f"  PSNR range   : {psnr_approx.min():.2f} – {psnr_approx.max():.2f} dB\n")

            # Best balanced solution using normalised equal-weight score
            norm_power = (raw_power - raw_power.min()) / (raw_power.ptp() + 1e-12)
            norm_area  = (raw_area  - raw_area.min())  / (raw_area.ptp()  + 1e-12)
            norm_perf  = (raw_perf  - raw_perf.min())  / (raw_perf.ptp()  + 1e-12)
            best_idx   = np.argmin(norm_power + norm_area + norm_perf)

            f.write(f"\n  Best balanced solution:\n")
            f.write(f"    Power      : {raw_power[best_idx]:.6f} W\n")
            f.write(f"    Area       : {raw_area[best_idx]:.0f} LUTs\n")
            f.write(f"    PSNR       : {psnr_approx[best_idx]:.2f} dB\n")
            f.write(f"    Perf Error : {raw_perf[best_idx]:.6f}\n")

    log_message(f"Comprehensive summary saved to {summary_file}")


def quick_test():
    """
    Quick test with a single small FFT size
    """
    log_message("Running quick test with 32-point FFT")

    setup_verilog_sources()

    global CURRENT_GEN
    CURRENT_GEN = 0

    # Reduce parameters for quick test
    global POPULATION, GENERATIONS
    original_pop = POPULATION
    original_gen = GENERATIONS

    POPULATION = 60
    GENERATIONS = 80

    result = run_optimization_for_fft_size(fft_size=512)

    # Restore parameters
    POPULATION = original_pop
    GENERATIONS = original_gen

    log_message("Quick test complete")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Mixed-Precision FFT Optimization using NSGA-II'
    )
    parser.add_argument(
        '--mode',
        choices=['test', 'single', 'full'],
        default='test',
        help='Optimization mode: test (quick), single (one size), full (all sizes)'
    )
    parser.add_argument(
        '--fft-size',
        type=int,
        default=8,
        choices=[2, 4, 8, 16, 32, 64, 128, 256, 512, 1024],
        help='FFT size for single mode'
    )

    args = parser.parse_args()

    if args.mode == 'test':
        quick_test()
    elif args.mode == 'single':
        setup_verilog_sources()
        run_optimization_for_fft_size(args.fft_size)
    elif args.mode == 'full':
        run_full_optimization_sweep()