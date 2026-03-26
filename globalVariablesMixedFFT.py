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

Objectives (4 total, all minimised by NSGA-II):
  1. Power       (W)
  2. Area        (LUTs)
  3. Performance error  = WEIGHT_PERFORMANCE / (SQNR + 1)
  4. Latency     (normalised cycles)
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
OBJECTIVES = 3            # Power, Area, Performance, Latency  ← was 3

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
    """
    Calculate chromosome size for stage-level precision (Option A).

    For N-point FFT:
    - num_stages = log₂(N)
    - Chromosome length = 2 × num_stages  (one mult_prec + one add_prec per stage)
    """
    num_stages = int(math.log2(fft_size))
    chromosome_length = 2 * num_stages
    return chromosome_length

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
WEIGHT_AREA = 0.001
WEIGHT_PERFORMANCE = 50.0
# WEIGHT_LATENCY = 1.0         # Normalised latency objective weight

# ======================= Constraint Thresholds =======================
MAX_POWER_W = 3.0
MAX_AREA_LUTS = 10000
MIN_SQNR_DB = -10.0

# Maximum acceptable latency in normalised units.
# 2.0 means the design may be at most 2× the all-FP4 reference latency.
# MAX_LATENCY_NORM = 2.0

# Minimum clock frequency after Vivado place-and-route (MHz).
# Designs that fail timing closure at this frequency are infeasible.
# MIN_FREQ_MHZ = 80.0

# ======================= Latency Model Parameters =======================
# Combinational delay (ns) for each arithmetic unit type.
# Values are calibrated against Vivado timing reports for xc7a35t;
# adjust if you retarget to a different device or speed grade.
#
# In the radix-2 butterfly, the multiplier feeds the adder (serial critical
# path), so per-stage delay = mult_delay + add_delay + overhead.
#
# FP8_MULT_DELAY_NS = 6.5      # FP8 E4M3 complex multiplier
# FP4_MULT_DELAY_NS = 3.5      # FP4 E2M1 complex multiplier
# FP8_ADD_DELAY_NS  = 4.0      # FP8 E4M3 complex adder
# FP4_ADD_DELAY_NS  = 2.0      # FP4 E2M1 complex adder

# Fixed overhead per stage: memory read address setup + write arbitration
# + AGU pipeline register + routing congestion margin (ns).
# STAGE_OVERHEAD_NS = 2.0

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
    strat9 = []
    for stage in range(gen.num_stages):
        prec = 1 if stage < 2 else 0
        strat9.extend([prec, prec])
    population.append(strat9)

    # Strategy 10: FP8 mult + FP4 add at every stage.
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

Chromosome format (length = num_stages × 2):
  [s0_mult, s0_add, s1_mult, s1_add, ..., sₙ_mult, sₙ_add]

Where:
  sᵢ_mult: Multiplier precision for stage i (0=FP4, 1=FP8)
  sᵢ_add : Adder precision for stage i     (0=FP4, 1=FP8)

LATENCY MODEL:
  For each stage i:
    stage_critical_path = mult_delay[i] + add_delay[i] + STAGE_OVERHEAD_NS
      (mult and add are serial in the butterfly critical path)
    stage_pipeline_cycles = ceil(stage_critical_path / CLOCK_PERIOD)

  Total latency (cycles) = N (load) + Σ stage_pipeline_cycles + N (unload)

  Normalised latency = total_cycles / reference_cycles
    where reference_cycles uses all-FP8 delays.

  The 4th NSGA-II objective minimises normalised latency × WEIGHT_LATENCY.
  The 4th constraint enforces timing closure: WNS ≥ CLOCK_PERIOD − (1000/MIN_FREQ_MHZ).
"""

# Initialize at import time
initialize_directories()