"""
Global Variables for Mixed-Precision FFT Optimization
Stage-level precision control (Option A):
  One mult_precision + one add_precision gene per FFT stage.
  Hardware instantiates one butterfly_wrapper per stage, so all N/2
  butterflies within a stage share the same precision — per-butterfly
  encoding would be redundant.

Chromosome sizes for different FFT sizes:
- FFT-8:    3 stages × 2 = 6 genes
- FFT-16:   4 stages × 2 = 8 genes
- FFT-32:   5 stages × 2 = 10 genes
- FFT-64:   6 stages × 2 = 12 genes
- FFT-128:  7 stages × 2 = 14 genes
- FFT-256:  8 stages × 2 = 16 genes
- FFT-512:  9 stages × 2 = 18 genes
- FFT-1024: 10 stages × 2 = 20 genes
"""

import random
import math
from multiprocessing.pool import ThreadPool

# ======================= NSGA-II Parameters =======================
# NOTE: For large chromosomes, smaller populations may be more effective
POPULATION = 30              # Increased for better diversity with large search space
GENERATIONS = 100            # More generations needed for convergence
SEED = 42
MUTATION_RATE = 0.05         # Lower rate for large chromosomes
CROSSOVER_RATE = 0.9         # Higher crossover for exploration
OBJECTIVES = 3               # Power, Area, Performance

CURRENT_GEN = 0
SOLUTION_THREADS = 4         # Parallel Vivado syntheses

FITNESS = 'fitness.npy'
DPI = 200

random.seed(SEED)

# ======================= FFT Configuration =======================
# Start with smaller sizes due to large chromosome dimensions
FFT_SIZES = [8, 16, 32, 64, 128, 256]  # Removed 512, 1024 for initial testing
CURRENT_FFT_SIZE = 8         # Start with 8-point FFT

# ======================= Chromosome Size Calculation =======================
def calculate_chromosome_size(fft_size):
    """
    Calculate chromosome size for stage-level precision (Option A).

    For N-point FFT:
    - num_stages = log₂(N)
    - Chromosome length = 2 × num_stages  (one mult_prec + one add_prec per stage)

    Args:
        fft_size: FFT size (power of 2)

    Returns:
        Chromosome length (number of genes)
    """
    num_stages = int(math.log2(fft_size))
    chromosome_length = 2 * num_stages
    return chromosome_length

# Print chromosome sizes for reference
print("Chromosome sizes for different FFT sizes:")
for size in [8, 16, 32, 64, 128, 256, 512, 1024]:
    chrom_size = calculate_chromosome_size(size)
    ns = int(math.log2(size))
    print(f"  FFT-{size:<4}: {ns:>2} stages × 2 = {chrom_size:>3} genes")

# ======================= Vivado Configuration =======================
VIVADO_PATH = '/tools/Xilinx/Vivado/2021.1/bin/vivado'
VIVADO_BATCH_MODE = True
CLOCK_PERIOD = 10.0          # ns (100 MHz target)
FPGA_DEVICE = 'xc7a35tcpg236-1'

# ======================= File Paths =======================
VERILOG_SOURCES_DIR = './verilog_sources'
GENERATED_DESIGNS_DIR = './generated_designs'
VIVADO_PROJECTS_DIR = './vivado_projects'
REPORTS_DIR = './reports'
SIMULATION_DIR = './sim'
RESULTS_DIR = './results'

# ======================= Optimization Weights =======================
WEIGHT_POWER = 1.0
WEIGHT_AREA = 1.0
WEIGHT_PERFORMANCE = 1.0

# Constraint thresholds
MAX_POWER_W = 3.0            # Increased for larger designs
MAX_AREA_LUTS = 10000        # Increased for larger designs
MIN_SQNR_DB = 20.0

# ======================= Performance Metrics =======================
ENABLE_RESULT_CACHE = True
RESULT_CACHE = {}

# ======================= Optimization Strategies =======================
# For large chromosomes, we can use domain knowledge to initialize population

def generate_smart_initial_population(fft_size, pop_size):
    """
    Generate initial population with domain-knowledge strategies.
    Stage-level encoding: chromosome = [s0_mult, s0_add, s1_mult, s1_add, ...]

    Strategies:
    1. All FP4 (minimum power / area)
    2. All FP8 (maximum accuracy)
    3. Progressive: FP4 early stages, FP8 later stages (errors accumulate)
    4. Progressive inverse: FP8 early, FP4 later
    5. Multipliers FP8, Adders FP4
    6. Multipliers FP4, Adders FP8
    7. Random 70% FP4
    8. Random 30% FP4
    """
    from fft_template_generator import FFTTemplateGenerator

    gen = FFTTemplateGenerator(fft_size)
    chrom_length = gen.get_chromosome_length()  # = num_stages * 2
    population = []

    # Strategy 1: All FP4
    population.append([0] * chrom_length)

    # Strategy 2: All FP8
    population.append([1] * chrom_length)

    # Strategy 3: Progressive — FP4 for first half of stages, FP8 for second half
    progressive = []
    for stage in range(gen.num_stages):
        prec = 1 if stage >= gen.num_stages // 2 else 0
        progressive.extend([prec, prec])
    population.append(progressive)

    # Strategy 4: Progressive inverse
    progressive_inv = []
    for stage in range(gen.num_stages):
        prec = 0 if stage >= gen.num_stages // 2 else 1
        progressive_inv.extend([prec, prec])
    population.append(progressive_inv)

    # Strategy 5: Multipliers FP8, Adders FP4
    mult_fp8 = []
    for _ in range(gen.num_stages):
        mult_fp8.extend([1, 0])
    population.append(mult_fp8)

    # Strategy 6: Multipliers FP4, Adders FP8
    mult_fp4 = []
    for _ in range(gen.num_stages):
        mult_fp4.extend([0, 1])
    population.append(mult_fp4)

    # Strategy 7-8: Random with bias
    for fp4_prob in [0.7, 0.3]:
        individual = [0 if random.random() < fp4_prob else 1
                      for _ in range(chrom_length)]
        population.append(individual)

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
    """Log message to file and console"""
    import datetime
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] [{level}] {message}"
    
    if VERBOSE:
        print(log_line)
    
    with open(LOG_FILE, 'a') as f:
        f.write(log_line + '\n')

def initialize_directories():
    """Create necessary directories"""
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

# ======================= Chromosome Encoding Notes =======================
"""
CHROMOSOME ENCODING (Stage-Level Precision — Option A):

For an N-point FFT using Radix-2 DIT:
- Stages: log₂(N)
- Hardware: one butterfly_wrapper instance per stage
  (all N/2 butterflies in a stage share the same precision)

Chromosome format (length = num_stages × 2):
  [s0_mult, s0_add, s1_mult, s1_add, ..., sₙ_mult, sₙ_add]

Where:
  sᵢ_mult: Multiplier precision for stage i (0=FP4, 1=FP8)
  sᵢ_add : Adder precision for stage i     (0=FP4, 1=FP8)

Example for 8-point FFT (3 stages):
  Chromosome length = 6
  [s0_mult, s0_add, s1_mult, s1_add, s2_mult, s2_add]
"""

# Initialize at import time
initialize_directories()