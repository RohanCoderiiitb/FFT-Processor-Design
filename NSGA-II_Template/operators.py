#!/usr/bin/python3
"""
Author: Bhargav D V, Research Scholar, IIITB, under guidance of Prof. Madhav Rao.
This script is used to implement operators for optimization algorithms.
"""

#------------import modules----------------#
from globalVariables import *
import numpy as np
from pymoo.core.crossover import Crossover
from pymoo.core.mutation import Mutation
import math
from optimizationUtils import determineDecisionVariableLimit
import copy
#------------import modules----------------#


#This is a random Resetting Mutation class
class randomResettingMutation(Mutation):
    def _do(self, problem, X, **kwargs):
        global CURRENT_GEN
        global MUTATION_RATE
        #MUTATION_RATE = math.exp(-(CURRENT_GEN)/GENERATIONS)

        Xp=np.copy(X)
        for i in range(len(Xp)):

            #randomly select a gene from current chromosome to reset to different value within the limit
            index=random.randint(0,len(X[i])-1)
            
            if(random.random()<MUTATION_RATE):
                Xp[i][index]=random.randint(problem.xl[index],problem.xu[index])

    

        return Xp
    
#This is a Swap Mutation class
class SwapMutation(Mutation):
    def _do(self, problem, X, **kwargs):
        global CURRENT_GEN
        global MUTATION_RATE
        #MUTATION_RATE = math.exp(-(CURRENT_GEN)/GENERATIONS)


        Xp=np.copy(X)
        #capturing the unique limits and its corresponding indices 
        eachLimit=[]
        uniqueUpperLimits=list(set(problem.xu))
        for i in range(len(uniqueUpperLimits)):
            limit=[]
            for j in range(len(problem.xu)):
                if(uniqueUpperLimits[i]==problem.xu[j]):
                    limit.append(j)
            eachLimit.append(limit)

        for i in range(len(Xp)):
            tempEachLimit=copy.deepcopy(eachLimit)

            #randomly select a gene from current chromosome to swap to different value within the limit and same limit gene
            index=random.randint(0,len(tempEachLimit)-1)
            
            if(random.random()<MUTATION_RATE):
                index1=random.choice(tempEachLimit[index])
                tempEachLimit[index].remove(index1)
                index2=random.choice(tempEachLimit[index])
                
                Xp[i][index1], Xp[i][index2] = Xp[i][index2],Xp[i][index1]

        return Xp


#This is uniform crossover where it exchanges each gene between two parent solutions
class uniformCrossover(Crossover):

    def __init__(self, n_points, **kwargs):
        super().__init__(2, 2, **kwargs)
        self.n_points = n_points

    def _do(self, problem, X, **kwargs):

        global CURRENT_GEN
        
        #CROSSOVER_RATE = math.exp(-(CURRENT_GEN)/GENERATIONS)
        x=(CURRENT_GEN/GENERATIONS)
        #CROSSOVER_RATE = 0.5 * math.exp(-((x-0.5)**2)/2)

        Xp=np.copy(X)

        choicesSolution=list(range(len(Xp)))
        for _ in range(len(choicesSolution)//2):
            index1=random.choice(choicesSolution)
            choicesSolution.remove(index1)
            index2=random.choice(choicesSolution)
            choicesSolution.remove(index2)

            for i in range(len(Xp[0])):
                if(random.random()<CROSSOVER_RATE):
                    Xp[index1][i], Xp[index2][i] = Xp[index2][i],Xp[index1][i]

        return Xp