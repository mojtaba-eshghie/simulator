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
import copy
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


    def calculate_max_depth(self):
        if Metas.DODAG_PICTURE:
            Metas.MAX_DEPTH = 0
            first_level = Metas.DODAG_PICTURE[0]
            for mote in first_level:
                while self.motes[mote].node.left_most_child:
                    Metas.MAX_DEPTH += 1
                    mote = self.motes[mote].node.left_most_child


    def calc_rx_tx_sum_reverse(self):
        if Metas.DODAG_PICTURE:
            for mote in self.motes:
                mote.tx_flows_sum = 0
                mote.rx_flows_sum = 0
            #firstly lets deepcopy each node object into another object
            this_iterate_leaves = set()
            for mote in self.motes:
                if mote.node.left_most_child is None:
                    #then this mote is a leaf and we want it,
                    #we need to find its parent, and right-childs
                    parent = mote.node.parent
                    kids = Metas.DODAG_PICTURE[parent]
                    #now we need to do the shit to this parent's kids
                    if kids:
                        #kids list is not empty,
                        for kid in kids:
                            if not self.motes[kid].tx_flows_sum:
                                self.motes[kid].tx_flows_sum = self.motes[kid].flow['cells']
                            #find the parent's tx_flows_sum and rx_flows_sum
                            self.motes[parent].rx_flows_sum += self.motes[kid].flow['cells']
                            #remove the kid we have been doing so to.
                        self.motes[parent].tx_flows_sum = self.motes[parent].rx_flows_sum + self.motes[parent].flow['cells']

                        this_iterate_leaves.add(parent)
            #print this_iterate_leaves

            for i in range(Metas.MAX_DEPTH):
                #print 'this iteration leaves:'
                #print this_iterate_leaves
                temp_leaves = copy.deepcopy(this_iterate_leaves)
                this_iterate_leaves = set()
                for mote in temp_leaves:
                    if self.motes[mote].node.left_most_child is None:
                        # then this mote is a leaf and we want it,
                        # we need to find its parent, and right-childs
                        parent = mote.node.parent
                        kids = Metas.DODAG_PICTURE[parent]
                        # now we need to do the shit to this parent's kids
                        if kids:
                            # kids list is not empty,
                            for kid in kids:
                                if not self.motes[kid].tx_flows_sum:
                                    self.motes[kid].tx_flows_sum = self.motes[kid].flow['cells']
                                # find the parent's tx_flows_sum and rx_flows_sum
                                self.motes[parent].rx_flows_sum += self.motes[kid].flow['cells']
                                # remove the kid we have been doing so to.
                            self.motes[parent].tx_flows_sum = self.motes[parent].rx_flows_sum + self.motes[parent].flow['cells']
                            this_iterate_leaves.add(parent)




    def give_out_tree(self):
        if Metas.DODAG_PICTURE:
            for device in self.motes:
                if device.id == 0:
                    device.node.parent = None
                    try:
                        device.node.left_most_child = Metas.DODAG_PICTURE[0][0]
                        device.node.right_sibling = None
                    except Exception:
                        print 'couldn\'t assign device.node.left_most_child'
                else:
                    #in case the node is not root
                    if device.id in Metas.DODAG_PICTURE.keys():
                        device.node.left_most_child = Metas.DODAG_PICTURE[device.id][0]
                        #in order to find the right-sibling, we need to find the parent of this guy,
                        #which means that we have to search inside the lists of values inside DODAG_PICTURE
                        for p, kds in Metas.DODAG_PICTURE.items():
                            if device.id in kds:
                                #put the then we have found the parent which is p
                                device.node.parent = p
                                #now to find the right sibling of this guy,
                                try:
                                    device.node.right_sibling = kds[kds.index(device.id) + 1]
                                except IndexError:
                                    device.node.right_sibling = None
                    else:
                        #in case that the device is a real leaf
                        device.node.left_most_child = None
                        #now to find the parent and right-sibling:
                        for p, kds in Metas.DODAG_PICTURE.items():
                            if device.id in kds:
                                #then we have found the node parent,
                                device.node.parent = p
                                #using that parent to find the right-sibling
                                try:
                                    device.node.right_sibling = kds[kds.index(device.id) + 1]
                                except IndexError:
                                    device.node.right_sibling = None




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

        for mote in self.motes:
            print 'mote with id: {0}, has such node structure:{1}, with rank {2}'.format(mote.id, mote.node, mote.rank)

        print('max rank is {0}'.format(Metas.MAX_DEPTH))
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
            self.give_out_tree()
            self.calc_rx_tx_sum_reverse()
            self.calculate_max_depth()
            # find correct index in schedule
            i = 0
            while i<len(self.events) and (self.events[i][0]<asn or (self.events[i][0]==asn and self.events[i][1]<=priority)):
                i +=1
            
            # add to schedule
            #self.calculate_rx_tx_sum()


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

