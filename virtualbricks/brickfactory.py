#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
Copyright (C) 2011 Virtualbricks team

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""

import copy
import gobject
import os
import re
import select
import socket
import subprocess
import sys
from threading import Thread, Timer
import time, socket, hashlib
from virtualbricks import tools
from virtualbricks.gui.graphics import *
from virtualbricks.logger import ChildLogger
from virtualbricks.models import BricksModel, EventsModel
from virtualbricks.settings import CONFIGFILE, MYPATH, Settings
from virtualbricks.errors import (BadConfig, DiskLocked, InvalidAction,
	InvalidName, Linkloop, NotConnected, UnmanagedType)
from virtualbricks.tcpserver import TcpServer
import getpass

global VDESUPPORT
try:
	import VdePlug
except:
	print "VdePlug support not found. I will disable native VDE python support."
	VDESUPPORT = False
else:
	VDESUPPORT = True
	print "VdePlug support ENABLED."



def CommandLineOutput(outf, data):
	if outf == sys.stdout:
		return outf.write(data + '\n')
	else:
		return outf.send(data + '\n')

class RemoteHostConnectionInstance(Thread):
	def __init__(self,remotehost,factory):
		self.host = remotehost
		self.factory = factory
		Thread.__init__(self)
	def run(self):
		if not self.host.connected:
			return
		self.host.post_connect_init()
		p = select.poll()
		p.register(self.host.sock, select.POLLIN | select.POLLERR | select.POLLHUP | select.POLLNVAL)
		while self.host.sock and self.host.connected:
			pollret = p.poll(100)
			if (len(pollret)) == 1:
				(fd,ev) = pollret[0]
				if ev != select.POLLIN:
					self.host.disconnect()
				else:
					event = self.host.sock.recv(200)
					if len(event) == 0:
						event = self.host.sock.recv(200)
						if len(event) == 0:
							self.host.disconnect()
							return
					for eventline in event.split('\n'):
						args = eventline.rstrip('\n').split(' ')


						if len(args) > 0 and args[0] == 'brick-started':
							for br in self.factory.bricks:
								if br.name == args[1]:
									br.proc = True
									br.factory.emit("brick-started", br.name)
									#print "Started %s" % br.name
									br.run_condition = True
									br.post_poweron()

						if len(args) > 0 and args[0] == 'brick-stopped':
							for br in self.factory.bricks:
								if br.name == args[1]:
									br.proc = None
									br.factory.emit("brick-stopped", br.name)
									#print "Stopped %s" % br.name
									br.run_condition = False
									br.post_poweroff()

						if len(args) > 0 and args[0] == 'udp':
							for br in self.factory.bricks:
								if br.name == args[1] and br.get_type() == 'Wire' and args[2] == 'remoteport':
									br.set_remoteport(args[3])
						self.remotehosts_changed=True

class RemoteHost():
	def __init__(self, factory, address):
		self.sock = None
		self.factory = factory
		self.addr = (address,1050)
		self.connected=False
		self.connection = None
		self.password=""
		self.factory.remotehosts_changed=True
		self.autoconnect=False


	def num_bricks(self):
		r = 0
		for b in self.factory.bricks:
			if b.homehost and b.homehost.addr[0] == self.addr[0]:
				r+=1
		return r

	def connect(self):
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.sock.connect(self.addr)
		except:
			return False,"Error connecting to host"
		else:
			try:
				rec = self.sock.recv(5)
			except:
				return False,"Error reading from socket"

		self.sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
		if (not rec.startswith('HELO')):
			return False,"Invalid server response"
		rec = self.sock.recv(256)
		sha = hashlib.sha256()
		sha.update(self.password)
		sha.update(rec)
		hashed = sha.digest()
		self.sock.send(hashed)
		p = select.poll()
		p.register(self.sock, select.POLLIN)
		pollret = p.poll(2000)
		if pollret is not None and len(pollret) != 0:
			rec = self.sock.recv(4)
			if rec.startswith("OK"):
				self.connected=True
				self.factory.remotehosts_changed=True
				self.connection = RemoteHostConnectionInstance(self, self.factory)
				self.connection.start()
				return True,"Success"
		self.factory.remotehosts_changed=True
		return False,"Authentication Failed."

	def disconnect(self):
		if self.connected:
			self.connected=False
			for b in self.factory.bricks:
				if b.homehost and b.homehost.addr[0] == self.addr[0]:
					b.poweroff()
			self.send("reset all")
			self.sock.close()
			self.sock = None
		self.factory.remotehosts_changed=True

	def expect_OK(self):
		p = select.poll()
		p.register(self.sock, select.POLLIN)
		if (p.poll(10)):
				rec = self.sock.recv(4)
				if rec.startswith("OK"):
					return True
		return False


	def upload(self,b):
		self.send("new "+b.get_type()+" "+b.name)
		self.putconfig(b)
		self.expect_OK()
		self.factory.remotehosts_changed=True



	def putconfig(self,b):
		for (k, v) in b.cfg.iteritems():
			if k != 'homehost':
				#print "sending "+ b.name+ " config " + "%s=%s" % (k, v)
				self.send(b.name + ' config ' + "%s=%s" % (k, v))
				self.expect_OK()
				time.sleep(0.1)
		self.factory.remotehosts_changed=True

	def post_connect_init(self):
		self.send('reset all')

		for b in self.factory.bricks:
			if b.homehost and b.homehost.addr == self.addr:
					self.upload(b)

	def send(self, cmd):
		ret = False
		if self.connected:
			self.sock.send(cmd + '\n')
		return ret

	def recv(self, size):
		if not self.connected:
			return ""
		ret = ""
		ret = self.sock.recv(size)
		return ret




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
	def __init__(self, brick):
		ChildLogger.__init__(self, brick)
		self.brick = brick
		self.sock = None
		self.antiloop = False
		self.mode = 'vde'

	def configured(self):
		return self.sock is not None

	def connected(self):
		if self.antiloop:
			if self.settings.get('erroronloop'):
				raise NotConnected('Network loop detected!')
			self.antiloop = False
			return False

		self.antiloop = True
		if self.sock is None or self.sock.brick is None:
			self.antiloop = False
			return False
		self.sock.brick.poweron()

		if self.sock.brick.homehost is None and self.sock.brick.proc is None:
			self.antiloop = False
			return False
		for p in self.sock.brick.plugs:
			if not p.connected():
				self.antiloop = False
				return False
		self.antiloop = False
		return True

	def connect(self, sock):
		if sock is None:
			return False
		else:
			sock.plugs.append(self)
			self.sock = sock
			return True

	def disconnect(self):
		self.sock = None

class Sock(object):
	def __init__(self, brick, name = ""):
		self.brick = brick
		self.path = name
		self.nickname = name
		self.plugs = []
		self.mode="sock"
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
		#Set value for running brick
		self.set_running(name, value)

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
			#Set value for running brick
			self.set_running(kv[0], val)
			return True

	def set_obj(self, key, obj):
		self[key] = obj

	def set_running(self, key, value):
		"""
		Set the value for the running brick,
		if available and running
		"""
		import inspect
		stack = inspect.stack()
		frame = stack[2][0]
		caller = frame.f_locals.get('self', None)

		if not isinstance(caller, Brick):
			return
		if not callable(caller.get_cbset):
			return
		callback = caller.get_cbset(key)
		if callable(callback):
			#self.debug("Callback: setting value %s for key %s" %(value,key))
			callback(caller, value)
		#else: self.debug("callback not found for key: %s" % (key))

	def dump(self):
		keys = sorted(self.keys())
		for k in keys:
			print "%s=%s" % (k, self[k])

class Brick(ChildLogger):
	def __init__(self, _factory, _name, homehost=None):
		ChildLogger.__init__(self, _factory)
		self.factory = _factory
		self.settings = self.factory.settings
		self.project_parms = self.factory.project_parms
		self.active = False
		self.run_condition = False
		self.name = _name
		self.plugs = []
		self.socks = []
		self.proc = None
		self.cfg = BrickConfig()
		#self.cfg.numports = 0 #Why is it needed here!?!
		self.command_builder = dict()
		self.factory.bricks.append(self)
		self.gui_changed = False
		self.need_restart_to_apply_changes = False
		self._needsudo = False
		self.internal_console = None
		self.icon = Icon(self)
		self.icon.get_img() #sic
		self.terminal = "vdeterm"
		self.config_socks = []
		self.cfg.pon_vbevent = ""
		self.cfg.poff_vbevent = ""
		if (homehost):
			self.set_host(homehost)
		else:
			self.homehost = None

		self.factory.bricksmodel.add_brick(self)

	def needsudo(self):
		return self.factory.TCP is None and self._needsudo

	def rewrite_sock_server(self, v):
		f = os.path.basename(v)
		return MYPATH + "/" + f


	def set_host(self,host):
		self.cfg.homehost=host
		self.homehost = None
		if len(host) > 0:
			for existing in self.factory.remote_hosts:
				if existing.addr[0] == host:
					self.homehost = existing
					break
			if not self.homehost:
				self.homehost = RemoteHost(self.factory, host)
				self.factory.remote_hosts.append(self.homehost)
			self.factory.remotehosts_changed=True

	def restore_self_plugs(self): # DO NOT REMOVE
		pass

	def clear_self_socks(self, sock=None): # DO NOT REMOVE
		pass

	def __deepcopy__(self, memo):
		newname = self.factory.nextValidName("Copy_of_%s" % self.name)
		if newname is None:
			raise InvalidName("'%s' (was '%s')" % newname)
		new_brick = type(self)(self.factory, newname)
		new_brick.cfg = copy.deepcopy(self.cfg, memo)
		return new_brick

	def path(self):
		return "%s/%s.ctl" % (MYPATH, self.name)

	def console(self):
		return "%s/%s.mgmt" % (MYPATH, self.name)

	def cmdline(self):
		return ""

	def pidfile(self):
		return "/tmp/%s.pid" % self.name
	pidfile = property(pidfile)

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
			if not p.configured():
				return False
		return True

	def check_links(self):
		for p in self.plugs:
			if not p.connected():
				return False
		return True

	def initialize(self, attrlist):
		"""TODO attrs : dict attr => value"""
		for attr in attrlist:
			self.cfg.set(attr)
			k=attr.split("=")[0]
			if k == 'homehost':
				self.set_host(attr.split('=')[1])
			if k == 'sock':
				s = self.rewrite_sock_server(attr.split('=')[1])
				self.cfg.sock = s

	def configure(self, attrlist):
		"""TODO attrs : dict attr => value"""
		self.initialize(attrlist)
		# TODO brick should be gobject and a signal should be launched
		self.factory.bricksmodel.change_brick(self)
		self.on_config_changed()
		if self.homehost and self.homehost.connected:
			self.homehost.putconfig(self)

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

		except:
			cb = None
		return cb


	############################
	########### Poweron/Poweroff
	############################

	def poweron(self):
		if self.factory.TCP is None:
			if not self.configured():
				print "bad config - TCP IS NONE"
				raise BadConfig()
			if not self.properly_connected():
				print "not connected"
				raise NotConnected()
			if not self.check_links():
				print "link down"
				raise Linkloop()
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
		if self.proc != None:
			return
		command_line = self.args()

		if self.needsudo():
			sudoarg = ""
			for cmdarg in command_line:
				sudoarg += cmdarg + " "
			sudoarg += "-P %s" % self.pidfile
			command_line[0] = self.settings.get("sudo")
			command_line[1] = sudoarg
		self.debug(_("Starting: '%s'"), ' '.join(command_line))
		if self.homehost:
			if not self.homehost.connected:
				self.factory.err(self, "Error: You must be connected to the host to perform this action")
				return
			else:
				# Initiate RemoteHost startup:
				self.homehost.send(self.name+" on")
				return
		else:
			# LOCAL BRICK
			try:
				#print command_line
				self.proc = subprocess.Popen(command_line, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
			except OSError:
				self.factory.err(self,"OSError: Brick startup failed. Check your configuration!")

			if self.proc:
				self.pid = self.proc.pid
			else:
				self.factory.err(self, "Brick startup failed. Check your configuration!")

			if self.open_internal_console and callable(self.open_internal_console):
				self.internal_console = self.open_internal_console()

		self.factory.emit("brick-started", self.name)
		self.run_condition = True
		self.post_poweron()

	def poweroff(self):
		if self.proc is None:
			return
		if self.run_condition is False:
			return
		self.run_condition = False
		if self.homehost:
			self.proc = None
			self.homehost.send(self.name+" off\n")
			return

		self.debug(_("Shutting down %s"), self.name)
		is_running = self.proc.poll() is None
		if is_running:
			if self.needsudo():
				with open(self.pidfile) as pidfile:
					pid = pidfile.readline().rstrip("\n")
					ret = os.system(self.settings.get('sudo') + ' "kill ' + pid + '"')
			else:
				if self.proc.pid <= 1:
					return

				pid = self.proc.pid
				try:
					self.proc.terminate()
				except Exception, err:
					self.factory.err(self, _("can not send SIGTERM: '%s'"), err)
				ret = os.system('kill ' + str(pid))
			if ret != 0:
				self.factory.err(self, _("can not stop brick error code:"), str(ret))
				return

		ret = None
		while ret is None:
			ret = self.proc.poll()
			time.sleep(0.2)

		self.proc = None
		self.need_restart_to_apply_changes = False
		if self.close_internal_console and callable(self.close_internal_console):
			self.close_internal_console()
		self.internal_console = None
		self.factory.emit("brick-stopped", self.name)
		self.post_poweroff()

	def post_poweron(self):
		self.active = True
		self.start_related_events(on=True)

	def post_poweroff(self):
		self.active = False
		self.start_related_events(off=True)

	def start_related_events(self, on=True, off=False):

		if on == False and off == False:
			return

		if (off and not self.cfg.poff_vbevent) or (on and not self.cfg.pon_vbevent):
			return

		if off:
			ev=self.factory.geteventbyname(self.cfg.poff_vbevent)
		elif on:
			ev=self.factory.geteventbyname(self.cfg.pon_vbevent)

		if ev:
			ev.poweron()
		else:
			self.warning("Warning. The Event '"+self.cfg.poff_vbevent+\
					"' attached to Brick '"+\
					self.name+"' is not available. Skipping execution.")

	#############################
	# Console related operations.
	#############################
	def has_console(self, closing = False):
		for i in range(1, 10):
			if self.proc != None and self.console() and os.path.exists(self.console()):
				return True
			else:
				if closing:
					return False
				time.sleep(0.5)
		return False


	def open_console(self):
		self.debug("open_console")
		if not self.has_console():
			return

		if os.access(self.settings.get('term'), os.X_OK):
			cmdline = [self.settings.get('term'), '-T', self.name, '-e', self.terminal, self.console()]
		elif os.access(self.settings.get('alt-term'), os.X_OK):
			cmdline = [self.settings.get('alt-term'), '-t', self.name, '-e', self.terminal + " " + self.console()]
		else:
			self.factory.err(self, _("Error: cannot start a terminal emulator"))
			return
		try:
			console = subprocess.Popen(cmdline)
		except:
			self.exception(_("Error running command line")+ " '" + cmdline + " '")
			return

	#Must be overridden in Qemu to use appropriate console as internal (stdin, stdout?)
	def open_internal_console(self):
		self.debug("open_internal_console")
		if not self.has_console():
			self.debug(self.get_type() + " " + _("does not have a console"))
			return None
		for i in range(1, 10):
			try:
				time.sleep(0.5)
				c = socket.socket(socket.AF_UNIX)
				c.connect(self.console())
			except:
				pass
			else:
				return c
		self.factory.err(self, self.get_type() + ": " + _("error opening internal console"))
		return None

	def send(self, msg):
		if self.internal_console == None or not self.active:
			self.debug(self.get_type()+": cancel send")
			return
		try:
			self.debug(self.get_type()+": sending '%s'", msg)
			self.internal_console.send(msg)
		except Exception, err:
			self.exception(self.get_type()+": send failed : %s", err)

	def recv(self):
		self.debug("recv")
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
		if not self.has_console(closing=True):
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
		self._needsudo = False
		self.internal_console = None
		self.icon = Icon(self)
		self.icon.get_img() #sic
		self.factory.eventsmodel.add_event(self)
		self.on_config_changed()
		self.timer = None

	def needsudo(self):
		return self.factory.TCP is None and self._needsudo

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
		if self.active:
			state = _('running')
		elif not self.configured():
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
		if self.active:
			self.poweroff()
		else:
			self.poweron()

	def configured(self):
		return (len(self.cfg.actions) > 0 and self.cfg.delay > 0)

	def initialize(self, attrlist):
		if 'add' in attrlist and 'addsh' in attrlist:
			raise InvalidAction(_("Error: config line must contain add OR "
				"addsh."))
		elif('add' in attrlist):
			configactions = list()
			configactions = (' '.join(attrlist)).split('add')
			for action in configactions[1:]:
				action = action.strip()
				self.cfg.actions.append(VbShellCommand(action))
				self.info(_("Added vb-shell command: '%s'"), unicode(action))
		elif('addsh' in attrlist):
			configactions = list()
			configactions = (' '.join(attrlist)).split('addsh')
			for action in configactions[1:]:
				action = action.strip()
				self.cfg.actions.append(ShellCommand(action))
				self.info(_("Added host-shell command: '%s'"), unicode(action))
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
				if isinstance(s, ShellCommand):
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
			raise BadConfig()
		if self.active:
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
		if not self.active:
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
					subprocess.Popen(action, shell = True)
				except:
					self.factory.err(self, "Error: cannot execute shell command \"%s\"" % action)
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
		if (self.cfg.get('fstp',False)):
			if self.cfg.fstp == '*':
				fstp = ", FSTP"
		if (self.cfg.get('hub',False)):
			if self.cfg.hub == '*':
				hub = ", HUB"
		return _("Ports:") + "%d%s%s" % ((int(unicode(self.cfg.get('numports','32')))), fstp, hub)

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
		self.debug( self.name + ": callback 'fstp' with argument " + arg)
		if arg:
			self.send("fstp/setfstp 1\n")
		else:
			self.send("fstp/setfstp 0\n")
		self.debug(self.recv())

	def cbset_hub(self, arg=False):
		self.debug( self.name + ": callback 'hub' with argument " + arg)
		if arg:
			self.send("port/sethub 1\n")
		else:
			self.send("port/sethub 0\n")
		self.debug(self.recv())

	def cbset_numports(self, arg="32"):
		self.debug( self.name + ": callback 'numports' with argument " + str(arg))
		self.send("port/setnumports " + str(arg))
		self.debug(self.recv())

class Tap(Brick):
	def __init__(self, _factory, _name):
		Brick.__init__(self, _factory, _name)
		self.pid = -1
		self.cfg.name = _name
		self.command_builder = {"-s":'sock', "*tap":"name"}
		self.cfg.sock = ""
		self.plugs.append(Plug(self))
		self._needsudo = True
		self.cfg.ip = "10.0.0.1"
		self.cfg.nm = "255.255.255.0"
		self.cfg.gw = ""
		self.cfg.mode = "off"

	def restore_self_plugs(self):
		self.plugs.append(Plug(self))

	def clear_self_socks(self, sock=None):
		self.cfg.sock=""

	def get_parameters(self):
		if self.plugs[0].sock:
			return _("plugged to %s ") % self.plugs[0].sock.brick.name

		return _("disconnected")

	def prog(self):
		return self.settings.get("vdepath") + "/vde_plug2tap"

	def get_type(self):
		return 'Tap'

	def console(self):
		return None

	def on_config_changed(self):
		if (self.plugs[0].sock is not None):
			self.cfg.sock = self.plugs[0].sock.path.rstrip("[]")
		if (self.proc is not None):
			self.need_restart_to_apply_changes = True

	def configured(self):
		return (self.plugs[0].sock is not None)

	def post_poweron(self):
		self.start_related_events(on=True)
		if self.cfg.mode == 'dhcp':
			if self.needsudo():
				ret = os.system(self.settings.get('sudo') + ' "dhclient ' + self.name + '"')
			else:
				ret = os.system('dhclient ' + self.name )


		elif self.cfg.mode == 'manual':
			if self.needsudo():
					# XXX Ugly, can't we ioctls?
					ret0 = os.system(self.settings.get('sudo') + ' "/sbin/ifconfig ' + self.name + ' ' + self.cfg.ip + ' netmask ' + self.cfg.nm + '"')
					if (len(self.cfg.gw) > 0):
						ret1 = os.system(self.settings.get('sudo') + ' "/sbin/route add default gw ' + self.cfg.gw + ' dev ' + self.name + '"')
			else:
					ret0 = os.system('/sbin/ifconfig ' + self.name + ' ' + self.cfg.ip + ' netmask ' + self.cfg.nm )
					if (len(self.cfg.gw) > 0):
						ret1 = os.system('/sbin/route add default gw ' + self.cfg.gw + ' dev ' + self.name)
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

	def restore_self_plugs(self):
		while len(self.plugs) < 2 :
			self.plugs.append(Plug(self))

	def clear_self_socks(self, sock=None):
		if sock is None:
			self.cfg.sock0=""
			self.cfg.sock1=""
		elif self.cfg.sock0 == sock:
			self.cfg.sock0=""
		elif self.cfg.sock1 == sock:
			self.cfg.sock1=""

	def get_parameters(self):
		if self.plugs[0].sock:
			p0 = self.plugs[0].sock.brick.name
		else:
			p0 = _("disconnected")

		if self.plugs[1].sock:
			p1 = self.plugs[1].sock.brick.name
		else:
			p1 = _("disconnected")

		if p0 != _('disconnected') and p1 != _('disconnected'):
			return _("Configured to connect") + " " + p0 + " " + "to" + " " + p1
		else:
			return _("Not yet configured.") + " " +\
				_("Left plug is") + " " + p0 +" " + _("and right plug is")+\
				" " + p1

	def on_config_changed(self):
		if (self.plugs[0].sock is not None):
			self.cfg.sock0 = self.plugs[0].sock.path.rstrip('[]')
		if (self.plugs[1].sock is not None):
			self.cfg.sock1 = self.plugs[1].sock.path.rstrip('[]')
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

class PyWireThread(Thread):
	def __init__(self, wire):
		self.wire = wire
		self.run_condition=False
		Thread.__init__(self)



	def run(self):
		self.run_condition=True
		self.wire.pid = -10
		host1 = self.wire.factory.TCP
		host0 = None
		if self.wire.factory.TCP is not None:
		# ON TCP SERVER SIDE OF REMOTE WIRE
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			for port in range(32400, 32500):
				try:
					s.bind(('', port))
				except:
					continue
				else:
					self.wire.factory.TCP.sock.send("udp "+self.wire.name+" remoteport " + str(port) + '\n')
			v = VdePlug.VdePlug(self.wire.plugs[0].sock.path)
			p = select.poll()
			p.register(v.datafd().fileno(), select.POLLIN)
			p.register(s.fileno(), select.POLLIN)
			while self.run_condition:
				res = p.poll(250)
				for (f,e) in res:
					if f == v.datafd().fileno() and (e & select.POLLIN):
						buf = v.recv(2000)
						s.sendto(buf, (self.wire.factory.TCP.master_address[0],self.wire.remoteport))
					if f == s.fileno() and (e & select.POLLIN):
						buf = s.recv(2000)
						v.send(buf)

		elif self.wire.plugs[1].sock.brick.homehost == self.wire.plugs[0].sock.brick.homehost:
		# LOCAL WIRE
			v0 = VdePlug.VdePlug(self.wire.plugs[0].sock.path)
			v1 = VdePlug.VdePlug(self.wire.plugs[1].sock.path)
			p = select.epoll()
			p.register(v0.datafd().fileno(), select.POLLIN)
			p.register(v1.datafd().fileno(), select.POLLIN)
			while self.run_condition:
				res = p.poll(0.250)
				for (f,e) in res:
					if f == v0.datafd().fileno() and (e & select.POLLIN):
						buf = v0.recv(2000)
						v1.send(buf)
					if f == v1.datafd().fileno() and (e & select.POLLIN):
						buf = v1.recv(2000)
						v0.send(buf)
		else:
		# ON GUI SIDE OF REMOTE WIRE
			if host0:
				v = VdePlug.VdePlug(self.wire.plugs[1].sock.path)
				remote = self.wire.plugs[0].sock.brick
			else:
				v = VdePlug.VdePlug(self.wire.plugs[0].sock.path)
				remote = self.wire.plugs[1].sock.brick
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			for port in range(32400, 32500):
				try:
					s.bind(('', port))
				except:
					continue
				if self.wire.remoteport == 0:
					remote.homehost.send("udp "+self.wire.name+" " + remote.name + " " +str(port))
			while self.run_condition:
				if self.wire.remoteport == 0:
					time.sleep(1)
					continue
				p = select.poll()
				p.register(v.datafd().fileno(), select.POLLIN)
				p.register(s.fileno(), select.POLLIN)
				res = p.poll(250)
				for (f,e) in res:
					if f == v.datafd().fileno() and (e & select.POLLIN):
						buf = v.recv(2000)
						s.sendto(buf, (remote.homehost.addr[0],self.wire.remoteport))
					if f == s.fileno() and (e & select.POLLIN):
						buf = s.recv(2000)
						v.send(buf)
			remote.homehost.send(self.wire.name+" off")

			print "bye!"
			self.wire.pid = -1


	def poll(self):
		if self.isAlive():
			return None
		else:
			return True

	def wait(self):
		return self.join()

	def terminate(self):
		self.run_condition=False

	def send_signal(self, signo):
		# TODO: Suspend/resume.
		self.run_condition=False


class PyWire(Wire):

	def __init__(self,factory, name, remoteport = 0):
		self.remoteport = remoteport
		Wire.__init__(self, factory, name)

	def on_config_changed(self):
		pass

	def set_remoteport(self, port):
		self.remoteport = int(port)

	def prog(self):
		return ''

	def _poweron(self):
		# self.proc
		self.pid = -1
		self.proc = PyWireThread(self)
		self.proc.start()

	def poweroff(self):
		self.remoteport = 0
		if self.proc:
			self.proc.terminate()
			self.proc.join()
			del(self.proc)
			self.proc=None



#	def configured(self):
#		if self.factory.TCP is not None:
#			return len(self.plugs) != 0 and self.plugs[0].sock is not None
#		else:
#			return (self.plugs[0].sock is not None and self.plugs[1].sock is not None)

#	def connected(self):
#		self.debug( "CALLED PyWire connected" )
#		return True

class Wirefilter(Wire):
	def __init__(self, _factory, _name):
		Wire.__init__(self, _factory, _name)
		self.command_builder = {
			"-N":"nofifo",
			"-M":self.console,
		}

		self.cfg.bandwidthLR = ""
		self.cfg.bandwidthRL = ""
		self.cfg.bandwidth = ""
		self.cfg.bandwidthLRJ = ""
		self.cfg.bandwidthRLJ = ""
		self.cfg.bandwidthJ = ""
		self.cfg.bandwidthmult = "Mega"
		self.cfg.bandwidthunit = "bit/s"
		self.cfg.bandwidthdistribLR = "Uniform"
		self.cfg.bandwidthdistribRL = "Uniform"
		self.cfg.bandwidthdistrib = "Uniform"
		self.cfg.bandwidthsymm = "*"

		self.cfg.speedLR = ""
		self.cfg.speedRL = ""
		self.cfg.speed = ""
		self.cfg.speedLRJ = ""
		self.cfg.speedRLJ = ""
		self.cfg.speedJ = ""
		self.cfg.speedmult = "Mega"
		self.cfg.speedunit = "bit/s"
		self.cfg.speeddistribLR = "Uniform"
		self.cfg.speeddistribRL = "Uniform"
		self.cfg.speeddistrib = "Uniform"
		self.cfg.speedsymm = "*"
		self.cfg.speedenable = ""

		self.cfg.delayLR = ""
		self.cfg.delayRL = ""
		self.cfg.delay = ""
		self.cfg.delayLRJ = ""
		self.cfg.delayRLJ = ""
		self.cfg.delayJ = ""
		self.cfg.delaymult = "milli"
		self.cfg.delayunit = "seconds"
		self.cfg.delaydistribLR = "Uniform"
		self.cfg.delaydistribRL = "Uniform"
		self.cfg.delaydistrib = "Uniform"
		self.cfg.delaysymm = "*"

		self.cfg.chanbufsizeLR = ""
		self.cfg.chanbufsizeRL = ""
		self.cfg.chanbufsize = ""
		self.cfg.chanbufsizeLRJ = ""
		self.cfg.chanbufsizeRLJ = ""
		self.cfg.chanbufsizeJ = ""
		self.cfg.chanbufsizemult = "Kilo"
		self.cfg.chanbufsizeunit = "bytes"
		self.cfg.chanbufsizedistribLR = "Uniform"
		self.cfg.chanbufsizedistribRL = "Uniform"
		self.cfg.chanbufsizedistrib = "Uniform"
		self.cfg.chanbufsizesymm = "*"

		self.cfg.lossLR = ""
		self.cfg.lossRL = ""
		self.cfg.loss = ""
		self.cfg.lossLRJ = ""
		self.cfg.lossRLJ = ""
		self.cfg.lossJ = ""
		self.cfg.lossmult = ""
		self.cfg.lossunit = "%"
		self.cfg.lossdistribLR = "Uniform"
		self.cfg.lossdistribRL = "Uniform"
		self.cfg.lossdistrib = "Uniform"
		self.cfg.losssymm = "*"

		self.cfg.dupLR = ""
		self.cfg.dupRL = ""
		self.cfg.dup = ""
		self.cfg.dupLRJ = ""
		self.cfg.dupRLJ = ""
		self.cfg.dupJ = ""
		self.cfg.dupmult = ""
		self.cfg.dupunit = "%"
		self.cfg.dupdistribLR = "Uniform"
		self.cfg.dupdistribRL = "Uniform"
		self.cfg.dupdistrib = "Uniform"
		self.cfg.dupsymm = "*"

		self.cfg.noiseLR = ""
		self.cfg.noiseRL = ""
		self.cfg.noise = ""
		self.cfg.noiseLRJ = ""
		self.cfg.noiseRLJ = ""
		self.cfg.noiseJ = ""
		self.cfg.noisemult = "Mega"
		self.cfg.noiseunit = "bit"
		self.cfg.noisedistribLR = "Uniform"
		self.cfg.noisedistribRL = "Uniform"
		self.cfg.noisedistrib = "Uniform"
		self.cfg.noisesymm = "*"

		self.cfg.lostburstLR = ""
		self.cfg.lostburstRL = ""
		self.cfg.lostburst = ""
		self.cfg.lostburstLRJ = ""
		self.cfg.lostburstRLJ = ""
		self.cfg.lostburstJ = ""
		self.cfg.lostburstmult = ""
		self.cfg.lostburstunit = "seconds"
		self.cfg.lostburstdistribLR = "Uniform"
		self.cfg.lostburstdistribRL = "Uniform"
		self.cfg.lostburstdistrib = "Uniform"
		self.cfg.lostburstsymm = "*"

		self.cfg.mtuLR = ""
		self.cfg.mtuRL = ""
		self.cfg.mtu = ""
		self.cfg.mtumult = "Kilo"
		self.cfg.mtuunit = "bytes"
		self.cfg.mtusymm = "*"

	def gui_to_wf_value(self, base, jitter, distrib, mult, unit, def_mult="", def_unit=""):
		#print (base,jitter,distrib,mult,unit,def_mult,def_unit)
		b = base
		if not b: return "0"

		u = unit
		if u != def_unit:
			if def_unit.startswith("byte"):
				b = float(b) / 8
			else: b = float(b) * 8

		value = str(round(float(b), 6)) # f.e. 50

		if mult != def_mult:
			if mult is "milli" and def_mult is "": m = "K"
			else: m = mult[0]
		else: m = ""

		j = jitter
		if j is not "":
			if def_unit is not "%":
				j = str(round((float(b) * float(j)/100), 6)) + m # GUI=100K(+-)10% becomes WF=100+20K
			else: j = str(round(float(j), 6))

		if distrib and distrib[0] is ("G" or "N"):
			d = "N"
		else: d = "U"

		if j is not "":
			value = value + "+" + j # f.e. 50+5K
			value = value + d # f.e. 50+5KU/N
		else: value = value + m # f.e. 50K

		return str(value)

	def compute_bandwidth(self):
		return self.gui_to_wf_value(self.cfg.bandwidth, self.cfg.bandwidthJ,\
								self.cfg.bandwidthdistrib, self.cfg.bandwidthmult,\
								self.cfg.bandwidthunit, "", "byte/s")

	def compute_bandwidthLR(self):
	 	return self.gui_to_wf_value(self.cfg.bandwidthLR, self.cfg.bandwidthLRJ,\
									self.cfg.bandwidthdistribLR, self.cfg.bandwidthmult,\
									self.cfg.bandwidthunit, "", "byte/s")

	def compute_bandwidthRL(self):
	 	return self.gui_to_wf_value(self.cfg.bandwidthRL, self.cfg.bandwidthRLJ, self.cfg.bandwidthdistribRL, self.cfg.bandwidthmult,
									self.cfg.bandwidthunit, "", "byte/s")

	def compute_speed(self):
		return self.gui_to_wf_value(self.cfg.speed, self.cfg.speedJ, self.cfg.speeddistrib, self.cfg.speedmult,
									self.cfg.speedunit, "", "byte/s")

	def compute_speedLR(self):
		return self.gui_to_wf_value(self.cfg.speedLR, self.cfg.speedLRJ, self.cfg.speeddistribLR, self.cfg.speedmult,
									self.cfg.speedunit, "", "byte/s")

	def compute_speedRL(self):
		return self.gui_to_wf_value(self.cfg.speedRL, self.cfg.speedRLJ, self.cfg.speeddistribRL, self.cfg.speedmult,
									self.cfg.speedunit, "", "byte/s")

	def compute_delay(self):
		return self.gui_to_wf_value(self.cfg.delay, self.cfg.delayJ, self.cfg.delaydistrib, self.cfg.delaymult,
									self.cfg.delayunit, "milli", "seconds")

	def compute_delayLR(self):
		return self.gui_to_wf_value(self.cfg.delayLR, self.cfg.delayLRJ, self.cfg.delaydistribLR, self.cfg.delaymult,
									self.cfg.delayunit, "milli", "seconds")

	def compute_delayRL(self):
		return self.gui_to_wf_value(self.cfg.delayRL, self.cfg.delayRLJ, self.cfg.delaydistribRL, self.cfg.delaymult,
									self.cfg.delayunit, "milli", "seconds")

	def compute_chanbufsize(self):
		return self.gui_to_wf_value(self.cfg.chanbufsize, self.cfg.chanbufsizeJ, self.cfg.chanbufsizedistrib, self.cfg.chanbufsizemult,
									self.cfg.chanbufsizeunit, "", "bytes")

	def compute_chanbufsizeLR(self):
		return self.gui_to_wf_value(self.cfg.chanbufsizeLR, self.cfg.chanbufsizeLRJ, self.cfg.chanbufsizedistribLR, self.cfg.chanbufsizemult,
									self.cfg.chanbufsizeunit, "", "bytes")


	def compute_chanbufsizeRL(self):
		return self.gui_to_wf_value(self.cfg.chanbufsizeRL, self.cfg.chanbufsizeRLJ, self.cfg.chanbufsizedistribRL, self.cfg.chanbufsizemult,
									self.cfg.chanbufsizeunit, "", "bytes")

	def compute_loss(self):
		return self.gui_to_wf_value(self.cfg.loss, self.cfg.lossJ, self.cfg.lossdistrib, self.cfg.lossmult,
									self.cfg.lossunit, "", "%")

	def compute_lossLR(self):
		return self.gui_to_wf_value(self.cfg.lossLR, self.cfg.lossLRJ, self.cfg.lossdistribLR, self.cfg.lossmult,
									self.cfg.lossunit, "", "%")

	def compute_lossRL(self):
		return self.gui_to_wf_value(self.cfg.lossRL, self.cfg.lossRLJ, self.cfg.lossdistribRL, self.cfg.lossmult,
									self.cfg.lossunit, "", "%")

	def compute_dup(self):
		return self.gui_to_wf_value(self.cfg.dup, self.cfg.dupJ, self.cfg.dupdistrib, self.cfg.dupmult,
									self.cfg.dupunit, "", "%")

	def compute_dupLR(self):
		return self.gui_to_wf_value(self.cfg.dupLR, self.cfg.dupLRJ, self.cfg.dupdistribLR, self.cfg.dupmult,
									self.cfg.dupunit, "", "%")

	def compute_dupRL(self):
		return self.gui_to_wf_value(self.cfg.dupRL, self.cfg.dupRLJ, self.cfg.dupdistribRL, self.cfg.dupmult,
									self.cfg.dupunit, "", "%")

	def compute_noise(self):
		return self.gui_to_wf_value(self.cfg.noise, self.cfg.noiseJ, self.cfg.noisedistrib, self.cfg.noisemult,
									self.cfg.noiseunit, "Mega", "bit")

	def compute_noiseLR(self):
		return self.gui_to_wf_value(self.cfg.noiseLR, self.cfg.noiseLRJ, self.cfg.noisedistribLR, self.cfg.noisemult,
									self.cfg.noiseunit, "Mega", "bit")

	def compute_noiseRL(self):
		return self.gui_to_wf_value(self.cfg.noiseRL, self.cfg.noiseRLJ, self.cfg.noisedistribRL, self.cfg.noisemult,
									self.cfg.noiseunit, "Mega", "bit")

	def compute_lostburst(self):
		return self.gui_to_wf_value(self.cfg.lostburst, self.cfg.lostburstJ, self.cfg.lostburstdistrib, self.cfg.lostburstmult,
									self.cfg.lostburstunit, "", "seconds")

	def compute_lostburstLR(self):
		return self.gui_to_wf_value(self.cfg.lostburstLR, self.cfg.lostburstLRJ, self.cfg.lostburstdistribLR, self.cfg.lostburstmult,
									self.cfg.lostburstunit, "", "seconds")

	def compute_lostburstRL(self):
		return self.gui_to_wf_value(self.cfg.lostburstRL, self.cfg.lostburstRLJ, self.cfg.lostburstdistribRL, self.cfg.lostburstmult,
									self.cfg.lostburstunit, "", "seconds")

	def compute_mtu(self):
		return self.gui_to_wf_value(self.cfg.mtu, "", "", self.cfg.mtumult,
									self.cfg.mtuunit, "", "bytes")

	def compute_mtuLR(self):
		return self.gui_to_wf_value(self.cfg.mtuLR, "", "", self.cfg.mtumult,
									self.cfg.mtuunit, "", "bytes")

	def compute_mtuRL(self):
		return self.gui_to_wf_value(self.cfg.mtuRL, "", "", self.cfg.mtumult,
									self.cfg.mtuunit, "", "bytes")

	def args(self):
		res = []
		res.append(self.prog())
		res.append('-v')
		res.append(self.cfg.sock0 + ":" + self.cfg.sock1)

		#Bandwidth
		if len(self.cfg.bandwidth) > 0 and int(self.cfg.bandwidth) > 0:
			res.append("-b")
			value = self.compute_bandwidth()
			res.append(value)
		else:
			if len(self.cfg.bandwidthLR) > 0:
				res.append("-b")
				value = self.compute_bandwidthLR()
				res.append("LR" + value)
			if len(self.cfg.bandwidthRL) > 0:
				res.append("-b")
				value = self.compute_bandwidthRL()
				res.append("RL" + value)

		#Speed
		if len(self.cfg.speed) > 0 and int(self.cfg.speed) > 0:
			res.append("-s")
			value = self.compute_speed()
			res.append(value)
		else:
			if len(self.cfg.speedLR) > 0:
				res.append("-s")
				value = self.compute_speedLR()
				res.append("LR" + value)
			if len(self.cfg.speedRL) > 0:
				res.append("-s")
				value = self.compute_speedRL()
				res.append("RL" + value)

		#Delay
		if len(self.cfg.delay) > 0 and int(self.cfg.delay) > 0:
			res.append("-d")
			value = self.compute_delay()
			res.append(value)
		else:
			if len(self.cfg.delayLR) > 0:
				res.append("-d")
				value = self.compute_delayLR()
				res.append("LR" + value)
			if len(self.cfg.delayRL) > 0:
				res.append("-d")
				value = self.compute_delayRL()
				res.append("RL" + value)

		#Chanbufsize
		if len(self.cfg.chanbufsize) > 0 and int(self.cfg.chanbufsize) > 0:
			res.append("-c")
			value = self.compute_chanbufsize()
			res.append(value)
		else:
			if len(self.cfg.chanbufsizeLR) > 0:
				res.append("-c")
				value = self.compute_chanbufsizeLR()
				res.append("LR" + value)
			if len(self.cfg.chanbufsizeRL) > 0:
				res.append("-c")
				value = self.compute_chanbufsizeRL()
				res.append("RL" + value)

		#Loss
		if len(self.cfg.loss) > 0 and int(self.cfg.loss) > 0:
			res.append("-l")
			value = self.compute_loss()
			res.append(value)
		else:
			if len(self.cfg.lossLR) > 0:
				res.append("-l")
				value = self.compute_lossLR()
				res.append("LR" + value)
			if len(self.cfg.lossRL) > 0:
				res.append("-l")
				value = self.compute_lossRL()
				res.append("RL" + value)

		#Dup
		if len(self.cfg.dup) > 0 and int(self.cfg.dup) > 0:
			res.append("-D")
			value = self.compute_dup()
			res.append(value)
		else:
			if len(self.cfg.dupLR) > 0:
				res.append("-D")
				value = self.compute_dupLR()
				res.append("LR" + value)
			if len(self.cfg.dupRL) > 0:
				res.append("-D")
				value = self.compute_dupRL()
				res.append("RL" + value)

		#Noise
		if len(self.cfg.noise) > 0 and int(self.cfg.noise) > 0:
			res.append("-n")
			value = self.compute_noise()
			res.append(value)
		else:
			if len(self.cfg.noiseLR) > 0:
				res.append("-n")
				value = self.compute_noiseLR()
				res.append("LR" + value)
			if len(self.cfg.noiseRL) > 0:
				res.append("-n")
				value = self.compute_noiseRL()
				res.append("RL" + value)

		#Lostburst
		if len(self.cfg.lostburst) > 0 and int(self.cfg.lostburst) > 0:
			res.append("-L")
			value = self.compute_lostburst()
			res.append(value)
		else:
			if len(self.cfg.lostburstLR) > 0:
				res.append("-L")
				value = self.compute_lostburstLR()
				res.append("LR" + value)
			if len(self.cfg.lostburstRL) > 0:
				res.append("-L")
				value = self.compute_lostburstRL()
				res.append("RL" + value)

		#MTU
		if len(self.cfg.mtu) > 0 and int(self.cfg.mtu) > 0:
			res.append("-m")
			value = self.compute_mtu()
			res.append(value)
		else:
			if len(self.cfg.mtuLR) > 0:
				res.append("-m")
				value = self.compute_mtuLR()
				res.append("LR" + value)
			if len(self.cfg.mtuRL) > 0:
				res.append("-m")
				value = self.compute_mtuRL()
				res.append("RL" + value)

		for param in Brick.build_cmd_line(self):
			res.append(param)
		return res

	def prog(self):
		return self.settings.get("vdepath") + "/wirefilter"

	def get_type(self):
		return 'Wirefilter'

	#callbacks for live-management
	def cbset_bandwidthLR(self, arg=0):
		if not self.active: return
		value = self.compute_bandwidthLR()
		self.debug(self.name + ": callback 'bandwidth LR' with argument " + value)
		self.send("bandwidth LR " + value + "\n")
		self.debug(self.recv())

	def cbset_bandwidthRL(self, arg=0):
		if not self.active: return
		value = self.compute_bandwidthRL()
		self.debug(self.name + ": callback 'bandwidth RL' with argument " + value)
		self.send("bandwidth RL " + value + "\n")
		self.debug(self.recv())

	def cbset_bandwidth(self, arg=0):
		if not self.active: return
		if self.cfg.bandwidthsymm != "*": return
		value = self.compute_bandwidth()
		self.debug(self.name + ": callback 'bandwidth RL&LR' with argument " + value)
		self.send("bandwidth " + value + "\n")
		self.debug(self.recv())

	def cbset_speedLR(self, arg=0):
		if not self.active: return
		value = self.compute_speedLR()
		self.debug(self.name + ": callback 'speed LR' with argument " + value)
		self.send("speed LR " + value + "\n")
		self.debug(self.recv())

	def cbset_speedRL(self, arg=0):
		if not self.active: return
		value = self.compute_speedRL()
		self.debug(self.name + ": callback 'speed RL' with argument " + value)
		self.send("speed RL " + value + "\n")
		self.debug(self.recv())

	def cbset_speed(self, arg=0):
		if not self.active: return
		if self.cfg.speedsymm != "*": return
		value = self.compute_speed()
		self.debug(self.name + ": callback 'speed LR&RL' with argument " + value)
		self.send("speed " + value + "\n")
		self.debug(self.recv())

	def cbset_delayLR(self, arg=0):
		if not self.active: return
		value = self.compute_delayLR()
		self.debug(self.name + ": callback 'delay LR' with argument " + value)
		self.send("delay LR " + value + "\n")
		self.debug(self.recv())

	def cbset_delayRL(self, arg=0):
		if not self.active: return
		value = self.compute_delayRL()
		self.debug(self.name + ": callback 'delay RL' with argument " + value)
		self.send("delay RL " + value + "\n")
		self.debug(self.recv())

	def cbset_delay(self, arg=0):
		if not self.active: return
		if self.cfg.delaysymm != "*": return
		value = self.compute_delay()
		self.debug(self.name + ": callback 'delay LR&RL' with argument " + value)
		self.send("delay " + value + "\n")
		self.debug(self.recv())

	def cbset_chanbufsizeLR(self, arg=0):
		if not self.active: return
		value = self.compute_chanbufsizeLR()
		self.debug(self.name + ": callback 'chanbufsize (capacity) LR' with argument " + value)
		self.send("chanbufsize LR " + value + "\n")
		self.debug(self.recv())

	def cbset_chanbufsizeRL(self, arg=0):
		if not self.active: return
		value = self.compute_chanbufsizeRL()
		self.debug(self.name + ": callback 'chanbufsize (capacity) RL' with argument " + value)
		self.send("chanbufsize RL " + value + "\n")
		self.debug(self.recv())

	def cbset_chanbufsize(self, arg=0):
		if not self.active: return
		if self.cfg.chanbufsizesymm != "*": return
		value = self.compute_chanbufsize()
		self.debug(self.name + ": callback 'chanbufsize (capacity) LR&RL' with argument " + value)
		self.send("chanbufsize " + value + "\n")
		self.debug(self.recv())

	def cbset_lossLR(self, arg=0):
		if not self.active: return
		value = self.compute_lossLR()
		self.debug(self.name + ": callback 'loss LR' with argument " + value)
		self.send("loss LR " + value + "\n")
		self.debug(self.recv())

	def cbset_lossRL(self, arg=0):
		if not self.active: return
		value = self.compute_lossRL()
		self.debug(self.name + ": callback 'loss RL' with argument " + value)
		self.send("loss RL " + value + "\n")
		self.debug(self.recv())

	def cbset_loss(self, arg=0):
		if not self.active: return
		if self.cfg.losssymm != "*": return
		value = self.compute_loss()
		self.debug(self.name + ": callback 'loss LR&RL' with argument " + value)
		self.send("loss " + value + "\n")
		self.debug(self.recv())

	def cbset_dupLR(self, arg=0):
		if not self.active: return
		value = self.compute_dupLR()
		self.debug(self.name + ": callback 'dup LR' with argument " + value)
		self.send("dup LR " + value + "\n")
		self.debug(self.recv())

	def cbset_dupRL(self, arg=0):
		if not self.active: return
		value = self.compute_dupRL()
		self.debug(self.name + ": callback 'dup RL' with argument " + value)
		self.send("dup RL " + value + "\n")
		self.debug(self.recv())

	def cbset_dup(self, arg=0):
		if not self.active: return
		if self.cfg.dupsymm != "*": return
		value = self.compute_dup()
		self.debug(self.name + ": callback 'dup RL&LR' with argument " + value)
		self.send("dup " + value + "\n")
		self.debug(self.recv())

	def cbset_noiseLR(self, arg=0):
		if not self.active: return
		value = self.compute_noiseLR()
		self.debug(self.name + ": callback 'noise LR' with argument " + value)
		self.send("noise LR " + value + "\n")
		self.debug(self.recv())

	def cbset_noiseRL(self, arg=0):
		if not self.active: return
		value = self.compute_noiseRL()
		self.debug(self.name + ": callback 'noise RL' with argument " + value)
		self.send("noise RL " + value + "\n")
		self.debug(self.recv())

	def cbset_noise(self, arg=0):
		if not self.active: return
		if self.cfg.noisesymm != "*": return
		value = self.compute_noise()
		self.debug(self.name + ": callback 'noise LR&RL' with argument " + value)
		self.send("noise " + value + "\n")
		self.debug(self.recv())

	def cbset_lostburstLR(self, arg=0):
		if not self.active: return
		value = self.compute_lostburstLR()
		self.debug(self.name + ": callback 'lostburst LR' with argument " + value)
		self.send("lostburst LR " + value + "\n")
		self.debug(self.recv())

	def cbset_lostburstRL(self, arg=0):
		if not self.active: return
		value = self.compute_lostburstRL()
		self.debug(self.name + ": callback 'lostburst RL' with argument " + value)
		self.send("lostburst RL " + value + "\n")
		self.debug(self.recv())

	def cbset_lostburst(self, arg=0):
		if not self.active: return
		if self.cfg.lostburstsymm != "*": return
		value = self.compute_lostburst()
		self.debug(self.name + ": callback 'lostburst RL&RL' with argument " + value)
		self.send("lostburst " + value + "\n")
		self.debug(self.recv())

	def cbset_mtuLR(self, arg=0):
		if not self.active: return
		value = self.compute_mtuLR()
		self.debug(self.name + ": callback 'mtu LR' with argument " + value)
		self.send("mtu LR " + value + "\n")
		self.debug(self.recv())

	def cbset_mtuRL(self, arg=0):
		if not self.active: return
		value = self.compute_mtuRL()
		self.debug(self.name + ": callback 'mtu RL' with argument " + value)
		self.send("mtu RL " + value + "\n")
		self.debug(self.recv())

	def cbset_mtu(self, arg=0):
		if not self.active: return
		if self.cfg.mtusymm != "*": return
		value = self.compute_mtu()
		self.debug(self.name + ": callback 'mtu LR&RL' with argument " + value)
		self.send("mtu " + value + "\n")
		self.debug(self.recv())

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

	def restore_self_plugs(self):
		self.plugs.append(Plug(self))

	def clear_self_socks(self, sock=None):
		self.cfg.sock=""

	def get_parameters(self):
		if self.plugs[0].sock:
			return _("plugged to") + " " + self.plugs[0].sock.brick.name + " " +\
				_("listening to udp:") + " " + str(self.cfg.port)
		return _("disconnected")

	def prog(self):
		return self.settings.get("vdepath") + "/vde_cryptcab"

	def get_type(self):
		return 'TunnelListen'

	def on_config_changed(self):
		if (self.plugs[0].sock is not None):
			self.cfg.sock = self.plugs[0].sock.path.rstrip('[]')
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

	#def post_poweroff(self):
	#	os.unlink("/tmp/tunnel_%s.key" % self.name)
	#	pass


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
			return _("plugged to") + " " + self.plugs[0].sock.brick.name +\
				_(", connecting to udp://") + str(self.cfg.host)

		return _("disconnected")

	def on_config_changed(self):
		if (self.plugs[0].sock is not None):
			self.cfg.sock = self.plugs[0].sock.path.rstrip('[]')

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
		self.mac = tools.RandMac()
		self.model = 'rtl8139'
		self.vlan = len(self.brick.plugs) + len(self.brick.socks)
		self.mode = 'vde'

class VMSock(Sock, BrickConfig):
	def __init__(self,brick):
		Sock.__init__(self, brick)
		self.mac = tools.RandMac()
		self.model = 'rtl8139'
		self.vlan = len(self.brick.plugs) + len(self.brick.socks)
		self.path = MYPATH + "/" + self.brick.name+ "_sock_eth" + str(self.vlan) + "[]"
		self.nickname = self.path.split('/')[-1].rstrip('[]')
	def connect(self, endpoint):
		return


class VMPlugHostonly(VMPlug):
	def __init__(self, _brick):
		VMPlug.__init__(self, _brick)
		self.mode = 'hostonly'

	def connect(self, endpoint):
		return

	def configured(self):
		return True

	def connected(self):
		self.debug( "CALLED hostonly connected" )
		return True

class DiskImage():
	''' Class DiskImage '''
	''' locked if already in use as read/write non-cow. '''
	''' VMDisk must associate to this, and must check the locked flag
		before use '''

	def __init__(self, name, path, description=""):
		self.name = name
		self.path = path
		if description!="":
			self.set_description(description)
		self.vmdisks = []
		self.master = None

	def rename(self, newname):
		self.name = newname
		for vmd in self.vmdisks:
			vmd.VM.cfg.set("base"+vmd.device +'='+ self.name)

	def set_master(self, vmdisk):
		if self.master is None:
			self.master = vmdisk
		if self.master == vmdisk:
			return True
		else:
			return False

	def add_vmdisk(self, vmdisk):
		for vmd in self.vmdisks:
			if vmd == vmdisk:
				return
		self.vmdisks.append(vmdisk)

	def del_vmdisk(self, vmdisk):
		self.vmdisks.remove(vmdisk)
		if len(self.vmdisks) == 0 or self.master == vmdisk:
			self.master = None

	def description_file(self):
		return self.path + ".vbdescr"

	def set_description(self,descr):
		try:
			f = open(self.description_file(), "w+")
		except:
			return False
		f.write(str(descr))
		f.flush()
		f.close()
		return True

	def get_description(self):
		try:
			f = open(self.description_file(), "r")
		except:
			return ""
		try:
			descr = f.read()
		except:
			return ""
		f.close()
		return descr

	def get_cows(self):
		count = 0
		for vmd in self.vmdisks:
			if vmd.cow:
				count+=1
		return count

	def get_users(self):
		return len(self.vmdisks)



class VMDisk():
	def __init__(self, VM, dev, basefolder=""):
		self.VM = VM
		self.cow = False
		self.device = dev
		self.basefolder = basefolder
		self.image = None

	def args(self, k):
		ret = []

		diskname = self.get_real_disk_name()

		if k:
			ret.append("-" + self.device)
		ret.append(diskname)
		return ret

	def set_image(self, image):
		''' Old virtualbricks (0.4) will pass a full path here, new behavior
			is to pass the image nickname '''

		if len(image) == 0:
			img = None
			if self.image:
				self.image.vmdisks.remove(self)
				self.image = None
			return

		''' Try to look for image by nickname '''
		img = self.VM.factory.get_image_by_name(image)
		if img:
			self.image = img
			img.add_vmdisk(self)
			self.VM.cfg.set("base"+self.device +'='+ img.name)
			if not self.cow and self.VM.cfg.get("snapshot")=="" and self.image.set_master(self):
				print "Machine "+self.VM.name+" acquired master lock on image " + self.image.name
			return True

		''' If that fails: rollback to old behavior, and search for an already
			registered image under that path. '''
		if img is None:
			img = self.VM.factory.get_image_by_path(image)

		''' If that fails: check for path existence and create a new image based
			there. It may be that we are using new method for the first time. '''
		if img is None:
			if os.access(image, os.R_OK):
				img = self.VM.factory.new_disk_image(os.path.basename(image), image)
		if img is None:
			return False

		self.image = img
		img.add_vmdisk(self)
		self.VM.cfg.set("base"+self.device +'='+ img.name)
		if not self.cow and self.VM.cfg.get("snapshot")=="":
			if self.image.set_master(self):
				print "Machine "+self.VM.name+" acquired master lock on image " + self.image.name
			else:
				print "ERROR SETTING MASTER!!"
		return True


	def get_base(self):
		return self.image.path

	def get_real_disk_name(self):
		if self.image == None:
			return ""
		if self.cow:
			if not os.path.exists(self.basefolder):
				os.makedirs(self.basefolder)
			cowname = self.basefolder + "/" + self.Name + "_" + self.device + ".cow"
			if not os.access(cowname, os.R_OK):
				os.system('qemu-img create -b %s -f cow %s' % (self.get_base(), cowname))
				os.system('sync')
				time.sleep(2)
			return cowname
		else:
			return self.image.path

	def readonly(self):
		if (self.VM.cfg.snapshot == "*"):
			return True
		else:
			return False

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
		# PRIVATE COW IMAGES MUST BE CREATED IN A DIFFERENT DIRECTORY FOR EACH PROJECT
		self.basepath = self.settings.get("baseimages") + "/." + self.project_parms['id']
		self.cfg.set_obj("hda", VMDisk(self, "hda", self.basepath))
		self.cfg.privatehda = ""
		self.cfg.basehdb = ""
		self.cfg.set_obj("hdb", VMDisk(self, "hdb", self.basepath))
		self.cfg.privatehdb = ""
		self.cfg.basehdc = ""
		self.cfg.set_obj("hdc", VMDisk(self, "hdc", self.basepath))
		self.cfg.privatehdc = ""
		self.cfg.basehdd = ""
		self.cfg.set_obj("hdd", VMDisk(self, "hdd", self.basepath))
		self.cfg.privatehdd = ""
		self.cfg.basefda = ""
		self.cfg.set_obj("fda", VMDisk(self, "fda", self.basepath))
		self.cfg.privatefda = ""
		self.cfg.basefdb = ""
		self.cfg.set_obj("fdb", VMDisk(self, "fdb", self.basepath))
		self.cfg.privatefdb = ""
		self.cfg.basemtdblock = ""
		self.cfg.set_obj("mtdblock", VMDisk(self, "mtdblock", self.basepath))
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
			'#append':'kopt',
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
		txt = _("command:") + " %s, ram: %s" % (self.prog(), self.cfg.ram)
		for p in self.plugs:
			if p.mode == 'hostonly':
				txt += ', eth %s: Host' % unicode(p.vlan)
			elif p.sock:
				txt += ', eth %s: %s' % (unicode(p.vlan), p.sock.nickname)
		return txt

	def get_type(self):
		return "Qemu"

	def on_config_changed(self):
		for hd in ['hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb', 'mtdblock']:
			disk = getattr(self.cfg,hd)
			if disk.image and self.cfg.get('base'+hd) != disk.image.name:
				disk.set_image(self.cfg.get('base'+hd))
			elif disk.image == None and len(self.cfg.get('base'+hd)) > 0:
				disk.set_image(self.cfg.get('base'+hd))

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
			if self.cfg.get("base" + dev) != "":
				master = False
				disk = getattr(self.cfg, dev)
				disk.set_image(self.cfg.get("base"+dev))
				if self.cfg.get("private" + dev) == "*":
					disk.cow = True
				else:
					disk.cow = False
				real_disk = disk.get_real_disk_name()

				if disk.cow == False and disk.readonly() == False:
					if disk.image.set_master(disk):
						print "Machine "+self.name+" acquired master lock on image "+disk.image.name
						master = True
					else:
						raise DiskLocked("Disk image %s already in use" % disk.base)
						print "ERROR SETTING MASTER!!"
						return

				if master:
					args = disk.args(True)
					res.append(args[0])
					res.append(args[1])
				else:
					args = disk.args(True)
					res.append(args[0])
					res.append(args[1])

		if self.cfg.kernelenbl == "*" and self.cfg.kernel!="":
			res.append("-kernel")
			res.append(self.cfg.kernel)

		if self.cfg.initrdenbl == "*" and self.cfg.initrd!="":
			res.append("-initrd")
			res.append(self.cfg.initrd)

		if self.cfg.kopt != "" and self.cfg.kernelenbl =="*" and self.cfg.kernel != "":
			res.append("-append")
			res.append(self.cfg.kopt)

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
		if (len(self.plugs) + len(self.socks) == 0):
			res.append('-net')
			res.append('none')
		else:
			for pl in self.plugs:
				res.append("-net")
				res.append("nic,model=%s,vlan=%d,macaddr=%s" % (pl.model, pl.vlan, pl.mac))
				if (pl.mode == 'vde'):
					res.append("-net")
					res.append("vde,vlan=%d,sock=%s" % (pl.vlan, pl.sock.path.rstrip('[]')))
				else:
					res.append("-net")
					res.append("user")
			for pl in self.socks:
				res.append("-net")
				res.append("nic,model=%s,vlan=%d,macaddr=%s" % (pl.model, pl.vlan, pl.mac))
				res.append("-net")
				res.append("vde,vlan=%d,sock=%s" % (pl.vlan, pl.path))

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
			res.append('unix:'+MYPATH+'/'+self.name+'_serial,server,nowait')

		res.append("-mon")
		res.append("chardev=mon")
		res.append("-chardev")
		res.append('socket,id=mon_cons,path=%s,server,nowait' % self.console2())

		res.append("-mon")
		res.append("chardev=mon_cons")
		res.append("-chardev")
		res.append('socket,id=mon,path=%s,server,nowait' % self.console())

		return res

	def __deepcopy__(self, memo):
		newname = self.factory.nextValidName("Copy_of_%s" % self.name)
		if newname is None:
			raise InvalidName("'%s' (was '%s')" % newname)
		new_brick = type(self)(self.factory, newname)
		new_brick.cfg = copy.deepcopy(self.cfg, memo)

		new_brick.newbrick_changes()

		return new_brick

	def newbrick_changes(self):

		basepath = self.basepath

		self.cfg.set_obj("hda", VMDisk(self, "hda", basepath))
		self.cfg.set_obj("hdb", VMDisk(self, "hdb", basepath))
		self.cfg.set_obj("hdc", VMDisk(self, "hdc", basepath))
		self.cfg.set_obj("hdd", VMDisk(self, "hdd", basepath))
		self.cfg.set_obj("fda", VMDisk(self, "fda", basepath))
		self.cfg.set_obj("fdb", VMDisk(self, "fdb", basepath))
		self.cfg.set_obj("mtdblock", VMDisk(self, "mtdblock", basepath))

	def console(self):
		return "%s/%s_cons.mgmt" % (MYPATH, self.name)

	def console2(self):
		return "%s/%s.mgmt" % (MYPATH, self.name)

	def add_sock(self, mac=None, model=None):
		sk = VMSock(self)
		self.socks.append(sk)
		if mac:
			sk.mac = mac
		if model:
			sk.model = model
		self.gui_changed = True
		return sk

	def add_plug(self, sock=None, mac=None, model=None):
		if sock and sock == '_hostonly':
			pl = VMPlugHostonly(self)
#			print "hostonly added"
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
		pl.mac = tools.RandMac()
		pl.model = 'rtl8139'
		pl.connect(endpoint)
		self.gui_changed = True

	def remove_plug(self, idx):
		for p in self.plugs:
			if p.vlan == idx:
				self.plugs.remove(p)
				del(p)
		for p in self.socks:
			if p.vlan == idx:
				self.socks.remove(p)
				del(p)
		for p in self.plugs:
			if p.vlan > idx:
				p.vlan -= 1
		for p in self.socks:
			if p.vlan > idx:
				p.vlan -= 1
		self.gui_changed = True

	def open_internal_console(self):

		if not self.has_console():
			self.factory.err(self, "No console detected.")
			return None

		try:
			time.sleep(0.5)
			c = socket.socket(socket.AF_UNIX)
			c.connect(self.console2())
			return c
		except Exception, err:
			self.factory.err(self, "Virtual Machine startup failed. Check your configuration!")
			return None

	def post_poweroff(self):
		self.active = False
		self.start_related_events(off=True)

class BrickFactory(ChildLogger, Thread, gobject.GObject):
	__gsignals__ = {
		'engine-closed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
		'brick-error'   : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str,)),
		'brick-started' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str,)),
		'brick-stopped' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str,)),
		'event-started' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
		'event-stopped' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
		'event-accomplished' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
	}

	def clear_project_parms(self):
		DEFAULT_PARMS = {
			"id": "0",
		}
		parms={}
		for key, value in DEFAULT_PARMS.items():
			parms[key]=value

		return parms


	def get_image_by_name(self, name):
		for img in self.disk_images:
			if img.name == name:
				return img
		return None

	def get_image_by_path(self,path):
		for img in self.disk_images:
			if img.path == path:
				return img
		return None

	def new_disk_image(self, name, path, description=""):
		img = DiskImage(name, path, description)
		self.disk_images.append(img)
		return img


	def __init__(self, logger=None, showconsole=True, nogui=False, server=False):
		gobject.GObject.__init__(self)
		ChildLogger.__init__(self, logger)
		# DEFINE PROJECT PARMS
		self.project_parms = self.clear_project_parms()
		self.remote_hosts = []
		self.bricks = []
		self.events = []
		self.socks = []
		self.disk_images = []
		self.bricksmodel = BricksModel()
		self.eventsmodel = EventsModel()
		self.showconsole = showconsole
		self.remotehosts_changed=False
		self.TCP = None
		Thread.__init__(self)
		self.running_condition = True
		self.settings = Settings(CONFIGFILE, self)

		if server:
			if os.getuid() != 0:
				print ("ERROR: -server requires to be run by root.")
				sys.exit(5)
			try:
				pwdfile = open("/etc/virtualbricks-passwd", "r")
			except:
				print "Password not set."
				while True:
					password = getpass.getpass("Insert password:")
					repeat = getpass.getpass("Confirm:")
					if password == repeat:
						try:
							pwdfile = open('/etc/virtualbricks-passwd', 'w+')
						except:
							print "Could not save password."
						else:
							pwdfile.write(password)
							pwdfile.close()
							print "Password saved."
						break
					else:
						print "Passwords don't match. Retry."
			else:
				password = pwdfile.readline()
				pwdfile.close()

			try:
				os.chmod('/etc/virtualbricks-passwd', 0600)
			except:
				os.unlink('/etc/virtualbricks-passwd')

			self.start_tcp_server(password)

		if not self.TCP:
			self.info("Current project is %s" % self.settings.get('current_project'))
			self.config_restore(self.settings.get('current_project'))
		else:
			self.config_restore('/tmp/TCP_controlled.vb')


	def start_tcp_server(self, password):
		self.TCP = TcpServer(self, password)
		try:
			self.TCP.start()
		except:
			print "Error starting TCP server."
			self.quit()

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

	def err(self, caller_obj, *args, **kargv):
		txt = ''
		for a in args:
			txt+=a
		self.emit("brick-error", txt)

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
			if self.remotehosts_changed:
				for rh in self.remote_hosts:
					if rh.connection and rh.connection.isAlive():
						rh.connection.join(0.001)
						if not rh.connection.isAlive():
							rh.connected = False
							rh.connection = None
		sys.exit(0)

	def config_dump(self, f):
		if self.TCP:
			return
		try:
			p = open(f, "w+")
		except:
			self.factory.err(self, "ERROR WRITING CONFIGURATION!\nProbably file doesn't exist or you can't write it.")
			return

		self.debug("CONFIG DUMP on " + f)

		# If project hasn't an ID we need to calculate it
		if self.project_parms['id'] == "0":
			projects = int(self.settings.get('projects'))
			self.settings.set("projects", projects+1)
			self.project_parms['id']=str(projects+1)
			self.debug("Project no= " + str(projects+1) + ", Projects: " + self.settings.get("projects"))
			self.settings.store()

		# DUMP PROJECT PARMS
		p.write('[Project:'+f+']\n')
		for key, value in self.project_parms.items():
			p.write( key + "=" + value+"\n")

		# Remote hosts
		for r in self.remote_hosts:
			p.write('[RemoteHost:'+r.addr[0]+']\n')
			p.write('port='+str(r.addr[1])+'\n')
			p.write('password='+r.password+'\n')
			if r.autoconnect:
				p.write('autoconnect=True\n')
			else:
				p.write('autoconnect=False\n')

		# Disk Images
		for img in self.disk_images:
			p.write('[DiskImage:'+img.name+']\n')
			p.write('path='+img.path +'\n')

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
							self.factory.err(self, "Error: unmanaged action type."+\
							"Will not be saved!" )
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
			for sk in b.socks:
				if b.get_type() == 'Qemu':
					p.write('sock|' + b.name + "|" + sk.nickname + '|' + sk.model + '|' + sk.mac + '|' + str(sk.vlan) + '\n')
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
				p = open(f, "w+")
				self.info("Current project file" + f + " doesn't exist. Creating a new file.")
				self.current_project = f
			else:
				raise BadConfig()
			#return

		self.info("Open " + f + " project")


		if start_from_scratch:
			self.bricksmodel.clear()
			self.eventsmodel.clear()
			for b in self.bricks:
				self.delbrick(b)
			del self.bricks[:]

			for e in self.events:
				self.delevent(e)
			del self.events[:]

			# RESET PROJECT PARMS TO DEFAULT
			self.project_parms = self.clear_project_parms()
			if create_if_not_found:
				# UPDATE PROJECT ID
				projects = int(self.settings.get('projects'))
				self.settings.set("projects", projects+1)
				self.project_parms['id']=str(projects+1)
				self.debug("Project no= " + str(projects+1) + ", Projects: " + self.settings.get("projects"))
				self.settings.store()
				return

		l = p.readline()
		b = None
		while (l):
			l = re.sub(' ', '', l)
			if re.search("\A.*sock\|", l) and len(l.split("|")) >= 3:
				l.rstrip('\n')
				self.debug( "************************* sock detected" )
				for bb in self.bricks:
					if bb.name == l.split("|")[1]:
						if (bb.get_type() == 'Qemu'):
							sockname = l.split('|')[2]
							model = l.split("|")[3]
							macaddr = l.split("|")[4]
							vlan = l.split("|")[5]
							pl = bb.add_sock(macaddr, model)

							pl.vlan = int(vlan)
							self.debug( "added eth%d" % pl.vlan )

			if re.search("\A.*link\|", l) and len(l.split("|")) >= 3:
				l.rstrip('\n')
				self.debug( "************************* link detected" )
				for bb in self.bricks:
					if bb.name == l.split("|")[1]:
						if (bb.get_type() == 'Qemu'):
							sockname = l.split('|')[2]
							model = l.split("|")[3]
							macaddr = l.split("|")[4]
							vlan = l.split("|")[5]
							this_sock = "?"
							if l.split("|")[0] == 'userlink':
								this_sock = '_hostonly'
							else:
								for s in self.socks:
									if s.nickname == sockname:
										this_sock = s
										break
							if this_sock == '?':
								self.warning( "socket '" + sockname + \
											"' not found while parsing following line: " +\
											l + "\n. Skipping." )
								continue
							pl = bb.add_plug(this_sock, macaddr, model)

							pl.vlan = int(vlan)
							self.debug( "added eth%d" % pl.vlan )
						else:
							bb.config_socks.append(l.split('|')[2].rstrip('\n'))

			if l.startswith('['):
				ntype = l.lstrip('[').split(':')[0]
				name = l.split(':')[1].rstrip(']\n')

				self.info("new %s : %s", ntype, name)
				try:
					if ntype == 'Event':
						self.newevent(ntype, name)
						component = self.geteventbyname(name)
					# READ PROJECT PARMS
					elif ntype == 'Project':
						self.debug( "Found Project " + name  + " Sections" )
						l = p.readline()
						while l and not l.startswith('['):
							values= l.rstrip("\n").split("=")
							if len(values)>1 and values[0] in self.project_parms:
								self.debug( "Add " + values[0] )
								self.project_parms[values[0]]=values[1]
							l = p.readline()
						continue
					elif ntype == 'DiskImage':
						self.debug("Found Disk image %s" % name)
						path = ""
						l = p.readline()
						while l and not l.startswith('['):
							k,v = l.rstrip("\n").split("=")
							if k == 'path':
								path = str(v)
							l = p.readline()
						self.new_disk_image(name,path)
						continue

					elif ntype == 'RemoteHost':
						self.debug("Found remote host %s" % name)
						newr=None
						for existing in self.remote_hosts:
							if existing.addr[0] == name:
								newr = existing
								break
						if not newr:
							newr = RemoteHost(self,name)
							self.remote_hosts.append(newr)
						l = p.readline()
						while l and not l.startswith('['):
							k,v = l.rstrip("\n").split("=")
							if k == 'password':
								newr.password = str(v)
							elif k == 'autoconnect' and v == 'True':
								newr.autoconnect = True
							l = p.readline()
						if newr.autoconnect:
							newr.connect()
						continue
					else: #elif ntype == 'Brick'
						self.newbrick(ntype, name)
						component = self.getbrickbyname(name)

				except Exception, err:
					import traceback,sys
					self.exception ( "--------- Bad config line:" + str(err))
					traceback.print_exc(file=sys.stdout)

					l = p.readline()
					continue

				l = p.readline()
				parameters = []
				while component and l and not l.startswith('[') and not re.search("\A.*link\|",l) and not re.search("\A.*sock\|", l):
					if len(l.split('=')) > 1:
						#Special management for event actions
						if l.split('=')[0] == "actions" and ntype == 'Event':
							actions=eval(''.join(l.rstrip('\n').split('=',1)[1:]))
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

		for b in self.bricks:
			for c in b.config_socks:
				self.connect_to(b,c)

		if self.project_parms['id']=="0":
			projects = int(self.settings.get('projects'))
			self.settings.set("projects", projects+1)
			self.project_parms['id']=str(projects+1)
			self.debug("Project no= " + str(projects+1) + ", Projects: " + self.settings.get("projects"))
			self.settings.store()

	def quit(self):
		for e in self.events:
			e.poweroff()
		for b in self.bricks:
			if b.proc is not None:
				b.poweroff()
		for h in self.remote_hosts:
			h.disconnect()
		if self.TCP:
			#XXX
			pass
		self.info(_('Engine: Bye!'))
		self.config_dump(self.settings.get('current_project'))
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

	def parse(self, command, console=sys.stdout):
		if (command == 'q' or command == 'quit'):
			self.quit()
		elif (command == 'h' or command == 'help'):
			CommandLineOutput(console,  'Base command -------------------------------------------------')
			CommandLineOutput(console,  'ps				List of active process')
			CommandLineOutput(console,  'n[ew]				Create a new brick')
			CommandLineOutput(console,  'list				List of bricks already created')
			CommandLineOutput(console,  'socks				List of connections available for bricks')
			CommandLineOutput(console,  'conn[ections]			List of connections for each bricks')
			CommandLineOutput(console,  '\nBrick configuration command ----------------------------------')
			CommandLineOutput(console,  'BRICK_NAME show			List parameters of BRICK_NAME brick')
			CommandLineOutput(console,  'BRICK_NAME on			Starts BRICK_NAME')
			CommandLineOutput(console,  'BRICK_NAME off			Stops BRICK_NAME')
			CommandLineOutput(console,  'BRICK_NAME remove		Delete BRICK_NAME')
			CommandLineOutput(console,  'BRICK_NAME config PARM=VALUE	Configure a parameter of BRICK_NAME.')
			CommandLineOutput(console,  'BRICK_NAME connect NICK		Connect BRICK_NAME to a Sock')
			CommandLineOutput(console,  'BRICK_NAME disconnect		Disconnect BRICK_NAME to a sock')
			CommandLineOutput(console,  'BRICK_NAME help			Help about parameters of BRICK_NAME')
			return True
		elif (command == 'ps'):
			self.proclist()
			return True
		elif command.startswith('reset all'):
			self.reset_config()
		elif command.startswith('n ') or command.startswith('new '):
			if(command.startswith('n event') or (command.startswith('new event'))):
				self.newevent(*command.split(" ")[1:])
			else:
				self.newbrick(*command.split(" ")[1:])
			return True
		elif command == 'list':
			CommandLineOutput(console,  "Bricks:")
			for obj in self.bricks:
				CommandLineOutput(console,  "%s %s" % (obj.get_type(), obj.name))
			CommandLineOutput(console,"" )
			CommandLineOutput(console,  "Events:")
			for obj in self.events:
				CommandLineOutput(console,  "%s %s" % (obj.get_type(), obj.name))
			CommandLineOutput(console,  "End of list.")
			CommandLineOutput(console, "" )
			return True

		elif command == 'socks':
			for s in self.socks:
				CommandLineOutput(console,  "%s" % s.nickname,)
				if s.brick is not None:
					CommandLineOutput(console,  " - port on %s %s - %d available" % (s.brick.get_type(), s.brick.name, s.get_free_ports()))
				else:
					CommandLineOutput(console,  "not configured.")
			return True

		elif command.startswith("conn") or command.startswith("connections"):
			for b in self.bricks:
				CommandLineOutput(console,  "Connections from " + b.name + " brick:\n")
				for sk in b.socks:
					if b.get_type() == 'Qemu':
						CommandLineOutput(console,  '\tsock connected to ' + sk.nickname + ' with an ' + sk.model + ' (' + sk.mac + ') card\n')
				for pl in b.plugs:
					if b.get_type() == 'Qemu':
						if pl.mode == 'vde':
							CommandLineOutput(console,  '\tlink connected to ' + pl.sock.nickname + ' with a ' + pl.model + ' (' + pl.mac + ') card\n')
						else:
							CommandLineOutput(console,  '\tuserlink connected with a ' + pl.model + ' (' + pl.mac + ') card\n')
					elif (pl.sock is not None):
						CommandLineOutput(console,  '\tlink: ' + pl.sock.nickname + '\n')
			return True

		elif command.startswith("control ") and len(command.split(" "))==3:
			host=command.split(" ")[1]
			password = command.split(" ")[2]
			remote = None
			for h in self.remote_hosts:
				if h.addr == host:
					remote = h
					break
			if not remote:
				remote = RemoteHost(self, host)
			remote.password = password
			self.factory.remotehosts_changed=True

			if remote.connect():
				CommandLineOutput(console, "Connection OK\n")
			else:
				CommandLineOutput(console, "Connection Failed.\n")
			return True

		elif command.startswith("udp ") and self.TCP:
			args = command.split(" ")
			if len(args) != 4 or args[0] != 'udp':
				CommandLineOutput(console,  "FAIL udp arguments \n")
				return False
			for b in self.bricks:
				if b.name == args[2]:
					w = PyWire(self, args[1])
					w.set_remoteport(args[3])
					w.connect(b.socks[0])
					w.poweron()
					return True
				CommandLineOutput(console,  "FAIL Brick not found: " + args[2] + "\n")
		elif command == '':
			return True

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
				return True
			else:
				print 'Invalid console command "%s"' % command
				return False

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
				raise UnmanagedType()
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

		if bricktodel.proc is not None:
			bricktodel.poweroff()

		for b in self.bricks:
			if b == bricktodel:
				for so in b.socks:
					self.socks.remove(so)
				self.bricks.remove(b)
			else: # connections to bricktodel must be deleted too
				for pl in reversed(b.plugs):
					if pl.sock:
						if pl.sock.nickname.startswith(bricktodel.name):
							self.debug( "Deleting plug to " + pl.sock.nickname )
							b.plugs.remove(pl)
							b.clear_self_socks(pl.sock.path)
							b.restore_self_plugs() # recreate Plug(self) of some objects

		self.bricksmodel.del_brick(bricktodel)

	def delremote(self, address):

		# Deferred removal: fill the list first, then call delbrick(b)
		# in sequence.

		mybricks = []
		for r in self.remote_hosts:
			if r.addr[0] == address:
				for br in self.bricks:
					if br.homehost and br.homehost.addr[0] == address:
						mybricks.append(br)
				for br in mybricks:
					self.delbrick(br)
				self.remote_hosts.remove(r)
		self.remotehosts_changed=True

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
			self.debug( "Name error duplicating event." )
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
			raise InvalidName()

		self.isNameFree(newname)

		b.name = newname
		if b.get_type() == "Switch":
			for so in b.socks:
				so.nickname = b.name + "_port"
		elif b.get_type() == "Qemu":
			b.newbrick_changes()

		b.gui_changed = True

	def renameevent(self, e, newname):
		newname = ValidName(newname)
		if newname == None:
			raise InvalidName()

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

	def newbrick(self, arg1="", arg2="",arg3="",arg4="", arg5=""):
		host=""
		remote=False
		if arg1 == "remote":
			print "remote brick"
			remote=True
			ntype=arg2
			name=arg3
			host=arg4
		else:
			ntype=arg1
			name=arg2

		name = ValidName(name)
		if not name:
			raise InvalidName()

		if not self.isNameFree(name):
			raise InvalidName()

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
			if VDESUPPORT and self.settings.python:
				brick = PyWire(self, name)
				self.debug("new cable %s OK - Type: Python-VdePlug.", brick.name)
			else:
				brick = Wire(self, name)
				self.debug("new cable %s OK - Type: Traditional.", brick.name)
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
			self.err(self,"Invalid console command '%s'", name)
			return False
		if remote:
			brick.set_host(host)
			if brick.homehost.connected:
				brick.homehost.send("new "+brick.get_type()+" "+brick.name)

		return True

	def reset_config(self):
		for b in self.bricks:
			b.poweroff()
			self.delbrick(b)
		for e in self.events:
			self.delevents(e)
		self.bricks=[]
		self.events=[]

	def newevent(self, ntype="", name=""):
		name = ValidName(name)
		if not name:
			raise InvalidName()

		if not self.isNameFree(name):
			raise InvalidName()

		if ntype == "event" or ntype == "Event":
			brick = Event(self, name)
			self.debug("new event %s OK", brick.name)
		else:
			self.err(self, "Invalid event command '%s'", name)
			return False

		return True

gobject.type_register(BrickFactory)

if __name__ == "__main__":
	"""
	run tests with 'python BrickFactory.py -v'
	"""
	import doctest
	doctest.testmod()
