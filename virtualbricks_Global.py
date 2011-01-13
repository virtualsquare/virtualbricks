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
CONFIGFILE=HOME + "/.virtualbricks.conf"


def RandMac():
	# put me into VM utilities, please.
	random.seed()
	mac = "00:aa:"
	mac = mac +"%02x:" % random.getrandbits(8)
	mac = mac +"%02x:" % random.getrandbits(8)
	mac = mac +"%02x:" % random.getrandbits(8)
	mac = mac +"%02x" % random.getrandbits(8)
	return mac

class Settings:
	def __init__(self, f):
		self.configfile = None
		#default config
		self.bricksdirectory = HOME + "/virtualbricks"
		self.iconsize = 32
		self.term = "xterm"
		self.sudo = "gksu"
		self.qemupath="/usr/bin"
		self.baseimages = HOME + "/virtualbricks/img"
		self.kvm = "1"
		self.ksm = "1"
		self.kqemu = "0"
		self.cdroms = ""
		self.vdepath="/usr/bin"
		self.python = "0"
		self.femaleplugs = "0"

		try:
			self.configfile = open(f, "r+")
		except Exception:
			try:
				self.configfile = open(f, "w+")
			except Exception:
				print "FATAL: Cannot open config file!!"
				return
			else:
				self.store()
				print "CONFIGURATION: WRITTEN."
		else:
			self.load()
			print "CONFIGURATION: LOADED."

	def load(self):
		for l in self.configfile:
			self.set(l.rstrip("\n"))

	def set(self,attr):
		kv = attr.split("=")
		if len(kv) != 2:
			return False
		else:
			print "setting %s to '%s'" % (kv[0], kv[1])
			self.__dict__[kv[0]] = kv[1]
		
	def get(self, key):
		try:
			val = self.__dict__[key]
		except KeyError:
			return "" 
		return self.__dict__[key]

	def store(self):
		for (k,v) in self.__dict__.items():
			if k is not 'configfile':	
				self.configfile.write("%s=%s\n" % (k,v))




