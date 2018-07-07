# -*- test-case-name: virtualbricks.tests.test_dialogs -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2018 Virtualbricks team

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

# This module is ported to new GTK3 using PyGObject

"""
Utility module to work with gtkbuilder.

When a new dialog is created a new glade project must be created. All the UI
definitions must live inside the `virtualbricks/gui/` package source
directory.

Then a new class should subclass the `Dialog` class and define at least the
`resource` class attribute with the name of the file (`data/resourcefile`). If
the `name` class attribute is not defined, the name of the new class should be
same of the main window in the ui definition.

Here the about dialog example.

    1. First of all the UI definition. The file is `about.ui` in the
       `virtualbricks/gui/data` directory. In this case the main widget/window
       is called "AboutDialog".

    2. Class definition. In `virtualbricks.gui.dialogs` the class `AboutDialog`
        is defined. The `resource` class attribute points to the UI definition
        and the `name` class attribute is not defined because the class name's
        match the main window's name.

    3. In the `__init__` all resources are initialized. It is much better to
        set here all the resource and not in setup.py because is easier to
        switch to another tools in the future. For example `pkgutil` in the
        standard library offer the `get_data()` function.

    4. Use the new code:

        dialogs.AboutDialog().run()

Note. Everytime a new dialog is created, a new gtk.Builder object is created,
this means that more than one dialogs of the same kind can live together. If
this is not desired is responsability of the programmer to do not (modal
dialogs, etc.). This means also that dialogs should be destroied. I'm not
really sure about this because when thare are no more references to the dialog
instance and the gc collect the object, the builder instance is collected too
and is the builder the only one that has an instance to the gtk.Dialog.

So, do not store a reference of the main widget or of the Dialog instance.

    # don't do this
    about = dialogs.AboutDialog()
    about.run()
    about.window # here the window is destroied
    # neither this
    awidget = dialogs.AboutDialog().get_object("awidget")


A note about Glade and the transition to gtk.Builder.

Glade supports gtk.builder but this must be specified in the project
paramentes. It is also possible to select the widget compatibility. The current
version of gtk in debian stable (squeeze) is 2.20, and 2.24 in debian testing
(wheeze) the, in a near future, new debian stable.

Exists a tools that help with the conversion, gtk-builder-convert, but its
results are not always excellent. A window at time conversion is highly
advised and possible with gtk-builder-convert.
"""

import os
import sys
import errno
import tempfile
import functools
import re
import string
import textwrap

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Pango
import twisted
from twisted.internet import utils, defer, task, error
from twisted.python import filepath
if twisted.__version__ >= '15.0.2':
    # This is an ugly hack but virtualbricks is not really ready for
    # Python3
    def mktempfn():
        return filepath._secureEnoughString(project.manager.path)
else:
    def mktempfn():
        return filepath._secureEnoughString()

from virtualbricks import __version__
from virtualbricks import (tools, log, console, settings,
                           virtualmachines, project, errors)
from virtualbricks.virtualmachines import is_virtualmachine
from virtualbricks.tools import dispose
from virtualbricks.gui import graphics, widgets
from virtualbricks._spawn import getQemuOutputAndValue
from virtualbricks.errors import NoOptionError


if False:  # pyflakes
    _ = str

logger = log.Logger()
bug_send = log.Event("Sending report bug")
bug_sent = log.Event("Report bug sent succefully")
bug_error = log.Event("{err}\nstderr:\n{stderr}")
bug_report_fail = log.Event("Report bug failed with code "
                            "{code}\nstderr:\n{stderr}")
bug_err_unknown = log.Event("Error on bug reporting")
lsusb_out = log.Event("lsusb output:\n{out}")
invalid_mac = log.Event("MAC address {mac} is not valid, generating "
                        "a random one")
not_implemented = log.Event("Not implemented")
event_created = log.Event("Event created successfully")
commit_failed = log.Event("Failed to commit image\n{err}")
img_invalid = log.Event("Invalid image")
base_not_found = log.Event("Base not found (invalid cow?)\nstderr:\n{err}")
img_combo = log.Event("Setting image for combobox")
img_create_err = log.Event("Error on creating image")
img_create = log.Event("Creating image...")
img_choose = log.Event("Choose a filename first!")
img_invalid_type = log.Event("Invalid value for format combo, assuming raw")
img_invalid_unit = log.Event("Invalid value for unit combo, assuming Mb")
extract_err = log.Event("Error on import project")
log_rebase = log.Event("Rebasing {cow} to {basefile}")
rebase_error = log.Event("Error on rebase")
image_not_exists = log.Event("Cannot save image to {destination}, file does "
                             "not exists: {source}")
invalid_step_assitant = log.Event("Assistant cannot handle step {num}")
project_extracted = log.Event("Project has beed extracted in {path}")
removing_temporary_project = log.Event("Remove temporary files in {path}")
error_on_import_project = log.Event("An error occurred while import project")
invalid_name = log.Event("Invalid name {name}")
search_usb = log.Event("Searching USB devices")
retr_usb = log.Event("Error while retrieving usb devices.")
brick_invalid_name = log.Event("Cannot create brick: Invalid name.")
created = log.Event("Created successfully")
apply_settings = log.Event("Apply settings...")

NUMERIC = set(map(str, range(10)))
NUMPAD = set(map(lambda i: "KP_%d" % i, range(10)))
EXTRA = set(["BackSpace", "Delete", "Left", "Right", "Home", "End", "Tab"])
VALIDKEY = NUMERIC | NUMPAD | EXTRA

BUG_REPORT_ERRORS = {
    1: "Error in command line syntax.",
    2: "One of the files passed on the command line did not exist.",
    3: "A required tool could not be found.",
    4: "The action failed.",
    5: "No permission to read one of the files passed on the command line."
}

BODY = """-- DO NOT MODIFY THE FOLLOWING LINES --

 affects virtualbrick
"""


def destroy_on_exit(func):
    @functools.wraps(func)
    def on_response(self, dialog, *args):
        try:
            return func(self, dialog, *args)
        finally:
            dialog.destroy()
    return on_response


class Base(object):
    """Base class to work with gtkbuilder files.

    @ivar domain: Translation domain.
    @type domain: C{str} or C{None}

    @ivar resource: A gtkbuilder UI definition resource that a data finder can
            load.
    @type resource: C{str}

    @ivar name: The name of the main widget that must be load.
    @type name: C{str} or C{None}. If C{None} the name of the class is used.
    """

    domain = "virtualbricks"
    resource = None
    name = None

    def __init__(self):
        self.builder = builder = Gtk.Builder()
        builder.set_translation_domain(self.domain)
        builder.add_from_file(graphics.get_data_filename(self.resource))
        self.widget = builder.get_object(self._get_name())
        builder.connect_signals(self)

    def __getattr__(self, name):
        obj = self.builder.get_object(name)
        if obj is None:
            raise AttributeError(name)
        return obj

    def get_object(self, name):
        return self.builder.get_object(name)

    def _get_name(self):
        if self.name:
            return self.name
        return self.__class__.__name__

    def show(self):
        self.widget.show()


class Window(Base):
    """Base class for all dialogs."""

    on_destroy = None

    @property
    def window(self):
        return self.widget

    def set_transient_for(self, parent):
        self.window.set_transient_for(parent)

    def show(self, parent=None):
        if parent is not None:
            self.window.set_transient_for(parent)
        self.window.connect("destroy", self.on_window_destroy)
        if self.on_destroy is not None:
            self.window.connect("destroy", lambda w: self.on_destroy())
        self.window.show()

    def on_window_destroy(self, window):
        dispose(self)

    def __dispose__(self):
        pass


class AboutDialog(Window):

    resource = "about.ui"

    def __init__(self):
        Window.__init__(self)
        self.window.set_version(__version__)
        # to handle show() instead of run()
        self.window.connect("response", lambda d, r: d.destroy())


class LoggingWindow(Window):

    resource = "logging.ui"

    def __init__(self, textbuffer):
        Window.__init__(self)
        self.textbuffer = textbuffer
        self.__bottom = True
        textview = self.get_object("textview")
        textview.set_buffer(textbuffer)
        self.__insert_text_h = textbuffer.connect("changed",
                self.on_textbuffer_changed, textview)
        vadjustment = self.get_object("scrolledwindow1").get_vadjustment()
        vadjustment.connect("value-changed", self.on_vadjustment_value_changed)
        self.scroll_to_end(textview, textbuffer)

    def scroll_to_end(self, textview, textbuffer):
        textview.scroll_to_mark(textbuffer.get_mark("end"), 0, True, 0, 1)

    def on_textbuffer_changed(self, textbuffer, textview):
        if self.__bottom:
            self.scroll_to_end(textview, textbuffer)

    def on_vadjustment_value_changed(self, adj):
        self.__bottom = adj.get_value() + adj.get_page_size() == \
                adj.get_upper()

    def on_LoggingWindow_destroy(self, window):
        self.textbuffer.disconnect(self.__insert_text_h)

    def on_closebutton_clicked(self, button):
        self.window.destroy()

    def on_cleanbutton_clicked(self, button):
        self.textbuffer.set_text("")

    def on_savebutton_clicked(self, button):
        chooser = Gtk.FileChooserDialog(title=_("Save as..."),
                action=Gtk.FileChooserAction.SAVE,
                buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        chooser.set_do_overwrite_confirmation(True)
        chooser.connect("response", self.__on_dialog_response)
        chooser.show()

    def __on_dialog_response(self, dialog, response_id):
        try:
            if response_id == Gtk.ResponseType.OK:
                with open(dialog.get_filename(), "w") as fp:
                    fp.write(self.textbuffer.get_property("text"))
        finally:
            dialog.destroy()

    def on_reportbugbutton_clicked(self, button):
        logger.info(bug_send)
        fd, filename = tempfile.mkstemp()
        os.write(fd, self.textbuffer.get_property("text"))
        #gtk.link_button_set_uri_hook(None) 	(REMOVED in GTK3)
        exit_d = utils.getProcessOutputAndValue("xdg-email",
            ["--utf8", "--body", BODY, "--attach", filename,
             "new@bugs.launchpad.net"],
            dict(os.environ, MM_NOTTTY="1"))

        def success((out, err, code)):
            if code == 0:
                logger.info(bug_sent)
            elif code in BUG_REPORT_ERRORS:
                logger.error(bug_error, err=BUG_REPORT_ERRORS[code],
                             stderr=err, hide_to_user=True)
            else:
                logger.error(bug_report_fail, code=code, stderr=err,
                             hide_to_user=True)

        exit_d.addCallback(success)
        exit_d.addErrback(logger.failure_eb, bug_err_unknown)
        exit_d.addBoth(lambda _: os.close(fd))


class DisksLibraryDialog(Window):

    resource = "disklibrary.ui"
    image = None
    _binding_list = None

    def __init__(self, factory):
        Window.__init__(self)
        self.factory = factory
        self._binding_list = widgets.ImagesBindingList(factory)
        self.lsImages.set_data_source(self._binding_list)
        self.tvcName.set_cell_data_func(self.crt1, self.crt1.set_cell_data)
        self.tvcPath.set_cell_data_func(self.crt2, self.crt2.set_cell_data)
        self.tvcUsed.set_cell_data_func(self.crt3, self._set_used_by, factory)
        self.tvcMaster.set_cell_data_func(self.crt4, self.crt4.set_cell_data)
        self.tvcCows.set_cell_data_func(self.crt5, self._set_cows, factory)
        self.tvcSize.set_cell_data_func(self.crt6, self.crt6.set_cell_data)

    def __dispose__(self):
        if self._binding_list is not None:
            dispose(self._binding_list)
            self._binding_list = None

    @staticmethod
    def _set_used_by(column, cell, model, itr, factory):
        image = model.get_value(itr, 0)
        c = 0
        for vm in filter(is_virtualmachine, factory.bricks):
            for disk in vm.disks():
                if disk.image is image:
                    c += 1
        cell.set_property("text", str(c))

    @staticmethod
    def _set_cows(column, cell, model, itr, factory):
        image = model.get_value(itr, 0)
        c = 0
        for vm in filter(is_virtualmachine, factory.bricks):
            for disk in vm.disks():
                if disk.image is image and disk.cow:
                    c += 1
        cell.set_property("text", str(c))

    def _show_config(self):
        self.pnlList.hide()
        self.pnlConfig.show()

    def _hide_config(self):
        self.pnlConfig.hide()
        self.pnlList.show()

    def on_btnClose_clicked(self, button):
        self.window.destroy()

    def on_tvImages_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        self.image = model.get_value(model.get_iter(path), 0)
        self._show_config()

    def on_btnRevert_clicked(self, button):
        self._hide_config()

    def on_btnRemove_clicked(self, button):
        self.factory.remove_disk_image(self.image)
        self._hide_config()

    def on_btnSave_clicked(self, button):
        self.image.set_name(self.etrName.get_text())
        self.image.set_description(self.etrDescription.get_text())
        self.image = None
        self._hide_config()

    def on_pnlConfig_show(self, panel):
        self.etrName.set_text(self.image.name)
        self.etrPath.set_text(self.image.path)
        self.etrDescription.set_text(self.image.description)


class UsbDevWindow(Window):

    resource = "usbdev.ui"

    def __init__(self, usb_devices):
        Window.__init__(self)
        self.usb_devices = usb_devices
        self.tvDevices.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.crt.set_property("formatter", string.Formatter())
        self.tvcDevs.set_cell_data_func(self.crt, self.crt.set_cell_data)

    @staticmethod
    def parse_lsusb(output):
        for line in output.splitlines():
            info = line.split(" ID ")[1]
            if " " in info:
                code, descr = info.split(" ", 1)
            else:
                code, descr = info, ""
            yield virtualmachines.UsbDevice(code, descr)

    @classmethod
    def show_dialog(cls, gui, usb_devices):

        def init(output):
            output = output.strip()
            logger.info(lsusb_out, out=output)
            dlg = cls(usb_devices)
            dlg.lDevs.set_data_source(cls.parse_lsusb(output))
            dlg.tvDevices.set_selected_values(usb_devices)
            dlg.show(gui.wndMain)

        logger.info(search_usb)
        d = utils.getProcessOutput("lsusb", env=os.environ)
        d.addCallback(init)
        d.addErrback(logger.failure_eb, retr_usb)
        gui.user_wait_action(d)

    def on_btnOk_clicked(self, button):
        self.usb_devices[:] = self.tvDevices.get_selected_values()
        self.window.destroy()


class BaseEthernetDialog(Window):

    resource = "ethernetdialog.ui"
    name = "EthernetDialog"

    def __init__(self, factory, brick):
        Window.__init__(self)
        self.factory = factory
        self.brick = brick

    def is_valid(self, mac):
        return tools.mac_is_valid(mac)

    def setup(self):
        socks = self.get_object("sock_model")
        socks.append(("Host-only ad hoc network",
                      virtualmachines.hostonly_sock))
        if settings.femaleplugs:
            socks.append(("Vde socket", "_sock"))
            for sock in self.factory.socks:
                socks.append((sock.nickname, sock))
        else:
            for sock in self.factory.socks:
                if sock.brick.get_type().startswith("Switch"):
                    socks.append((sock.nickname, sock))

    def on_randomize_button_clicked(self, button):
        self.get_object("mac_entry").set_text(tools.random_mac())

    def on_EthernetDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            combo = self.get_object("sock_combo")
            sock = combo.get_model().get_value(combo.get_active_iter(), 1)
            combo = self.get_object("model_combo")
            model = combo.get_model().get_value(combo.get_active_iter(), 0)
            mac = self.get_object("mac_entry").get_text()
            if not self.is_valid(mac):
                logger.error(invalid_mac, mac=mac)
                mac = tools.random_mac()
            self.do(sock, mac, model)
        dialog.destroy()


class AddEthernetDialog(BaseEthernetDialog):

    def __init__(self, factory, brick, model):
        BaseEthernetDialog.__init__(self, factory, brick)
        self.model = model

    def show(self, parent=None):
        self.setup()
        self.get_object("sock_combo").set_active(0)
        BaseEthernetDialog.show(self, parent)

    def do(self, sock, mac, model):
        if sock == "_sock":
            link = self.brick.add_sock(mac, model)
        else:
            link = self.brick.add_plug(sock, mac, model)
        self.model.append((link, ))


class EditEthernetDialog(BaseEthernetDialog):

    def __init__(self, factory, brick, plug):
        BaseEthernetDialog.__init__(self, factory, brick)
        self.plug = plug

    def show(self, parent=None):
        self.setup()
        self.get_object("title_label").set_label(
            "<b>Edit ethernet interface</b>")
        self.get_object("ok_button").set_property("label", Gtk.STOCK_OK)
        self.get_object("mac_entry").set_text(self.plug.mac)
        model = self.get_object("netmodel_model")
        itr = model.get_iter_first()
        while itr:
            if model.get_value(itr, 0) == self.plug.model:
                self.get_object("model_combo").set_active_iter(itr)
                break
            itr = model.iter_next(itr)

        socks = self.get_object("sock_model")
        if self.plug.mode == "sock" and settings.femaleplugs:
            self.get_object("sock_combo").set_active(1)
        else:
            itr = socks.get_iter_first()
            while itr:
                if self.plug.sock is socks.get_value(itr, 1):
                    self.get_object("sock_combo").set_active_iter(itr)
                    break
                itr = socks.iter_next(itr)
        BaseEthernetDialog.show(self, parent)

    def do(self, sock, mac, model):
        if sock == "_sock":
            logger.error(not_implemented)
        else:
            if self.plug.configured():
                self.plug.disconnect()
            self.plug.connect(sock)
            if mac:
                self.plug.mac = mac
            if model:
                self.plug.model = model


class ConfirmDialog(Window):

    resource = "confirmdialog.ui"

    def __init__(self, question, on_yes=None, on_yes_arg=None, on_no=None,
                 on_no_arg=None, ):
        Window.__init__(self)
        self.window.set_markup(question)
        self.on_yes = on_yes
        self.on_yes_arg = on_yes_arg
        self.on_no = on_no
        self.on_no_arg = on_no_arg

    def format_secondary_text(self, text):
        self.window.format_secondary_text(text)

    def on_ConfirmDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES and self.on_yes:
            self.on_yes(self.on_yes_arg)
        elif response_id == Gtk.ResponseType.NO and self.on_no:
            self.on_no(self.on_no_arg)
        dialog.destroy()


class NewEventDialog(Window):

    resource = "newevent.ui"

    def __init__(self, gui):
        Window.__init__(self)
        self.gui = gui

    def on_delay_entry_key_press_event(self, entry, event):
        if Gdk.keyval_name(event.keyval) not in VALIDKEY:
            return True
        elif Gdk.keyval_name(event.keyval) == "Return":
            self.window.response(Gtk.ResponseType.OK)
            return True

    def on_name_entry_key_press_event(self, entry, event):
        if Gdk.keyval_name(event.keyval) == "Return":
            self.window.response(Gtk.ResponseType.OK)
            return True

    def get_event_type(self):
        for name in "start", "stop", "config", "shell", "collation":
            button = self.get_object(name + "_button")
            if button.get_active():
                return name
        return "shell"  # this condition show not be reached

    def on_NewEventDialog_response(self, dialog, response_id):
        try:
            if response_id == Gtk.ResponseType.OK:
                name = self.get_object("name_entry").get_text()
                delay = self.get_object("delay_entry").get_text()
                type = self.get_event_type()
                event = self.gui.brickfactory.new_event(name)
                event.set({"delay": int(delay)})
                if type in ("start", "stop", "collation"):
                    action = "off" if type == "stop" else "on"
                    bricks = self.gui.brickfactory.bricks
                    dialog_n = BrickSelectionDialog(event, action, bricks)
                elif type == "shell":
                    action = console.VbShellCommand("new switch myswitch")
                    event.set({"actions": [action]})
                    dialog_n = ShellCommandDialog(event)
                else:
                    raise RuntimeError("Invalid event type %s" % type)
                dialog_n.show(self.gui.wndMain)
        finally:
            dialog.destroy()


class BrickSelectionDialog(Window):

    resource = "brickselection.ui"

    def __init__(self, event, action, bricks):
        Window.__init__(self)
        self._event = event
        self._action = action
        self._added = set()
        self.lBricks.set_data_source(bricks)
        self.tmfAvl.set_visible_func(self._is_not_added, self._added)
        self.tmfAdd.set_visible_func(self._is_added, self._added)
        self.crName1.set_property("formatter", string.Formatter())
        self.crName2.set_property("formatter", string.Formatter())
        widgets.set_cells_data_func(self.tvcAvailables)
        widgets.set_cells_data_func(self.tvcAdded)
        self.tmfAvl.refilter()
        self.tmfAdd.refilter()

    @staticmethod
    def _is_not_added(model, itr, added):
        brick = model.get_value(itr, 0)
        return brick and brick not in added

    @staticmethod
    def _is_added(model, itr, added):
        brick = model.get_value(itr, 0)
        return brick and brick in added

    def on_add(self, *_):
        for brick in self.tvAvailables.get_selected_values():
            self._added.add(brick)
        self.tvAvailables.get_model().refilter()
        self.tvAdded.get_model().refilter()
        return True

    def on_remove(self, *_):
        for brick in self.tvAdded.get_selected_values():
            self._added.remove(brick)
        self.tvAvailables.get_model().refilter()
        self.tvAdded.get_model().refilter()
        return True

    @destroy_on_exit
    def on_BrickSelectionDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            act = self._action
            actions = ("{0} {1}".format(b.name, act) for b in self._added)
            self._event.set({"actions": map(console.VbShellCommand, actions)})
            logger.info(event_created)


class EventControllerMixin(object):

    resource = "eventconfig.ui"

    def setup_controller(self, event):
        self.get_object("action_treeview").get_selection().set_mode(
            Gtk.SelectionMode.MULTIPLE)
        self.get_object("sh_cellrenderer").set_activatable(True)
        self.get_object("action_cellrenderer").set_property("editable", True)
        model = self.get_object("actions_liststore")
        for action in event.config["actions"]:
            model.append((action, isinstance(action, console.ShellCommand)))
        model.append(("", False))

    def on_action_cellrenderer_edited(self, cell_renderer, path, new_text):
        model = self.get_object("actions_liststore")
        iter = model.get_iter(path)
        if new_text:
            model.set_value(iter, 0, new_text)
            if model.iter_next(iter) is None:
                model.append(("", False))
        elif model.iter_next(iter) is not None:
            model.remove(iter)
        else:
            model.set_value(iter, 0, new_text)

    def on_sh_cellrenderer_toggled(self, cell_renderer, path):
        model = self.get_object("actions_liststore")
        model.set_value(model.get_iter(path), 1,
                        not cell_renderer.get_active())

    def configure_event(self, event, attrs):
        model = self.get_object("actions_liststore")
        f = (console.VbShellCommand, console.ShellCommand)
        attrs["actions"] = [f[row[1]](row[0]) for row in model if row[0]]
        event.set(attrs)


class ShellCommandDialog(Window, EventControllerMixin):

    resource = "eventcommand.ui"

    def __init__(self, event):
        Window.__init__(self)
        self.event = event
        self.setup_controller(event)

    def on_ShellCommandDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            self.configure_event(self.event, {})
        dialog.destroy()


def disks_of(brick):
    if brick.get_type() == "Qemu":
        for dev in "hda", "hdb", "hdc", "hdd", "fda", "fdb", "mtdblock":
            yield brick.config[dev]


class CommitImageDialog(Window):

    resource = "commitdialog.ui"
    parent = None
    _set_label_d = None

    def __init__(self, progessbar, factory):
        Window.__init__(self)
        self.progessbar = progessbar
        model = self.get_object("model1")
        for brick in factory.bricks:
            for disk in (disk for disk in disks_of(brick) if disk.cow):
                model.append((disk.device + " on " + brick.name, disk))

    def show(self, parent=None):
        self.parent = parent
        Window.show(self, parent)

    def _do_image_commit(self, path):

        def log_err((out, err, exit_status)):
            if exit_status != 0:
                logger.error(commit_failed, err=err)

        d = getQemuOutputAndValue("qemu-img", ["commit", path], os.environ)
        d.addCallback(log_err)
        return d

    def do_image_commit(self, path):
        self.window.destroy()
        self.progessbar.wait_for(self._do_image_commit, path)

    def commit_file(self, pathname):
        question = ("Warning: the base image will be updated to the\n"
                    "changes contained in the COW. This operation\n"
                    "cannot be undone. Are you sure?")
        ConfirmDialog(question, on_yes=self.do_image_commit,
                      on_yes_arg=pathname).show(self.parent)

    def _commit_vm(self, img):
        logger.warning(not_implemented)
        # img.VM.commit_disks()
        self.window.destroy()

    def commit_vm(self):
        combobox = self.get_object("disk_combo")
        model = combobox.get_model()
        itr = combobox.get_active_iter()
        if itr:
            img = model[itr][1]
            if not self.get_object("cow_checkbutton").get_active():
                question = ("Warning: the private COW image will be "
                            "updated.\nThis operation cannot be undone.\n"
                            "Are you sure?")
                ConfirmDialog(question, on_yes=self._commit_vm,
                              on_yes_arg=img).show(self.parent)
            else:
                pathname = os.path.join(img.basefolder,
                        "{0.vm_name}_{0.device}.cow".format(img))
                self.commit_file(pathname)
        else:
            logger.error(img_invalid)

    def on_CommitImageDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            if self.get_object("file_radiobutton").get_active():
                pathname = self.get_object(
                    "cowpath_filechooser").get_filename()
                self.commit_file(pathname)
            else:
                self.commit_vm()
        else:
            dialog.destroy()

    def on_file_radiobutton_toggled(self, button):
        active = button.get_active()
        filechooser = self.get_object("cowpath_filechooser")
        filechooser.set_visible(active)
        filechooser.unselect_all()
        combo = self.get_object("disk_combo")
        combo.set_visible(not active)
        combo.set_active(-1)
        self.get_object("cow_checkbutton").set_visible(not active)
        self.get_object("msg_label").set_visible(False)

    def _commit_image_show_result(self, (out, err, code)):
        if code != 0:
            logger.error(base_not_found, err=err)
        else:
            label = self.get_object("msg_label")
            for line in out.splitlines():
                if line.startswith("backing file: "):
                    label.set_text(line)
                    break
            else:
                label.set_text(_("Base not found (invalid cow?)"))
            label.set_visible(True)

    def on_cowpath_filechooser_file_set(self, filechooser):
        if self._set_label_d is not None:
            self._set_label_d.cancel()
        filename = filechooser.get_filename()
        if os.access(filename, os.R_OK):
            code = getQemuOutputAndValue("qemu-img", ["info", filename],
                                         os.environ)
            code.addCallback(self._commit_image_show_result)
            self._set_label_d = code
            return code

    def set_label(self, combobox=None, button=None):
        if self._set_label_d is not None:
            self._set_label_d.cancel()
        if combobox is None:
            combobox = self.get_object("disk_combo")
        if button is None:
            button = self.get_object("cow_checkbutton")
        label = self.get_object("msg_label")
        label.set_visible(False)
        model = combobox.get_model()
        itr = combobox.get_active_iter()
        if itr is not None:
            disk = model[itr][1]
            base = disk.image and disk.image.path or None
            if base and button.get_active():
                # XXX: make disk.get_real_disk_name's deferred cancellable
                deferred = disk.get_real_disk_name()
                deferred.addCallback(label.set_text)
                deferred.addCallback(lambda _: label.set_visible(True))
                deferred.addErrback(logger.failure_eb, img_combo)
                self._set_label_d = deferred
            elif base:
                label.set_visible(True)
                label.set_text(base)
            else:
                label.set_visible(True)
                label.set_text("base not found")
        else:
            label.set_visible(True)
            label.set_text("base not found")

    def on_disk_combo_changed(self, combobox):
        self.set_label(combobox=combobox)

    def on_cow_checkbutton_toggled(self, button):
        self.set_label(button=button)


def choose_new_image(gui, factory):
    main = gui.wndMain
    dialog = Gtk.FileChooserDialog(_("Open a disk image"), main,
        Gtk.FileChooserAction.OPEN,
        (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
         Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
    if dialog.run() == Gtk.ResponseType.OK:
        pathname = dialog.get_filename()
        LoadImageDialog(factory, pathname).show(main)
    dialog.destroy()


class LoadImageDialog(Window):

    resource = "loadimagedialog.ui"

    def __init__(self, factory, pathname):
        Window.__init__(self)
        self.pathname = pathname
        self.factory = factory

    def show(self, parent=None):
        name = os.path.basename(self.pathname)
        self.get_object("name_entry").set_text(name)
        buf = self.get_object("description_textview").get_buffer()
        buf.set_text(self.load_desc())
        Window.show(self, parent)

    def load_desc(self):
        try:
            with open(self.pathname + ".vbdescr") as fd:
                return fd.read()
        except IOError:
            return ""

    def on_LoadImageDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            name = self.get_object("name_entry").get_text()
            buf = self.get_object("description_textview").get_buffer()
            desc = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), include_hidden_chars=True)
            try:
                self.factory.new_disk_image(name, self.pathname, desc)
            except:
                dialog.destroy()
                raise
        dialog.destroy()


class CreateImageDialog(Window):

    resource = "createimagedialog.ui"

    def __init__(self, gui, factory):
        self.gui = gui
        self.factory = factory
        Window.__init__(self)

    def create_image(self, name, pathname, fmt, size, unit):

        def _create_disk(result):
            out, err, code = result
            if code:
                logger.error(err)
            else:
                return self.factory.new_disk_image(name, pathname)

        exit = getQemuOutputAndValue("qemu-img",
            ["create", "-f", fmt, pathname, size + unit], os.environ)
        exit.addCallback(_create_disk)
        logger.log_failure(exit, img_create_err)
        return exit

    def on_CreateImageDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            logger.info(img_create)
            name = self.get_object("name_entry").get_text()
            if not name:
                logger.error(img_choose)
                return
            folder = self.get_object("folder_filechooserbutton").get_filename()
            fmt_cmb = self.get_object("format_combobox")
            itr = fmt_cmb.get_active_iter()
            if itr:
                fmt = fmt_cmb.get_model()[itr][0]
                if fmt == "Auto":
                    fmt = "raw"
            else:
                logger.info(img_invalid_type)
                fmt = "raw"
            size = str(self.get_object("size_spinbutton").get_value_as_int())
            # Get size unit and remove the last character "B"
            # because qemu-img want k, M, G or T suffixes.
            unit_cmb = self.get_object("unit_combobox")
            itr = unit_cmb.get_active_iter()
            if itr:
                unit = unit_cmb.get_model()[itr][0][0]
            else:
                logger.info(img_invalid_unit)
                unit = "M"
            pathname = "%s/%s.%s" % (folder, name, fmt)
            self.gui.user_wait_action(self.create_image(name, pathname, fmt,
                                                        size, unit))
        dialog.destroy()


class SimpleEntryDialog(Window):

    resource = "simpleentry.ui"
    name = "SimpleEntryDialog"
    description = ""

    def __init__(self, gui):
        Window.__init__(self)
        self.gui = gui
        self.get_object("label1").set_text(self.description)

    @destroy_on_exit
    def on_SimpleEntryDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            self.do_action(self.get_object("name_entry").get_text())


class NewProjectDialog(SimpleEntryDialog):

    @property
    def description(self):
        return _("Project name")

    def do_action(self, name):
        self.gui.on_new(name)


class ListProjectsDialog(Window):

    resource = "listprojects.ui"
    name = "ListProjectsDialog"
    title = ""

    def show(self, parent=None):
        self.populate(self.get_projects())
        if self.title:
            self.window.set_title(self.title)
        Window.show(self, parent)

    def get_projects(self):
        return (prj.name for prj in project.manager)

    def populate(self, projects):
        model = self.get_object("liststore1")
        for prj in projects:
            model.append((prj, ))

    def get_project_name(self):
        treeview = self.get_object("treeview")
        model, itr = treeview.get_selection().get_selected()
        if itr:
            return model.get_value(itr, 0)

    def on_treeview_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        itr = model.get_iter(path)
        if itr:
            name = model.get_value(itr, 0)
            self.do_action(self.window, Gtk.ResponseType.OK, name)
        return True

    def on_ListProjectsDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            name = self.get_project_name()
            if name is not None:
                self.do_action(dialog, response_id, name)
        else:
            dialog.destroy()
        return True

    def do_action(self, dialog, response_id, name):
        pass


class _ListProjectAbstract(ListProjectsDialog):

    def __init__(self, gui):
        self.gui = gui
        Window.__init__(self)

    def get_projects(self):
        curr = project.manager.current
        return (prj.name for prj in project.manager if prj != curr)


class OpenProjectDialog(_ListProjectAbstract):

    @property
    def title(self):
        return _("Virtualbricks - Open project")

    @destroy_on_exit
    def do_action(self, dialog, response_id, name):
        self.gui.on_open(name)


class DeleteProjectDialog(_ListProjectAbstract):

    @property
    def title(self):
        return _("Virtualbricks - Delete project")

    @destroy_on_exit
    def do_action(self, dialog, response_id, name):
        project.manager.get_project(name).delete()


class RenameProjectDialog(SimpleEntryDialog):

    @property
    def description(self):
        return _("New project name")

    def do_action(self, name):
        project.manager.current.rename(name)


def has_cow(disk):
    return disk.image and disk.cow


def cowname(brick, disk):
    return os.path.join(project.manager.current.path,
                        "{0.name}_{1.device}.cow".format(brick, disk))


def gather_selected(model, parent, workspace, lst):
    itr = model.iter_children(parent)
    while itr:
        fp = model[itr][FILEPATH]
        if model[itr][SELECTED] and fp.isfile():
            lst.append(os.path.join(*fp.segmentsFrom(workspace)))
        else:
            gather_selected(model, itr, workspace, lst)
        itr = model.iter_next(itr)


class ImportCanceled(Exception):
    pass


SELECTED, ACTIVABLE, TYPE, NAME, FILEPATH = range(5)


def ConfirmOverwriteDialog(fp, parent):
    question = _("A file named \"{0}\" already exists.  Do you want to "
                 "replace it?").format(fp.basename())
# gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT
# not existing in GTK3, documentation suggests to put 0
    dialog = Gtk.MessageDialog(parent, 0, 	
                               Gtk.MessageType.QUESTION,
                               message_format=question)
    dialog.format_secondary_text(_("The file already exists in \"{0}\". "
                                   "Replacing it will overwrite its "
                                   "contents.").format(fp.dirname()))
    dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
    button = Gtk.Button(_("_Replace"))
    button.set_can_default(True)
    button.set_image(Gtk.Image.new_from_stock(Gtk.STOCK_SAVE_AS,
                                              Gtk.IconSize.BUTTON))
    button.show()
    dialog.add_action_widget(button, Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)
    return dialog


class ExportProjectDialog(Window):

    resource = "exportproject.ui"
    include_images = False

    def __init__(self, progressbar, prjpath, disk_images):
        super(Window, self).__init__()
        self.progressbar = progressbar
        if isinstance(prjpath, basestring):
            prjpath = filepath.FilePath(prjpath)
        self.prjpath = prjpath
        self.image_files = [(image.name, filepath.FilePath(image.path))
                            for image in disk_images]
        # self.image_files = set(filepath.FilePath(image.path) for image in
        #                         disk_images)
        self.required_files = set([prjpath.child(".project"),
                                   prjpath.child("README")])
        self.internal_files = set([prjpath.child("vde.dot"),
                                   prjpath.child("vde_topology.plain"),
                                   prjpath.child(".images")])

    def append_dirs(self, dirpath, dirnames, model, parent, nodes):
        for dirname in sorted(dirnames):
            child = dirpath.child(dirname)
            if child in self.required_files | self.internal_files:
                dirnames.remove(dirname)
            else:
                row = (True, True, Gtk.STOCK_DIRECTORY, dirname, child)
                nodes[child.path] = model.append(parent, row)

    def append_files(self, dirpath, filenames, model, parent):
        for filename in sorted(filenames):
            child = dirpath.child(filename)
            if (child not in self.required_files | self.internal_files and
                    child.isfile() and not child.islink()):
                row = (True, True, Gtk.STOCK_FILE, filename, child)
                model.append(parent, row)

    def build_path_tree(self, model, prjpath):
        row = (True, True, Gtk.STOCK_DIRECTORY, prjpath.basename(), prjpath)
        root = model.append(None, row)
        nodes = {prjpath.path: root}
        for dirpath, dirnames, filenames in os.walk(prjpath.path):
            parent = nodes[dirpath]
            dp = filepath.FilePath(dirpath)
            self.append_dirs(dp, dirnames, model, parent, nodes)
            self.append_files(dp, filenames, model, parent)

    def show(self, parent_w=None):
        model = self.get_object("treestore1")
        self.build_path_tree(model, self.prjpath)
        pixbuf_cr = self.get_object("icon_cellrenderer")
        pixbuf_cr.set_property("stock-size", Gtk.IconSize.MENU)
        size_c = self.get_object("treeviewcolumn2")
        size_cr = self.get_object("size_cellrenderer")
        size_c.set_cell_data_func(size_cr, self._set_size)
        self.get_object("selected_cellrenderer").connect(
            "toggled", self.on_selected_cellrenderer_toggled, model)
        self.get_object("treeview1").expand_row(0, False)
        Window.show(self, parent_w)

    def _set_size(self, column, cellrenderer, model, itr):
        fp = model.get_value(itr, FILEPATH)
        if fp.isfile():
            cellrenderer.set_property("text", tools.fmtsize(fp.getsize()))
        else:
            size = self._calc_size(model, itr)
            if model.get_path(itr) == (0,):
                size += sum(fp.getsize() for fp in self.required_files if
                            fp.exists())
                if self.include_images:
                    size += sum(fp.getsize() for n, fp in self.image_files)
            cellrenderer.set_property("text", tools.fmtsize(size))

    def _calc_size(self, model, parent):
        size = 0
        fp = model[parent][FILEPATH]
        if fp.isdir():
            itr = model.iter_children(parent)
            while itr:
                size += self._calc_size(model, itr)
                itr = model.iter_next(itr)
        elif model[parent][SELECTED]:
            size += fp.getsize()
        return size

    def _normalize_filename(self, filename):
        if filename[-4:] != ".vbp":
            return filename + ".vbp"
        return filename

    def on_selected_cellrenderer_toggled(self, cellrenderer, path, model):
        itr = model.get_iter(path)
        model[itr][SELECTED] = not model[itr][SELECTED]
        self._select_children(model, itr, model[itr][SELECTED])
        parent = model.iter_parent(itr)
        while parent:
            child = model.iter_children(parent)
            while child:
                if not model[child][SELECTED]:
                    model[parent][SELECTED] = False
                    break
                child = model.iter_next(child)
            else:
                model[parent][SELECTED] = True
            parent = model.iter_parent(parent)

    def _select_children(self, model, parent, selected):
        itr = model.iter_children(parent)
        while itr:
            self._select_children(model, itr, selected)
            model[itr][SELECTED] = selected
            itr = model.iter_next(itr)

    @destroy_on_exit
    def on_filechooser_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            if filename is None:
                self.get_object("export_button").set_sensitive(False)
            elif os.path.exists(filename) and not os.path.isfile(filename):
                dialog.unselect_all()
                self.get_object("export_button").set_sensitive(False)
            else:
                filename = self._normalize_filename(filename)
                txt = filename.decode(sys.getfilesystemencoding()).encode(
                    "utf8")
                self.get_object("filename_entry").set_text(txt)
                self.get_object("export_button").set_sensitive(True)

    def on_open_button_clicked(self, button):
        chooser = Gtk.FileChooserDialog(title=_("Export project"),
                action=Gtk.FileChooserAction.SAVE,
                buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                         Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
        vbp = Gtk.FileFilter()
        vbp.add_pattern("*.vbp")
        chooser.set_filter(vbp)
        chooser.connect("response", self.on_filechooser_response)
        chooser.set_transient_for(self.window)
        chooser.set_current_name(self.get_object("filename_entry").get_text())
        chooser.show()

    def on_filename_entry_changed(self, entry):
        self.get_object("export_button").set_sensitive(bool(entry.get_text()))

    def on_include_images_checkbutton_toggled(self, checkbutton):
        self.include_images = checkbutton.get_active()
        model = self.get_object("treestore1")
        model.row_changed((0,), model.get_iter((0,)))

    def export(self, model, ancestor, filename, export=project.manager.export):
        files = []
        gather_selected(model, model.get_iter_first(), ancestor, files)
        for fp in self.required_files:
            if fp.exists():
                files.append(os.path.join(*fp.segmentsFrom(ancestor)))
        images = []
        if self.include_images:
            images = [(name, fp.path) for name, fp in self.image_files]
        return export(filename, files, images)

    @destroy_on_exit
    def on_confirm_response(self, dialog, response_id, parent, filename):
        if response_id == Gtk.ResponseType.ACCEPT:
            parent.destroy()
            self.do_export(filename)

    def do_export(self, filename):
        model = self.get_object("treestore1")
        ancestor = filepath.FilePath(settings.VIRTUALBRICKS_HOME)
        self.progressbar.wait_for(self.export(model, ancestor, filename))

    def on_ExportProjectDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            filename = self._normalize_filename(self.get_object(
                "filename_entry").get_text())
            fp = filepath.FilePath(filename)
            if fp.exists():
                cdialog = ConfirmOverwriteDialog(fp, dialog)
                cdialog.connect("response", self.on_confirm_response, dialog,
                                fp.path)
                cdialog.show()
            else:
                dialog.destroy()
                self.do_export(fp.path)
        else:
            dialog.destroy()


def retrieve_data(widget, data):
    lst, name = data
    attr = widget.get_data(name)
    if attr is not None:
        lst.append((attr, widget))


def accumulate_data(container, name):
    lst = []
    container.foreach(retrieve_data, (lst, name))
    return lst


def pass_through(function, *args, **kwds):
    def wrapper(arg):
        function(*args, **kwds)
        return arg
    return wrapper


def iter_model(model, *columns):
    itr = model.get_iter_root()
    if not columns:
        columns = range(model.get_n_columns())
    while itr:
        yield model.get(itr, *columns)
        itr = model.iter_next(itr)


def complain_on_error(result):
    out, err, code = result
    if code != 0:
        logger.warn(err)
        raise error.ProcessTerminated(code)
    logger.info(err)
    return result


def _set_path(column, cell_renderer, model, iter, colid):
    path = model.get_value(iter, colid)
    cell_renderer.set_property("text",  path.path if path else "")


def _set_path_remap(column, cell_renderer, model, iter, colid):
    path = model.get_value(iter, colid)
    if path:
        cell_renderer.set_properties(font_desc=None, foreground=None,
                                     text=path.path)
    else:
        font = Pango.FontDescription()
        font.set_style(Pango.Style.ITALIC)
        cell_renderer.set_properties(font_desc=font, foreground="gray",
                                     text="(Click here to select an image)")


class Freezer:

    def __init__(self, freeze, unfreeze, parent):
        self.freeze = freeze
        self.unfreeze = unfreeze
        builder = Gtk.Builder()
        res = graphics.get_data_filename("userwait.ui")
        builder.add_from_file(res)
        self.progressbar = builder.get_object("progressbar")
        self.window = builder.get_object("UserWaitWindow")
        self.window.set_transient_for(parent)
        self.window.set_modal(True)

    def wait_for(self, something, *args):
        if isinstance(something, defer.Deferred):
            return self.wait_for_deferred(something)
        elif hasattr(something, "__call__"):
            return self.wait_for_action(something, *args)
        raise RuntimeError("Invalid argument")

    def wait_for_action(self, action, *args):
        done = defer.maybeDeferred(action, *args)
        return self.wait_for_deferred(done)

    def wait_for_deferred(self, deferred):
        deferred.addBoth(self.stop, self.start())
        return deferred

    def start(self):
        self.freeze()
        self.window.show_all()
        lc = task.LoopingCall(self.progressbar.pulse)
        lc.start(0.2, False)
        return lc

    def stop(self, passthru, lc):
        self.window.destroy()
        self.unfreeze()
        lc.stop()
        return passthru


class ProgressBar:

    def __init__(self, dialog):
        self.freezer = Freezer(lambda: None, lambda: None, dialog)

    def wait_for(self, something, *args):
        return self.freezer.wait_for(something, *args)


def all_paths_set(model):
    return all(path for (path,) in iter_model(model, 1))


class _HumbleImport:

    def step_1(self, dialog, model, path, extract=project.manager.import_prj):
        archive_path = dialog.get_archive_path()
        if archive_path != dialog.archive_path:
            if dialog.project:
                dialog.project.delete()
            dialog.archive_path = archive_path
            d = extract(mktempfn(), archive_path)
            d.addCallback(self.extract_cb, dialog)
            d.addCallback(self.fill_model_cb, dialog, model, path)
            d.addErrback(self.extract_eb, dialog)
            return d

    def extract_cb(self, project, dialog):
        logger.debug(project_extracted, path=project.path)
        dialog.project = project
        dialog.images = dict((name, section["path"]) for (_, name), section in
                              project.get_descriptor().get_images())
        return project

    def extract_eb(self, fail, dialog):
        logger.failure(extract_err, fail)
        dialog.destroy()
        return fail

    def fill_model_cb(self, project, dialog, model, vipath):
        model.clear()
        for name in project.images():
            if name in dialog.images:
                fp = vipath.child(os.path.basename(dialog.images[name]))
            else:
                fp = vipath.child(name)
            fp2 = filepath.FilePath(fp.path)
            c = 1
            while fp2.exists():
                fp2 = fp.siblingExtension(".{0}".format(c))
                c += 1
            model.append((name, fp2, True))
        return project

    def step_2(self, dialog, store1, store2):
        """Step 2: map images."""

        imgs = dict((name, path) for name, path, save in
                    iter_model(store1) if save)
        store2.clear()
        for name in dialog.images:
            store2.append((name, imgs.get(name)))
        if len(store2) == 0 or all_paths_set(store2):
            dialog.set_page_complete()

    def step_3(self, dialog):
        w = dialog.get_object
        w("projectname_label").set_text(dialog.get_project_name())
        path_label = w("projectpath_label")
        fp = filepath.FilePath(dialog.project.path)
        path = fp.sibling(dialog.get_project_name()).path
        path_label.set_text(path)
        path_label.set_tooltip_text(path)
        w("open_label").set_text(str(dialog.get_open()))
        w("overwrite_label").set_text(str(dialog.get_overwrite()))
        iimgs = (name for name, s in iter_model(w("liststore1"), 0, 2) if s)
        w("imported_label").set_text("\n".join(iimgs))
        store = w("liststore2")
        vbox = w("vbox1")
        vbox.foreach(vbox.remove)
        for i, (name, dest) in enumerate(iter_model(store)):
            nlabel = Gtk.Label(name + ":")
            nlabel.set_alignment(0.0, 0.5)
            dlabel = Gtk.Label(dest.path)
            dlabel.set_tooltip_text(dest.path)
            dlabel.set_alignment(0.0, 0.5)
            dlabel.set_ellipsize(pango.ELLIPSIZE_MIDDLE)
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            box.pack_start(nlabel, False, True, 0)
            box.pack_start(dlabel, True, True, 0)
            vbox.pack_start(box, False, True, 3)
            box.show_all()

    def apply(self, project, name, factory, overwrite, open, store1, store2):
        entry = project.get_descriptor()
        imgs = self.get_images(project, entry, store1, store2)
        deferred = self.rebase_all(project, imgs, entry)
        deferred.addCallback(self.check_rebase)
        deferred.addCallback(lambda a: project.rename(name, overwrite))
        if open:
            deferred.addCallback(pass_through(project.open, factory))
        deferred.addErrback(pass_through(project.delete))
        logger.log_failure(deferred, error_on_import_project)
        return deferred

    def get_images(self, project, entry, store1, store2):
        imagesfp = filepath.FilePath(project.path).child(".images")
        imgs = self.save_images(store1, imagesfp)
        self.remap_images(entry, store2, imgs)
        entry.save(project)
        return imgs

    def save_images(self, model, source):
        saved = {}
        for name, destination, save in iter_model(model):
            if save:
                fp = source.child(name)
                try:
                    fp.moveTo(destination)
                except OSError as e:
                    if e.errno == errno.ENOENT:
                        logger.error(image_not_exists, source=fp.path,
                                     destination=destination.path)
                        continue
                    else:
                        raise
                else:
                    saved[name] = destination
        return saved

    def remap_images(self, entry, store, saved):
        for name, destination in saved.iteritems():
            entry.remap_image(name, destination.path)
        for name, path in iter_model(store):
            entry.remap_image(name, path.path)
            saved[name] = path

    def rebase_all(self, project, images, entry):
        lst = []
        for name, path in images.iteritems():
            for vmname, dev in entry.device_for_image(name):
                cow_name = "{0}_{1}.cow".format(vmname, dev)
                cow = filepath.FilePath(project.path).child(cow_name)
                if cow.exists():
                    logger.debug(log_rebase, cow=cow.path, basefile=path.path)
                    lst.append(self.rebase(path.path, cow.path))
        return defer.DeferredList(lst)

    def rebase(self, backing_file, cow, run=utils.getProcessOutputAndValue):
        args = ["rebase", "-u", "-b", backing_file, cow]
        d = run("qemu-img", args, os.environ)
        return d.addCallback(complain_on_error)

    def check_rebase(self, result):
        for success, status in result:
            if not success:
                logger.error(rebase_error, log_failure=status)


class ImportDialog(Window):

    resource = "importdialog.ui"
    NAME, PATH, SELECTED = range(3)
    archive_path = None
    project = None
    images = None
    humble = _HumbleImport()

    def __init__(self, factory):
        Window.__init__(self)
        self.factory = factory

    @property
    def assistant(self):
        return self.builder.get_object("ImportDialog")

    def show(self, parent=None):
        col1 = self.get_object("pathcolumn1")
        cell1 = self.get_object("cellrenderertext2")
        col1.set_cell_data_func(cell1, _set_path, 1)
        col2 = self.get_object("pathcolumn2")
        cell2 = self.get_object("cellrenderertext4")
        col2.set_cell_data_func(cell2, _set_path_remap, 1)
        view1 = self.get_object("treeview1")
        view1.connect("button_press_event", self.on_button_press_event, col1,
                      self.get_save_filechooserdialog)
        view2 = self.get_object("treeview2")
        view2.connect("button_press_event", self.on_button_press_event, col2,
                      self.get_map_filechooserdialog)
        Window.show(self, parent)

    def destroy(self):
        self.assistant.destroy()

    # assistant method helpers

    def set_page_complete(self, page=None, complete=True):
        if page is None:
            page = self.assistant.get_nth_page(
                self.assistant.get_current_page())
        self.assistant.set_page_complete(page, complete)

    ####

    def get_project_name(self):
        return self.get_object("prjname_entry").get_text()

    def set_project_name(self, name):
        self.get_object("prjname_entry").set_text(name)

    def get_archive_path(self):
        return self.get_object("filechooserbutton").get_filename()

    def get_open(self):
        return self.get_object("opencheckbutton").get_active()

    def get_overwrite(self):
        return self.get_object("overwritecheckbutton").get_active()

    def get_filechooserdialog(self, model, path, title, action, stock_id):
        chooser = Gtk.FileChooserDialog(title, self.window, action,
                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                 stock_id, Gtk.ResponseType.OK))
        chooser.set_modal(True)
        chooser.set_select_multiple(False)
        chooser.set_transient_for(self.window)
        chooser.set_destroy_with_parent(True)
        chooser.set_position(Gtk.WindowPosition.CENTER)
        chooser.set_do_overwrite_confirmation(True)
        chooser.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        chooser.connect("response", self.on_filechooserdialog_response, model,
                        path)
        return chooser

    def get_save_filechooserdialog(self, model, path):
        return self.get_filechooserdialog(model, path, _("Save image as..."),
                                           Gtk.FileChooserAction.SAVE,
                                           Gtk.STOCK_SAVE)

    def get_map_filechooserdialog(self, model, path):
        return self.get_filechooserdialog(model, path, _("Map image as..."),
                                           Gtk.FileChooserAction.OPEN,
                                           Gtk.STOCK_OPEN)

    # callbacks

    def on_liststore2_row_changed(self, model, path, iter):
        self.set_page_complete(complete=all_paths_set(model))

    def on_ImportDialog_prepare(self, assistant, page):
        page_num = assistant.get_current_page()
        if page_num == 0:
            pass
        elif page_num == 1:
            ws = settings.get("workspace")
            deferred = self.humble.step_1(self, self.get_object("liststore1"),
                    filepath.FilePath(ws).child("vimages"))
            if deferred:
                ProgressBar(self.assistant).wait_for(deferred)
        elif page_num == 2:
            self.humble.step_2(self, self.get_object("liststore1"),
                               self.get_object("liststore2"))
        elif page_num == 3:
            self.humble.step_3(self)
        else:
            logger.error(invalid_step_assitant, num=page_num)
        return True

    def on_ImportDialog_cancel(self, assistant):
        if self.project:
            logger.info(removing_temporary_project, path=self.project.path)
            self.project.delete()
        assistant.destroy()
        return True

    def on_ImportDialog_apply(self, assistant):
        deferred = self.humble.apply(self.project, self.get_project_name(),
                                     self.factory, self.get_overwrite(),
                                     self.get_open(),
                                     self.get_object("liststore1"),
                                     self.get_object("liststore2"))
        ProgressBar(assistant).wait_for(deferred)
        return True

    def on_ImportDialog_close(self, assistant):
        assistant.destroy()
        return True

    def on_filechooserbutton_file_set(self, filechooser):
        filename = filechooser.get_filename()
        name = os.path.splitext(os.path.basename(filename))[0]
        if not self.get_project_name():
            self.set_project_name(name)
        return True

    def on_prjname_entry_changed(self, entry):
        self.set_import_sensitive(self.get_archive_path(), entry.get_text(),
                                  self.get_object("overwritecheckbutton"))
        return True

    def on_overwritecheckbutton_toggled(self, checkbutton):
        self.set_import_sensitive(self.get_archive_path(),
                                  self.get_object("prjname_entry").get_text(),
                                  checkbutton)
        return True

    def set_import_sensitive(self, filename, name, overwrite_btn):
        page = self.get_object("intro_page")
        label = self.get_object("warn_label")
        if name in list(prj.name for prj in project.manager):
            overwrite_btn.set_visible(True)
            overwrite = overwrite_btn.get_active()
            label.set_visible(not overwrite)
            self.set_page_complete(page, overwrite)
        else:
            overwrite_btn.set_active(False)
            overwrite_btn.set_visible(False)
            label.set_visible(False)
            if filename and name:
                self.set_page_complete(page, True)
            else:
                self.set_page_complete(page, False)

    def on_cellrenderertoggle1_toggled(self, renderer, path):
        model = self.get_object("liststore1")
        active = renderer.get_active()
        model.set(model.get_iter(path), self.SELECTED, not active)
        return True

    def on_button_press_event(self, treeview, event, column, dialog_factory):
        if event.button == 1:
            x = int(event.x)
            y = int(event.y)
            pthinfo = treeview.get_path_at_pos(x, y)
            if pthinfo is not None and pthinfo[1] is column:
                path, col = pthinfo[:2]
                treeview.grab_focus()
                treeview.set_cursor(path, col, 0)
                model = treeview.get_model()
                chooser = dialog_factory(model, path)
                itr = model.get_iter(path)
                filename = model.get_value(itr, self.PATH)
                if filename is not None:
                    if not chooser.set_filename(filename.path):
                        chooser.set_current_name(filename.basename())
                chooser.show()
                return True

    def on_filechooserdialog_response(self, dialog, response_id, model, path):
        if response_id == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            if filename is not None:
                model.set_value(model.get_iter(path), self.PATH,
                                filepath.FilePath(filename))
        dialog.destroy()
        return True


class SaveAsDialog(Window):

    resource = "saveas.ui"
    home = filepath.FilePath(settings.DEFAULT_HOME)

    def __init__(self, factory, projects):
        Window.__init__(self)
        self.factory = factory
        self.model = model = self.get_object("liststore1")
        for prj in projects:
            model.append((prj, ))

    def get_project_name(self):
        return self.get_object("name_entry").get_text()

    def set_invalid(self, invalid):
        self.get_object("ok_button").set_sensitive(not invalid)

    def on_name_entry_changed(self, entry):
        name = entry.get_text()
        try:
            self.home.child(name)
        except filepath.InsecurePath:
            self.set_invalid(True)
        else:
            model = self.model
            itr = model.get_iter_first()
            while itr:
                if model.get_value(itr, 0) == name:
                    self.set_invalid(True)
                    break
                itr = model.iter_next(itr)
            else:
                self.set_invalid(False)

    @destroy_on_exit
    def on_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            project.manager.current.save_as(self.get_project_name(),
                                            self.factory)


class RenameDialog(Window):

    resource = "renamedialog.ui"
    name = "RenameDialog"

    def __init__(self, original, checker=None):
        Window.__init__(self)
        self.original = original
        entry = self.get_entry()
        entry.set_text(original.name)
        if checker:
            self.set_sensitive(False)
            entry.connect("changed", self.on_changed, checker)

    def get_entry(self):
        return self.get_object("name_entry")

    def set_sensitive(self, sensitive):
        self.get_object("ok_button").set_sensitive(sensitive)

    def get_name(self):
        return self.get_entry().get_text()

    def on_changed(self, entry, check):
        try:
            check(self.get_name())
            self.set_sensitive(True)
        except errors.InvalidNameError:
            self.set_sensitive(False)

    @destroy_on_exit
    def on_RenameDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            name = self.get_name()
            try:
                self.rename(name)
            except errors.InvalidNameError:
                logger.error(invalid_name, name=name)

    def rename(self, name):
        self.original.rename(name)


class RenameBrickDialog(RenameDialog):

    def rename(self, name):
        old = self.original.name
        self.original.rename(name)
        regex = re.compile("^{0}_([a-z0-9]+).cow$".format(old))
        new = r"{0}_\1.cow".format(self.original.name)
        for fp in filepath.FilePath(project.manager.current.path).children():
            if fp.isfile() and regex.match(fp.basename()):
                fp.moveTo(fp.sibling(regex.sub(new, fp.basename())))


class NewBrickDialog(Window):

    resource = "newbrick.ui"
    _type = "Switch"

    def __init__(self, factory):
        Window.__init__(self)
        self.factory = factory

    def on_BrickType_toggled(self, radiobutton):
        self._type = Gtk.Buildable.get_name(radiobutton)[2:]
        return True

    @destroy_on_exit
    def on_NewBrickDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            name = self.etrName.get_text()
            try:
                self.factory.new_brick(self._type, name)
            except errors.InvalidNameError:
                logger.error(brick_invalid_name)
            else:
                logger.debug(created)
        return True


class SettingsDialog(Window):

    resource = "settings.ui"

    def __init__(self, gui):
        Window.__init__(self)
        self.gui = gui
        # general
        self.etrTerm.set_text(settings.get("term"))
        self.etrSudo.set_text(settings.get("sudo"))
        self.cbSystray.set_active(settings.get("systray"))
        self.cbShowMissing.set_active(settings.get("show_missing"))
        # vde
        try:
            self.fcbVdepath.set_current_folder(settings.get('vdepath'))
        except NoOptionError:
            pass
        self.cbPython.set_active(settings.get("python"))
        self.cbFemaleplugs.set_active(settings.get("femaleplugs"))
        self.cbErroronloop.set_active(settings.get("erroronloop"))
        # qemu
        try:
            self.fcbQemupath.set_current_folder(settings.get('qemupath'))
        except NoOptionError:
            pass
        self.lFormats.set_data_source(["cow", "qcow", "qcow2"])
        self.cbCowfmt.set_selected_value(settings.get("cowfmt"))
        self.cbCowfmt.set_cell_data_func(self.crt1, self.crt1.set_cell_data)
        self.cbKsm.set_active(settings.get("ksm"))
        self.cbKsm.set_sensitive(tools.check_ksm())

    def on_fcbVdepath_selection_changed(self, filechooser):
        newpath = filechooser.get_filename()
        missing = tools.check_missing_vde(newpath)
        if not os.access(newpath, os.X_OK):
            text = '<span color="red">{0}:</span>\n{1}'.format(
                _("Error"), _("invalid path for vde binaries"))
        elif len(missing) > 0:
            text = '<span color="red">{0}:</span>\n'.format(
                _("Warning, missing modules"))
            for l in missing:
                text += l + "\n"
        else:
            text = '<span color="darkgreen">{0}.</span>\n'.format(
                _("All VDE components detected"))
        self.lblVdepath.set_markup(text)

    def on_fcbQemupath_selection_changed(self, filechooser):
        newpath = filechooser.get_filename()
        missing_qemu = False
        missing, found = tools.check_missing_qemu(newpath)
        if "qemu" in missing:
            missing_qemu = True
        if not os.access(newpath, os.X_OK):
            text = '<span color="red">{0}:</span>\n{1}'.format(
                _("Error"), _("invalid path for qemu binaries"))
        else:
            if missing_qemu:
                text = '<span color="red">{0}:</span>\n{1}'.format(
                    _("Warning"), _("cannot find qemu, using kvm only"))
            else:
                text = '<span color="darkgreen">{0}.</span>\n'.format(
                    _("Qemu detected"))
            arch = []
            for f in found:
                if f.startswith("qemu-system-"):
                    arch.append(f[12:])
            if arch:
                text += "{0}:\n{1}".format(_("additional targets supported"),
                                           textwrap.fill(" ".join(arch), 30))
        self.lblQemupath.set_markup(text)

    def on_SettingsDialog_response(self, dialog, response_id):
        if response_id in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
            logger.debug(apply_settings)
            # general
            settings.set("term", self.etrTerm.get_text())
            settings.set("sudo", self.etrSudo.get_text())
            settings.set("systray", self.cbSystray.get_active())
            settings.set("show_missing", self.cbShowMissing.get_active())
            # vde
            vdepath = self.fcbVdepath.get_current_folder()
            if vdepath is not None:
                settings.set('vdepath', vdepath)
            settings.set("python", self.cbPython.get_active())
            settings.set("femaleplugs", self.cbFemaleplugs.get_active())
            settings.set("erroronloop", self.cbErroronloop.get_active())
            # qemu
            qemupath = self.fcbQemupath.get_current_folder()
            if qemupath is not None:
                settings.set('qemupath', qemupath)
            settings.set("cowfmt", self.cbCowfmt.get_selected_value())
            settings.set("ksm", self.cbKsm.get_active())
            tools.enable_ksm(self.cbKsm.get_active(), settings.get("sudo"))
            if self.cbSystray.get_active():
                self.gui.start_systray()
            else:
                self.gui.stop_systray()
            if response_id == Gtk.ResponseType.APPLY:
                return
        dialog.destroy()


class AttachEventDialog(Window):

    resource = "attachevent.ui"

    def __init__(self, brick, factory):
        Window.__init__(self)
        self.brick = brick
        events = (e for e in factory.events if e.configured())
        self.lEvents.set_data_source(events)
        # event start
        event_start = factory.get_event_by_name(brick.get("pon_vbevent"))
        self.tvStart.set_selected_value(event_start)
        self.tvStart.set_cells_data_func()
        # event stop
        event_stop = factory.get_event_by_name(brick.get("poff_vbevent"))
        self.tvStop.set_selected_value(event_stop)
        self.tvStop.set_cells_data_func()

    def on_btnStartSelClear_clicked(self, button):
        self.tvStart.set_selected_value(widgets.SELECT_NONE)
        return True

    def on_btnStopSelClear_clicked(self, button):
        self.tvStop.set_selected_value(widgets.SELECT_NONE)
        return True

    def on_treeview_button_press_event(self, treeview, event):
        if event.button == 1:
            path = treeview.get_path_at_pos(int(event.x), int(event.y))
            if path is None:
                treeview.set_selected_value(widgets.SELECT_NONE)
                return True

    @destroy_on_exit
    def on_AttachEventDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            event_start = self.tvStart.get_selected_value()
            event_stop = self.tvStop.get_selected_value()
            cfg = {
                "pon_vbevent": event_start.name if event_start else "",
                "poff_vbevent": event_stop.name if event_stop else "",
            }
            self.brick.set(cfg)
        return True
