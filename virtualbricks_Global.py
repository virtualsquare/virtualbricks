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





def RandMac():
	# put me into VM utilities, please.
	random.seed()
	mac = "00:aa:"
	mac = mac +"%02x:" % random.getrandbits(8)
	mac = mac +"%02x:" % random.getrandbits(8)
	mac = mac +"%02x:" % random.getrandbits(8)
	mac = mac +"%02x" % random.getrandbits(8)
	return mac

