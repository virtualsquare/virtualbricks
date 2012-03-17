#!/usr/bin/env python
# coding: utf-8
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

import ConfigParser
import new
import os

from virtualbricks.logger import ChildLogger

VDEPATH = "/usr/bin"
HOME = os.path.expanduser("~")
MYPATH = os.path.join(HOME, ".virtualbricks")
CONFIGFILE = os.path.join(HOME, ".virtualbricks.conf")

class Settings(ChildLogger):
	DEFAULT_SECTION = "Main"
	def __init__(self, filename, logger):
		ChildLogger.__init__(self, logger)
		# default config
		default_conf = {
			"bricksdirectory": HOME + "/.virtualbricks",
			"term": "/usr/bin/xterm",
			"alt-term": "/usr/bin/gnome-terminal",
			"sudo": "/usr/bin/gksu",
			"qemupath": "/usr/bin",
			"baseimages": HOME + "/.virtualbricks/img",
			"kvm": False,
			"ksm": False,
			"kqemu": False,
			"cdroms": "",
			"vdepath": "/usr/bin",
			"python": False,
			"femaleplugs": False,
			"erroronloop": False,
			"systray": True,
			"current_project": HOME + "/.virtualbricks/.virtualbricks.vbl",
			"projects": 0,
			"cowfmt":"cow",
			"show_missing": True,
		}
		self.filename = filename
		self.config = ConfigParser.SafeConfigParser()
		try:
			os.mkdir(MYPATH)
		except:
			pass

		def create_get(attr):
			return lambda instance, x: self.config.getboolean(self.DEFAULT_SECTION, attr)

		def create_set(attr):
			return lambda instance, x, enabled: self.config.set(self.DEFAULT_SECTION, attr,
				unicode(enabled))

		for attr in ['kvm', 'ksm', 'kqemu', 'python', 'femaleplugs',
				'erroronloop', 'systray', 'show_missing']:
			m_get = new.instancemethod(create_get(attr), self, Settings)
			m_set = new.instancemethod(create_set(attr), self, Settings)
			setattr(self, 'get_%s' % attr, m_get)
			setattr(self, 'set_%s' % attr, m_set)
			setattr(Settings, attr, property(m_get, m_set))

		self.config.add_section(self.DEFAULT_SECTION)
		for key, value in default_conf.items():
			self.config.set(self.DEFAULT_SECTION, key, unicode(value))

		if os.path.exists(self.filename):
			try:
				self.config.read(self.filename)
				self.info(_("Configuration loaded ('%s')"), self.filename)
			except Exception, err:
				self.error(_("Cannot read config file ") + "'" + self.filename + "':" + "'" + err + "'!")
		else:
			self.info(_("Default configuration loaded"))
			try:
				with open(self.filename, 'wb') as configfile:
					self.config.write(configfile)
				self.info(_("Default configuration saved ('%s')"),
						self.filename)
			except Exception, err:
				self.error(_("Cannot save default configuration"))

		self.check_ksm(self.ksm)
		self.ksm = self.ksm

	def get(self, attr):
		val = self.config.get(self.DEFAULT_SECTION, unicode(attr))
		if attr == 'sudo' and os.getuid()==0:
			return ''
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
			self.error("Can not change ksm state. (failed command: %s)" % cmd )

	def sudo_system(self, cmd):
		sudo = self.get("sudo")
		if len(sudo) > 0:
			return os.system(self.get("sudo") + ' ' + repr(cmd))
		else:
			return os.system(cmd)

