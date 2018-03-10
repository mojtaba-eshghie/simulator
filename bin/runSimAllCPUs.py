#!/usr/bin/python
'''
\brief Start batch of simulations concurrently.
Workload is distributed equally among CPU cores.
\author Thomas Watteyne <watteyne@eecs.berkeley.edu>
'''

import os
import time
import math
import multiprocessing

MIN_TOTAL_RUNRUNS = 20

def runOneSim(params):
    (cpuID,numRuns,numMotes,scheduler,numBroad,overlapBroad,rpl,otf,top) = params
    command     = []
    command    += ['python ./runSimOneCPU.py']  #emunicio
    command    += ['--numRuns {0}'.format(numRuns)]
    command    += ['--numMotes {0}'.format(numMotes)]
    command    += ['--scheduler {0}'.format(scheduler)]
    command    += ['--numBroadcastCells {0}'.format(numBroad)]
    command    += ['--overlappingBrCells {0}'.format(overlapBroad)]
    command    += ['--dioPeriod {0}'.format(rpl)]
    command    += ['--otfHousekeepingPeriod {0}'.format(otf)]
    command    += ['--sixtopHousekeepingPeriod {0}'.format(top)]
    command    += ['--simDataDir simData_{3}-{4}_rpl_{0}_otf_{1}_sixtop_{2}'.format(rpl,otf,top,scheduler,numBroad)]
    command    += ['--cpuID {0}'.format(cpuID)]
    #command    += ['&']
    command     = ' '.join(command)
    
    os.system(command)

def printProgress(num_cpus):
    while True:
        time.sleep(1)
        output     = []
        for cpu in range(num_cpus):
            with open('cpu{0}.templog'.format(cpu),'r') as f:
                output += ['[cpu {0}] {1}'.format(cpu,f.read())]
        allDone = True
        for line in output:
            if line.count('ended')==0:
                allDone = False
        output = '\n'.join(output)
        #os.system('clear')  #emunicio
        #print output
        if allDone:
            break
    for cpu in range(num_cpus):
        os.remove('cpu{0}.templog'.format(cpu))

if __name__ == '__main__':

    numMotes=os.sys.argv[1]
    scheduler=os.sys.argv[2]
    numBroad=os.sys.argv[3]
    overlapBroad=os.sys.argv[4]
    rpl=os.sys.argv[5]
    otf=os.sys.argv[6]
    top=os.sys.argv[7]

    print "Simulating with "+str(numMotes)
    print "Simulating with "+str(overlapBroad)
    multiprocessing.freeze_support()
    num_cpus = multiprocessing.cpu_count()
    num_cpus = 20
    print num_cpus
    runsPerCpu = int(math.ceil(float(MIN_TOTAL_RUNRUNS)/float(num_cpus)))
    pool = multiprocessing.Pool(num_cpus)
    pool.map_async(runOneSim,[(i,runsPerCpu,numMotes,scheduler,numBroad,overlapBroad,rpl,otf,top) for i in range(num_cpus)])
    printProgress(num_cpus)
    #raw_input("Done. Press Enter to close.")
    print "Finish."
