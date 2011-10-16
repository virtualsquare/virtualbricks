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

import gobject
import gtk
import os
import re
import subprocess
import sys
from threading import Thread
import time
from traceback import format_exception
import re

from virtualbricks import tools
from virtualbricks.brickfactory import BrickFactory, ValidName, VbShellCommand, RemoteHost
from virtualbricks.errors import BadConfig, DiskLocked, InvalidName, Linkloop, NotConnected
from virtualbricks.gui.combo import ComboBox
from virtualbricks.gui.graphics import *
from virtualbricks.gui.logger import Logger
from virtualbricks.gui.tree import *
from virtualbricks.models import BricksModel, EventsModel
from virtualbricks.settings import MYPATH


class VBGUI(Logger, gobject.GObject):
	def __init__(self, noterm=False):
		gobject.GObject.__init__(self)
		Logger.__init__(self)

		if not os.access(MYPATH, os.X_OK):
			os.mkdir(MYPATH)

		self.topology = None
		try:
			self.gladefile = gtk.glade.XML('/usr/share/virtualbricks/virtualbricks.glade')
		except:
			try:
				self.gladefile = gtk.glade.XML(os.path.join(sys.prefix, '/share/virtualbricks/virtualbricks.glade'))
			except:
				# FTFY, distutils!
				try:
					self.gladefile = gtk.glade.XML(os.path.join(sys.prefix,'local')+ '/share/virtualbricks/virtualbricks.glade')
				except:
					self.critical("Cannot open required file 'virtualbricks.glade'")


		self.widg = self.get_widgets(self.widgetnames())

		self.info("Starting VirtualBricks!")

		gtk.gdk.threads_init()

		self.brickfactory = BrickFactory(self, not noterm)

		self.brickfactory.bricksmodel.connect("brick-added", self.cb_brick_added)
		self.brickfactory.bricksmodel.connect("brick-deleted", self.cb_brick_deleted)

		self._engine_closed = self.brickfactory.connect("engine-closed", self.quit_from_commandline)

		self.brickfactory.connect("brick-stopped", self.cb_brick_stopped)
		self.brickfactory.connect("brick-started", self.cb_brick_started)
		self.brickfactory.connect("brick-error", self.cb_brickfactory_error)
		self.brickfactory.connect("brick-changed", self.cb_brick_changed)

		self.brickfactory.connect("event-started", self.cb_event_started)
		self.brickfactory.connect("event-stopped", self.cb_event_stopped)
		self.brickfactory.connect("event-changed", self.cb_event_changed)

		self.brickfactory.eventsmodel.connect("event-added", self.cb_event_added)
		self.brickfactory.eventsmodel.connect("event-deleted", self.cb_event_deleted)


		self.availmodel = None
		self.addedmodel = None
		self.eventsmodel = None
		self.shcommandsmodel = None


		self.config = self.brickfactory.settings

		self.gladefile.get_widget("messages_textview").set_buffer(self.messages_buffer)

		self.widg['main_win'].show()

		self.ps = []
		self.bricks = []

		''' Don't remove me, I am useful after config, when treeview may lose focus and selection. '''
		self.last_known_selected_brick = None
		self.last_known_selected_event = None
		self.gladefile.get_widget("main_win").connect("delete-event", self.delete_event)
		self.topology_active = False

		self.sockscombo = dict()

		self.running_bricks = VBTree(self, 'treeview_joblist', None, [gtk.gdk.Pixbuf,
			gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING],
			['',_('PID'),_('Type'),_('Name')])

		''' Main Treeview '''
		self.maintree = BricksTree(self, 'treeview_bookmarks', self.brickfactory.bricksmodel, [gtk.gdk.Pixbuf, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING], [_('Icon'), _('Status'), _('Type'), _('Name'), _('Parameters')])

		self.remote_hosts_tree = VBTree(self, 'treeview_remotehosts', None, [gtk.gdk.Pixbuf,
			 gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING],
			['Status',_('Address'),_('Bricks'),_('Autoconnect')])

		self.image_tree = VBTree(self, 'treeview_diskimages', None, [gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING],
			[_('Image name'),_('Used by'),_('Master Brick'),_('COWs')])

		self.usbdev_tree = VBTree(self, 'treeview_usbdev', None, [gobject.TYPE_STRING, gobject.TYPE_STRING], [ _('ID'), _('Description')])
		self.gladefile.get_widget('treeview_usbdev').get_selection().set_mode(gtk.SELECTION_MULTIPLE)


		eventstree = self.gladefile.get_widget('treeview_events_bookmarks')
		eventstree.set_model(self.brickfactory.eventsmodel)

		''' This is the association to the events model. TODO: move it to its class '''
		columns = [_('Icon'), _('Status'), _('Type'), _('Name'), _('Parameters')]
		for name in columns:
			col = gtk.TreeViewColumn(name)
			if name != _('Icon'):
				elem = gtk.CellRendererText()
				col.pack_start(elem, False)
			else:
				elem = gtk.CellRendererPixbuf()
				col.pack_start(elem, False)
			col.set_cell_data_func(elem, self.event_to_cell)
			col.set_clickable(True)
			eventstree.append_column(col)

		# associate Drag and Drop action for main tree
		self.maintree.associate_drag_and_drop('BRICK')

		# associate Drag and Drop action for events tree
		eventstree = self.gladefile.get_widget('treeview_events_bookmarks')
		eventstree.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, [('EVENT', gtk.TARGET_SAME_WIDGET | gtk.TARGET_SAME_APP, 0)], gtk.gdk.ACTION_DEFAULT | gtk.gdk.ACTION_COPY)
		eventstree.enable_model_drag_dest([('EVENT', gtk.TARGET_SAME_WIDGET | gtk.TARGET_SAME_APP, 0)], gtk.gdk.ACTION_DEFAULT| gtk.gdk.ACTION_PRIVATE )

		self.vmplugs = VBTree(self, 'treeview_networkcards', None, [gobject.TYPE_STRING,
			gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING],
			['Eth','connection','model','macaddr'])

		self.statusicon = None

		#TRAYICON
		if self.config.systray:
			self.start_systray()

		self.curtain = self.gladefile.get_widget('vpaned_mainwindow')
		self.Dragging = None
		self.curtain_down()

		self.vmplug_selected = None
		self.joblist_selected = None
		self.event_selected = None
		self.remotehost_selected = None

		gtk.gdk.threads_enter()
		self.draw_topology()
		self.brickfactory.start()
		self.signals()
		self.timers()
		try:
			gtk.main()
		except KeyboardInterrupt:
			self.quit()
		finally:
			gtk.gdk.threads_leave()

	def event_to_cell(self, column, cell, model, iter):
		event = model.get_value(iter, EventsModel.EVENT_IDX)
		assert event is not None
		if column.get_title() == _('Icon'):
			#print "base: %s, grey: %s" % (event.icon.base,event.icon.grey)
			icon = gtk.gdk.pixbuf_new_from_file_at_size(event.icon.get_img(), 48,
				48)
			cell.set_property('pixbuf', icon)
		elif column.get_title() == _('Status'):
			cell.set_property('text', event.get_state())
		elif column.get_title() == _('Type'):
			cell.set_property('text', event.get_type())
		elif column.get_title() == _('Name'):
			cell.set_property('text', event.name)
		elif column.get_title() == _('Parameters'):
			cell.set_property('text', event.get_parameters())
		else:
			raise NotImplemented()

	def get_event_selected_bookmark(self):
		tree = self.gladefile.get_widget('treeview_events_bookmarks');
		path = tree.get_cursor()[0]

		if path is None:
			'''
			' Default to something that makes sense,
			' otherwise on_config_ok will be broken
			' when treeviews lose their selections.
			'''
			return self.last_known_selected_event

		model = tree.get_model()
		iter = model.get_iter(path)
		name = model.get_value(iter, EventsModel.EVENT_IDX).name
		self.last_known_selected_event = self.brickfactory.geteventbyname(name)
		return self.last_known_selected_event


	""" ******************************************************** """
	""" Signal handlers										  """
	""" ******************************************************** """

	def cb_brick_added(self, model, name):
		self.draw_topology()

	def cb_brick_deleted(self, model, name):
		self.draw_topology()

	def cb_brick_changed(self, model, name, startup):
		if not startup:
			self.draw_topology()

	def cb_brick_stopped(self, model, name=""):
		self.draw_topology()
		self.systray_blinking(None, False)

	def cb_brick_started(self, model, name=""):
		self.draw_topology()
		self.check_joblist(force=True)

	def cb_brickfactory_error(self, model, name="Unnamed"):
		gtk.gdk.threads_enter()
		self.error(name)
		gtk.gdk.threads_leave()

	def cb_event_added(self, model, name):
		pass

	def cb_event_deleted(self, model, name):
		pass

	def cb_event_changed(self, model, name, startup):
		pass

	def cb_event_stopped(self, model, name=""):
		pass

	def cb_event_started(self, model, name=""):
		pass

	""" ******************************************************** """
	"""														  """
	""" EVENT CONFIGURATION									  """
	"""														  """
	"""														  """
	""" ******************************************************** """

	def config_event_prepare(self):
		e = self.event_selected
		for key in e.cfg.keys():
			t = e.get_type()


			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "text")
			if (widget is not None):
				widget.set_text(str(e.cfg[key]))

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "treeview")
			if (widget is not None):
				self.shcommandsmodel = None
				self.shcommandsmodel = gtk.ListStore (str, bool)

				for a in e.cfg[key]:
					iter = self.shcommandsmodel.append([a, not isinstance(a, VbShellCommand)])

				iter = self.shcommandsmodel.append(["", False])

				actions = self.gladefile.get_widget('cfg_Event_actions_treeview')
				actions.set_model(self.shcommandsmodel)

				columns = (COL_COMMAND, COL_BOOL) = range(2)
				cell = gtk.CellRendererText ()
				column_command = gtk.TreeViewColumn(_("Command"), cell, text = COL_COMMAND)
				cell.set_property('editable', True)
				cell.connect('edited', self.edited_callback, (self.shcommandsmodel, COL_COMMAND))
				cell = gtk.CellRendererToggle()
				column_bool = gtk.TreeViewColumn(_("Host shell command"), cell, active = COL_BOOL)
				cell.set_property('activatable', True)
				cell.connect('toggled', self.toggled_callback, (self.shcommandsmodel, COL_BOOL))

				# Clear columns
				for c in actions.get_columns():
					actions.remove_column(c)

				# Add columns
				actions.append_column (column_command)
				actions.append_column (column_bool)
		return

	""" ******************************************************** """
	"""														  """
	""" BRICK CONFIGURATION									  """
	"""														  """
	"""														  """
	""" ******************************************************** """

	def prepare_ifcombo(self, b):
		combo = ComboBox(self.gladefile.get_widget('ifcombo_capture'))
		opt = dict()
		try:
			netdev = open("/proc/net/dev", "r")
		except:
			pass
		for line in netdev.readlines():
			if ":" in line:
				while line.startswith(" "):
					line = line.strip(" ")
				name = line.split(":")[0]
				if name != 'lo':
					opt[name] = name
		combo.populate(opt)
		for n,s in opt.iteritems():
			if n == b.cfg.iface:
				combo.select(n)

	def config_brick_prepare(self):
		b = self.maintree.get_selection()
		if b.get_type() == 'Capture':
			self.prepare_ifcombo(b)
		# Fill socks combobox
		for k in self.sockscombo_names():
			combo = ComboBox(self.gladefile.get_widget(k))
			opt=dict()
			# add Ad-hoc host only to the vmehternet
			if k == 'sockscombo_vmethernet':
				opt['Host-only ad hoc network']='_hostonly'
			if self.config.femaleplugs:
				opt['Vde socket']='_sock'

			for so in self.brickfactory.socks:
				if (so.brick.homehost == b.homehost or (b.get_type() == 'Wire' and self.config.python)) and \
				(so.brick.get_type() == 'Switch' or self.config.femaleplugs):
					opt[so.nickname] = so.nickname
			combo.populate(opt)
			t = b.get_type()
			if (not t.startswith('Wire')) or k.endswith('0'):
				if len(b.plugs) >= 1 and b.plugs[0].sock:
					combo.select(b.plugs[0].sock.nickname)

			elif k.endswith('1') and t.startswith('Wire'):
				if len(b.plugs) >= 1 and b.plugs[1].sock:
					combo.select(b.plugs[1].sock.nickname)

		dicts=dict()
		#QEMU COMMAND COMBO
		missing,found = self.config.check_missing_qemupath(self.config.get("qemupath"))
		qemuarch = ComboBox(self.gladefile.get_widget("cfg_Qemu_argv0_combo"))
		opt = dict()
		for arch in found:
			if arch.startswith('qemu-system-'):
				opt[arch.split('qemu-system-')[1]] = arch
		qemuarch.populate(opt, 'i386')
		dicts['argv0']=opt

		#SNDCARD COMBO
		sndhw = ComboBox(self.gladefile.get_widget("cfg_Qemu_soundhw_combo"))
		opt = dict()
		opt['no audio']=""
		opt['PC speaker']="pcspk"
		opt['Creative Sound Blaster 16'] = "sb16"
		opt['Intel 82801AA AC97 Audio'] = "ac97"
		opt['ENSONIQ AudioPCI ES1370'] = "es1370"
		dicts['soundhw']=opt
		sndhw.populate(opt, "")
		ComboBox(self.gladefile.get_widget("cfg_Qemu_soundhw_combo")).select('Intel 82801AA AC97 Audio')

		#device COMBO
		devices = ComboBox(self.gladefile.get_widget("cfg_Qemu_device_combo"))
		opt = dict()
		opt['NO']=""
		opt['cdrom']="/dev/cdrom"
		dicts['device']=opt
		devices.populate(opt, "")
		ComboBox(self.gladefile.get_widget("cfg_Qemu_device_combo")).select('NO')

		#boot COMBO
		boot_c = ComboBox(self.gladefile.get_widget("cfg_Qemu_boot_combo"))
		opt = dict()
		opt['HD1']=""
		opt['FLOPPY'] = "a"
		opt['CDROM'] = "d"
		dicts['boot']=opt
		boot_c.populate(opt, "")
		ComboBox(self.gladefile.get_widget("cfg_Qemu_boot_combo")).select('HD1')

		#images COMBO
		if b.get_type() == "Qemu":
			for hd in ['hda','hdb','hdc','hdd','fda','fdb','mtdblock']:
				images = ComboBox(self.gladefile.get_widget("cfg_Qemu_base"+hd+"_combo"))
				opt = dict()
				opt['Off'] = ""
				for img in self.brickfactory.disk_images:
					if b.homehost is None and img.host is None:
						opt[img.name] = img.name
					elif b.homehost is not None and img.host is not None and img.host.addr[0] == b.homehost.addr[0]:
						opt[img.name] = img.name
				images.populate(opt,"")
				if len(b.cfg.get('base'+hd)) > 0 and (getattr(b.cfg, hd)).set_image(b.cfg.get('base'+hd)):
					images.select(b.cfg.get("base"+hd))
				else:
					images.select("Off")

		# Qemu VMplugs:
		ComboBox(self.gladefile.get_widget("vmplug_model")).populate(self.qemu_eth_model())
		ComboBox(self.gladefile.get_widget("vmplug_model")).select('rtl8139')
		if len(b.plugs)+ len(b.socks) == 0:
			self.gladefile.get_widget('radiobutton_network_nonet').set_active(True)
			self.set_nonsensitivegroup(['vmplug_model', 'sockscombo_vmethernet','vmplug_macaddr','randmac',
				'button_network_netcard_add','button_network_edit','button_network_remove', 'treeview_networkcards'])
		else:
			self.gladefile.get_widget('radiobutton_network_usermode').set_active(True)
			self.set_sensitivegroup(['vmplug_model', 'sockscombo_vmethernet','vmplug_macaddr','randmac',
				'button_network_netcard_add','button_network_edit','button_network_remove', 'treeview_networkcards'])
		self.gladefile.get_widget('button_network_edit').hide()
		self.gladefile.get_widget('button_network_remove').hide()
		self.gladefile.get_widget('netcard_combo_type').set_active(0)

		# Qemu: usb devices bind button
		if (b.get_type() == "Qemu"):
			if b.cfg.get('usbmode')=='*':
				self.gladefile.get_widget('vm_usb_show').set_sensitive(True)
			else:
				self.gladefile.get_widget('vm_usb_show').set_sensitive(False)
				self.maintree.get_selection().cfg.set('usbdevlist=')


		# Qemu: check if KVM is checkable
		if (b.get_type()=="Qemu"):
			if self.config.kvm:
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_sensitive(True)
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_label("KVM")
			else:
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_sensitive(False)
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_label(_("KVM is disabled from Properties"))
				b.cfg.kvm=""

		self.update_vmplugs_tree()

		for key in b.cfg.keys():
			t = b.get_type()

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "check")
			if (widget is not None):
				if (b.cfg[key] == "*" or b.cfg[key] == 'True' or b.cfg[key] == True):
					if key is "kvm" and self.config.kvm: widget.set_active(True)
					elif key is not "kvm": widget.set_active(True)
				else: widget.set_active(False)
				if b.get_type() == 'Wirefilter':
					#Trigger wirefilter "symmetrical" checkbox management
					if key is "speedenable":
						self.on_wf_speed_checkbox_toggle(widget)
					#Trigger wirefilter "speed" section management
					else:
						self.on_symm_toggle(widget)

		for key in b.cfg.keys():
			t = b.get_type()

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "text")
			if (widget is not None):
				widget.set_text(str(b.cfg[key]))

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "spinint")
			if (widget is not None and len(b.cfg[key]) > 0):
				widget.set_value(int(b.cfg[key]))

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "spinfloat")
			if (widget is not None):
				widget.set_value(float(b.cfg[key]))

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "combo")
			if (widget is not None and dicts.has_key(key)):
				for k, v in dicts[key].iteritems():
					if (v==b.cfg[key]):
						ComboBox(self.gladefile.get_widget("cfg_"+t+"_"+key+"_combo")).select(k)

			#what a mess...
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "comboinitial")
			if (widget is not None):
				model = widget.get_model()
				iter = model.get_iter_first()
				i = 0
				while iter:
					if model.get_value(iter,0)==b.cfg[key]:
						widget.set_active(i)
						break
					else:
						iter=model.iter_next(iter)
						i = i + 1

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "filechooser")
			if (widget is not None and len(b.cfg[key]) > 0):
				widget.set_filename(b.cfg[key])
			elif (widget is not None and t=='Qemu' and (key[0:4]=='base' or key=='cdrom')):
				widget.set_current_folder(self.config.get('baseimages'))

			if 'icon' in b.cfg.keys() and b.cfg['icon'] != "":
				self.gladefile.get_widget("qemuicon").set_from_pixbuf(self.pixbuf_scaled(b.cfg['icon']))
			else:
				self.gladefile.get_widget("qemuicon").set_from_file(b.icon.get_img())

		# Tap mode:
		if b.get_type() == 'Tap':
			self.gladefile.get_widget('radio_tap_no').set_active(True)
			self.gladefile.get_widget('radio_tap_manual').set_active(True)
			if b.cfg.mode == 'off':
				self.gladefile.get_widget('radio_tap_no').set_active(True)
			if b.cfg.mode == 'dhcp':
				self.gladefile.get_widget('radio_tap_dhcp').set_active(True)
			if b.cfg.mode == 'manual':
				self.gladefile.get_widget('radio_tap_manual').set_active(True)

	def config_brick_confirm(self):
		# TODO merge in on_config_ok

		parameters = {}
		notebook=self.gladefile.get_widget('main_notebook')
		# It's an event
		if notebook.get_current_page() == 1:
			b = self.event_selected
		else:
			b = self.maintree.get_selection()
		for key in b.cfg.keys():
			t = b.get_type()
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "text")
			if (widget is not None):
				parameters[key] = widget.get_text()

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "spinint")
			if (widget is not None):
				parameters[key] = str(int(widget.get_value()))

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "spinfloat")
			if (widget is not None):
				parameters[key]=str(widget.get_value())

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "comboinitial")
			if (widget is not None):
				txt = widget.get_active_text()
				parameters[key] = txt

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "combo")
			if (widget is not None):
				combo = ComboBox(widget)
				#txt = widget.get_active_text()
				txt = combo.get_selected()
				if txt is not None and (txt != "-- default --"):
					parameters[key] = txt

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "check")
			if (widget is not None):
				if widget.get_active():
					parameters[key] = '*'
				else:
					parameters[key] = ''

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "filechooser")
			if (widget is not None):
				f = widget.get_filename()
				if f is not None:
					parameters[key] = f
				else:
					parameters[key] = ''

			b.gui_changed = True
			t = b.get_type()

			if t == 'Event':


				actions = self.gladefile.get_widget('cfg_Event_actions_treeview')

				iter = self.shcommandsmodel.get_iter_first()

				#Do not hide window
				#if not iter:
				#	return

				currevent = None
				columns = (COL_COMMAND, COL_BOOL) = range(2)
				currevent = self.event_selected

				currevent.cfg.actions=list()

				while iter:
					linecommand = self.shcommandsmodel.get_value(iter, COL_COMMAND)
					shbool = self.shcommandsmodel.get_value(iter, COL_BOOL)

					linecommand = linecommand.lstrip("\n").rstrip("\n").strip()
					"""
					Can be multiline command.
					CTRL+ENTER does not send "enter" inside
					the field but confirms the field instead, exiting edit mode.
					That feature is managed anyway.
					Example:
					sw1 config fstp=False
					wf1 config xxx=yyy
					....
					will be transformed into:
					[eventname] config add sw1 config fstp=False add wf1 config xxx=yyy add...
					"""
		 			commands = linecommand.split("\n")
		 			commandtype = 'addsh' if shbool else 'add'

		 			if not commands[0]:
		 				iter = self.shcommandsmodel.iter_next(iter)
		 				continue

		 			commands[0] = 'config %s %s' % (commandtype, commands[0])
		 			c = unicode(' %s ' % commandtype).join(commands)

		 			self.brickfactory.brickAction(currevent, c.split(" "))
		 			iter = self.shcommandsmodel.iter_next(iter)

			elif t == 'Tap':
				sel = ComboBox(self.gladefile.get_widget('sockscombo_tap')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[0].connect(so)

				# Address mode radio
				if (self.gladefile.get_widget('radio_tap_no').get_active()):
					b.cfg.mode = 'off'
				elif (self.gladefile.get_widget('radio_tap_dhcp').get_active()):
					b.cfg.mode = 'dhcp'
				else:
					b.cfg.mode = 'manual'

			elif t == 'Capture':
				sel = ComboBox(self.gladefile.get_widget('sockscombo_capture')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[0].connect(so)
				sel = ComboBox(self.gladefile.get_widget('ifcombo_capture')).get_selected()
				if sel:
					b.cfg.set("iface="+str(sel))
				else:
					b.cfg.set("iface=")


			elif t == 'TunnelConnect':
				sel = ComboBox(self.gladefile.get_widget('sockscombo_tunnelc')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[0].connect(so)
			elif t == 'TunnelListen':
				sel = ComboBox(self.gladefile.get_widget('sockscombo_tunnell')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[0].connect(so)
			elif t == 'Wire':
				sel = ComboBox(self.gladefile.get_widget('sockscombo_wire0')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[0].connect(so)
				sel = ComboBox(self.gladefile.get_widget('sockscombo_wire1')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[1].connect(so)
			elif t == 'Wirefilter':
				sel = ComboBox(self.gladefile.get_widget('sockscombo_wirefilter0')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[0].connect(so)
				sel = ComboBox(self.gladefile.get_widget('sockscombo_wirefilter1')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[1].connect(so)

		fmt_params = ['%s=%s' % (key,value) for key, value in parameters.iteritems()]
		self.user_wait_action(b.configure, fmt_params)

	def config_brick_cancel(self):
		self.curtain_down()


	""" ******************************************************** """
	"""														  """
	""" MISC / WINDOWS BEHAVIOR								  """
	"""														  """
	"""														  """
	""" ******************************************************** """


	def start_systray(self):
		if self.statusicon is None:
			self.statusicon = gtk.StatusIcon()
			self.statusicon.set_from_file("/usr/share/pixmaps/virtualbricks.png")
			self.statusicon.set_tooltip("VirtualBricks Visible")
			self.statusicon.connect('activate', self.on_systray_menu_toggle)
			systray_menu = self.gladefile.get_widget("systray_menu")
			self.statusicon.connect('popup-menu', self.systray_menu_popup, systray_menu)

		if not self.statusicon.get_visible():
			self.statusicon.set_visible(True)

	def systray_menu_popup(self, widget, button, time, data = None):
		if button == 3 and data:
			data.show_all()
			data.popup(None, None, None, 3, time)

	def stop_systray(self):
		if self.statusicon is not None and self.statusicon.get_visible():
			self.statusicon.set_visible(False)
			self.statusicon = None

	def systray_blinking(self, args=None, disable=False):
		if self.statusicon is None or not self.statusicon.get_visible():
			return

		if disable:
			self.statusicon.set_blinking(False)
		elif not self.statusicon.get_blinking():
			self.statusicon.set_blinking(True)

	def delete_event(self,window,event):
		#don't delete; hide instead
		if self.config.systray and self.statusicon is not None:
			self.gladefile.get_widget("main_win").hide_on_delete()
			self.statusicon.set_tooltip("VirtualBricks Hidden")
		else:
			self.quit()
		return True

	def curtain_is_down(self):
		self.debug(self.curtain.get_position())
		return (self.curtain.get_position()>660)

	def curtain_down(self):
		self.curtain.set_position(99999)
		self.gladefile.get_widget('label_showhidesettings').set_text(_('Show Settings'))

	def curtain_up(self):
		notebook=self.gladefile.get_widget('main_notebook')

		if (notebook.get_current_page() != 1) and (notebook.get_current_page() != 0):
			return
		self.debug("Old position: %d", self.curtain.get_position())
		self.gladefile.get_widget('box_vmconfig').hide()
		self.gladefile.get_widget('box_tapconfig').hide()
		self.gladefile.get_widget('box_tunnellconfig').hide()
		self.gladefile.get_widget('box_tunnelcconfig').hide()
		self.gladefile.get_widget('box_wireconfig').hide()
		self.gladefile.get_widget('box_wirefilterconfig').hide()
		self.gladefile.get_widget('box_switchconfig').hide()
		self.gladefile.get_widget('box_captureconfig').hide()
		self.gladefile.get_widget('box_eventconfig').hide()
		self.gladefile.get_widget('box_switchwrapperconfig').hide()

		wg = self.curtain
		notebook=self.gladefile.get_widget('main_notebook')

		if notebook.get_current_page() == 1:
			if self.event_selected is None:
				return
			if self.event_selected.get_type() == 'Event':
				self.debug("event config")
				ww = self.gladefile.get_widget('box_eventconfig')
				wg.set_position(430)
				self.config_event_prepare()
				ww.show_all()
				self.gladefile.get_widget("wait_label").hide()
				self.gladefile.get_widget('label_showhidesettings').set_text(_('Hide Settings'))
			return

		if self.maintree.get_selection() is None:
			return

		if self.maintree.get_selection().get_type() == 'Switch':
			self.debug("switch config")
			ww = self.gladefile.get_widget('box_switchconfig')
			wg.set_position(575)
		elif self.maintree.get_selection().get_type() == 'Qemu':
			self.debug("qemu config")
			ww = self.gladefile.get_widget('box_vmconfig')
			wg.set_position(245)
		elif self.maintree.get_selection().get_type() == 'Tap':
			self.debug("tap config")
			ww = self.gladefile.get_widget('box_tapconfig')
			wg.set_position(500)
		elif self.maintree.get_selection().get_type() == 'Wire':
			self.debug("wire config")
			ww = self.gladefile.get_widget('box_wireconfig')
			wg.set_position(606)
		elif self.maintree.get_selection().get_type() == 'Wirefilter':
			self.debug("wirefilter config")
			ww = self.gladefile.get_widget('box_wirefilterconfig')
			wg.set_position(344)
		elif self.maintree.get_selection().get_type() == 'TunnelConnect':
			self.debug("tunnelc config")
			ww = self.gladefile.get_widget('box_tunnelcconfig')
			wg.set_position(500)
		elif self.maintree.get_selection().get_type() == 'TunnelListen':
			self.debug("tunnell config")
			ww = self.gladefile.get_widget('box_tunnellconfig')
			wg.set_position(524)
		elif self.maintree.get_selection().get_type() == 'Capture':
			self.debug("capture config")
			ww = self.gladefile.get_widget('box_captureconfig')
			wg.set_position(500)
		elif self.maintree.get_selection().get_type() == 'SwitchWrapper':
			self.debug("switchwrapper config")
			ww = self.gladefile.get_widget('box_switchwrapperconfig')
			wg.set_position(580)

		self.config_brick_prepare()
		ww.show_all()
		self.gladefile.get_widget("wait_label").hide()
		self.gladefile.get_widget('label_showhidesettings').set_text(_('Hide Settings'))

	def get_treeselected(self, tree, store, pthinfo, c):
		if pthinfo is not None:
			path, col, cellx, celly = pthinfo
			tree.grab_focus()
			tree.set_cursor(path, col, 0)
			iter = store.model.get_iter(path)
			name = store.model.get_value(iter, c)
			self.config_last_iter = iter
			return name
		return ""

	def get_treeselected_name(self, t, s, p):
		return self.get_treeselected(t, s, p, 3)

	def get_treeselected_type(self, t, s, p):
		return self.get_treeselected(t, s, p, 2)

	def quit(self, args=None):
		self.info("GUI: Goodbye!")
		self.brickfactory.disconnect(self._engine_closed)
		self.brickfactory.quit()
		sys.exit(0)

	def quit_from_commandline(self, args=None):
		self.info("GUI: Goodbye!")
		gtk.main_quit()
		#sys.exit(0)

	def get_widgets(self, l):
		r = dict()
		for i in l:
			r[i] = self.gladefile.get_widget(i)
			r[i].hide()
		return r


	def qemu_eth_model(self):
		res = dict()
		for k in [ "rtl8139",
			"e1000",
			"virtio",
			"i82551",
			"i82557b",
			"i82559er",
			"ne2k_pci",
			"pcnet",
			"ne2k_isa"]:
			res[k]=k
		return res

	def widgetnames(self):
		return ['main_win',
		'filechooserdialog_openimage',
		'dialog_settings',
		'dialog_bookmarks',
		'menu_popup_bookmarks',
		'dialog_about1',
		'dialog_create_image',
		'dialog_messages',
		'menu_popup_imagelist',
		'dialog_jobmonitor',
		'menu_popup_joblist',
		'menu_popup_usbhost',
		'menu_popup_usbguest',
		'menu_popup_volumes',
		'dialog_newnetcard',
		'dialog_confirm_action',
		'dialog_new_redirect',
		'ifconfig_win',
		'dialog_newbrick',
		'dialog_newevent',
		'menu_brickactions',
		'menu_eventactions',
		'dialog_confirm',
		'menu_popup_remotehosts',
		'dialog_remote_password',
		'dialog_diskimage',
		'dialog_usbdev'
		]
	def sockscombo_names(self):
		return [
		'sockscombo_vmethernet',
		'sockscombo_tap',
		'sockscombo_capture',
		'sockscombo_wire0',
		'sockscombo_wire1',
		'sockscombo_wirefilter0',
		'sockscombo_wirefilter1',
		'sockscombo_tunnell',
		'sockscombo_tunnelc'
		]

	def show_window(self, name):
		for w in self.widg.keys():
			if name == w or w == 'main_win':
				if w.startswith('menu'):
					self.widg[w].popup(None, None, None, 3, 0)
				else:
					self.widg[w].show_all()
			elif not name.startswith('menu'):
				self.widg[w].hide()

	def critical(self, text, *args, **kwargs):
		exc_type, exc_value, exc_traceback = sys.exc_info()
		traceback = format_exception(exc_type, exc_value, exc_traceback)
		Logger.critical(self, text, *args, **kwargs)
		for line in traceback:
			Logger.critical(self, line.rstrip('\n'))
		sys.exit(1)

	def error(self, text, *args, **kwargs):
		Logger.error(self, text, *args, **kwargs)
		if args:
			text = text % args

		#gtk.gdk.threads_enter()
		#try:
		self.show_error(text)
		#finally:
		#	gtk.gdk.threads_leave()

	def show_error(self, text):
		def on_response(widget, response_id=None, data=None):
			gtk.gdk.threads_leave()
			widget.destroy()
			return True

		parent = self.gladefile.get_widget("main_win")
		dlg = gtk.MessageDialog(parent=parent, flags=gtk.DIALOG_MODAL,
			type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_CLOSE,
			message_format=None)
		dlg.set_property('message-type', gtk.MESSAGE_ERROR)
		dlg.set_property('text', text)
		dlg.connect("response", on_response)
		dlg.run()

	def pixbuf_scaled(self, filename):
		if filename is None or filename == "":
				return None
		pixbuf=gtk.gdk.pixbuf_new_from_file(filename)
		width=pixbuf.get_width()
		height=pixbuf.get_height()
		if width<=height:
				new_height=48*height/width
				new_width=48
		else:
				new_height=48
				new_width=48*width/height
		pixbuf = pixbuf.scale_simple(new_width, new_height, gtk.gdk.INTERP_BILINEAR)
		return pixbuf


	""" ******************************************************** """
	"""														  """
	""" EVENTS / SIGNALS										 """
	"""														  """
	"""														  """
	""" ******************************************************** """

	def on_bricks_keypressed(self, widget, event="", data=""):
		if event.keyval == 65288 or event.keyval == 65535:
			self.on_brick_delete()


	def on_systray_menu_toggle(self, widget=None, data=""):
		if self.statusicon.get_blinking():
			self.systray_blinking(None, True)
			return

		if not self.gladefile.get_widget("main_win").get_visible():
			self.gladefile.get_widget("main_win").show_all()
			self.statusicon.set_tooltip("the window is visible")
		else:
			self.gladefile.get_widget("main_win").hide()

	def on_systray_exit(self, widget=None, data=""):
		self.quit()

	def on_windown_destroy(self, widget=None, data=""):
		widget.hide()
		return True

	def confirm(self, message):
		dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_INFO, gtk.BUTTONS_YES_NO, message)
		response = dialog.run()
		dialog.destroy()

		if response == gtk.RESPONSE_YES:
			return True
		elif response == gtk.RESPONSE_NO:
			return False

	def ask_confirm(self, text, on_yes=None, on_no=None, arg=None):
		self.curtain_down()
		self.gladefile.get_widget('lbl_confirm').set_text(text)
		self.on_confirm_response_yes = on_yes
		self.on_confirm_response_no = on_no
		self.on_confirm_response_arg = arg
		self.gladefile.get_widget('dialog_confirm').show_all()

	def on_newbrick_cancel(self, widget=None, data=""):
		self.curtain_down()
		self.show_window('')

	def selected_type(self):
		for ntype in ['Switch','Tap','Wire','Wirefilter','TunnelConnect','TunnelListen','Qemu','Capture', 'SwitchWrapper']:
			if self.gladefile.get_widget('typebutton_'+ntype).get_active():
				return ntype
		return 'Switch'

	def selected_event_type(self):
		for ntype in ['BrickStart','BrickStop','BrickConfig','ShellCommand','EventsCollation']:
			if self.gladefile.get_widget('typebutton_'+ntype).get_active():
				return ntype
		return 'ShellCommand'

	def on_newbrick_ok(self, widget=None, data=""):
		self.show_window('')
		self.curtain_down()
		name = self.gladefile.get_widget('text_newbrickname').get_text()
		ntype = self.selected_type()
		runremote = self.gladefile.get_widget('check_newbrick_runremote').get_active()
		if runremote:
			remotehost = self.gladefile.get_widget('text_newbrick_runremote').get_text()
			try:
				self.brickfactory.newbrick('remote', ntype, name, remotehost, "")
			except InvalidName:
				self.error(_("Cannot create brick: Invalid name."))
			else:
				self.debug("Created successfully")
		else:
			try:
				self.brickfactory.newbrick(ntype, name)
			except InvalidName:
				self.error(_("Cannot create brick: Invalid name."))
			else:
				self.debug("Created successfully")


	def on_newevent_cancel(self, widget=None, data=""):
		self.curtain_down()
		self.show_window('')

	def on_newevent_ok(self, widget=None, data=""):

		eventname = self.gladefile.get_widget('text_neweventname').get_text()
		if eventname == '':
			return

		validname = ValidName(eventname)
		if validname is None:
			self.error(_("The name \"")+eventname+_("\" has forbidden format."))
			return
		elif validname != eventname:
			self.gladefile.get_widget('text_neweventname').set_text(validname)
			self.error(_("The name \"")+eventname+_("\" has been adapted to \"")+validname+"\".")
			eventname = validname

		if not self.brickfactory.isNameFree(eventname):
			self.error(_("An event named \"")+eventname+_("\" already exist."))
			return

		self.show_window('')
		self.curtain_down()

		ntype = self.selected_event_type()

		try:
			if ntype == 'ShellCommand':

				self.shcommandsmodel = None
				self.shcommandsmodel = gtk.ListStore (str, bool)
				iter = self.shcommandsmodel.append (["new switch myswitch", False])
				iter = self.shcommandsmodel.append (["", False])

				actions = self.gladefile.get_widget('treeview_event_actions')
				actions.set_model(self.shcommandsmodel)

				columns = (COL_COMMAND, COL_BOOL) = range(2)
				cell = gtk.CellRendererText ()
				column_command = gtk.TreeViewColumn (_("Command"), cell, text = COL_COMMAND)
				cell.set_property('editable', True)
				cell.connect('edited', self.edited_callback, (self.shcommandsmodel, COL_COMMAND))
				cell = gtk.CellRendererToggle ()
				column_bool = gtk.TreeViewColumn (_("Host shell command"), cell, active = COL_BOOL)
				cell.set_property('activatable', True)
				cell.connect('toggled', self.toggled_callback, (self.shcommandsmodel, COL_BOOL))

				# Clear columns
				for c in actions.get_columns():
					actions.remove_column(c)

				# Add columns
				actions.append_column (column_command)
				actions.append_column (column_bool)

				self.gladefile.get_widget('dialog_shellcommand').show_all()

			elif ntype in ['BrickStart', 'BrickStop', 'EventsCollation']:

				columns = (COL_ICON, COL_TYPE, COL_NAME, COL_CONFIG) = range(4)

				availbricks = self.gladefile.get_widget('bricks_available_treeview')
				addedbricks = self.gladefile.get_widget('bricks_added_treeview')

				self.availmodel = gtk.ListStore (gtk.gdk.Pixbuf, str, str, str)
				self.addedmodel = gtk.ListStore (gtk.gdk.Pixbuf, str, str, str)

				if ntype == 'EventsCollation':
					container = self.brickfactory.events
				else:
					container = self.brickfactory.bricks

				for brick in container:
					parameters = brick.get_parameters()
					if len(parameters) > 30:
						parameters = "%s..." % parameters[:30]
					iter = self.availmodel.append(
						[gtk.gdk.pixbuf_new_from_file_at_size(brick.icon.base, 48, 48),
						brick.get_type(), brick.name, parameters])

				availbricks.set_model(self.availmodel)
				addedbricks.set_model(self.addedmodel)

				cell = gtk.CellRendererPixbuf ()
				column_icon = gtk.TreeViewColumn (_("Icon"), cell, pixbuf = COL_ICON)
				cell = gtk.CellRendererText ()
				column_type = gtk.TreeViewColumn (_("Type"), cell, text = COL_TYPE)
				cell = gtk.CellRendererText ()
				column_name = gtk.TreeViewColumn (_("Name"), cell, text = COL_NAME)
				cell = gtk.CellRendererText ()
				column_config = gtk.TreeViewColumn (_("Parameters"), cell, text = COL_CONFIG)

				# Clear columns
				for c in availbricks.get_columns():
					availbricks.remove_column(c)

				for c in addedbricks.get_columns():
					addedbricks.remove_column(c)

				# Add columns
				availbricks.append_column (column_icon)
				availbricks.append_column (column_type)
				availbricks.append_column (column_name)
				availbricks.append_column (column_config)

				cell = gtk.CellRendererPixbuf ()
				column_icon = gtk.TreeViewColumn (_("Icon"), cell, pixbuf = COL_ICON)
				cell = gtk.CellRendererText ()
				column_type = gtk.TreeViewColumn (_("Type"), cell, text = COL_TYPE)
				cell = gtk.CellRendererText ()
				column_name = gtk.TreeViewColumn (_("Name"), cell, text = COL_NAME)
				cell = gtk.CellRendererText ()
				column_config = gtk.TreeViewColumn (_("Parameters"), cell, text = COL_CONFIG)

				addedbricks.append_column (column_icon)
				addedbricks.append_column (column_type)
				addedbricks.append_column (column_name)
				addedbricks.append_column (column_config)

				if(ntype == 'BrickStart'):
					self.gladefile.\
				get_widget('dialog_event_bricks_select').\
				set_title(_("Bricks to add to the event to be started"))
				elif(ntype == 'BrickStop'):
					self.gladefile.\
				get_widget('dialog_event_bricks_select').\
				set_title(_("Bricks to add to the event to be stopped"))
				else:
					self.gladefile.\
				get_widget('dialog_event_bricks_select').\
				set_title(_("Events to add to the event to be started"))

				self.gladefile.get_widget('dialog_event_bricks_select').show_all()

		except InvalidName:
			self.error(_("Cannot create event: Invalid name."))

	def edited_callback (self, cell, rowpath, new_text, user_data):
		model, col_id = user_data
		model[rowpath][col_id] = new_text
		iter = self.shcommandsmodel.get_iter_first()
		while iter:
			last=iter
			iter=self.shcommandsmodel.iter_next(iter)
		if self.shcommandsmodel.get_value(last, col_id) != '':
			self.shcommandsmodel.append (["", False])
		return

	def toggled_callback (self, cell, rowpath, user_data):
		model, col_id = user_data
		model[rowpath][col_id] = not model[rowpath][col_id]
		return

	def on_event_brick_select_add_clicked(self, widget=None, data=""):
		availbricks = self.gladefile.get_widget('bricks_available_treeview')
		model, iter =availbricks.get_selection().get_selected()
		if not iter:
			return
		self.addedmodel.append(model[iter])
		model.remove(iter)

	def on_event_brick_select_remove_clicked(self, widget=None, data=""):
		addedbricks = self.gladefile.get_widget('bricks_added_treeview')
		model, iter = addedbricks.get_selection().get_selected()
		if not iter:
			return
		self.availmodel.append(model[iter])
		model.remove(iter)

	def on_config_cancel(self, widget=None, data=""):
		self.config_brick_cancel()
		self.curtain_down()

	def on_config_ok(self, widget=None, data=""):
		self.gladefile.get_widget("wait_label").show_now()
		self.config_brick_confirm()
		self.curtain_down()

	def on_config_save(self, widget=None, data=""):
		self.config_brick_confirm()

	def set_sensitivegroup(self,l):
		for i in l:
			w = self.gladefile.get_widget(i)
			w.set_sensitive(True)

	def set_nonsensitivegroup(self,l):
		for i in l:
			w = self.gladefile.get_widget(i)
			w.set_sensitive(False)

	def on_symm_toggle(self, widget=None, data=""):
		base_name = widget.name.replace("cfg_","").replace("symm_check","")
		text = self.gladefile.get_widget('cfg_' + base_name + '_text')
		text_LR = self.gladefile.get_widget('cfg_' + base_name + 'LR_text')
		text_RL = self.gladefile.get_widget('cfg_' + base_name + 'RL_text')
		text_jitter = self.gladefile.get_widget('cfg_' + base_name + 'J_text')
		text_jitter_LR = self.gladefile.get_widget('cfg_' + base_name + 'LRJ_text')
		text_jitter_RL = self.gladefile.get_widget('cfg_' + base_name + 'RLJ_text')
		frame = self.gladefile.get_widget(base_name + '_frame')
		frame_LR = self.gladefile.get_widget(base_name + 'LR_frame')
		frame_RL = self.gladefile.get_widget(base_name + 'RL_frame')
		if widget.get_active():
			frame_LR.set_sensitive(False)
			text_LR.set_text("")
			if text_jitter_LR: text_jitter_LR.set_text("")
			frame_RL.set_sensitive(False)
			text_RL.set_text("")
			if text_jitter_RL: text_jitter_RL.set_text("")
			frame.set_sensitive(True)
			text.set_text("")
			if text_jitter: text_jitter.set_text("")
		else:
			frame.set_sensitive(False)
			text.set_text("")
			if text_jitter: text_jitter.set_text("")
			frame_LR.set_sensitive(True)
			frame_RL.set_sensitive(True)

	def on_wf_speed_checkbox_toggle(self, widget=None, data=""):
		frame = self.gladefile.get_widget('Wirefilter_speed_frame')
		frame_GP = self.gladefile.get_widget('Speed_General_Parameters_Frame')
		frame_LR = self.gladefile.get_widget('Wirefilter_speedLR_frame')
		frame_RL = self.gladefile.get_widget('Wirefilter_speedRL_frame')
		if not widget.get_active():
			text = self.gladefile.get_widget('cfg_Wirefilter_speed_text')
			text_LR = self.gladefile.get_widget('cfg_Wirefilter_speedLR_text')
			text_RL = self.gladefile.get_widget('cfg_Wirefilter_speedRL_text')
			text_jitter = self.gladefile.get_widget('cfg_Wirefilter_speedJ_text')
			text_jitter_LR = self.gladefile.get_widget('cfg_Wirefilter_speedLRJ_text')
			text_jitter_RL = self.gladefile.get_widget('cfg_Wirefilter_speedRLJ_text')
			text.set_text("")
			text_LR.set_text("")
			text_RL.set_text("")
			text_jitter.set_text("")
			text_jitter_LR.set_text("")
			text_jitter_RL.set_text("")
			frame.set_sensitive(False)
			frame_LR.set_sensitive(False)
			frame_RL.set_sensitive(False)
			frame_GP.set_sensitive(False)
		else:
			frame_GP.set_sensitive(True)
			self.on_symm_toggle(self.gladefile.get_widget('cfg_Wirefilter_speedsymm_check'))

	def on_percent_insert_text(self, editable, new_text, new_text_length, position):
		text = editable.get_text() + new_text
		if not re.match("^(?:[1-9]+\.?[0-9]{0,3}|0\.[0-9]{0,3}|0)$", text ):
			editable.emit_stop_by_name('insert-text')

	def on_non_negative_insert_text(self, editable, new_text, new_text_length, position):
		import re
		text = editable.get_text() + new_text
		if not re.match("^(?:[1-9][0-9]*|0)$", text ):
			editable.emit_stop_by_name('insert-text')

	def on_Wirefilter_help_button_clicked(self, widget=None, data=""):
		paramname = widget.name.replace("Wirefilter_","").replace("_help_button","")
		f_name = getattr(self, paramname + "_help")
		if not f_name: return
		text = self.gladefile.get_widget('textview_messages')
		window = self.gladefile.get_widget('dialog_messages')
		window.set_title(_("Help for parameter:") + " " + paramname)
		text.get_buffer().set_text(f_name())
		window.show_all()

	#Do NOT change string layout please
	jitter_str = " " + _("""\nJitter is the variation from the \
base value. Jitter 10 percent for a \
base value of 100 means the final value goes from 90 to 110. \
The distribution can be Uniform or Gaussian normal \
(more than 98% of the values are inside the limits).""")

	def bandwidth_help(self):
		#Do NOT change string layout please
		return _("\t\t\tCHANNEL BANDWIDTH\n\n\
Sender is not prevented \
from sending packets, delivery is delayed to limit the bandwidth \
to the desired value (like a bottleneck along the path).") + self.jitter_str

	def speed_help(self):
		#Do NOT change string layout please
		return _("\t\t\tINTERFACE SPEED\n\n\
Input is blocked for the tramission time of the packet, thus the \
sender is prevented from sending too fast.\n\
This feature can be confusing, consider using bandwidth.") + self.jitter_str

	def delay_help(self):
		#Do NOT change string layout please
		return _("\t\t\tDELAY\n\n\
Extra delay (in milliseconds). This delay is added to the real \
communication delay. Packets are temporarily stored and resent \
after the delay.") + self.jitter_str

	def chanbufsize_help(self):
		#Do NOT change string layout please
		return _("\t\t\tCHANNEL BUFFER SIZE\n\n\
Maximum size of the packet \
queue. Exceeding packets are discarded.") + self.jitter_str

	def loss_help(self):
		#Do NOT change string layout please
		return _("\t\t\tPACKET LOSS\n\n\
Percentage of loss as a floating point number.") + self.jitter_str

	def dup_help(self):
		#Do NOT change string layout please
		return _("\t\t\tPACKET DUPLICATION\n\n\
Percentage of dup packet. Do not use dup factor 100% because it \
means that each packet is sent infinite times.") + self.jitter_str

	def noise_help(self):
		#Do NOT change string layout please
		return _("\t\t\tNOISE\n\n\
Number of bits damaged/one megabyte (megabit).") + self.jitter_str

	def lostburst_help(self):
		#Do NOT change string layout please
		return _("\t\t\tLOST BURST\n\n\
When this is not zero, wirefilter uses the Gilbert model for \
bursty errors. This is the mean length of lost packet bursts.") + self.jitter_str

	def mtu_help(self):
		#Do NOT change string layout please
		return _("\t\t\tMTU: MAXIMUM TRANSMISSION UNIT\n\n\
Packets longer than specified size are discarded.")

	def on_item_quit_activate(self, widget=None, data=""):
		self.quit()

	def on_item_settings_activate(self, widget=None, data=""):
		self.gladefile.get_widget('filechooserbutton_bricksdirectory').set_current_folder(self.config.get('bricksdirectory'))
		self.gladefile.get_widget('filechooserbutton_qemupath').set_current_folder(self.config.get('qemupath'))
		self.gladefile.get_widget('filechooserbutton_vdepath').set_current_folder(self.config.get('vdepath'))
		self.gladefile.get_widget('filechooserbutton_baseimages').set_current_folder(self.config.get('baseimages'))

		if self.config.kvm:
			self.gladefile.get_widget('check_kvm').set_active(True)
		else:
			self.gladefile.get_widget('check_kvm').set_active(False)

		if self.config.ksm:
			self.gladefile.get_widget('check_ksm').set_active(True)
		else:
			self.gladefile.get_widget('check_ksm').set_active(False)

		if self.config.kqemu:
			self.gladefile.get_widget('check_kqemu').set_active(True)
		else:
			self.gladefile.get_widget('check_kqemu').set_active(False)

		if self.config.femaleplugs:
			self.gladefile.get_widget('check_femaleplugs').set_active(True)
		else:
			self.gladefile.get_widget('check_femaleplugs').set_active(False)

		if self.config.erroronloop:
			self.gladefile.get_widget('check_erroronloop').set_active(True)
		else:
			self.gladefile.get_widget('check_erroronloop').set_active(False)

		if self.config.python:
			self.gladefile.get_widget('check_python').set_active(True)
		else:
			self.gladefile.get_widget('check_python').set_active(False)

		if self.config.systray:
			self.gladefile.get_widget('check_systray').set_active(True)
		else:
			self.gladefile.get_widget('check_systray').set_active(False)

		self.gladefile.get_widget('entry_term').set_text(self.config.get('term'))
		self.gladefile.get_widget('entry_sudo').set_text(self.config.get('sudo'))
		self.curtain_down()
		self.show_window('dialog_settings')

	def on_item_settings_autoshow_activate(self, widget=None, data=""):
		raise NotImplementedError()

	def on_item_settings_autohide_activate(self, widget=None, data=""):
		raise NotImplementedError()

	def on_item_about_activate(self, widget=None, data=""):
		self.show_window('dialog_about1')
		self.curtain_down()

	def on_toolbutton_launchxterm_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_toolbutton_start_all_clicked(self, widget=None, data=""):
		self.curtain_down()
		for b in self.brickfactory.bricks:
			if b.proc is None:
				b.poweron()

	def on_toolbutton_stop_all_clicked(self, widget=None, data=""):
		self.curtain_down()
		for b in self.brickfactory.bricks:
			if b.proc is not None:
				b.poweroff()

	def on_toolbutton_start_all_events_clicked(self, widget=None, data=""):
		self.curtain_down()
		for e in self.brickfactory.events:
			if not e.active:
				e.poweron()

	def on_toolbutton_stop_all_events_clicked(self, widget=None, data=""):
		self.curtain_down()
		for e in self.brickfactory.events:
			if e.active:
				e.poweroff()

	def on_mainwindow_dropaction(self, widget, drag_context, x, y, selection_data, info, timestamp):
		pth = self.maintree.get_selection_at(x,y)
		dropbrick = self.maintree.get_selection(pth)
		drop_info = self.maintree.get_info_at(x,y)
		if drop_info:
			pth, pos = drop_info

		if pos == gtk.TREE_VIEW_DROP_BEFORE:
			self.debug('dropped before')
			drag_context.finish(False, False, timestamp)
			return False

		if pos == gtk.TREE_VIEW_DROP_AFTER:
			drag_context.finish(False, False, timestamp)
			self.debug('dropped after')
			return False

		if dropbrick and (dropbrick != self.Dragging):
			self.debug("drag&drop: %s onto %s", self.Dragging.name, dropbrick.name)
			res = False
			if len(dropbrick.socks) > 0:
				res = self.Dragging.connect(dropbrick.socks[0])
			elif len(self.Dragging.socks) > 0:
				res = dropbrick.connect(self.Dragging.socks[0])

			if res:
				drag_context.finish(True, False, timestamp)
			else:
				drag_context.finish(False, False, timestamp)
		else:
			drag_context.finish(False, False, timestamp)
		self.Dragging = None

	def show_brickactions(self):
		if self.maintree.get_selection().get_type() == "Qemu":
			self.set_sensitivegroup(['vmresume'])
		else:
			self.set_nonsensitivegroup(['vmresume'])

		self.gladefile.get_widget("brickaction_name").set_label(self.maintree.get_selection().name)
		self.show_window('menu_brickactions')

	def show_eventactions(self):
		self.gladefile.get_widget("eventaction_name").set_label(self.event_selected.name)
		self.show_window('menu_eventactions')

	def on_treeview_bookmarks_button_release_event(self, widget=None, event=None, data=""):
		b = self.maintree.get_selection()
		if b is None:
			return

		self.curtain_down()
		tree = self.gladefile.get_widget('treeview_bookmarks');
		path = tree.get_cursor()[0]
		if path is None:
			return
		self.Dragging = b
		if event.button == 3:
			self.show_brickactions()

	def on_treeview_events_bookmarks_button_release_event(self, widget=None, event=None, data=""):
		self.event_selected = self.get_event_selected_bookmark()
		if self.event_selected is None:
			return

		self.curtain_down()
		tree = self.gladefile.get_widget('treeview_events_bookmarks');
		path = tree.get_cursor()[0]
		#print "on_treeview_events_bookmarks_button_release_event"
		if path is None:
			#print "nothing selected!"
			return

		iter = tree.get_model().get_iter(path)
		name = tree.get_model().get_value(iter, EventsModel.EVENT_IDX).name
		self.Dragging = self.brickfactory.geteventbyname(name)
		if event.button == 3:
			self.show_eventactions()

	def on_treeview_bookmarks_cursor_changed(self, widget=None, event=None, data=""):
		self.curtain_down()

	def on_treeview_bookmarks_row_activated_event(self, widget=None, event=None, data=""):
		self.on_brick_startstop(widget, event, data)
		self.curtain_down()

	def on_treeview_events_bookmarks_row_activated_event(self, widget=None, event=None, data=""):
		self.on_event_startstop(widget, event, data)
		self.curtain_down()

	def on_focus_out(self, widget=None, event=None , data=""):
		self.curtain_down()

	def on_brick_startstop(self, widget=None, event=None, data=""):
		self.curtain_down()
		self.user_wait_action(self.startstop_brick, self.maintree.get_selection())

	def on_event_startstop(self, widget=None, event=None, data=""):
		self.curtain_down()
		self.user_wait_action(self.event_startstop_brick, self.event_selected)

	def event_startstop_brick(self, e):
		if e.get_type() == 'Event':
			if e.active:
				self.debug( "Power OFF" )
				e.poweroff()
			else:
				self.debug ( "Power ON" )
				e.poweron()
			return

	def startstop_brick(self, b):
		if b.proc is not None:
			b.poweroff()
		else:
			if b.get_type() == "Qemu":
				b.cfg.loadvm = '' #prevent restore from saved state
			try:
				b.poweron()
			except BadConfig:
				b.gui_changed=True
				gtk.gdk.threads_enter()
				self.error(_("Cannot start '%s': not configured"),
					b.name)
				gtk.gdk.threads_leave()
			except NotConnected:
				gtk.gdk.threads_enter()
				self.error(_("Cannot start '%s': not connected"),
					b.name)
				gtk.gdk.threads_leave()
			except Linkloop:
				if self.config.erroronloop:
					gtk.gdk.threads_enter()
					self.error(_("Loop link detected: aborting operation. If you want to start "
						"a looped network, disable the check loop feature in the general "
						"settings"))
					gtk.gdk.threads_leave()
					b.poweroff()
			except DiskLocked:
				b.gui_changed=True
				gtk.gdk.threads_enter()
				self.error(_("Disk used by the VM is locked by another "
					"machine"))
				gtk.gdk.threads_leave()
				b.poweroff()

	def on_treeview_bootimages_button_press_event(self, widget=None, data=""):
		raise NotImplementedError()

	def on_treeview_bootimages_cursor_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_treeview_bootimages_row_activated_event(self, widget=None, data=""):
		raise NotImplementedError()

	def getremotehost(self, addr):
		for r in self.brickfactory.remote_hosts:
			if r.addr[0]+":"+str(r.addr[1]) == addr:
				return r
		return None

	def on_treeview_remotehosts_button_release_event(self, widget=None, event=None, data=""):
		tree = self.gladefile.get_widget('treeview_remotehosts');
		store = self.remote_hosts_tree
		x = int(event.x)
		y = int(event.y)
		pthinfo = tree.get_path_at_pos(x, y)
		addr = self.get_treeselected(tree, store, pthinfo, 1)
		self.remotehost_selected = self.getremotehost(addr)
		if not self.remotehost_selected:
			return
		if event.button == 3:
			self.gladefile.get_widget('popupcheck_autoconnect').set_active(self.remotehost_selected.autoconnect)
			self.show_window('menu_popup_remotehosts')

	def on_treeview_remotehosts_button_press_event(self, widget=None, event=None, data=""):
		tree = self.gladefile.get_widget('treeview_remotehosts');
		store = self.remote_hosts_tree
		x = int(event.x)
		y = int(event.y)
		pthinfo = tree.get_path_at_pos(x, y)
		addr = self.get_treeselected(tree, store, pthinfo, 1)
		self.remotehost_selected = self.getremotehost(addr)
		if not self.remotehost_selected:
			return
		elif event.button == 1 and event.type == gtk.gdk._2BUTTON_PRESS:
			if self.remotehost_selected.connected:
				self.user_wait_action(self.remotehost_selected.disconnect)
			else:
				conn_ok, msg = self.remotehost_selected.connect()
				if not conn_ok:
					self.error("Error connecting to remote host %s: %s" % (self.remotehost_selected.addr[0], msg))

	def on_treeview_joblist_button_press_event(self, widget=None, event=None, data=""):
		tree = self.gladefile.get_widget('treeview_joblist');
		store = self.running_bricks
		x = int(event.x)
		y = int(event.y)
		pthinfo = tree.get_path_at_pos(x, y)
		name = self.get_treeselected_name(tree, store, pthinfo)
		if event.button == 3:
			self.joblist_selected = self.brickfactory.getbrickbyname(name)
			if not self.joblist_selected:
				return

			if self.joblist_selected.get_type()=="Qemu":
				self.set_sensitivegroup(['vmsuspend', 'vmpoweroff', 'vmhardreset'])
			else:
				self.set_nonsensitivegroup(['vmsuspend', 'vmpoweroff', 'vmhardreset'])

			self.show_window('menu_popup_joblist')

	def on_treeview_joblist_row_activated_event(self, widget=None, data=""):
		raise NotImplementedError()

	def on_button_togglesettings_clicked(self, widget=None, data=""):
		if self.curtain_is_down():
			self.curtain_up()
			self.debug("up")
		else:
			self.curtain_down()
			self.debug("down")

	def on_dialog_settings_delete_event(self, widget=None, event=None, data=""):
		"""we could use deletable property but deletable is only available in
		GTK+ 2.10 and above"""
		widget.hide()
		return True

	def on_button_newimage_close_clicked(self, widget=None, data=""):
		self.gladefile.get_widget('dialog_create_image').hide()
		return True


	def on_dialog_settings_response(self, widget=None, response=0, data=""):
		if response == gtk.RESPONSE_CANCEL:
			widget.hide()
			return

		if response in [gtk.RESPONSE_APPLY, gtk.RESPONSE_OK]:
			self.debug("Apply settings...")
			for k in ['bricksdirectory', 'qemupath', 'vdepath', 'baseimages']:
				self.config.set(k, self.gladefile.get_widget('filechooserbutton_'+k).get_filename())

			if self.gladefile.get_widget('check_kvm').get_active():
				self.config.set("kvm", True)
			else:
				self.config.set("kvm", False)

			if self.gladefile.get_widget('check_ksm').get_active():
				self.config.set("ksm", True)
				try:
					self.config.check_ksm(True)
				except:
					pass
			else:
				try:
					self.config.check_ksm(False)
				except:
					pass
				self.config.set("ksm", False)

			if self.gladefile.get_widget('check_kqemu').get_active():
				self.config.set("kqemu", True)
			else:
				self.config.set("kqemu", False)

			if self.gladefile.get_widget('check_python').get_active():
				self.config.set("python", True)
			else:
				self.config.set("python", False)

			if self.gladefile.get_widget('check_femaleplugs').get_active():
				self.config.set("femaleplugs", True)
			else:
				self.config.set("femaleplugs", False)

			if self.gladefile.get_widget('check_erroronloop').get_active():
				self.config.set("erroronloop", True)
			else:
				self.config.set("erroronloop", False)

			if self.gladefile.get_widget('check_systray').get_active():
				self.config.set('systray', True)
				self.start_systray()
			else:
				self.config.set('systray', False)
				self.stop_systray()

			self.config.set("term", self.gladefile.get_widget('entry_term').get_text())
			self.config.set("sudo", self.gladefile.get_widget('entry_sudo').get_text())

			self.config.store()

			if response == gtk.RESPONSE_OK:
				widget.hide()

	def on_dialog_confirm_response(self, widget=None, response=0, data=""):
		widget.hide()
		if (response == 1):
			if (self.on_confirm_response_yes):
				self.on_confirm_response_yes(self.on_confirm_response_arg)
		elif (response == 0):
			if (self.on_confirm_response_no):
				self.on_confirm_response_no(self.on_confirm_response_arg)

	def on_dialog_attach_event_response(self, widget=None, response=0, data=""):
		widget.hide()
		if (response == 1):
			startevents = self.gladefile.get_widget('start_events_avail_treeview')
			stopevents = self.gladefile.get_widget('stop_events_avail_treeview')
			model, iter = startevents.get_selection().get_selected()
			if iter:
				self.maintree.get_selection().cfg.pon_vbevent = model[iter][2]
			else:
				self.maintree.get_selection().cfg.pon_vbevent = ""
			model, iter = stopevents.get_selection().get_selected()
			if iter:
				self.maintree.get_selection().cfg.poff_vbevent = model[iter][2]
			else:
				self.maintree.get_selection().cfg.poff_vbevent = ""

		return True

	def on_start_assign_nothing_button_clicked(self, widget=None, data=""):
		startevents = self.gladefile.get_widget('start_events_avail_treeview')
		treeselection = startevents.get_selection()
		treeselection.unselect_all()

	def on_stop_assign_nothing_button_clicked(self, widget=None, data=""):
		stopevents = self.gladefile.get_widget('stop_events_avail_treeview')
		treeselection = stopevents.get_selection()
		treeselection.unselect_all()

	def on_treeview_cdromdrives_row_activated(self, widget=None, data=""):
		raise NotImplementedError()

	def on_button_settings_add_cdevice_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_button_settings_rem_cdevice_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_treeview_qemupaths_row_activated(self, widget=None, data=""):
		raise NotImplementedError()

	def on_button_settings_add_qemubin_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_button_settings_rem_qemubin_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_dialog_bookmarks_response(self, widget=None, data=""):
		raise NotImplementedError()

	def on_edit_bookmark_activate(self, widget=None, data=""):
		raise NotImplementedError()

	def on_bookmark_info_activate(self, widget=None, data=""):
		raise NotImplementedError()

	def on_delete_bookmark_activate(self, widget=None, data=""):
		raise NotImplementedError()

	def on_dialog_about_response(self, widget=None, data=""):
		self.widg['dialog_about1'].hide()
		return True

	def on_dialog_create_image_response(self, widget=None, data=""):
		raise NotImplementedError()

	def on_filechooserbutton_newimage_dest_selection_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_filechooserbutton_newimage_dest_current_folder_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_entry_newimage_name_changed(self, widget=None, data=""):
		pass

	def on_combobox_newimage_format_changed(self, widget=None, data=""):
		pass

	def on_spinbutton_newimage_size_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_combobox_newimage_sizeunit_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_diskimage_selected(self, widget=None, event=None, data=""):
		tree = self.gladefile.get_widget('treeview_diskimages');
		store = self.image_tree
		x = int(event.x)
		y = int(event.y)
		pthinfo = tree.get_path_at_pos(x, y)
		name = self.get_treeselected(tree, store, pthinfo, 0)
		self.diskimage_show(name)

	def diskimage_show(self, name):
		img = self.brickfactory.get_image_by_name(name)
		if (img):
			self.gladefile.get_widget('diskimage_path_text').set_text(img.path)
			self.gladefile.get_widget('diskimage_name_text').set_text(img.name)
			self.gladefile.get_widget('diskimage_description_text').set_text(img.get_description())
			if img.host is None:
				host = ""
			else:
				host = img.host.addr[0]
			self.gladefile.get_widget('diskimage_host_text').set_text(str(host))

	def on_diskimage_save(self, widget=None, event=None, data=""):
		path = self.gladefile.get_widget('diskimage_path_text').get_text()
		img = self.brickfactory.get_image_by_path(path)
		host = self.gladefile.get_widget('diskimage_host_text').get_text()
		if (img):
			name = ValidName(self.gladefile.get_widget('diskimage_name_text').get_text())
			if name:
				img.rename(self.gladefile.get_widget('diskimage_name_text').get_text())
			else:
				self.error("Invalid Name.")
			img.set_description(self.gladefile.get_widget('diskimage_description_text').get_text())
		if (host != ""):
			host = self.brickfactory.get_host_by_name(host)
			if host is not None:
				img.host = host
		self.diskimage_show(img.name)

	def on_diskimage_revert(self, widget=None, event=None, data=""):
		path = self.gladefile.get_widget('diskimage_path_text').get_text()
		img = self.brickfactory.get_image_by_path(path)
		if (img):
			self.gladefile.get_widget('diskimage_name_text').set_text(img.name)
			self.gladefile.get_widget('diskimage_description_text').set_text(img.get_description())

	def browse_diskimage(self):
		self.curtain_down()
		self.show_window('filechooserdialog_openimage')

	def show_diskimage(self):
		self.curtain_down()

		self.image_tree.model.clear()
		for img in self.brickfactory.disk_images:
			iter = self.image_tree.new_row()
			self.image_tree.set_value(iter, 0, img.name)
			self.image_tree.set_value(iter,1, img.get_users())
			master = ""
			if img.master:
				master = img.master.VM.name
			self.image_tree.set_value(iter,2,master)
			self.image_tree.set_value(iter,3,img.get_cows())

		self.show_window('dialog_diskimage')

	def show_createimage(self):
		self.curtain_down()
		self.gladefile.get_widget('combobox_newimage_format').set_active(0)
		self.gladefile.get_widget('combobox_newimage_sizeunit').set_active(1)
		self.show_window('dialog_create_image')

	def on_filechooserdialog_openimage_response(self, widget=None, data=""):
		self.show_window('')
		return True

	def on_button_openimage_cancel_clicked(self, widget=None, data=""):
		self.show_window('')
		return True

	def on_button_openimage_open_clicked(self, widget=None, data=""):
		self.show_window('')
		path = self.gladefile.get_widget('filechooserdialog_openimage').get_filename()
		name = os.path.basename(path)
		self.brickfactory.new_disk_image(name,path)
		return True

	def on_dialog_diskimage_close(self, widget=None, data=""):
		self.show_window('')
		return True

	def on_image_newfromfile(self, widget=None, data=""):
		self.browse_diskimage()

	def on_image_library(self, widget=None, data=""):
		self.show_diskimage()

	def on_image_newempty(self, widget=None, data=""):
		self.show_createimage()

	def on_item_create_image_activate(self, widget=None, data=""):
		self.show_createimage()

	def image_create (self):
		self.debug("Image creating.. ",)
		path = self.gladefile.get_widget('filechooserbutton_newimage_dest').get_filename() + "/"
		filename = self.gladefile.get_widget('entry_newimage_name').get_text()
		img_format = self.gladefile.get_widget('combobox_newimage_format').get_active_text()
		img_size = str(self.gladefile.get_widget('spinbutton_newimage_size').get_value())
		#Get size unit and remove the last character 'B'
		#because qemu-img want k, M, G or T suffixes.
		img_sizeunit = self.gladefile.get_widget('combobox_newimage_sizeunit').get_active_text()[:-1]
		cmd='qemu-img create'
		if not filename:
			self.error(_("Choose a filename first!"))
			return

		if img_format == "Auto":
			img_format = "raw"
		fullname = path+filename+"."+img_format
		os.system('%s -f %s %s %s' % (cmd, img_format, fullname, img_size+img_sizeunit))
		os.system('sync')
		time.sleep(2)
		self.brickfactory.new_disk_image(filename,fullname)

	def on_button_create_image_clicked(self, widget=None, data=""):
		self.curtain_down()
		self.user_wait_action(self.image_create)

	def on_newimage_close_clicked(self, widget=None, data=""):
		self.curtain_down()
		self.widg['dialog_create_image'].hide()
		return True

	def on_dialog_messages_response(self, widget=None, data=""):
		raise NotImplementedError()

	def on_item_info_activate(self, widget=None, data=""):
		raise NotImplementedError()

	def on_item_bookmark_activate(self, widget=None, data=""):
		raise NotImplementedError()

	def on_dialog_jobmonitor_response(self, widget=None, data=""):
		raise NotImplementedError()

	def on_toolbutton_stop_job_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_toolbutton_reset_job_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_toolbutton_pause_job_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_toolbutton_rerun_job_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_treeview_jobmon_volumes_button_press_event(self, widget=None, data=""):
		raise NotImplementedError()

	def on_treeview_jobmon_volumes_row_activated(self, widget=None, data=""):
		raise NotImplementedError()

	def on_button_jobmon_apply_cdrom_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_button_jobmon_apply_fda_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_button_jobmon_apply_fdb_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_combobox_jobmon_cdrom_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_combobox_jobmon_fda_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_combobox_jobmon_fdb_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_treeview_usbhost_button_press_event(self, widget=None, data=""):
		raise NotImplementedError()

	def on_treeview_usbhost_row_activated(self, widget=None, data=""):
		raise NotImplementedError()

	def on_treeview_usbguest_button_press_event(self, widget=None, data=""):
		raise NotImplementedError()

	def on_treeview_usbguest_row_activated(self, widget=None, data=""):
		raise NotImplementedError()

	def on_item_jobmonoitor_activate(self, widget=None, data=""):
		self.joblist_selected.open_console()

	def on_item_stop_job_activate(self, widget=None, data=""):
		if self.joblist_selected is None:
			return
		if self.joblist_selected.proc != None:
			self.debug("Sending to process signal 19!")
			self.joblist_selected.proc.send_signal(19)

	def on_item_cont_job_activate(self, widget=None, data=""):
		if self.joblist_selected is None:
			return
		if self.joblist_selected.proc != None:
			self.debug("Sending to process signal 18!")
			self.joblist_selected.proc.send_signal(18)

	def on_item_reset_job_activate(self, widget=None, data=""):
		self.debug(self.joblist_selected)
		if self.joblist_selected is None:
			return
		if self.joblist_selected.proc != None:
			self.debug("Restarting process!")
			self.joblist_selected.poweroff()
			self.joblist_selected.poweron()

	def on_item_kill_job_activate(self, widget=None, data=""):
		if self.joblist_selected is None:
			return
		if self.joblist_selected.proc != None:
			self.debug("Sending to process signal 9!")
			self.joblist_selected.proc.send_signal(9)

	def on_attach_device_activate(self, widget=None, data=""):
		raise NotImplementedError()

	def on_detach_device_activate(self, widget=None, data=""):
		raise NotImplementedError()

	def on_item_eject_activate(self, widget=None, data=""):
		raise NotImplementedError()

	def on_dialog_newnetcard_response(self, widget=None, data=""):
		raise NotImplementedError()

	def on_combobox_networktype_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_entry_network_macaddr_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_entry_network_ip_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_spinbutton_network_port_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_spinbutton_network_vlan_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_entry_network_ifacename_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_entry_network_tuntapscript_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_button__network_open_tuntap_file_clicked(self, widget=None, data=""):
		raise NotImplementedError()

	def on_spinbutton_network_filedescriptor_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_dialog_new_redirect_response(self, widget=None, data=""):
		raise NotImplementedError()

	def on_radiobutton_redirect_TCP_toggled(self, widget=None, data=""):
		raise NotImplementedError()

	def on_radiobutton_redirect_UDP_toggled(self, widget=None, data=""):
		raise NotImplementedError()

	def on_spinbutton_redirect_sport_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_entry_redirect_gIP_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_spinbutton_redirect_dport_changed(self, widget=None, data=""):
		raise NotImplementedError()

	def on_newbrick(self, widget=None, event=None, data=""):
		self.curtain_down()
		self.gladefile.get_widget('text_newbrickname').set_text("")
		self.show_window('dialog_newbrick')

	def on_newevent(self, widget=None, event=None, data=""):
		self.curtain_down()
		self.gladefile.get_widget('text_neweventname').set_text("")
		self.show_window('dialog_newevent')

	def on_testconfig(self, widget=None, event=None, data=""):
		raise NotImplementedError()

	def on_autodetectsettings(self, widget=None, event=None, data=""):
		raise NotImplementedError()

	def on_check_kvm(self, widget=None, event=None, data=""):
		if widget.get_active():
			try:
				self.config.check_kvm()
			except IOError:
				self.error(_("No KVM binary found")+". "+_("Check your active configuration")+". "+_("KVM will stay disabled")+".")
				widget.set_active(False)
			except NotImplementedError:
				self.error(_("No KVM support found on the system")+". "+_("Check your active configuration")+". "+_("KVM will stay disabled")+".")
				widget.set_active(False)

	def on_check_ksm(self, widget=None, event=None, data=""):
		try:
			self.config.check_ksm(True)
		except NotImplementedError:
			self.debug("no support")
			self.error(_("No KSM support found on the system")+". "+_("Check your configuration")+". "+_("KSM will stay disabled")+".")
			widget.set_active(False)

	def on_add_cdrom(self, widget=None, event=None, data=""):
		raise NotImplementedError()

	def on_remove_cdrom(self, widget=None, event=None, data=""):
		raise NotImplementedError()

	def on_brick_delete(self,widget=None, event=None, data=""):
		self.curtain_down()

		message=""
		if self.maintree.get_selection().proc is not None:
			message = _("The brick is still running, it will be killed before being deleted!\n")

		self.ask_confirm(message + _("Do you really want to delete ") +
				self.maintree.get_selection().get_type() + " \"" + self.maintree.get_selection().name + "\" ?",
				on_yes = self.brickfactory.delbrick, arg = self.maintree.get_selection())

	def on_event_delete(self,widget=None, event=None, data=""):
		self.curtain_down()

		msg=""
		if self.event_selected.active:
			msg=_("This event is in use")+". "

		self.ask_confirm(msg + _("Do you really want to delete") + " "+
				_(self.event_selected.get_type()) + " \"" + self.event_selected.name + "\" ?",
				on_yes = self.brickfactory.delevent, arg = self.event_selected)

	def on_brick_copy(self,widget=None, event=None, data=""):
		self.curtain_down()
		self.brickfactory.dupbrick(self.maintree.get_selection())

	def on_brick_rename(self,widget=None, event=None, data=""):
		if self.maintree.get_selection().proc != None:
			self.error(_("Cannot rename Brick: it is in use."))
			return

		self.gladefile.get_widget('entry_brick_newname').set_text(self.maintree.get_selection().name)
		self.gladefile.get_widget('dialog_rename').show_all()
		self.curtain_down()

	def on_event_copy(self,widget=None, event=None, data=""):
		self.curtain_down()
		self.brickfactory.dupevent(self.event_selected)

	def on_event_configure(self,widget=None, event=None, data=""):
		self.curtain_up()
		return

	def on_event_rename(self,widget=None, event=None, data=""):
		self.gladefile.get_widget('entry_event_newname').set_text(self.event_selected.name)
		self.gladefile.get_widget('dialog_event_rename').show_all()
		self.curtain_down()

	def on_dialog_rename_response(self, widget=None, response=0, data=""):
		widget.hide()
		if response == 1:
			try:
				self.brickfactory.renamebrick(self.maintree.get_selection(), self.gladefile.get_widget('entry_brick_newname').get_text())
			except InvalidName:
				self.error(_("Invalid name!"))

	def on_dialog_event_rename_response(self, widget=None, response=0, data=""):
		widget.hide()
		if response == 1:
			if self.event_selected.active:
				self.error(_("Cannot rename Event: it is in use."))
				return

			try:
				self.brickfactory.renameevent(self.event_selected, self.gladefile.get_widget('entry_event_newname').get_text())
			except InvalidName:
				self.error(_("Invalid name!"))

	def on_dialog_shellcommand_response(self, widget=None, response=0, data=""):
		if response == 1:
			try:
				name = self.gladefile.get_widget('text_neweventname').get_text()
				delay = int(self.gladefile.get_widget('text_neweventdelay').get_text())
				actions = self.gladefile.get_widget('treeview_event_actions')

				iter = self.shcommandsmodel.get_iter_first()

				#Do not hide window
				if not iter:
					return

				currevent = None
				columns = (COL_COMMAND, COL_BOOL) = range(2)

				while iter:
					linecommand = self.shcommandsmodel.get_value (iter, COL_COMMAND)
					shbool = self.shcommandsmodel.get_value(iter, COL_BOOL)

					linecommand = linecommand.lstrip("\n").rstrip("\n").strip()
					"""
					Can be multiline command.
					CTRL+ENTER does not send "enter" inside
					the field but confirms the field instead, exiting edit mode.
					That feature is managed anyway.
					Example:
					sw1 config fstp=False
					wf1 config xxx=yyy
					....
					will be transformed into:
					[eventname] config add sw1 config fstp=False add wf1 config xxx=yyy add...
					"""
		 			commands = linecommand.split("\n")
		 			commandtype = 'addsh' if shbool else 'add'

		 			if not commands[0]:
		 				iter = self.shcommandsmodel.iter_next(iter)
		 				continue

		 			commands[0] = 'config %s %s' % (commandtype, commands[0])
		 			c = unicode(' %s ' % commandtype).join(commands)

		 			if currevent is None:
						self.brickfactory.newevent("event", name)
		 				currevent = self.brickfactory.geteventbyname(name)
		 				self.brickfactory.brickAction(currevent,
							('config delay='+str(delay)).split(" "))

		 			self.brickfactory.brickAction(currevent, c.split(" "))
		 			iter = self.shcommandsmodel.iter_next(iter)

		 		if currevent is not None:
					#If at least one element added
					self.debug("Event created successfully")
		 			widget.hide()
			except InvalidName:
				self.error(_("Invalid name!"))
				widget.hide()
		#Dialog window canceled
		else:
			widget.hide()

	def on_dialog_event_bricks_select_response(self,widget=None, response=0, data=""):
		columns = (COL_ICON, COL_TYPE, COL_NAME, COL_CONFIG) = range(4)
		addedbricks = self.gladefile.get_widget('bricks_added_treeview')
		iter = self.addedmodel.get_iter_first()

		if not iter and response==1:
			return
		elif response==0:
			widget.hide()
			return
		else:
			widget.hide()

		evname = self.gladefile.get_widget('text_neweventname').get_text()
		delay = int(self.gladefile.get_widget('text_neweventdelay').get_text())
		self.brickfactory.newevent("event", evname)
		currevent = self.brickfactory.geteventbyname(evname)
		self.brickfactory.brickAction(currevent,('config delay='+str(delay)).split(" "))

		action = ' on' if self.selected_event_type() in ['BrickStart', 'EventsCollation'] else ' off'

		while iter:
			evnametoadd = self.addedmodel.get_value(iter, COL_NAME)
			self.brickfactory.\
			brickAction(currevent,('config add ' + evnametoadd + action).\
										split(" "))
			iter = self.addedmodel.iter_next(iter)

		self.debug("Event created successfully")

	def on_brick_configure(self,widget=None, event=None, data=""):
		self.curtain_up()

	def on_qemupath_changed(self, widget, data=None):
		newpath = widget.get_filename()
		missing_qemu = False
		missing_kvm = False
		missing,found = self.config.check_missing_qemupath(newpath)
		lbl = self.gladefile.get_widget("label_qemupath_status")
		if not os.access(newpath,os.X_OK):
			lbl.set_markup('<span color="red">'+_("Error")+':</span>\n'+_("invalid path for qemu binaries"))
			return

		for t in missing:
			if t == 'qemu':
				missing_qemu = True
			if t == 'kvm':
				missing_kvm = True
		if missing_qemu and missing_kvm:
			lbl.set_markup('<span color="red">'+_("Error")+':</span>\n'+_("cannot find neither qemu nor kvm in this path"))
			return
		txt = ""
		if missing_qemu:
			txt = '<span color="red">'+_("Warning")+':</span>\n'+_("cannot find qemu, using kvm only\n")

		elif missing_kvm:
			txt = '<span color="yellow">'+_("Warning")+':</span>\n'+_("kvm not found")+"."+_("KVM support disabled")+'.\n'
		else:
			txt = '<span color="darkgreen">'+_("KVM and Qemu detected")+'.</span>\n'
		arch = ""
		rowlimit = 30
		for i in found:
			if i.startswith('qemu-system-'):
				arch+=i.split('qemu-system-')[1] + ", "
				if (len(arch) > rowlimit):
					rowlimit+=30
					arch.rstrip(', ')
					arch+="\n"

		if len(arch) > 0:
			txt += _("additional targets supported")+":\n"
			txt += arch.rstrip(', ')
		lbl.set_markup(txt)

	def on_vdepath_changed(self, widget, data=None):
		newpath = widget.get_filename()
		missing = self.config.check_missing_vdepath(newpath)
		lbl = self.gladefile.get_widget("label_vdepath_status")
		if not os.access(newpath,os.X_OK):
			lbl.set_markup('<span color="red">'+_("Error")+':</span>\n'+_("invalid path for vde binaries"))
		elif len(missing) > 0:
			txt = '<span color="red">'+_("Warning, missing modules")+':</span>\n'
			for l in missing:
				txt+=l + "\n"
			lbl.set_markup(txt)
		else:
			lbl.set_markup('<span color="darkgreen">'+_("All VDE components detected")+'.</span>\n')

	def on_arch_changed(self, widget, data=None):
		if self.maintree.get_selection().get_type() != 'Qemu':
			return

		combo = ComboBox(widget)
		path = self.config.get('qemupath')

		#Machine COMBO
		machine_c = ComboBox(self.gladefile.get_widget("cfg_Qemu_machine_combo"))
		opt_m = dict()
		os.system(path + "/" + combo.get_selected() + " -M ? >" + MYPATH+"/.vmachines")
		for m in open(MYPATH+"/.vmachines").readlines():
			if not re.search('machines are', m):
				v = m.split(' ')[0]
				k = m.lstrip(v).rstrip('/n')
				while (k.startswith(' ')):
					k = k.lstrip(' ')
				opt_m[v]=v
		toSelect=""
		for k, v in opt_m.iteritems():
			if v.strip() == self.maintree.get_selection().cfg.machine.strip():
				toSelect=k
		machine_c.populate(opt_m, toSelect)
		os.unlink(MYPATH+"/.vmachines")

		#CPU combo
		opt_c = dict()
		cpu_c = ComboBox(self.gladefile.get_widget("cfg_Qemu_cpu_combo"))
		os.system(path + "/" + combo.get_selected() + " -cpu ? >" + MYPATH+"/.cpus")
		for m in open(MYPATH+"/.cpus").readlines():
			if not re.search('Available CPU', m):
				if (m.startswith('  ')):
					while (m.startswith(' ')):
						m = m.lstrip(' ')
					if m.endswith('\n'):
						m = m.rstrip('\n')
					opt_c[m] = m
				else:
					lst = m.split(' ')
					if len(lst) > 1:
						val = m.lstrip(lst[0])
						while (val.startswith(' ')):
							val = val.lstrip(' ')
						if val.startswith('\''):
							val = val.lstrip('\'')
						if val.startswith('['):
							val = val.lstrip('[')
						if val.endswith('\n'):
							val = val.rstrip('\n')

						if val.endswith('\''):
							val = val.rstrip('\'')
						if val.endswith(']'):
							val = val.rstrip(']')
						opt_c[val]=val
		cpu_c.populate(opt_c, self.maintree.get_selection().cfg.cpu)
		os.unlink(MYPATH+"/.cpus")

	def on_check_kvm_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			try:
				self.config.check_kvm()
				self.kvm_toggle_all(True)
			except IOError:
				self.error(_("No KVM binary found. Check your active configuration. KVM will stay disabled."))
				widget.set_active(False)
			except NotImplementedError:
				self.error(_("No KVM support found on the system. Check your active configuration. KVM will stay disabled."))
				widget.set_active(False)
		else:
			self.kvm_toggle_all(False)

	def kvm_toggle_all(self, enabled):
		self.gladefile.get_widget('cfg_Qemu_kvmsmem_spinint').set_sensitive(enabled)
		self.gladefile.get_widget('cfg_Qemu_kvmsm_check').set_sensitive(enabled)
		# disable incompatible options
		if self.gladefile.get_widget('cfg_Qemu_tdf_check').get_active() and not enabled:
			self.gladefile.get_widget('cfg_Qemu_tdf_check').set_active(False)
		self.gladefile.get_widget('cfg_Qemu_tdf_check').set_sensitive(enabled)
		self.disable_qemu_combos(not enabled)

	def disable_qemu_combos(self,active):
		self.gladefile.get_widget('cfg_Qemu_argv0_combo').set_sensitive(active)
		self.gladefile.get_widget('cfg_Qemu_cpu_combo').set_sensitive(active)
		self.gladefile.get_widget('cfg_Qemu_machine_combo').set_sensitive(active)

	def on_check_customkernel_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			self.gladefile.get_widget('cfg_Qemu_kernel_filechooser').set_sensitive(True)
			self.gladefile.get_widget('filedel_cfg_Qemu_kernel').set_sensitive(True)
		else:
			self.on_filechooser_clear(self.gladefile.get_widget('cfg_Qemu_kernel_filechooser'), None, "", True)
			self.gladefile.get_widget('cfg_Qemu_kernel_filechooser').set_sensitive(False)
			self.gladefile.get_widget('filedel_cfg_Qemu_kernel').set_sensitive(False)

	def on_check_initrd_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			self.gladefile.get_widget('cfg_Qemu_initrd_filechooser').set_sensitive(True)
			self.gladefile.get_widget('filedel_cfg_Qemu_initrd').set_sensitive(False)
		else:
			self.on_filechooser_clear(self.gladefile.get_widget('cfg_Qemu_initrd_filechooser'), None, "", True)
			self.gladefile.get_widget('cfg_Qemu_initrd_filechooser').set_sensitive(False)
			self.gladefile.get_widget('filedel_cfg_Qemu_initrd').set_sensitive(True)

	def on_check_gdb_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			self.gladefile.get_widget('cfg_Qemu_gdbport_spinint').set_sensitive(True)
		else:
			self.gladefile.get_widget('cfg_Qemu_gdbport_spinint').set_sensitive(False)

	def on_random_macaddr(self, widget=None, event=None, data=""):
		self.gladefile.get_widget('vmplug_macaddr').set_text(tools.RandMac())

	def valid_mac(self, mac):
		test = re.match("[a-fA-F0-9]{2}:[a-fA-F0-9]{2}:[a-fA-F0-9]{2}:[a-fA-F0-9]{2}:[a-fA-F0-9]{2}:[a-fA-F0-9]{2}", mac)
		if test:
			return True
		return False

	def on_vmplug_add(self, widget=None, event=None, data=""):
		b = self.maintree.get_selection()
		if b is None:
			return
		sockname = ComboBox(self.gladefile.get_widget('sockscombo_vmethernet')).get_selected()
		if sockname == '_sock':
			pl = b.add_sock()
		elif (sockname == '_hostonly'):
			pl = b.add_plug('_hostonly')
		else:
			pl = b.add_plug()
			for so in self.brickfactory.socks:
				if so.nickname == sockname:
					pl.connect(so)
		pl.model = self.gladefile.get_widget('vmplug_model').get_active_text()
		mac = self.gladefile.get_widget('vmplug_macaddr').get_text()
		if not self.valid_mac(mac):
			mac = tools.RandMac()
		if pl.brick.proc and pl.hotadd:
			pl.hotadd()
		self.update_vmplugs_tree()

	def update_vmplugs_tree(self):
		b = self.maintree.get_selection()
		if b is None:
			return

		if (b.get_type() == 'Qemu'):
			self.vmplugs.model.clear()
			for pl in b.plugs:
				iter = self.vmplugs.new_row()
				self.vmplugs.set_value(iter,0,pl.vlan)
				if pl.mode == 'hostonly':
					self.vmplugs.set_value(iter,1,'Host')
				elif pl.sock:
					self.vmplugs.set_value(iter,1,pl.sock.brick.name)
				self.vmplugs.set_value(iter,2,pl.model)
				self.vmplugs.set_value(iter,3,pl.mac)
			if self.config.femaleplugs:
				for sk in b.socks:
					iter = self.vmplugs.new_row()
					self.vmplugs.set_value(iter,0,sk.vlan)
					self.vmplugs.set_value(iter,1,'Vde socket (female plug)')
					self.vmplugs.set_value(iter,2,sk.model)
					self.vmplugs.set_value(iter,3,sk.mac)
			self.vmplugs.order(0, True)

	def on_vmplug_selected(self, widget=None, event=None, data=""):
		b = self.maintree.get_selection()
		if b is None:
			return
		tree = self.gladefile.get_widget('treeview_networkcards');
		store = self.vmplugs
		x = int(event.x)
		y = int(event.y)
		pthinfo = tree.get_path_at_pos(x, y)
		number = self.get_treeselected(tree, store, pthinfo, 0)
		self.vmplug_selected = None
		vmsock = False
		for pl in b.plugs:
			if str(pl.vlan) == number:
				self.vmplug_selected = pl
				break
		if not self.vmplug_selected:
			for pl in b.socks:
				if str(pl.vlan) == number:
					self.vmplug_selected = pl
					vmsock=True
					break
		pl = self.vmplug_selected

		if pl:
			ComboBox(self.gladefile.get_widget("vmplug_model")).select(pl.model)
			self.gladefile.get_widget('vmplug_macaddr').set_text(pl.mac)
			if (pl.mode == 'sock'):
				ComboBox(self.gladefile.get_widget('sockscombo_vmethernet')).select('Vde socket')
			elif (pl.mode == 'hostonly'):
				ComboBox(self.gladefile.get_widget('sockscombo_vmethernet')).select('Host-only ad hoc network')
			elif (pl.sock):
				ComboBox(self.gladefile.get_widget('sockscombo_vmethernet')).select(pl.sock.nickname)
			self.gladefile.get_widget('button_network_netcard_add').hide()
			self.gladefile.get_widget('button_network_edit').show()
			self.gladefile.get_widget('button_network_remove').show()
			self.gladefile.get_widget('netcard_label_type').hide()
			self.gladefile.get_widget('netcard_combo_type').hide()
		else:
			self.gladefile.get_widget('button_network_netcard_add').show()
			self.gladefile.get_widget('treeview_networkcards').get_selection().unselect_all()
			self.gladefile.get_widget('button_network_netcard_add').grab_focus()
			self.gladefile.get_widget('button_network_edit').hide()
			self.gladefile.get_widget('button_network_remove').hide()
			self.gladefile.get_widget('netcard_label_type').show()
			self.gladefile.get_widget('netcard_combo_type').show()
			self.gladefile.get_widget('netcard_combo_type').set_active(0)

	def on_vmplug_edit(self, widget=None, event=None, data=""):
		pl = self.vmplug_selected
		if pl == None:
			return
		vlan = pl.vlan
		b = self.maintree.get_selection()
		if b is None:
			return

		if (pl.mode == 'sock'):
			b.socks.remove(pl)
		else:
			b.plugs.remove(pl)
		del(pl)
		model = ComboBox(self.gladefile.get_widget('vmplug_model')).get_selected()
		mac = self.gladefile.get_widget('vmplug_macaddr').get_text()
		sockname = ComboBox(self.gladefile.get_widget('sockscombo_vmethernet')).get_selected()
		if (sockname == '_sock'):
			pl = b.add_sock()
		if (sockname == '_hostonly'):
			pl = b.add_plug(sockname)
		else:
			for so in self.brickfactory.socks:
				if so.nickname == sockname:
					pl = b.add_plug(so)
		pl.vlan = vlan
		pl.model = model
		if (self.valid_mac(pl.mac)):
			pl.mac = mac
		else:
			pl.mac = tools.RandMac()
		self.update_vmplugs_tree()

	def on_vmplug_remove(self, widget=None, event=None, data=""):
		b = self.maintree.get_selection()
		if b is None:
			return
		pl = self.vmplug_selected
		if pl.brick.proc and pl.hotdel:
			pl.hotdel()
		b.remove_plug(pl.vlan)
		self.update_vmplugs_tree()

	def on_vmplug_onoff(self, widget=None, event=None, data=""):
		if self.gladefile.get_widget('radiobutton_network_nonet').get_active():
			self.set_nonsensitivegroup(['vmplug_model', 'sockscombo_vmethernet','vmplug_macaddr','randmac',
				'button_network_netcard_add','button_network_edit','button_network_remove', 'treeview_networkcards'])
		else:
			self.set_sensitivegroup(['vmplug_model', 'sockscombo_vmethernet','vmplug_macaddr','randmac',
				'button_network_netcard_add','button_network_edit','button_network_remove', 'treeview_networkcards'])

	def on_tap_config_manual(self, widget=None, event=None, data=""):
		if widget.get_active():
			self.gladefile.get_widget('tap_ipconfig').set_sensitive(True)
		else:
			self.gladefile.get_widget('tap_ipconfig').set_sensitive(False)

	def on_vm_suspend(self, widget=None, event=None, data=""):
		hda = self.joblist_selected.cfg.get('basehda')
		if hda is None or 0 != subprocess.Popen(["qemu-img","snapshot","-c","virtualbricks",hda]).wait():
			self.error(_("Suspend/Resume not supported on this disk."))
			return
		self.joblist_selected.recv()
		self.joblist_selected.send("savevm virtualbricks\n")
		while(not self.joblist_selected.recv().startswith("(qemu")):
			print ".",
			time.sleep(1)
		print
		self.joblist_selected.poweroff()

	def on_vm_resume(self, widget=None, event=None, data=""):
		b = self.maintree.get_selection()
		if b is None:
			return

		hda = b.cfg.get('basehda')
		self.debug("resume")
		if os.system("qemu-img snapshot -l "+hda+" |grep virtualbricks") == 0:
			if b.proc is not None:
				b.send("loadvm virtualbricks\n")
				b.recv()
				return
			else:
				b.cfg.set("loadvm=virtualbricks")
				b.poweron()
		else:
			self.error(_("Cannot find suspend point."))

	def on_vm_powerbutton(self, widget=None, event=None, data=""):
		self.joblist_selected.send("system_powerdown\n")
		self.joblist_selected.recv()

	def on_vm_hardreset(self, widget=None, event=None, data=""):
		self.joblist_selected.send("system_reset\n")
		self.joblist_selected.recv()

	def on_topology_drag(self, widget=None, event=None, data=""):
		raise NotImplementedError()

	def on_topology_redraw(self, widget=None, event=None, data=""):
		self.draw_topology()

	def on_topology_export(self, widget=None, event=None, data=""):
		self.gladefile.get_widget('topology_export_dialog').show_all()

	def on_topology_export_ok(self, widget=None, event=None, data=""):
		fname = self.gladefile.get_widget('topology_export_dialog').get_filename()
		self.gladefile.get_widget('topology_export_dialog').hide()
		if fname:
			if os.access(fname,os.R_OK):
				self.ask_confirm("Do you want to overwrite " + fname + "?", on_yes=self.topology_export, arg=fname)
			else:
				self.topology_export(fname)

	def topology_export(self, fname):
		try:
			self.draw_topology(fname)
		except KeyError:
			self.error(_("Error saving topology: Invalid image format"))
		except IOError:
			self.error(_("Error saving topology: Could not write file"))
		except:
			self.error(_("Error saving topology: Unknown error"))

	def on_topology_export_cancel(self, widget=None, event=None, data=""):
		self.gladefile.get_widget('topology_export_dialog').hide()

	def on_topology_action(self, widget=None, event=None, data=""):
		if self.topology:
			for n in self.topology.nodes:
				if n.here(event.x,event.y) and event.button == 3:
					brick = self.brickfactory.getbrickbyname(n.name)
					if brick is not None:
						self.maintree.set_selection(brick)
						self.show_brickactions()
				if n.here(event.x,event.y) and event.button == 1 and event.type == gtk.gdk._2BUTTON_PRESS:
					brick = self.brickfactory.getbrickbyname(n.name)
					if brick is not None:
						self.maintree.set_selection(brick)
						self.user_wait_action(self.startstop_brick, brick)
		self.curtain_down()

	def on_topology_scroll(self, widget=None, event=None, data=""):
		raise NotImplementedError()

	def on_vnc_novga_toggled(self, widget=None, event=None, data=""):
		novga = self.gladefile.get_widget('cfg_Qemu_novga_check')
		vnc = self.gladefile.get_widget('cfg_Qemu_vnc_check')
		if (novga==widget):
			vnc.set_sensitive(not novga.get_active())
			self.gladefile.get_widget('cfg_Qemu_vncN_spinint').set_sensitive(not novga.get_active())
			self.gladefile.get_widget('label33').set_sensitive(not novga.get_active())
		if (vnc == widget):
			novga.set_sensitive(not vnc.get_active())

	def on_vmicon_file_change(self, widget=None, event=None, data=""):
		if widget.get_filename() is not None:
			pixbuf = self.pixbuf_scaled(widget.get_filename())
			self.gladefile.get_widget("qemuicon").set_from_pixbuf(pixbuf)

	def on_filechooser_clear(self, widget=None, event=None, data="", direct=False):
		if not direct:
			filechooser = widget.name[8:] + "_filechooser"
		else:
			filechooser = widget.name
		self.gladefile.get_widget(filechooser).unselect_all()

	def on_filechooser_hd_clear(self, widget=None, event=None, data=""):
		#self.on_filechooser_clear(widget)
		hd = widget.name[21:]
		check = self.gladefile.get_widget("cfg_Qemu_private"+hd+"_check")
		check.set_active(False)
		imgcombo = widget.name[8:] + "_combo"
		images = ComboBox(self.gladefile.get_widget(imgcombo))
		opt = dict()
		opt['Off'] = ""
		for img in self.brickfactory.disk_images:
			opt[img.name] = img.name
		images.populate(opt,"")
		images.select("Off")

	def on_filechooser_image_clear(self, widget=None, event=None, data=""):
		self.on_filechooser_clear(widget)
		self.gladefile.get_widget("qemuicon").set_from_file("Qemu.png")

	def on_show_messages_activate(self, menuitem, data=None):
		messages = self.gladefile.get_widget("messages_dialog")
		messages.show_all()

	def on_messages_dialog_delete_event(self, widget=None, event=None, data=""):
		"""we could use deletable property but deletable is only available in
		GTK+ 2.10 and above"""
		widget.hide()
		return True

	def on_dialog_messages_close_event(self, widget=None, event=None, data=""):
		self.on_dialog_messages_delete_event(self)
		return True

	def on_dialog_messages_delete_event(self, widget=None, event=None, data=""):
		messages = self.gladefile.get_widget("dialog_messages")
		messages.hide()
		return True

	def on_messages_dialog_close_event(self, widget=None, event=None, data=""):
		messages = self.gladefile.get_widget("messages_dialog")
		messages.hide()
		return True

	def on_messages_dialog_clear_clicked(self, button, data=None):
		self.messages_buffer.set_text("")
		return True

	def on_brick_attach_event(self, menuitem, data=None):
		attach_event_window = self.gladefile.get_widget("dialog_attach_event")

		columns = (COL_ICON, COL_TYPE, COL_NAME, COL_CONFIG) = range(4)

		startavailevents = self.gladefile.get_widget('start_events_avail_treeview')
		stopavailevents = self.gladefile.get_widget('stop_events_avail_treeview')

		self.eventsmodel = gtk.ListStore (gtk.gdk.Pixbuf, str, str, str)

		startavailevents.set_model(self.eventsmodel)
		stopavailevents.set_model(self.eventsmodel)

		treeviewselectionstart = startavailevents.get_selection()
		treeviewselectionstart.unselect_all()
		treeviewselectionstop = stopavailevents.get_selection()
		treeviewselectionstop.unselect_all()

		container = self.brickfactory.events

		for event in container:
			if event.configured():
				parameters = event.get_parameters()
				if len(parameters) > 30:
					parameters = "%s..." % parameters[:30]
				image = gtk.gdk.pixbuf_new_from_file_at_size(event.icon.base, 48, 48)
				iter = self.eventsmodel.append([image, event.get_type(), event.name, parameters])
				if self.maintree.get_selection().cfg.pon_vbevent == event.name:
					treeviewselectionstart.select_iter(iter)
				if self.maintree.get_selection().cfg.poff_vbevent == event.name:
					treeviewselectionstop.select_iter(iter)

		cell = gtk.CellRendererPixbuf ()
		column_icon = gtk.TreeViewColumn (_("Icon"), cell, pixbuf = COL_ICON)
		cell = gtk.CellRendererText ()
		column_type = gtk.TreeViewColumn (_("Type"), cell, text = COL_TYPE)
		cell = gtk.CellRendererText ()
		column_name = gtk.TreeViewColumn (_("Name"), cell, text = COL_NAME)
		cell = gtk.CellRendererText ()
		column_config = gtk.TreeViewColumn (_("Parameters"), cell, text = COL_CONFIG)

		# Clear columns
		for c in startavailevents.get_columns():
			startavailevents.remove_column(c)

		for c in stopavailevents.get_columns():
			stopavailevents.remove_column(c)

		# Add columns
		startavailevents.append_column (column_icon)
		startavailevents.append_column (column_type)
		startavailevents.append_column (column_name)
		startavailevents.append_column (column_config)

		cell = gtk.CellRendererPixbuf ()
		column_icon = gtk.TreeViewColumn (_("Icon"), cell, pixbuf = COL_ICON)
		cell = gtk.CellRendererText ()
		column_type = gtk.TreeViewColumn (_("Type"), cell, text = COL_TYPE)
		cell = gtk.CellRendererText ()
		column_name = gtk.TreeViewColumn (_("Name"), cell, text = COL_NAME)
		cell = gtk.CellRendererText ()
		column_config = gtk.TreeViewColumn (_("Parameters"), cell, text = COL_CONFIG)

		stopavailevents.append_column (column_icon)
		stopavailevents.append_column (column_type)
		stopavailevents.append_column (column_name)
		stopavailevents.append_column (column_config)

		self.gladefile.\
		get_widget('dialog_attach_event').\
		set_title(_("Virtualbricks-Events to attach to the start/stop Brick Events"))

		attach_event_window.show_all()
		return True

	def on_open_project(self, widget, data=None):
		if self.confirm(_("Save current project?"))==True:
			self.brickfactory.config_dump(self.config.get('current_project'))

		chooser = gtk.FileChooserDialog(title=_("Open a project"),action=gtk.FILE_CHOOSER_ACTION_OPEN, buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
		chooser.set_current_folder(self.config.get('bricksdirectory'))
		filt = gtk.FileFilter()
		filt.set_name(_("Virtualbricks Bricks List") + " (*.vbl)")
		filt.add_pattern("*.vbl")
		chooser.add_filter(filt)
		filt = gtk.FileFilter()
		filt.set_name(_("All files"))
		filt.add_pattern("*")
		chooser.add_filter(filt)
		resp = chooser.run()
		if resp == gtk.RESPONSE_OK:
			filename = chooser.get_filename()
			self.config.set('current_project', filename)
			self.brickfactory.config_restore(filename, False, True)
			self.config.store()
		chooser.destroy()

	def on_save_project(self, widget, data=None):
		chooser = gtk.FileChooserDialog(title=_("Save as..."),action=gtk.FILE_CHOOSER_ACTION_SAVE, buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_SAVE,gtk.RESPONSE_OK))
		chooser.set_do_overwrite_confirmation(True)
		chooser.set_current_folder(self.config.get('bricksdirectory'))
		filt = gtk.FileFilter()
		filt.set_name(_("Virtualbricks Bricks List") + " (*.vbl)")
		filt.add_pattern("*.vbl")
		chooser.add_filter(filt)
		filt = gtk.FileFilter()
		filt.set_name(_("All files"))
		filt.add_pattern("*")
		chooser.add_filter(filt)
		resp = chooser.run()
		if resp == gtk.RESPONSE_OK:
			filename = chooser.get_filename()
			if filename[len(filename)-4:] != ".vbl":
				filename+=".vbl"
			self.config.set('current_project', filename)
			# FORCE CONFIG_DUMP TO CALCULATE A NEW PROJECT ID
			self.brickfactory.project_parms['id'] = "0"
			self.brickfactory.config_dump(filename)
			self.config.store()
		chooser.destroy()

	def on_import_project(self, widget, data=None):
		self.debug( "IMPORT PROJECT undefined" )

	def on_new_project(self, widget, data=None):
		if self.confirm("Save current project?")==True:
			self.brickfactory.config_dump(self.config.get('current_project'))

		chooser = gtk.FileChooserDialog(title=_("New project"),action=gtk.FILE_CHOOSER_ACTION_SAVE, buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_SAVE,gtk.RESPONSE_OK))
		chooser.set_do_overwrite_confirmation(True)
		chooser.set_current_folder(self.config.get('bricksdirectory'))
		filt = gtk.FileFilter()
		filt.set_name(_("Virtualbricks Bricks List") + " (*.vbl)")
		filt.add_pattern("*.vbl")
		chooser.add_filter(filt)
		filt = gtk.FileFilter()
		filt.set_name(_("All files"))
		filt.add_pattern("*")
		chooser.add_filter(filt)
		resp = chooser.run()
		if resp == gtk.RESPONSE_OK:
			filename = chooser.get_filename()
			if filename[len(filename)-4:] != ".vbl":
				filename+=".vbl"
			self.config.set('current_project', filename)
			self.brickfactory.config_restore(filename, True, True)
			self.config.store()
		chooser.destroy()

	def on_open_recent_project(self, widget, data=None):
		raise NotImplementedError()

	def on_add_remotehost(self, widget, data=None):
		txt = self.gladefile.get_widget("newhost_text").get_text()
		if len(txt) > 0:
			for existing in self.brickfactory.remote_hosts:
				if (txt == existing.addr[0]):
					return
			self.brickfactory.remote_hosts.append(RemoteHost(self.brickfactory, txt))

	def on_check_newbrick_runremote_toggled(self, widget, event=None, data=None):
		self.gladefile.get_widget('text_newbrick_runremote').set_sensitive(widget.get_active())

	def on_passwd_ok(self, widget, event=None, data=None):
		self.remotehost_selected.password=self.gladefile.get_widget('text_remote_password').get_text()
		self.show_window('')
		return True

	def on_passwd_cancel(self, widget, event=None, data=None):
		self.show_window('')
		return True

	def on_remote_connect(self, widget, event=None, data=None):
		print "connect"
		if self.remotehost_selected.connected:
			self.remotehost_selected.disconnect()
		else:
			conn_ok, msg = self.remotehost_selected.connect()
			if not conn_ok:
				self.error("Error connecting to remote host %s: %s" % (self.remotehost_selected.addr[0], msg))

	def on_remote_password(self, widget, event=None, data=None):
		self.gladefile.get_widget('text_remote_password').set_text(self.remotehost_selected.password)
		self.show_window('dialog_remote_password')

	def on_remote_autoconnect(self, widget, event=None, data=None):
		self.remotehost_selected.autoconnect = widget.get_active()

	def on_remote_delete(self, widget, event=None, data=None):
		for existing in self.brickfactory.remote_hosts:
			if (existing.addr[0] == self.remotehost_selected.addr[0]):
				self.ask_confirm(_("Do you really want to delete remote host ") +
					" \"" + existing.addr[0] + "\" and all the bricks related?",
					on_yes = self.brickfactory.delremote, arg = self.remotehost_selected.addr[0])

	def on_usbmode_onoff(self, w, event=None, data=None):
		if (w.get_active()):
			self.maintree.get_selection().cfg.set('usbmode=*')
		else:
			self.maintree.get_selection().cfg.set('usbmode=')
			self.maintree.get_selection().cfg.set('usbdevlist=')
		self.gladefile.get_widget('vm_usb_show').set_sensitive(w.get_active())

	def on_usb_show(self, w, event=None, data=None):
		vm = self.maintree.get_selection()
		current_usbview = dict()
		self.curtain_down()
		os.system("lsusb >" + MYPATH + "/.usbdev")

		self.usbdev_tree.model.clear()
		self.show_window('dialog_usbdev')
		try:
			f = open(MYPATH + "/.usbdev")
		except:
			return
		for l in f:
			info = l.split(" ID ")[1]
			if re.search(' ', info):
				code = info.split(' ')[0]
				descr = info.split(' ')[1]
				iter = self.usbdev_tree.new_row()
				self.usbdev_tree.set_value(iter, 0, code)
				self.usbdev_tree.set_value(iter, 1, descr)
				current_usbview[iter] = code
		selection = self.gladefile.get_widget('treeview_usbdev').get_selection()
		for selected in vm.cfg.usbdevlist.split(' '):
			for iter,dev in current_usbview.iteritems():
				if dev == selected:
					selection.select_iter(iter)
					print "found " + dev




	def on_usbdev_close(self, w, event=None, data=None):
		tree = self.gladefile.get_widget('treeview_usbdev')
		model,paths = tree.get_selection().get_selected_rows()
		devlist = ''
		for p in paths:
			new_id = model[p[0]][0]
			devlist += new_id + ' '

		if len(devlist) > 0 and not os.access("/dev/bus/usb", os.W_OK):
				self.show_window('')
				self.curtain_up()
				self.error(_("Cannot access /dev/bus/usb. Check user privileges."))
				self.gladefile.get_widget('cfg_Qemu_usbmode_check').set_active(False)
				return True

		self.show_window('')
		self.curtain_up()
		old_val = self.maintree.get_selection().cfg.usbdevlist
		self.maintree.get_selection().cfg.set('usbdevlist='+devlist.rstrip(' '))
		self.maintree.get_selection().update_usbdevlist(devlist.rstrip(' '), old_val)
		return True








	def signals(self):
		self.gladefile.signal_autoconnect(self)

	""" ******************************************************** """
	"""							     """
	""" TIMERS						     """
	"""							     """
	"""							     """
	""" ******************************************************** """

	def timers(self):
		gobject.timeout_add(1000, self.check_joblist)
		gobject.timeout_add(500, self.check_topology_scroll)

	def check_topology_scroll(self):
		if self.topology:
			self.topology.x_adj = self.gladefile.get_widget('topology_scrolled').get_hadjustment().get_value()
			self.topology.y_adj = self.gladefile.get_widget('topology_scrolled').get_vadjustment().get_value()
			return True

	def check_joblist(self, force=False):
		new_ps = []
		for b in self.brickfactory.bricks:
			if b.proc is not None:
				if b.homehost and b.homehost.connected:
					ret = None
				else:
					ret = b.proc.poll()
				if ret is None:
					new_ps.append(b)
				else:
					b.poweroff()
					b.gui_changed = True

		if self.ps != new_ps or force==True:
			self.ps = new_ps
			self.bricks = []
			self.running_bricks.model.clear()
			for b in self.ps:
				iter = self.running_bricks.new_row()
				if (b.pid == -10):
					pid = "python-thread   "
				elif b.homehost:
					pid = "Remote"
				else:
					pid = str(b.pid)
				self.running_bricks.set_value(iter, 0,gtk.gdk.pixbuf_new_from_file_at_size(b.icon.get_img(), 48, 48))
				self.running_bricks.set_value(iter,1,pid)
				self.running_bricks.set_value(iter,2,b.get_type())
				self.running_bricks.set_value(iter,3,b.name)
			self.debug("proc list updated")
		new_rhosts = []
		if self.brickfactory.remotehosts_changed:
			#TODO: define/Use VBTree.redraw() for this
			self.remote_hosts_tree.model.clear()
			for r in self.brickfactory.remote_hosts:
				iter = self.remote_hosts_tree.new_row()
				if (r.connected):
					self.remote_hosts_tree.set_value(iter, 0, gtk.gdk.pixbuf_new_from_file_at_size("/usr/share/pixmaps/Connect.png", 48, 48) )
				else:
					self.remote_hosts_tree.set_value(iter, 0, gtk.gdk.pixbuf_new_from_file_at_size("/usr/share/pixmaps/Disconnect.png", 48, 48) )
				self.remote_hosts_tree.set_value(iter, 1, r.addr[0]+":"+str(r.addr[1]))
				self.remote_hosts_tree.set_value(iter, 2, str(r.num_bricks()))
				if r.autoconnect:
					self.remote_hosts_tree.set_value(iter, 3, "Yes")
				else:
					self.remote_hosts_tree.set_value(iter, 3, "No")
				self.brickfactory.remotehosts_changed=False


		self.widg['main_win'].set_title("Virtualbricks ( "+self.brickfactory.settings.get('current_project')+ " ID: " + self.brickfactory.project_parms["id"] + " )")

		return True

	def draw_topology(self, export=None):
		self.maintree.order()
		if self.gladefile.get_widget('topology_tb').get_active():
			orientation = "TB"
		else:
			orientation = "LR"

		self.topology = Topology(self.gladefile.get_widget('image_topology'), self.brickfactory.bricksmodel, 1.00, orientation, export, self.brickfactory.settings.get("bricksdirectory")+"/")

	def user_wait_action(self, action, *args):
		self.gladefile.get_widget("window_userwait").show_all()
		self.gladefile.get_widget("main_win").set_sensitive(False)
		thread = Thread(target=action, args=args)
		gobject.timeout_add(200, self.user_wait_action_timer, thread)
		thread.start()

	def user_wait_action_timer(self, thread):
		is_alive = thread.isAlive()
		if not is_alive:
			self.gladefile.get_widget("window_userwait").hide()
			self.gladefile.get_widget("main_win").set_sensitive(True)
		else:
			self.gladefile.get_widget("userwait_progressbar").pulse()
		return is_alive
