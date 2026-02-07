"""
Global Variables for Mixed-Precision FFT Optimization
CORRECTED VERSION: Per-butterfly precision control

Chromosome sizes for different FFT sizes:
- FFT-8:    12 butterflies × 2 = 24 genes
- FFT-16:   32 butterflies × 2 = 64 genes
- FFT-32:   80 butterflies × 2 = 160 genes
- FFT-64:   192 butterflies × 2 = 384 genes
- FFT-128:  448 butterflies × 2 = 896 genes
- FFT-256:  1024 butterflies × 2 = 2048 genes
- FFT-512:  2304 butterflies × 2 = 4608 genes
- FFT-1024: 5120 butterflies × 2 = 10240 genes
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
    Calculate chromosome size for per-butterfly precision
    
    For N-point FFT:
    - Total butterflies = (N/2) × log₂(N)
    - Chromosome length = 2 × total_butterflies
    
    Args:
        fft_size: FFT size (power of 2)
    
    Returns:
        Chromosome length (number of genes)
    """
    num_stages = int(math.log2(fft_size))
    butterflies_per_stage = fft_size // 2
    total_butterflies = butterflies_per_stage * num_stages
    chromosome_length = 2 * total_butterflies
    return chromosome_length

# Print chromosome sizes for reference
print("Chromosome sizes for different FFT sizes:")
for size in [8, 16, 32, 64, 128, 256, 512, 1024]:
    chrom_size = calculate_chromosome_size(size)
    total_bf = (size // 2) * int(math.log2(size))
    print(f"  FFT-{size:<4}: {total_bf:>4} butterflies × 2 = {chrom_size:>5} genes")

# ======================= Vivado Configuration =======================
VIVADO_PATH = '/tools/Xilinx/Vivado/2023.2/bin/vivado'
VIVADO_BATCH_MODE = True
CLOCK_PERIOD = 10.0          # ns (100 MHz target)
FPGA_DEVICE = 'xc7z020clg484-1'

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
    Generate initial population with domain-knowledge strategies
    instead of pure random initialization
    
    Strategies:
    1. All FP4 (minimum power)
    2. All FP8 (maximum performance)
    3. Progressive precision (FP4 early, FP8 later)
    4. Alternating precision
    5. Random variations
    """
    from fft_template_generator_corrected import FFTTemplateGeneratorPerButterfly
    
    gen = FFTTemplateGeneratorPerButterfly(fft_size)
    chrom_length = gen.get_chromosome_length()
    population = []
    
    # Strategy 1: All FP4
    population.append([0] * chrom_length)
    
    # Strategy 2: All FP8
    population.append([1] * chrom_length)
    
    # Strategy 3: Progressive precision per stage
    progressive = []
    for stage in range(gen.num_stages):
        prec = 1 if stage >= gen.num_stages // 2 else 0
        for bf in range(gen.butterflies_per_stage):
            progressive.extend([prec, prec])
    population.append(progressive)
    
    # Strategy 4: Progressive precision inverse
    progressive_inv = []
    for stage in range(gen.num_stages):
        prec = 0 if stage >= gen.num_stages // 2 else 1
        for bf in range(gen.butterflies_per_stage):
            progressive_inv.extend([prec, prec])
    population.append(progressive_inv)
    
    # Strategy 5: Multipliers FP8, Adders FP4
    mult_fp8 = []
    for _ in range(gen.total_butterflies):
        mult_fp8.extend([1, 0])  # FP8 mult, FP4 add
    population.append(mult_fp8)
    
    # Strategy 6: Multipliers FP4, Adders FP8
    mult_fp4 = []
    for _ in range(gen.total_butterflies):
        mult_fp4.extend([0, 1])  # FP4 mult, FP8 add
    population.append(mult_fp4)
    
    # Strategy 7-8: Random with 70% FP4, 30% FP8 and vice versa
    for fp4_prob in [0.7, 0.3]:
        individual = []
        for _ in range(chrom_length):
            individual.append(0 if random.random() < fp4_prob else 1)
        population.append(individual)
    
    # Fill rest with pure random
    while len(population) < pop_size:
        individual = [random.randint(0, 1) for _ in range(chrom_length)]
        population.append(individual)
    
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
CHROMOSOME ENCODING (Per-Butterfly Precision):

For an N-point FFT using Radix-2 DIT:
- Stages: log₂(N)
- Butterflies per stage: N/2 (operating in parallel)
- Total butterflies: (N/2) × log₂(N)

Chromosome format:
[bf0_mult, bf0_add, bf1_mult, bf1_add, ..., bfₖ_mult, bfₖ_add]

Where:
- bfᵢ_mult: Multiplier precision for butterfly i (0=FP4, 1=FP8)
- bfᵢ_add: Adder precision for butterfly i (0=FP4, 1=FP8)
- k = total_butterflies - 1

Example for 8-point FFT (3 stages, 4 butterflies/stage, 12 total):
Chromosome length = 24

Layout by stage:
Stage 0: [bf0_m, bf0_a, bf1_m, bf1_a, bf2_m, bf2_a, bf3_m, bf3_a]  (8 genes)
Stage 1: [bf4_m, bf4_a, bf5_m, bf5_a, bf6_m, bf6_a, bf7_m, bf7_a]  (8 genes)
Stage 2: [bf8_m, bf8_a, bf9_m, bf9_a, bf10_m, bf10_a, bf11_m, bf11_a]  (8 genes)
"""

# Initialize at import time
initialize_directories()
