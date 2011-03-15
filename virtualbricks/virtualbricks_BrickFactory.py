#!/usr/bin/python
# -*- coding: utf-8 -*-

##	Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
##	Copyright (C) 2011 Virtualbricks team
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

import copy
import gobject
import os
import re
import select
import socket
import subprocess
import sys
from threading import Thread, Timer
import time

import virtualbricks_Global as Global
from virtualbricks_Logger import ChildLogger
import virtualbricks_Models as Models
import virtualbricks_Settings as Settings
#from virtualbricks_Events import Event
import virtualbricks_Events as Events
from virtualbricks_Graphics import *

class InvalidNameException(Exception):
	pass

class BadConfigException(Exception):
	pass

class NotConnectedException(Exception):
	pass

class LinkloopException(Exception):
	pass

class UnmanagedTypeException(Exception):
	pass

class InvalidActionException(Exception):
	pass

def ValidName(name):
	name=str(name)
	if not re.search("\A[a-zA-Z]", name):
		return None
	while(name.startswith(' ')):
		name = name.lstrip(' ')
	while(name.endswith(' ')):
		name = name.rstrip(' ')

	name = re.sub(' ', '_', name)
	if not re.search("\A\w+\Z", name):
		return None
	return name

class Plug(ChildLogger):
	def __init__(self, _brick):
		ChildLogger.__init__(self, _brick)
		self.brick = _brick
		self.sock = None
		self.antiloop = False
		self.mode = 'vde'

	def configured(self):
		if self.sock is None:
			return False
		else:
			return True

	def connected(self):
		if self.antiloop:
			if self.settings.get('erroronloop'):
				raise NotConnectedException('Network loop detected!')
			self.antiloop = False
			return False

		self.antiloop = True
		if self.sock is None or self.sock.brick is None:
			self.antiloop = False
			return False
		self.sock.brick.poweron()
		if self.sock.brick.proc is None:
			self.antiloop = False
			return False
		for p in self.sock.brick.plugs:
			if not p.connected():
				self.antiloop = False
				return False
		self.antiloop = False
		return True

	def connect(self, _sock):
		if _sock is None:
			return False
		else:
			_sock.plugs.append(self)
			self.sock = _sock
			return True

	def disconnect(self):
		self.sock = None

class Sock(object):
	def __init__(self, _brick, _nickname):
		self.brick = _brick
		self.nickname = _nickname
		self.path = ""
		self.plugs = []
		self.brick.factory.socks.append(self)

	def get_free_ports(self):
		return int(self.brick.cfg.numports) - len(self.plugs)

	def has_valid_path(self):
		return os.access(os.path.dirname(self.path), os.W_OK)

class BrickConfig(dict):
	"""Generic configuration for Brick

	>>> cfg = BrickConfig()
	>>> cfg.enabled = True
	>>> cfg['enabled'] == True
	True
	>>> cfg.enabled == True
	True
	>>> cfg.disabled = True
	>>> cfg['disabled'] == True
	True
	>>> cfg.disabled == True
	True
	>>> from copy import deepcopy
	>>> cfg2 = deepcopy(cfg)
	"""
	def __getattr__(self, name):
		"""override dict.__getattr__"""
		try:
			return self[name]
		except KeyError:
			raise AttributeError(name)

	def __setattr__(self, name, value):
		"""override dict.__setattr__"""
		self[name] = value

	def set(self, attr):
		kv = attr.split("=")
		if len(kv) < 2:
			return False
		else:
			val = ''
			if len(kv) > 2:
				val = '"'
				for c in kv[1:]:
					val += c.lstrip('"').rstrip('"')
					val += "="
				val = val.rstrip('=') + '"'
			else:
				val += kv[1]
			#print "setting %s to '%s'" % (kv[0], val)
			self[kv[0]] = val
			return True

	def set_obj(self, key, obj):
		self[key] = obj

	def dump(self):
		for (k, v) in self.iteritems():
			print "%s=%s" % (k, v)

class Brick(ChildLogger):
	def __init__(self, _factory, _name):
		ChildLogger.__init__(self, _factory)
		self.factory = _factory
		self.settings = self.factory.settings
		self.active = False
		self.name = _name
		self.plugs = []
		self.socks = []
		self.proc = None
		self.cfg = BrickConfig()
		self.cfg.numports = 0 #Why is it needed here!?!
		self.command_builder = dict()
		self.factory.bricks.append(self)
		self.gui_changed = False
		self.need_restart_to_apply_changes = False
		self.needsudo = False
		self.internal_console = None
		self.icon = Icon(self)
		self.terminal = "vdeterm"

		self.factory.bricksmodel.add_brick(self)

	def __deepcopy__(self, memo):
		newname = self.factory.nextValidName("Copy_of_%s" % self.name)
		if newname is None:
			raise Exception("Name error duplicating event.")
		new_brick = type(self)(self.factory, newname)
		new_brick.cfg = copy.deepcopy(self.cfg, memo)
		return new_brick

	def path(self):
		return "%s/%s.ctl" % (Settings.MYPATH, self.name)

	def console(self):
		return "%s/%s.mgmt" % (Settings.MYPATH, self.name)

	def cmdline(self):
		return ""

	def getname(self):
		return self.name

	def on_config_changed(self):
		return

	def help(self):
		print "Object type: " + self.get_type()
		print "Possible configuration parameter: "
		for (switch, v) in self.command_builder.items():
			if not switch.startswith("*"):
				if callable(v):
					print v.__name__,
				else:
					print v,
				print "  ",
				print "\t(like %s %s)" % (self.prog(), switch)
			else:
				print "%s %s\tset '%s' to append this value to the command line with no argument prefix" % (switch, v, v)
		print "END of help"
		print

	def configured(self):
		return False

	def properly_connected(self):
		for p in self.plugs:
			if p.configured() == False:
				return False
		return True

	def check_links(self):
		for p in self.plugs:
			if p.connected() == False:
				return False
		return True

	def initialize(self, attrlist):
		"""TODO attrs : dict attr => value"""
		for attr in attrlist:
			self.cfg.set(attr)

	def configure(self, attrlist):
		"""TODO attrs : dict attr => value"""
		self.initialize(attrlist)
		# TODO brick should be gobject and a signal should be launched
		self.factory.bricksmodel.change_brick(self)
		self.on_config_changed()

	def connect(self, endpoint):
		for p in self.plugs:
			if not p.configured():
				if p.connect(endpoint):
					self.on_config_changed()
					self.gui_changed = True
					return True
		return False

	def disconnect(self):
		for p in self.plugs:
			if p.configured():
				p.disconnect()
		self.on_config_changed()

	def get_cbset(self, key):
		cb = None
		try:
			if self.get_type() == 'Switch':
				cb = Switch.__dict__["cbset_" + key]

			elif self.get_type() == 'Wirefilter':
				cb = Wirefilter.__dict__["cbset_" + key]

			elif self.get_type() == 'Qemu':
				cb = VM.__dict__["cbset_" + key]

			#elif self.get_type() == 'Event':
			#	cb = None;
		except:
			cb = None
		return cb


	############################
	########### Poweron/Poweroff
	############################

	def poweron(self):

		if not self.configured():
			print "bad config"
			raise BadConfigException
		if not self.properly_connected():
			print "not connected"
			raise NotConnectedException
		if not self.check_links():
			print "link down"
			raise LinkloopException
		self._poweron()
		self.factory.bricksmodel.change_brick(self)

	def build_cmd_line(self):
		res = []

		for (switch, v) in self.command_builder.items():
			if not switch.startswith("#"):
				if callable(v):
					value = v()
				else:
					value = self.cfg.get(v)
				if value is "*":
					res.append(switch)
				elif value is not None and len(value) > 0:
					if not switch.startswith("*"):
						res.append(switch)
					res.append(value)
		return res

	def args(self):
		res = []
		res.append(self.prog())
		for c in self.build_cmd_line():
			res.append(c)
		return res

	def _poweron(self):
		if (self.proc != None):
			return
		command_line = self.args()

		if self.needsudo:
			sudoarg = ""
			for cmdarg in command_line:
				sudoarg += cmdarg + " "
			sudoarg += "-P /tmp/" + self.name + ".pid "
			command_line[0] = self.settings.get("sudo")
			command_line[1] = sudoarg
		print 'Starting "',
		for cmdarg in command_line:
			print cmdarg + " ",
		print '"'
		self.proc = subprocess.Popen(command_line, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		self.send('\n')
#		self.proc.fromchild.close()
#		self.proc.tochild.close()
		if self.needsudo:
			time.sleep(5)
			try:
				pidfile = open("/tmp/" + self.name + ".pid", "r")
				self.pid = int(pidfile.readline().rstrip('\n'))
			except:
				print("Cannot get pid from pidfile!")
				pass
		else:
			self.pid = self.proc.pid

		if self.open_internal_console and callable(self.open_internal_console):
			self.internal_console = self.open_internal_console()
		self.factory.emit("brick-started")
		self.post_poweron()

	def poweroff(self):
		print "Shutting down %s" % self.name

		if self.proc is None:
			return False

		if self.pid > 0:
			if (self.needsudo):
				os.system(self.settings.get('sudo') + ' "kill ' + str(self.pid) + '"')
			else:
				try:
					#self.proc.send_signal(15)
					os.kill(self.pid, 15)
				except Exception, err:
					print "ERROR", err

			ret = self.proc.poll()
			while ret is None:
				ret = self.proc.poll()

		self.proc = None
		self.need_restart_to_apply_changes = False
		if self.close_internal_console and callable(self.close_internal_console):
			self.close_internal_console()
		self.internal_console == None
		self.factory.emit("brick-stopped")
		self.post_poweroff()

	def post_poweron(self):
		self.active = True

	def post_poweroff(self):
		self.active = False

	#############################
	# Console related operations.
	#############################
	def has_console(self):
		if (self.cfg.get('console')) and self.proc != None:
			return True
		else:
			return False

	def open_console(self):
		print "open_console"
		if not self.has_console():
			return
		else:
			cmdline = [self.settings.get('term'), '-T', self.name, '-e', self.terminal, self.console()]
			try:
				console = subprocess.Popen(cmdline)
			except:
				print "xterm run failed, trying gnome-terminal"
				cmdline = ['gnome-terminal', '-t', self.name, '-e', self.terminal + " " + self.console()]
				print cmdline
				try:
					console = subprocess.Popen(cmdline)
				except:
					print "Error: cannot start a terminal emulator"
					return

	#Must be overridden in Qemu to use appropriate console as internal (stdin, stdout?)
	def open_internal_console(self):
		print "open_internal_console"
		if not self.has_console():
			return None
		while True:
			try:
				time.sleep(0.5)
				c = socket.socket(socket.AF_UNIX)
				c.connect(self.console())
			except:
				pass
			else:
				break
		return c

	def send(self, msg):
		if self.internal_console == None or not self.active:
			print "cancel send"
			return
		try:
			print "= sending " + msg
			self.internal_console.send(msg)
		except Exception, err:
			print "send failed", err, type(err)

	def recv(self):
		print "recv"
		if self.internal_console == None:
			return ''
		res = ''
		p = select.poll()
		p.register(self.internal_console, select.POLLIN)
		while True:
			pollret = p.poll(300)
			if (len(pollret) == 1 and pollret[0][1] == select.POLLIN):
				line = self.internal_console.recv(100)
				res += line
			else:
				break
		return res

	def close_internal_console(self):
		if not self.has_console():
			return
		self.internal_console.close()

	def close_tty(self):
		sys.stdin.close()
		sys.stdout.close()
		sys.stderr.close()

	def get_parameters(self):
		raise NotImplemented('get_parameters')

	def get_state(self):
		"""return state of the brick"""
		if self.proc is not None:
			state = _('running')
		elif not self.properly_connected():
			state = _('disconnected')
		else:
			state = _('off')
		return state

class VbShellCommand(str):
	def __init__(self, mystr):
		self=mystr
	pass

class ShellCommand(str):
	def __init__(self, mystr):
		self=mystr
	pass

class Event(ChildLogger):
	def __init__(self, _factory, _name):
		ChildLogger.__init__(self, _factory)
		self.factory = _factory
		self.settings = self.factory.settings
		self.active = False
		self.name = _name
		self.cfg = BrickConfig()
		self.cfg.actions = list()
		self.cfg.delay = 0
		self.factory.events.append(self)
		self.gui_changed = False
		self.need_restart_to_apply_changes = False
		self.needsudo = False
		self.internal_console = None
		self.icon = Icon(self)
		self.factory.eventsmodel.add_event(self)
		self.on_config_changed()
		self.timer = None

	def help(self):
		print "Object type: " + self.get_type()
		print "Possible configuration parameter: "
		print "delay=n OR add [vb-shell command] OR addsh [host-shell command]"
		print "Example: <eventname> config delay=5"
		print "Example: <eventname> config add new switch myswitch add n wirefilter wf"
		print "Example: <eventname> config addsh touch /tmp/vbshcmd addsh cp /tmp/vbshcmd /tmp/vbshcmd1"
		print "END of help"
		print

	def get_type(self):
		return 'Event'

	def get_state(self):
		"""return state of the event"""
		if self.active == True:
			state = _('running')
		elif self.configured() == False:
			state = _('unconfigured')
		else:
			state = _('off')
		return state

	def get_cbset(self, key):
		cb = None
		try:
			if self.get_type() == 'Event':
				cb = Event.__dict__["cbset_" + key]
		except:
			cb = None
		return cb

	def change_state(self):
		if self.active == True:
			self.poweroff()
		else:
			self.poweron()

	def configured(self):
		return (len(self.cfg.actions) > 0 and self.cfg.delay > 0)

	def initialize(self, attrlist):
		if('add' in attrlist and 'addsh' in attrlist):
			print "Error: config line must contain add OR addsh."
			print "Split in two different line."
			raise InvalidActionException
		elif('add' in attrlist):
			configactions = list()
			configactions = (' '.join(attrlist)).split('add')
			for action in configactions[1:]:
				action = action.strip()
				self.cfg.actions.append(VbShellCommand(action))
				print "Added vb-shell command: \"%s\"" % str(action)
		elif('addsh' in attrlist):
			configactions = list()
			configactions = (' '.join(attrlist)).split('addsh')
			for action in configactions[1:]:
				action = action.strip()
				self.cfg.actions.append(ShellCommand(action))
				print "Added host-shell command: \"%s\"" % str(action)
#		elif('addev' in attrlist):
#			configactions = list()
#			configactions = (' '.join(attrlist)).split('addev')
#			for action in configactions[1:]:
#				action = action.strip()
#				self.actions.append(self.factory.geteventbyname(action))
#				print "Added event: \"%s\"" % str(action)
		else:
			for attr in attrlist:
				self.cfg.set(attr)

	def properly_connected(self):
		return True

	def get_parameters(self):
		tempstr = _("Delay") + ": %d" % int(self.cfg.delay)
		l = len(self.cfg.actions)
		if l > 0:
			tempstr += "; "+ _("Actions")+":"
			#Add actions cutting the tail if it's too long
			for s in self.cfg.actions:
				#if(len(tempstr)+len(s) > Global.GUI_EVENT_PARAM_NCHAR):
				#	tempstr+=" ...."
				#	break
				if isinstance(s, ShellCommand) == True:
					tempstr += " \"*%s\"," % s
				else:
					tempstr += " \"%s\"," % s
			#Remove the last character
			tempstr=tempstr[0:-1]
		return tempstr

	def connect(self, endpoint):
		return True

	def disconnect(self):
		return

	def configure(self, attrlist):
		self.initialize(attrlist)
		# TODO brick should be gobject and a signal should be launched
		self.factory.eventsmodel.change_event(self)
		self.on_config_changed()

	############################
	########### Poweron/Poweroff
	############################
	def poweron(self):
		if not self.configured():
			print "bad config"
			raise BadConfigException
		if(self.active == True):
			self.timer.cancel()
			self.active=False
			self.factory.emit("event-stopped")
			self.on_config_changed()
		try:
			self.timer.start()
		except RuntimeError:
			pass
		self.active = True
		self.factory.emit("event-started")

	def poweroff(self):
		if(self.active == False):
			return
		self.timer.cancel()
		self.active = False
		#We get ready for new poweron
		self.on_config_changed()
		self.factory.emit("event-stopped")

	def doactions(self):
		for action in self.cfg.actions:
			if (isinstance(action, VbShellCommand)):
				self.factory.parse(action)
			elif (isinstance(action, ShellCommand)):
				try:
					console = subprocess.Popen(action.split(' '))
				except:
					print "Error: cannot execute shell command \"%s\"" % action
					continue
#			else:
#				#it is an event
#				action.poweron()

		self.active = False
		#We get ready for new poweron
		self.on_config_changed()
		self.factory.emit("event-accomplished")

	def on_config_changed(self):
		self.timer = Timer(float(self.cfg.delay), self.doactions, ())

	#############################
	# Console related operations.
	#############################
	def has_console(self):
			return False

	def close_tty(self):
		return

class Switch(Brick):
	"""
	>>> # bug #730812
	>>> from copy import deepcopy
	>>> factory = BrickFactory()
	>>> sw1 = Switch(factory, 'sw1')
	>>> sw2 = factory.dupbrick(sw1)
	>>> id(sw1) != id(sw2)
	True
	>>> sw1 is not sw2
	True
	>>> sw1.cfg is not sw2.cfg
	True
	>>> sw1.icon is not sw2.icon
	True
	"""
	def __init__(self, _factory, _name):
		Brick.__init__(self, _factory, _name)
		self.pid = -1
		self.cfg.numports = "32"
		self.cfg.hub = ""
		self.cfg.fstp = ""
		self.ports_used = 0
		self.command_builder = {"-s":self.path,
					"-M":self.console,
					"-x":"hubmode",
					"-n":"numports",
					"-F":"fstp",
					"--macaddr":"macaddr",
					"-m":"mode",
					"-g":"group",
					"--priority":"priority",
					"--mgmtmode":"mgmtmode",
					"--mgmtgroup":"mgmtgroup"

					}
		portname = self.name + "_port"
		self.socks.append(Sock(self, portname))
		self.on_config_changed()

	def get_parameters(self):
		fstp = ""
		hub = ""
		if (self.cfg.get('fstp')):
			fstp = ", FSTP"
		if (self.cfg.get('hub')):
			hub = ", HUB"
		return "Ports:%d%s%s" % ((int(unicode(self.cfg.numports))), fstp, hub)

	def prog(self):
		return self.settings.get("vdepath") + "/vde_switch"

	def get_type(self):
		return 'Switch'

	def on_config_changed(self):
		self.socks[0].path = self.path()

		if self.proc is not None:
			self.need_restart_to_apply_changes = True

	def configured(self):
		return self.socks[0].has_valid_path()

	# live-management callbacks
	def cbset_fstp(self, arg=False):
		if (arg):
			self.send("fstp/setfstp 1\n")
		else:
			self.send("fstp/setfstp 0\n")
		print self.recv()

	def cbset_hub(self, arg=False):
		print "Callback hub with argument " + self.name
		if (arg):
			self.send("port/sethub 1\n")
		else:
			self.send("port/sethub 0\n")
		print self.recv()

	def cbset_numports(self, arg="32"):
		print "Callback numports with argument " + self.name
		self.send("port/setnumports " + arg)
		print self.recv()


class Tap(Brick):
	def __init__(self, _factory, _name):
		Brick.__init__(self, _factory, _name)
		self.pid = -1
		self.cfg.name = _name
		self.command_builder = {"-s":'sock', "*tap":"name"}
		self.cfg.sock = ""
		self.plugs.append(Plug(self))
		self.needsudo = True
		self.cfg.ip = "10.0.0.1"
		self.cfg.nm = "255.255.255.0"
		self.cfg.gw = ""
		self.cfg.mode = "off"

	def get_parameters(self):
		if self.plugs[0].sock:
			return "plugged to %s " % self.plugs[0].sock.brick.name

		return "disconnected"

	def prog(self):
		return self.settings.get("vdepath") + "/vde_plug2tap"

	def get_type(self):
		return 'Tap'

	def on_config_changed(self):
		print "self.plugs[0].sock", self.plugs[0].sock
		if (self.plugs[0].sock is not None):
			self.cfg.sock = self.plugs[0].sock.path
		if (self.proc is not None):
			self.need_restart_to_apply_changes = True

	def configured(self):
		return (self.plugs[0].sock is not None)

	def post_poweron(self):
		if self.cfg.mode == 'dhcp':
			ret = os.system(self.settings.get('sudo') + ' "dhclient ' + self.name + '"')

		elif self.cfg.mode == 'manual':
			# XXX Ugly, can't we ioctls?
			ret0 = os.system(self.settings.get('sudo') + ' "/sbin/ifconfig ' + self.name + ' ' + self.cfg.ip + ' netmask ' + self.cfg.nm + '"')
			if (len(self.cfg.gw) > 0):
				ret1 = os.system(self.settings.get('sudo') + ' "/sbin/route add default gw ' + self.cfg.gw + ' dev ' + self.name + '"')
		else:
			return


class Wire(Brick):
	def __init__(self, _factory, _name):
		Brick.__init__(self, _factory, _name)
		self.pid = -1
		self.cfg.name = _name
		self.command_builder = {"#sock left":"sock0", "#sock right":"sock1"}
		self.cfg.sock0 = ""
		self.cfg.sock1 = ""
		self.plugs.append(Plug(self))
		self.plugs.append(Plug(self))

	def get_parameters(self):
		if self.plugs[0].sock:
			p0 = self.plugs[0].sock.brick.name
		else:
			p0 = "disconnected"

		if self.plugs[1].sock:
			p1 = self.plugs[1].sock.brick.name
		else:
			p1 = "disconnected"

		if p0 != 'disconnected' and p1 != 'disconnected':
			return "Configured to connect %s to %s" % (p0, p1)
		else:
			return "Not yet configured. "\
				"Left plug is %s and right plug is %s" % (p0, p1)

	def on_config_changed(self):
		if (self.plugs[0].sock is not None):
			self.cfg.sock0 = self.plugs[0].sock.path
		if (self.plugs[1].sock is not None):
			self.cfg.sock1 = self.plugs[1].sock.path
		if (self.proc is not None):
			self.need_restart_to_apply_changes = True

	def configured(self):
		return (self.plugs[0].sock is not None and self.plugs[1].sock is not None)

	def prog(self):
		return self.settings.get("vdepath") + "/dpipe"

	def get_type(self):
		return 'Wire'

	def args(self):
		res = []
		res.append(self.prog())
		res.append(self.settings.get("vdepath") + '/vde_plug')
		res.append(self.cfg.sock0)
		res.append('=')
		res.append(self.settings.get("vdepath") + '/vde_plug')
		res.append(self.cfg.sock1)
		return res

class Wirefilter(Wire):
	def __init__(self, _factory, _name):
		Wire.__init__(self, _factory, _name)
		self.command_builder = {
			"-d":"delay",
			"-l":"loss",
			"-L":"lostburst",
			"-D":"dup",
			"-b":"bandwidth",
			"-s":"speed",
			"-c":"chanbufsize",
			"-n":"noise",
			"-m":"mtu",
			"-N":"nofifo",
			"-M":self.console,
		}

#		self.cfg.sock0 = ""
#		self.cfg.sock1 = ""
#
#		self.plugs.append(Plug(self))
#		self.plugs.append(Plug(self))


		self.cfg.mtuLR = ""
		self.cfg.mtuRL = ""
		#remove the following line when the interface will split mtu
		#into mtu[LR,RL]
		self.cfg.mtu = ""
		self.cfg.mtuck = ""
		self.cfg.noiseLR = ""
		self.cfg.noiseRL = ""
		#remove the following line when the interface will split noise
		#into noise[LR,RL]
		self.cfg.noise = ""
		self.cfg.chanbufsizeLR = ""
		self.cfg.chanbufsizeRL = ""
		#remove the following line when the interface will split chanbufsize
		#into chanbufsize[LR,RL]
		self.cfg.chanbufsize = ""
		self.cfg.delayLR = ""
		self.cfg.delayRL = ""
		self.cfg.lossLR = ""
		self.cfg.lossRL = ""
		self.cfg.lostburstLR = ""
		self.cfg.lostburstRL = ""
		#remove the following line when the interface will split lostburst
		#into lostburst[LR,RL]
		self.cfg.lostburst = ""
		self.cfg.gilbertck = ""
		self.cfg.dupLR = ""
		self.cfg.dupRL = ""
		self.cfg.speedLR = ""
		self.cfg.speedRL = ""
		self.cfg.speedLRunit = ""
		self.cfg.speedRLunit = ""
		self.cfg.speedLRdistribution = ""
		self.cfg.speedRLdistribution = ""
		self.cfg.bandwidthLR = ""
		self.cfg.bandwidthRL = ""
		self.cfg.bandwidthLRunit = ""
		self.cfg.bandwidthRLunit = ""
		self.cfg.bandwidthLRdistribution = ""
		self.cfg.bandwidthRLdistribution = ""

	def args(self):
		res = []
		res.append(self.prog())
		res.append('-v')
		res.append(self.cfg.sock0 + ":" + self.cfg.sock1)

		if len(self.cfg.delayLR) > 0:
			res.append("-d")
			res.append("LR" + self.cfg.delayLR)
		if len(self.cfg.delayRL) > 0:
			res.append("-d")
			res.append("RL" + self.cfg.delayRL)

		if len(self.cfg.lossLR) > 0:
			res.append("-l")
			res.append("LR" + self.cfg.lossLR)
		if len(self.cfg.lossRL) > 0:
			res.append("-l")
			res.append("RL" + self.cfg.lossRL)

		if len(self.cfg.dupLR) > 0:
			res.append("-D")
			res.append("LR" + self.cfg.dupLR)
		if len(self.cfg.dupRL) > 0:
			res.append("-D")
			res.append("RL" + self.cfg.dupRL)

		if len(self.cfg.speedLR) > 0:
			res.append("-s")
			res.append("LR" + self.cfg.speedLR + self.cfg.speedLRunit + self.cfg.speedLRdistribution)
		if len(self.cfg.speedRL) > 0:
			res.append("-s")
			res.append("RL" + self.cfg.speedRL + self.cfg.speedRLunit + self.cfg.speedRLdistribution)

		if len(self.cfg.bandwidthLR) > 0:
			res.append("-b")
			res.append("LR" + self.cfg.bandwidthLR + self.cfg.bandwidthLRunit + self.cfg.bandwidthLRdistribution)
		if len(self.cfg.bandwidthRL) > 0:
			res.append("-b")
			res.append("RL" + self.cfg.bandwidthRL + self.cfg.bandwidthRLunit + self.cfg.bandwidthRLdistribution)

		if len(self.cfg.chanbufsizeLR) > 0:
			res.append("-c")
			res.append("LR" + self.cfg.chanbufsizeLR)
		if len(self.cfg.chanbufsizeRL) > 0:
			res.append("-c")
			res.append("RL" + self.cfg.chanbufsizeRL)

		if len(self.cfg.noiseLR) > 0:
			res.append("-n")
			res.append("LR" + self.cfg.noiseLR)
		if len(self.cfg.noiseRL) > 0:
			res.append("-n")
			res.append("RL" + self.cfg.noiseRL)

		if len(self.cfg.mtuLR) > 0:
			res.append("-m")
			res.append("LR" + self.cfg.mtuLR)
		if len(self.cfg.mtuRL) > 0:
			res.append("-m")
			res.append("RL" + self.cfg.mtuRL)

		if len(self.cfg.lostburstLR) > 0:
			res.append("-L")
			res.append("LR" + self.cfg.lostburstLR)
		if len(self.cfg.lostburstRL) > 0:
			res.append("-L")
			res.append("RL" + self.cfg.lostburstRL)

		for param in Brick.build_cmd_line(self):
			res.append(param)
		return res

	def prog(self):
		return self.settings.get("vdepath") + "/wirefilter"

	def get_type(self):
		return 'Wirefilter'

	#callbacks for live-management
	def cbset_lossLR(self, arg=0):
		print "Callback loss LR with argument " + self.name
		self.send("loss LR " + arg + "\n")
		print self.recv()

	def cbset_lossRL(self, arg=0):
		print "Callback loss RL with argument " + self.name
		self.send("loss RL " + arg + "\n")
		print self.recv()

	def cbset_loss(self, arg=0):
		print "Callback loss LR&RL with argument " + self.name
		self.send("loss " + arg + "\n")
		print self.recv()

	def cbset_speedLR(self, arg=0):
		print "Callback speed LR with argument " + self.name
		self.send("speed LR " + arg + "\n")
		print self.recv()

	def cbset_speedRL(self, arg=0):
		print "Callback speed RL with argument " + self.name
		self.send("speed RL " + arg + "\n")
		print self.recv()

	def cbset_speed(self, arg=0):
		print "Callback speed LR&RL with argument " + self.name
		self.send("speed " + arg + "\n")
		print self.recv()

	def cbset_noiseLR(self, arg=0):
		print "Callback noise LR with argument " + self.name
		self.send("noise LR " + arg + "\n")
		print self.recv()

	def cbset_noiseRL(self, arg=0):
		print "Callback noise RL with argument " + self.name
		self.send("noise RL " + arg + "\n")
		print self.recv()

	def cbset_noise(self, arg=0):
		print "Callback noise LR&RL with argument " + self.name
		self.send("noise " + arg + "\n")
		print self.recv()

	def cbset_bandwidthLR(self, arg=0):
		print "Callback bandwidth LR with argument " + self.name
		self.send("bandwidth LR " + arg + "\n")
		print self.recv()

	def cbset_bandwidthRL(self, arg=0):
		print "Callback bandwidth RL with argument " + self.name
		self.send("bandwidth RL " + arg + "\n")
		print self.recv()

	def cbset_bandwidth(self, arg=0):
		print "Callback bandwidth LR&RL with argument " + self.name
		self.send("bandwidth " + arg + "\n")
		print self.recv()

	def cbset_delayLR(self, arg=0):
		print "Callback delay LR with argument " + self.name
		self.send("delay LR " + arg + "\n")
		print self.recv()

	def cbset_delayRL(self, arg=0):
		print "Callback delay RL with argument " + self.name
		self.send("delay RL " + arg + "\n")
		print self.recv()

	def cbset_delay(self, arg=0):
		print "Callback delay LR&RL with argument " + self.name
		self.send("delay " + arg + "\n")
		print self.recv()

	def cbset_dupLR(self, arg=0):
		print "Callback dup LR with argument " + self.name
		self.send("dup LR " + arg + "\n")
		print self.recv()

	def cbset_dupRL(self, arg=0):
		print "Callback dup RL with argument " + self.name
		self.send("dup RL " + arg + "\n")
		print self.recv()

	def cbset_dup(self, arg=0):
		print "Callback dup LR&RL with argument " + self.name
		self.send("dup " + arg + "\n")
		print self.recv()

	def cbset_mtuLR(self, arg=0):
		print "Callback mtu LR with argument " + self.name
		self.send("mtu LR " + arg + "\n")
		print self.recv()

	def cbset_mtuRL(self, arg=0):
		print "Callback mtu RL with argument " + self.name
		self.send("mtu RL " + arg + "\n")
		print self.recv()

	def cbset_mtu(self, arg=0):
		print "Callback mtu LR&RL with argument " + self.name
		self.send("mtu " + arg + "\n")
		print self.recv()

	def cbset_lostburstLR(self, arg=0):
		print "Callback lostburst LR with argument " + self.name
		self.send("lostburst LR " + arg + "\n")
		print self.recv()

	def cbset_lostburstRL(self, arg=0):
		print "Callback lostburst RL with argument " + self.name
		self.send("lostburst RL " + arg + "\n")
		print self.recv()

	def cbset_lostburst(self, arg=0):
		print "Callback lostburst LR&RL with argument " + self.name
		self.send("lostburst " + arg + "\n")
		print self.recv()

	def cbset_chanbufsizeLR(self, arg=0):
		print "Callback chanbufsize LR (capacity) with argument " + self.name
		self.send("chanbufsize LR " + arg + "\n")
		print self.recv()

	def cbset_chanbufsizeRL(self, arg=0):
		print "Callback chanbufsize RL (capacity) with argument " + self.name
		self.send("chanbufsize RL " + arg + "\n")
		print self.recv()

	def cbset_chanbufsize(self, arg=0):
		print "Callback chanbufsize LR&RL (capacity) with argument " + self.name
		self.send("chanbufsize " + arg + "\n")
		print self.recv()

	#Follows a "duplicate" code of "chanbufsizeXX", because chanbufsize was called
	#capacity before. Justo to be sure...
	#Remove when will be sure that "capacity" will not be used anymore.
	def cbset_capacityLR(self, arg=0):
		cbset_chanbufsizeLR(arg)

	def cbset_capacityeRL(self, arg=0):
		cbset_chanbufsizeRL(arg)

	def cbset_capacity(self, arg=0):
		cbset_chanbufsize(arg)
#Current Delay Queue size:   L->R 0	  R->L 0 ??? Is it status or parameter?

class TunnelListen(Brick):
	def __init__(self, _factory, _name):
		Brick.__init__(self, _factory, _name)
		self.pid = -1
		self.cfg.name = _name
		self.command_builder = {"-s":'sock',
			"#password":"password",
			"-p":"port"
		}
		self.cfg.sock = ""
		self.cfg.password = ""
		self.plugs.append(Plug(self))
		self.cfg.port = "7667"

	def get_parameters(self):
		if self.plugs[0].sock:
			return "plugged to %s, listening to udp: %s" % (self.plugs[0].sock.brick.name
				, self.cfg.port)
		return "disconnected"

	def prog(self):
		return self.settings.get("vdepath") + "/vde_cryptcab"

	def get_type(self):
		return 'TunnelListen'

	def on_config_changed(self):
		if (self.plugs[0].sock is not None):
			self.cfg.sock = self.plugs[0].sock.path
		if (self.proc is not None):
			self.need_restart_to_apply_changes = True

	def configured(self):
		return (self.plugs[0].sock is not None)

	def args(self):
		pwdgen = "echo %s | sha1sum >/tmp/tunnel_%s.key && sync" % (self.cfg.password, self.name)
		print "System= %d" % os.system(pwdgen)
		res = []
		res.append(self.prog())
		res.append("-P")
		res.append("/tmp/tunnel_%s.key" % self.name)
		for arg in self.build_cmd_line():
			res.append(arg)
		return res

	def post_poweroff(self):
		##os.unlink("/tmp/tunnel_%s.key" % self.name)
		pass


class TunnelConnect(TunnelListen):
	def __init__(self, _factory, _name):
		TunnelListen.__init__(self, _factory, _name)
		self.command_builder = {"-s":'sock',
			"#password":"password",
			"-p":"localport",
			"-c":"host",
			"#port":"port"
		}
		self.cfg.sock = ""
		self.cfg.host = ""
		self.cfg.localport = "10771"
		self.cfg.port = "7667"

	def get_parameters(self):
		if self.plugs[0].sock:
			return "plugged to %s, connecting to udp://%s" % (
				self.plugs[0].sock.brick.name, self.cfg.host)

		return "disconnected"

	def on_config_changed(self):
		if (self.plugs[0].sock is not None):
			self.cfg.sock = self.plugs[0].sock.path

		p = self.cfg.get("port")
		if p is not None:
			h = self.cfg.get("host")
			if h is not None:
				h = h.split(":")[0]
				h += ":" + p
				self.cfg.host = h

		if (self.proc is not None):
			self.need_restart_to_apply_changes = True

	def configured(self):
		return (self.plugs[0].sock is not None) and self.cfg.get("host") and len(self.cfg.host) > 0

	def get_type(self):
		return 'TunnelConnect'


class VMPlug(Plug, BrickConfig):
	def __init__(self, brick):
		Plug.__init__(self, brick)
		self.mac = Global.RandMac()
		self.model = 'rtl8139'
		self.vlan = len(self.brick.plugs) + len(self.brick.socks)
		self.mode = 'vde'

class VMPlugHostonly(VMPlug):
	def __init__(self, _brick):
		VMPlug.__init__(self, _brick)
		self.mode = 'hostonly'

	def connect(self, endpoint):
		return

	def configured(self):
		return True

	def connected(self):
		print "CALLED hostonly connected"
		return True

class VMDisk():
	def __init__(self, name, dev):
		self.Name = name
		self.base = ""
		self.cow = False
		self.device = dev
		#self.snapshot = False

	def args(self, k):
		ret = []
		if self.cow:
			cowname = os.path.dirname(self.base) + "/" + self.Name + "_" + self.device + ".cow"
			if not os.access(cowname, os.R_OK):
				print ("Creating Cow image...")
				os.system('qemu-img create -b %s -f cow %s' % (self.base, cowname))
				os.system('sync')
				time.sleep(2)
				print ("Done")
			diskname = cowname
		else:
			diskname = self.base

		#if self.snapshot:
			#ret.append('-snapshot')

		if k:
			ret.append("-" + self.device)
		ret.append(diskname)
		return ret

class VM(Brick):
	def __init__(self, _factory, _name):
		Brick.__init__(self, _factory, _name)
		self.pid = -1
		self.cfg.name = _name
		self.cfg.argv0 = "i386"
		self.cfg.machine = ""
		self.cfg.cpu = ""
		self.cfg.smp = ""
		self.cfg.ram = "64"
		self.cfg.novga = ""
		self.cfg.vga = ""
		self.cfg.vnc = ""
		self.cfg.vncN = "1"
		self.cfg.usbmode = ""
		self.cfg.snapshot = ""
		self.cfg.boot = ""
		self.cfg.basehda = ""
		self.cfg.set_obj("hda", VMDisk(_name, "hda"))
		self.cfg.privatehda = ""
		self.cfg.basehdb = ""
		self.cfg.set_obj("hdb", VMDisk(_name, "hdb"))
		self.cfg.privatehdb = ""
		self.cfg.basehdc = ""
		self.cfg.set_obj("hdc", VMDisk(_name, "hdc"))
		self.cfg.privatehdc = ""
		self.cfg.basehdd = ""
		self.cfg.set_obj("hdd", VMDisk(_name, "hdd"))
		self.cfg.privatehdd = ""
		self.cfg.basefda = ""
		self.cfg.set_obj("fda", VMDisk(_name, "fda"))
		self.cfg.privatefda = ""
		self.cfg.basefdb = ""
		self.cfg.set_obj("fdb", VMDisk(_name, "fdb"))
		self.cfg.privatefdb = ""
		self.cfg.basemtdblock = ""
		self.cfg.set_obj("mtdblock", VMDisk(_name, "mtdblock"))
		self.cfg.privatemtdblock = ""
		self.cfg.cdrom = ""
		self.cfg.device = ""
		self.cfg.cdromen = ""
		self.cfg.deviceen = ""
		self.cfg.kvm = ""
		self.cfg.soundhw = ""
		self.cfg.rtc = ""
		#kernel etc.
		self.cfg.kernel = ""
		self.cfg.kernelenbl = ""
		self.cfg.initrd = ""
		self.cfg.initrdenbl = ""
		self.cfg.gdb = ""
		self.cfg.gdbport = ""
		self.cfg.kopt = ""
		self.cfg.icon = ""
		self.terminal = "unixterm"
		self.cfg.keyboard = ""
		self.cfg.noacpi = ""
		self.cfg.sdl = ""
		self.cfg.portrait = ""
		self.cfg.tdf = ""
		self.cfg.kvmsm = ""
		self.cfg.kvmsmem = ""
		self.cfg.serial = ""

		self.command_builder = {
			'#argv0':'argv0',
			'#M':'machine',
			'#cpu':'cpu',
			'-smp':'smp',
			'-m':'ram',
			'-boot':'boot',
			##numa not supported
			'#basefda':'basefda',
			'#basefdb':'basefdb',
			'#basehda':'basehda',
			'#basehdb':'basehdb',
			'#basehdc':'basehdc',
			'#basehdd':'basehdd',
			'#basemtdblock':'basemtdblock',
			'#privatehda': 'privatehda',
			'#privatehdb': 'privatehdb',
			'#privatehdc': 'privatehdc',
			'#privatehdd': 'privatehdd',
			'#privatefda': 'privatefda',
			'#privatefdb': 'privatefdb',
			'#privatemtdblock': 'privatemtdblock',
			'#cdrom':'cdrom',
			'#device':'device',
			'#cdromen': 'cdromen',
			'#deviceen': 'deviceen',
			##extended drive: TBD
			#'-mtdblock':'mtdblock', ## TODO 0.3
			'#keyboard':'keyboard',
			'-soundhw':'soundhw',
			'-usb':'usbmode',
			##usbdevice to be implemented as a collection
			##device to be implemented as a collection
			####'-name':'name', for NAME, BRINCKNAME is used.
			#'-uuid':'uuid',
			'-nographic':'novga',
			#'-curses':'curses', ## not implemented
			#'-no-frame':'noframe', ## not implemented
			#'-no-quit':'noquit', ## not implemented.
			'-snapshot':'snapshot',
			'#vga':'vga',
			'#vncN':'vncN',
			'#vnc':'vnc',
			#'-full-screen':'full-screen', ## TODO 0.3
			'-sdl':'sdl',
			'-portrait':'portrait',
			'-win2k-hack':'win2k', ## not implemented
			'-no-acpi':'noacpi',
			#'-no-hpet':'nohpet', ## ???
			#'-baloon':'baloon', ## ???
			##acpitable not supported
			##smbios not supported
			'#kernel':'kernel',
			'#kernelenbl':'kernelenbl',
			'-append':'kopt',
			'#initrd':'initrd',
			'#initrdenbl': 'initrdenbl',
			#'-serial':'serial',
			#'-parallel':'parallel',
			#'-monitor':'monitor',
			#'-qmp':'qmp',
			#'-mon':'',
			#'-pidfile':'', ## not needed
			#'-singlestep':'',
			#'-S':'',
			'#gdb_e':'gdb',
			'#gdb_port':'gdbport',
			#'-s':'',
			#'-d':'',
			#'-hdachs':'',
			#'-L':'',
			#'-bios':'',
			'#kvm':'kvm',
			#'-no-reboot':'', ## not supported
			#'-no-shutdown':'', ## not supported
			'-loadvm':'loadvm',
			#'-daemonize':'', ## not supported
			#'-option-rom':'',
			#'-clock':'',
			'#rtc':'rtc',
			#'-icount':'',
			#'-watchdog':'',
			#'-watchdog-action':'',
			#'-echr':'',
			#'-virtioconsole':'', ## future
			#'-show-cursor':'',
			#'-tb-size':'',
			#'-incoming':'',
			#'-nodefaults':'',
			#'-chroot':'',
			#'-runas':'',
			#'-readconfig':'',
			#'-writeconfig':'',
			#'-no-kvm':'', ## already implemented otherwise
			#'-no-kvm-irqchip':'',
			#'-no-kvm-pit':'',
			#'-no-kvm-pit-reinjection':'',
			#'-pcidevice':'',
			#'-enable-nesting':'',
			#'-nvram':'',
			'-tdf':'tdf',
			'#kvmsm':'kvmsm',
			'#kvmsmem': 'kvmsmem',
			#'-mem-path':'',
			#'-mem-prealloc':'',
			'#icon': 'icon',
			'#serial': 'serial'
		}

	def get_parameters(self):
		txt = "command: %s, ram: %s" % (self.prog(), self.cfg.ram)
		for p in self.plugs:
			if p.mode == 'hostonly':
				txt += ', eth %s: Host' % unicode(p.vlan)
			elif p.sock:
				txt += ', eth %s: %s' % (unicode(p.vlan), p.sock.nickname)
		return txt

	def get_type(self):
		return "Qemu"

	def configured(self):
		cfg_ok = True
		for p in self.plugs:
			if p.sock is None and p.mode == 'vde':
				cfg_ok = False
		return cfg_ok
	# QEMU PROGRAM SELECTION
	def prog(self):
		if (len(self.cfg.argv0) > 0 and self.cfg.kvm != "*"):
			cmd = self.settings.get("qemupath") + "/" + self.cfg.argv0
		else:
			cmd = self.settings.get("qemupath") + "/qemu"
		if self.cfg.kvm :
			cmd = self.settings.get("qemupath") + "/kvm"
		return cmd


	def args(self):
		res = []
		res.append(self.prog())

		if (self.cfg.kvm == ""):
			if self.cfg.machine != "":
				res.append("-M")
				res.append(self.cfg.machine)
			if self.cfg.cpu != "":
				res.append("-cpu")
				res.append(self.cfg.cpu)

		for c in self.build_cmd_line():
			res.append(c)

		for dev in ['hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb', 'mtdblock']:
			print dev + self.cfg.get("base" + dev)
			if self.cfg.get("base" + dev) != "":
				disk = getattr(self.cfg, dev)
				disk.base = self.cfg.get("base" + dev)
				disk.cow = False
				if (self.cfg.get("private" + dev) == "*"):
					disk.cow = True
				args = disk.args(True)
				res.append(args[0])
				res.append(args[1])

		if self.cfg.kernelenbl == "*":
			res.append("-kernel")
			res.append(self.cfg.kernel)

		if self.cfg.initrdenbl == "*":
			res.append("-initrd")
			res.append(self.cfg.initrd)

		if self.cfg.gdb:
			res.append('-gdb')
			res.append('tcp::' + self.cfg.gdbport)
		if self.cfg.vnc:
			res.append('-vnc')
			res.append(':' + self.cfg.vncN)
		if self.cfg.vga:
			res.append('-vga')
			res.append('std')

		res.append('-name')
		res.append(self.name)
		if (len(self.plugs) == 0):
			res.append('-net')
			res.append('none')
		else:
			for pl in self.plugs:
				res.append("-net")
				res.append("nic,model=%s,vlan=%d,macaddr=%s" % (pl.model, pl.vlan, pl.mac))
				if (pl.mode == 'vde'):
					res.append("-net")
					res.append("vde,vlan=%d,sock=%s" % (pl.vlan, pl.sock.path))
				else:
					res.append("-net")
					res.append("user")

		if (self.cfg.cdromen == "*"):
			if (self.cfg.cdrom != ""):
				res.append('-cdrom')
				res.append(self.cfg.cdrom)
		elif (self.cfg.deviceen == "*"):
			if (self.cfg.device != ""):
				res.append('-cdrom')
				res.append(self.cfg.device)

		if (self.cfg.rtc == "*"):
			res.append('-rtc')
			res.append('base=localtime')

		if (len(self.cfg.keyboard) == 2):
			res.append('-k')
			res.append(self.cfg.keyboard)

		if (self.cfg.kvmsm == "*"):
			res.append('-kvm-shadow-memory')
			res.append(self.cfg.kvmsmem)

		if (self.cfg.serial == "*"):
			res.append('-serial')
			res.append('unix:'+Settings.MYPATH+'/'+self.name+'_serial,server,nowait')

		res.append("-mon")
		res.append("chardev=mon")
		res.append("-chardev")
		res.append('socket,id=mon_cons,path=%s,server,nowait' % self.console2())

		res.append("-mon")
		res.append("chardev=mon_cons")
		res.append("-chardev")
		res.append('socket,id=mon,path=%s,server,nowait' % self.console())

		return res

	def console(self):
		return "%s/%s_cons.mgmt" % (Settings.MYPATH, self.name)

	def console2(self):
		return "%s/%s.mgmt" % (Settings.MYPATH, self.name)

	def add_plug(self, sock=None, mac=None, model=None):
		if sock and sock == '_hostonly':
			pl = VMPlugHostonly(self)
			print "hostonly added"
			pl.mode = "hostonly"
		else:
			pl = VMPlug(self)
		self.plugs.append(pl)
		if pl.mode == 'vde':
			pl.connect(sock)
		if mac:
			pl.mac = mac
		if model:
			pl.model = model
		self.gui_changed = True
		return pl

	def connect(self, endpoint):
		pl = self.add_plug()
		pl.mac = Global.RandMac()
		pl.model = 'rtl8139'
		pl.connect(endpoint)
		self.gui_changed = True

	def remove_plug(self, idx):
		for p in self.plugs:
			if p.vlan == idx:
				self.plugs.remove(p)
				del(p)
		for p in self.plugs:
			if p.vlan > idx:
				p.vlan -= 1
		self.gui_changed = True

	def open_internal_console(self):
		print "open_internal_console_qemu"
		if not self.has_console():
			return None
		fail_count = 0
		while True:
			try:
				time.sleep(0.5)
				c = socket.socket(socket.AF_UNIX)
				c.connect(self.console2())
			except:
				fail_count += 1
				if fail_count > 9:
					print "give up!"
					print "FATAL: Virtual Machine startup failed. Check your configuration!"
					break
				pass
			else:
				break
		return c

class BricksLockManager():

       def __init__(self):
               self.bricks_lock = {}

       def lock_brick(self, brick, value):
               print "LOCK %s con %d" % (brick.get_type()+"_"+value, id(brick))
               self.bricks_lock[brick.get_type()+"_"+value]=id(brick)

       def unlock_brick(self, brick, value):
               if self.bricks_lock.has_key(brick.get_type()+"_"+value):
                       print "UNLOCK %s con %d" % (brick.get_type()+"_"+value, id(brick))
                       self.bricks_lock[brick.get_type()+"_"+value]=None

       def get_brick_lock_status(self, brick, value):
               if self.bricks_lock.has_key(brick.get_type()+"_"+value) and self.bricks_lock[brick.get_type()+"_"+value] != id(brick):
                       print "LOCK TRUE %s con %d" % (brick.get_type()+"_"+value, id(brick))
                       return True
               else:
                       print "LOCK FALSE %s con %d" % (brick.get_type()+"_"+value, id(brick))
                       return False


class BrickFactory(ChildLogger, Thread, gobject.GObject):
	__gsignals__ = {
		'engine-closed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
		'brick-started' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
		'brick-stopped' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
		'event-started' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
		'event-stopped' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
		'event-accomplished' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
	}

	def __init__(self, logger=None, showconsole=True):
		gobject.GObject.__init__(self)
		ChildLogger.__init__(self, logger)
		self.bricks = []
		self.events = []
		self.socks = []
		self.bricksmodel = Models.BricksModel()
		self.eventsmodel = Models.EventsModel()
		self.showconsole = showconsole
		Thread.__init__(self)
		self.running_condition = True
		self.settings = Settings.Settings(Settings.CONFIGFILE, self)
		self.config_restore(Settings.MYPATH + "/.virtualbricks.state")
		self.current_project = None
		self.recent_projects = []

	def getbrickbyname(self, name):
		for b in self.bricks:
			if b.name == name:
				return b
		return None

	def geteventbyname(self, name):
		for e in self.events:
			if e.name == name:
				return e
		return None

	def run(self):
		print "virtualbricks> ",
		sys.stdout.flush()
		p = select.poll()
		p.register(sys.stdin, select.POLLIN)
		while self.running_condition:
			if (self.showconsole):
				if (len(p.poll(10)) > 0):
					command = sys.stdin.readline()
					self.parse(command.rstrip('\n'))
					print ""
					print "virtualbricks> ",
					sys.stdout.flush()
			else:
				time.sleep(1)
		sys.exit(0)

	def config_dump(self, f):
		try:
			p = open(f, "w+")
		except:
			print "ERROR WRITING CONFIGURATION!\nProbably file doesn't exist or you can't write it."
			return

		for e in self.events:
			p.write('[' + e.get_type() + ':' + e.name + ']\n')
			for k, v in e.cfg.iteritems():
				#Special management for actions parameter
				if k == 'actions':
					tempactions=list()
					for action in e.cfg.actions:
						#It's an host shell command
						if isinstance(action, ShellCommand):
							tempactions.append("addsh "+action)
						#It's a vb shell command
						elif isinstance(action, VbShellCommand):
							tempactions.append("add "+action)
						else:
							print "Error: unmanaged action type."
							print "Will not be saved!"
							continue
					p.write(k + '=' + str(tempactions) + '\n')
				#Standard management for other parameters
				else:
					p.write(k + '=' + str(v) + '\n')

		for b in self.bricks:
			p.write('[' + b.get_type() + ':' + b.name + ']\n')
			for k, v in b.cfg.iteritems():
				# VMDisk objects don't need to be saved
				if b.get_type() != "Qemu" or (b.get_type() == "Qemu" and k not in ['hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb', 'mtdblock']):
					p.write(k + '=' + str(v) + '\n')

		for b in self.bricks:
			for pl in b.plugs:
				if b.get_type() == 'Qemu':
					if pl.mode == 'vde':
						p.write('link|' + b.name + "|" + pl.sock.nickname + '|' + pl.model + '|' + pl.mac + '|' + str(pl.vlan) + '\n')
					else:
						p.write('userlink|' + b.name + '||' + pl.model + '|' + pl.mac + '|' + str(pl.vlan) + '\n')
				elif (pl.sock is not None):
					p.write('link|' + b.name + "|" + pl.sock.nickname + '\n')


	def config_restore(self, f, create_if_not_found=True, start_from_scratch=False):
		"""
		ACTIONS flags for this:
		Initial restore of latest open: True,False (default)
		Open or Open Recent: False, True
		Import: False, False
		New: True, True (missing check for existing file, must be check from caller)
		"""
		try:
			p = open(f, "r")
		except:
			if create_if_not_found:
				p = open(f, "w")
				self.current_project = f
			else:
				raise BadConfigException
			return

		if start_from_scratch:
			self.current_project = f
			for b in self.bricks:
				self.delbrick(b)
			self.bricks = []

			for e in self.events:
				self.delevent(e)
			self.events = []

			return

		l = p.readline()
		b = None
		while (l):
			l = re.sub(' ', '', l)
			if re.search("\A.*link\|", l) and len(l.split("|")) >= 3:
				l.rstrip('\n')
				print "************************* link detected"
				for bb in self.bricks:
					if bb.name == l.split("|")[1]:
						if (bb.get_type() == 'Qemu'):
							sockname = l.split('|')[2]
							model = l.split("|")[3]
							macaddr = l.split("|")[4]
							vlan = l.split("|")[5]
							this_sock = '?'
							if l.split("|")[0] == 'userlink':
								this_sock = '_hostonly'
							else:
								for s in self.socks:
									if s.nickname == sockname:
										this_sock = s
										break
							pl = bb.add_plug(this_sock, macaddr, model)

							pl.vlan = int(vlan)
							print "added eth%d" % pl.vlan
						else:
							self.connect_to(bb, l.split('|')[2].rstrip('\n'))

			if l.startswith('['):
				ntype = l.lstrip('[').split(':')[0]
				name = l.split(':')[1].rstrip(']\n')
				print \
				"new " +Global.ImIf(ntype=='Event',"event","brick")\
				+": "+ ntype + ":" + name
				try:
					if(ntype == 'Event'):
						self.newevent(ntype, name)
						component = self.geteventbyname(name)
					else:
						self.newbrick(ntype, name)
						component = self.getbrickbyname(name)

				except Exception, err:
					print "--------- Bad config line:", err
					l = p.readline()
					continue

				l = p.readline()
				#print "-------- loading settings for "+b.name + " first line: " + l
				parameters = []
				while component and l and not l.startswith('[') and not re.search("\A.*link\|", l):
					if len(l.split('=')) > 1:
						#Special management for event actions
						if l.split('=')[0] == "actions" and ntype == 'Event':
							actions=eval(''.join(l.rstrip('\n').split('=')[1:]))
							for action in actions:
							#Initialize one by one
								component.configure(action.split(' '))
							l = p.readline()
							continue
						parameters.append(l.rstrip('\n'))
					l = p.readline()
				if parameters:
					component.configure(parameters)

				continue
			l = p.readline()

	def quit(self):
		for e in self.events:
			e.poweroff()
		for b in self.bricks:
			if b.proc is not None:
				b.poweroff()
		print 'Engine: Bye!'
		self.config_dump(Settings.MYPATH + "/.virtualbricks.state")
		self.running_condition = False
		self.emit("engine-closed")
		sys.exit(0)

	def proclist(self):
		procs = 0
		for b in self.bricks:
			if b.proc is not None:
				procs += 1

		if procs > 0:
			print "PID\tType\tname"
			for b in self.bricks:
				if b.proc is not None:
					print "%d\t%s\t%s" % (b.pid, b.get_type(), b.name)
		else:
			print "No process running"

	def parse(self, command):
		if (command == 'q' or command == 'quit'):
			self.quit()
		elif (command == 'h' or command == 'help'):
			print 'no help available'
		elif (command == 'ps'):
			self.proclist()
		elif command.startswith('n ') or command.startswith('new '):
			if(command.startswith('n event') or (command.startswith('new event'))):
				self.newevent(*command.split(" ")[1:])
			else:
				self.newbrick(*command.split(" ")[1:])
		elif command == 'list':
			print "Bricks:"
			for obj in self.bricks:
				print "%s %s" % (obj.get_type(), obj.name)
			print
			print "Events:"
			for obj in self.events:
				print "%s %s" % (obj.get_type(), obj.name)
			print "End of list."
			print

		elif command == 'socks':
			for s in self.socks:
				print "%s" % s.nickname,
				if s.brick is not None:
					print " - port on %s %s - %d available" % (s.brick.get_type(), s.brick.name, s.get_free_ports())
				else:
					print "not configured."

		elif command == '':
			pass

		else:
			found = None
			for obj in self.bricks:
				if obj.name == command.split(" ")[0]:
					found = obj
					break
			if found is None:
				for obj in self.events:
					if obj.name == command.split(" ")[0]:
						found = obj
						break

			if found is not None and len(command.split(" ")) > 1:
				self.brickAction(found, command.split(" ")[1:])
			else:
				print 'Invalid command "%s"' % command

	def brickAction(self, obj, cmd):
		if (cmd[0] == 'on'):
			obj.poweron()
		if (cmd[0] == 'off'):
			obj.poweroff()
		if (cmd[0] == 'remove'):
			if obj.get_type() == 'Event':
				self.delevent(obj)
			elif isinstance(obj, Brick):
				self.delbrick(obj)
			else:
				raise UnmanagedTypeException
		if (cmd[0] == 'config'):
			obj.configure(cmd[1:])
		if (cmd[0] == 'show'):
			obj.cfg.dump()
		if (cmd[0] == 'connect' and len(cmd) == 2):
			if(self.connect_to(obj, cmd[1].rstrip('\n'))):
				print ("Connection ok")
			else:
				print ("Connection failed")
		if (cmd[0] == 'disconnect'):
			obj.disconnect()
		if (cmd[0] == 'help'):
			obj.help()

	def connect_to(self, brick, nick):
		endpoint = None
		if not nick:
			return False
		for n in self.socks:
			if n.nickname == nick:
				endpoint = n
		if endpoint is not None:
			return brick.connect(endpoint)
		else:
			print "cannot find " + nick
			print self.socks

	def delbrick(self, bricktodel):
		# XXX check me
		for b in self.bricks:
			if b == bricktodel:
				for so in b.socks:
					self.socks.remove(so)
				self.bricks.remove(b)
		self.bricksmodel.del_brick(bricktodel)

	def delevent(self, eventtodel):
		# XXX check me
		for e in self.events:
			if e == eventtodel:
				e.poweroff()
				self.events.remove(e)
		self.eventsmodel.del_event(eventtodel)

	def dupbrick(self, bricktodup):
		new_brick = copy.deepcopy(bricktodup)
		new_brick.on_config_changed()
		return new_brick

	def dupevent(self, eventtodup):
		newname = self.nextValidName("Copy_of_"+eventtodup.name)
		if newname == None:
			print "Name error duplicating event."
			return
		self.newevent("Event", newname)
		event = self.geteventbyname(eventtodup.name)
		newevent = self.geteventbyname(newname)
		newevent.cfg = copy.deepcopy(event.cfg)
		newevent.active = False
		newevent.on_config_changed()

	def renamebrick(self, b, newname):
		newname = ValidName(newname)
		if newname == None:
			raise InvalidNameException

		self.isNameFree(newname)

		b.name = newname
		if b.get_type() == "Switch":
			for so in b.socks:
				so.nickname = b.name + "_port"
		b.gui_changed = True

	def renameevent(self, e, newname):
		newname = ValidName(newname)
		if newname == None:
			raise InvalidNameException

		self.isNameFree(newname)

		e.name = newname
		if e.get_type() == "Event":
			#It's a little comlicated here, if we are renaming
			#an event we have to rename it in all command of other
			#events...
			pass
		#e.gui_changed = True

	def isNameFree(self, name):
		for b in self.bricks:
			if b.name == name:
				return False

		for e in self.events:
			if e.name == name:
				return False

		return True

	def nextValidName(self, name, toappend="_new"):
		newname = ValidName(name)
		if not newname:
			return None
		for e in self.events:
			if newname == e.name:
				newname += toappend
		for b in self.bricks:
			if newname == b.name:
				newname += toappend
		return newname

	def newbrick(self, ntype="", name=""):
		name = ValidName(name)
		if not name:
			raise InvalidNameException

		if self.isNameFree(name) == False:
			raise InvalidNameException

		if ntype == "switch" or ntype == "Switch":
			brick = Switch(self, name)
			self.debug("new switch %s OK", brick.name)
		elif ntype == "tap" or ntype == "Tap":
			brick = Tap(self, name)
			self.debug("new tap %s OK", brick.name)
		elif ntype == "vm" or ntype == "Qemu":
			brick = VM(self, name)
			self.debug("new vm %s OK", brick.name)
		elif ntype == "wire" or ntype == "Wire" or ntype == "Cable":
			brick = Wire(self, name)
			self.debug("new cable %s OK", brick.name)
		elif ntype == "wirefilter" or ntype == "Wirefilter":
			brick = Wirefilter(self, name)
			self.debug("new wirefilter %s OK", brick.name)
		elif ntype == "tunnell" or ntype == "Tunnel Server" or ntype == "TunnelListen":
			brick = TunnelListen(self, name)
			self.debug("new tunnel server %s OK", brick.name)
		elif ntype == "tunnelc" or ntype == "Tunnel Client" or ntype == "TunnelConnect":
			brick = TunnelConnect(self, name)
			self.debug("new tunnel client %s OK", brick.name)
		elif ntype == "event" or ntype == "Event":
			brick = Event(self, name)
			self.debug("new event %s OK", brick.name)
		else:
			self.error("Invalid command '%s'", name)
			return False

		return True

	def newevent(self, ntype="", name=""):
		name = ValidName(name)
		if not name:
			raise InvalidNameException

		if self.isNameFree(name) == False:
			raise InvalidNameException

		if ntype == "event" or ntype == "Event":
			brick = Event(self, name)
			self.debug("new event %s OK", brick.name)
		else:
			self.error("Invalid command '%s'", name)
			return False

		return True

gobject.type_register(BrickFactory)

if __name__ == "__main__":
	"""
	run tests with 'python virtualbricks_BrickFactory.py -v'
	"""
	import doctest
	doctest.testmod()
