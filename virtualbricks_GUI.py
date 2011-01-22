#!/usr/bin/python
import os, re
import sys
import gtk
import gtk.glade
import virtualbricks_Global as Global
import virtualbricks_Settings as Settings
import virtualbricks_BrickFactory as BrickFactory
import gobject
import time
import pygraphviz as pgv



class VBGUI:
	def __init__(self):
		if not os.access(Settings.MYPATH, os.X_OK):
			os.mkdir(Settings.MYPATH)

		gtk.gdk.threads_init()
		self.brickfactory = BrickFactory.BrickFactory(True)
		self.brickfactory.start()
		try:
			self.gladefile = gtk.glade.XML('./virtualbricks.glade')
		except:
			print "Cannot open required file 'virtualbricks.glade'"
			sys.exit(1)
		self.widg = self.get_widgets(self.widgetnames())
		self.widg['main_win'].show()
		self.ps = []
		self.bricks = []


		self.config = self.brickfactory.settings 
		self.config.load()
		self.signals()
		self.timers()
		self.topology_active = False

		self.sockscombo = dict()
		self.set_nonsensitivegroup(['cfg_Wirefilter_lossburst_text', 'cfg_Wirefilter_mtu_text'])
		self.running_bricks = self.treestore('treeview_joblist', 
			[gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING], 
			['PID','Type','Name'])
		self.bookmarks = self.treestore('treeview_bookmarks', 
				[gtk.gdk.Pixbuf, 
				 gobject.TYPE_STRING, 
				 gobject.TYPE_STRING, 
				 gobject.TYPE_STRING, 
				 gobject.TYPE_STRING], 
				['','Status','Type','Name', 'Parameters'])

		self.vmplugs = self.treestore('treeview_networkcards',
				[	gobject.TYPE_STRING,
					gobject.TYPE_STRING,
					gobject.TYPE_STRING,
					gobject.TYPE_STRING
				],
				['Eth','connection','model','macaddr'])
		
		self.curtain = self.gladefile.get_widget('vpaned_mainwindow')
		self.Dragging = None
		self.curtain_down()
		
		self.selected = None
		self.vmplug_selected = None
		self.joblist_selected = None
		

		try:
			gtk.main()
		except KeyboardInterrupt:
			self.quit()



	""" ******************************************************** """
	"""                                                          """
	""" BRICK CONFIGURATION                                      """
	"""                                                          """
	"""                                                          """
	""" ******************************************************** """
	
	def config_brick_prepare(self):
		# Fill socks combobox
		b = self.selected
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
		missing,found = self.config.check_missing_qemupath(self.config.qemupath)
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
		
		self.update_vmplugs_tree()
		kernelcheck=False
		initrdcheck=False
		
		for key in b.cfg.__dict__.keys():
			t = b.get_type()
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "text")
			if (widget is not None):
				widget.set_text(b.cfg.__dict__[key])
			
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "spinint")
			if (widget is not None and len(b.cfg.__dict__[key]) > 0):
				widget.set_value(int(b.cfg.__dict__[key]))
			
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "spinfloat")
			if (widget is not None):
				widget.set_value(float(b.cfg.__dict__[key]))
			
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "check")
			if (widget is not None):
				if (b.cfg.__dict__[key] == "*"):
					widget.set_active(True)
				else:
					widget.set_active(False)
					
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "combo")
			if (widget is not None and dicts.has_key(key)):
				for k, v in dicts[key].iteritems():
					if (v==b.cfg.__dict__[key]):
						Settings.ComboBox(self.gladefile.get_widget("cfg_"+t+"_"+key+"_combo")).select(k)
			    
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "filechooser")
			if (widget is not None and len(b.cfg.__dict__[key]) > 0):
				widget.set_filename(b.cfg.__dict__[key])
				if key == 'kernel':
					kernelcheck=True
				elif key == 'initrd':
					initrdcheck=True

		self.gladefile.get_widget('check_customkernel').set_active(True)
		self.gladefile.get_widget('check_initrd').set_active(True)
		self.gladefile.get_widget('check_customkernel').set_active(kernelcheck)
		self.gladefile.get_widget('check_initrd').set_active(initrdcheck)
		
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
		b = self.selected
		for key in b.cfg.__dict__.keys():
			t = b.get_type()
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "text")
			if (widget is not None):
				b.cfg.set(key+"="+widget.get_text())
			
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "spinint")
			if (widget is not None):
				b.cfg.set(key+"="+str(int(widget.get_value())))
			
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "spinfloat")
			if (widget is not None):
				b.cfg.set(key+"="+str(widget.get_value()))
			
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "comboinitial")
			if (widget is not None):
				txt = widget.get_active_text()
				if (txt):
					b.cfg.set(key+"="+txt[0])
					
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "combo")
			if (widget is not None):
				combo = Settings.ComboBox(widget)
				#txt = widget.get_active_text()
				txt = combo.get_selected()
				if txt is not None and (txt != "-- default --"):
					b.cfg.set(key+"="+txt)
			
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "check")
			if (widget is not None):
				if widget.get_active():
					b.cfg.set(key+'=*')
				else:
					b.cfg.set(key+'=')
			
			widget = self.gladefile.get_widget("cfg_" + t + "_" + key + "_" + "filechooser")
			if (widget is not None):
				f = widget.get_filename()
				if f:
				  #print f
				  b.cfg.set(key+'='+f)
					
			b.gui_changed = True
			t = b.get_type()

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
					
			if t == 'Qemu':
				k = self.gladefile.get_widget('check_customkernel')
				if not k.get_active():
					b.cfg.kernel=""
				ki = self.gladefile.get_widget('check_initrd')
				if not ki.get_active():
					b.cfg.initrd=""
					
				
		self.curtain_down()
		

	def config_brick_cancel(self):
		self.curtain_down()

	
	""" ******************************************************** """
	"""                                                          """
	""" MISC / WINDOWS BEHAVIOR                                  """
	"""                                                          """
	"""                                                          """
	""" ******************************************************** """

	def curtain_is_down(self):
		print self.curtain.get_position()
		return (self.curtain.get_position()>660)

	def curtain_down(self):
		#print "Old position: %d" % self.curtain.get_position()
		self.curtain.set_position(99999)
		self.gladefile.get_widget('label_showhidesettings').set_text('Show Settings')

	def curtain_up(self):
		print "Old position: %d" % self.curtain.get_position()
		self.gladefile.get_widget('box_vmconfig').hide()
		self.gladefile.get_widget('box_tapconfig').hide()
		self.gladefile.get_widget('box_tunnellconfig').hide()
		self.gladefile.get_widget('box_tunnelcconfig').hide()
		self.gladefile.get_widget('box_wireconfig').hide()
		self.gladefile.get_widget('box_wirefilterconfig').hide()
		self.gladefile.get_widget('box_switchconfig').hide()
		
		if self.selected is None:
			return  
		
		wg = self.curtain
		if self.selected.get_type() == 'Switch':
			print "switch config"
			ww = self.gladefile.get_widget('box_switchconfig')
			wg.set_position(589)	
		
		elif self.selected.get_type() == 'Qemu':
			print "qemu config"
			ww = self.gladefile.get_widget('box_vmconfig')
			wg.set_position(245)

		
		elif self.selected.get_type() == 'Tap':
			print "tap config"
			ww = self.gladefile.get_widget('box_tapconfig')
			wg.set_position(513)	
			
		elif self.selected.get_type() == 'Wire':
			print "wire config"
			ww = self.gladefile.get_widget('box_wireconfig')
			wg.set_position(606)	
		elif self.selected.get_type() == 'Wirefilter':
			print "wirefilter config"
			ww = self.gladefile.get_widget('box_wirefilterconfig')
			wg.set_position(424)	
		elif self.selected.get_type() == 'TunnelConnect':
			print "tunnelc config"
			ww = self.gladefile.get_widget('box_tunnelcconfig')
			wg.set_position(424)	
		elif self.selected.get_type() == 'TunnelListen':
			print "tunnell config"
			ww = self.gladefile.get_widget('box_tunnellconfig')
			wg.set_position(424)	
		self.config_brick_prepare()
		ww.show_all()

		self.gladefile.get_widget('label_showhidesettings').set_text('Hide Settings')
		
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
		

	def quit(self):
		print
		print "GUI: Goodbye!"
		self.brickfactory.quit()
		sys.exit(0)


	def get_widgets(self, l):
		r = dict()
		for i in l:	
			r[i] =  self.gladefile.get_widget(i)
			r[i].hide()
		return r

	def treestore(self, tree_name, fields,names):
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
		'menu_brickactions',
		'dialog_warn',
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
					self.widg[w].popup(None,None,None, 3, 0)
				else:
					self.widg[w].show_all()
			elif not name.startswith('menu') and not name.endswith('dialog_warn'):
				self.widg[w].hide()
	
	""" ******************************************************** """
	"""                                                          """
	""" EVENTS / SIGNALS                                         """
	"""                                                          """
	"""                                                          """
	""" ******************************************************** """
	def on_window1_destroy(self, widget=None, data=""):
		self.quit()
		pass
	def on_windown_destroy(self, widget=None, data=""):
		widget.hide()
		return True

	def error(self, text):
		self.gladefile.get_widget('texterror').set_text(text)
		self.show_window('dialog_warn')
	
	def ask_confirm(self, text, on_yes=None, on_no=None, arg=None):
		self.gladefile.get_widget('lbl_confirm').set_text(text)
		self.on_confirm_response_yes = on_yes
		self.on_confirm_response_no = on_no
		self.on_confirm_response_arg = arg
		self.gladefile.get_widget('dialog_confirm').show_all()

	def on_error_close(self, widget=None, data =""):
		self.widg['dialog_warn'].hide()
		return True

	def on_newbrick_cancel(self, widget=None, data=""):
		self.show_window('')
		
	def on_newbrick_ok(self, widget=None, data=""):
		self.show_window('')
		name = self.gladefile.get_widget('text_newbrickname').get_text()
		ntype = self.gladefile.get_widget('combo_newbricktype').get_active_text()
		try:
			self.brickfactory.newbrick(ntype, name)
		except BrickFactory.InvalidNameException:
			self.error("Cannot create brick: Invalid name.")
		else:
			print "Created successfully"


	def on_config_cancel(self, widget=None, data=""):
		self.config_brick_cancel()
	def on_config_ok(self, widget=None, data=""):
		self.config_brick_confirm()

	def set_sensitivegroup(self,l):
		for i in l:
			w = self.gladefile.get_widget(i)
			w.set_sensitive(True)

	def set_nonsensitivegroup(self,l):
		for i in l:
			w = self.gladefile.get_widget(i)
			w.set_sensitive(False)

	def on_gilbert_toggle(self, widget=None, data=""):	
		if widget.get_active():
			self.gladefile.get_widget('cfg_Wirefilter_lossburst_text').set_sensitive(True)
			self.gladefile.get_widget('cfg_Wirefilter_lossburst_text').set_text("0")
		else:
			self.gladefile.get_widget('cfg_Wirefilter_lossburst_text').set_text("")
			self.gladefile.get_widget('cfg_Wirefilter_lossburst_text').set_sensitive(False)
		
	def on_mtu_toggle(self, widget=None, data=""):
		if widget.get_active():
			self.gladefile.get_widget('cfg_Wirefilter_mtu_text').set_sensitive(True)
			self.gladefile.get_widget('cfg_Wirefilter_mtu_text').set_text("1024")
		else:
			self.gladefile.get_widget('cfg_Wirefilter_mtu_text').set_text("")
			self.gladefile.get_widget('cfg_Wirefilter_mtu_text').set_sensitive(False)
 

	def on_item_quit_activate(self, widget=None, data=""):
		self.quit()
		pass
	def on_item_settings_activate(self, widget=None, data=""):
		self.gladefile.get_widget('filechooserbutton_bricksdirectory').set_filename(self.config.get('bricksdirectory'))	
		self.gladefile.get_widget('filechooserbutton_qemupath').set_filename(self.config.get('qemupath'))	
		self.gladefile.get_widget('filechooserbutton_vdepath').set_filename(self.config.get('vdepath'))	
		self.gladefile.get_widget('filechooserbutton_baseimages').set_filename(self.config.get('baseimages'))	
		if self.config.get('kvm') is "1":
			self.gladefile.get_widget('check_kvm').set_active(True)
		else:
			self.gladefile.get_widget('check_kvm').set_active(False)

		if self.config.get('ksm') is "1":
			self.gladefile.get_widget('check_ksm').set_active(True)
		else:
			self.gladefile.get_widget('check_ksm').set_active(False)

		if self.config.get('kqemu') is "1":
			self.gladefile.get_widget('check_kqemu').set_active(True)
		else:
			self.gladefile.get_widget('check_kqemu').set_active(False)

		if self.config.get('femaleplugs') is "1":
			self.gladefile.get_widget('check_femaleplugs').set_active(True)
		else:
			self.gladefile.get_widget('check_femaleplugs').set_active(False)
		
		if self.config.get('erroronloop') is "1":
			self.gladefile.get_widget('check_erroronloop').set_active(True)
		else:
			self.gladefile.get_widget('check_erroronloop').set_active(False)

		if self.config.get('python') is "1":
			self.gladefile.get_widget('check_python').set_active(True)
		else:
			self.gladefile.get_widget('check_python').set_active(False)

		self.gladefile.get_widget('entry_term').set_text(self.config.get('term'))
		self.gladefile.get_widget('entry_sudo').set_text(self.config.get('sudo'))
		

		self.show_window('dialog_settings')
		pass
	def on_item_settings_autoshow_activate(self, widget=None, data=""):
		print "on_item_settings_autoshow_activate undefined!"
		pass
	def on_item_settings_autohide_activate(self, widget=None, data=""):
		print "on_item_settings_autohide_activate undefined!"
		pass
	

	def on_item_about_activate(self, widget=None, data=""):
		self.show_window('dialog_about1')
		pass
	def on_toolbutton_launchxterm_clicked(self, widget=None, data=""):
		print "on_toolbutton_launchxterm_clicked undefined!"
		pass

	def on_toolbutton_start_all_clicked(self, widget=None, data=""):
		for b in self.bricks:
			if b.proc is None:
				b.poweron()

	def on_toolbutton_stop_all_clicked(self, widget=None, data=""):
		for b in self.bricks:
			if b.proc is not None:
				b.poweroff()
	def on_vpaned_mainwindow_button_release_event(self, widget=None, event=None, data=""):
		tree = self.gladefile.get_widget('treeview_bookmarks');
		store = self.bookmarks
		x = int(event.x)
		y = int(event.y)
		time = event.time
		pthinfo = tree.get_path_at_pos(x, y)
		name = self.get_treeselected_name(tree, store, pthinfo)
		dropbrick = self.brickfactory.getbrickbyname(name)
		if (dropbrick and dropbrick != self.Dragging):
			print "drag&drop!"
			if (len(dropbrick.socks) > 0):
				self.Dragging.connect(dropbrick.socks[0])
			elif (len(self.Dragging.socks) > 0):
				dropbrick.connect(self.Dragging.socks[0])
			
		self.Dragging = None

	def on_treeview_bookmarks_button_press_event(self, widget=None, event=None, data=""):
		tree = self.gladefile.get_widget('treeview_bookmarks');
		store = self.bookmarks
		x = int(event.x)
		y = int(event.y)
		time = event.time
		pthinfo = tree.get_path_at_pos(x, y)
		name = self.get_treeselected_name(tree, store, pthinfo)
		self.Dragging = self.brickfactory.getbrickbyname(name)
		if event.button == 3:
			self.selected = self.brickfactory.getbrickbyname(name)
			if self.selected:
				self.show_window('menu_brickactions')
			
		
	def on_treeview_bookmarks_cursor_changed(self, widget=None, event=None, data=""):
		tree = self.gladefile.get_widget('treeview_bookmarks');
		store = self.bookmarks
		path, focus = tree.get_cursor()
		iter = store.get_iter(path)
		ntype = store.get_value(iter, 2)
		name = store.get_value(iter, 3)
		self.selected = self.brickfactory.getbrickbyname(name)
		self.curtain_down()
		
	def on_treeview_bookmarks_row_activated_event(self, widget=None, event=None , data=""):
		self.tree_startstop()

	def on_treeview_bookmarks_focus_out(self, widget=None, event=None , data=""):
		self.curtain_down()
		self.selected=None

	def tree_startstop(self, widget=None, event=None , data=""):
		tree = self.gladefile.get_widget('treeview_bookmarks');
		store = self.bookmarks
		path, focus = tree.get_cursor()
		iter = store.get_iter(path)
		ntype = store.get_value(iter, 2)
		name = store.get_value(iter, 3)
		b = self.brickfactory.getbrickbyname(name)
		if b.proc is not None:
			b.poweroff()
		else:
			try:
				b.poweron()
			except(BrickFactory.BadConfigException):
				b.gui_changed=True
				self.error("Cannot start this Brick: Brick not configured, yet.")
			except(BrickFactory.NotConnectedException):
				self.error("Cannot start this Brick: Brick not connected.")
			except(BrickFactory.LinkloopException):
				if (self.config.erroronloop):
					error("Loop link detected: aborting operation. If you want to start a looped network, disable the check loop feature in the general settings")
					b.poweroff()
				else:
					pass
				
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
		print "Hello"
		tree = self.gladefile.get_widget('treeview_joblist');
		store = self.running_bricks
		x = int(event.x)
		y = int(event.y)
		time = event.time
		pthinfo = tree.get_path_at_pos(x, y)
		name = self.get_treeselected_name(tree, store, pthinfo)
		if event.button == 3:
			self.joblist_selected = self.brickfactory.getbrickbyname(name)
			if self.joblist_selected:
				self.show_window('menu_popup_joblist')
		pass
	def on_treeview_joblist_row_activated_event(self, widget=None, data=""):
		print "on_treeview_joblist_row_activated_event undefined!"
		pass
	def on_button_togglesettings_clicked(self, widget=None, data=""):
		print "selected: " + repr(self.selected)
		if self.curtain_is_down():
			self.curtain_up()
			print "up"
		else:
			self.curtain_down()
			print "down"
	def on_filechooserdialog_openimage_response(self, widget=None, data=""):
		print "on_filechooserdialog_openimage_response undefined!"
		pass
	def on_button_openimage_cancel_clicked(self, widget=None, data=""):
		print "on_button_openimage_cancel_clicked undefined!"
		pass
	def on_button_openimage_open_clicked(self, widget=None, data=""):
		print "on_button_openimage_open_clicked undefined!"
		pass
	def on_dialog_settings_response(self, widget=None, response=0, data=""):
		if response == gtk.RESPONSE_CANCEL:
			widget.hide()
			return
		if response == gtk.RESPONSE_APPLY or response == gtk.RESPONSE_OK:
			print "Apply settings..."
			for k in ['bricksdirectory', 'qemupath', 'vdepath', 'baseimages']:
				self.config.set(k + '=' + self.gladefile.get_widget('filechooserbutton_'+k).get_filename())
			
			if self.gladefile.get_widget('check_kvm').get_active():
				self.config.set("kvm=1")
			else:
				self.config.set("kvm=0")

			if self.gladefile.get_widget('check_ksm').get_active():
				self.config.set("ksm=1")
				try:
					self.config.check_ksm(True)
				except:
					pass
			else:
				try:
					self.config.check_ksm(False)
				except:
					pass
				self.config.set("ksm=0")

			if self.gladefile.get_widget('check_kqemu').get_active():
				self.config.set("kqemu=1")
			else:
				self.config.set("kqemu=0")
			
			if self.gladefile.get_widget('check_python').get_active():
				self.config.set("python=1")
			else:
				self.config.set("python=0")
			
			if self.gladefile.get_widget('check_femaleplugs').get_active():
				self.config.set("femaleplugs=1")
			else:
				self.config.set("femaleplugs=0")
			
			if self.gladefile.get_widget('check_erroronloop').get_active():
				self.config.set("erroronloop=1")
			else:
				self.config.set("erroronloop=0")
	
			self.config.set("term="+self.gladefile.get_widget('entry_term').get_text())
			self.config.set("sudo="+self.gladefile.get_widget('entry_sudo').get_text())
			
			
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
		self.gladefile.get_widget('combobox_newimage_format').set_active(0)
		self.gladefile.get_widget('combobox_newimage_sizeunit').set_active(1)
		self.show_window('dialog_create_image')
		pass
	      
	def on_button_create_image_clicked(self, widget=None, data=""):
		print "Image creating.. ",
		path = self.gladefile.get_widget('filechooserbutton_newimage_dest').get_filename() + "/"
		filename = self.gladefile.get_widget('entry_newimage_name').get_text()
		img_format = self.gladefile.get_widget('combobox_newimage_format').get_active_text()
		img_size = str(self.gladefile.get_widget('spinbutton_newimage_size').get_value())
		img_sizeunit = self.gladefile.get_widget('combobox_newimage_sizeunit').get_active_text()
		cmd='qemu-img create'
		if filename=="":
		  self.error("Choose a filename first!")
		  return
		if img_format == "Auto":
		  img_format = "raw"		  
		os.system('%s -f %s %s %s' % (cmd, img_format, path+filename+"."+img_format, img_size+img_sizeunit))
		os.system('sync')
		time.sleep(2)
		print '%s -f %s %s %s' % (cmd, img_format, path+filename, img_size+img_sizeunit)
		print ("Done")
		pass

	def on_newimage_close_clicked(self, widget=None, data=""):
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
		print "on_item_jobmonoitor_activate undefined!"
		pass
	def on_item_stop_job_activate(self, widget=None, data=""):
		print "on_item_stop_job_activate undefined!"
		pass
	def on_item_cont_job_activate(self, widget=None, data=""):
		print "on_item_cont_job_activate undefined!"
		pass
	def on_item_reset_job_activate(self, widget=None, data=""):
		print "on_item_reset_job_activate undefined!"
		pass
	def on_item_kill_job_activate(self, widget=None, data=""):
		print "on_item_kill_job_activate undefined!"
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
		self.gladefile.get_widget('combo_newbricktype').set_active(0)
		self.show_window('dialog_newbrick')

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
				self.error("No KVM binary found. Check your active configuration. KVM will stay disabled.")
				widget.set_active(False)
				
			except NotImplementedError:
				print "no support"
				self.error("No KVM support found on the system. Check your active configuration. KVM will stay disabled.")
				widget.set_active(False)

	def on_check_ksm(self, widget=None, event=None, data=""):
		try:
			self.config.check_ksm(True)
		except NotImplementedError:
			print "no support"
			self.error("No KSM support found on the system. Check your configuration. KSM will stay disabled.")
			widget.set_active(False)
	def on_add_cdrom(self, widget=None, event=None, data=""):
		print "signal not connected"
	def on_remove_cdrom(self, widget=None, event=None, data=""):
		print "signal not connected"

	def on_brick_startstop(self,widget=None, event=None, data=""):
		if self.selected is None:
			return
		if self.selected.proc is not None:
			self.selected.poweroff()
		else:
			self.selected.poweron()

	def on_brick_delete(self,widget=None, event=None, data=""):
		if self.selected is None:
			return
		if self.selected.proc != None:
			error("Cannot delete brick: Brick is in use.")
			return
		self.ask_confirm("Do you really want to delete " + self.selected.get_type() + " " + self.selected.name,
				on_yes = self.brickfactory.delbrick, arg = self.selected)
		

	def on_brick_copy(self,widget=None, event=None, data=""):
		if self.selected is None:
			return
		self.brickfactory.dupbrick(self.selected)

	def on_brick_rename(self,widget=None, event=None, data=""):
		if self.selected is None:
			return
		if self.selected.proc != None:
			error("Cannot rename brick: Brick is in use.")
			return

		self.gladefile.get_widget('entry_brick_newname').set_text(self.selected.name)
		self.gladefile.get_widget('dialog_rename').show_all()
	
	def on_dialog_rename_response(self, widget=None, response=0, data=""):
		widget.hide()
		if response == 1:
			try:
				self.brickfactory.renamebrick(self.selected,self.gladefile.get_widget('entry_brick_newname').get_text())
			except BrickFactory.InvalidNameException:
				self.error("Invalid name!")
			
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
			lbl.set_markup('<span color="red">Error:</span>\ninvalid path for qemu binaries')
			return
		
		for t in missing:
			if t == 'qemu':
				missing_qemu = True	
			if t == 'kvm':
				missing_kvm = True
		if missing_qemu and missing_kvm:
			lbl.set_markup('<span color="red">Error:</span>\ncannot find neither qemu nor kvm in this path')
			return
		txt = ""
		if missing_qemu:
			txt = '<span color="red">Warning:</span>\ncannot find qemu, using kvm only\n'
		
		elif missing_kvm:
			txt = '<span color="yellow">Warning:</span>\nkvm not found. KVM support disabled.\n'
		else:
			txt = '<span color="darkgreen">KVM and Qemu detected.</span>\n'
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
			txt += "additional targets supported:\n"
			txt += arch.rstrip(', ')
		lbl.set_markup(txt)

		
	
	def on_vdepath_changed(self, widget, data=None):
		newpath = widget.get_filename()
		missing = self.config.check_missing_vdepath(newpath)
		lbl = self.gladefile.get_widget("label_vdepath_status")
		if not os.access(newpath,os.X_OK):
			lbl.set_markup('<span color="red">Error:</span>\ninvalid path for vde binaries')
		elif len(missing) > 0:
			txt = '<span color="red">Warning, missing modules:</span>\n' 
			for l in missing:
				txt+=l + "\n"
			lbl.set_markup(txt)
		else:
			lbl.set_markup('<span color="darkgreen">All VDE components detected.</span>\n')
	
	def on_arch_changed(self, widget, data=None):
		combo = Settings.ComboBox(widget)
		path = self.config.get('qemupath')
		cpus = Settings.ComboBox(self.gladefile.get_widget('cfg_Qemu_cpu_combo'))
		machines = Settings.ComboBox(self.gladefile.get_widget('cfg_Qemu_machine_combo'))
	
		os.system(path + "/" + combo.get_selected() + " -M ? >" + Settings.MYPATH+"/.vmachines")
		optm={}
		for m in open(Settings.MYPATH+"/.vmachines").readlines():
			if not re.search('machines are', m):
				v = m.split(' ')[0]
				k = m.lstrip(v).rstrip('/n')
				while (k.startswith(' ')):
					k = k.lstrip(' ')
				optm[k] = v
		machines.clear()
		machines.populate(optm)
		os.unlink(Settings.MYPATH+"/.vmachines")
		
		os.system(path + "/" + combo.get_selected() + " -cpu ? >" + Settings.MYPATH+"/.cpus")
		optc={}
		for m in open(Settings.MYPATH+"/.cpus").readlines():
			if not re.search('Available CPU', m):
				if (m.startswith('  ')):
					while (m.startswith(' ')):
						m = m.lstrip(' ')
					if m.endswith('\n'):
						m = m.rstrip('\n')
					optc[m] = m
				else:
					lst = m.split(' ')
					if len(lst) > 1:
						val = m.lstrip(lst[0])
						while (val.startswith(' ')):
							val = val.lstrip(' ')
						if val.endswith('\n'):
							val = val.rstrip('\n')
						optc[val] = val
		cpus.clear()
		cpus.populate(optc)
		os.unlink(Settings.MYPATH+"/.cpus")
		
	def on_check_kvm_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			try:
				self.config.check_kvm()
				self.gladefile.get_widget('cfg_Qemu_argv0_combo').set_sensitive(False)
				self.gladefile.get_widget('cfg_Qemu_cpu_combo').set_sensitive(False)
				self.gladefile.get_widget('cfg_Qemu_machine_combo').set_sensitive(False)
			except IOError:
				print "ioerror"
				self.error("No KVM binary found. Check your active configuration. KVM will stay disabled.")
				widget.set_active(False)
			except NotImplementedError:
				print "no support"
				self.error("No KVM support found on the system. Check your active configuration. KVM will stay disabled.")
				widget.set_active(False)
			else:
				self.gladefile.get_widget('cfg_Qemu_argv0_combo').set_sensitive(True)
				self.gladefile.get_widget('cfg_Qemu_cpu_combo').set_sensitive(True)
				self.gladefile.get_widget('cfg_Qemu_machine_combo').set_sensitive(True)
		
	def on_check_customkernel_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			self.gladefile.get_widget('cfg_Qemu_kernel_filechooser').set_sensitive(True)
		else:
			self.gladefile.get_widget('cfg_Qemu_kernel_filechooser').set_filename('/')
			self.gladefile.get_widget('cfg_Qemu_kernel_filechooser').set_sensitive(False)
	
	def on_check_initrd_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			self.gladefile.get_widget('cfg_Qemu_initrd_filechooser').set_sensitive(True)
		else:
			self.gladefile.get_widget('cfg_Qemu_initrd_filechooser').set_filename('/')
			self.gladefile.get_widget('cfg_Qemu_initrd_filechooser').set_sensitive(False)

	def on_check_gdb_toggled(self, widget=None, event=None, data=""):
		if widget.get_active():
			self.gladefile.get_widget('cfg_Qemu_gdbport_spinint').set_sensitive(True)
		else:
			self.gladefile.get_widget('cfg_Qemu_gdbport_spinint').set_sensitive(False)
	
	def on_random_macaddr(self, widget=None, event=None, data=""):
		self.gladefile.get_widget('vmplug_macaddr').set_text(Global.RandMac())

	def on_vmplug_add(self, widget=None, event=None, data=""):
		
		sockname = Settings.ComboBox(self.gladefile.get_widget('sockscombo_vmethernet')).get_selected()
		if (sockname == '_hostonly'):
			pl = self.selected.add_plug('_hostonly')
		else:
			pl = self.selected.add_plug()
			for so in self.brickfactory.socks:
				if so.nickname == sockname:
					pl.connect(so)
		pl.model = self.gladefile.get_widget('vmplug_model').get_active_text()
		pl.macaddr = self.gladefile.get_widget('vmplug_macaddr').get_text()
		self.update_vmplugs_tree()

	def update_vmplugs_tree(self):
		self.vmplugs.clear()
		if (self.selected.get_type() == 'Qemu'):
			for pl in self.selected.plugs:
				iter = self.vmplugs.append(None, None)
				#self.vmplugs.set_value(iter,0,pl.vlan)
				if pl.mode == 'hostonly':
					self.vmplugs.set_value(iter,1,'Host')
				elif pl.sock:
					self.vmplugs.set_value(iter,1,pl.sock.brick.name)
				self.vmplugs.set_value(iter,2,pl.model)
				self.vmplugs.set_value(iter,3,pl.mac)
			
		
		
		
	def on_vmplug_selected(self, widget=None, event=None, data=""):
		tree = self.gladefile.get_widget('treeview_networkcards');
		store = self.vmplugs
		x = int(event.x)
		y = int(event.y)
		time = event.time
		pthinfo = tree.get_path_at_pos(x, y)
		number = self.get_treeselected(tree, store, pthinfo, 0)
		for pl in self.selected.plugs:
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
		self.selected.plugs.remove(pl)
		del(pl)
		model = Settings.ComboBox(self.gladefile.get_widget('vmplug_model')).get_selected()
		mac = self.gladefile.get_widget('vmplug_macaddr').get_text()
		sockname = Settings.ComboBox(self.gladefile.get_widget('sockscombo_vmethernet')).get_selected()
		if (sockname == '_hostonly'):
			pl = self.selected.add_plug(sockname)
		else:
			for so in self.brickfactory.socks:
				if so.nickname == sockname:
					pl = self.selected.add_plug(so)
		pl.vlan = vlan
		pl.model = model
		pl.mac = mac
		self.update_vmplugs_tree()

	def on_vmplug_remove(self, widget=None, event=None, data=""):
		pl = self.vmplug_selected
		self.selected.remove_plug(pl.vlan)
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
		
			
	def signals(self):
		self.signaldict =  {
			"on_window1_destroy":self.on_window1_destroy,
			"on_windown_destroy":self.on_windown_destroy,
			"on_newbrick_cancel":self.on_newbrick_cancel,
			"on_newbrick_ok":self.on_newbrick_ok,
			"on_error_close":self.on_error_close,
			"on_config_cancel":self.on_config_cancel,
			"on_config_ok":self.on_config_ok,
			"on_gilbert_toggle": self.on_gilbert_toggle,
			"on_mtu_toggle": self.on_mtu_toggle,
			"on_brick_startstop": self.tree_startstop,
			"on_brick_configure": self.on_brick_configure,
			"on_brick_delete": self.on_brick_delete,
			"on_brick_copy": self.on_brick_copy,
			"on_brick_rename": self.on_brick_rename,
			"on_dialog_rename_response": self.on_dialog_rename_response,
			"on_item_quit_activate":self.on_item_quit_activate,
			"on_item_settings_activate":self.on_item_settings_activate,
			"on_item_settings_autoshow_activate":self.on_item_settings_autoshow_activate,
			"on_item_settings_autohide_activate":self.on_item_settings_autohide_activate,
			"on_item_create_image_activate":self.on_item_create_image_activate,
			"on_item_about_activate":self.on_item_about_activate,
			"on_toolbutton_start_all_clicked":self.on_toolbutton_start_all_clicked,
			"on_toolbutton_stop_all_clicked":self.on_toolbutton_stop_all_clicked,
			"on_vpaned_mainwindow_button_release_event":self.on_vpaned_mainwindow_button_release_event,
			"on_treeview_bookmarks_button_press_event":self.on_treeview_bookmarks_button_press_event,
			"on_treeview_bookmarks_cursor_changed":self.on_treeview_bookmarks_cursor_changed,
			"on_treeview_bookmarks_row_activated_event":self.on_treeview_bookmarks_row_activated_event,
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
			"on_button_newimage_close_clicked": self.on_newimage_close_clicked
		}
		self.gladefile.signal_autoconnect(self.signaldict)

	""" ******************************************************** """
	"""                                                          """
	""" TIMERS                                                   """
	"""                                                          """
	"""                                                          """
	""" ******************************************************** """

	def timers(self):
		gobject.timeout_add(1000,self.check_joblist)
		gobject.timeout_add(200,self.check_bricks)

	def check_bricks(self):
		new_bricks = []
		force_render = False
		for b in self.brickfactory.bricks:
			if b.gui_changed:
				b.gui_changed = False
				force_render = True
			new_bricks.append(b)
		if force_render or new_bricks != self.bricks:
			self.bookmarks.clear()
			self.bricks = new_bricks
			tree = self.gladefile.get_widget('treeview_bookmarks')
			for b in self.bricks:
				iter = self.bookmarks.append(None, None)
				state='running'
				if b.proc is not None:
					self.bookmarks.set_value(iter,0,gtk.gdk.pixbuf_new_from_file_at_size(b.get_type()+'.png', 48, 48))
				elif not b.properly_connected():
					self.bookmarks.set_value(iter,0,tree.render_icon(gtk.STOCK_DIALOG_ERROR, gtk.ICON_SIZE_LARGE_TOOLBAR))
					state='disconnected'
				else:
					state='off'
					self.bookmarks.set_value(iter,0,gtk.gdk.pixbuf_new_from_file_at_size(b.get_type()+'.png', 48, 48))

				self.bookmarks.set_value(iter,1,state)
				self.bookmarks.set_value(iter,2,b.get_type())
				self.bookmarks.set_value(iter,3,b.name)

				if (b.get_type() == "Qemu"):
					txt = "command: " + b.prog() + ", "
					txt += "ram: " + b.cfg.ram + ", "
					for p in b.plugs:
						if p.mode == 'hostonly':
							txt+='eth'+str(p.vlan)+': Host, '
						elif p.sock:
							txt+='eth'+str(p.vlan)+': '+ p.sock.nickname+', '
					
					self.bookmarks.set_value(iter, 4, txt.rstrip(', '))
			
					
				if (b.get_type() == "Switch"):
					self.bookmarks.set_value(iter, 4, "Ports:%d" % (int(str(b.cfg.numports))))
				if (b.get_type().startswith("Wire")):
						
					ok = -2
					p0 = "disconnected"
					p1 = "disconnected"
					if (b.plugs[0].sock):
						ok+=1
						p0 = b.plugs[0].sock.brick.name
					if b.plugs[1].sock:
						ok+=1
						p1 = b.plugs[1].sock.brick.name
					if ok == 0:
						self.bookmarks.set_value(iter, 4, "Configured to connect %s to %s" %(p0,p1))
					else:
						self.bookmarks.set_value(iter, 4, "Not yet configured. Left plug is %s and right plug is %s" % (p0,p1))
				if (b.get_type() == "Tap"):
					p0 = "disconnected"
					if b.plugs[0].sock:
						p0 = "plugged to " + b.plugs[0].sock.brick.name 
					self.bookmarks.set_value(iter, 4, p0)
				if (b.get_type() == "TunnelListen"):
					p0 = "disconnected"
					if b.plugs[0].sock:
						p0 = "plugged to " + b.plugs[0].sock.brick.name + ", listening to udp:" + b.cfg.port 
					self.bookmarks.set_value(iter, 4, p0)
				if (b.get_type() == "TunnelConnect"):
					p0 = "disconnected"
					if b.plugs[0].sock:
						p0 = "plugged to " + b.plugs[0].sock.brick.name + ", connecting to udp://" + b.cfg.host
					self.bookmarks.set_value(iter, 4, p0)
					
			print "bricks list updated"
			self.draw_topology()	
		return True
			
			
		
	def check_joblist(self):
		new_ps = []
		for b in self.brickfactory.bricks:
			if b.proc is not None:
				new_ps.append(b)
				ret = b.proc.poll()
				if ret != None:
					b.poweroff()
					self.error("%s '%s' Terminated with code %d" %(b.get_type(), b.name, ret))
					b.gui_changed = True
		
		if self.ps != new_ps:
			self.ps = new_ps
			self.bricks = []
			self.running_bricks.clear()
			for b in self.ps:
				iter = self.running_bricks.append(None, None)
				self.running_bricks.set_value(iter,0,str(b.pid))
				self.running_bricks.set_value(iter,1,b.get_type())
				self.running_bricks.set_value(iter,2,b.name)
			print "proc list updated"
		return True

	def draw_topology(self):
		topowidget = self.gladefile.get_widget('image_topology')
		topo=pgv.AGraph()
		topo.graph_attr['rankdir']='TB'
		topo.graph_attr['ranksep']='1.2'

		# Add nodes
		sg = topo.add_subgraph([],name="switches_rank")
		sg.graph_attr['rank'] = 'same'
		for b in self.bricks:
		### I would like to use this code, but pygraphviz has a bug.
		#	if b.get_type() == 'Switch' or b.get_type().startswith('Wire'):
		#		sg.add_node(b.name)
		#		n = sg.get_node(b.name)
		#		print n
		#		n.attr['shape']='none'
		#		n.attr['fontsize']='9'
		#		n.attr['image']=b.get_type()+'.png'
		#	else:
				topo.add_node(b.name)
				n = topo.get_node(b.name)
				print n
				n.attr['shape']='none'
				n.attr['fontsize']='9'
				n.attr['image']=b.get_type()+'.png'


		for b in self.bricks:
			for e in b.plugs:
				if e.sock is not None:
					topo.add_edge(b.name, e.sock.brick.name)
					e = topo.get_edge(b.name, e.sock.brick.name)
					e.attr['dir'] = 'none'
					e.attr['color'] = 'black'
					e.attr['name'] = "      "
					e.attr['decorate']='true'
					

		#draw and save
		topo.write("/tmp/vde.dot")
		topo.layout('dot')
		topo.draw("/tmp/vde_topology.png")
		topowidget.set_from_file("/tmp/vde_topology.png")
