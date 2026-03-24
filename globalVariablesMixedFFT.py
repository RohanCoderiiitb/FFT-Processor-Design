"""
Global Variables for Mixed-Precision FFT Optimization
Stage-level precision control (Option A):
  One mult_precision + one add_precision gene per FFT stage.
  Hardware instantiates one butterfly_wrapper per stage, so all N/2
  butterflies within a stage share the same precision — per-butterfly
  encoding would be redundant.

Chromosome sizes for different FFT sizes:
- FFT-8:    3 stages x 2 = 6 genes
- FFT-16:   4 stages x 2 = 8 genes
- FFT-32:   5 stages x 2 = 10 genes
- FFT-64:   6 stages x 2 = 12 genes
- FFT-128:  7 stages x 2 = 14 genes
- FFT-256:  8 stages x 2 = 16 genes
- FFT-512:  9 stages x 2 = 18 genes
- FFT-1024: 10 stages x 2 = 20 genes
"""

import random
import math
from multiprocessing.pool import ThreadPool

# ======================= NSGA-II Parameters =======================
POPULATION = 30
GENERATIONS = 100
SEED = 42
MUTATION_RATE = 0.05
CROSSOVER_RATE = 0.9
OBJECTIVES = 3               # Power, Area, Performance

CURRENT_GEN = 0
SOLUTION_THREADS = 6

FITNESS = 'fitness.npy'
DPI = 200

random.seed(SEED)

# ======================= FFT Configuration =======================
FFT_SIZES = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
CURRENT_FFT_SIZE = 8

# ======================= Chromosome Size Calculation =======================
def calculate_chromosome_size(fft_size):
    num_stages = int(math.log2(fft_size))
    chromosome_length = 2 * num_stages
    return chromosome_length

print("Chromosome sizes for different FFT sizes:")
for size in [8, 16, 32, 64, 128, 256, 512, 1024]:
    chrom_size = calculate_chromosome_size(size)
    ns = int(math.log2(size))
    print(f"  FFT-{size:<4}: {ns:>2} stages x 2 = {chrom_size:>3} genes")

# ======================= Vivado Configuration =======================
VIVADO_PATH = '/tools/Xilinx/Vivado/2021.1/bin/vivado'
VIVADO_BATCH_MODE = True
CLOCK_PERIOD = 10.0
FPGA_DEVICE = 'xc7a35tcpg236-1'

# ======================= File Paths =======================
VERILOG_SOURCES_DIR = './verilog_sources'
GENERATED_DESIGNS_DIR = './generated_designs'
VIVADO_PROJECTS_DIR = './vivado_projects'
REPORTS_DIR = './reports'
SIMULATION_DIR = './sim'
RESULTS_DIR = './results'

# ======================= Optimization Weights =======================
# Rebalanced so all three objectives are the same order of magnitude.
# Old weights (1,1,5) let area (~2000) dominate power (~0.12) by 16000x,
# making NSGA-II effectively a single-objective LUT minimiser.
WEIGHT_POWER       = 10.0    # 0.12 W    x 10    -> ~1.2
WEIGHT_AREA        = 0.001   # 2000 LUTs x 0.001 -> ~2.0
WEIGHT_PERFORMANCE = 50.0    # 1/(P+1)   x 50    -> ~1-4

# Constraint thresholds
MAX_POWER_W   = 3.0
MAX_AREA_LUTS = 10000
# Relaxed from 0.0 to -10.0 so mixed-precision solutions are not immediately
# infeasible in early generations. WEIGHT_PERFORMANCE drives PSNR up through
# the objective; the constraint only rejects genuine failures (-100 dB).
MIN_PSNR_DB = -10.0

# ======================= Performance Metrics =======================
ENABLE_RESULT_CACHE = True
RESULT_CACHE = {}

# ======================= Optimization Strategies =======================

def generate_smart_initial_population(fft_size, pop_size):
    """
    Generate initial population with domain-knowledge strategies.
    Stage-level encoding: chromosome = [s0_mult, s0_add, s1_mult, s1_add, ...]
    """
    from fft_template_generator import FFTTemplateGenerator

    gen = FFTTemplateGenerator(fft_size)
    chrom_length = gen.get_chromosome_length()
    population = []

    # Strategy 1: All FP4
    population.append([0] * chrom_length)

    # Strategy 2: All FP8
    population.append([1] * chrom_length)

    # Strategy 3: FP8 early stages, FP4 late stages.
    # Errors in early stages propagate through all downstream stages,
    # so FP8 budget is most valuable at the beginning of the pipeline.
    progressive = []
    for stage in range(gen.num_stages):
        prec = 1 if stage < gen.num_stages // 2 else 0
        progressive.extend([prec, prec])
    population.append(progressive)

    # Strategy 4: FP4 early, FP8 late (contrast / inverse)
    progressive_inv = []
    for stage in range(gen.num_stages):
        prec = 0 if stage < gen.num_stages // 2 else 1
        progressive_inv.extend([prec, prec])
    population.append(progressive_inv)

    # Strategy 5: FP8 multipliers everywhere, FP4 adders everywhere
    mult_fp8 = []
    for _ in range(gen.num_stages):
        mult_fp8.extend([1, 0])
    population.append(mult_fp8)

    # Strategy 6: FP4 multipliers everywhere, FP8 adders everywhere
    mult_fp4 = []
    for _ in range(gen.num_stages):
        mult_fp4.extend([0, 1])
    population.append(mult_fp4)

    # Strategies 7-8: Random with bias
    for fp4_prob in [0.7, 0.3]:
        individual = [0 if random.random() < fp4_prob else 1
                      for _ in range(chrom_length)]
        population.append(individual)

    # Strategy 9: FP8 first 2 stages only, FP4 rest.
    # Stages 0 and 1 have the highest error-propagation multiplier,
    # so this gives the best PSNR-per-FP8-stage ratio.
    strat9 = []
    for stage in range(gen.num_stages):
        prec = 1 if stage < 2 else 0
        strat9.extend([prec, prec])
    population.append(strat9)

    # Strategy 10: FP8 mult + FP4 add at every stage.
    # Multiply errors scale with both operand magnitudes; adder errors are
    # bounded by the larger operand. FP8 multiply gives more PSNR per LUT
    # than FP8 add.
    strat10 = []
    for _ in range(gen.num_stages):
        strat10.extend([1, 0])
    population.append(strat10)

    # Fill remainder with pure random
    while len(population) < pop_size:
        population.append([random.randint(0, 1) for _ in range(chrom_length)])

    return population[:pop_size]


ENABLE_SMART_INITIALIZATION = True

# ======================= Logging =======================
VERBOSE = True
LOG_FILE = './optimization.log'
SAVE_ALL_DESIGNS = False

# ======================= Helper Functions =======================
def log_message(message, level='INFO'):
    import datetime
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] [{level}] {message}"
    if VERBOSE:
        print(log_line)
    with open(LOG_FILE, 'a') as f:
        f.write(log_line + '\n')

def initialize_directories():
    import os
    dirs = [
        VERILOG_SOURCES_DIR,
        GENERATED_DESIGNS_DIR,
        VIVADO_PROJECTS_DIR,
        REPORTS_DIR,
        SIMULATION_DIR,
        RESULTS_DIR
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    log_message("Initialized directory structure")

# Initialize at import time
initialize_directories()