"""
Author: Bhargav D V, Research Scholar, IIITB, under guidance of Prof. Madhav Rao.
This script contains global variables used across scripts.
"""


#------------import modules----------------#
from multiprocessing.pool import ThreadPool
import random
#------------import modules----------------#

#----------------------- user variables --------------------------#
POPULATION=20
GENERATIONS=50
SEED=20
CLOCK_PERIOD=10

MUTATION_RATE=0.15
CROSSOVER_RATE=0.8
OBJECTIVES=2

CURRENT_GEN=0
SOLUTION_THREADS=4

FITNESS='fitness.npy'

DPI=200

random.seed(SEED)
#----------------------- user variables --------------------------#

### FFT Configuration
FFT_SIZES = [8, 16, 32, 64, 128, 256, 512, 1024]
CLOCK_PERIOD = 10.0      # Target clock period (ns)
FPGA_DEVICE = 'xc7a100tcsg324-1'  # Target device

### Optimization Constraints
MAX_POWER_W = 2.0        # Maximum power (Watts)
MAX_AREA_LUTS = 5000     # Maximum LUT count
MIN_SQNR_DB = 20.0       # Minimum SQNR (dB)