#!/usr/bin/python
import gtk
import gtk.glade
import sys
import os
import ConfigParser
import time
import re
import subprocess 
import gobject
import signal
import string
import random
import threading



VDEPATH="/usr/bin"
HOME=os.path.expanduser("~")
MYPATH=HOME + "/.virtualbricks"

#errors, please put us in a common file
ENOERROR	= 0
ENOTCONFIGURED = 1
ENOTPROPERLYCONNECTED = 2
ELINKDOWN = 4
ENORESOURCE = 8
# 

def RandMac():
	# put me into VM utilities, please.
	random.seed()
	mac = "00:aa:"
	mac = mac +"%02x:" % random.getrandbits(8)
	mac = mac +"%02x:" % random.getrandbits(8)
	mac = mac +"%02x:" % random.getrandbits(8)
	mac = mac +"%02x" % random.getrandbits(8)
	return mac
