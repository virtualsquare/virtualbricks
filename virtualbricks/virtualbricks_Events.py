#!/usr/bin/python
# coding=utf-8

##    Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
##    Copyright (C) 2011 Virtualbricks team
##
##    This program is free software; you can redistribute it and/or
##    modify it under the terms of the GNU General Public License
##    as published by the Free Software Foundation; either version 2
##    of the License, or (at your option) any later version.
##
##    This program is distributed in the hope that it will be useful,
##    but WITHOUT ANY WARRANTY; without even the implied warranty of
##    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##    GNU General Public License for more details.
##
##    You should have received a copy of the GNU General Public License
##    along with this program; if not, write to the Free Software
##    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from threading import Timer
import time #used for time.time() can probably be removed later

#===============================================================================
# class Event():
#    def __init__(self,_factory,_name):
#        #self.id=id
#        self.name=_name
#        self.actions=list()
#        self.delay=0
#        self.timer=Timer(self.delay,self.doActions,())
#    
#    def start(self):
#        self.timer.start()
#    
#    def stop(self):
#        self.timer.cancel()
# 
#    def doActions(self):
#        for action in self.actions:
#            action()
# 
#    def addAction(self,action):
#        self.actions.append(action)
# 
#    def delAction(self,action):
#        self.actions.remove(action)
# 
#    def setTimer(self,delay):
#        self.delay=delay
#        self.timer=Timer(delay,self.doActions,())
#===============================================================================

class eventCollation():
    def __init__(self,name):
        self.name=name
        self.events=[]

    def startAll(self):
        for event in self.events:
            event.poweron()

    def stopAll(self):
        for event in self.events:
            event.poweroff()

    def addEvent(self,event):
        self.events.append(event)
#Sorting may be moved in StartAll/StopAll
#but doing this here lower the "delta"
#after calling StartAll/StopAll.
#The same about RemoveEvent.
        self.events.sort(key=lambda delay:event.delay)

    def removeEvent(self,event):
        if event in self.events:
            self.events.remove(event)
            self.events.sort(key=lambda delay:event.delay)
        else:
            print "Event [id=%s,name=\"%s\"], not found into event list!" % (event.id,event.name)

