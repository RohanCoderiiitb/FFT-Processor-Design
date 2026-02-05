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
GENERATIONS=100
SEED=20
CLOCK_PERIOD=10

MUTATION_RATE=0.1
CROSSOVER_RATE=0.1
OBJECTIVES=2

CURRENT_GEN=0
SOLUTION_THREADS=25

FITNESS='fitness.npy'

DPI=200

random.seed(SEED)
#----------------------- user variables --------------------------#


