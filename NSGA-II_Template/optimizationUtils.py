"""
Author: Bhargav D V, Research Scholar, IIITB, under guidance of Prof. Madhav Rao.
This script is used to implement utility or helper Class or functions for genetic algorithm.
"""


#------------import modules----------------#
from pymoo.core.mutation import Mutation
import random
import re
import numpy as np
import math
from pymoo.core.crossover import Crossover
from globalVariables import *
#------------import modules----------------#





#This class is used to get data of entire evolution
class MyCallback:
    def __init__(self):
        self.data = []

    def __call__(self, algorithm):
        # Extract the objective values for all solutions in the current population
        F = algorithm.pop.get('F')
        # Store the objective values
        self.data.append(F)



    
#This funciton is used to determine the upper and lower limits for decision variables
#Change here for your problem statement
def determineDecisionVariableLimit():
    lowerLimit=[0]*8
    upperLimit=[3]*8

    return [lowerLimit,upperLimit]