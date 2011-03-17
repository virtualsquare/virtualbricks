#!/usr/bin/python
# -*- coding: utf-8 -*-

##	Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
##	Copyright (C) 2011 Virtualbricks team
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

import gobject
import gtk
import os
import re
import subprocess
import sys
import time
from traceback import format_exception

import virtualbricks_BrickFactory as BrickFactory
import virtualbricks_Global as Global
from virtualbricks_GUILogger import GUILogger
import virtualbricks_Models as Models
import virtualbricks_Settings as Settings
import virtualbricks_Events as Events
from threading import Thread
from virtualbricks_Graphics import *

#Gettext stuff
try:
	import gettext
	import locale
except:
	print "locale and/or gettext for language support not installed"
	sys.exit(1)

APP = 'virtualbricks'
#DIR = 'locale'
DIR = '/usr/share/locale'
#print "DIR: " + DIR
locale.setlocale(locale.LC_ALL, '')
for module in gtk.glade, gettext:
	module.bindtextdomain(APP, DIR)
	module.textdomain(APP)

import __builtin__
__builtin__._ = gettext.gettext
#_ = gettext.gettext

class MyTray(gtk.StatusIcon):

	def __init__(self):
		gtk.StatusIcon.__init__(self)
		self.enabled = False
		self.win_hide = False

	def set_enabled(self, val):
		self.enabled=val

	def set_window_is_hide(self, val):
		self.win_hide=val

	def get_enabled(self):
		return self.enabled

	def get_window_is_hide(self):
		return self.win_hide

class VBuserwait(Thread):
	def __init__(self, call, args=[]):
		self.action = call
		self.args = args
		Thread.__init__(self)
		self.running = True
	def run(self):
		print "thread started"
		self.action(*self.args)
		print "thread finished"
		self.running = False

class VBGUI(GUILogger, gobject.GObject):
	def __init__(self):
		gobject.GObject.__init__(self)
		GUILogger.__init__(self)

		if not os.access(Settings.MYPATH, os.X_OK):
			os.mkdir(Settings.MYPATH)

		self.topology = None
		try:
			self.gladefile = gtk.glade.XML('/usr/share/virtualbricks/virtualbricks.glade')
		except:
			self.critical("Cannot open required file 'virtualbricks.glade'")

		self.widg = self.get_widgets(self.widgetnames())

		self.info("Starting VirtualBricks!")

		gtk.gdk.threads_init()

		self.brickfactory = BrickFactory.BrickFactory(self, True)

		self.brickfactory.bricksmodel.connect("brick-added", self.cb_brick_added)
		self.brickfactory.bricksmodel.connect("brick-deleted", self.cb_brick_deleted)

		self._engine_closed = self.brickfactory.connect("engine-closed", self.quit_from_commandline)

		self.brickfactory.connect("brick-stopped", self.cb_brick_stopped)
		self.brickfactory.connect("brick-started", self.cb_brick_started)

		self.brickfactory.connect("event-stopped", self.cb_event_stopped)

		self.brickfactory.eventsmodel.connect("event-added", self.cb_event_added)
		self.brickfactory.eventsmodel.connect("event-deleted", self.cb_event_deleted)

		self.availmodel = None
		self.addedmodel = None
		self.shcommandsmodel = None

		self.draw_topology()
		self.brickfactory.start()

		self.gladefile.get_widget("messages_textview").set_buffer(self.messages_buffer)

		self.widg['main_win'].show()

		self.ps = []
		self.bricks = []

		''' Don't remove me, I am useful after config, when treeview may lose focus and selection. '''
		self.last_known_selected_brick = None
		self.last_known_selected_event = None
		self.gladefile.get_widget("main_win").connect("delete-event", self.delete_event)
		self.config = self.brickfactory.settings
		self.signals()
		self.timers()
		self.topology_active = False

		self.sockscombo = dict()
		self.set_nonsensitivegroup(['cfg_Wirefilter_lostburst_text', 'cfg_Wirefilter_mtu_text'])

		self.running_bricks = self.treestore('treeview_joblist', [gtk.gdk.Pixbuf,
			gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING],
			['',_('PID'),_('Type'),_('Name')])

		columns = [_('Icon'), _('Status'), _('Type'), _('Name'), _('Parameters')]
		tree = self.gladefile.get_widget('treeview_bookmarks')
		tree.set_model(self.brickfactory.bricksmodel)
		for name in columns:
			col = gtk.TreeViewColumn(name)
			if name != _('Icon'):
				elem = gtk.CellRendererText()
				col.pack_start(elem, False)
			else:
				elem = gtk.CellRendererPixbuf()
				col.pack_start(elem, False)
			col.set_cell_data_func(elem, self.brick_to_cell)
			tree.append_column(col)

		eventstree = self.gladefile.get_widget('treeview_events_bookmarks')
		eventstree.set_model(self.brickfactory.eventsmodel)
		for name in columns:
			col = gtk.TreeViewColumn(name)
			if name != _('Icon'):
				elem = gtk.CellRendererText()
				col.pack_start(elem, False)
			else:
				elem = gtk.CellRendererPixbuf()
				col.pack_start(elem, False)
			col.set_cell_data_func(elem, self.event_to_cell)
			eventstree.append_column(col)

		# associate Drag and Drop action
		tree = self.gladefile.get_widget('treeview_bookmarks')
		tree.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, [('BRICK', gtk.TARGET_SAME_WIDGET | gtk.TARGET_SAME_APP, 0)], gtk.gdk.ACTION_DEFAULT | gtk.gdk.ACTION_COPY)
		tree.enable_model_drag_dest([('BRICK', gtk.TARGET_SAME_WIDGET | gtk.TARGET_SAME_APP, 0)], gtk.gdk.ACTION_DEFAULT| gtk.gdk.ACTION_PRIVATE )

		eventstree = self.gladefile.get_widget('treeview_events_bookmarks')
		eventstree.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, [('EVENT', gtk.TARGET_SAME_WIDGET | gtk.TARGET_SAME_APP, 0)], gtk.gdk.ACTION_DEFAULT | gtk.gdk.ACTION_COPY)
		eventstree.enable_model_drag_dest([('EVENT', gtk.TARGET_SAME_WIDGET | gtk.TARGET_SAME_APP, 0)], gtk.gdk.ACTION_DEFAULT| gtk.gdk.ACTION_PRIVATE )

		self.vmplugs = self.treestore('treeview_networkcards', [gobject.TYPE_STRING,
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
		self.brick_selected = None
		self.event_selected = None

		try:
			gtk.main()
		except KeyboardInterrupt:
			self.quit()

	def brick_to_cell(self, column, cell, model, iter):
		brick = model.get_value(iter, Models.BricksModel.BRICK_IDX)
		assert brick is not None
		if column.get_title() == _('Icon'):
			if brick.proc is not None:
				icon = gtk.gdk.pixbuf_new_from_file_at_size(brick.icon.get_img(), 48,
					48)
				cell.set_property('pixbuf', icon)
			elif not brick.properly_connected():
				cell.set_property('stock-id', gtk.STOCK_DIALOG_ERROR)
				cell.set_property('stock-size', gtk.ICON_SIZE_LARGE_TOOLBAR)
			else:
				icon = gtk.gdk.pixbuf_new_from_file_at_size(brick.icon.get_img(), 48,
						48)
				cell.set_property('pixbuf', icon)
		elif column.get_title() == _('Status'):
			cell.set_property('text', brick.get_state())
		elif column.get_title() == _('Type'):
			cell.set_property('text', brick.get_type())
		elif column.get_title() == _('Name'):
			cell.set_property('text', brick.name)
		elif column.get_title() == _('Parameters'):
			cell.set_property('text', brick.get_parameters())
		else:
			raise NotImplemented()

	def event_to_cell(self, column, cell, model, iter):
		event = model.get_value(iter, Models.EventsModel.EVENT_IDX)
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

	def get_selected_bookmark(self):
		tree = self.gladefile.get_widget('treeview_bookmarks');
		path = tree.get_cursor()[0]

		if path is None:
			'''
			' Default to something that makes sense,
			' otherwise on_config_ok will be broken
			' when treeviews lose their selections.
			'''
			return self.last_known_selected_brick

		model = tree.get_model()
		iter = model.get_iter(path)
		name = model.get_value(iter, Models.BricksModel.BRICK_IDX).name
		self.last_known_selected_brick = self.brickfactory.getbrickbyname(name)
		return self.last_known_selected_brick

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
		name = model.get_value(iter, Models.EventsModel.EVENT_IDX).name
		self.last_known_selected_event = self.brickfactory.geteventbyname(name)
		return self.last_known_selected_event

	""" ******************************************************** """
	""" Signal handlers										  """
	""" ******************************************************** """

	def cb_brick_added(self, model, name):
		self.draw_topology()
		pass

	def cb_brick_deleted(self, model, name):
		self.draw_topology()

	def cb_brick_stopped(self, model, name=""):
		self.draw_topology()
		self.systray_blinking(None, False)

	def cb_brick_started(self, model, name=""):
		self.draw_topology()

	def cb_event_added(self, model, name):
		pass

	def cb_event_deleted(self, model, name):
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
				widget.set_text(e.cfg[key])

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "treeview")
			if (widget is not None):
				self.shcommandsmodel = None
				self.shcommandsmodel = gtk.ListStore (str, bool)

				for a in e.cfg[key]:
					iter = self.shcommandsmodel.append([a, not isinstance(a, BrickFactory.VbShellCommand)])

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

	def config_brick_prepare(self):
		b = self.brick_selected
		# Fill socks combobox
		for k in self.sockscombo_names():
			combo = Settings.ComboBox(self.gladefile.get_widget(k))
			opt=dict()
			# add Ad-hoc host only to the vmehternet
			if k == 'sockscombo_vmethernet':
				opt['Host-only ad hoc network']='_hostonly'

			for so in self.brickfactory.socks:
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
		qemuarch = Settings.ComboBox(self.gladefile.get_widget("cfg_Qemu_argv0_combo"))
		opt = dict()
		for arch in found:
			if arch.startswith('qemu-system-'):
				opt[arch.split('qemu-system-')[1]] = arch
		qemuarch.populate(opt, 'i386')
		dicts['argv0']=opt

		#SNDCARD COMBO
		sndhw = Settings.ComboBox(self.gladefile.get_widget("cfg_Qemu_soundhw_combo"))
		opt = dict()
		opt['no audio']=""
		opt['PC speaker']="pcspk"
		opt['Creative Sound Blaster 16'] = "sb16"
		opt['Intel 82801AA AC97 Audio'] = "ac97"
		opt['ENSONIQ AudioPCI ES1370'] = "es1370"
		dicts['soundhw']=opt
		sndhw.populate(opt, "")
		Settings.ComboBox(self.gladefile.get_widget("cfg_Qemu_soundhw_combo")).select('Intel 82801AA AC97 Audio')

		#device COMBO
		devices = Settings.ComboBox(self.gladefile.get_widget("cfg_Qemu_device_combo"))
		opt = dict()
		opt['NO']=""
		opt['cdrom']="/dev/cdrom"
		dicts['device']=opt
		devices.populate(opt, "")
		Settings.ComboBox(self.gladefile.get_widget("cfg_Qemu_device_combo")).select('NO')

		#boot COMBO
		boot_c = Settings.ComboBox(self.gladefile.get_widget("cfg_Qemu_boot_combo"))
		opt = dict()
		opt['HD1']=""
		opt['FLOPPY'] = "a"
		opt['CDROM'] = "d"
		dicts['boot']=opt
		boot_c.populate(opt, "")
		Settings.ComboBox(self.gladefile.get_widget("cfg_Qemu_boot_combo")).select('HD1')

		# Qemu VMplugs:
		Settings.ComboBox(self.gladefile.get_widget("vmplug_model")).populate(self.qemu_eth_model())
		Settings.ComboBox(self.gladefile.get_widget("vmplug_model")).select('rtl8139')
		if len(b.plugs) == 0:
			self.gladefile.get_widget('radiobutton_network_nonet').set_active(True)
			self.set_nonsensitivegroup(['vmplug_model', 'sockscombo_vmethernet','vmplug_macaddr','randmac',
				'button_network_netcard_add','button_network_edit','button_network_remove', 'treeview_networkcards'])
		else:
			self.gladefile.get_widget('radiobutton_network_usermode').set_active(True)
			self.set_sensitivegroup(['vmplug_model', 'sockscombo_vmethernet','vmplug_macaddr','randmac',
				'button_network_netcard_add','button_network_edit','button_network_remove', 'treeview_networkcards'])

		# Qemu: check if KVM is checkable
		if (b.get_type()=="Qemu"):
			if self.config.kvm:
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_sensitive(True)
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_label("KVM")
			else:
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_sensitive(False)
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_label("KVM is disabled from Properties")
				b.cfg.kvm=False



		self.update_vmplugs_tree()

		for key in b.cfg.keys():
			t = b.get_type()
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "text")
			if (widget is not None):
				widget.set_text(b.cfg[key])

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "spinint")
			if (widget is not None and len(b.cfg[key]) > 0):
				widget.set_value(int(b.cfg[key]))

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "spinfloat")
			if (widget is not None):
				widget.set_value(float(b.cfg[key]))

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "check")
			if (widget is not None):
				if (b.cfg[key] == "*"):
					widget.set_active(True)
				else:
					if key is "kvm" and self.config.kvm and b.cfg.kvm=="*":
						self.gladefile.get_widget('cfg_Qemu_kvm_check').set_active(True)
					else:
						widget.set_active(False)

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "combo")
			if (widget is not None and dicts.has_key(key)):
				for k, v in dicts[key].iteritems():
					if (v==b.cfg[key]):
						Settings.ComboBox(self.gladefile.get_widget("cfg_"+t+"_"+key+"_combo")).select(k)

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
			b = self.brick_selected
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
				if (txt):
					parameters[key] = txt[0]

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "combo")
			if (widget is not None):
				combo = Settings.ComboBox(widget)
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
				pass

			if t == 'Tap':
				sel = Settings.ComboBox(self.gladefile.get_widget('sockscombo_tap')).get_selected()
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


			if t == 'TunnelConnect':
				sel = Settings.ComboBox(self.gladefile.get_widget('sockscombo_tunnelc')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[0].connect(so)
			if t == 'TunnelListen':
				sel = Settings.ComboBox(self.gladefile.get_widget('sockscombo_tunnell')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[0].connect(so)
			if t == 'Wire':
				sel = Settings.ComboBox(self.gladefile.get_widget('sockscombo_wire0')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[0].connect(so)
				sel = Settings.ComboBox(self.gladefile.get_widget('sockscombo_wire1')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[1].connect(so)
			if t == 'Wirefilter':
				sel = Settings.ComboBox(self.gladefile.get_widget('sockscombo_wirefilter0')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[0].connect(so)
				sel = Settings.ComboBox(self.gladefile.get_widget('sockscombo_wirefilter1')).get_selected()
				for so in self.brickfactory.socks:
					if sel == so.nickname:
						b.plugs[1].connect(so)

		fmt_params = ['%s=%s' % (key,value) for key, value in parameters.iteritems()]
		b.configure(fmt_params)
		for key, value in parameters.iteritems():
			callback = b.get_cbset(key)
			if callable(callback):
				callback(b, value)

	def config_brick_cancel(self):
		self.curtain_down()


	""" ******************************************************** """
	"""														  """
	""" MISC / WINDOWS BEHAVIOR								  """
	"""														  """
	"""														  """
	""" ******************************************************** """


	def start_systray(self):
		systray = getattr(self, "statusicon", None)
		if systray is None:
			self.statusicon = MyTray()
			self.statusicon.set_from_file("/usr/share/pixmaps/virtualbricks.png")
			self.statusicon.set_tooltip("VirtualBricks Visible")
			self.statusicon.connect('activate', self.status_clicked )
			systray_menu = self.gladefile.get_widget("systray_menu")
			self.statusicon.connect('popup-menu', self.systray_menu_popup, systray_menu)

		if not self.statusicon.get_enabled():
			self.statusicon.set_enabled(True)
			self.statusicon.set_visible(True)

	def systray_menu_popup(self, widget, button, time, data = None):
		if button == 3 and data:
			data.show_all()
			data.popup(None, None, None, 3, time)

	def stop_systray(self):
		if self.statusicon.get_enabled():
			self.statusicon.set_visible(False)
			self.statusicon.set_enabled(False)

	def systray_blinking(self, args=None, disable=False):
		if not self.statusicon or self.statusicon.get_enabled() == False:
			return
		if disable:
			self.statusicon.set_blinking(False)
			return
		if not self.statusicon.get_blinking():
			self.statusicon.set_blinking(True)

	def delete_event(self,window,event):
		#don't delete; hide instead
		if self.config.systray and self.statusicon.get_enabled():
			self.gladefile.get_widget("main_win").hide_on_delete()
			self.statusicon.set_window_is_hide(True)
			self.statusicon.set_tooltip("VirtualBricks Hidden")
		else:
			self.quit()
		return True

	def status_clicked(self,status=None):
		#unhide the window
		if self.statusicon.get_blinking():
			self.systray_blinking(None, True)
			return
		if self.statusicon.get_window_is_hide() or status == True:
			self.gladefile.get_widget("main_win").show_all()
			self.statusicon.set_tooltip("the window is visible")
			self.statusicon.set_window_is_hide(False)
		else:
			self.gladefile.get_widget("main_win").hide()
			self.statusicon.set_window_is_hide(True)

	def curtain_is_down(self):
		self.debug(self.curtain.get_position())
		return (self.curtain.get_position()>660)

	def curtain_down(self):
		self.curtain.set_position(99999)
		self.gladefile.get_widget('label_showhidesettings').set_text(_('Show Settings'))

	def curtain_up(self):
		self.debug("Old position: %d", self.curtain.get_position())
		self.gladefile.get_widget('box_vmconfig').hide()
		self.gladefile.get_widget('box_tapconfig').hide()
		self.gladefile.get_widget('box_tunnellconfig').hide()
		self.gladefile.get_widget('box_tunnelcconfig').hide()
		self.gladefile.get_widget('box_wireconfig').hide()
		self.gladefile.get_widget('box_wirefilterconfig').hide()
		self.gladefile.get_widget('box_switchconfig').hide()
		self.gladefile.get_widget('box_eventconfig').hide()

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
				self.gladefile.get_widget('label_showhidesettings').set_text(_('Hide Settings'))
			return

		if self.brick_selected is None:
			return

		if self.brick_selected.get_type() == 'Switch':
			self.debug("switch config")
			ww = self.gladefile.get_widget('box_switchconfig')
			wg.set_position(589)
		elif self.brick_selected.get_type() == 'Qemu':
			self.debug("qemu config")
			ww = self.gladefile.get_widget('box_vmconfig')
			wg.set_position(245)
		elif self.brick_selected.get_type() == 'Tap':
			self.debug("tap config")
			ww = self.gladefile.get_widget('box_tapconfig')
			wg.set_position(513)
		elif self.brick_selected.get_type() == 'Wire':
			self.debug("wire config")
			ww = self.gladefile.get_widget('box_wireconfig')
			wg.set_position(606)
		elif self.brick_selected.get_type() == 'Wirefilter':
			self.debug("wirefilter config")
			ww = self.gladefile.get_widget('box_wirefilterconfig')
			wg.set_position(424)
		elif self.brick_selected.get_type() == 'TunnelConnect':
			self.debug("tunnelc config")
			ww = self.gladefile.get_widget('box_tunnelcconfig')
			wg.set_position(424)
		elif self.brick_selected.get_type() == 'TunnelListen':
			self.debug("tunnell config")
			ww = self.gladefile.get_widget('box_tunnellconfig')
			wg.set_position(424)
		self.config_brick_prepare()
		ww.show_all()

		self.gladefile.get_widget('label_showhidesettings').set_text(_('Hide Settings'))

	def get_tree_selected(self, tree, store, pthinfo, idx):
		"""TODO replace get_treeselected by get_tree_selected"""
		if pthinfo is not None:
			path, col, cellx, celly = pthinfo
			tree.grab_focus()
			tree.set_cursor(path, col, 0)
			iter = store.get_iter(path)
			brick = store.get_value(iter, idx)
			self.config_last_iter = iter
			return brick

	def get_treeselected(self, tree, store, pthinfo, c):
		if pthinfo is not None:
			path, col, cellx, celly = pthinfo
			tree.grab_focus()
			tree.set_cursor(path, col, 0)
			iter = store.get_iter(path)
			name = store.get_value(iter, c)
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
		#gtk.mainquit()
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

	def treestore(self, tree_name, fields, names):
		tree = self.gladefile.get_widget(tree_name)
		ret = gtk.TreeStore(*fields)
		tree.set_model(ret)
		for idx, name in enumerate(names):
			col = gtk.TreeViewColumn(name)
			if fields[idx] == gtk.gdk.Pixbuf:
				elem = gtk.CellRendererPixbuf()
				col.pack_start(elem, False)
				col.add_attribute(elem, 'pixbuf', idx)
			else:
	 			elem = gtk.CellRendererText()
				col.pack_start(elem, False)
				col.add_attribute(elem, 'text', idx)
			tree.append_column(col)
		return ret

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
		'dialog_confirm'
		]
	def sockscombo_names(self):
		return [
		'sockscombo_vmethernet',
		'sockscombo_tap',
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
		GUILogger.critical(self, text, *args, **kwargs)
		for line in traceback:
			GUILogger.critical(self, line.rstrip('\n'))
		sys.exit(1)

	def error(self, text, *args, **kwargs):
		GUILogger.error(self, text, *args, **kwargs)
		text = text % args
		self.show_error(text)

	def show_error(self, text):
		def on_response(widget, response_id=None, data=None):
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
		#pixbuf= pixbuf.scale(pixbuf, 0, 0, 48, 48, 0, 0, height/new_height, width/new_width, gtk.gdk.INTERP_BILINEAR)
		#print "%s %d %d" % (filename, new_height, new_width)
		return pixbuf


	""" ******************************************************** """
	"""														  """
	""" EVENTS / SIGNALS										 """
	"""														  """
	"""														  """
	""" ******************************************************** """

	def systray_show_window_cb(self, widget=None, data=""):
		self.status_clicked(True)

	def systray_hide_window_cb(self, widget=None, data=""):
		self.status_clicked(False)


	def on_window1_destroy(self, widget=None, data=""):
		self.quit()

	def on_windown_destroy(self, widget=None, data=""):
		widget.hide()
		return True

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
		for ntype in ['Switch','Tap','Wire','Wirefilter','TunnelConnect','TunnelListen','Qemu']:
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
		try:
			self.brickfactory.newbrick(ntype, name)
		except BrickFactory.InvalidNameException:
			self.error("Cannot create brick: Invalid name.")
		else:
			self.debug("Created successfully")

	def on_newevent_cancel(self, widget=None, data=""):
		self.curtain_down()
		self.show_window('')

	def on_newevent_ok(self, widget=None, data=""):

		eventname = self.gladefile.get_widget('text_neweventname').get_text()
		if eventname == '':
			return

		validname = BrickFactory.ValidName(eventname)
		if  validname == None:
			self.show_error(_("The name \"")+eventname+_("\" has forbidden format."))
			return
		elif validname != eventname:
			self.gladefile.get_widget('text_neweventname').set_text(validname)
			self.show_error(_("The name \"")+eventname+_("\" has been adapted to \"")+validname+"\".")
			eventname=validname
		if self.brickfactory.isNameFree(eventname) == False:
			self.show_error(_("An event named \"")+eventname+_("\" already exist."))
			return

		self.show_window('')
		self.curtain_down()

		ntype = self.selected_event_type()

		try:
			if(ntype == 'ShellCommand'):

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

			elif ntype in ['BrickStart', 'BrickStop']:

				columns = (COL_ICON, COL_TYPE, COL_NAME, COL_CONFIG) = range(4)

				availbricks = self.gladefile.get_widget('bricks_available_treeview')
				addedbricks = self.gladefile.get_widget('bricks_added_treeview')

				self.availmodel = gtk.ListStore (gtk.gdk.Pixbuf, str, str, str)
				self.addedmodel = gtk.ListStore (gtk.gdk.Pixbuf, str, str, str)

				for brick in self.brickfactory.bricks:
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
				else:
					self.gladefile.\
				get_widget('dialog_event_bricks_select').\
				set_title(_("Bricks to add to the event to be stopped"))

				self.gladefile.get_widget('dialog_event_bricks_select').show_all()

		except BrickFactory.InvalidNameException:
			self.error("Cannot create event: Invalid name.")

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
		self.config_brick_confirm()
		self.curtain_down()

	def on_generic_event(self, widget=None, data=""):
		self.systray_blinking(None, True)

	def set_sensitivegroup(self,l):
		for i in l:
			w = self.gladefile.get_widget(i)
			w.set_sensitive(True)

	def set_nonsensitivegroup(self,l):
		for i in l:
			w = self.gladefile.get_widget(i)
			w.set_sensitive(False)

	def on_gilbert_toggle(self, widget=None, data=""):
		currentwidget = self.gladefile.get_widget('cfg_Wirefilter_lostburst_text')
		if widget.get_active():
			currentwidget.set_sensitive(True)
			currentwidget.set_text("0")
		else:
			currentwidget.set_text("")
			currentwidget.set_sensitive(False)

	def on_mtu_toggle(self, widget=None, data=""):
		currentwidget = self.gladefile.get_widget('cfg_Wirefilter_mtu_text')
		if widget.get_active():
			currentwidget.set_sensitive(True)
			currentwidget.set_text("1024")
		else:
			currentwidget.set_text("")
			currentwidget.set_sensitive(False)


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
		print "on_item_settings_autoshow_activate undefined!"
		pass
	def on_item_settings_autohide_activate(self, widget=None, data=""):
		print "on_item_settings_autohide_activate undefined!"
		pass

	def on_item_about_activate(self, widget=None, data=""):
		self.show_window('dialog_about1')
		self.curtain_down()
		pass
	def on_toolbutton_launchxterm_clicked(self, widget=None, data=""):
		print "on_toolbutton_launchxterm_clicked undefined!"
		pass

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
			if e.active == False:
				e.poweron()

	def on_toolbutton_stop_all_events_clicked(self, widget=None, data=""):
		self.curtain_down()
		for e in self.brickfactory.events:
			if e.active == True:
				e.poweroff()

	def on_mainwindow_dropaction(self, widget, drag_context, x, y, selection_data, info, timestamp):
		tree = self.gladefile.get_widget('treeview_bookmarks');
		x = int(x)
		y = int(y)
		pthinfo = tree.get_path_at_pos(x, y)
		dropbrick = self.get_tree_selected(tree, self.brickfactory.bricksmodel,
			pthinfo, Models.BricksModel.BRICK_IDX)
		#print x, y, pthinfo, dropbrick.name

		drop_info = tree.get_dest_row_at_pos(x, y)
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

		if dropbrick and dropbrick != self.Dragging:
			self.debug("drag&drop: %s onto %s", self.Dragging.name, dropbrick.name)
			res = False
			if (len(dropbrick.socks) > 0):
				res = self.Dragging.connect(dropbrick.socks[0])
			elif (len(self.Dragging.socks) > 0):
				res = dropbrick.connect(self.Dragging.socks[0])
			if (res):
				drag_context.finish(True, False, timestamp)
			else:
				drag_context.finish(False, False, timestamp)
		else:
			drag_context.finish(False, False, timestamp)
		self.Dragging = None

	def show_brickactions(self):
		if self.brick_selected.get_type() == "Qemu":
			self.set_sensitivegroup(['vmresume'])
		else:
			self.set_nonsensitivegroup(['vmresume'])

		self.gladefile.get_widget("brickaction_name").set_label(self.brick_selected.name)
		self.show_window('menu_brickactions')

	def show_eventactions(self):
		#if self.event_selected.get_type() == "Event":
		self.gladefile.get_widget("eventaction_name").set_label(self.event_selected.name)
		self.show_window('menu_eventactions')

	def on_treeview_bookmarks_button_release_event(self, widget=None, event=None, data=""):
		self.brick_selected = self.get_selected_bookmark()
		if self.brick_selected is None:
			return

		self.curtain_down()
		tree = self.gladefile.get_widget('treeview_bookmarks');
		path = tree.get_cursor()[0]
		#print "on_treeview_bookmarks_button_release_event"
		if path is None:
			#print "nothing selected!"
			return

		iter = tree.get_model().get_iter(path)
		name = tree.get_model().get_value(iter, Models.BricksModel.BRICK_IDX).name
		self.Dragging = self.brickfactory.getbrickbyname(name)
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
		name = tree.get_model().get_value(iter, Models.EventsModel.EVENT_IDX).name
		self.Dragging = self.brickfactory.geteventbyname(name)
		if event.button == 3:
			self.show_eventactions()

	def on_treeview_drag_get_data(self, tree, context, selection, target_id, etime):
		self.debug("in get data?!")
		self.Dragging = self.get_tree_selected(tree, self.brickfactory.bricksmodel,
				pthinfo, Models.BricksModel.BRICK_IDX)
		#context.set_icon_pixbuf('./'+self.Dragging.get_type()+'.png')

	def on_treeview_bookmarks_cursor_changed(self, widget=None, event=None, data=""):
		self.curtain_down()

	def on_treeview_bookmarks_row_activated_event(self, widget=None, event=None, data=""):
		self.tree_startstop(widget, event, data)
		self.curtain_down()

	def on_treeview_events_bookmarks_row_activated_event(self, widget=None, event=None, data=""):
		self.events_tree_startstop(widget, event, data)
		self.curtain_down()

	def on_treeview_bookmarks_focus_out(self, widget=None, event=None , data=""):
		self.curtain_down()

	def tree_startstop(self, widget=None, event=None, data=""):
		self.curtain_down()
		self.user_wait_action(self.startstop_brick, [self.brick_selected])

	def events_tree_startstop(self, widget=None, event=None, data=""):
		self.curtain_down()
		self.user_wait_action(self.events_startstop_brick, [self.event_selected])

	def events_startstop_brick(self, e):
		if(e.get_type() == 'Event'):
			if(e.active == True):
				print "Power OFF"
				e.poweroff()
			else:
				print "Power ON"
				e.poweron()
			return

	def startstop_brick(self, b):
		if b.proc is not None:
			print "Power OFF"
			b.poweroff()
		else:
			print "Power ON"
			if b.get_type() == "Qemu":
				b.cfg.loadvm='' #prevent restore from saved state
			try:
				b.poweron()
			except(BrickFactory.BadConfigException):
				b.gui_changed=True
				self.show_error("Cannot start this Brick: Brick not configured, yet.")
			except(BrickFactory.NotConnectedException):
				self.show_error("Cannot start this Brick: Brick not connected.")
			except(BrickFactory.LinkloopException):
				if (self.config.erroronloop):
					self.show_error("Loop link detected: aborting operation. If you want to start a looped network, disable the check loop feature in the general settings")
					b.poweroff()
			except(BrickFactory.DiskLockedException):
				b.gui_changed=True
				#self.show_error("Disk used is loked by another VM")
				print "Disk used by the VM is locked by another machine"
				b.poweroff()

	def on_treeview_bootimages_button_press_event(self, widget=None, data=""):
		print "on_treeview_bootimages_button_press_event undefined!"
		pass
	def on_treeview_bootimages_cursor_changed(self, widget=None, data=""):
		print "on_treeview_bootimages_cursor_changed undefined!"
		pass
	def on_treeview_bootimages_row_activated_event(self, widget=None, data=""):
		print "on_treeview_bootimages_row_activated_event undefined!"
		pass
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
		print "on_treeview_joblist_row_activated_event undefined!"
		pass

	def on_button_togglesettings_clicked(self, widget=None, data=""):
		if self.curtain_is_down():
			self.curtain_up()
			self.debug("up")
		else:
			self.curtain_down()
			self.debug("down")

	def on_filechooserdialog_openimage_response(self, widget=None, data=""):
		print "on_filechooserdialog_openimage_response undefined!"
		pass
	def on_button_openimage_cancel_clicked(self, widget=None, data=""):
		print "on_button_openimage_cancel_clicked undefined!"
		pass
	def on_button_openimage_open_clicked(self, widget=None, data=""):
		print "on_button_openimage_open_clicked undefined!"
		pass

	def on_dialog_settings_delete_event(self, widget=None, event=None, data=""):
		"""we could use deletable property but deletable is only available in
		GTK+ 2.10 and above"""
		widget.hide()
		return True

	def on_dialog_settings_response(self, widget=None, response=0, data=""):
		if response == gtk.RESPONSE_CANCEL:
			widget.hide()
			return

		if response == gtk.RESPONSE_APPLY or response == gtk.RESPONSE_OK:
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


	def on_treeview_cdromdrives_row_activated(self, widget=None, data=""):
		print "on_treeview_cdromdrives_row_activated undefined!"
		pass
	def on_button_settings_add_cdevice_clicked(self, widget=None, data=""):
		print "on_button_settings_add_cdevice_clicked undefined!"
		pass
	def on_button_settings_rem_cdevice_clicked(self, widget=None, data=""):
		print "on_button_settings_rem_cdevice_clicked undefined!"
		pass
	def on_treeview_qemupaths_row_activated(self, widget=None, data=""):
		print "on_treeview_qemupaths_row_activated undefined!"
		pass
	def on_button_settings_add_qemubin_clicked(self, widget=None, data=""):
		print "on_button_settings_add_qemubin_clicked undefined!"
		pass
	def on_button_settings_rem_qemubin_clicked(self, widget=None, data=""):
		print "on_button_settings_rem_qemubin_clicked undefined!"
		pass
	def on_dialog_bookmarks_response(self, widget=None, data=""):
		print "on_dialog_bookmarks_response undefined!"
		pass
	def on_edit_bookmark_activate(self, widget=None, data=""):
		print "on_edit_bookmark_activate undefined!"
		pass
	def on_bookmark_info_activate(self, widget=None, data=""):
		print "on_bookmark_info_activate undefined!"
		pass
	def on_delete_bookmark_activate(self, widget=None, data=""):
		print "on_delete_bookmark_activate undefined!"
		pass
	def on_dialog_about_response(self, widget=None, data=""):
		self.widg['dialog_about1'].hide()
		return True
	def on_dialog_create_image_response(self, widget=None, data=""):
		print "on_dialog_create_image_response undefined!"
		pass
	def on_filechooserbutton_newimage_dest_selection_changed(self, widget=None, data=""):
		print "on_filechooserbutton_newimage_dest_selection_changed undefined!"
		pass
	def on_filechooserbutton_newimage_dest_current_folder_changed(self, widget=None, data=""):
		print "on_filechooserbutton_newimage_dest_current_folder_changed undefined!"
		pass
	def on_entry_newimage_name_changed(self, widget=None, data=""):
		print "on_entry_newimage_name_changed undefined!"
		pass
	def on_combobox_newimage_format_changed(self, widget=None, data=""):
		print "on_combobox_newimage_format_changed undefined!"
		pass
	def on_spinbutton_newimage_size_changed(self, widget=None, data=""):
		print "on_spinbutton_newimage_size_changed undefined!"
		pass
	def on_combobox_newimage_sizeunit_changed(self, widget=None, data=""):
		print "on_combobox_newimage_sizeunit_changed undefined!"
		pass
	def on_item_create_image_activate(self, widget=None, data=""):
		self.curtain_down()
		self.gladefile.get_widget('combobox_newimage_format').set_active(0)
		self.gladefile.get_widget('combobox_newimage_sizeunit').set_active(1)
		self.show_window('dialog_create_image')

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
		if filename=="":
			self.show_error("Choose a filename first!")
			return
		if img_format == "Auto":
			img_format = "raw"
		os.system('%s -f %s %s %s' % (cmd, img_format, path+filename+"."+img_format, img_size+img_sizeunit))
		os.system('sync')
		time.sleep(2)
		print '%s -f %s %s %s' % (cmd, img_format, path+filename, img_size+img_sizeunit)
		print ("Done")

	def on_button_create_image_clicked(self, widget=None, data=""):
		self.curtain_down()
		self.user_wait_action(self.image_create)

	def on_newimage_close_clicked(self, widget=None, data=""):
		self.curtain_down()
		self.widg['dialog_create_image'].hide()
		return True

	def on_dialog_messages_response(self, widget=None, data=""):
		print "on_dialog_messages_response undefined!"
		pass
	def on_item_info_activate(self, widget=None, data=""):
		print "on_item_info_activate undefined!"
		pass
	def on_item_bookmark_activate(self, widget=None, data=""):
		print "on_item_bookmark_activate undefined!"
		pass
	def on_dialog_jobmonitor_response(self, widget=None, data=""):
		print "on_dialog_jobmonitor_response undefined!"
		pass
	def on_toolbutton_stop_job_clicked(self, widget=None, data=""):
		print "on_toolbutton_stop_job_clicked undefined!"
		pass
	def on_toolbutton_reset_job_clicked(self, widget=None, data=""):
		print "on_toolbutton_reset_job_clicked undefined!"
		pass
	def on_toolbutton_pause_job_clicked(self, widget=None, data=""):
		print "on_toolbutton_pause_job_clicked undefined!"
		pass
	def on_toolbutton_rerun_job_clicked(self, widget=None, data=""):
		print "on_toolbutton_rerun_job_clicked undefined!"
		pass
	def on_treeview_jobmon_volumes_button_press_event(self, widget=None, data=""):
		print "on_treeview_jobmon_volumes_button_press_event undefined!"
		pass
	def on_treeview_jobmon_volumes_row_activated(self, widget=None, data=""):
		print "on_treeview_jobmon_volumes_row_activated undefined!"
		pass
	def on_button_jobmon_apply_cdrom_clicked(self, widget=None, data=""):
		print "on_button_jobmon_apply_cdrom_clicked undefined!"
		pass
	def on_button_jobmon_apply_fda_clicked(self, widget=None, data=""):
		print "on_button_jobmon_apply_fda_clicked undefined!"
		pass
	def on_button_jobmon_apply_fdb_clicked(self, widget=None, data=""):
		print "on_button_jobmon_apply_fdb_clicked undefined!"
		pass
	def on_combobox_jobmon_cdrom_changed(self, widget=None, data=""):
		print "on_combobox_jobmon_cdrom_changed undefined!"
		pass
	def on_combobox_jobmon_fda_changed(self, widget=None, data=""):
		print "on_combobox_jobmon_fda_changed undefined!"
		pass
	def on_combobox_jobmon_fdb_changed(self, widget=None, data=""):
		print "on_combobox_jobmon_fdb_changed undefined!"
		pass
	def on_treeview_usbhost_button_press_event(self, widget=None, data=""):
		print "on_treeview_usbhost_button_press_event undefined!"
		pass
	def on_treeview_usbhost_row_activated(self, widget=None, data=""):
		print "on_treeview_usbhost_row_activated undefined!"
		pass
	def on_treeview_usbguest_button_press_event(self, widget=None, data=""):
		print "on_treeview_usbguest_button_press_event undefined!"
		pass
	def on_treeview_usbguest_row_activated(self, widget=None, data=""):
		print "on_treeview_usbguest_row_activated undefined!"
		pass

	def on_item_jobmonoitor_activate(self, widget=None, data=""):
		self.joblist_selected.open_console()
		pass

	def on_item_stop_job_activate(self, widget=None, data=""):
		if self.joblist_selected is None:
			return
		if self.joblist_selected.proc != None:
			self.debug("Sending to process signal 19!")
			self.joblist_selected.proc.send_signal(19)
		pass

	def on_item_cont_job_activate(self, widget=None, data=""):
		if self.joblist_selected is None:
			return
		if self.joblist_selected.proc != None:
			self.debug("Sending to process signal 18!")
			self.joblist_selected.proc.send_signal(18)
		pass
	def on_item_reset_job_activate(self, widget=None, data=""):
		self.debug(self.joblist_selected)
		if self.joblist_selected is None:
			return
		if self.joblist_selected.proc != None:
			self.debug("Restarting process!")
			self.joblist_selected.poweroff()
			self.joblist_selected.poweron()
		pass
	def on_item_kill_job_activate(self, widget=None, data=""):
		if self.joblist_selected is None:
			return
		if self.joblist_selected.proc != None:
			self.debug("Sending to process signal 9!")
			self.joblist_selected.proc.send_signal(9)
		pass
	def on_attach_device_activate(self, widget=None, data=""):
		print "on_attach_device_activate undefined!"
		pass
	def on_detach_device_activate(self, widget=None, data=""):
		print "on_detach_device_activate undefined!"
		pass
	def on_item_eject_activate(self, widget=None, data=""):
		print "on_item_eject_activate undefined!"
		pass
	def on_dialog_newnetcard_response(self, widget=None, data=""):
		print "on_dialog_newnetcard_response undefined!"
		pass
	def on_combobox_networktype_changed(self, widget=None, data=""):
		print "on_combobox_networktype_changed undefined!"
		pass
	def on_entry_network_macaddr_changed(self, widget=None, data=""):
		print "on_entry_network_macaddr_changed undefined!"
		pass
	def on_entry_network_ip_changed(self, widget=None, data=""):
		print "on_entry_network_ip_changed undefined!"
		pass
	def on_spinbutton_network_port_changed(self, widget=None, data=""):
		print "on_spinbutton_network_port_changed undefined!"
		pass
	def on_spinbutton_network_vlan_changed(self, widget=None, data=""):
		print "on_spinbutton_network_vlan_changed undefined!"
		pass
	def on_entry_network_ifacename_changed(self, widget=None, data=""):
		print "on_entry_network_ifacename_changed undefined!"
		pass
	def on_entry_network_tuntapscript_changed(self, widget=None, data=""):
		print "on_entry_network_tuntapscript_changed undefined!"
		pass
	def on_button__network_open_tuntap_file_clicked(self, widget=None, data=""):
		print "on_button__network_open_tuntap_file_clicked undefined!"
		pass
	def on_spinbutton_network_filedescriptor_changed(self, widget=None, data=""):
		print "on_spinbutton_network_filedescriptor_changed undefined!"
		pass
	def on_dialog_new_redirect_response(self, widget=None, data=""):
		print "on_dialog_new_redirect_response undefined!"
		pass
	def on_radiobutton_redirect_TCP_toggled(self, widget=None, data=""):
		print "on_radiobutton_redirect_TCP_toggled undefined!"
		pass
	def on_radiobutton_redirect_UDP_toggled(self, widget=None, data=""):
		print "on_radiobutton_redirect_UDP_toggled undefined!"
		pass
	#def on_radiobutton_cdromtype2_toggled(self, widget=None, data=""):
		#self.gladefile.get_widget('cfg_Qemu_cdrom_filechooser').set_active(True)

	def on_spinbutton_redirect_sport_changed(self, widget=None, data=""):
		print "on_spinbutton_redirect_sport_changed undefined!"
		pass
	def on_entry_redirect_gIP_changed(self, widget=None, data=""):
		print "on_entry_redirect_gIP_changed undefined!"
		pass
	def on_spinbutton_redirect_dport_changed(self, widget=None, data=""):
		print "on_spinbutton_redirect_dport_changed undefined!"
		pass

	def on_newbrick(self, widget=None, event=None, data=""):
		self.curtain_down()
		self.gladefile.get_widget('text_newbrickname').set_text("")
		self.show_window('dialog_newbrick')

	def on_newevent(self, widget=None, event=None, data=""):
		self.curtain_down()
		self.gladefile.get_widget('text_neweventname').set_text("")
		self.show_window('dialog_newevent')

	def on_testconfig(self, widget=None, event=None, data=""):
		print "signal not connected"
	def on_autodetectsettings(self, widget=None, event=None, data=""):
		print "signal not connected"

	def on_check_kvm(self, widget=None, event=None, data=""):
		if widget.get_active():
			try:
				self.config.check_kvm()
			except IOError:
				print "ioerror"
				self.show_error(_("No KVM binary found")+". "+_("Check your active configuration")+". "+_("KVM will stay disabled")+".")
				widget.set_active(False)

			except NotImplementedError:
				print "no support"
				self.show_error(_("No KVM support found on the system")+". "+_("Check your active configuration")+". "+_("KVM will stay disabled")+".")
				widget.set_active(False)

	def on_check_ksm(self, widget=None, event=None, data=""):
		try:
			self.config.check_ksm(True)
		except NotImplementedError:
			self.debug("no support")
			self.show_error(_("No KSM support found on the system")+". "+_("Check your configuration")+". "+_("KSM will stay disabled")+".")
			widget.set_active(False)

	def on_add_cdrom(self, widget=None, event=None, data=""):
		print "signal not connected"
	def on_remove_cdrom(self, widget=None, event=None, data=""):
		print "signal not connected"

	def on_brick_startstop(self, widget=None, event=None, data=""):
		if self.brick_selected.proc is not None:
			self.brick_selected.poweroff()
		else:
			self.brick_selected.poweron()

	def on_event_startstop(self, widget=None, event=None, data=""):
		if self.event_selected.active == True:
			self.event_selected.poweroff()
		else:
			self.event_selected.poweron()


	def on_brick_delete(self,widget=None, event=None, data=""):
		self.curtain_down()

		if self.brick_selected.proc is not None:
			self.show_error(_("Cannot delete Brick: it is in use")+".")
			return

		self.ask_confirm(_("Do you really want to delete ") +
				_(self.brick_selected.get_type()) + " \"" + self.brick_selected.name + "\" ?",
				on_yes = self.brickfactory.delbrick, arg = self.brick_selected)

	def on_event_delete(self,widget=None, event=None, data=""):
		self.curtain_down()

		msg=""
		if self.event_selected.active == True:
			msg=_("This event is in use")+". "

		self.ask_confirm(msg + _("Do you really want to delete") + " "+
				_(self.event_selected.get_type()) + " \"" + self.event_selected.name + "\" ?",
				on_yes = self.brickfactory.delevent, arg = self.event_selected)

	def on_brick_copy(self,widget=None, event=None, data=""):
		self.curtain_down()
		self.brickfactory.dupbrick(self.brick_selected)

	def on_brick_rename(self,widget=None, event=None, data=""):
		if self.brick_selected.proc != None:
			self.show_error(_("Cannot rename Brick: it is in use."))
			return

		self.gladefile.get_widget('entry_brick_newname').set_text(self.brick_selected.name)
		self.gladefile.get_widget('dialog_rename').show_all()
		self.curtain_down()

	def on_event_copy(self,widget=None, event=None, data=""):
		self.curtain_down()
		self.brickfactory.dupevent(self.event_selected)
		pass

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
				self.brickfactory.renamebrick(self.brick_selected, self.gladefile.get_widget('entry_brick_newname').get_text())
			except BrickFactory.InvalidNameException:
				self.show_error("Invalid name!")

	def on_dialog_event_rename_response(self, widget=None, response=0, data=""):
		widget.hide()
		if response == 1:
			if self.event_selected.active == True:
				self.show_error(_("Cannot rename Event: it is in use."))
				return

			try:
				self.brickfactory.renameevent(self.event_selected, self.gladefile.get_widget('entry_event_newname').get_text())
			except BrickFactory.InvalidNameException:
				self.show_error("Invalid name!")

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
			except BrickFactory.InvalidNameException:
				self.show_error("Invalid name!")
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

		action = ' on' if self.selected_event_type() == 'BrickStart' else 'off'

		while iter:
			evnametoadd = self.addedmodel.get_value(iter, COL_NAME)
			self.brickfactory.\
			brickAction(currevent,('config add ' + evnametoadd + action).\
										split(" "))
			iter = self.addedmodel.iter_next(iter)

		self.debug("Event created successfully")

	def on_brick_configure(self,widget=None, event=None, data=""):
		self.curtain_up()
		pass

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
		combo = Settings.ComboBox(widget)
		path = self.config.get('qemupath')

		#Machine COMBO
		machine_c = Settings.ComboBox(self.gladefile.get_widget("cfg_Qemu_machine_combo"))
		opt_m = dict()
		os.system(path + "/" + combo.get_selected() + " -M ? >" + Settings.MYPATH+"/.vmachines")
		for m in open(Settings.MYPATH+"/.vmachines").readlines():
			if not re.search('machines are', m):
				v = m.split(' ')[0]
				k = m.lstrip(v).rstrip('/n')
				while (k.startswith(' ')):
					k = k.lstrip(' ')
				opt_m[v]=v
		toSelect=""
		for k, v in opt_m.iteritems():
			if v.strip() == self.brick_selected.cfg.machine.strip():
				toSelect=k
		machine_c.populate(opt_m, toSelect)
		os.unlink(Settings.MYPATH+"/.vmachines")

		#CPU combo
		opt_c = dict()
		cpu_c = Settings.ComboBox(self.gladefile.get_widget("cfg_Qemu_cpu_combo"))
		os.system(path + "/" + combo.get_selected() + " -cpu ? >" + Settings.MYPATH+"/.cpus")
		for m in open(Settings.MYPATH+"/.cpus").readlines():
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
		cpu_c.populate(opt_c, self.brick_selected.cfg.cpu)
		os.unlink(Settings.MYPATH+"/.cpus")


	def on_check_kvm_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			try:
				self.config.check_kvm()
				self.kvm_toggle_all(True)
			except IOError:
				self.debug("ioerror")
				self.show_error("No KVM binary found. Check your active configuration. KVM will stay disabled.")
				widget.set_active(False)
			except NotImplementedError:
				self.debug("no support")
				self.show_error("No KVM support found on the system. Check your active configuration. KVM will stay disabled.")
				widget.set_active(False)
		else:
			self.kvm_toggle_all(False)

	def kvm_toggle_all(self, enabled):
		self.gladefile.get_widget('cfg_Qemu_kvmsmem_spinint').set_sensitive(enabled)
		self.gladefile.get_widget('cfg_Qemu_kvmsm_check').set_sensitive(enabled)
		# disable incompatible options
		if (self.gladefile.get_widget('cfg_Qemu_tdf_check').get_active()==True and enabled == False):
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
			self.filechooser_clear(self.gladefile.get_widget('cfg_Qemu_kernel_filechooser'), None, "", True)
			self.gladefile.get_widget('cfg_Qemu_kernel_filechooser').set_sensitive(False)
			self.gladefile.get_widget('filedel_cfg_Qemu_kernel').set_sensitive(False)

	def on_check_initrd_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			self.gladefile.get_widget('cfg_Qemu_initrd_filechooser').set_sensitive(True)
			self.gladefile.get_widget('filedel_cfg_Qemu_initrd').set_sensitive(False)
		else:
			self.filechooser_clear(self.gladefile.get_widget('cfg_Qemu_initrd_filechooser'), None, "", True)
			self.gladefile.get_widget('cfg_Qemu_initrd_filechooser').set_sensitive(False)
			self.gladefile.get_widget('filedel_cfg_Qemu_initrd').set_sensitive(True)

	def on_check_gdb_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			self.gladefile.get_widget('cfg_Qemu_gdbport_spinint').set_sensitive(True)
		else:
			self.gladefile.get_widget('cfg_Qemu_gdbport_spinint').set_sensitive(False)

	def on_random_macaddr(self, widget=None, event=None, data=""):
		self.gladefile.get_widget('vmplug_macaddr').set_text(Global.RandMac())

	def on_vmplug_add(self, widget=None, event=None, data=""):
		if self.brick_selected is None:
			return
		sockname = Settings.ComboBox(self.gladefile.get_widget('sockscombo_vmethernet')).get_selected()
		if (sockname == '_hostonly'):
			pl = self.brick_selected.add_plug('_hostonly')
		else:
			pl = self.brick_selected.add_plug()
			for so in self.brickfactory.socks:
				if so.nickname == sockname:
					pl.connect(so)
		pl.model = self.gladefile.get_widget('vmplug_model').get_active_text()
		pl.macaddr = self.gladefile.get_widget('vmplug_macaddr').get_text()
		self.update_vmplugs_tree()

	def update_vmplugs_tree(self):
		if self.brick_selected is None:
			return

		self.vmplugs.clear()
		if (self.brick_selected.get_type() == 'Qemu'):
			for pl in self.brick_selected.plugs:
				iter = self.vmplugs.append(None, None)
				self.vmplugs.set_value(iter,0,pl.vlan)
				if pl.mode == 'hostonly':
					self.vmplugs.set_value(iter,1,'Host')
				elif pl.sock:
					self.vmplugs.set_value(iter,1,pl.sock.brick.name)
				self.vmplugs.set_value(iter,2,pl.model)
				self.vmplugs.set_value(iter,3,pl.mac)

	def on_vmplug_selected(self, widget=None, event=None, data=""):
		if self.brick_selected is None:
			return

		tree = self.gladefile.get_widget('treeview_networkcards');
		store = self.vmplugs
		x = int(event.x)
		y = int(event.y)
		pthinfo = tree.get_path_at_pos(x, y)
		number = self.get_treeselected(tree, store, pthinfo, 0)
		for pl in self.brick_selected.plugs:
			if str(pl.vlan) == number:
				self.vmplug_selected = pl
				break
		Settings.ComboBox(self.gladefile.get_widget("vmplug_model")).select(pl.model)
		self.gladefile.get_widget('vmplug_macaddr').set_text(pl.mac)
		if (pl.mode == 'hostonly'):
			Settings.ComboBox(self.gladefile.get_widget('sockscombo_vmethernet')).select('Host-only ad hoc network')
		elif (pl.sock):
			Settings.ComboBox(self.gladefile.get_widget('sockscombo_vmethernet')).select(pl.sock.nickname)
		self.vmplug_selected = pl

	def on_vmplug_edit(self, widget=None, event=None, data=""):
		pl = self.vmplug_selected
		if pl == None:
			return
		vlan = pl.vlan

		if self.brick_selected is None:
			return

		self.brick_selected.plugs.remove(pl)
		del(pl)
		model = Settings.ComboBox(self.gladefile.get_widget('vmplug_model')).get_selected()
		mac = self.gladefile.get_widget('vmplug_macaddr').get_text()
		sockname = Settings.ComboBox(self.gladefile.get_widget('sockscombo_vmethernet')).get_selected()
		if (sockname == '_hostonly'):
			pl = self.brick_selected.add_plug(sockname)
		else:
			for so in self.brickfactory.socks:
				if so.nickname == sockname:
					pl = self.brick_selected.add_plug(so)
		pl.vlan = vlan
		pl.model = model
		pl.mac = mac
		self.update_vmplugs_tree()

	def on_vmplug_remove(self, widget=None, event=None, data=""):
		pl = self.vmplug_selected
		self.brick_selected.remove_plug(pl.vlan)
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
			self.show_error("Suspend/Resume not supported on this disk.")
			return
		self.joblist_selected.recv()
		self.joblist_selected.send("savevm virtualbricks\n")
		while(not self.joblist_selected.recv().startswith("(qemu")):
			print ".",
			time.sleep(1)
		print
		self.joblist_selected.poweroff()

	def on_vm_resume(self, widget=None, event=None, data=""):
		if self.brick_selected is None:
			return

		hda = self.brick_selected.cfg.get('basehda')
		self.debug("resume")
		if os.system("qemu-img snapshot -l "+hda+" |grep virtualbricks") == 0:
			if self.brick_selected.proc is not None:
				self.brick_selected.send("loadvm virtualbricks\n")
				self.brick_selected.recv()
				return
			else:
				self.brick_selected.cfg.set("loadvm=virtualbricks")
				self.brick_selected.poweron()
		else:
			self.show_error("Cannot find suspend point.")


	def on_vm_powerbutton(self, widget=None, event=None, data=""):
		self.joblist_selected.send("system_powerdown\n")
		self.joblist_selected.recv()

	def on_vm_hardreset(self, widget=None, event=None, data=""):
		self.joblist_selected.send("system_reset\n")
		self.joblist_selected.recv()

	def on_topology_drag(self, widget=None, event=None, data=""):
		print "DRAG"
	def on_topology_redraw(self, widget=None, event=None, data=""):
		print "redraw"
		self.draw_topology()
	def on_topology_export(self, widget=None, event=None, data=""):
		print "export"
		self.gladefile.get_widget('topology_export_dialog').show_all()
	def on_topology_export_ok(self, widget=None, event=None, data=""):
		print "   OK " + self.gladefile.get_widget('topology_export_dialog').get_filename()
		fname = self.gladefile.get_widget('topology_export_dialog').get_filename()
		self.gladefile.get_widget('topology_export_dialog').hide()
		if fname:
			if os.access(fname,os.R_OK):
				self.ask_confirm("Do you want to overwrite " + fname + "?", on_yes=self.topology_export, arg=fname)
			else:
				self.topology_export(fname)

	def topology_export(self, fname):
		try:
			Image.open('/tmp/vde_topology.png').save(fname)
		except KeyError:
			self.error("Error saving topology: Invalid image format")
		except IOError:
			self.error("Error saving topology: Could not write file")
		except:
			self.error("Error saving topology: Unknown error")



	def on_topology_export_cancel(self, widget=None, event=None, data=""):
		print "   cancel"
		self.gladefile.get_widget('topology_export_dialog').hide()

	def on_topology_action(self, widget=None, event=None, data=""):
		if self.topology:
			for n in self.topology.nodes:
				if n.here(event.x,event.y) and event.button == 3:
					brick = self.brickfactory.getbrickbyname(n.name)
					if brick is not None:
						self.brick_selected = brick
						self.show_brickactions()
				if n.here(event.x,event.y) and event.button == 1 and event.type == gtk.gdk._2BUTTON_PRESS:
					brick = self.brickfactory.getbrickbyname(n.name)
					if brick is not None:
						self.brick_selected = brick
						self.user_wait_action(self.startstop_brick,[brick])
		self.curtain_down()

	def on_topology_scroll(self, widget=None, event=None, data=""):
		print "scroll"

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
		print "ON_VMICON_FILE_CHANGE"
		if (widget.get_filename() is not None):
			pixbuf = self.pixbuf_scaled(widget.get_filename())
			self.gladefile.get_widget("qemuicon").set_from_pixbuf(pixbuf)

	def filechooser_clear(self, widget=None, event=None, data="", direct=False):
		if (direct is False):
			filechooser = widget.name[8:] + "_filechooser"
		else:
			filechooser = widget.name
		self.gladefile.get_widget(filechooser).unselect_all()

	def filechooser_hd_clear(self, widget=None, event=None, data=""):
		self.filechooser_clear(widget)
		hd = widget.name[21:]
		check = self.gladefile.get_widget("cfg_Qemu_private"+hd+"_check")
		check.set_active(False)
		filechooser = widget.name[8:] + "_filechooser"
		self.gladefile.get_widget(filechooser).set_current_folder(self.config.get('baseimages'))

	def filechooser_image_clear(self, widget=None, event=None, data=""):
		self.filechooser_clear(widget)
		self.gladefile.get_widget("qemuicon").set_from_file("Qemu.png")

	def on_show_messages_activate(self, menuitem, data=None):
		messages = self.gladefile.get_widget("messages_dialog")
		messages.show_all()

	def on_messages_dialog_delete_event(self, widget=None, event=None, data=""):
		"""we could use deletable property but deletable is only available in
		GTK+ 2.10 and above"""
		widget.hide()
		return True

	def on_messages_dialog_clear_clicked(self, button, data=None):
		self.messages_buffer.set_text("")

	def on_open_project(self, widget, data=None):
		chooser = gtk.FileChooserDialog(title="Open a project",action=gtk.FILE_CHOOSER_ACTION_OPEN, buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_OPEN,gtk.RESPONSE_OK))
		chooser.set_current_folder(self.config.get('bricksdirectory'))
		filt = gtk.FileFilter()
		filt.set_name("Virtualbricks Bricks List (*.vbl)")
		filt.add_pattern("*.vbl")
		chooser.add_filter(filt)
		filt = gtk.FileFilter()
		filt.set_name("All files")
		filt.add_pattern("*")
		chooser.add_filter(filt)
		resp = chooser.run()
		if resp == gtk.RESPONSE_OK:
			filename = chooser.get_filename()
			self.brickfactory.config_restore(filename, False, True)
		self.config.set('current-project', filename)
		self.config.store()
		chooser.destroy()

	def on_save_project(self, widget, data=None):
		chooser = gtk.FileChooserDialog(title="Save as...",action=gtk.FILE_CHOOSER_ACTION_SAVE, buttons=(gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_SAVE,gtk.RESPONSE_OK))
		chooser.set_do_overwrite_confirmation(True)
		chooser.set_current_folder(self.config.get('bricksdirectory'))
		filt = gtk.FileFilter()
		filt.set_name("Virtualbricks Bricks List (*.vbl)")
		filt.add_pattern("*.vbl")
		chooser.add_filter(filt)
		filt = gtk.FileFilter()
		filt.set_name("All files")
		filt.add_pattern("*")
		chooser.add_filter(filt)
		resp = chooser.run()
		if resp == gtk.RESPONSE_OK:
			filename = chooser.get_filename()
			if filename[len(filename)-4:] != ".vbl":
				filename+=".vbl"
			self.brickfactory.config_dump(filename)
		self.config.set('current-project', filename)
		self.config.store()
		chooser.destroy()


	def on_import_project(self, widget, data=None):
		self.debug( "IMPORT PROJECT undefined" )

	def on_new_project(self, widget, data=None):
		self.debug( "NEW PROJECT undefined" )

	def on_recent_project(self, widget, data=None):
		self.debug( "RECENT PROJECT undefined" )

	def signals(self):
		self.signaldict = {
			"on_generic_event":self.on_generic_event,
			"on_dialog_event_bricks_select_response":self.on_dialog_event_bricks_select_response,
			"on_event_brick_select_add_clicked":self.on_event_brick_select_add_clicked,
			"on_event_brick_select_remove_clicked":self.on_event_brick_select_remove_clicked,
			"on_window1_destroy":self.on_window1_destroy,
			"on_windown_destroy":self.on_windown_destroy,
			"on_newbrick_cancel":self.on_newbrick_cancel,
			"on_newbrick_ok":self.on_newbrick_ok,
			"on_newevent_cancel":self.on_newevent_cancel,
			"on_newevent_ok":self.on_newevent_ok,
			"on_config_cancel":self.on_config_cancel,
			"on_config_ok":self.on_config_ok,
			"on_gilbert_toggle": self.on_gilbert_toggle,
			"on_mtu_toggle": self.on_mtu_toggle,
			"on_brick_startstop": self.tree_startstop,
			"on_event_startstop": self.events_tree_startstop,
			"on_brick_configure": self.on_brick_configure,
			"on_brick_delete": self.on_brick_delete,
			"on_event_delete": self.on_event_delete,
			"on_brick_copy": self.on_brick_copy,
			"on_brick_rename": self.on_brick_rename,
			"on_event_rename": self.on_event_rename,
			"on_event_copy": self.on_event_copy,
			"on_event_configure": self.on_event_configure,
			"on_dialog_rename_response": self.on_dialog_rename_response,
			"on_dialog_event_rename_response": self.on_dialog_event_rename_response,
			"on_dialog_shellcommand_response": self.on_dialog_shellcommand_response,
			"on_item_quit_activate":self.on_item_quit_activate,
			"on_item_settings_activate":self.on_item_settings_activate,
			"on_item_settings_autoshow_activate":self.on_item_settings_autoshow_activate,
			"on_item_settings_autohide_activate":self.on_item_settings_autohide_activate,
			"on_item_create_image_activate":self.on_item_create_image_activate,
			"on_item_about_activate":self.on_item_about_activate,
			"on_toolbutton_start_all_clicked":self.on_toolbutton_start_all_clicked,
			"on_toolbutton_stop_all_clicked":self.on_toolbutton_stop_all_clicked,
			"on_toolbutton_start_all_events_clicked":self.on_toolbutton_start_all_events_clicked,
			"on_toolbutton_stop_all_events_clicked":self.on_toolbutton_stop_all_events_clicked,
			"on_mainwindow_dropaction":self.on_mainwindow_dropaction,
			"on_treeview_bookmarks_button_release_event":self.on_treeview_bookmarks_button_release_event,
			"on_treeview_events_bookmarks_button_release_event":self.on_treeview_events_bookmarks_button_release_event,
			"on_treeview_drag_get_data":self.on_treeview_drag_get_data,
			"on_treeview_bookmarks_cursor_changed":self.on_treeview_bookmarks_cursor_changed,
			"on_treeview_bookmarks_row_activated_event":self.on_treeview_bookmarks_row_activated_event,
			"on_treeview_events_bookmarks_row_activated_event":self.on_treeview_events_bookmarks_row_activated_event,
			"on_focus_out":self.on_treeview_bookmarks_focus_out,
			"on_treeview_bootimages_button_press_event":self.on_treeview_bootimages_button_press_event,
			"on_treeview_bootimages_cursor_changed":self.on_treeview_bootimages_cursor_changed,
			"on_treeview_bootimages_row_activated_event":self.on_treeview_bootimages_row_activated_event,
			"on_treeview_joblist_button_press_event":self.on_treeview_joblist_button_press_event,
			"on_treeview_joblist_row_activated_event":self.on_treeview_joblist_row_activated_event,
			"on_button_togglesettings_clicked":self.on_button_togglesettings_clicked,
			"on_filechooserdialog_openimage_response":self.on_filechooserdialog_openimage_response,
			"on_button_openimage_cancel_clicked":self.on_button_openimage_cancel_clicked,
			"on_button_openimage_open_clicked":self.on_button_openimage_open_clicked,
			"on_dialog_settings_delete_event":self.on_dialog_settings_delete_event,
			"on_dialog_settings_response":self.on_dialog_settings_response,
			"on_treeview_cdromdrives_row_activated":self.on_treeview_cdromdrives_row_activated,
			"on_button_settings_add_cdevice_clicked":self.on_button_settings_add_cdevice_clicked,
			"on_button_settings_rem_cdevice_clicked":self.on_button_settings_rem_cdevice_clicked,
			"on_treeview_qemupaths_row_activated":self.on_treeview_qemupaths_row_activated,
			"on_button_settings_add_qemubin_clicked":self.on_button_settings_add_qemubin_clicked,
			"on_button_settings_rem_qemubin_clicked":self.on_button_settings_rem_qemubin_clicked,
			"on_dialog_bookmarks_response":self.on_dialog_bookmarks_response,
			"on_edit_bookmark_activate":self.on_edit_bookmark_activate,
			"on_bookmark_info_activate":self.on_bookmark_info_activate,
			"on_delete_bookmark_activate":self.on_delete_bookmark_activate,
			"on_dialog_about_response":self.on_dialog_about_response,
			"on_dialog_create_image_response":self.on_dialog_create_image_response,
			"on_filechooserbutton_newimage_dest_selection_changed":self.on_filechooserbutton_newimage_dest_selection_changed,
			"on_filechooserbutton_newimage_dest_current_folder_changed":self.on_filechooserbutton_newimage_dest_current_folder_changed,
			"on_entry_newimage_name_changed":self.on_entry_newimage_name_changed,
			"on_combobox_newimage_format_changed":self.on_combobox_newimage_format_changed,
			"on_spinbutton_newimage_size_changed":self.on_spinbutton_newimage_size_changed,
			"on_combobox_newimage_sizeunit_changed":self.on_combobox_newimage_sizeunit_changed,
			"on_button_create_image_clicked":self.on_button_create_image_clicked,
			"on_dialog_messages_response":self.on_dialog_messages_response,
			"on_item_info_activate":self.on_item_info_activate,
			"on_item_bookmark_activate":self.on_item_bookmark_activate,
			"on_dialog_jobmonitor_response":self.on_dialog_jobmonitor_response,
			"on_toolbutton_stop_job_clicked":self.on_toolbutton_stop_job_clicked,
			"on_toolbutton_reset_job_clicked":self.on_toolbutton_reset_job_clicked,
			"on_toolbutton_pause_job_clicked":self.on_toolbutton_pause_job_clicked,
			"on_toolbutton_rerun_job_clicked":self.on_toolbutton_rerun_job_clicked,
			"on_treeview_jobmon_volumes_button_press_event":self.on_treeview_jobmon_volumes_button_press_event,
			"on_treeview_jobmon_volumes_row_activated":self.on_treeview_jobmon_volumes_row_activated,
			"on_button_jobmon_apply_cdrom_clicked":self.on_button_jobmon_apply_cdrom_clicked,
			"on_button_jobmon_apply_fda_clicked":self.on_button_jobmon_apply_fda_clicked,
			"on_button_jobmon_apply_fdb_clicked":self.on_button_jobmon_apply_fdb_clicked,
			"on_combobox_jobmon_cdrom_changed":self.on_combobox_jobmon_cdrom_changed,
			"on_combobox_jobmon_fda_changed":self.on_combobox_jobmon_fda_changed,
			"on_combobox_jobmon_fdb_changed":self.on_combobox_jobmon_fdb_changed,
			"on_treeview_usbhost_button_press_event":self.on_treeview_usbhost_button_press_event,
			"on_treeview_usbhost_row_activated":self.on_treeview_usbhost_row_activated,
			"on_treeview_usbguest_button_press_event":self.on_treeview_usbguest_button_press_event,
			"on_treeview_usbguest_row_activated":self.on_treeview_usbguest_row_activated,
			"on_item_jobmonoitor_activate":self.on_item_jobmonoitor_activate,
			"on_item_stop_job_activate":self.on_item_stop_job_activate,
			"on_item_cont_job_activate":self.on_item_cont_job_activate,
			"on_item_reset_job_activate":self.on_item_reset_job_activate,
			"on_item_kill_job_activate":self.on_item_kill_job_activate,
			"on_attach_device_activate":self.on_attach_device_activate,
			"on_detach_device_activate":self.on_detach_device_activate,
			"on_item_eject_activate":self.on_item_eject_activate,
			"on_dialog_newnetcard_response":self.on_dialog_newnetcard_response,
			"on_combobox_networktype_changed":self.on_combobox_networktype_changed,
			"on_entry_network_macaddr_changed":self.on_entry_network_macaddr_changed,
			"on_entry_network_ip_changed":self.on_entry_network_ip_changed,
			"on_spinbutton_network_port_changed":self.on_spinbutton_network_port_changed,
			"on_spinbutton_network_vlan_changed":self.on_spinbutton_network_vlan_changed,
			"on_entry_network_ifacename_changed":self.on_entry_network_ifacename_changed,
			"on_entry_network_tuntapscript_changed":self.on_entry_network_tuntapscript_changed,
			"on_button__network_open_tuntap_file_clicked":self.on_button__network_open_tuntap_file_clicked,
			"on_spinbutton_network_filedescriptor_changed":self.on_spinbutton_network_filedescriptor_changed,
			"on_dialog_new_redirect_response":self.on_dialog_new_redirect_response,
			"on_radiobutton_redirect_TCP_toggled":self.on_radiobutton_redirect_TCP_toggled,
			"on_radiobutton_redirect_UDP_toggled":self.on_radiobutton_redirect_UDP_toggled,
			#"on_radiobutton_cdromtype2_toggled":self.on_radiobutton_cdromtype2_toggled,
			"on_spinbutton_redirect_sport_changed":self.on_spinbutton_redirect_sport_changed,
			"on_entry_redirect_gIP_changed":self.on_entry_redirect_gIP_changed,
			"on_spinbutton_redirect_dport_changed":self.on_spinbutton_redirect_dport_changed,
			"on_newbrick":self.on_newbrick,
			"on_newevent":self.on_newevent,
			"on_testconfig":self.on_testconfig,
			"on_autodetectsettings":self.on_autodetectsettings,
			"on_check_kvm":self.on_check_kvm,
			"on_check_ksm":self.on_check_ksm,
			"on_add_cdrom":self.on_add_cdrom,
			"on_remove_cdrom":self.on_remove_cdrom,
			"on_qemupath_changed":self.on_qemupath_changed,
			"on_vdepath_changed":self.on_vdepath_changed,
			"on_arch_changed":self.on_arch_changed,
			"on_dialog_confirm_response":self.on_dialog_confirm_response,
			"on_check_customkernel_toggled":self.on_check_customkernel_toggled,
			"on_check_initrd_toggled":self.on_check_initrd_toggled,
			"on_check_gdb_toggled":self.on_check_gdb_toggled,
			"on_vmplug_add":self.on_vmplug_add,
			"on_vmplug_edit":self.on_vmplug_edit,
			"on_vmplug_selected":self.on_vmplug_selected,
			"on_vmplug_remove":self.on_vmplug_remove,
			"on_vmplug_onoff":self.on_vmplug_onoff,
			"on_random_macaddr":self.on_random_macaddr,
			"on_tap_config_manual":self.on_tap_config_manual,
			"on_check_kvm_toggled":self.on_check_kvm_toggled,
			"on_button_newimage_close_clicked": self.on_newimage_close_clicked,
			"on_vm_suspend":self.on_vm_suspend,
			"on_vm_powerbutton":self.on_vm_powerbutton,
			"on_vm_hardreset":self.on_vm_hardreset,
			"on_vm_resume":self.on_vm_resume,
			"on_topology_action":self.on_topology_action,
			"on_topology_scroll":self.on_topology_scroll,
			"on_topology_drag":self.on_topology_drag,
			"on_topology_redraw":self.on_topology_redraw,
			"on_topology_export":self.on_topology_export,
			"on_cfg_Qemu_vnc_check_toggled": self.on_vnc_novga_toggled,
			"on_cfg_Qemu_novga_check_toggled": self.on_vnc_novga_toggled,
			"on_filechooserbutton1_file_set": self.on_vmicon_file_change,
			"on_topology_export_ok":self.on_topology_export_ok,
			"on_topology_export_cancel":self.on_topology_export_cancel,
			"filechooser_image_clear": self.filechooser_image_clear,
			"systray_show_window_cb": self.systray_show_window_cb,
			"systray_hide_window_cb": self.systray_hide_window_cb,
			"systray_exit_cb": self.on_window1_destroy,
			"filechooser_clear": self.filechooser_clear,
			"filechooser_hd_clear": self.filechooser_hd_clear,
			"on_show_messages_activate": self.on_show_messages_activate,
			"on_messages_dialog_delete_event": self.on_messages_dialog_delete_event,
			"on_messages_dialog_clear_clicked": self.on_messages_dialog_clear_clicked,
			"on_open_project": self.on_open_project,
			"on_open-recent_project": self.on_recent_project,
			"on_new_project": self.on_new_project,
			"on_import_project": self.on_import_project,
			"on_save_project_as": self.on_save_project,
		}
		self.gladefile.signal_autoconnect(self.signaldict)

	""" ******************************************************** """
	"""														  """
	""" TIMERS												   """
	"""														  """
	"""														  """
	""" ******************************************************** """

	def timers(self):
		gobject.timeout_add(1000, self.check_joblist)
		gobject.timeout_add(500, self.check_topology_scroll)

	def check_topology_scroll(self):
		if self.topology:
			self.topology.x_adj = self.gladefile.get_widget('topology_scrolled').get_hadjustment().get_value()
			self.topology.y_adj = self.gladefile.get_widget('topology_scrolled').get_vadjustment().get_value()
			return True

	def check_joblist(self):
		new_ps = []
		for b in self.brickfactory.bricks:
			if b.proc is not None:
				new_ps.append(b)
				ret = b.proc.poll()
				if ret != None:
					b.poweroff()
					#self.error("%s '%s' Terminated with code %d" %(b.get_type(), b.name, ret))
					b.gui_changed = True

		if self.ps != new_ps:
			self.ps = new_ps
			self.bricks = []
			self.running_bricks.clear()
			for b in self.ps:
				iter = self.running_bricks.append(None, None)
				self.running_bricks.set_value(iter, 0,gtk.gdk.pixbuf_new_from_file_at_size(b.icon.get_img(), 48, 48))
				self.running_bricks.set_value(iter,1,str(b.pid))
				self.running_bricks.set_value(iter,2,b.get_type())
				self.running_bricks.set_value(iter,3,b.name)
			self.debug("proc list updated")
		return True

	def draw_topology(self):
		print "topo"
		if self.gladefile.get_widget('topology_tb').get_active():
			orientation = "TB"
		else:
			orientation = "LR"

		self.topology = Topology(self.gladefile.get_widget('image_topology'), self.brickfactory.bricksmodel, 1.00, orientation)

	def user_wait_action(self, action, args=[]):
		self.gladefile.get_widget("window_userwait").show_all()
		t = VBuserwait(action, args)
		gobject.timeout_add(200, self.user_wait_action_timer, t)
		t.start()

	def user_wait_action_timer(self, t):
		if not t.running:
			self.gladefile.get_widget("window_userwait").hide()
			self.gladefile.get_widget("main_win").set_sensitive(True)
		else:
			self.gladefile.get_widget("main_win").set_sensitive(False)
			self.gladefile.get_widget("userwait_progressbar").pulse()
		return t.running
