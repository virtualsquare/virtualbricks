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
import new
import os
import ConfigParser
from virtualbricks_Logger import ChildLogger

VDEPATH = "/usr/bin"
HOME = os.path.expanduser("~")
MYPATH = os.path.join(HOME, ".virtualbricks")
CONFIGFILE = os.path.join(HOME, ".virtualbricks.conf")
#TERM=os.environ.get("COLORTERM",None);

COMBOBOXES = dict()

def ComboBox(widget):
	for k, v in COMBOBOXES.items():
		if k == widget:
			return v
	COMBOBOXES[widget] = ComboBoxObj(widget)
	return COMBOBOXES[widget]


class ComboBoxObj:
	def __init__(self, _widget):
		self.widget = _widget
		self.model = self.widget.get_model()
		self.options = dict()

	def populate(self, args, selected=None, _clear=True):
		"""args is dict[showing_name] = real name"""
		if _clear:
			self.clear()
		for (k, v) in args.items():
			self.options[k] = v

		items = [(v, k) for k, v in self.options.items()]
		items.sort()
		items = [(k, v) for v, k in items]
		for k, v in items:
			self.widget.append_text(k)

		if selected:
			self.select(selected)

	def clear(self):
		self.options = {}
		self.widget.set_model(None)
		self.model.clear()
		self.widget.set_model(self.model)

	def select(self, regexp):
		index = self.model.get_iter_first()
		active = -1
		while index is not None:
			value = self.model.get_value(index, 0)
			if value == regexp:
			#if re.search(regexp, s):
				print "Found match:" + value
				active = index
				print "activate " + regexp
				print "setting active to " + unicode(active)
				self.widget.set_active_iter(active)
				break
			index = self.model.iter_next(index)

	def get_selected(self):
		txt = self.widget.get_active_text()
		try:
			return self.options[txt]
		except KeyError:
			return None

class Settings(ChildLogger):
	DEFAULT_SECTION = "Main"
	def __init__(self, filename, logger):
		ChildLogger.__init__(self, logger)
		# default config
		default_conf = {
			"bricksdirectory": os.path.join(HOME, "virtualbricks"),
			"term": "/usr/bin/xterm",
			"sudo": "/usr/bin/gksu",
			"qemupath": "/usr/bin",
			"baseimages": HOME + "/virtualbricks/img",
			"kvm": False,
			"ksm": False,
			"kqemu": False,
			"cdroms": "",
			"vdepath": "/usr/bin",
			"python": False,
			"femaleplugs": False,
			"erroronloop": False,
			"systray": True,
		}
		self.filename = filename
		self.config = ConfigParser.SafeConfigParser()

		def create_get(attr):
			return lambda instance, x: self.config.getboolean(self.DEFAULT_SECTION, attr)

		def create_set(attr):
			return lambda instance, x, enabled: self.config.set(self.DEFAULT_SECTION, attr,
				unicode(enabled))

		for attr in ['kvm', 'ksm', 'kqemu', 'python', 'femaleplugs',
				'erroronloop', 'systray']:
			m_get = new.instancemethod(create_get(attr), self, Settings)
			m_set = new.instancemethod(create_set(attr), self, Settings)
			setattr(self, 'get_%s' % attr, m_get)
			setattr(self, 'set_%s' % attr, m_set)
			setattr(Settings, attr, property(m_get, m_set))

		self.config.add_section(self.DEFAULT_SECTION)
		for key, value in default_conf.items():
			self.config.set(self.DEFAULT_SECTION, key, unicode(value))

		self.config.read(self.filename)

		try:
			self.config.read(self.filename)
			print "CONFIGURATION: LOADED."
			self.check_ksm(self.ksm)
			self.ksm = self.ksm
		except Exception, err:
			print "Cannot open config file '%s': '%s'!" % (self.filename, err)
			raise err
			try:
				with open(self.filename, 'wb') as configfile:
					self.config.write(configfile)
					print "default configuration written"
			except Exception, err:
				print "Can not save default configuration: '%s'" % err
				return

	def get(self, attr):
		val = self.config.get(self.DEFAULT_SECTION, unicode(attr))
		if val == "False" or val == "True":
			raise Exception("'%s' use getboolean" % attr)
		return val

	def set(self, attr, value):
		self.config.set(self.DEFAULT_SECTION, unicode(attr), unicode(value))

	def store(self):
		with open(self.filename, 'wb') as configfile:
			self.config.write(configfile)

	def check_missing_vdepath(self, path):
		vdebin_template = ['vde_switch', 'vde_plug', 'vde_cryptcab', 'dpipe', 'vdeterm', 'vde_plug2tap', 'wirefilter']
		res = []
		for v in vdebin_template:
			if not os.access(os.path.join(path, v), os.X_OK):
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
		for b in self.check_missing_qemupath(self.get("qemupath")):
			if b == 'kvm':
				raise IOError()

		if not os.access("/sys/class/misc/kvm", os.X_OK):
			raise NotImplementedError()
		return True

	def check_ksm(self, enable_ksm):
		"""enable ksm if needed"""
		ksm_path = '/sys/kernel/mm/ksm/run'
		if not os.path.isfile(ksm_path):
			return

		with open(ksm_path) as input:
			ksm_state = input.readline().strip()

		cmd = ''
		if enable_ksm and ksm_state == '0':
			cmd = "echo 1 > %s" % ksm_path

		if not enable_ksm and ksm_state == '1':
			cmd = "echo 0 > %s" % ksm_path

		if cmd and self.sudo_system(cmd) != 0:
			self.error("Can not change ksm state.")

	def sudo_system(self, cmd):
		return os.system(self.get("sudo") + ' ' + repr(cmd))
