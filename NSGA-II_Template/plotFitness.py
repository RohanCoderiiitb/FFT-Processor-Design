"""
Author: Bhargav D V, Research Scholar, IIITB, under guidance of Prof. Madhav Rao.
This script is used to generate fitness plots for evolutionary runs
"""

#-------------import packages---------------#
import numpy as np
import matplotlib.pyplot as plt
from globalVariables import *
#---------------import packages-------------#





def generateFitnessPlot():
    #read numpy array data
    
    
    #fitnessData=np.load(FITNESS)
    data=np.load(FITNESS[:-3]+'npz')
    previousBestFitness=1e5
    #print(fitnessData[0][1][0])




    #x axis
    #X=range(0,len(fitnessData))
    X=range(0,len(data.files))



    #X=range(0,101)
    #y axis
    FitnessPlot1=[]
    #mean_actual=21307064320/65536
    for name in data.files:
        gen = data[name]
    #for gen in fitnessData:
        euclideanValues=[]
        for value in gen:
            
            Sums=0
            for objective in range(len(value)):
                Sums=Sums+value[objective]**2
            euclideanValues.append((Sums)**0.5)
                #euclideanValues.append(((value[0]**2)+(value[1]**2))**0.5)
        bestFitness=np.mean(np.array((euclideanValues)))
        #bestFitness=min(euclideanValues)
        if(bestFitness<previousBestFitness):
            FitnessPlot1.append(bestFitness)
            previousBestFitness=bestFitness
        else:
            FitnessPlot1.append(previousBestFitness)

    
    plt.figure(dpi=DPI)
    #plt.title("MAE {} 8bit unsigned Multiplier Fitness Convergence".format(MAE))
    #plt.scatter(0, 3**0.5, color='red',label=f'Exact {DESIGN}')
    plt.plot(X,FitnessPlot1, "--",color="blue",)
    
    plt.xlabel('Generations', fontsize=14)
    plt.ylabel('Fitness', fontsize=14)
    plt.legend()

    #You can use this for saving the image
    #plt.savefig('fitness.png')
    #plt.close()
    plt.show()

        


generateFitnessPlot()