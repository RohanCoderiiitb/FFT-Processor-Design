"""
Author: Bhargav D V, Research Scholar, IIITB, under guidance of Prof. Madhav Rao.
This script is used to generate optimized pareto optimal reconfigurable approximate circuits
"""


#------------import modules----------------#
from globalVariables import *
from objectiveEvaluation import customProblem
from optimizationUtils import MyCallback
from operators import *
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.soo.nonconvex.pso import PSO
from pymoo.algorithms.soo.nonconvex.ga import GA
from pymoo.operators.crossover.pntx import PointCrossover
from pymoo.operators.sampling.rnd import IntegerRandomSampling
from pymoo.termination import get_termination
from pymoo.optimize import minimize
import numpy as np
#------------import modules----------------#




def runFramework():
    
    problem=customProblem()
    callback = MyCallback()
    #You can use available default operator in pymoo or use the ones described in operators.py
    algorithm = NSGA2(pop_size=POPULATION,sampling=IntegerRandomSampling(),crossover=uniformCrossover(n_points=1,prob=0.1),
        mutation=randomResettingMutation())
    #algorithm = PSO(pop_size=POPULATION,sampling=IntegerRandomSampling())
    termination = get_termination("n_gen", GENERATIONS)
    res = minimize(problem,
                    algorithm,
                    termination,
                    save_history=False,
                    callback=callback,
                    seed=SEED,
                    verbose=True)
    
    print('Objectives')
    #objective values
    print(res.F)
    objectives=np.array(list(res.F))
    solution=np.array(list(res.X.astype(int)))

    #solutions
    print('Solutions')
    print(res.X)


    # Convert data to numpy array for easier manipulation
    data = callback.data
    print(len(data))
    #save fitness evluations in numpy array
    np.savez('{}npz'.format(FITNESS[:-3]),*data)

    np.save('{}'.format(FITNESS),np.array(data))


if(__name__=='__main__'):
    runFramework()