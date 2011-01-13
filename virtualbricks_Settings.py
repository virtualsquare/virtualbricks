#!/usr/bin/env python
# coding=utf-8

##	Qemulator - a qemu gui written in python and GTK/Glade.
##	Copyright (C) 2006  rainer haage
##
##	This program is free software; you can redistribute it and/or
##	modify it under the terms of the GNU General Public License
##	as published by the Free Software Foundation; either version 2
##	of the License, or (at your option) any later version.
##	
##	This program is distributed in the hope that it will be useful,
##	but WITHOUT ANY WARRANTY; without even the implied warranty of
##	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##	GNU General Public License for more details.
##	
##	You should have received a copy of the GNU General Public License
##	along with this program; if not, write to the Free Software
##	Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
from os import path
import os
import sys
import pickle
import re
import shutil
from copy import copy


VDEPATH="/usr/bin"
HOME=os.path.expanduser("~")
MYPATH=HOME + "/.virtualbricks"
CONFIGFILE=HOME + "/.virtualbricks.conf"

class Settings:
	def __init__(self, f):
		self.configfile = None
		#default config
		self.bricksdirectory = HOME + "/virtualbricks"
		self.term = "/usr/bin/xterm"
		self.sudo = "/usr/bin/gksu"
		self.qemupath="/usr/bin"
		self.baseimages = HOME + "/virtualbricks/img"
		self.kvm = "0"
		self.ksm = "0"
		self.kqemu = "0"
		self.cdroms = ""
		self.vdepath="/usr/bin"
		self.python = "0"
		self.femaleplugs = "0"
		self.erroronloop = "0"

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


	def check_missing_vdepath(self, path):
		vdebin_template = ['vde_switch', 'vde_plug', 'vde_cryptcab', 'dpipe', 'vdeterm', 'vde_plug2tap', 'wirefilter']
		res = []
		for v in vdebin_template:
			if not os.access(path + "/" + v, os.X_OK):
				res.append(v)
		return res
	
	def check_missing_qemupath(self, path):
		qemubin_template = ['qemu', 'kvm',
			'qemu-system-arm',
			'qemu-system-cris',
			'qemu-system-i386',
			'qemu-system-m68k',
			'qemu-system-microblaze',
			'qemu-system-mips',
			'qemu-system-mips64',
			'qemu-system-mips64el',
			'qemu-system-mipsel',
			'qemu-system-ppc',
			'qemu-system-ppc64',
			'qemu-system-ppcemb',
			'qemu-system-sh4',
			'qemu-system-sh4eb',
			'qemu-system-sparc',
			'qemu-system-sparc64',
			'qemu-system-x86_64'
		]
	
		res0 = []
		res1 = []
		for v in qemubin_template:
			if not os.access(path + "/" + v, os.X_OK):
				res0.append(v)
			else:
				res1.append(v)
		return res0, res1

	def check_kvm(self):
		for b in self.check_missing_qemupath(self.qemupath):
			if b == 'kvm':
				raise IOError	
				return False
		
		if not os.access("/sys/class/misc/kvm", os.X_OK):
			raise NotImplementedError
		
	def check_ksm(self, onoff):
		if (onoff == False and self.ksm != "1"):
			return True
		if (onoff):
			arg = '1'
		else:
			arg = '0'
		cmd = "echo '" + arg + "'>/sys/kernel/mm/ksm/run"

		if self.sudo_system(cmd) != 0:
			print cmd
			raise NotImplementedError
		
		
		
	def sudo_system(self, cmd):
		return (os.system(self.sudo+' '+repr(cmd)))
		
