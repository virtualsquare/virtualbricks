# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2013 Virtualbricks team

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import re

import gobject
import gtk
import gtk.glade

from twisted.application import app
from twisted.python import log as _log
from twisted.internet import error, defer, task, protocol, reactor, utils

from virtualbricks import (interfaces, tools, errors, settings, configfile,
						brickfactory, _compat)

from virtualbricks.gui import _gui, graphics, dialogs
from virtualbricks.gui.combo import ComboBox


log = _compat.getLogger(__name__)

if False:  # pyflakes
    _ = str


class SyncProtocol(protocol.ProcessProtocol):

	def __init__(self, done):
		self.done = done

	def processEnded(self, status):
		if isinstance(status.value, error.ProcessTerminated):
			log.err(status.value)
			self.done.errback(None)
		else:
			self.done.callback(None)


class QemuImgCreateProtocol(protocol.ProcessProtocol):

	def __init__(self, done):
		self.done = done

	def processEnded(self, status):
		if isinstance(status.value, error.ProcessTerminated):
			log.err(status.value)
			self.done.errback(None)
		else:
			reactor.spawnProcess(SyncProtocol(self.done), "sync", ["sync"],
				os.environ)

def get_treeselected(gui, tree, model, pthinfo, c):
	if pthinfo is not None:
		path, col, cellx, celly = pthinfo
		tree.grab_focus()
		tree.set_cursor(path, col, 0)
		iter_ = model.get_iter(path)
		name = model.get_value(iter_, c)
		gui.config_last_iter = iter_
		return name
	return ""


def get_treeselected_name(gui, tree, model, pathinfo):
	return get_treeselected(gui, tree, model, pathinfo, 3)


def get_combo_text(widget):
	# XXX: this can return None
	combo = ComboBox(widget)
	txt = combo.get_selected()
	if txt is not None and txt != "-- default --":
		return txt


def widget_to_params(brick, get_widget):
	"""Widget to params reads the config directly from
	gtk widgets.
	If the widget name is in the format:
		- cfg_<type>_<variablename>_<widgettype>
	the configuration will be read automatically.
	"""

	pattern_setters = [("cfg_%s_%s_text", lambda w: w.get_text()),
		("cfg_%s_%s_spinint", lambda w: w.get_value_as_int()),
		("cfg_%s_%s_spinfloat", lambda w: w.get_value()),
		("cfg_%s_%s_comboinitial", lambda w: w.get_active_text()),
		("cfg_%s_%s_combo", lambda w: get_combo_text(w)),
		("cfg_%s_%s_check", lambda w: w.get_active()),
		("cfg_%s_%s_filechooser", lambda w: (w.get_filename() or ""))]

	parameters = {}
	for param_name in brick.config.keys():
		for pattern, setter in pattern_setters:
			name = pattern % (brick.get_type(), param_name)
			widget = get_widget(name)
			if widget:
				parameters[param_name] = setter(widget)
	return dict((k, v) for k, v in parameters.items() if v is not None)


def changed(brick, row):
	if row.valid():
		path = row.get_path()
		model = row.get_model()
		model.row_changed(path, model.get_iter(path))
	return brick


def changed_brick_in_model(result, model):
	try:
		brick, status = result
	except TypeError:
		brick = result
	for path, brick_ in enumerate(model):
		if brick is brick_:
			model.row_changed(path, model.get_iter(path))
			break
	return result


TYPE_CONFIG_WIDGET_NAME_MAP = {"Qemu": "box_vmconfig",
							"Wirefilter": "box_wirefilterconfig",
							"Router": "box_routerconfig"}
TOPOLOGY_TAB = 4


class TopologyMixin(object):

	_should_draw_topology = True
	topology = None

	def __init__(self):
		super(TopologyMixin, self).__init__()
		ts = self.get_object("topology_scrolled")
		ts.get_hadjustment().connect("value-changed",
			self.on_topology_h_scrolled)
		ts.get_vadjustment().connect("value-changed",
			self.on_topology_v_scrolled)

	def draw_topology(self, export=""):
		if self.get_object("main_notebook").get_current_page() == TOPOLOGY_TAB:
			self._draw_topology()
		else:
			self._should_draw_topology = True

	def _draw_topology(self, export=""):
		log.debug("drawing topology")
		# self.maintree.order()
		if self.get_object('topology_tb').get_active():
			orientation = "TB"
		else:
			orientation = "LR"
		self.topology = graphics.Topology(
			self.get_object('image_topology'),
			self.brickfactory.bricks, 1.00, orientation, export,
			settings.VIRTUALBRICKS_HOME + "/")
		# self._should_draw_topology = False

	def on_topology_h_scrolled(self, adjustment):
		self.topology.x_adj = adjustment.get_value()

	def on_topology_v_scrolled(self, adjustment):
		self.topology.y_adj = adjustment.get_value()

	def on_topology_redraw(self, widget=None, event=None, data=""):
		self._draw_topology()

	def on_topology_export(self, widget=None, event=None, data=""):
		def on_response(dialog, response_id):
			try:
				if response_id == gtk.RESPONSE_OK:
					try:
						self._draw_topology(dialog.get_filename())
					except KeyError:
						log.exception(_("Error saving topology: Invalid image"
							" format"))
					except IOError:
						log.exception(_("Error saving topology: Could not "
							"write file"))
					except:
						log.exception(_("Error saving topology: Unknown "
							"error"))
			finally:
				dialog.destroy()

		chooser = gtk.FileChooserDialog(title=_("Select an image file"),
				action=gtk.FILE_CHOOSER_ACTION_OPEN,
				buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
						gtk.STOCK_SAVE, gtk.RESPONSE_OK))
		chooser.set_do_overwrite_confirmation(True)
		chooser.connect("response", on_response)
		chooser.show()

	def on_topology_action(self, widget=None, event=None, data=""):
		if self._should_draw_topology:
			self._draw_topology()
		if self.topology:
			for n in self.topology.nodes:
				if n.here(event.x,event.y) and event.button == 3:
					brick = self.brickfactory.get_brick_by_name(n.name)
					if brick is not None:
						# self.maintree.set_selection(brick)
						self.show_brickactions()
				if n.here(event.x,event.y) and event.button == 1 and event.type == gtk.gdk._2BUTTON_PRESS:
					brick = self.brickfactory.get_brick_by_name(n.name)
					if brick is not None:
						# self.maintree.set_selection(brick)
						self.startstop_brick(brick)
		self.curtain_down()

	def on_main_notebook_change_current_page(self, notebook, offset):
		if (notebook.get_current_page() == TOPOLOGY_TAB and
				self._should_draw_topology):
			self._draw_topology()

	def on_main_notebook_switch_page(self, notebook, page, page_num):
		if page_num == TOPOLOGY_TAB and self._should_draw_topology:
			self._draw_topology()

	def on_main_notebook_select_page(self, notebook, move_focus):
		if (notebook.get_current_page() == TOPOLOGY_TAB and
				self._should_draw_topology):
			self._draw_topology()


class VBGUI(gobject.GObject, TopologyMixin):
	"""
	The main GUI object for virtualbricks, containing all the configuration for
	the widgets and the connections to the main engine.
	"""

	def __init__(self, factory, gladefile, quit, textbuffer=None):
		gobject.GObject.__init__(self)
		self.brickfactory = factory
		self.gladefile = gladefile
		self.messages_buffer = textbuffer
		self.quit_d = quit
		TopologyMixin.__init__(self)

		self.widg = self.get_widgets(self.widgetnames())
		self.__config_panel = None
		self.__summary_table = None

		log.info("Starting VirtualBricks!")

		# Connect all the signal from the factory to specific callbacks
		self.__row_changed_h = factory.bricks.connect("row-changed",
				self.on_brick_changed)

		# General settings (system properties)
		self.config = settings

		# Show the main window
		self.widg['main_win'].show()
		self.ps = []
		self.bricks = []

		# Set two useful file filters
		self.vbl_filter = gtk.FileFilter()
		self.vbl_filter.set_name(_("Virtualbricks Bricks List") + " (*.vbl)")
		self.vbl_filter.add_pattern("*.vbl")
		self.all_files_filter = gtk.FileFilter()
		self.all_files_filter.set_name(_("All files"))
		self.all_files_filter.add_pattern("*")

		# Don't remove me, I am useful after config, when treeview may lose focus and selection.
		self.last_known_selected_brick = None
		self.last_known_selected_event = None
		self.gladefile.get_widget("main_win").connect("delete-event", self.delete_event)

		# self.sockscombo = dict()

		self.setup_bricks()
		self.setup_events()
		self.setup_joblist()
		# self.setup_remotehosts()
		self.setup_netwoks_cards()
		self.setup_router_devs()
		self.setup_router_routes()
		self.setup_router_filters()

		self.statusicon = None

		''' Tray icon '''
		if settings.systray:
			self.start_systray()

		''' Set the settings panel to bottom '''
		self.curtain = self.gladefile.get_widget('vpaned_mainwindow')
		# self.Dragging = None
		self.curtain_down()

		''' Reset the selections for the TWs'''
		self.vmplug_selected = None
		self.joblist_selected = None
		self.curtain_is_down = True

		''' Initialize threads, timers etc.'''
		self.signals()
		task.LoopingCall(self.running_bricks.refilter).start(2)


		''' FIXME: re-enable when implemented '''
		#self.gladefile.get_widget('convert_image_menuitem').set_sensitive(False)


		''' Check GUI prerequisites '''
		missing = self.check_gui_prerequisites()
		self.disable_config_kvm = False
		self.disable_config_ksm = False
		missing_text=""
		missing_components=""
		if (len(missing) > 0 and settings.show_missing == True):
			for m in missing:
				if m == "kvm":
					settings.kvm = False
					self.disable_config_kvm = True
					missing_text = missing_text + "KVM not found: kvm support will be disabled.\n"
				elif m == "ksm":
					settings.ksm = False
					self.disable_config_ksm = True
					missing_text = missing_text + "KSM not found in Linux. Samepage memory will not work on this system.\n"
				else:
					missing_components = missing_components + ('%s ' % m)
			log.error("%s\nThere are some components not found: %s some "
					"functionalities may not be available.\nYou can disable "
					"this alert from the general settings.", missing_text,
					missing_components)

	def quit(self):
		self.brickfactory.bricks.disconnect(self.__row_changed_h)
		self.__row_changed_h = None

	def __setup_treeview(self, resource, window_name, widget_name):
		ui = graphics.get_data("virtualbricks.gui", resource)
		builder = gtk.Builder()
		builder.add_from_string(ui)
		builder.connect_signals(self)
		window = self.gladefile.get_widget(window_name)
		widget = builder.get_object(widget_name)
		widget.reparent(window)
		return builder

	def setup_joblist(self):
		builder = self.__setup_treeview("data/joblist.ui", "scrolledwindow1",
								"joblist_treeview")

		def set_icon(column, cell_renderer, model, iter):
			brick = model.get_value(iter, 0)
			pixbuf = graphics.pixbuf_for_brick_at_size(brick, 48, 48)
			cell_renderer.set_property("pixbuf", pixbuf)

		def set_pid(column, cell_renderer, model, iter):
			brick = model.get_value(iter, 0)
			if brick.pid == -10:
				pid = "python-thread   "
			elif brick.homehost:
				pid = "Remote"
			else:
				pid = str(brick.pid)
			cell_renderer.set_property("text", pid)

		def set_type(column, cell_renderer, model, iter):
			brick = model.get_value(iter, 0)
			cell_renderer.set_property("text", brick.get_type())

		def set_name(column, cell_renderer, model, iter):
			brick = model.get_value(iter, 0)
			cell_renderer.set_property("text", brick.name)

		icon_c = builder.get_object("icon_treeviewcolumn")
		icon_cr = builder.get_object("icon_cellrenderer")
		icon_c.set_cell_data_func(icon_cr, set_icon)
		pid_c = builder.get_object("pid_treeviewcolumn")
		pid_cr = builder.get_object("pid_cellrenderer")
		pid_c.set_cell_data_func(pid_cr, set_pid)
		type_c = builder.get_object("type_treeviewcolumn")
		type_cr = builder.get_object("type_cellrenderer")
		type_c.set_cell_data_func(type_cr, set_type)
		name_c = builder.get_object("name_treeviewcolumn")
		name_cr = builder.get_object("name_cellrenderer")
		name_c.set_cell_data_func(name_cr, set_name)
		self.running_bricks = self.brickfactory.bricks.filter_new()

		def is_running(model, iter):
			brick = model[iter][0]
			if brick:
				return brick.proc is not None
			return False
			# return model[iter][0].proc is not None

		self.running_bricks.set_visible_func(is_running)
		builder.get_object("joblist_treeview").set_model(self.running_bricks)

	# def setup_remotehosts(self):
	# 	builder = self.__setup_treeview("data/remotehosts.ui",
	# 							"scrolledwindow5", "remotehosts_treeview")

	# 	def set_status(column, cell_renderer, model, iter):
	# 		host = model.get_value(iter, 0)
	# 		filename = "connect.png" if host.connected else "disconnect.png"
	# 		pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(
	# 			graphics.get_image(filename), 48, 48)
	# 		cell_renderer.set_property("pixbuf", pixbuf)

	# 	def set_address(column, cell_renderer, model, iter):
	# 		host = model.get_value(iter, 0)
	# 		label = "{0[0]}:{0[1]}".format(host.addr)
	# 		cell_renderer.set_property("text", label)

	# 	def set_num_bricks(column, cell_renderer, model, iter):
	# 		host = model.get_value(iter, 0)
	# 		cell_renderer.set_property("text", str(host.num_bricks()))

	# 	def set_ac(column, cell_renderer, model, iter):
	# 		host = model.get_value(iter, 0)
	# 		cell_renderer.set_property("text",
	# 			"Yes" if host.autoconnect else "No")

	# 	status_c = builder.get_object("status_treeviewcolumn")
	# 	status_cr = builder.get_object("status_cellrenderer")
	# 	status_c.set_cell_data_func(status_cr, set_status)
	# 	address_c = builder.get_object("address_treeviewcolumn")
	# 	address_cr = builder.get_object("address_cellrenderer")
	# 	address_c.set_cell_data_func(address_cr, set_address)
	# 	numbrick_c = builder.get_object("numbrick_treeviewcolumn")
	# 	numbrick_cr = builder.get_object("numbrick_cellrenderer")
	# 	numbrick_c.set_cell_data_func(numbrick_cr, set_num_bricks)
	# 	ac_c = builder.get_object("ac_treeviewcolumn")
	# 	ac_cr = builder.get_object("ac_cellrenderer")
	# 	ac_c.set_cell_data_func(ac_cr, set_ac)
	# 	builder.get_object("remotehosts_treeview").set_model(
	# 		self.brickfactory.remote_hosts)

	def setup_netwoks_cards(self):
		builder = self.__setup_treeview("data/networkcards.ui",
								"scrolledwindow12", "networkcards_treeview")

		def set_vlan(column, cell_renderer, model, iter):
			link = model.get_value(iter, 0)
			cell_renderer.set_property("text", str(link.vlan))

		def set_connection(column, cell_renderer, model, iter):
			link = model.get_value(iter, 0)
			if link.mode == "hostonly":
				conn = "Host"
			elif link.sock:
				conn = link.sock.brick.name
			elif link.mode == "sock" and settings.femaleplugs:
				conn = "Vde socket (female plug)"
			else:
				conn = "None"
			cell_renderer.set_property("text", conn)

		def set_model(column, cell_renderer, model, iter):
			link = model.get_value(iter, 0)
			cell_renderer.set_property("text", link.model)

		def set_mac(column, cell_renderer, model, iter):
			link = model.get_value(iter, 0)
			cell_renderer.set_property("text", link.mac)

		vlan_c = builder.get_object("vlan_treeviewcolumn")
		vlan_cr = builder.get_object("vlan_cellrenderer")
		vlan_c.set_cell_data_func(vlan_cr, set_vlan)
		connection_c = builder.get_object("connection_treeviewcolumn")
		connection_cr = builder.get_object("connection_cellrenderer")
		connection_c.set_cell_data_func(connection_cr, set_connection)
		model_c = builder.get_object("model_treeviewcolumn")
		model_cr = builder.get_object("model_cellrenderer")
		model_c.set_cell_data_func(model_cr, set_model)
		mac_c = builder.get_object("mac_treeviewcolumn")
		mac_cr = builder.get_object("mac_cellrenderer")
		mac_c.set_cell_data_func(mac_cr, set_mac)
		self.vmplugs = builder.get_object("liststore1")

		def sort_links(model, iter1, iter2):
			return cmp(model.get_value(iter1, 0).vlan,
				model.get_value(iter2, 0).vlan)

		self.vmplugs.set_sort_func(0, sort_links)
		self.vmplugs.set_sort_column_id(0, gtk.SORT_ASCENDING)

	def setup_events(self):
		builder = self.__setup_treeview("data/events.ui",
			"events_scrolledwindow", "events_treeview")

		def set_icon(column, cell_renderer, model, iter):
			event = model.get_value(iter, 0)
			pixbuf = graphics.pixbuf_for_brick_at_size(event, 48, 48)
			cell_renderer.set_property("pixbuf", pixbuf)

		def set_status(column, cell_renderer, model, iter):
			event = model.get_value(iter, 0)
			cell_renderer.set_property("text", event.get_state())

		def set_name(column, cell_renderer, model, iter):
			event = model.get_value(iter, 0)
			cell_renderer.set_property("text", event.name)

		def set_parameters(column, cell_renderer, model, iter):
			event = model.get_value(iter, 0)
			cell_renderer.set_property("text", event.get_parameters())

		icon_c = builder.get_object("icon_treeviewcolumn")
		icon_cr = builder.get_object("icon_cellrenderer")
		icon_c.set_cell_data_func(icon_cr, set_icon)
		status_c = builder.get_object("status_treeviewcolumn")
		status_cr = builder.get_object("status_cellrenderer")
		status_c.set_cell_data_func(status_cr, set_status)
		name_c = builder.get_object("name_treeviewcolumn")
		name_cr = builder.get_object("name_cellrenderer")
		name_c.set_cell_data_func(name_cr, set_name)
		parameters_c = builder.get_object("parameters_treeviewcolumn")
		parameters_cr = builder.get_object("parameters_cellrenderer")
		parameters_c.set_cell_data_func(parameters_cr, set_parameters)
		self.__events_treeview = builder.get_object("events_treeview")
		self.__events_treeview.set_model(self.brickfactory.events)

	def setup_bricks(self):
		builder = self.__setup_treeview("data/bricks.ui",
			"bricks_scrolledwindow", "bricks_treeview")

		def set_icon(column, cell_renderer, model, iter):
			brick = model.get_value(iter, 0)
			pixbuf = graphics.pixbuf_for_brick_at_size(brick, 48, 48)
			cell_renderer.set_property("pixbuf", pixbuf)

		def set_status(column, cell_renderer, model, iter):
			brick = model.get_value(iter, 0)
			cell_renderer.set_property("text", brick.get_state())

		def set_type(column, cell_renderer, model, iter):
			brick = model.get_value(iter, 0)
			cell_renderer.set_property("text", brick.get_type())

		def set_name(column, cell_renderer, model, iter):
			brick = model.get_value(iter, 0)
			cell_renderer.set_property("text", brick.name)

		def set_parameters(column, cell_renderer, model, iter):
			brick = model.get_value(iter, 0)
			cell_renderer.set_property("text", brick.get_parameters())

		icon_c = builder.get_object("icon_treeviewcolumn")
		icon_cr = builder.get_object("icon_cellrenderer")
		icon_c.set_cell_data_func(icon_cr, set_icon)
		status_c = builder.get_object("status_treeviewcolumn")
		status_cr = builder.get_object("status_cellrenderer")
		status_c.set_cell_data_func(status_cr, set_status)
		type_c = builder.get_object("type_treeviewcolumn")
		type_cr = builder.get_object("type_cellrenderer")
		type_c.set_cell_data_func(type_cr, set_type)
		name_c = builder.get_object("name_treeviewcolumn")
		name_cr = builder.get_object("name_cellrenderer")
		name_c.set_cell_data_func(name_cr, set_name)
		parameters_c = builder.get_object("parameters_treeviewcolumn")
		parameters_cr = builder.get_object("parameters_cellrenderer")
		parameters_c.set_cell_data_func(parameters_cr, set_parameters)
		self.__bricks_treeview = builder.get_object("bricks_treeview")
		self.__bricks_treeview.set_model(self.brickfactory.bricks)

	def setup_router_devs(self):
		pass
		# self.routerdevs = tree.VBTree(self, "treeview_router_netdev", None,
		# 						[str, str, str],
		# 						["Eth", "connection", "macaddr"])

	def setup_router_routes(self):
		pass

		# ''' TW with Router routes '''
		# self.routerroutes = tree.VBTree(self, 'treeview_router_routes', None,
    # [gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING],
		# [ 'Destination','Netmask','Gateway','Via','metric'])

	def setup_router_filters(self):
		pass
		# ''' TW with Router filters '''
		# self.routerfilters = tree.VBTree(self, 'treeview_router_filters', None,
    # [gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING],
		# [ 'Dev','Source','Destination','Protocol','TOS','Action'])

	def check_gui_prerequisites(self):
		qmissing, _ = tools.check_missing_qemu(settings.get("qemupath"))
		vmissing = tools.check_missing_vde(settings.get("vdepath"))
		ksmissing = []
		if not os.access("/sys/kernel/mm/ksm",os.X_OK):
			ksmissing.append("ksm")
		return vmissing + qmissing + ksmissing

	def get_object(self, name):
		return self.gladefile.get_widget(name)

	""" ******************************************************** 	"""
	""" Signal handlers                                           """
	""" ******************************************************** 	"""

	def on_brick_changed(self, model, path, iter):
		self.draw_topology()

	"""
	" ******************************************************** "
	" ******************************************************** "
	" ******************************************************** "
	" BRICK CONFIGURATION
	"	'PREPARE' METHODS
	"			--  fill panel form with current brick/event
	"				configuration
	"""
	def config_brick_prepare(self, b):
		"""fill the current configuration in the config interface.
		This is the global method to fill in all the forms
		in the configuration panel for bricks and events
		"""

		# Fill socks combobox
		for k in self.sockscombo_names():
			combo = ComboBox(self.gladefile.get_widget(k))
			opt=dict()
			# add Ad-hoc host only to the vmehternet
			if settings.femaleplugs:
				opt['Vde socket']='_sock'

			for so in self.brickfactory.socks:
				if (so.brick.homehost == b.homehost or (b.get_type() == 'Wire'
											and settings.python)) and \
				(so.brick.get_type().startswith('Switch') or settings.femaleplugs):
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
		__, found = tools.check_missing_qemu(settings.get("qemupath"))
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
				if (b.config["base" + hd] and
						b.config[hd].set_image(b.config["base" + hd])):
					images.select(b.config["base" + hd])
				else:
					images.select("Off")

		# Qemu: usb devices bind button
		if b.get_type() == "Qemu":
			if b.config["usbmode"]:
				self.gladefile.get_widget('vm_usb_show').set_sensitive(True)
			else:
				self.gladefile.get_widget('vm_usb_show').set_sensitive(False)
				b.config["usbdevlist"] = ""


		# Qemu: check if KVM is checkable
		if b.get_type()=="Qemu":
			if settings.kvm or b.homehost:
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_sensitive(True)
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_label("KVM")
			else:
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_sensitive(False)
				self.gladefile.get_widget('cfg_Qemu_kvm_check').set_label(_("KVM is disabled"))
				b.config["kvm"] = False

		self.__update_vmplugs_tree()

		t = b.get_type()
		for key in b.config.keys():
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "check")
			if widget is not None:
				if b.config[key]:
					if key is "kvm" and settings.kvm:
						widget.set_active(True)
					elif key is not "kvm":
						widget.set_active(True)
				else:
					widget.set_active(False)
				if b.get_type() == 'Wirefilter':
					#Trigger wirefilter "symmetrical" checkbox management
					if key is "speedenable":
						self.on_wf_speed_checkbox_toggle(widget)
					#Trigger wirefilter "speed" section management
					else:
						self.on_symm_toggle(widget)

		t = b.get_type()
		for key in b.config.keys():
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "text")
			if widget is not None:
				widget.set_text(b.config.get(key))

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "spinint")
			if widget is not None and b.config.get(key):
				widget.set_value(b.config[key])
			if t == "Switch" and key == 'numports':
				nports = 0
				for it in self.brickfactory.bricks:
					for p in [p for p in it.plugs if p.configured()]:
						if p.sock.nickname == b.socks[0].nickname:
							nports += 1
				if nports > 0:
					widget.set_range(nports, 128)
				else:
					widget.set_range(1,128)


			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "combo")
			if widget is not None and dicts.has_key(key):
				for k, v in dicts[key].iteritems():
					if v == b.config.get(key):
						ComboBox(self.gladefile.get_widget("cfg_"+t+"_"+key+"_combo")).select(k)

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "comboinitial")
			if widget is not None:
				model = widget.get_model()
				iter_ = model.get_iter_first()
				i = 0
				while iter_:
					if model.get_value(iter_, 0) == b.config.get(key):
						widget.set_active(i)
						break
					else:
						iter_ = model.iter_next(iter_)
						i = i + 1

			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "filechooser")
			if widget is not None and b.config.get(key):
				widget.set_filename(b.config.get(key))
			elif (widget is not None and t == 'Qemu' and
					(key[0:4] == 'base' or key == 'cdrom')):
				widget.set_current_folder(settings.get('baseimages'))
			elif widget is not None:
				widget.unselect_all()

			self.gladefile.get_widget("qemuicon").set_from_pixbuf(
				graphics.pixbuf_for_running_brick(b))

	"""
	" ******************************************************** "
	" ******************************************************** "
	" ******************************************************** "
	" BRICK CONFIGURATION
	"	'CONFIRM' METHODS
	"			--  store new parameters from the form into the
	"				brick configuration if the modifies are
	"				confirmed.
	"""
	'''
	' Widget to params reads the config directly from
	' gtk widgets.
	' If the widget name is in the format:
	' 	- cfg_<type>_<variablename>_<widgettype>
	' the configuration will be read automatically.
	'''
	def widget_to_params(self, b):
		"""Widget to params reads the config directly from
		gtk widgets.
		If the widget name is in the format:
			- cfg_<type>_<variablename>_<widgettype>
		the configuration will be read automatically.
		"""

		parameters = {}
		for key in b.config.keys():
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
		return parameters

	'''
	' Specific per-type confirm methods
	'''

	def config_Wirefilter_confirm(self,b):
		sel = ComboBox(self.gladefile.get_widget('sockscombo_wirefilter0')).get_selected()
		for so in self.brickfactory.socks:
			if sel == so.nickname:
				b.plugs[0].connect(so)
		sel = ComboBox(self.gladefile.get_widget('sockscombo_wirefilter1')).get_selected()
		for so in self.brickfactory.socks:
			if sel == so.nickname:
				b.plugs[1].connect(so)

	def config_brick_confirm(self):
		if self.__config_panel:
			self.__config_panel.configure_brick(self)
		else:
			self._config_brick_confirm()

	def _config_brick_confirm(self):
		"""Main configuration confirm method.  called from on_config_ok"""

		notebook = self.gladefile.get_widget('main_notebook')
		# is it an event?
		if notebook.get_current_page() == 1:
			b = self.__get_selection(self.__events_treeview)
		else:
			b = self.__get_selection(self.__bricks_treeview)
		parameters = widget_to_params(b, self.gladefile.get_widget)
		t = b.get_type()

		if t == "Wirefilter":
			self.config_Wirefilter_confirm(b)

		b.set(parameters)

	def config_brick_cancel(self):
		self.curtain_down()

	"""
	" ******************************************************** "
	" ******************************************************** "
	" ******************************************************** "
	" MISC GUI FUNCTIONS
	"
	"""

	'''
	'	Systray management
	'''
	def start_systray(self):
		if self.statusicon is None:
			self.statusicon = gtk.StatusIcon()
			self.statusicon.set_from_file(graphics.get_image("virtualbricks.png"))
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

	def systray_blinking(self, disable=False):
		if self.statusicon is not None and self.statusicon.get_visible():
			self.statusicon.set_blinking(not disable)


	'''
	'	Method to catch delete event from dialog windows.
	'	Hide the main window into systray.
	'''

	def delete_event(self,window,event):
		#don't delete; hide instead
		if settings.systray and self.statusicon is not None:
			self.gladefile.get_widget("main_win").hide_on_delete()
			self.statusicon.set_tooltip("VirtualBricks Hidden")
		else:
			self.quit_d.callback(None)
		return True

	def curtain_down(self):
		self.get_object("top_panel").show_all()
		self.get_object("config_panel").hide()
		self.get_object("padding_panel").hide()
		self.get_object("label_showhidesettings").set_text(_("Show Settings"))
		configframe = self.gladefile.get_widget("configframe")
		configpanel = configframe.get_child()
		if configpanel:
			configframe.remove(configpanel)
		self.__config_panel = None
		self.__summary_table = None
		self.curtain_is_down = True

	def __fill_config_table(self, brick, table):
		table.foreach(table.remove)
		table.resize(len(brick.config), 2)
		for i, (name, value) in enumerate((name, brick.config.get(name))
				for name in sorted(brick.config)):
			nlabel = gtk.Label("%s:" % name)
			nlabel.set_alignment(1.0, 0.5)
			nlabel.set_padding(0, 2)
			table.attach(nlabel, 0, 1, i, i + 1, gtk.FILL, gtk.FILL)
			vlabel = gtk.Label(value)
			vlabel.set_alignment(0.0, 0.5)
			vlabel.set_padding(0, 2)
			table.attach(vlabel, 1, 2, i, i + 1, gtk.FILL, gtk.FILL)

	def __get_brick_summary_frame(self, brick, panel):
		builder = gtk.Builder()
		builder.add_from_file(graphics.get_filename("virtualbricks.gui",
			"data/brickconfigsummary.ui"))
		builder.get_object("label").set_markup(_("<b>%s(%s) settings</b>")
			% (brick.get_name(), brick.get_type()))
		builder.get_object("image").set_from_pixbuf(
			graphics.pixbuf_for_running_brick(brick))
		self.__summary_table = table = builder.get_object("table")
		self.__fill_config_table(brick, table)
		builder.get_object("vbox").pack_start(panel, True, True, 0)
		return builder.get_object("frame")

	def _show_config_for_brick(self, brick, configpanel):
		# log.debug("Found custom config panel")
		self.__config_panel = configpanel
		self.__hide_panels()
		frame = self.__get_brick_summary_frame(brick,
			configpanel.get_view(self))
		configframe = self.get_object("configframe")
		configframe.add(frame)
		configframe.show_all()
		self.__show_config(brick.get_name())

	def curtain_up(self, brick=None):
		if brick is None:
			notebook = self.gladefile.get_widget("main_notebook")
			if notebook.get_current_page() == 0:
				brick = self.__get_selection(self.__bricks_treeview)
			elif notebook.get_current_page() == 1:
				brick = self.__get_selection(self.__events_treeview)

		if brick is not None:
			configpanel = interfaces.IConfigController(brick, None)
			if configpanel is not None:
				self._show_config_for_brick(brick, configpanel)
				return
		self._curtain_up()

	def __hide_panels(self):
		for name in TYPE_CONFIG_WIDGET_NAME_MAP.itervalues():
			self.gladefile.get_widget(name).hide()

	def __show_config(self, name):
		self.get_object("top_panel").hide()
		self.get_object("config_panel").show()
		# self.get_object("padding_panel").show()
		self.get_object("label_showhidesettings").set_text(
			_("Hide Settings"))
		self.curtain_is_down = False
		self.widg["main_win"].set_title(
			"Virtualbricks (Configuring Brick %s)" % name)

	def __get_selection(self, treeview):
		selection = treeview.get_selection()
		if selection is not None:
			model, iter = selection.get_selected()
			if iter is not None:
				return model.get_value(iter, 0)

	def _curtain_up(self):
		notebook = self.gladefile.get_widget("main_notebook")
		if notebook.get_current_page() != 0:
			return
		self.__hide_panels()
		brick = self.__get_selection(self.__bricks_treeview)
		if brick is None:
			return
		log.debug("config brick %s (%s)", brick.get_name(), brick.get_type())
		try:
			name = TYPE_CONFIG_WIDGET_NAME_MAP[brick.get_type()]
		except KeyError:
			log.debug("Error: invalid brick type")
			self.curtain_down()
			return
		ww = self.gladefile.get_widget(name)
		self.config_brick_prepare(brick)
		ww.show()
		self.__show_config(brick.get_name())


	'''
	'	Methods to access treestore elements
	'''

	def get_treeselected(self, tree, store, pthinfo, c):
		if pthinfo is not None:
			path, col, cellx, celly = pthinfo
			tree.grab_focus()
			tree.set_cursor(path, col, 0)
			iter_ = store.model.get_iter(path)
			name = store.model.get_value(iter_, c)
			self.config_last_iter = iter_
			return name
		return ""

	def get_treeselected_name(self, t, s, p):
		return self.get_treeselected(t, s, p, 3)

	def get_treeselected_type(self, t, s, p):
		return self.get_treeselected(t, s, p, 2)

	'''
	'	populate a list of all the widget whose names
	'	are listed in parameter l
	'''
	def get_widgets(self, l):
		r = dict()
		for i in l:
			r[i] = self.gladefile.get_widget(i)
			r[i].hide()
		return r

	'''
	'	method that returns a dictionary
	'	containing the eth models, to fill in the
	'	model selection combobox
	'''
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

	'''
	'	Returns a list with all the
	'	dialog windows names
	'''
	def widgetnames(self):
		return ['main_win',
		'dialog_settings',
		'dialog_bookmarks',
		'menu_popup_bookmarks',
		'menu_popup_imagelist',
		'dialog_jobmonitor',
		'menu_popup_usbhost',
		'menu_popup_usbguest',
		'menu_popup_volumes',
		'dialog_newnetcard',
		'dialog_confirm_action',
		'dialog_new_redirect',
		'ifconfig_win',
		'dialog_newbrick',
		'menu_brickactions',
		'dialog_confirm',
		'dialog_convertimage',
		]
	'''
	'	Returns a list with all the combos
	'	that provide a list of vde socks nicknames
	'''
	def sockscombo_names(self):
		return [
		'sockscombo_wirefilter0',
		'sockscombo_wirefilter1',
		'sockscombo_router_netconf'
		]

	def show_window(self, name):
		self.curtain_down()
		for w in self.widg.keys():
			if name == w or w == 'main_win':
				if w.startswith('menu'):
					self.widg[w].popup(None, None, None, 3, 0)
				else:
					self.widg[w].show()
			elif not name.startswith('menu'):
				self.widg[w].hide()

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
	"""                                                          """
	""" EVENTS / SIGNALS                                         """
	"""                                                          """
	"""                                                          """
	""" ******************************************************** """

	def ask_remove_brick(self, brick):
		if brick.proc is not None:
			other = _("\nThe brick is still running, it will be "
					"killed before being deleted!")
		else:
			other = None
		self.__ask_for_deletion(self.brickfactory.del_brick, brick, other)

	def ask_remove_event(self, event):
		if event.scheduled is not None:
			other = _("The event is in use, it will be stopped before.")
		else:
			other = None
		self.__ask_for_deletion(self.brickfactory.del_event, event, other)

	def __ask_for_deletion(self, on_yes, what, secondary_text=None):
		question = _("Do you really want to delete %s (%s)?") % (
			what.name, what.get_type())
		dialog = dialogs.ConfirmDialog(question, on_yes=on_yes,
				on_yes_arg=what)
		if secondary_text is not None:
			dialog.format_secondary_text(secondary_text)
		dialog.window.set_transient_for(self.widg["main_win"])
		dialog.show()

	def on_bricks_treeview_key_release_event(self, treeview, event):
		if gtk.gdk.keyval_name(event.keyval) in set(["Delete", "BackSpace"]):
			brick = self.__get_selection(treeview)
			if brick is not None:
				self.ask_remove_brick(brick)

	def on_events_treeview_key_release_event(self, treeview, event):
		if gtk.gdk.keyval_name(event.keyval) in set(["Delete", "BackSpace"]):
			event = self.__get_selection(treeview)
			if event is not None:
				self.ask_remove_event(event)

	def on_systray_menu_toggle(self, widget=None, data=""):
		if self.statusicon.get_blinking():
			self.systray_blinking(True)
			return

		if not self.gladefile.get_widget("main_win").get_visible():
			self.gladefile.get_widget("main_win").show_all()
			self.curtain_down()
			self.statusicon.set_tooltip("the window is visible")
		else:
			self.gladefile.get_widget("main_win").hide()

	def on_systray_exit(self, widget=None, data=""):
		self.quit_d.callback(None)

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
		for ntype in ['Switch','Tap','Wire','Wirefilter','TunnelConnect','TunnelListen','Qemu','Capture', 'SwitchWrapper', 'Router']:
			if self.gladefile.get_widget('typebutton_'+ntype).get_active():
				return ntype
		return 'Switch'

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
			except errors.InvalidNameError:
				log.error(_("Cannot create brick: Invalid name."))
			else:
				log.debug("Created successfully")
		else:
			try:
				self.brickfactory.newbrick(ntype, name)
			except errors.InvalidNameError:
				log.error(_("Cannot create brick: Invalid name."))
			else:
				log.debug("Created successfully")


	def on_config_cancel(self, widget=None, data=""):
		self.config_brick_cancel()
		self.curtain_down()

	def on_config_ok(self, widget=None, data=""):
		self.config_brick_confirm()
		self.curtain_down()

	def on_config_save(self, widget=None, data=""):
		# TODO: update config values
		self.config_brick_confirm()
		if self.__config_panel:
			self.__fill_config_table(self.__config_panel.original,
				self.__summary_table)
			self.__summary_table.show_all()

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

		frame.hide()
		frame_LR.hide()
		frame_RL.hide()
		if widget.get_active():
			text_LR.set_text("")
			if text_jitter_LR:
				text_jitter_LR.set_text("")
			text_RL.set_text("")
			if text_jitter_RL:
				text_jitter_RL.set_text("")
			frame.show_all()
			text.set_text("")
			if text_jitter:
				text_jitter.set_text("")
		else:
			text.set_text("")
			if text_jitter:
				text_jitter.set_text("")
			frame_LR.show_all()
			frame_RL.show_all()


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
			#frame.set_sensitive(False)
			#frame_LR.set_sensitive(False)
			#frame_RL.set_sensitive(False)
			frame.show_all()
			frame_LR.hide()
			frame_RL.hide()
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
	def jitter_str(self):
		return " " + _("\nJitter is the variation from the "
			"base value. Jitter 10 percent for a "
			"base value of 100 means the final value goes from 90 to 110. "
			"The distribution can be Uniform or Gaussian normal "
			"(more than 98% of the values are inside the limits).")

	def bandwidth_help(self):
		#Do NOT change string layout please
		return _("\t\t\tCHANNEL BANDWIDTH\n\n"
			"Sender is not prevented "
			"from sending packets, delivery is delayed to limit the bandwidth "
			"to the desired value (like a bottleneck along the path)."
			) + self.jitter_str()

	def speed_help(self):
		#Do NOT change string layout please
		return _("\t\t\tINTERFACE SPEED\n\n"
			"Input is blocked for the tramission time of the packet, thus the "
			"sender is prevented from sending too fast.\n"
			"This feature can be confusing, consider using bandwidth."
			) + self.jitter_str()

	def delay_help(self):
		#Do NOT change string layout please
		return _("\t\t\tDELAY\n\n"
			"Extra delay (in milliseconds). This delay is added to the real "
			"communication delay. Packets are temporarily stored and resent "
			"after the delay.") + self.jitter_str()

	def chanbufsize_help(self):
		#Do NOT change string layout please
		return _("\t\t\tCHANNEL BUFFER SIZE\n\n"
			"Maximum size of the packet "
			"queue. Exceeding packets are discarded.") + self.jitter_str()

	def loss_help(self):
		#Do NOT change string layout please
		return _("\t\t\tPACKET LOSS\n\n"
			"Percentage of loss as a floating point number."
			) + self.jitter_str()

	def dup_help(self):
		#Do NOT change string layout please
		return _("\t\t\tPACKET DUPLICATION\n\n"
			"Percentage of dup packet. Do not use dup factor 100% because it "
			"means that each packet is sent infinite times."
			) + self.jitter_str()

	def noise_help(self):
		#Do NOT change string layout please
		return _("\t\t\tNOISE\n\n"
			"Number of bits damaged/one megabyte (megabit)."
			) + self.jitter_str()

	def lostburst_help(self):
		#Do NOT change string layout please
		return _("\t\t\tLOST BURST\n\n"
			"When this is not zero, wirefilter uses the Gilbert model for "
			"bursty errors. This is the mean length of lost packet bursts."
			) + self.jitter_str()

	def mtu_help(self):
		#Do NOT change string layout please
		return _("\t\t\tMTU: MAXIMUM TRANSMISSION UNIT\n\n"
			"Packets longer than specified size are discarded.")

	def on_item_quit_activate(self, widget=None, data=""):
		self.quit_d.callback(None)

	def on_item_settings_activate(self, widget=None, data=""):
		self.gladefile.get_widget('filechooserbutton_qemupath').set_current_folder(settings.get('qemupath'))
		self.gladefile.get_widget('filechooserbutton_vdepath').set_current_folder(settings.get('vdepath'))
		self.gladefile.get_widget('filechooserbutton_baseimages').set_current_folder(settings.get('baseimages'))

		cowfmt = settings.get('cowfmt')

		if cowfmt == 'qcow2':
			self.gladefile.get_widget('combo_cowfmt').set_active(2)
		elif cowfmt == 'qcow':
			self.gladefile.get_widget('combo_cowfmt').set_active(1)
		else: #default to cow
			self.gladefile.get_widget('combo_cowfmt').set_active(0)

		if self.disable_config_kvm:
			self.gladefile.get_widget('check_kvm').set_sensitive(False)
		else:
			self.gladefile.get_widget('check_kvm').set_sensitive(True)

		if self.disable_config_ksm:
			self.gladefile.get_widget('check_ksm').set_sensitive(False)
		else:
			self.gladefile.get_widget('check_ksm').set_sensitive(True)

		if settings.kvm:
			self.gladefile.get_widget('check_kvm').set_active(True)
		else:
			self.gladefile.get_widget('check_kvm').set_active(False)

		if settings.ksm:
			self.gladefile.get_widget('check_ksm').set_active(True)
		else:
			self.gladefile.get_widget('check_ksm').set_active(False)

		if settings.kqemu:
			self.gladefile.get_widget('check_kqemu').set_active(True)
		else:
			self.gladefile.get_widget('check_kqemu').set_active(False)

		if settings.femaleplugs:
			self.gladefile.get_widget('check_femaleplugs').set_active(True)
		else:
			self.gladefile.get_widget('check_femaleplugs').set_active(False)

		if settings.erroronloop:
			self.gladefile.get_widget('check_erroronloop').set_active(True)
		else:
			self.gladefile.get_widget('check_erroronloop').set_active(False)

		if settings.python:
			self.gladefile.get_widget('check_python').set_active(True)
		else:
			self.gladefile.get_widget('check_python').set_active(False)

		if settings.systray:
			self.gladefile.get_widget('check_systray').set_active(True)
		else:
			self.gladefile.get_widget('check_systray').set_active(False)

		if settings.show_missing:
			self.gladefile.get_widget('check_show_missing').set_active(True)
		else:
			self.gladefile.get_widget('check_show_missing').set_active(False)

		self.gladefile.get_widget('entry_term').set_text(settings.get('term'))
		self.gladefile.get_widget('entry_sudo').set_text(settings.get('sudo'))
		self.curtain_down()
		self.show_window('dialog_settings')

	def on_item_settings_autoshow_activate(self, widget=None, data=""):
		raise NotImplementedError("on_item_settings_autoshow_activate not implemented")

	def on_item_settings_autohide_activate(self, widget=None, data=""):
		raise NotImplementedError("on_item_settings_autohide_activate not implemented")

	def on_item_about_activate(self, widget=None, data=""):
		dialogs.AboutDialog().show()

	def on_toolbutton_launchxterm_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_toolbutton_launchxterm_clicked not implemented")

	def on_toolbutton_start_all_clicked(self, widget=None, data=""):

		def started_all(results):
			for success, value in results:
				if not success:
					log.err(value, "Brick not started.")
			self.running_bricks.refilter()

		self.curtain_down()
		bricks = self.brickfactory.bricks
		l = []
		for idx, brick in enumerate(bricks):
			d = brick.poweron()
			d.addCallback(changed, gtk.TreeRowReference(bricks, idx))
			l.append(d)
		defer.DeferredList(l, consumeErrors=True).addCallback(started_all)

	def on_toolbutton_stop_all_clicked(self, widget=None, data=""):

		def stopped_all(results):
			self.running_bricks.refilter()

		self.curtain_down()
		bricks = self.brickfactory.bricks
		l = []
		for idx, brick in enumerate(bricks):
			d = brick.poweroff()
			d.addCallback(changed, gtk.TreeRowReference(bricks, idx))
			l.append(d)
		defer.DeferredList(l, consumeErrors=True).addCallback(stopped_all)

	def on_toolbutton_start_all_events_clicked(self, widget=None, data=""):
		self.curtain_down()
		events = self.brickfactory.events
		for idx, event in enumerate(events):
			d = event.poweron()
			d.addCallback(changed, gtk.TreeRowReference(events, idx))
			events.row_changed(idx, events.get_iter(idx))

	def on_toolbutton_stop_all_events_clicked(self, widget=None, data=""):
		self.curtain_down()
		events = self.brickfactory.events
		for idx, event in enumerate(events):
			event.poweroff()
			events.row_changed(idx, events.get_iter(idx))

	def show_brickactions(self):
		brick = self.__get_selection(self.__bricks_treeview)
		if brick.get_type() == "Qemu":
			self.set_sensitivegroup(['vmresume'])
		else:
			self.set_nonsensitivegroup(['vmresume'])
		self.gladefile.get_widget("brickaction_name").set_label(brick.name)
		self.show_window('menu_brickactions')

	def on_bricks_treeview_button_release_event(self, treeview, event):
		if event.button == 3:
			pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
			if pthinfo is not None:
				path, col, cellx, celly = pthinfo
				treeview.grab_focus()
				treeview.set_cursor(path, col, 0)
				model = treeview.get_model()
				obj = model.get_value(model.get_iter(path), 0)
				interfaces.IMenu(obj).popup(event.button, event.time, self)
			return True

	def on_events_treeview_button_release_event(self, treeview, event):
		return self.on_bricks_treeview_button_release_event(treeview, event)

	def on_bricks_treeview_row_activated(self, treeview, path, column):
		model = treeview.get_model()
		iter = model.get_iter(path)
		brick = model.get_value(iter, 0)
		self.startstop_brick(brick)

	def on_events_treeview_row_activated(self, treeview, path, column):
		model = treeview.get_model()
		event = model.get_value(model.get_iter(path), 0)
		event.toggle().addCallback(changed, gtk.TreeRowReference(model, path))

	def on_focus_out(self, widget=None, event=None , data=""):
		self.curtain_down()

	def startstop_brick(self, brick):
		d = brick.poweron() if brick.proc is None else brick.poweroff()
		d.addCallback(changed_brick_in_model, self.brickfactory.bricks)
		d.addCallbacks(lambda _: self.running_bricks.refilter(), log.err)

	# def on_remotehosts_treeview_button_release_event(self, treeview, event):
	# 	if event.button == 3:
	# 		pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
	# 		if pthinfo is not None:
	# 			path, col, cellx, celly = pthinfo
	# 			treeview.grab_focus()
	# 			treeview.set_cursor(path, col, 0)
	# 			model = treeview.get_model()
	# 			obj = model.get_value(model.get_iter(path), 0)
	# 			interfaces.IMenu(obj).popup(event.button, event.time, self)
	# 		return True

	# def on_remotehosts_treeview_button_press_event(self, treeview, event):
	# 	if event.button == 1 and event.type == gtk.gdk._2BUTTON_PRESS:
	# 		pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
	# 		if pthinfo is not None:
	# 			path, col, cellx, celly = pthinfo
	# 			treeview.grab_focus()
	# 			treeview.set_cursor(path, col, 0)
	# 			model = treeview.get_model()
	# 			remote_host = model.get_value(model.get_iter(path), 0)
	# 			if remote_host.connected:
	# 				self.user_wait_action(remote_host.disconnect)
	# 			else:
	# 				# XXX: this will block
	# 				conn_ok, msg = remote_host.connect()
	# 				if not conn_ok:
	# 					log.error("Error connecting to remote host %s: %s",
	# 						remote_host.addr[0], msg)
	# 		return True

	def on_joblist_treeview_button_release_event(self, treeview, event):
		if event.button == 3:
			pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
			if pthinfo is not None:
				path, col, cellx, celly = pthinfo
				treeview.grab_focus()
				treeview.set_cursor(path, col, 0)
				model = treeview.get_model()
				brick = model.get_value(model.get_iter(path), 0)
				interfaces.IJobMenu(brick).popup(event.button, event.time, self)
				return True

	def on_button_togglesettings_clicked(self, widget=None, data=""):
		if self.curtain_is_down:
			self.curtain_up()
			self.curtain_is_down = False
		else:
			self.curtain_down()
			self.curtain_is_down = True

	def on_dialog_settings_delete_event(self, widget=None, event=None, data=""):
		"""we could use deletable property but deletable is only available in
		GTK+ 2.10 and above"""
		widget.hide()
		return True

	def on_dialog_close(self, widget=None, data=""):
		self.show_window('')
		return True


	def on_dialog_settings_response(self, widget=None, response=0, data=""):
		if response == gtk.RESPONSE_CANCEL:
			widget.hide()
			return

		if response in [gtk.RESPONSE_APPLY, gtk.RESPONSE_OK]:
			log.debug("Apply settings...")
			for k in ['qemupath', 'vdepath', 'baseimages']:
				settings.set(k, self.gladefile.get_widget('filechooserbutton_'+k).get_filename())

			settings.set('cowfmt', self.gladefile.get_widget('combo_cowfmt').get_active_text())

			if self.gladefile.get_widget('check_kvm').get_active():
				settings.set("kvm", True)
			else:
				settings.set("kvm", False)

			ksm = self.gladefile.get_widget('check_ksm').get_active()
			settings.set("ksm", ksm)
			tools.enable_ksm(ksm, settings.get("sudo"))

			if self.gladefile.get_widget('check_kqemu').get_active():
				settings.set("kqemu", True)
			else:
				settings.set("kqemu", False)

			if self.gladefile.get_widget('check_python').get_active():
				settings.set("python", True)
			else:
				settings.set("python", False)

			if self.gladefile.get_widget('check_femaleplugs').get_active():
				settings.set("femaleplugs", True)
			else:
				settings.set("femaleplugs", False)

			if self.gladefile.get_widget('check_erroronloop').get_active():
				settings.set("erroronloop", True)
			else:
				settings.set("erroronloop", False)

			if self.gladefile.get_widget('check_systray').get_active():
				settings.set('systray', True)
				self.start_systray()
			else:
				settings.set('systray', False)
				self.stop_systray()

			if self.gladefile.get_widget('check_show_missing').get_active():
				settings.set('show_missing', True)
				self.start_systray()
			else:
				settings.set('show_missing', False)
				self.stop_systray()

			settings.set("term", self.gladefile.get_widget('entry_term').get_text())
			settings.set("sudo", self.gladefile.get_widget('entry_sudo').get_text())

			settings.store()

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
			brick = self.__get_selection(self.__bricks_treeview)
			startevents = self.gladefile.get_widget('start_events_avail_treeview')
			stopevents = self.gladefile.get_widget('stop_events_avail_treeview')
			model, iter_ = startevents.get_selection().get_selected()
			if iter_:
				brick.config["pon_vbevent"] = model[iter_][2]
			else:
				brick.config["pon_vbevent"] = ""
			model, iter_ = stopevents.get_selection().get_selected()
			if iter_:
				brick.config["poff_vbevent"] = model[iter_][2]
			else:
				brick.config["poff_vbevent"] = ""

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
		raise NotImplementedError("on_treeview_cdromdrives_row_activated not implemented")

	def on_button_settings_add_cdevice_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_button_settings_add_cdevice_clicked not implemented")

	def on_button_settings_rem_cdevice_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_button_settings_rem_cdevice_clicked not implemented")

	def on_treeview_qemupaths_row_activated(self, widget=None, data=""):
		raise NotImplementedError("on_treeview_qemupaths_row_activated not implemented")

	def on_button_settings_add_qemubin_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_button_settings_add_qemubin_clicked not implemented")

	def on_button_settings_rem_qemubin_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_button_settings_rem_qemubin_clicked not implemented")

	def on_dialog_bookmarks_response(self, widget=None, data=""):
		raise NotImplementedError("on_dialog_bookmarks_response not implemented")

	def on_edit_bookmark_activate(self, widget=None, data=""):
		raise NotImplementedError("on_edit_bookmark_activate not implemented")

	def on_bookmark_info_activate(self, widget=None, data=""):
		raise NotImplementedError("on_bookmark_info_activate not implemented")

	def on_delete_bookmark_activate(self, widget=None, data=""):
		raise NotImplementedError("on_delete_bookmark_activate not implemented")

	def on_filechooserbutton_newimage_dest_selection_changed(self, widget=None, data=""):
		raise NotImplementedError("on_filechooserbutton_newimage_dest_selection_changed not implemented")

	def on_filechooserbutton_newimage_dest_current_folder_changed(self, widget=None, data=""):
		raise NotImplementedError("on_filechooserbutton_newimage_dest_current_folder_changed not implemented")

	def on_entry_newimage_name_changed(self, widget=None, data=""):
		pass

	def on_combobox_newimage_format_changed(self, widget=None, data=""):
		pass

	def on_spinbutton_newimage_size_changed(self, widget=None, data=""):
		raise NotImplementedError("on_spinbutton_newimage_size_changed not implemented")

	def on_combobox_newimage_sizeunit_changed(self, widget=None, data=""):
		raise NotImplementedError("on_combobox_newimage_sizeunit_changed not implemented")

	def on_filechooserdialog_openimage_response(self, dialog, response):
		pass

	def on_button_openimage_cancel_clicked(self, widget=None, data=""):
		pass

	def on_button_openimage_open_clicked(self, button):
		pass

	def on_image_newfromfile(self, menuitem):
		dialogs.choose_new_image(self, self.brickfactory)

	def on_image_library(self, widget=None, data=""):
		dialogs.DisksLibraryDialog(self.brickfactory).show()

	def on_image_newempty(self, widget=None, data=""):
		dialogs.CreateImageDialog(self.brickfactory).show(
			self.get_object("main_win"))

	def on_item_create_image_activate(self, widget=None, data=""):
		dialogs.CreateImageDialog(self.brickfactory).show(
			self.get_object("main_win"))

	def image_create (self):
		log.msg("Image creating.. ",)
		path = self.get_object("filechooserbutton_newimage_dest").get_filename() + "/"
		filename = self.get_object("entry_newimage_name").get_text()
		img_format = self.get_object("combobox_newimage_format").get_active_text()
		img_size = str(self.get_object("spinbutton_newimage_size").get_value())
		#Get size unit and remove the last character "B"
		#because qemu-img want k, M, G or T suffixes.
		unit = self.gladefile.get_widget("combobox_newimage_sizeunit").get_active_text()[1]
		# XXX: use a two value combobox
		if not filename:
			log.err(_("Choose a filename first!"))
			return
		if img_format == "Auto":
			img_format = "raw"
		fullname = "%s%s.%s" % (path, filename, img_format)
		exe = "qemu-img"
		args = [exe, "create", "-f", img_format, fullname, img_size+unit]
		done = defer.Deferred()
		reactor.spawnProcess(QemuImgCreateProtocol(done), exe, args,
			os.environ)
		done.addCallback(
			lambda _: self.brickfactory.new_disk_image(filename, fullname))
		done.addErrback(log.err)
		return done

	def on_button_create_image_clicked(self, widget=None, data=""):
		self.curtain_down()
		self.user_wait_action(self.image_create)

	def on_dialog_messages_response(self, widget=None, data=""):
		raise NotImplementedError("on_dialog_messages_response not implemented")

	def on_item_info_activate(self, widget=None, data=""):
		raise NotImplementedError("on_item_info_activate not implemented")

	def on_item_bookmark_activate(self, widget=None, data=""):
		raise NotImplementedError("on_item_bookmark_activate not implemented")

	def on_dialog_jobmonitor_response(self, widget=None, data=""):
		raise NotImplementedError("on_dialog_jobmonitor_response not implemented")

	def on_toolbutton_stop_job_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_toolbutton_stop_job_clicked not implemented")

	def on_toolbutton_reset_job_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_toolbutton_reset_job_clicked not implemented")

	def on_toolbutton_pause_job_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_toolbutton_pause_job_clicked not implemented")

	def on_toolbutton_rerun_job_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_toolbutton_rerun_job_clicked not implemented")

	def on_treeview_jobmon_volumes_button_press_event(self, widget=None, data=""):
		raise NotImplementedError("on_treeview_jobmon_volumes_button_press_event not implemented")

	def on_treeview_jobmon_volumes_row_activated(self, widget=None, data=""):
		raise NotImplementedError("on_treeview_jobmon_volumes_row_activated not implemented")

	def on_button_jobmon_apply_cdrom_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_button_jobmon_apply_cdrom_clicked not implemented")

	def on_button_jobmon_apply_fda_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_button_jobmon_apply_fda_clicked not implemented")

	def on_button_jobmon_apply_fdb_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_button_jobmon_apply_fdb_clicked not implemented")

	def on_combobox_jobmon_cdrom_changed(self, widget=None, data=""):
		raise NotImplementedError("on_combobox_jobmon_cdrom_changed not implemented")

	def on_combobox_jobmon_fda_changed(self, widget=None, data=""):
		raise NotImplementedError("on_combobox_jobmon_fda_changed not implemented")

	def on_combobox_jobmon_fdb_changed(self, widget=None, data=""):
		raise NotImplementedError("on_combobox_jobmon_fdb_changed not implemented")

	def on_treeview_usbhost_button_press_event(self, widget=None, data=""):
		raise NotImplementedError("on_treeview_usbhost_button_press_event not implemented")

	def on_treeview_usbhost_row_activated(self, widget=None, data=""):
		raise NotImplementedError("on_treeview_usbhost_row_activated not implemented")

	def on_treeview_usbguest_button_press_event(self, widget=None, data=""):
		raise NotImplementedError("on_treeview_usbguest_button_press_event not implemented")

	def on_treeview_usbguest_row_activated(self, widget=None, data=""):
		raise NotImplementedError("on_treeview_usbguest_row_activated not implemented")

	def on_attach_device_activate(self, widget=None, data=""):
		raise NotImplementedError("on_attach_device_activate not implemented")

	def on_detach_device_activate(self, widget=None, data=""):
		raise NotImplementedError("on_detach_device_activate not implemented")

	def on_item_eject_activate(self, widget=None, data=""):
		raise NotImplementedError("on_item_eject_activate not implemented")

	def on_dialog_newnetcard_response(self, widget=None, data=""):
		raise NotImplementedError("on_dialog_newnetcard_response not implemented")

	def on_combobox_networktype_changed(self, widget=None, data=""):
		raise NotImplementedError("on_combobox_networktype_changed not implemented")

	def on_entry_network_macaddr_changed(self, widget=None, data=""):
		raise NotImplementedError("on_entry_network_macaddr_changed not implemented")

	def on_entry_network_ip_changed(self, widget=None, data=""):
		raise NotImplementedError("on_entry_network_ip_changed not implemented")

	def on_spinbutton_network_port_changed(self, widget=None, data=""):
		raise NotImplementedError("on_spinbutton_network_port_changed not implemented")

	def on_spinbutton_network_vlan_changed(self, widget=None, data=""):
		raise NotImplementedError("on_spinbutton_network_vlan_changed not implemented")

	def on_entry_network_ifacename_changed(self, widget=None, data=""):
		raise NotImplementedError("on_entry_network_ifacename_changed not implemented")

	def on_entry_network_tuntapscript_changed(self, widget=None, data=""):
		raise NotImplementedError("on_entry_network_tuntapscript_changed not implemented")

	def on_button__network_open_tuntap_file_clicked(self, widget=None, data=""):
		raise NotImplementedError("on_button__network_open_tuntap_file_clicked not implemented")

	def on_spinbutton_network_filedescriptor_changed(self, widget=None, data=""):
		raise NotImplementedError("on_spinbutton_network_filedescriptor_changed not implemented")

	def on_dialog_new_redirect_response(self, widget=None, data=""):
		raise NotImplementedError("on_dialog_new_redirect_response not implemented")

	def on_radiobutton_redirect_TCP_toggled(self, widget=None, data=""):
		raise NotImplementedError("on_radiobutton_redirect_TCP_toggled not implemented")

	def on_radiobutton_redirect_UDP_toggled(self, widget=None, data=""):
		raise NotImplementedError("on_radiobutton_redirect_UDP_toggled not implemented")

	def on_spinbutton_redirect_sport_changed(self, widget=None, data=""):
		raise NotImplementedError("on_spinbutton_redirect_sport_changed not implemented")

	def on_entry_redirect_gIP_changed(self, widget=None, data=""):
		raise NotImplementedError("on_entry_redirect_gIP_changed not implemented")

	def on_spinbutton_redirect_dport_changed(self, widget=None, data=""):
		raise NotImplementedError("on_spinbutton_redirect_dport_changed not implemented")

	def on_newbrick(self, widget=None, event=None, data=""):
		self.curtain_down()
		self.gladefile.get_widget('text_newbrickname').set_text("")
		self.show_window('dialog_newbrick')

	def on_newevent(self, widget=None, event=None, data=""):
		dialog = dialogs.NewEventDialog(self)
		dialog.window.set_transient_for(self.widg["main_win"])
		dialog.show()

	def on_testconfig(self, widget=None, event=None, data=""):
		raise NotImplementedError("on_testconfig not implemented")

	def on_autodetectsettings(self, widget=None, event=None, data=""):
		raise NotImplementedError("on_autodetectsettings not implemented")

	def on_check_kvm(self, widget=None, event=None, data=""):
		if widget.get_active():
			kvm = tools.check_kvm(settings.get("qemupath"))
			if not kvm:
				log.error(_("No KVM support found on the local system. "
					"Check your active configuration. "
					"KVM will stay disabled."))
			widget.set_active(kvm)

	def on_add_cdrom(self, widget=None, event=None, data=""):
		raise NotImplementedError("on_add_cdrom not implemented")

	def on_remove_cdrom(self, widget=None, event=None, data=""):
		raise NotImplementedError("on_remove_cdrom not implemented")

	def on_event_configure(self,widget=None, event=None, data=""):
		self.curtain_up()
		return

	def on_dialog_rename_response(self, widget=None, response=0, data=""):
		widget.hide()
		if response == 1:
			try:
				brick = self.__get_selection(self.__bricks_treeview)
				self.brickfactory.renamebrick(brick, self.gladefile.get_widget('entry_brick_newname').get_text())
			except errors.InvalidNameError:
				log.error(_("Invalid name!"))

	def on_qemupath_changed(self, widget, data=None):
		newpath = widget.get_filename()
		missing_qemu = False
		missing_kvm = False
		missing, found = tools.check_missing_qemu(newpath)
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
		missing = tools.check_missing_vde(newpath)
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
		brick = self.__get_selection(self.__bricks_treeview)
		if brick.get_type() != 'Qemu':
			return

		combo = ComboBox(widget)
		path = settings.get('qemupath')

		#Machine COMBO
		machine_c = ComboBox(self.gladefile.get_widget("cfg_Qemu_machine_combo"))
		opt_m = dict()
		os.system(path + "/" + combo.get_selected() + " -M ? >" +
			settings.VIRTUALBRICKS_HOME + "/.vmachines")
		for m in open(settings.VIRTUALBRICKS_HOME + "/.vmachines").readlines():
			if not re.search('machines are', m):
				v = m.split(' ')[0]
				k = m.lstrip(v).rstrip('/n')
				while (k.startswith(' ')):
					k = k.lstrip(' ')
				opt_m[v]=v
		toSelect=""
		for k, v in opt_m.iteritems():
			if v.strip() == brick.config["machine"].strip():
				toSelect=k
		machine_c.populate(opt_m, toSelect)
		os.unlink(settings.VIRTUALBRICKS_HOME + "/.vmachines")

		#CPU combo
		opt_c = dict()
		cpu_c = ComboBox(self.gladefile.get_widget("cfg_Qemu_cpu_combo"))
		os.system(path + "/" + combo.get_selected() + " -cpu ? >" +
			settings.VIRTUALBRICKS_HOME + "/.cpus")
		for m in open(settings.VIRTUALBRICKS_HOME + "/.cpus").readlines():
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
		cpu_c.populate(opt_c, brick.config["cpu"])
		os.unlink(settings.VIRTUALBRICKS_HOME + "/.cpus")

	def on_check_kvm_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			brick = self.__get_selection(self.__bricks_treeview)
			if not brick.homehost:
				kvm = tools.check_kvm(settings.get("qemupath"))
				self.kvm_toggle_all(True)
				if not kvm:
					log.error(_("No KVM support found on the system. "
						"Check your active configuration. "
						"KVM will stay disabled."))
				widget.set_active(kvm)
			else:
				self.kvm_toggle_all(True)
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

	def on_addplug_button_clicked(self, button):
		brick = self.__get_selection(self.__bricks_treeview)
		if brick is not None:
			dialog = dialogs.EthernetDialog(self, brick)
			dialog.window.set_transient_for(self.widg["main_win"])
			dialog.show()

	def __update_vmplugs_tree(self):
		b = self.__get_selection(self.__bricks_treeview)
		if b is None:
			return

		if b.get_type() == 'Qemu':
			self.vmplugs.clear()
			for plug in b.plugs:
				self.vmplugs.append((plug, ))

			if settings.femaleplugs:
				for sock in b.socks:
					self.vmplugs.append((sock,))

	def remove_link(self, link):
		if link.brick.proc and link.hotdel:
			link.hotdel()
		link.brick.remove_plug(link.vlan)
		get_value = self.vmplugs.get_value
		iter_next = self.vmplugs.iter_next
		i = self.vmplugs.get_iter_first()
		while i:
			l = get_value(i, 0)
			if link is l:
				self.vmplugs.remove(i)
				break
			i = iter_next(i)

	def ask_remove_link(self, link):
		question = _("Do you really want to delete eth%d network interface") \
				% link.vlan
		dialog = dialogs.ConfirmDialog(question, on_yes=self.remove_link,
				on_yes_arg=link)
		dialog.window.set_transient_for(self.widg["main_win"])
		dialog.show()

	def on_networkcards_treeview_key_press_event(self, treeview, event):
		if gtk.gdk.keyval_from_name("Delete") == event.keyval:
			brick = self.__get_selection(self.__bricks_treeview)
			if brick is not None:
				selection = treeview.get_selection()
				model, itr = selection.get_selected()
				if itr is not None:
					self.ask_remove_link(model.get_value(itr, 0))
					return True

	def on_networkcards_treeview_button_release_event(self, treeview, event):
		if event.button == 3:
			pthinfo = treeview.get_path_at_pos(int(event.x), int(event.y))
			if pthinfo is not None:
				path, col, cellx, celly = pthinfo
				treeview.grab_focus()
				treeview.set_cursor(path, col, 0)
				model = treeview.get_model()
				obj = model.get_value(model.get_iter(path), 0)
				interfaces.IMenu(obj).popup(event.button, event.time, self)
				return True

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
		self.gladefile.get_widget("qemuicon").set_from_pixbuf(
			graphics.pixbuf_for_brick_type("qemu"))

	def on_show_messages_activate(self, menuitem, data=None):
		dialogs.LoggingWindow(self.messages_buffer).show()

	def on_dialog_messages_close_event(self, widget=None, event=None, data=""):
		self.on_dialog_messages_delete_event(self)
		return True

	def on_dialog_messages_delete_event(self, widget=None, event=None, data=""):
		messages = self.gladefile.get_widget("dialog_messages")
		messages.hide()
		return True

	def on_brick_attach_event(self, menuitem, data=None):
		attach_event_window = self.gladefile.get_widget("dialog_attach_event")

		# columns = (COL_ICON, COL_TYPE, COL_NAME, COL_CONFIG) = range(4)
		COL_ICON, COL_TYPE, COL_NAME, COL_CONFIG = range(4)

		startavailevents = self.gladefile.get_widget('start_events_avail_treeview')
		stopavailevents = self.gladefile.get_widget('stop_events_avail_treeview')

		eventsmodel = gtk.ListStore (gtk.gdk.Pixbuf, str, str, str)

		startavailevents.set_model(eventsmodel)
		stopavailevents.set_model(eventsmodel)

		treeviewselectionstart = startavailevents.get_selection()
		treeviewselectionstart.unselect_all()
		treeviewselectionstop = stopavailevents.get_selection()
		treeviewselectionstop.unselect_all()
		brick = self.__get_selection(self.__bricks_treeview)

		for event in self.brickfactory.events:
			if event.configured():
				parameters = event.get_parameters()
				if len(parameters) > 30:
					parameters = "%s..." % parameters[:30]
				image = graphics.pixbuf_for_running_brick_at_size(event, 48, 48)
				iter_ = eventsmodel.append([image, event.get_type(), event.name, parameters])
				if brick.config["pon_vbevent"] == event.name:
					treeviewselectionstart.select_iter(iter_)
				if brick.config["poff_vbevent"] == event.name:
					treeviewselectionstop.select_iter(iter_)

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

	def __on_dialog_response(self, dialog, response_id, do_action):
		try:
			if response_id == gtk.RESPONSE_OK:
				filename = dialog.get_filename()
				if dialog.get_action() == gtk.FILE_CHOOSER_ACTION_SAVE:
					ext = ".vbl"
					if not filename.endswith(ext):
						filename += ext
				current_project = settings.get("current_project")
				settings.set("current_project", filename)
				try:
					do_action(filename)
				except IOError:
					settings.set("current_project", current_project)
				else:
					try:
						settings.store()
					except IOError:
						log.exception("Cannot save settings")
		finally:
			dialog.destroy()

	def __open_project(self, filename):
		self._stop_listening()
		try:
			configfile.restore(self.brickfactory, filename)
		finally:
			self._start_listening()
			self.draw_topology()
			# self.check_joblist(force=True)

	def on_open_project(self, widget, data=None):
		if self.confirm(_("Save current project?")):
			configfile.safe_save(self.brickfactory)

		chooser = gtk.FileChooserDialog(title=_("Open a project"),
				action=gtk.FILE_CHOOSER_ACTION_OPEN,
				buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
						gtk.STOCK_OPEN, gtk.RESPONSE_OK))
		chooser.set_current_folder(settings.VIRTUALBRICKS_HOME)
		chooser.add_filter(self.vbl_filter)
		chooser.add_filter(self.all_files_filter)
		chooser.connect("response", self.__on_dialog_response,
				self.__open_project)
		chooser.show()

	def __save_project(self, filename):
		configfile.safe_save(self.brickfactory, filename)

	def on_save_project(self, menuitem):
		chooser = gtk.FileChooserDialog(title=_("Save as..."),
				action=gtk.FILE_CHOOSER_ACTION_SAVE,
				buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
						gtk.STOCK_SAVE,gtk.RESPONSE_OK))
		chooser.set_do_overwrite_confirmation(True)
		chooser.set_current_folder(settings.VIRTUALBRICKS_HOME)
		chooser.add_filter(self.vbl_filter)
		chooser.add_filter(self.all_files_filter)
		chooser.connect("response", self.__on_dialog_response,
				self.__save_project)
		chooser.show()

	def on_import_project(self, widget, data=None):
		raise NotImplementedError("on_import_project not implemented")

	def __new_project(self, filename):
		self._stop_listening()
		try:
			self.brickfactory.reset()
			with open(filename, "w+"):
				pass
		except IOError:
			log.exception("Exception occurred while starting new project")
			raise
		finally:
			self._start_listening()
			self.draw_topology()
			# self.check_joblist(force=True)

	def on_new_project(self, widget, data=None):
		if self.confirm("Save current project?"):
			configfile.safe_save(self.brickfactory)

		chooser = gtk.FileChooserDialog(title=_("New project"),
				action=gtk.FILE_CHOOSER_ACTION_SAVE,
				buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
						gtk.STOCK_SAVE, gtk.RESPONSE_OK))
		chooser.set_do_overwrite_confirmation(True)
		chooser.set_current_folder(settings.VIRTUALBRICKS_HOME)
		chooser.add_filter(self.vbl_filter)
		chooser.add_filter(self.all_files_filter)
		chooser.connect("response", self.__on_dialog_response,
				self.__new_project)
		chooser.show()

	def on_open_recent_project(self, widget, data=None):
		raise NotImplementedError("on_open_recent_project not implemented")

	# def on_add_remotehost(self, widget, data=None):
	# 	hostname = self.gladefile.get_widget("newhost_text").get_text()
	# 	if len(hostname) > 0:
	# 		self.brickfactory.get_host_by_name(hostname)

	def on_check_newbrick_runremote_toggled(self, widget, event=None, data=None):
		self.gladefile.get_widget('text_newbrick_runremote').set_sensitive(widget.get_active())

	def on_usbmode_onoff(self, w, event=None, data=None):
		brick = self.__get_selection(self.__bricks_treeview)
		if w.get_active():
			brick.config["usbmode"] = True
		else:
			brick.config["usbmode"] = False
			brick.config["usbdevlist"] = ""
		self.gladefile.get_widget('vm_usb_show').set_sensitive(w.get_active())

	def usb_show(self):

		def show_dialog(output):
			dialog = dialogs.UsbDevWindow(self, output.strip(), vm)
			dialog.window.set_transient_for(self.widg["main_win"])
			dialog.show()

		vm = self.__get_selection(self.__bricks_treeview)
		devices = utils.getProcessOutput("lsusb", env=os.environ)
		devices.addCallback(show_dialog).addErrback(log.err)
        log.msg("Searching USB devices")

	def on_usb_show(self, button):
		self.user_wait_action(self.usb_show)

	def do_image_convert(self, arg=None):
		raise NotImplementedError("do_image_convert")
		# src = self.gladefile.get_widget('filechooser_imageconvert_source').get_filename()
		# fmt = self.gladefile.get_widget('combobox_imageconvert_format').get_active_text()
		# # dst = src.rstrip(src.split('.')[-1]).rstrip('.')+'.'+fmt
		# src.rstrip(src.split('.')[-1]).rstrip('.')+'.'+fmt
		# # self.user_wait_action(self.exec_image_convert)
		# self.exec_image_convert()

	def on_convertimage_convert(self, widget, event=None, data=None):
		if self.gladefile.get_widget('filechooser_imageconvert_source').get_filename() is None:
			log.error("Select a file")
			return

		# src = self.gladefile.get_widget('filechooser_imageconvert_source').get_filename()
		# fmt = self.gladefile.get_widget('combobox_imageconvert_format').get_active_text()
		if not os.access(os.path.dirname(self.gladefile.get_widget('filechooser_imageconvert_source').get_filename()), os.W_OK):
			log.error("Cannot write to the specified location")
		else:
			self.do_image_convert()

		self.show_window('')
		return True

	def on_commit_menuitem_activate(self, menuitem):
		dialog = dialogs.CommitImageDialog(self.brickfactory)
		dialog.show(self.get_object("main_win"))

	def on_convert_image(self,widget,event=None, data=None):
		self.gladefile.get_widget('combobox_imageconvert_format').set_active(2)
		self.show_window('dialog_convertimage')


	def on_router_netconf_auto_mac_checked(self, widget, event=None, data=None):
		macaddr_txtfield = self.gladefile.get_widget('entry_router_netconf_mac')
		if widget.get_active():
			macaddr_txtfield.set_sensitive(False)
			macaddr_txtfield.set_text('')
		else:
			macaddr_txtfield.set_sensitive(True)

	def on_router_netconf_dhcpd_onoff(self, widget, event=None, data=None):
		group = ['label_dhcpserv0', 'label_dhcpserv1', 'entry_router_netconf_dhcp_start', 'entry_router_netconf_dhcp_end']
		if widget.get_active():
			self.set_sensitivegroup(group)
		else:
			self.set_nonsensitivegroup(group)

	def on_router_filter_src_onoff(self, widget, event=None, data=None):
		group = ['hbox_filter_src_iface']
		if widget.get_active():
			self.set_sensitivegroup(group)
		else:
			self.set_nonsensitivegroup(group)

	def on_router_filter_from_onoff(self, widget, event=None, data=None):
		group = ['table_filter_srcaddr']
		if widget.get_active():
			self.set_sensitivegroup(group)
		else:
			self.set_nonsensitivegroup(group)

	def on_router_filter_to_onoff(self, widget, event=None, data=None):
		group = ['table_filter_dstaddr']
		if widget.get_active():
			self.set_sensitivegroup(group)
		else:
			self.set_nonsensitivegroup(group)

	def on_router_filter_proto_onoff(self, widget, event=None, data=None):
		group = ['table_filter_proto']
		if widget.get_active():
			self.set_sensitivegroup(group)
		else:
			self.set_nonsensitivegroup(group)

	def on_router_filter_tos_onoff(self, widget, event=None, data=None):
		group = ['hbox_filter_tos']
		if widget.get_active():
			self.set_sensitivegroup(group)
		else:
			self.set_nonsensitivegroup(group)



	def signals(self):
		self.gladefile.signal_autoconnect(self)

	""" ******************************************************** """
	"""                                                          """
	""" TIMERS                                                   """
	"""                                                          """
	"""                                                          """
	""" ******************************************************** """

	def _main_window_set_insensitive(self):
		window = self.get_object("main_win")
		window.set_sensitive(False)
		progressbar = self.get_object("userwait_progressbar")
		lc = task.LoopingCall(progressbar.pulse)
		wait_window = self.get_object("window_userwait")
		wait_window.set_transient_for(window)
		wait_window.show_all()
		lc.start(0.2, False)
		return lc

	def _main_window_set_sensitive(self, _, lc):
		self.get_object("window_userwait").hide()
		self.get_object("main_win").set_sensitive(True)
		lc.stop()

	def user_wait_action(self, action, *args):
		lc = self._main_window_set_insensitive()
		if isinstance(action, defer.Deferred):
			done = action
		else:
			done = defer.maybeDeferred(action, *args)
		done.addBoth(self._main_window_set_sensitive, lc)


class List(gtk.ListStore):

	def __init__(self):
		gtk.ListStore.__init__(self, object)

	def __iter__(self):
		i = self.get_iter_first()
		while i:
			yield self.get_value(i, 0)
			i = self.iter_next(i)

	def append(self, element):
		gtk.ListStore.append(self, (element, ))

	def remove(self, element):
		i = self.get_iter_first()
		while i:
			el = self.get_value(i, 0)
			if el is element:
				return gtk.ListStore.remove(self, i)
			i = self.iter_next(i)
		raise ValueError("list.remove(x): x not in list")

	# def __getitem__(self, key):
	# 	if isinstance(key, int):
	# 		return gtk.ListStore.__getitem__(self, key)[0]
	# 	elif isinstance(key, slice):
	# 		return [self[idx][0] for idx in xrange(*key.indices(len(self)))]
	# 	else:
	# 		raise TypeError

	def __delitem__(self, key):
		if isinstance(key, int):
			gtk.ListStore.__delitem__(self, key)
		elif isinstance(key, slice):
			if (key.start is None and key.stop is None and
					key.step in (1, -1, None)):
				self.clear()
			else:
				raise TypeError
		else:
			raise TypeError


class VisualFactory(brickfactory.BrickFactory):

	def __init__(self, quit):
		brickfactory.BrickFactory.__init__(self, quit)
		self.events = List()
		self.bricks = List()
		self.disk_images = List()
		self.socks = List()
		# self.remote_hosts = List()


class TextBufferObserver(_log.FileLogObserver):

	def __init__(self, textbuffer):
		textbuffer.create_mark("end", textbuffer.get_end_iter(), False)
		self.textbuffer = textbuffer

	def emit(self, record):
		gobject.idle_add(self._emit, record)

	def _emit(self, eventDict):
		if "record" in eventDict:
			lvl = eventDict["record"].levelname
			text = eventDict["record"].getMessage()
		else:
			lvl = "ERROR" if eventDict["isError"] else "INFO"
			text = _log.textFromEventDict(eventDict)
			if text is None:
				return

		timeStr = self.formatTime(eventDict["time"])
		fmtDict = {"system": eventDict["system"],
					"text": text.replace("\n", "\n\t"),
					"timeStr": timeStr}
		msg = _log._safeFormat("%(timeStr)s [%(system)s] %(text)s\n", fmtDict)
		self.textbuffer.insert_with_tags_by_name(
			self.textbuffer.get_iter_at_mark(self.textbuffer.get_mark("end")),
			msg, lvl)


class MessageDialogObserver:

	def __init__(self, parent=None):
		self.__parent = parent

	def set_parent(self, parent):
		self.__parent = parent

	def emit(self, eventDict):
		if ("show_to_user" not in eventDict and (("record" in eventDict and
				eventDict["record"].levelno >= _compat.ERROR) or
				eventDict["isError"])):
			gobject.idle_add(self._emit, eventDict)

	def _emit(self, eventDict):
		if "record" in eventDict:
			msg = eventDict["record"].getMessage()
		elif "why" in eventDict and eventDict["why"] is not None:
			msg = eventDict["why"]
		elif "failure" in eventDict:
			msg = eventDict["failure"].getErrorMessage()
		else:
			msg = _log.textFromEventDict(eventDict)
			if msg is None:
				return
		dialog = gtk.MessageDialog(self.__parent, gtk.DIALOG_MODAL,
				gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE)
		dialog.set_property('text', msg)
		dialog.connect("response", lambda d, r: d.destroy())
		dialog.show()


TEXT_TAGS = [('DEBUG', {'foreground': '#a29898'}),
			('INFO', {}),
			('WARNING', {'foreground': '#ff9500'}),
			('ERROR', {'foreground': '#b8032e'}),
			('CRITICAL', {'foreground': '#b8032e', 'background': '#000'}),
			('EXCEPTION', {'foreground': '#000', 'background': '#b8032e'})]


class AppLogger(app.AppLogger):

	def start(self, application):
		observer = self._observerFactory()
		if self._logfilename:
			_log.addObserver(self._getLogObserver())
		self._observer = observer
		_log.startLoggingWithObserver(self._observer, False)
		self._initialLog()


class Application(brickfactory.Application):

	factory_factory = VisualFactory

	def __init__(self, config):
		self.textbuffer = gtk.TextBuffer()
		config["logger"] = self.textbuffer_logger
		brickfactory.Application.__init__(self, config)

	def textbuffer_logger(self):
		for name, attrs in TEXT_TAGS:
			self.textbuffer.create_tag(name, **attrs)
		return TextBufferObserver(self.textbuffer).emit

	def install_locale(self):
		brickfactory.Application.install_locale(self)
		gtk.glade.bindtextdomain("virtualbricks", "/usr/share/locale")
		gtk.glade.textdomain("virtualbricks")

	def get_namespace(self):
		return {"gui": self.gui}

	def _run(self, factory, quit):
		# a bug in gtk2 make impossibile to use this and is not required anyway
		gtk.set_interactive(False)
		gladefile = load_gladefile()
		factory.register_brick_type(_gui.GVirtualMachine, "vm", "qemu")
		message_dialog = MessageDialogObserver()
		_log.addObserver(message_dialog.emit)
		# disable default link_button action
		gtk.link_button_set_uri_hook(lambda b, s: None)
		self.gui = VBGUI(factory, gladefile, quit, self.textbuffer)
		message_dialog.set_parent(self.gui.widg["main_win"])  #XXX: ugly hack


def load_gladefile():
	try:
		gladefile = graphics.get_filename("virtualbricks.gui",
									"data/virtualbricks.glade")
		return gtk.glade.XML(gladefile)
	except Exception:
		raise SystemExit("Cannot load gladefile")


# vim: se noet :
