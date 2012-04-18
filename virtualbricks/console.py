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
from threading import Thread, Lock
import select, sys, os, re, socket, hashlib, time

class VbShellCommand(str):
	def __init__(self, mystr):
		self=mystr
	pass

class ShellCommand(str):
	def __init__(self, mystr):
		self=mystr
	pass

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
		self.basepath=os.path.expanduser("~")+"/VM"
		self.lock = Lock()

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
		self.sock.sendall(hashed)
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
		buff=""
		rec=""
                while (p.poll(100)):
			buff = self.sock.recv(1)
			rec=rec+buff
			if rec.endswith("OK\n"):
				return True
			elif rec.endswith("\nFAIL\n"):
				return "FAIL\n"
		return False

	def upload(self,b):
		self.lock.acquire()
		self.send_nolock("new "+b.get_type()+" "+b.name)
		self.putconfig(b)
		self.expect_OK()
		self.factory.remotehosts_changed=True
		self.lock.release()

	def putconfig(self,b):
		for (k, v) in b.cfg.iteritems():
			if k != 'homehost':
				# ONLY SEND TO SERVER STRING PARAMETERS, OBJECT WON'T BE SENT TO SERVER AS A STRING!
				if isinstance(v, basestring) is True:
					self.send_nolock(b.name + ' config ' + "%s=%s" % (k, v))
					# I CAN'T WAIT AN OK FOR EACH CONFIG COMMAND
					#self.expect_OK()
					time.sleep(0.1)
		for pl in b.plugs:
			if b.get_type() == 'Qemu':
				if pl.mode == 'vde':
					self.send_nolock(b.name + " connect " + pl.sock.nickname)
				else:
					print "Qemu but not VDE plug"
			elif (pl.sock is not None):
				print "Not a Qemu Plug"

		self.factory.remotehosts_changed=True

	def post_connect_init(self):
		self.send('reset all')

		basepath = self.send_and_recv("i base show")
		if basepath and len(basepath) == 1:
			self.basepath = basepath[0]

		for img in self.factory.disk_images:
			if img.host is not None and img.host.addr[0] == self.addr[0]:
				name = img.path.split("/")
				name = name[len(name)-1]
				self.send("i add " + img.name + " " + self.basepath + "/" + name)
				self.expect_OK()

		for b in self.factory.bricks:
			if b.homehost and b.homehost.addr == self.addr:
					self.upload(b)

	def get_files_list(self):
		return self.send_and_recv("i files")

	def send_and_recv(self, cmd):
		#print "send_and_recv starting: %s" % cmd
		p = select.poll()
                p.register(self.sock, select.POLLIN)
		# clear the socket input
		while (p.poll(10)):
			self.sock.recv(4)
		self.send(cmd)
		buff=""
		rec=""
                while (p.poll(10)):
			buff = self.sock.recv(1)
			rec=rec+buff
			if rec.endswith("\nOK\n"):
				rec = rec.split("\n")
				rec = rec[:len(rec)-2]
				#print "send_and_recv finished"
				return rec
			elif rec.endswith("FAIL\n"):
				return []

	def send(self, cmd):
		self.lock.acquire()
		ret = False
		if self.connected:
			self.sock.sendall(cmd + '\n')
		self.lock.release()
		return ret

	def send_nolock(self, cmd):
		ret = False
		if self.connected:
			self.sock.sendall(cmd + "\n")
		return ret

	def recv(self, size):
		if not self.connected:
			return ""
		ret = ""
		ret = self.sock.recv(size)
		return ret

def CommandLineOutput(outf, data):
	if outf == sys.stdout:
		return outf.write(data + '\n')
	else:
		return outf.send(data + '\n')

def Parse(factory, command, console=sys.stdout):
	if (command == 'q' or command == 'quit'):
		factory.quit()
	elif (command == 'h' or command == 'help'):
		CommandLineOutput(console,  'Base command -------------------------------------------------')
		CommandLineOutput(console,  'ps				List of active process')
		CommandLineOutput(console,  'n[ew] TYPE NAME			Create a new TYPE brick with NAME')
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
		factory.proclist(console)
		return True
	elif command.startswith('reset all'):
		factory.reset_config()
		return True
	elif command.startswith('n ') or command.startswith('new '):
		if(command.startswith('n event') or (command.startswith('new event'))):
			factory.newevent(*command.split(" ")[1:])
		else:
			factory.newbrick(*command.split(" ")[1:])
		return True
	elif command == 'list':
		CommandLineOutput(console,  "Bricks:")
		for obj in factory.bricks:
			CommandLineOutput(console,  "%s %s" % (obj.get_type(), obj.name))
		CommandLineOutput(console,"" )
		CommandLineOutput(console,  "Events:")
		for obj in factory.events:
			CommandLineOutput(console,  "%s %s" % (obj.get_type(), obj.name))
		CommandLineOutput(console,  "End of list.")
		CommandLineOutput(console, "" )
		return True
	elif command.startswith('images') or command.startswith("i"):
		factory.images_manager(console, *command.split(" ")[1:])
		return True
	elif command == 'socks':
		for s in factory.socks:
			CommandLineOutput(console,  "%s" % s.nickname,)
			if s.brick is not None:
				CommandLineOutput(console,  " - port on %s %s - %d available" % (s.brick.get_type(), s.brick.name, s.get_free_ports()))
			else:
				CommandLineOutput(console,  "not configured.")
		return True

	elif command.startswith("conn") or command.startswith("connections"):
		for b in factory.bricks:
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
		for h in factory.remote_hosts:
			if h.addr == host:
				remote = h
				break
		if not remote:
			remote = RemoteHost(factory, host)
		remote.password = password
		factory.factory.remotehosts_changed=True

		if remote.connect():
			CommandLineOutput(console, "Connection OK\n")
		else:
			CommandLineOutput(console, "Connection Failed.\n")
		return True

	elif command.startswith("udp ") and factory.TCP:
		args = command.split(" ")
		if len(args) != 4 or args[0] != 'udp':
			CommandLineOutput(console,  "FAIL udp arguments \n")
			return False
		for b in factory.bricks:
			if b.name == args[2]:
				w = PyWire(factory, args[1])
				w.set_remoteport(args[3])
				w.connect(b.socks[0])
				w.poweron()
				return True
			CommandLineOutput(console,  "FAIL Brick not found: " + args[2] + "\n")
	elif command == '':
		return True
	else:
		found = None
		for obj in factory.bricks:
			if obj.name == command.split(" ")[0]:
				found = obj
				break
		if found is None:
			for obj in factory.events:
				if obj.name == command.split(" ")[0]:
					found = obj
					break

		if found is not None and len(command.split(" ")) > 1:
			factory.brickAction(found, command.split(" ")[1:])
			return True
		else:
			print 'Invalid console command "%s"' % command
			return False
