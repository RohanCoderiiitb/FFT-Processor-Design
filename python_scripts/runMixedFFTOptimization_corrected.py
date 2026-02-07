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

from globalVariablesMixedFFT_corrected import *
from objectiveEvaluationFFT_corrected import MixedPrecisionFFTProblem
from optimizationUtils_corrected import (
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
        'adder.v',
        'multiplier.v',
        'mixed_precision_wrappers.v',
        'twiddle_rom.v',
        'agu.v',
        'memory.v'
    ]
    
    # Copy from upload directory
    upload_dir = '/mnt/user-data/uploads'
    for fname in source_files:
        src = os.path.join(upload_dir, fname)
        dst = os.path.join(VERILOG_SOURCES_DIR, fname)
        
        if os.path.exists(src):
            shutil.copy(src, dst)
            log_message(f"Copied {fname}")
        else:
            log_message(f"Warning: {fname} not found in uploads", level='WARN')
    
    # Copy wrapper file from current directory
    wrapper_src = './mixed_precision_wrappers.v'
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


def save_optimization_results(result, callback, fft_size):
    """
    Save optimization results to files
    
    Args:
        result: PyMOO result object
        callback: Callback object with evolution history
        fft_size: FFT size
    """
    log_message("Saving optimization results...")
    
    results_subdir = os.path.join(RESULTS_DIR, f"fft_{fft_size}")
    os.makedirs(results_subdir, exist_ok=True)
    
    # Save Pareto front objectives
    pareto_objectives = result.F
    np.save(
        os.path.join(results_subdir, 'pareto_objectives.npy'),
        pareto_objectives
    )
    
    # Save Pareto front solutions (chromosomes)
    pareto_solutions = result.X
    np.save(
        os.path.join(results_subdir, 'pareto_solutions.npy'),
        pareto_solutions
    )
    
    # Save evolution history
    fitness_data = callback.data
    np.savez(
        os.path.join(results_subdir, 'fitness_history.npz'),
        *fitness_data
    )
    
    # Save summary report
    summary_file = os.path.join(results_subdir, 'summary.txt')
    with open(summary_file, 'w') as f:
        f.write(f"Mixed-Precision FFT Optimization Results\n")
        f.write(f"{'='*60}\n\n")
        f.write(f"FFT Size: {fft_size}\n")
        f.write(f"Population: {POPULATION}\n")
        f.write(f"Generations: {GENERATIONS}\n")
        f.write(f"Objectives: {OBJECTIVES}\n\n")
        
        f.write(f"Pareto Front Solutions: {len(pareto_solutions)}\n\n")
        
        f.write("Pareto Front (Objectives):\n")
        f.write(f"{'ID':<5} {'Power(W)':<12} {'Area(LUTs)':<12} {'Perf Error':<12}\n")
        f.write('-' * 50 + '\n')
        
        for i, obj in enumerate(pareto_objectives):
            f.write(f"{i:<5} {obj[0]:<12.6f} {obj[1]:<12.0f} {obj[2]:<12.6f}\n")
        
        f.write("\n\nBest Solutions by Objective:\n")
        f.write('-' * 50 + '\n')
        
        # Best power
        best_power_idx = np.argmin(pareto_objectives[:, 0])
        f.write(f"\nBest Power:\n")
        f.write(f"  Solution ID: {best_power_idx}\n")
        f.write(f"  Power: {pareto_objectives[best_power_idx, 0]:.6f} W\n")
        f.write(f"  Area: {pareto_objectives[best_power_idx, 1]:.0f} LUTs\n")
        f.write(f"  Perf Error: {pareto_objectives[best_power_idx, 2]:.6f}\n")
        f.write(f"  Chromosome: {pareto_solutions[best_power_idx]}\n")
        
        # Best area
        best_area_idx = np.argmin(pareto_objectives[:, 1])
        f.write(f"\nBest Area:\n")
        f.write(f"  Solution ID: {best_area_idx}\n")
        f.write(f"  Power: {pareto_objectives[best_area_idx, 0]:.6f} W\n")
        f.write(f"  Area: {pareto_objectives[best_area_idx, 1]:.0f} LUTs\n")
        f.write(f"  Perf Error: {pareto_objectives[best_area_idx, 2]:.6f}\n")
        f.write(f"  Chromosome: {pareto_solutions[best_area_idx]}\n")
        
        # Best performance
        best_perf_idx = np.argmin(pareto_objectives[:, 2])
        f.write(f"\nBest Performance:\n")
        f.write(f"  Solution ID: {best_perf_idx}\n")
        f.write(f"  Power: {pareto_objectives[best_perf_idx, 0]:.6f} W\n")
        f.write(f"  Area: {pareto_objectives[best_perf_idx, 1]:.0f} LUTs\n")
        f.write(f"  Perf Error: {pareto_objectives[best_perf_idx, 2]:.6f}\n")
        f.write(f"  Chromosome: {pareto_solutions[best_perf_idx]}\n")
    
    log_message(f"Results saved to {results_subdir}")
    log_message(f"Pareto front has {len(pareto_solutions)} solutions")


def run_full_optimization_sweep():
    """
    Run optimization for all FFT sizes from 2 to 1024
    """
    log_message("\n" + "="*60)
    log_message("Mixed-Precision FFT Optimization Framework")
    log_message("="*60 + "\n")
    
    # Setup environment
    setup_verilog_sources()
    
    # Results summary across all FFT sizes
    all_results = {}
    
    for fft_size in FFT_SIZES:
        try:
            global CURRENT_GEN
            CURRENT_GEN = 0  # Reset generation counter
            
            result = run_optimization_for_fft_size(fft_size)
            all_results[fft_size] = result
            
        except Exception as e:
            log_message(
                f"ERROR: Optimization failed for {fft_size}-point FFT: {e}",
                level='ERROR'
            )
            continue
    
    # Generate comprehensive summary
    generate_comprehensive_summary(all_results)
    
    log_message("\n" + "="*60)
    log_message("Optimization sweep complete!")
    log_message("="*60)


def generate_comprehensive_summary(all_results):
    """
    Generate a comprehensive summary across all FFT sizes
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
            
            # Statistics
            f.write(f"  Pareto front size: {len(pareto_front)}\n")
            f.write(f"  Power range: {pareto_front[:, 0].min():.6f} - "
                   f"{pareto_front[:, 0].max():.6f} W\n")
            f.write(f"  Area range: {pareto_front[:, 1].min():.0f} - "
                   f"{pareto_front[:, 1].max():.0f} LUTs\n")
            f.write(f"  Performance error range: {pareto_front[:, 2].min():.6f} - "
                   f"{pareto_front[:, 2].max():.6f}\n")
            
            # Best solution
            best_idx = np.argmin(pareto_front[:, 0] + pareto_front[:, 1] + pareto_front[:, 2])
            f.write(f"\n  Best balanced solution:\n")
            f.write(f"    Power: {pareto_front[best_idx, 0]:.6f} W\n")
            f.write(f"    Area: {pareto_front[best_idx, 1]:.0f} LUTs\n")
            f.write(f"    Perf Error: {pareto_front[best_idx, 2]:.6f}\n")
    
    log_message(f"Comprehensive summary saved to {summary_file}")


def quick_test():
    """
    Quick test with a single small FFT size
    """
    log_message("Running quick test with 8-point FFT")
    
    setup_verilog_sources()
    
    global CURRENT_GEN
    CURRENT_GEN = 0
    
    # Reduce parameters for quick test
    global POPULATION, GENERATIONS
    original_pop = POPULATION
    original_gen = GENERATIONS
    
    POPULATION = 6
    GENERATIONS = 3
    
    result = run_optimization_for_fft_size(fft_size=8)
    
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
        help='Optimization mode: test (quick 8-pt), single (one size), full (all sizes)'
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
