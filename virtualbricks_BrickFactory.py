#!/usr/bin/python
# -*- coding: utf-8 -*-

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
import virtualbricks_GUI
import virtualbricks_Global as Global
import virtualbricks_Settings as Settings
import select
import copy
import socket


class InvalidNameException(Exception):
	def __init__(self):
		pass
class BadConfigException(Exception):
	def __init__(self):
		pass
class NotConnectedException(Exception):
	def __init__(self):
		pass
class LinkloopException(Exception):
	def __init__(self):
		pass


def ValidName(name):
	if not re.search("\A[a-zA-Z]", name):
		return None
	while(name.startswith(' ')):
		name = name.lstrip(' ')
	while(name.endswith(' ')):
		name = name.rstrip(' ')

	name = re.sub(' ','_',name)
	if not re.search("\A\w+\Z", name):
		return None
	return name
	
class Plug():
	def __init__(self, _brick):
		self.brick = _brick
		self.sock=None
		self.antiloop=False
		self.mode='vde'

	def configured(self):
		if self.sock is None:
			return False
		else:
			return True

	def connected(self):
		if self.antiloop:
			print "Network loop detected!"
			self.antiloop = False
			return False

		self.antiloop = True
		if self.sock is None or self.sock.brick is None:
			self.antiloop=False
			return False
		self.sock.brick.poweron()
		if self.sock.brick.proc is None:
			self.antiloop = False
			return False
		for p in self.sock.brick.plugs:
			if p.connected() == False:
				self.antiloop = False
				return False
		self.antiloop = False
		print "connect ok"
		return True
		
	def connect(self, _sock):
		if _sock == None:
			return False
		else:
			_sock.plugs.append(self)
			self.sock = _sock
			return True
	def disconnect(self):
		self.sock=None

	
		

class Sock():
	def __init__(self, _brick, _nickname):
		self.brick = _brick
		self.nickname=_nickname
		self.path = ""
		self.plugs = []
		self.brick.factory.socks.append(self)

	def get_free_ports(self):
		return int(self.brick.cfg.numports) - len(self.plugs)
	
	def has_valid_path(self):
		return os.access(os.path.dirname(self.path), os.W_OK)
		
		

class BrickConfig():
	def set(self,attr):
		kv = attr.split("=")
		if len(kv) < 2:
			return False
		else:
			val = ''
			if (len(kv)) > 2:
				val='"'
				for c in kv[1:]:
					val+=c.lstrip('"').rstrip('"')
					val+="="
				val = val.rstrip('=') + '"'
				
			else:
				val+=kv[1]

			print "setting %s to '%s'" % (kv[0], val)
			# pure magic. I love python.
			self.__dict__[kv[0]] = val

		
      
	def set_obj(self, key, obj):
		print "setting_obj %s to '%s'" % (key, obj)
		self.__dict__[key] = obj
		
	def get(self, key):
		try:
			val = self.__dict__[key]
		except KeyError:
			return None
		return self.__dict__[key]

	def dump(self):
		for (k,v) in self.__dict__.items():
			print "%s=%s" % (k,v)

class Brick():
	def __init__(self, _factory, _name):
		self.factory = _factory
		self.settings = self.factory.settings
		self.name = _name
		self.plugs = []
		self.socks = []
		self.proc = None
		self.cfg = BrickConfig()
		self.cfg.numports = 0
		self.command_builder=dict()
		self.factory.bricks.append(self)
		self.gui_changed = False
		self.need_restart_to_apply_changes = False
		self.needsudo = False
		self.internal_console = None
		
	def cmdline(self):
		return ""

	def on_config_changed(self):
		return
	
	def help(self):
		print "Object type: " + self.get_type()
		print "Possible configuration parameter: "
		for (k,v) in self.command_builder.items():
			if not k.startswith("*"):
				print v,
				print "  ",
				print "\t(like %s %s)" % (self.prog(), k)	
			else:
				print k + " " + v + "\tset '" + v + "' to append this value to the command line with no argument prefix"
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
	

	def configure(self, attrlist):
		for attr in attrlist:
			self.cfg.set(attr)
		self.on_config_changed()
	
	def connect(self,endpoint):
		for p in self.plugs:
			if not p.configured():
				if (p.connect(endpoint)):
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
				cb = Switch.__dict__["cbset_"+key]

			elif self.get_type() == 'Wirefilter':
				cb = Wirefilter.__dict__["cbset_"+key]
				
			elif self.get_type() == 'Qemu':
				cb = Qemu.__dict__["cbset_"+key]
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

	def build_cmd_line(self):
		res = []
		
		for (k,v) in self.command_builder.items():
			
			if not k.startswith("#"):
				value = self.cfg.get(v)
				if value is "*":
					res.append(k)
					
				elif value is not None and len(value) > 0:
					if not k.startswith("*"):
						res.append(k)
						
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
				sudoarg+=cmdarg + " "
			sudoarg += "-P /tmp/" +self.name+".pid "
			command_line[0] = self.settings.sudo
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
				pidfile = open("/tmp/" +self.name+".pid", "r")
				print "open ok"
				self.pid = int(pidfile.readline().rstrip('\n'))
				print "read ok"
				print self.pid
			except:
				print("Cannot get pid from pidfile!")	
				pass
		else:
			self.pid = self.proc.pid
		if self.open_internal_console and callable(self.open_internal_console):
			self.internal_console = self.open_internal_console()
		self.post_poweron()
		
	def poweroff(self):
		print "Shutting down %s" % self.name
		if (self.proc == None):
			return False
		if self.pid > 0:
				
				
			if (self.needsudo):
				os.system(self.settings.get('sudo') + ' "kill '+ str(self.pid) + '"')
			elif self.internal_console is not None and self.get_type() != "Qemu":
				self.send('shutdown\n')
				print self.recv()
			else:
				try:
					os.kill(self.proc.pid, 15)
				except:
					pass
			if(self.proc.poll()==None):
				return
		self.proc = None
		self.need_restart_to_apply_changes = False
		if self.close_internal_console and callable(self.close_internal_console):
			self.close_internal_console()
		self.internal_console == None
		self.post_poweroff()

	def post_poweron(self):
		pass
	def post_poweroff(self):
		pass


	#############################
	# Console related operations.
	#############################
	def has_console(self):
		if (self.cfg.get('console')) and self.proc != None:
			return True
		else:
			return False

	def open_console(self):
		if not self.has_console():
			return 
		else:
			cmdline = [self.settings.get('term'),'-T',self.name,'-e','vdeterm',self.cfg.console]
			print cmdline
			try:
				console = subprocess.Popen(cmdline)
			except:
				print "Error: cannot start xterm"
				return

	#Must be overridden in Qemu to use appropriate console as internal (stdin, stdout?)
	def open_internal_console(self):
		if not self.has_console():
			return None
		time.sleep(0.5)
		c = socket.socket(socket.AF_UNIX)
		c.connect(self.cfg.console)
		return c

	def send(self,msg):
		if self.internal_console == None:
			return
		try:
			print "= sending " + msg
			self.internal_console.send(msg)
		except:
			print "send failed"

	def recv(self):
		if self.internal_console == None:
			return ''
		res = ''
		p = select.poll()
		p.register(self.internal_console, select.POLLIN)
		while True:
			pollret = p.poll(300)
			if (len(pollret)==1 and pollret[0][1] == select.POLLIN):
				print "called recv"
				line = self.internal_console.recv(100)
				print "recv: line: "+line
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
		

class Switch(Brick):
	def __init__(self, _factory, _name):
		Brick.__init__(self, _factory, _name)
		self.pid = -1
		self.active = 0
		self.cfg.path = Settings.MYPATH + '/' + self.name + '.ctl' 
		self.cfg.console = Settings.MYPATH + '/' + self.name + '.mgmt' 
		self.cfg.numports = "32"
		self.cfg.hub = ""
		self.cfg.fstp = ""
		self.ports_used = 0
		self.command_builder = {"-s":'path',
					"-M":'console',
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
	

	def prog(self):
		return self.settings.get("vdepath") + "/vde_switch"

	def get_type(self):
		return 'Switch'

	def on_config_changed(self):
		self.socks[0].path=self.cfg.path
		self.socks[0].ports=int(self.cfg.numports)

		if (self.proc is not None):
			self.need_restart_to_apply_changes = True
	
	def configured(self):
		return self.socks[0].has_valid_path()

	# live-management callbacks
	def cbset_fstp(self, arg=False):
		print "Callback fstp with argument " + self.name
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

	def cbset_numports(self, arg=32):
		print "Callback numports with argument " + self.name
		self.send("port/setnumports "+str(arg))
		print self.recv()
		

class Tap(Brick):
	def __init__(self, _factory, _name):
		Brick.__init__(self, _factory, _name)
		self.pid = -1
		self.active = 0
		self.cfg.name = _name
		self.command_builder = {"-s":'sock', "*tap":"name"}
		self.cfg.sock = ""
		self.plugs.append(Plug(self))
		self.needsudo = True
		self.cfg.ip="10.0.0.1"
		self.cfg.nm="255.255.255.0"
		self.cfg.gw=""
		self.cfg.mode="off"
		

	def prog(self):
		return self.settings.get("vdepath") + "/vde_plug2tap"

	def get_type(self):
		return 'Tap'

	def on_config_changed(self):
		if (self.plugs[0].sock is not None):
			self.cfg.sock = self.plugs[0].sock.path
		if (self.proc is not None):
			self.need_restart_to_apply_changes = True

	def configured(self):
		return (self.plugs[0].sock is not None)	

	def post_poweron(self):
		if self.cfg.mode == 'dhcp':
			ret = os.system(self.settings.get('sudo')+' "dhclient '+self.name+'"')
	
		elif self.cfg.mode == 'manual':
			# XXX Ugly, can't we ioctls?
			ret0 = os.system(self.settings.get('sudo') + ' "/sbin/ifconfig '+ self.name + ' ' +  self.cfg.ip + ' netmask ' + self.cfg.nm+'"')
			if (len(self.cfg.gw) > 0):
				ret1 = os.system(self.settings.get('sudo') + ' "/sbin/route add default gw '+ self.cfg.gw + ' dev ' + self.name+'"')
		else:
			return
			


class Wire(Brick):
	def __init__(self, _factory, _name):
		Brick.__init__(self, _factory, _name)
		self.pid = -1
		self.active = 0
		self.cfg.name = _name
		self.command_builder = {"#sock left":"sock0", "#sock right":"sock1"}
		self.cfg.sock0 = ""
		self.cfg.sock1 = ""
		self.plugs.append(Plug(self))
		self.plugs.append(Plug(self))
	
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
		self.command_builder = {"-d":"delay",
					"-l":"loss",
					"-L":"lossburst",
					"-D":"dup",
					"-b":"bandwidth",
					"-s":"speed",
					"-c":"capacity",
					"-n":"noise",
					"-m":"mtu",
					"-N":"nofifo",
					"-M":"console"
			} 
		self.cfg.noise = ""
		self.cfg.capacity = ""
		self.cfg.delayLR = ""
		self.cfg.delayRL = ""
		self.cfg.lossLR = ""
		self.cfg.lossRL = ""
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
		res.append(self.cfg.sock0+":"+self.cfg.sock1)

		if len(self.cfg.delayLR) > 0:
			res.append("-d")
			res.append("LR"+self.cfg.delayLR)
		if len(self.cfg.delayRL) > 0:
			res.append("-d")
			res.append("RL"+self.cfg.delayLR)
		
		if len(self.cfg.lossLR) > 0:
			res.append("-l")
			res.append("LR"+self.cfg.lossLR)
		if len(self.cfg.lossRL) > 0:
			res.append("-l")
			res.append("RL"+self.cfg.lossLR)
		
		if len(self.cfg.dupLR) > 0:
			res.append("-D")
			res.append("LR"+self.cfg.dupLR)
		if len(self.cfg.dupRL) > 0:
			res.append("-D")
			res.append("RL"+self.cfg.dupLR)
		
		if len(self.cfg.speedLR) > 0:
			res.append("-s")
			res.append("LR" + self.cfg.speedLR + self.cfg.speedLRunit + self.cfg.speedLRdistribution)
		if len(self.cfg.speedRL) > 0:
			res.append("-s")
			res.append("RL" + self.cfg.speedRL + self.cfg.speedRLunit + self.cfg.speedRLdistribution)
		
		if len(self.cfg.bandwidthLR) > 0:
			res.append("-s")
			res.append("LR" + self.cfg.bandwidthLR + self.cfg.bandwidthLRunit + self.cfg.bandwidthLRdistribution)
		if len(self.cfg.bandwidthRL) > 0:
			res.append("-s")
			res.append("RL" + self.cfg.bandwidthRL + self.cfg.bandwidthRLunit + self.cfg.bandwidthRLdistribution)

		for param in Brick.build_cmd_line(self):
			res.append(param)
		return res
	
	def prog(self):
		return self.settings.get("vdepath") + "/wirefilter"
	
	def get_type(self):
		return 'Wirefilter'

	#callbacks for live-management	
	# TODO

class TunnelListen(Brick):
	def __init__(self, _factory, _name):
		Brick.__init__(self, _factory, _name)
		self.pid = -1
		self.active = 0
		self.cfg.name = _name
		self.command_builder = {"-s":'sock', 
			"#password":"password", 
			"-p":"port"
		}
		self.cfg.sock = ""
		self.cfg.password = ""
		self.plugs.append(Plug(self))
		self.cfg.port = "7667"
	

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
		pwdgen="echo %s | sha1sum >/tmp/tunnel_%s.key && sync" % (self.cfg.password, self.name)
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
		self.cfg.localport="10771"
		self.cfg.port="7667"
	
	def on_config_changed(self):
		if (self.plugs[0].sock is not None):
			self.cfg.sock = self.plugs[0].sock.path

		p = self.cfg.get("port")
		if p is not None:
			del(self.cfg.port)
			h = self.cfg.get("host")
			if h is not None:
				h = h.split(":")[0]
				h +=":"+p
				self.cfg.host=h
			
		if (self.proc is not None):
			self.need_restart_to_apply_changes = True
	
	def configured(self):
		return (self.plugs[0].sock is not None) and self.cfg.get("host") and len(self.cfg.host) > 0	
	
	def get_type(self):
		return 'TunnelConnect'


class VMPlug(Plug, BrickConfig):
	def __init__(self, brick):
		Plug.__init__(self, brick)
		self.mac=Global.RandMac()
		self.model='rtl8139'
		self.vlan=len(self.brick.plugs) + len(self.brick.socks) 
		self.mode='vde'


class VMPlugHostonly(VMPlug):
	
	def __init__(self, _brick):
		VMPlug.__init__(self, _brick)
		self.mode='hostonly'

	def connect(self, endpoint):
		return

	def configured(self):
		return True

	def connected(self):
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
			ret.append("-"+self.device)
		ret.append(diskname)
		return ret

class VM(Brick):
	def __init__(self, _factory, _name):
		Brick.__init__(self, _factory, _name)
		self.pid = -1
		self.active = 0
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
		self.cfg.basehda =""
		self.cfg.set_obj("hda",VMDisk(_name, "hda"))
		self.cfg.privatehda=""
		self.cfg.basehdb =""
		self.cfg.set_obj("hdb", VMDisk(_name, "hdb"))
		self.cfg.privatehdb=""
		self.cfg.basehdc =""
		self.cfg.set_obj("hdc", VMDisk(_name, "hdc"))
		self.cfg.privatehdc=""
		self.cfg.basehdd =""
		self.cfg.set_obj("hdd", VMDisk(_name, "hdd"))
		self.cfg.privatehdd=""
		self.cfg.basefda =""
		self.cfg.set_obj("fda", VMDisk(_name, "fda"))
		self.cfg.privatefda=""
		self.cfg.basefdb =""
		self.cfg.set_obj("fdb", VMDisk(_name, "fdb"))
		self.cfg.privatefdb=""
		self.cfg.cdrom = ""
		self.cfg.device = ""
		self.cfg.cdromen = ""
		self.cfg.deviceen = ""
		self.cfg.kvm = ""
		self.cfg.soundhw=""
		self.cfg.rtc = ""
		#kernel etc.
		self.cfg.kernel=""
		self.cfg.initrd=""
		self.cfg.gdb=""
		self.cfg.gdbport=""	
		self.cfg.kopt=""
			
		self.command_builder = {
			'#argv0':'argv0',
			'-M':'machine',
			'-cpu':'cpu',
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
			'#privatehda': 'privatehda',
			'#privatehdb': 'privatehdb',
			'#privatehdc': 'privatehdc',
			'#privatehdd': 'privatehdd',
			'#privatefda': 'privatefda',
			'#privatefdb': 'privatefdb',
			'#cdrom':'cdrom',
			'#device':'device',
			'#cdromen': 'cdromen',
			'#deviceen': 'deviceen',
			##extended drive: TBD
			#'-mtdblock':'mtdblock', ## TODO 0.3
			#'-k':'keyboard',  ## TODO 0.3
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
			#'-sdl':'sdl', ## TODO 0.3
			#'-potrait':'potrait', ## TODO 0.3
			#'-win2k-hack':'win2k', ## not implemented
			#'-no-acpi':'noacpi', ## TODO 0.3
			#'-no-hpet':'nohpet', ## ???
			#'-baloon':'baloon', ## ???
			##acpitable not supported
			##smbios not supported
			'-kernel':'kernel',
			'-append':'kopt',
			'-initrd':'initrd',
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
			#'-tdf':'', ## TODO 0.3
			#'-kvm-shadow-memory':'',  ## TODO: maybe a global option
			#'-mem-path':'',
			#'-mem-prealloc':''
		}
		
		
	def get_type(self):
		return "Qemu"
	
	def check_links(self):
		return True 
	
	def configured(self):
		cfg_ok = True
		for p in self.plugs:
			if p.sock is None and p.mode == 'vde':
				cfg_ok = False
		return cfg_ok
	# QEMU PROGRAM SELECTION	
	def prog(self):
		if (len(self.cfg.argv0) > 0):
			cmd = self.settings.get("qemupath") + "/" + self.cfg.argv0
		else:
			cmd = self.settings.get("qemupath") + "/qemu"
		if ((cmd == 'qemu' or cmd.endswith('i386')) and (self.cfg.kvm == '*' or self.settings.kvm == 'kvm')):
			cmd = self.settings.get("qemupath") + "/kvm"
			self.cfg.cpu=""
			self.cfg.machine=""
		return cmd
		

	def args(self):
		res = []
		res.append(self.prog())
		for c in self.build_cmd_line():
			res.append(c)
		for dev in ['hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb']:
		  if self.cfg.get("base"+dev) != "":
			disk = getattr(self.cfg, dev)
			disk.base = self.cfg.get("base"+dev)
			disk.cow=False
			if (self.cfg.get("private"+dev) == "*"):
			  disk.cow = True
			args=disk.args(True)
			res.append(args[0])
			res.append(args[1])
		if self.cfg.gdb == '*':
			res.append('-gdb')
			res.append('tcp::' + self.cfg.gdbport) 
		if self.cfg.vnc == '*':
			res.append('-vnc')
			res.append(':' + self.cfg.vncN) 
		if self.cfg.vga == '*':
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
				if (pl.mode=='vde'):
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
		
		if (self.cfg.rtc== "*"):
			res.append('-rtc')
			res.append('base=localtime')

		res.append("-mon")
		res.append("chardev=mon")
		res.append("-chardev")
		res.append('socket,id=mon,path='+Settings.MYPATH + '/' + self.name + '.mgmt,server')
		self.cfg.console=Settings.MYPATH + '/' + self.name + '.mgmt'
		print res
		return res

	def add_plug(self, sock=None, mac=None, model=None):
		if sock and sock == '_hostonly':
			pl = VMPlugHostonly(self)
			print "hostonly added"
		else:	
			pl = VMPlug(self)
		self.plugs.append(pl)
		if pl.mode == 'vde':
			pl.connect(sock)
		if mac:
			pl.mac = mac
		if model:
			pl.model = model
		self.gui_changed=True
		return pl

	def connect(self,endpoint):
		pl = self.add_plug()
		pl.mac = Global.RandMac()
		pl.model = 'rtl8139'
		pl.connect(endpoint)
		self.gui_changed=True

	def remove_plug(self, idx):
		for p in self.plugs:
			if p.vlan == idx:
				self.plugs.remove(p)	
				del(p)
		for p in self.plugs:
			if p.vlan > idx:
				p.vlan-=1
		self.gui_changed=True
			

class BrickFactory(threading.Thread):
	def __init__(self, showconsole=True):
		self.bricks = []
		self.socks = []
		self.showconsole = showconsole
		threading.Thread.__init__(self)
		self.running_condition = True
		self.settings=Settings.Settings(Settings.CONFIGFILE)
		self.settings.load()
		self.config_restore(Settings.MYPATH+"/.virtualbricks.state")
		

	def getbrickbyname(self, name):
		for b in self.bricks:
			if b.name == name:
				return b
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
					print
					print "virtualbricks> ",
					sys.stdout.flush()
			else:
				time.sleep(1)
		sys.exit(0)

	def config_dump(self,f):
		try:
		    p = open(f, "w+")
		except:
		    print "ERROR WRITING CONFIGURATION!\nProbably file doesn't exist or you can't write it."
		    return
		
		for b in self.bricks:
			p.write('[' + b.get_type() +':'+ b.name + ']\n')
			for k,v in b.cfg.__dict__.items():
				# VMDisk objects don't need to be saved 
				if b.get_type()!="Qemu" or ( b.get_type()=="Qemu" and k not in ['hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb'] ):
				  p.write(k +'=' + str(v) + '\n')
				  
		for b in self.bricks: 
			for pl in b.plugs:
				if b.get_type()=='Qemu':
					if pl.mode == 'vde':
						p.write('link|' + b.name + "|" + pl.sock.nickname+'|'+pl.model+'|'+pl.mac+'|'+str(pl.vlan)+'\n')
					else:
						p.write('userlink|'+b.name+'||'+pl.model+'|'+pl.mac+'|'+str(pl.vlan)+'\n')
				elif (pl.sock is not None):
					p.write('link|' + b.name + "|" + pl.sock.nickname+'\n')


	def config_restore(self,f):
		try:
			p = open(f, "r")
		except:
			p = open(f, "w")
			return 

		l = p.readline()
		b = None
		while (l):
			l = re.sub(' ','',l)
			if re.search("\A.*link\|", l) and len(l.split("|")) >= 3:
				l.rstrip('\n')
				print "************************* link detected"
				for bb in self.bricks:
					if bb.name == l.split("|")[1]:
						if (bb.get_type()=='Qemu'):
							sockname = l.split('|')[2]
							model = l.split("|")[3]	
							macaddr = l.split("|")[4]	
							vlan = l.split("|")[5]	
							this_sock='?'
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
							self.connect(bb,l.split('|')[2].rstrip('\n'))
				
			if l.startswith('['):
				ntype = l.lstrip('[').split(':')[0]
				name = l.split(':')[1].rstrip(']\n')
				print "new brick: "+ntype+":"+name
				try:
					self.newbrick(ntype,name)
					for bb in self.bricks:
						if name == bb.name:
							b = bb
				except Exception:
					print "--------- Bad config line"
					l = p.readline()
					continue
				
				l = p.readline()
				print "-------- loading settings for "+b.name + " first line: " + l
				while b and l and not l.startswith('[') and not re.search("\A.*link\|", l):
					if len(l.split('=')) > 1:
						print "setting" + l.strip('\n')
						b.cfg.set(l.rstrip('\n'))
					l = p.readline()
					
				continue
			l = p.readline()
			

	def quit(self):
		for b in self.bricks:
			if b.proc is not None:
				b.poweroff()
		print 'Engine: Bye!'
		self.config_dump(Settings.MYPATH+"/.virtualbricks.state")
		self.running_condition = False
		sys.exit(0)


	def proclist(self):
		procs = 0
		for b in self.bricks:
			if b.proc is not None:
				procs+=1

			
		if procs > 0:
			print "PID\tType\tname"
			for b in self.bricks:
				if b.proc is not None:
					print "%d\t%s\t%s" % (b.pid,b.get_type(),b.name)
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
			self.newbrick(*command.split(" ")[1:])
		elif command == 'list':
			for obj in self.bricks:
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
		else:
			found=None
			for obj in self.bricks:
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
		if (cmd[0] == 'config'):
			obj.configure(cmd[1:])
		if (cmd[0] == 'show'):
			obj.cfg.dump()
		if (cmd[0] == 'connect' and len(cmd) == 2):
			if(self.connect(obj, cmd[1].rstrip('\n'))):
				print ("Connection ok")
			else:
				print ("Connection failed")
		if (cmd[0] == 'disconnect'):
			obj.disconnect()
		if (cmd[0] == 'help'):
			obj.help()

	def connect(self, brick, nick):
		endpoint = None
		if len(nick) == 0:
			return False
		for n in self.socks:
			if n.nickname == nick:
				endpoint = n
		if endpoint is not None:
			return 	brick.connect(endpoint)
		else:
			print "cannot find " + nick
			print self.socks


	def delbrick(self,bricktodel):
		for b in self.bricks:
			if b == bricktodel:
				for so in b.socks:
					self.socks.remove(so)
				self.bricks.remove(b)
				del(b)
	def dupbrick(self,bricktodup):
		b1 = copy.copy(bricktodup)
		b1.cfg = copy.copy(bricktodup.cfg)
		b1.name = "copy_of_"+bricktodup.name
		b1.plugs = []
		b1.socks = []
		if b1.get_type() == "Switch":
			portname = b1.name + "_port"
			b1.socks.append(Sock(b1, portname))
			b1.cfg.path = Settings.MYPATH + '/' + b1.name + '.ctl' 
		if b1.get_type().startswith("Wire"):
			self.cfg.sock0 = ""
			self.cfg.sock1 = ""
		
		if (b1.cfg.console):
			b1.cfg.console = Settings.MYPATH + '/' + b1.name + '.mgmt' 
		self.bricks.append(b1)
		b1.on_config_changed()

	def renamebrick(self,b,newname):
		newname = ValidName(newname)
		if newname == None:
			raise InvalidNameException
		else:
			b.name = newname
			if b.get_type() == "Switch":
				for so in b.socks:
					so.nickname = b.name + "_port"
				b.cfg.path = Settings.MYPATH + '/' + b.name + '.ctl' 
				b.cfg.console = Settings.MYPATH + '/' + b.name + '.mgmt' 
			b.gui_changed = True
	
	def newbrick(self, ntype="", name=""):
		for oldb in self.bricks:
			if oldb.name == name:
				raise InvalidNameException
		name = ValidName(name)
		if not name:
			raise InvalidNameException

		if ntype == "switch" or ntype == "Switch":
			s = Switch(self,name) 
			print "new switch %s OK" % s.name
		elif ntype == "tap" or ntype == "Tap":
			s = Tap(self,name) 
			print "new tap %s OK" % s.name
		elif ntype == "vm" or ntype == "Qemu":
			s = VM(self, name) 
			print "new vm %s OK" % s.name
		elif ntype == "wire" or ntype == "Wire" or ntype == "Cable":
			s = Wire(self, name) 
			print "new cable %s OK" % s.name
		elif ntype == "wirefilter" or ntype == "Wirefilter":
			s = Wirefilter(self,name) 
			print "new wirefilter %s OK" % s.name
		elif ntype == "tunnell" or ntype == "Tunnel Server" or ntype == "TunnelListen":
			s = TunnelListen(self,name) 
			print "new tunnel server %s OK" % s.name
		elif ntype == "tunnelc" or ntype == "Tunnel Client" or ntype == "TunnelConnect":
			s = TunnelConnect(self,name) 
			print "new tunnel client %s OK" % s.name
		#elif ...:
		else:
			print 'Invalid command.'
			return False
		return True
