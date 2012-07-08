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

import re, os, shutil
from virtualbricks import tools
from virtualbricks.console import (ShellCommand, RemoteHost,  VbShellCommand)
from virtualbricks.errors import BadConfig
from virtualbricks.project import VBProject

class ConfigFile():
	def __init__(self, factory):
		self.factory = factory

	def save(self, f):
		if self.factory.TCP:
			return

		self.factory.projectsave_sema.acquire()

		backup_project_file = self.factory.settings.get("bricksdirectory")+"/.vb_current_project.vbl"
		if os.path.isfile(f):
			'''create a new backup file of the project'''
			shutil.copyfile(f, backup_project_file)

		try:
			p = open(f, "w+")
		except:
			self.factory.err(self.factory, "ERROR WRITING CONFIGURATION!\nProbably file doesn't exist or you can't write it.")
			self.factory.projectsave_sema.release()
			return
		self.factory.debug("CONFIG DUMP on " + f)

		# If project hasn't an ID we need to calculate it
		if self.factory.project_parms['id'] == "0":
			projects = int(self.factory.settings.get('projects'))
			self.factory.settings.set("projects", projects+1)
			self.factory.project_parms['id']=str(projects+1)
			self.factory.debug("Project no= " + str(projects+1) + ", Projects: " + self.factory.settings.get("projects"))
			self.factory.settings.store()
		if self.factory.project_parms['name'] == "":
			path_array=f.split("/")
			path_array = path_array[len(path_array)-1].split(".")
			if path_array[len(path_array)-1] == "vbl":
				index = path_array[len(path_array)-2]
			else:
				path_array[len(path_array)-1]
			self.factory.project_parms['name'] = index

		self.factory.project_parms['filename'] = f

		# DUMP PROJECT PARMS
		p.write('[Project:'+f+']\n')
		for key, value in self.factory.project_parms.items():
			p.write( key + "=" + value+"\n")

		# Remote hosts
		for r in self.factory.remote_hosts:
			p.write('[RemoteHost:'+r.addr[0]+']\n')
			p.write('port='+str(r.addr[1])+'\n')
			p.write('password='+r.password+'\n')
			p.write('basepath='+r.basepath+'\n')
			if r.autoconnect:
				p.write('autoconnect=True\n')
			else:
				p.write('autoconnect=False\n')

		# Disk Images
		for img in self.factory.disk_images:
			p.write('[DiskImage:'+img.name+']\n')
			p.write('path='+img.path +'\n')
			if img.host is not None:
				p.write('host='+img.host.addr[0]+'\n')
			if img.readonly is not False:
				p.write('readonly=True\n')

		for e in self.factory.events:
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
							self.factory.factory.err(self.factory, "Error: unmanaged action type."+\
							"Will not be saved!" )
							continue
					p.write(k + '=' + str(tempactions) + '\n')
				#Standard management for other parameters
				else:
					p.write(k + '=' + str(v) + '\n')

		for b in self.factory.bricks:
			p.write('[' + b.get_type() + ':' + b.name + ']\n')
			for k, v in b.cfg.iteritems():
				# VMDisk objects don't need to be saved
				if b.get_type() != "Qemu" or (b.get_type() == "Qemu" and k not in ['hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb', 'mtdblock']):
					p.write(k + '=' + str(v) + '\n')

		for b in self.factory.bricks:
			for sk in b.socks:
				if b.get_type() == 'Qemu':
					p.write('sock|' + b.name + "|" + sk.nickname + '|' + sk.model + '|' + sk.mac + '|' + str(sk.vlan) + '\n')
		for b in self.factory.bricks:
			for pl in b.plugs:
				if b.get_type() == 'Qemu':
					if pl.mode == 'vde':
						p.write('link|' + b.name + "|" + pl.sock.nickname + '|' + pl.model + '|' + pl.mac + '|' + str(pl.vlan) + '\n')
					else:
						p.write('userlink|' + b.name + '||' + pl.model + '|' + pl.mac + '|' + str(pl.vlan) + '\n')
				elif (pl.sock is not None):
					p.write('link|' + b.name + "|" + pl.sock.nickname + '\n')

		# remove the project backup file
		if os.path.isfile(backup_project_file):
			os.remove (backup_project_file)

		self.factory.projectsave_sema.release()




	def restore(self, f, create_if_not_found=True, start_from_scratch=False):
		"""
		ACTIONS flags for this:
		Initial restore of latest open: True,False (default)
		Open or Open Recent: False, True
		Import: False, False
		New: True, True (missing check for existing file, must be check from caller)
		"""
		backup_project_file = self.factory.settings.get("bricksdirectory")+"/.vb_current_project.vbl"
		'''check if there's a project backup to restore and if its size is different from current project file'''
		if os.path.isfile(backup_project_file):
			self.factory.info("I found a backup project file, I'm going to restore it!")
			if os.path.isfile(f):
				self.factory.info("Corrupted file moved to " + f + ".back")
				shutil.copyfile(f, f+".back")
			''' restore backup file'''
			shutil.copyfile(backup_project_file, f)
			os.remove(backup_project_file)
			self.factory.info("Backup project file restored.")
			self.factory.backup_restore=True
			self.factory.emit("backup-restored", "A backup project has been restored.\nIf you want more informations please read View->Messages.")
		try:
			p = open(f, "r")
		except:
			if create_if_not_found:
				p = open(f, "w+")
				self.factory.info("Current project file" + f + " doesn't exist. Creating a new file.")
				self.factory.current_project = f
			else:
				raise BadConfig()
			#return

		self.factory.info("Open " + f + " project")


		if start_from_scratch:
			self.factory.bricksmodel.clear()
			self.factory.eventsmodel.clear()
			for b in self.factory.bricks:
				self.factory.delbrick(b)
			del self.factory.bricks[:]

			for e in self.factory.events:
				self.factory.delevent(e)
			del self.factory.events[:]

			self.factory.socks = []

			# RESET PROJECT PARMS TO DEFAULT
			self.factory.project_parms = self.factory.clear_project_parms()
			if create_if_not_found:
				# UPDATE PROJECT ID
				projects = int(self.factory.settings.get('projects'))
				self.factory.settings.set("projects", projects+1)
				self.factory.project_parms['id']=str(projects+1)
				path_array=f.split("/")
				path_array = path_array[len(path_array)-1].split(".")
				if path_array[len(path_array)-1] == "vbl":
					index = path_array[len(path_array)-2]
				else:
					path_array[len(path_array)-1]
				self.factory.project_parms['name'] = index
				self.factory.debug("Project no= " + self.factory.project_parms['id'] + ", name: " + self.factory.project_parms['name']  + ", projects: " + self.factory.settings.get("projects"))
				self.factory.settings.store()
				return

		l = p.readline()
		b = None
		while (l):
			l = re.sub(' ', '', l)
			if re.search("\A.*sock\|", l) and len(l.split("|")) >= 3:
				l.rstrip('\n')
				self.factory.debug( "************************* sock detected" )
				for bb in self.factory.bricks:
					if bb.name == l.split("|")[1]:
						if (bb.get_type() == 'Qemu'):
							sockname = l.split('|')[2]
							model = l.split("|")[3]
							macaddr = l.split("|")[4]
							vlan = l.split("|")[5]
							pl = bb.add_sock(macaddr, model)

							pl.vlan = int(vlan)
							self.factory.debug( "added eth%d" % pl.vlan )

			if re.search("\A.*link\|", l) and len(l.split("|")) >= 3:
				l.rstrip('\n')
				self.factory.debug( "************************* link detected" )
				for bb in self.factory.bricks:
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
								for s in self.factory.socks:
									if s.nickname == sockname:
										this_sock = s
										break
							if this_sock == '?':
								self.factory.warning( "socket '" + sockname + \
											"' not found while parsing following line: " +\
											l + "\n. Skipping." )
								continue
							pl = bb.add_plug(this_sock, macaddr, model)

							pl.vlan = int(vlan)
							self.factory.debug( "added eth%d" % pl.vlan )
						else:
							bb.config_socks.append(l.split('|')[2].rstrip('\n'))

			if l.startswith('['):
				ntype = l.lstrip('[').split(':')[0]
				name = l.split(':')[1].rstrip(']\n')

				self.factory.info("new %s : %s", ntype, name)
				try:
					if ntype == 'Event':
						self.factory.newevent(ntype, name)
						component = self.factory.geteventbyname(name)
					# READ PROJECT PARMS
					elif ntype == 'Project':
						self.factory.debug( "Found Project " + name  + " Sections" )
						l = p.readline()
						while l and not l.startswith('['):
							values= l.rstrip("\n").split("=")
							if len(values)>1 and values[0] in self.factory.project_parms:
								self.factory.debug( "Add " + values[0] )
								self.factory.project_parms[values[0]]=values[1]
							l = p.readline()
						continue
					elif ntype == 'DiskImage':
						self.factory.debug("Found Disk image %s" % name)
						path = ""
						host=None
						readonly=False
						l = p.readline()
						while l and not l.startswith('['):
							k,v = l.rstrip("\n").split("=")
							if k == 'path':
								path = str(v)
							elif k == 'host':
								host = self.factory.get_host_by_name(str(v))
							elif k == 'readonly' and v == 'True':
								readonly=True
							l = p.readline()
						if not tools.NameNotInUse(self.factory, name):
							continue
						if host is None and not os.access(path,os.R_OK):
							continue
						img = self.factory.new_disk_image(name,path, host=host)
						img.set_readonly(readonly)
						continue

					elif ntype == 'RemoteHost':
						self.factory.debug("Found remote host %s" % name)
						newr=None
						for existing in self.factory.remote_hosts:
							if existing.addr[0] == name:
								newr = existing
								break
						if not newr:
							newr = RemoteHost(self.factory,name)
							self.factory.remote_hosts.append(newr)
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
						self.factory.newbrick(ntype, name)
						component = self.factory.getbrickbyname(name)

				except Exception, err:
					import traceback,sys
					self.factory.exception ( "--------- Bad config line:" + str(err))
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

		for b in self.factory.bricks:
			for c in b.config_socks:
				self.factory.connect_to(b,c)

		if self.factory.project_parms['id']=="0":
			projects = int(self.factory.settings.get('projects'))
			self.factory.settings.set("projects", projects+1)
			self.factory.project_parms['id']=str(projects+1)
			self.factory.debug("Project no= " + str(projects+1) + ", Projects: " + self.factory.settings.get("projects"))

		if self.factory.project_parms['name'] == "":
			path_array=f.split("/")
			path_array = path_array[len(path_array)-1].split(".")
			if path_array[len(path_array)-1] == "vbl":
				index = path_array[len(path_array)-2]
			else:
				index =	path_array[len(path_array)-1]
			self.factory.project_parms['name'] = index
			self.factory.debug("Project no= " + self.factory.project_parms['id'] + ", name:" + self.factory.project_parms['name']  + ", projects: " + self.factory.settings.get("projects"))
			self.factory.settings.store()

		self.factory.project_parms['filename'] = f
		self.factory.settings.store()

