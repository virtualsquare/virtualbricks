#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
Copyright (C) 2011 Virtualbricks team

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; version 2.

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
import subprocess
import sys
import time
import socket
from virtualbricks.logger import ChildLogger
from virtualbricks.settings import CONFIGFILE, MYPATH, Settings
from virtualbricks.gui.graphics import Icon, Topology
from virtualbricks.brickconfig import BrickConfig
from virtualbricks.link import Sock, Plug
from virtualbricks.errors import (BadConfig,
	InvalidName, Linkloop, NotConnected)
from virtualbricks.console import RemoteHost

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

	# each brick must overwrite this method
	def get_type(self):
		pass

	# each brick must overwrite this method
	def prog(self):
		pass

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
		self.factory.emit("brick-changed", self.name, self.factory.startup)

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
			k=attr.split("=")[0]
			self.cfg.set(attr)
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

	def escape(self, arg):
		arg = re.sub('"','\\"',arg)
		#arg = '"' + arg + '"'
		return arg

	def _poweron(self):
		if self.proc != None:
			return
		command_line = self.args()
		if self.needsudo():
			sudoarg = ""
			if self.get_type() == 'Qemu':
				command_line = []
				command_line.append(self.settings.get("sudo"))
				for cmdarg in self.args():
					command_line.append(self.escape(cmdarg))
				command_line.append('-pidfile')
				command_line.append(self.pidfile)

			else:
				for cmdarg in command_line:
					sudoarg += cmdarg + " "
				sudoarg += "-P %s" % self.pidfile
				command_line[0] = self.settings.get("sudo")
				command_line[1] = self.escape(sudoarg)
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
				# out and err files (if configured) for saving VM output
				out = subprocess.PIPE
				err = subprocess.PIPE
				if self.get_type() == 'Qemu':
					if self.cfg.stdout != "":
						out = open(self.cfg.stdout,"wb")
					if self.cfg.stderr != "":
						err = open(self.cfg.stderr,"wb")
				self.proc = subprocess.Popen(command_line, stdin=subprocess.PIPE, stdout=out, stderr=err)
			except OSError:
				self.factory.err(self,"OSError: Brick startup failed. Check your configuration!")

			if self.proc:
				self.pid = self.proc.pid
			else:
				self.factory.err(self, "Brick startup failed. Check your configuration!\nMessage:\n"+"\n".join(self.proc.stdout.readlines()))

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


'''import (virtualbricks.switches, virtualbricks.tunnels, virtualbricks.tuntaps,
	virtualbricks.virtualmachines, virtualbricks.wires, )'''

from virtualbricks.switches import Switch, SwitchWrapper
from virtualbricks.tunnels import TunnelConnect, TunnelListen
from virtualbricks.tuntaps import Capture, Tap
from virtualbricks.virtualmachines import VMDisk, VMPlug, VMSock, DiskImage, VM, VMPlugHostonly
from virtualbricks.wires import Wirefilter, Wire, PyWire, PyWireThread
