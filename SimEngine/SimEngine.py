#!/usr/bin/python
'''
\brief Discrete-event simulation engine.

\author Thomas Watteyne <watteyne@eecs.berkeley.edu>
\author Kazushi Muraoka <k-muraoka@eecs.berkeley.edu>
\author Nicola Accettura <nicola.accettura@eecs.berkeley.edu>
\author Xavier Vilajosana <xvilajosana@eecs.berkeley.edu>
'''

#============================ logging =========================================

import logging
class NullHandler(logging.Handler):
    def emit(self, record):
        pass
log = logging.getLogger('SimEngine')
log.setLevel(logging.ERROR)
log.addHandler(NullHandler())

#============================ imports =========================================

import threading

import Propagation
import Topology
import Mote
from Mote import Metas
import SimSettings
import time
import inspect
import random

#============================ defines =========================================

#============================ body ============================================

class SimEngine(threading.Thread):
    
    #===== start singleton
    _instance      = None
    _init          = False
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(SimEngine,cls).__new__(cls, *args, **kwargs)
        return cls._instance
    #===== end singleton
    
    def __init__(self,runNum=None,failIfNotInit=False):
        
        if failIfNotInit and not self._init:
            raise EnvironmentError('SimEngine singleton not initialized.')
        
        #===== start singleton
        if self._init:
            return
        self._init = True
        #===== end singleton
        
        # store params
        self.runNum                         = runNum
        
        # local variables
        self.dataLock                       = threading.RLock()
        self.pauseSem                       = threading.Semaphore(0)
        self.simPaused                      = False
        self.goOn                           = True
        self.asn                            = 0
        self.startCb                        = []
        self.endCb                          = []
        self.events                         = []
        self.settings                       = SimSettings.SimSettings()
        self.propagation                    = Propagation.Propagation()
        self.motes                          = [Mote.Mote(id) for id in range(self.settings.numMotes)]
        self.topology                       = Topology.Topology(self.motes)
        self.topology.createTopology()
        self.all_nodes = self.motes

        # load flows into motes & boot all motes:
        random.seed(time.time())
        for i in range(len(self.motes)):

            choice = random.choice(Mote.Mote.FLOWS_INFO)
            self.motes[i].flow.update({
                'id':choice['id'],
                'priority': choice['priority'],
                'cells': choice['cells']
            })
            print(self.motes[i].flow)
            self.motes[i].boot()



        self.initTimeStampTraffic          = 0
        self.endTimeStampTraffic           = 0       
        
        # initialize parent class
        threading.Thread.__init__(self)
        #print "Initialized Parent class"
        self.name                           = 'SimEngine'
        self.scheduler=self.settings.scheduler

        

	#emunicio
        self.timeElapsedFlow=0        
        self.totalTx=0
        self.totalRx=0
        self.dropByCollision=0
        self.dropByPropagation=0
        self.bcstReceived=0
        self.bcstTransmitted=0
	self.packetsSentToRoot=0  #total packets sent from all nodes to the root node
        self.packetReceivedInRoot=0 #total packets sent from all nodes to the root node
	self.olGeneratedToRoot=0  #average throughput generated	
	self.thReceivedInRoot=0   #average throughput received
     
        # emunicio settings
        self.numBroadcastCell=self.settings.numBroadcastCells
        
    # ===== extra functions to get things done
    def calculate_rx_tx_sum_reverse_tree_traversal(self):
        first_round = True
        all_parents = [parent for parent in Metas.DODAG_PICTURE.keys()]
        all_nodes = self.motes
        all_leafs = list(set(all_nodes) - set(all_parents))

        temp_dodag_picture = Metas.DODAG_PICTURE

        while True:
            #needs a review of each round
            if not temp_dodag_picture:
                break

            for leaf in all_leafs:
                if first_round:
                    #these are the first rounders!, the real leaves of original dodag
                    self.motes[leaf].rx_flows_sum = 0
                    self.motes[leaf].tx_flows_sum = self.motes[leaf].flow['cells']
                    first_round = False

                    #now delete the leaves from dodag picture
                    for leaf in all_leafs:
                        if leaf in temp_dodag_picture.keys():
                            del temp_dodag_picture[leaf]

                    for node, kids in temp_dodag_picture:
                        if leaf in kids:
                            del kids[kids.index(leaf)]
                else:
                    for kid in Metas.DODAG_PICTURE[leaf]:
                        self.motes[leaf].rx_flows_sum = self.motes[leaf].rx_flows_sum + self.motes[kid].flow['cells']
                    self.motes[leaf].tx_flows_sum = self.motes[leaf].tx_flows_sum + self.motes[leaf].rx_flows_sum

                    #now delete the leaves from dodag picture
                    for leaf in all_leafs:
                        if leaf in temp_dodag_picture.keys():
                            del temp_dodag_picture[leaf]

                    for node, kids in temp_dodag_picture:
                        if leaf in kids:
                            del kids[kids.index(leaf)]


            all_nodes = [parent for parent in temp_dodag_picture.keys()]
            for key, value in temp_dodag_picture.items():
                for val in value:
                    if val in all_nodes:
                        continue
                    else:
                        all_nodes.append(val)
            all_parents = [parent for parent in temp_dodag_picture.keys()]
            all_leafs = list(set(all_nodes) - set(all_parents))




            #delete leafs completely


    def calculate_rx_tx_sum(self):
        temp_dodag_picture = Metas.DODAG_PICTURE
        for parent, kids in temp_dodag_picture.items():
            #kids is a list containing the direct predecessor of a node
            self.motes[parent].rx_flows_sum = 0
            self.motes[parent].tx_flows_sum = self.motes[parent].flow['cells']
            for kid in kids:
                #kid is the desired child id (self.motes[id].....)
                #motes[id].flow is usable, keys are "id", "priority", "cells"
                self.motes[parent].rx_flows_sum = self.motes[parent].rx_flows_sum + self.motes[kid].flow['cells']
            self.motes[parent].tx_flows_sum = self.motes[parent].tx_flows_sum + self.motes[parent].rx_flows_sum

            all_parents = [parent for parent in Metas.DODAG_PICTURE.keys()]
            all_nodes = [node.id for node in self.motes]
            all_leafs = list(set(all_nodes) - set(all_parents))
            for leaf in all_leafs:
                self.motes[leaf].rx_flows_sum = 0
                self.motes[leaf].tx_flows_sum = self.motes[leaf].flow['cells']
            self.motes[0].tx_flows_sum = 0

    def newfunction(self):
        print self.motes


    def destroy(self):
        
        print "Drops by collision "+str(self.dropByCollision)
	print "Drops by propagation "+str(self.dropByPropagation)
        print "Broadcast received "+str(self.bcstReceived)
        print "Broadcast sent "+str(self.bcstTransmitted)
        if self.bcstTransmitted!=0: #avoiding zero division
            print "Broadcast PER "+str(float(self.bcstReceived)/self.bcstTransmitted)
        print Mote.Metas.CHILD_PARENT_PAIRS
        print "TX total "+str(self.totalTx)
        print "RX total "+str(self.totalRx)
        print "PER "+str(float(self.totalRx)/self.totalTx)
        print "some simulation results:"
        for i in range(self.motes.__len__()):
            print 'for node {0}'.format(str(i))
            print str(self.motes[i].flow)
            print('the sum of tx flows is {0}'.format(self.motes[i].tx_flows_sum))
            print('the sum of rx flows is {0}'.format(self.motes[i].rx_flows_sum))
            print('***********************')
            print('::::::::::::this is the tree structure:::::::::::')
            print(Metas.DODAG_PICTURE)
        self.propagation.destroy()
        
        # destroy my own instance
        self._instance                      = None
        self._init                          = False
    
    #======================== thread ==========================================
    
    def run(self):
        ''' event driven simulator, this thread manages the events '''
        #print "Initializing parent "+ str(len(self.startCb))
        # log

        print self.startCb
        log.info("thread {0} starting".format(self.name))
        #print "Simulating nodes: "+str(self.settings.numMotes)
        # schedule the endOfSimulation event
        self.scheduleAtAsn(
            asn         = self.settings.slotframeLength*self.settings.numCyclesPerRun,
            cb          = self._actionEndSim,
            uniqueTag   = (None,'_actionEndSim'),
        )
        
        # call the start callbacks
        for cb in self.startCb:
            cb()
        
        # consume events until self.goOn is False
        while self.goOn:
            
            with self.dataLock:
                
                # abort simulation when no more events
                if not self.events:
                    log.info("end of simulation at ASN={0}".format(self.asn))
                    break
                               
                #emunicio, to avoid errors when exectuing step by step
		(a,b,cb,c)=self.events[0]
                if c[1]!='_actionPauseSim':                 
                       assert self.events[0][0] >= self.asn
                
		# make sure we are in the future
                assert self.events[0][0] >= self.asn

                # update the current ASN
                self.asn = self.events[0][0]
                
                # call callbacks at this ASN
                while True:
                        
                    if self.events[0][0]!=self.asn:
                        break
                    (_,_,cb,_) = self.events.pop(0)
                    cb()
        
        # call the end callbacks
        for cb in self.endCb:
            cb()
        
        # log
        log.info("thread {0} ends".format(self.name))
    
    #======================== public ==========================================
    
    #emunicio    
    def incrementStatDropByCollision(self):
        self.dropByCollision+=1
     
    def incrementStatDropByPropagation(self):  
        self.dropByPropagation+=1


    #=== scheduling
    
    def scheduleAtStart(self,cb):
        with self.dataLock:
            self.startCb    += [cb]
    
    def scheduleIn(self,delay,cb,uniqueTag=None,priority=0,exceptCurrentASN=True):
        ''' used to generate events. Puts an event to the queue '''
        
        with self.dataLock:
            asn = int(self.asn+(float(delay)/float(self.settings.slotDuration)))
            self.scheduleAtAsn(asn,cb,uniqueTag,priority,exceptCurrentASN)
    
    def scheduleAtAsn(self,asn,cb,uniqueTag=None,priority=0,exceptCurrentASN=True):
        ''' schedule an event at specific ASN '''
        
        # make sure we are scheduling in the future
        assert asn>self.asn
        
        # remove all events with same uniqueTag (the event will be rescheduled)
        if uniqueTag:
            self.removeEvent(uniqueTag,exceptCurrentASN)
        
        with self.dataLock:
            
            # find correct index in schedule
            i = 0
            while i<len(self.events) and (self.events[i][0]<asn or (self.events[i][0]==asn and self.events[i][1]<=priority)):
                i +=1
            
            # add to schedule
            #self.calculate_rx_tx_sum()
            #self.calculate_rx_tx_sum_reverse_tree_traversal()
            self.newfunction()


            self.events.insert(i,(asn,priority,cb,uniqueTag))



    def removeEvent(self,uniqueTag,exceptCurrentASN=True):
        with self.dataLock:
            i = 0
            while i<len(self.events):
                if self.events[i][3]==uniqueTag and not (exceptCurrentASN and self.events[i][0]==self.asn):
                    self.events.pop(i)
                else:
                    i += 1
    
    def scheduleAtEnd(self,cb):
        with self.dataLock:
            self.endCb      += [cb]
    
    #=== play/pause
    
    def play(self):
        self._actionResumeSim()
    
    def pauseAtAsn(self,asn):
        #print "Pausing simulation"
        if not self.simPaused:
            self.scheduleAtAsn(
                asn         = asn,
                cb          = self._actionPauseSim,
                uniqueTag   = ('SimEngine','_actionPauseSim'),
            )
    
    #=== getters/setters
    
    def getAsn(self):
        return self.asn
        
    #======================== private =========================================
    
    def _actionPauseSim(self):
        if not self.simPaused:
            self.simPaused = True
            self.pauseSem.acquire()
    
    def _actionResumeSim(self):
        if self.simPaused:
            self.simPaused = False
            self.pauseSem.release()
    
    def _actionEndSim(self):
        
        with self.dataLock:
            self.goOn = False
            	    
            for mote in self.motes:
                mote._log_printEndResults()

