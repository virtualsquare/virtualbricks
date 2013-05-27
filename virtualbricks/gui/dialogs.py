# -*- test-case-name: virtualbricks.tests.test_dialogs -*-
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
import errno
import logging
import subprocess
import threading

import gtk

from virtualbricks import version, tools
from virtualbricks.gui import graphics


log = logging.getLogger(__name__)


if False:  # pyflakes
    _ = str


BUG_REPORT_ERRORS = {
    1: "Error in command line syntax.",
    2: "One of the files passed on the command line did not exist.",
    3: "A required tool could not be found.",
    4: "The action failed.",
    5: "No permission to read one of the files passed on the command line."
}


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
        self.builder = builder = gtk.Builder()
        builder.set_translation_domain(self.domain)
        builder.add_from_file(graphics.get_filename("virtualbricks.gui",
                                                    self.resource))
        self.widget = builder.get_object(self.get_name())
        builder.connect_signals(self)

    def get_object(self, name):
        return self.builder.get_object(name)

    def get_name(self):
        if self.name:
            return self.name
        return self.__class__.__name__

    def show(self):
        self.widget.show()


class Window(Base):
    """Base class for all dialogs."""

    @property
    def window(self):
        return self.widget

    def show(self):
        self.widget.show()


class AboutDialog(Window):

    resource = "data/about.ui"

    def __init__(self):
        Window.__init__(self)
        self.window.set_version(version.short())
        # to handle show() instead of run()
        self.window.connect("response", lambda d, r: d.destroy())


class LoggingWindow(Window):

    resource = "data/logging.ui"

    def __init__(self, textbuffer):
        Window.__init__(self)
        self.textbuffer = textbuffer
        self.__bottom = True
        textview = self.get_object("textview1")
        textview.set_buffer(textbuffer)
        self.__insert_text_h = textbuffer.connect("changed",
                self.on_textbuffer_changed, textview)
        vadjustment = self.get_object("scrolledwindow1").get_vadjustment()
        self.__vadjustment_h = vadjustment.connect("value-changed",
                self.on_vadjustment_value_changed)
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
        vadjustment = self.get_object("scrolledwindow1").get_vadjustment()
        vadjustment.disconnect(self.__vadjustment_h)

    def on_closebutton_clicked(self, button):
        self.window.destroy()

    def on_cleanbutton_clicked(self, button):
        self.textbuffer.set_text("")

    def on_savebutton_clicked(self, button):
        chooser = gtk.FileChooserDialog(title=_("Save as..."),
                action=gtk.FILE_CHOOSER_ACTION_SAVE,
                buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                        gtk.STOCK_SAVE, gtk.RESPONSE_OK))
        chooser.set_do_overwrite_confirmation(True)
        chooser.connect("response", self.__on_dialog_response)
        chooser.show()

    def __on_dialog_response(self, dialog, response_id):
        try:
            if response_id == gtk.RESPONSE_OK:
                with open(dialog.get_filename(), "w") as fp:
                    self.save_to(fp)
        finally:
            dialog.destroy()

    def on_reportbugbutton_clicked(self, button):
        td = threading.Thread(target=self.send_bug_report,
                              name="BugReportThread")
        td.daemon = True
        td.start()

    def send_bug_report(self):
        log.info("Sending report bug")
        with tools.Tempfile() as (fd, filename):
            with os.fdopen(fd, "w") as fp:
                self.save_to(fp)
            try:
                subprocess.call(["xdg-email", "--utf8", "--body",
                                 " affects virtualbrick", "--attach", filename,
                                 "new@bugs.launchpad.net"])
                log.info("Report bug sent succefully")
            except OSError, e:
                # This is a special exception with the child traceback
                # attacched
                if e.errno == errno.ENOENT:
                    log.exception("Cannot find xdg-email utility")
                else:
                    log.exception("Exception raised in the child.")
                log.warning("Child traceback:\n%s", e.child_traceback)
            except subprocess.CalledProcessError, e:
                msg = _("Bug report not sent because of an error")
                if e.returncode in BUG_REPORT_ERRORS:
                    err = _(BUG_REPORT_ERRORS[e.returncode])
                else:
                    err = _("Unknown error.")
                log.error("%s: %s\nCommand output:\n%s", msg, err, e.output)

    def save_to(self, fileobj):
        fileobj.write(self.textbuffer.get_property("text"))


class DisksLibraryDialog(Window):

    resource = "data/disklibrary.ui"
    cols_cell = (
        ("treeviewcolumn1", "cellrenderertext1", lambda i: i.name),
        ("treeviewcolumn2", "cellrenderertext2", lambda i: i.get_users()),
        ("treeviewcolumn3", "cellrenderertext3",
         lambda i: i.get_master_name()),
        ("treeviewcolumn4", "cellrenderertext4", lambda i: i.get_cows()),
        ("treeviewcolumn5", "cellrenderertext5", lambda i: i.get_size())
    )

    image = None

    def __init__(self, factory):
        Window.__init__(self)
        self.factory = factory
        model = self.get_object("liststore1")
        self.__add_handler_id = factory.connect("image_added",
                self.on_image_added, model)
        self.__del_handler_id = factory.connect("image_removed",
                self.on_image_removed, model)
        self.window.connect("destroy", self.on_window_destroy)
        self.tree_panel = self.get_object("treeview_panel")  # just handy
        self.config_panel = self.get_object("config_panel")  # just handy
        for column_name, cell_renderer_name, getter in self.cols_cell:
            column = self.get_object(column_name)
            cell_renderer = self.get_object(cell_renderer_name)
            column.set_cell_data_func(cell_renderer, self._set_cell_data,
                                      getter)
        for image in factory.disk_images:
            model.append((image,))

    def _set_cell_data(self, column, cell_renderer, model, iter, getter):
        image = model.get_value(iter, 0)
        cell_renderer.set_property("text", getter(image))
        color = "black" if image.exists() else "grey"
        cell_renderer.set_property("foreground", color)

    def show(self):
        Window.show(self)
        self.config_panel.hide()

    def on_window_destroy(self, widget):
        assert self.__add_handler_id is not None, \
                "Called on_window_destroy but no handler are associated"
        self.factory.disconnect(self.__add_handler_id)
        self.factory.disconnect(self.__del_handler_id)
        self.__add_handler_id = self.__del_handler_id = None

    def on_image_added(self, factory, image, model):
        model.append((image,))

    def on_image_removed(self, factory, image, model):
        iter = model.get_iter_first()
        while iter:
            if model.get_value(iter, 0) == image:
                model.remove(iter)
                break
        else:
            log.warning("image_removed signal is emitted but seems I don't"
                        " have that image")

    def on_close_button_clicked(self, button):
        self.window.destroy()

    def on_treeview_diskimages_row_activated(self, treeview, path, column):
        self.image = treeview.get_model()[path][0]
        self.tree_panel.hide()
        self.config_panel.show()

    def on_revert_button_clicked(self, button):
        self.config_panel.hide()
        self.tree_panel.show()

    def on_remove_button_clicked(self, button):
        assert self.image is not None, \
                "Called on_remove_button_clicked but self.image is not set."
        try:
            self.factory.remove_disk_image(self.image)
        except Exception:
            log.exception("Cannot remove image %s", self.image)
        self.tree_panel.show()
        self.config_panel.hide()

    def on_save_button_clicked(self, button):
        assert self.image is not None, \
                "Called on_save_button_clicked but no image is selected"
        name = self.get_object("name_entry").get_text()
        if self.image.name != name:
            self.image.rename(name)
        host = self.get_object("host_entry").get_text()
        if host != self.image.host:
            self.image.host = host
        ro = self.get_object("readonly_checkbutton").get_active()
        self.image.set_readonly(ro)
        desc = self.get_object("description_entry").get_text()
        self.image.set_description(desc)
        self.image = None
        self.tree_panel.show()
        self.config_panel.hide()

    def on_diskimages_config_panel_show(self, panel):
        assert self.image is not None, \
                "Called on_diskimages_config_panel_show but image is None"
        i, w = self.image, self.get_object
        w("name_entry").set_text(i.name)
        w("path_entry").set_text(i.path)
        w("description_entry").set_text(i.get_description())
        w("readonly_checkbutton").set_active(i.is_readonly())
        w("host_entry").set_text(i.host or "")


def get_usb_devices():
    try:
        return subprocess.check_output("lsusb")
    except subprocess.CalledProcessError, e:
        log.exception("lsusb returned with error code %d\n%s",
                      e.returncode, e.output)
    except OSError, e:
        log.exception("cannot launch lsusb")


class UsbDevWindow(Window):

    resource = "data/usbdev.ui"

    def __init__(self, gui):
        Window.__init__(self)
        self.gui = gui

        output = get_usb_devices().strip()
        if output is None:
            self.window.destroy()
            return
        log.debug("lsusb output:\n%s", output)
        model = self.get_object("liststore1")
        self._populate_model(model, output)

    def _populate_model(self, model, output):
        for line in output.split("\n"):
            info = line.split(" ID ")[1]
            if " " in info:
                code, descr = info.split(" ", 1)
                model.append([code, descr])
        treeview = self.get_object("treeview1")
        selection = treeview.get_selection()
        selection.set_mode(gtk.SELECTION_MULTIPLE)
        vm = self.gui.maintree.get_selection()
        currents = vm.cfg.usbdevlist.split()
        # if currents:
        iter = model.get_iter_first()
        while iter:
            for dev in currents:
                ndev = model.get_value(iter, 0)
                if ndev == dev:
                    selection.select_iter(iter)
                    log.debug("found %s", dev)
                    break
            iter = model.iter_next(iter)

    def on_ok_button_clicked(self, button):
        treeview = self.get_object("treeview1")
        selection = treeview.get_selection()
        if selection:
            model, paths = selection.get_selected_rows()
            devs = " ".join(model[p[0]][0] for p in paths)

            if devs and not os.access("/dev/bus/usb", os.W_OK):
                log.error(_("Cannot access /dev/bus/usb. "
                            "Check user privileges."))
                self.gui.gladefile.get_widget("cfg_Qemu_usbmode_check"
                                             ).set_active(False)

            vm = self.gui.maintree.get_selection()
            old = vm.cfg.usbdevlist
            vm.cfg.set('usbdevlist=' + devs)
            vm.update_usbdevlist(devs, old)
        self.window.destroy()


class ChangePasswordDialog(Window):

    resource = "data/changepwd.ui"

    def __init__(self, remote_host):
        Window.__init__(self)
        self.remote_host = remote_host
        self.get_object("password_entry").set_text(remote_host.password)

    def on_ChangePasswordDialog_response(self, dialog, response_id):
        if response_id == gtk.RESPONSE_OK:
            password = self.get_object("password_entry").get_text()
            self.remote_host.password = password
        dialog.destroy()

    def on_password_entry_activate(self, entry):
        self.window.response(gtk.RESPONSE_OK)
