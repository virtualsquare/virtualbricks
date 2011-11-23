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
from threading import Thread, Semaphore
import time, socket
from virtualbricks import tools
from virtualbricks.gui.graphics import Icon, Node, Topology
from virtualbricks.logger import ChildLogger
from virtualbricks.models import BricksModel, EventsModel
from virtualbricks.settings import CONFIGFILE, MYPATH, Settings
from virtualbricks.errors import (BadConfig,
	InvalidName, Linkloop, NotConnected, UnmanagedType)
from virtualbricks.tcpserver import TcpServer
import getpass
from virtualbricks.bricks import Brick
from virtualbricks.events import Event
from virtualbricks.switches import Switch, SwitchWrapper
from virtualbricks.virtualmachines import VM, DiskImage, DiskLocked
from virtualbricks.tunnels import TunnelListen, TunnelConnect
from virtualbricks.tuntaps import Capture, Tap
from virtualbricks.wires import Wire, Wirefilter, PyWire, VDESUPPORT
from virtualbricks.console import (Parse, ShellCommand, RemoteHostConnectionInstance,
	RemoteHost, CommandLineOutput, VbShellCommand)





class BrickFactory(ChildLogger, Thread, gobject.GObject):
	__gsignals__ = {
		'engine-closed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
		'brick-error'   : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str,)),
		'brick-started' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str,)),
		'brick-stopped' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str,)),
		'brick-changed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str, bool,)),
		'event-started' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str,)),
		'event-stopped' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str,)),
		'event-changed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str, bool,)),
		'event-accomplished' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str,)),
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

	def new_disk_image(self, name, path, description="", host=None):
		img = DiskImage(name, path, description, host)
		self.disk_images.append(img)
		return img

	def clear_machine_vmdisks(self, machine):
		for img in self.disk_images:
			for vmd in img.vmdisks:
				if vmd.VM == machine:
					img.del_vmdisk(vmd)
					self.debug("Vmdisk lock released")


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
		self.startup = True
		self.showconsole = showconsole
		self.remotehosts_changed=False
		self.TCP = None
		Thread.__init__(self)
		self.running_condition = True
		self.settings = Settings(CONFIGFILE, self)
		self.projectsave_sema = Semaphore()
		self.autosave_timer = tools.AutoSaveTimer(self)
		self.autosave_timer.start()

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

		self.startup = False


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
					Parse(self, command.rstrip('\n'))
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

		self.projectsave_sema.acquire()
		try:
			p = open(f, "w+")
		except:
			self.factory.err(self, "ERROR WRITING CONFIGURATION!\nProbably file doesn't exist or you can't write it.")
			self.projectsave_sema.release()
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
			p.write('basepath='+r.basepath+'\n')
			if r.autoconnect:
				p.write('autoconnect=True\n')
			else:
				p.write('autoconnect=False\n')

		# Disk Images
		for img in self.disk_images:
			p.write('[DiskImage:'+img.name+']\n')
			p.write('path='+img.path +'\n')
			if img.host is not None:
				p.write('host='+img.host.addr[0]+'\n')

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
		self.projectsave_sema.release()




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

			self.socks = []

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
						host=None
						l = p.readline()
						while l and not l.startswith('['):
							k,v = l.rstrip("\n").split("=")
							if k == 'path':
								path = str(v)
							elif k == 'host':
								host = self.get_host_by_name(str(v))
							l = p.readline()
						img = self.new_disk_image(name,path, host=host)
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
							elif k == 'basepath':
								newr.basepath = str(v)
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
		self.autosave_timer.join()
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

	def get_host_by_name(self, host):
		for h in self.remote_hosts:
			if h.addr[0] == host:
				return h
		return None



	def images_manager(self, console, *cmd):
		if isinstance(cmd, basestring) is False:
			command = cmd[0]
		else:
			command = cmd
			cmd = []
		host = None
		remote = False
		if command == "list":
			if len(cmd)>1:
				host=self.get_host_by_name(cmd[1])
			for img in self.disk_images:
				if (len(cmd)==1 and img.host is None):
					CommandLineOutput(console, "%s,%s" % (img.name, img.path))
				if (host is not None and img.host is not None and img.host.addr[0] == host.addr[0]):
					CommandLineOutput(console, "%s,%s" % (img.name, img.path))
				else:
					continue
		elif command == "files":
			if len(cmd)>1:
				host=self.get_host_by_name(cmd[1])
				if host is not None and host.connected is True:
					files = host.get_files_list()
					for f in files:
						print f
				else:
					CommandLineOutput(console, "Not connected to %s" % cmd[1])
				return
			for image_file in os.listdir(self.settings.get("baseimages")):
				if os.path.isfile(self.settings.get("baseimages")+"/"+image_file):
					CommandLineOutput(console, "%s" % (image_file))
		elif command == "add":
			if len(cmd) > 1 and cmd[2] is not None and cmd[1] is not None:
				basepath = self.settings.get("baseimages")
				host = None
				if len(cmd) == 3:
					host = self.get_host_by_name(cmd[2])
					if host is not None:
						basepath = host.basepath
				img = self.new_disk_image(cmd[1], basepath+ "/" + cmd[1])
				if host is not None:
					img.host = host
					if host.connected is True:
						host.send("i add " + cmd[1])
						host.expect_OK()
		elif command == "del":
			if len(cmd) > 1:
				image = self.get_image_by_name(cmd[1])
				if image is not None:
					if len(cmd) == 3:
						host = self.get_host_by_name(cmd[2])
						if host.connected is False:
							host = None
						if host is None:
							return
						if host is not None and image.host != host:
							return
						self.disk_images.remove(image)
						if host.connected is True:
							host.send("i del " + cmd[1])
							host.expect_OK()
					if image.host is not None:
						return
					self.disk_images.remove(image)
		elif command == "base":
			if len(cmd) == 1 or (len(cmd) > 1 and cmd[1] == "show"):
				CommandLineOutput(console, "%s" % (self.settings.get("baseimages")))
			elif cmd[1] == "set" and len(cmd)>2:
				self.settings.set("baseimages", cmd[2])
		return

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
		newname = tools.ValidName(newname)
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
		newname = tools.ValidName(newname)
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
		newname = tools.ValidName(name)
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

		name = tools.ValidName(name)
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
		elif ntype == "capture" or ntype == "Capture":
			brick = Capture(self, name)
			self.debug("new capture %s OK", brick.name)
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
		elif ntype == "capture" or ntype == "Capture Interface":
			brick = Capture(self, name)
			self.debug("new capture %s OK", brick.name)
		elif ntype == "switchwrapper" or ntype == "SwitchWrapper":
			brick = SwitchWrapper(self, name)
			self.debug("new SwitchWrapper %s OK", brick.name)
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
		name = tools.ValidName(name)
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
