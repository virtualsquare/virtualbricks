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
import os
import re
import socket
import time
import subprocess
from datetime import datetime
from shutil import move
from virtualbricks.bricks import Brick
from virtualbricks.brickconfig import BrickConfig
from virtualbricks.link import Sock, Plug
from virtualbricks.errors import DiskLocked, InvalidName, BadConfig
from virtualbricks.settings import CONFIGFILE, MYPATH, Settings
from virtualbricks import tools

class VMPlug(Plug, BrickConfig):
	def __init__(self, brick):
		Plug.__init__(self, brick)
		self.mac = tools.RandMac()
		self.model = 'rtl8139'
		self.vlan = len(self.brick.plugs) + len(self.brick.socks)
		self.mode = 'vde'

	def get_model_driver(self):
		if self.model == 'virtio':
			return "virtio-net-pci"
		return self.model

	def hotadd(self):
		driver = self.get_model_driver()
		self.brick.send("device_add %s,mac=%s,vlan=%s,id=eth%s\n" % (str(driver), str(self.mac), str(self.vlan), str(self.vlan)))
		self.brick.send("host_net_add vde sock=%s,vlan=%s\n" % (self.sock.path.rstrip('[]'), str(self.vlan)))

	def hotdel(self):
		self.brick.send("host_net_remove %s vde.%s\n" % (str(self.vlan), str(self.vlan)))
		self.brick.send("device_del eth%s\n" % str(self.vlan))



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

	def get_model_driver(self):
		if self.model == 'virtio':
			return "virtio-net-pci"
		return self.model


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

	def __init__(self, name, path, description="", host=None):
		self.name = name
		self.path = path
		if description!="":
			self.set_description(description)
		self.vmdisks = []
		self.master = None
		self.host = host
		self.readonly=False

	def set_readonly(self, value):
		self.readonly=value

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

	def get_size(self):
		if not os.path.exists(self.path):
			return 
		size = os.path.getsize(self.path)
		if (size > 1000000):
			return (str(size/1000000))
		else:
			return (str(size / 1000000.0))


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
				self.VM.factory.debug("Machine "+self.VM.name+" acquired master lock on image " + self.image.name)
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
				self.VM.factory.debug("Machine "+self.VM.name+" acquired master lock on image " + self.image.name)
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
			cowname = self.basefolder + "/" + self.VM.name + "_" + self.device + ".cow"
			if os.access(cowname, os.R_OK):
				f = open(cowname)
				buff = f.read(1)
				while buff != '/':
					buff=f.read(1)
				base = ""
				while buff != '\x00':
					base += buff
					buff = f.read(1)
				f.close()
				if base != self.get_base():
					dt = datetime.now()
					cowback = cowname + ".back-" + dt.strftime("%Y-%m-%d_%H-%M-%S")
					self.VM.factory.debug("%s private cow found with a different base image (%s): moving it in %s" % (cowname, base, cowback))
					move(cowname, cowback)
			if not os.access(cowname, os.R_OK):
				qmissing,qfound = self.VM.settings.check_missing_qemupath(self.VM.settings.get("qemupath"))
				if "qemu-img" in qmissing:
					raise BadConfig(_("qemu-img not found! I can't create a new image."))
				else:
					self.VM.factory.debug("Creating a new private COW from %s base image." % self.get_base())
					command=[self.VM.settings.get("qemupath")+"/qemu-img","create","-b",self.get_base(),"-f",self.VM.settings.get('cowfmt'),cowname]
					proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
					proc.wait()
					proc = subprocess.Popen(["/bin/sync"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
					proc.wait()
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
		self._needsudo = False
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
		# PRIVATE COW IMAGES MUST BE CREATED IN A DIFFERENT DIRECTORY FOR EACH PROJECT
		self.basepath = self.settings.get("baseimages") + "/." + self.project_parms['id']
		self.cfg.basehda = ""
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
		self.cfg.use_virtio=""
		self.cfg.stdout=""
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
			'#keyboard':'keyboard',
			'#usbdevlist':'usbdevlist',
			'-soundhw':'soundhw',
			'-usb':'usbmode',
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
			'#serial': 'serial',
			'#stdout': ''
		}

	def get_parameters(self):
		txt = _("command:") + " %s, ram: %s" % (self.prog(), self.cfg.ram)
		for p in self.plugs:
			if p.mode == 'hostonly':
				txt += ', eth %s: Host' % unicode(p.vlan)
			elif p.sock:
				txt += ', eth %s: %s' % (unicode(p.vlan), p.sock.nickname)
		return txt

	def update_usbdevlist(self, dev, old):
		print "update_usbdevlist: old [%s] - new[%s]" % (old,dev)
		for d in dev.split(' '):
			if not d in old.split(' '):
				self.send("usb_add host:"+d+"\n")
		# FIXME: Don't know how to remove old devices, due to the ugly syntax of
		# usb_del command.


	def get_type(self):
		return "Qemu"

	def associate_disk(self):
		for hd in ['hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb', 'mtdblock']:
			disk = getattr(self.cfg,hd)
			if hasattr(disk, "image"):
				if disk.image is not None and self.cfg.get('base'+hd) != disk.image.name:
					disk.set_image(self.cfg.get('base'+hd))
				elif disk.image is None and len(self.cfg.get('base'+hd)) > 0:
					disk.set_image(self.cfg.get('base'+hd))
			else:
				return

	def post_rename(self, newname):
		self.newbrick_changes()

	def on_config_changed(self):
		self.associate_disk()
		Brick.on_config_changed(self)

	def configured(self):
		cfg_ok = True
		for p in self.plugs:
			if p.sock is None and p.mode == 'vde':
				cfg_ok = False
		return cfg_ok
	# QEMU PROGRAM SELECTION
	def prog(self):
		#IF IS IN A SERVER, CHECK IF KVM WORKS
		if self.factory.server:
			try:
				self.settings.check_kvm()
			except IOError:
				raise BadConfig(_("KVM not found! Please change VM configuration."))
				return
			except NotImplementedError:
				raise BadConfig(_("KVM not found! Please change VM configuration."))
				return

		if (len(self.cfg.argv0) > 0 and self.cfg.kvm != "*"):
			cmd = self.settings.get("qemupath") + "/" + self.cfg.argv0
		else:
			cmd = self.settings.get("qemupath") + "/qemu"
		if self.cfg.kvm == "*":
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

		if self.factory.nogui == True or self.homehost is not None:
			res.append("-nographic")

		self.factory.clear_machine_vmdisks(self)
		idx = 0
		for dev in ['hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb', 'mtdblock']:
			if self.cfg.get("base" + dev) != "":
				master = False
				disk = getattr(self.cfg, dev)
				if self.cfg.get("private" + dev) == "*":
					disk.cow = True
				else:
					disk.cow = False
				real_disk = disk.get_real_disk_name()
				if disk.cow == False and disk.readonly() == False:
					if disk.image.readonly is not True:
						if disk.image.set_master(disk):
							self.factory.debug(_("Machine ")+self.name+_(" acquired master lock on image ")+disk.image.name)
							master = True
						else:
							raise DiskLocked(_("Disk image %s already in use." % disk.image.name))
							return
					else:
						raise DiskLocked(_("Disk image %s is marked as readonly and you are not using private cow or snapshot mode." % disk.image.name))
						return
				if self.cfg.get('use_virtio') == "*":
					res.append('-drive')
					diskname = disk.get_real_disk_name()
					res.append('file='+diskname+',if=virtio,index='+str(idx))
					idx += 1
				else:

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
			res.append(re.sub('"','',self.cfg.kopt));

		if self.cfg.gdb:
			res.append('-gdb')
			res.append('tcp::' + self.cfg.gdbport)
		if self.cfg.vnc:
			res.append('-vnc')
			res.append(':' + self.cfg.vncN)
		if self.cfg.vga:
			res.append('-vga')
			res.append('std')

		if self.cfg.usbmode and self.cfg.usbdevlist:
			for dev in self.cfg.usbdevlist.split(' '):
				res.append('-usbdevice')
				res.append('host:'+dev)
			''' The world is not ready for this, do chown /dev/bus/usb instead. '''
			#self._needsudo = True
		else:
			self._needsudo = False

		res.append('-name')
		res.append(self.name)
		if (len(self.plugs) + len(self.socks) == 0):
			res.append('-net')
			res.append('none')
		else:
			for pl in sorted(self.plugs + self.socks, key= lambda plug: plug.vlan):
				res.append("-device")
				res.append("%s,vlan=%d,mac=%s,id=eth%s" % (pl.get_model_driver(), pl.vlan, pl.mac, str(pl.vlan)))
				if (pl.mode == 'vde'):
					res.append("-net")
					res.append("vde,vlan=%d,sock=%s" % (pl.vlan, pl.sock.path.rstrip('[]')))
				elif (pl.mode == 'sock'):
					res.append("-net")
					res.append("vde,vlan=%d,sock=%s" % (pl.vlan, pl.path))
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
		self.associate_disk()

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
			if self.proc.stdout is not None:
				self.factory.err(self, "Virtual Machine startup failed. Check your configuration!\nMessage:\n"+"\n".join(self.proc.stdout.readlines()))
			elif self.cfg.stdout != "":
				stdout = open(self.cfg.stdout, "r")
				self.factory.err(self, "Virtual Machine startup failed. Check your configuration!\nMessage:\n"+"\n".join(stdout.readlines()))
			else:
				self.factory.err(self, "Virtual Machine startup failed. Check your configuration!")

			return None

	def commit_disks(self, args):
		self.send("commit all\n")

	def post_poweroff(self):
		self.active = False
		self.start_related_events(off=True)
