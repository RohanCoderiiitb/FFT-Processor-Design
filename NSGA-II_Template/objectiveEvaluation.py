"""
Author: Bhargav D V, Research Scholar, IIITB, under guidance of Prof. Madhav Rao.
This script is used to implement genetic algorithm flow.
"""


#------------import modules----------------#
from globalVariables import *
from optimizationUtils import determineDecisionVariableLimit
from pymoo.core.problem import Problem
import numpy as np
import re
import os
from multiprocessing.pool import ThreadPool
from hardwareMetrics import runSynthesis
from concurrent.futures import ThreadPoolExecutor, as_completed
#------------import modules----------------#





#this is custom problem formulation class for Genetic Algorithm
class customProblem(Problem):

    def __init__(self,**kwargs):
        
        self.xl,self.xu=determineDecisionVariableLimit()

        #Determine the number of variables
        variables=len(self.xl)

        
        super().__init__(n_var=variables, n_obj=OBJECTIVES, n_ieq_constr=1,n_constr=0,elementwise_evaluation=False, xl=self.xl, xu=self.xu,vtype=int,**kwargs)

    #NSGA2 problem in-built function to evaluate solution.
    def _evaluate(self, X, out, *args, **kwargs):
        global CURRENT_GEN

        # Write current generation to a file to keep track of generations, 
        with open(f'generation.txt', 'w') as genFile:
            genFile.write(str(CURRENT_GEN))
        
        CURRENT_GEN += 1
        #input('press')
        F = [None] * len(X)
        G = [None] * len(X)

        # Parallel evaluation using ThreadPoolExecutor, SOLUTIONS_THREADS is used to define how many threads are being used for evalaution
        with ThreadPoolExecutor(max_workers=SOLUTION_THREADS) as executor:
            futures = {executor.submit(self.evaluateProblem, X[k], k): k for k in range(len(X))}

            for future in as_completed(futures):
                k = futures[future]
                
                f_val, g_val = future.result()
                F[k] = f_val
                G[k] = g_val
                

        out["F"] = np.array(F)
        out["G"] = np.array(G)

    #this function is used to evaluate each solution independently and should return objectives and constraints
    def evaluateProblem(self,x,Z):
        

        #let say if number of objectives is 2, f1 and f2, return f1 and f2 in first list like below
        #let say your violation varaibles are 1, you can return the violation in second list as below v1
        f1=1
        f2=4


        v1=0

        return[[f1,f2],[v1]]