"""
Objective Evaluation for Mixed-Precision FFT Optimization
Integrates Vivado synthesis and performance evaluation
"""

import numpy as np
import subprocess
import os
import csv
import hashlib
from pymoo.core.problem import Problem
from concurrent.futures import ThreadPoolExecutor, as_completed
from globalVariablesMixedFFT import *
from fft_template_generator import FFTTemplateGeneratorFinal
from performance_evaluator import PerformanceEvaluator


class MixedPrecisionFFTProblem(Problem):
    """
    Custom problem formulation for mixed-precision FFT optimization
    
    Objectives:
        1. Minimize Power (W)
        2. Minimize Area (LUTs)
        3. Minimize Performance Error (1/SQNR + MAE)
    
    Constraints:
        - Power < MAX_POWER_W
        - Area < MAX_AREA_LUTS
        - SQNR > MIN_SQNR_DB
    """
    
    def __init__(self, fft_size=8, **kwargs):
        self.fft_size = fft_size
        
        # Initialize generators
        self.template_gen = FFTTemplateGeneratorFinal(fft_size)
        self.perf_eval = PerformanceEvaluator(fft_size)
        
        # Get chromosome length from template generator
        chrom_length = self.template_gen.get_chromosome_length()
        
        # Decision variables: [0, 1] for each butterfly's mult and add precision
        xl = [0] * chrom_length
        xu = [1] * chrom_length
        
        super().__init__(
            n_var=chrom_length,
            n_obj=OBJECTIVES,
            n_ieq_constr=3,  # Power, Area, SQNR constraints
            xl=xl,
            xu=xu,
            vtype=int,
            elementwise_evaluation=False,
            **kwargs
        )
        
        log_message(f"Initialized FFT-{fft_size} optimization problem")
        log_message(f"Chromosome length: {chrom_length}")
        log_message(f"Number of stages: {self.template_gen.num_stages}")
        log_message(f"Total butterflies: {self.template_gen.total_butterflies}")
    
    def _evaluate(self, X, out, *args, **kwargs):
        """
        Evaluate population of solutions
        X: Population matrix (pop_size x chromosome_length)
        """
        global CURRENT_GEN
        
        log_message(f"=== Generation {CURRENT_GEN} ===", level='GEN')
        
        # Write generation number
        with open('generation.txt', 'w') as f:
            f.write(str(CURRENT_GEN))
        
        CURRENT_GEN += 1
        
        F = [None] * len(X)  # Objectives
        G = [None] * len(X)  # Constraints
        
        # Parallel evaluation
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
                    # Assign worst possible values on failure
                    F[idx] = [MAX_POWER_W * 2, MAX_AREA_LUTS * 2, 1e6]
                    G[idx] = [MAX_POWER_W, MAX_AREA_LUTS, -MIN_SQNR_DB]
        
        out["F"] = np.array(F)
        out["G"] = np.array(G)
        
        log_message(f"Generation {CURRENT_GEN-1} complete")
    
    def evaluate_solution(self, chromosome, sol_id):
        """
        Evaluate a single solution (chromosome)
        
        Returns:
            objectives: [power, area, performance_error]
            constraints: [power_violation, area_violation, sqnr_violation]
        """
        log_message(f"Evaluating solution {sol_id}: {chromosome}")
        
        # Check cache
        chrom_hash = self._hash_chromosome(chromosome)
        if ENABLE_RESULT_CACHE and chrom_hash in RESULT_CACHE:
            log_message(f"Solution {sol_id} found in cache")
            cached = RESULT_CACHE[chrom_hash]
            return self._compute_objectives_and_constraints(cached)
        
        # Generate unique design name
        design_name = f"fft_{self.fft_size}_sol{sol_id}_gen{CURRENT_GEN}"
        
        # Step 1: Generate Verilog from chromosome
        verilog_file = os.path.join(
            GENERATED_DESIGNS_DIR, 
            f"{design_name}.v"
        )
        self.template_gen.generate_verilog(chromosome, verilog_file)
        log_message(f"Generated Verilog: {design_name}")
        
        # Step 2: Run Vivado synthesis
        power, area = self._run_vivado_synthesis(design_name)
        
        # Step 3: Run performance evaluation (simulation)
        sqnr, mae = self._run_performance_evaluation(verilog_file, design_name)
        
        # Cache results
        results = {
            'power': power,
            'area': area,
            'sqnr': sqnr,
            'mae': mae
        }
        RESULT_CACHE[chrom_hash] = results
        
        # Save individual result
        self._save_solution_result(sol_id, chromosome, results)
        
        # Log chromosome statistics
        stats = self.template_gen.analyze_chromosome_statistics(chromosome)
        log_message(
            f"Solution {sol_id}: Power={power:.4f}W, Area={area} LUTs, "
            f"SQNR={sqnr:.2f}dB, MAE={mae:.6f} | "
            f"FP8_mult={stats['fp8_mult']}/{self.template_gen.total_butterflies} "
            f"({stats['fp8_mult']/self.template_gen.total_butterflies*100:.1f}%), "
            f"FP8_add={stats['fp8_add']}/{self.template_gen.total_butterflies} "
            f"({stats['fp8_add']/self.template_gen.total_butterflies*100:.1f}%)"
        )
        
        return self._compute_objectives_and_constraints(results)
    
    def _hash_chromosome(self, chromosome):
        """Create hash of chromosome for caching"""
        chrom_str = ''.join(map(str, chromosome))
        return hashlib.md5(chrom_str.encode()).hexdigest()
    
    def _run_vivado_synthesis(self, design_name):
        """
        Run Vivado synthesis and extract power and area metrics
        Returns: (power_watts, area_luts)
        """
        log_message(f"Running Vivado synthesis for {design_name}")
        
        csv_output = os.path.join(REPORTS_DIR, f"{design_name}_metrics.csv")
        
        # Construct Vivado command
        tcl_script = './vivado_synthesis.tcl'
        cmd = [
            VIVADO_PATH,
            '-mode', 'batch',
            '-source', tcl_script,
            '-tclargs', design_name, csv_output, str(CLOCK_PERIOD)
        ]
        
        try:
            # Run synthesis
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if result.returncode != 0:
                log_message(
                    f"Vivado synthesis failed for {design_name}: {result.stderr}", 
                    level='ERROR'
                )
                return MAX_POWER_W * 2, MAX_AREA_LUTS * 2
            
            # Parse CSV output
            power, area = self._parse_vivado_metrics(csv_output)
            return power, area
            
        except subprocess.TimeoutExpired:
            log_message(f"Vivado synthesis timeout for {design_name}", level='ERROR')
            return MAX_POWER_W * 2, MAX_AREA_LUTS * 2
        except Exception as e:
            log_message(f"Vivado synthesis error for {design_name}: {e}", level='ERROR')
            return MAX_POWER_W * 2, MAX_AREA_LUTS * 2
    
    def _parse_vivado_metrics(self, csv_file):
        """Parse Vivado metrics from CSV file"""
        power = MAX_POWER_W * 2
        area = MAX_AREA_LUTS * 2
        
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    metric = row['Metric']
                    value = row['Value']
                    
                    if metric == 'total_power_w':
                        power = float(value)
                    elif metric == 'lut_count':
                        area = int(value)
        except Exception as e:
            log_message(f"Error parsing Vivado metrics: {e}", level='ERROR')
        
        return power, area
    
    def _run_performance_evaluation(self, verilog_file, design_name):
        """
        Run performance evaluation (simulation)
        Returns: (sqnr_db, mae)
        """
        log_message(f"Running performance evaluation for {design_name}")
        
        try:
            sqnr, mae = self.perf_eval.evaluate_design(verilog_file, design_name)
            return sqnr, mae
        except Exception as e:
            log_message(
                f"Performance evaluation failed for {design_name}: {e}", 
                level='ERROR'
            )
            return -100.0, 1e6
    
    def _compute_objectives_and_constraints(self, results):
        """
        Compute objective values and constraint violations
        
        Objectives (minimize):
            1. Power (W)
            2. Area (LUTs)
            3. Performance error = 1/(SQNR+1) + MAE
        
        Constraints (<=0 is feasible):
            1. Power - MAX_POWER_W
            2. Area - MAX_AREA_LUTS
            3. MIN_SQNR_DB - SQNR
        """
        power = results['power']
        area = results['area']
        sqnr = results['sqnr']
        mae = results['mae']
        
        # Objective 3: Performance error (lower is better)
        # Combine SQNR (higher is better) and MAE (lower is better)
        performance_error = (1.0 / (sqnr + 1.0)) + mae
        
        objectives = [
            power * WEIGHT_POWER,
            area * WEIGHT_AREA,
            performance_error * WEIGHT_PERFORMANCE
        ]
        
        # Constraint violations (negative = feasible)
        constraints = [
            power - MAX_POWER_W,           # Power constraint
            area - MAX_AREA_LUTS,          # Area constraint
            MIN_SQNR_DB - sqnr             # SQNR constraint
        ]
        
        return objectives, constraints
    
    def _save_solution_result(self, sol_id, chromosome, results):
        """Save individual solution results with detailed chromosome analysis"""
        result_file = os.path.join(
            RESULTS_DIR,
            f"gen{CURRENT_GEN}_sol{sol_id}.txt"
        )
        
        stats = self.template_gen.analyze_chromosome_statistics(chromosome)
        
        with open(result_file, 'w') as f:
            f.write(f"FFT Size: {self.fft_size}\n")
            f.write(f"Generation: {CURRENT_GEN}\n")
            f.write(f"Solution ID: {sol_id}\n")
            f.write(f"Total Butterflies: {self.template_gen.total_butterflies}\n")
            f.write(f"Chromosome Length: {len(chromosome)}\n")
            f.write(f"Chromosome: {list(chromosome)}\n")
            f.write(f"\nResults:\n")
            f.write(f"  Power: {results['power']:.6f} W\n")
            f.write(f"  Area: {results['area']} LUTs\n")
            f.write(f"  SQNR: {results['sqnr']:.2f} dB\n")
            f.write(f"  MAE: {results['mae']:.6f}\n")
            
            f.write(f"\nOverall Precision Distribution:\n")
            f.write(f"  FP4 Multipliers: {stats['fp4_mult']} ({stats['fp4_mult']/self.template_gen.total_butterflies*100:.1f}%)\n")
            f.write(f"  FP8 Multipliers: {stats['fp8_mult']} ({stats['fp8_mult']/self.template_gen.total_butterflies*100:.1f}%)\n")
            f.write(f"  FP4 Adders: {stats['fp4_add']} ({stats['fp4_add']/self.template_gen.total_butterflies*100:.1f}%)\n")
            f.write(f"  FP8 Adders: {stats['fp8_add']} ({stats['fp8_add']/self.template_gen.total_butterflies*100:.1f}%)\n")
            
            f.write(f"\nPer-Stage Breakdown:\n")
            f.write(f"{'Stage':<8} {'FP4 Mult':<12} {'FP8 Mult':<12} {'FP4 Add':<12} {'FP8 Add':<12}\n")
            f.write('-' * 60 + '\n')
            for stage_stat in stats['stage_stats']:
                f.write(f"{stage_stat['stage']:<8} "
                       f"{stage_stat['fp4_mult']:<12} "
                       f"{stage_stat['fp8_mult']:<12} "
                       f"{stage_stat['fp4_add']:<12} "
                       f"{stage_stat['fp8_add']:<12}\n")


# Test function
def test_problem():
    """Test the problem formulation"""
    problem = MixedPrecisionFFTProblem(fft_size=8)
    
    # Test with sample chromosome
    test_chromosome = np.array([0, 0, 1, 0, 1, 1])  # 3 stages, mixed precision
    
    print(f"Testing with chromosome: {test_chromosome}")
    objectives, constraints = problem.evaluate_solution(test_chromosome, 0)
    
    print(f"Objectives: {objectives}")
    print(f"Constraints: {constraints}")


if __name__ == "__main__":
    test_problem()
