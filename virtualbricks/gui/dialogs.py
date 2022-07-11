# -*- test-case-name: virtualbricks.tests.test_dialogs -*-
# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2019 Virtualbricks team

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

from contextlib import contextmanager
import errno
import functools
import os
from os.path import (
    basename,
    splitext
)
from pathlib import Path
import string
import tempfile
import textwrap

from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango
import twisted
from twisted.internet import utils, defer, task, error
from twisted.python import filepath
from zope.interface import implementer

from virtualbricks import __version__
from virtualbricks import console
from virtualbricks import errors
from virtualbricks import log
from virtualbricks import settings
from virtualbricks import tools
from virtualbricks import virtualmachines
from virtualbricks._settings import DEFAULT_CONF
from virtualbricks.spawn import qemu_commit_image, qemu_img
from virtualbricks.errors import (
    InvalidNameError,
    NameAlreadyInUseError,
    NoOptionError,
)
from virtualbricks.gui import graphics, widgets
from virtualbricks.gui.interfaces import IDialog, IWidgetBuilder, IWindow
from virtualbricks.project import manager as project_manager
from virtualbricks.tools import dispose
from virtualbricks.virtualmachines import is_virtualmachine


if False:  # pyflakes
    _ = str
if twisted.__version__ >= '15.0.2':
    # This is an ugly hack but virtualbricks is not really ready for
    # Python3
    def mktempfn():
        return filepath._secureEnoughString(project_manager.path)
else:
    def mktempfn():
        return filepath._secureEnoughString()


_MARKER = object()


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
# img_choose = log.Event("Choose a filename first!")
# img_invalid_type = log.Event("Invalid value for format combo, assuming raw")
# img_invalid_unit = log.Event("Invalid value for unit combo, assuming Mb")
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


@implementer(IWidgetBuilder)
class BuilderHelper:

    def __init__(self, resource, translation_domain='virtualbricks'):
        """
        :param str resource: the Gtk.Builder resource file. Only the basename.
        :type translation_domain: str
        """

        self.builder = builder = Gtk.Builder()
        builder.set_translation_domain(translation_domain)
        builder_filename = graphics.get_data_filename(resource)
        if builder_filename is None:
            raise FileNotFoundError(f'File not found {resource!r}')
        builder.add_from_file(builder_filename)

    def __getattr__(self, name):
        return self.get_object(name)

    def get_object(self, name, default=_MARKER):
        """
        Return the widget in the Gtk.Builder with name ``name``. If no widget
        is found WidgetNotFound is raised or a default is returned if given.

        :type name: str
        :type default: Any
        :type default: Any
        """

        widget = self.builder.get_object(name)
        if widget is None:
            if default is _MARKER:
                raise errors.WidgetNotFound(name)
            else:
                return default
        else:
            return widget

    def connect_signals(self, signal_handler):
        """
        Connect the signals degined in the Gtk.Builder file to signal_handler.

        :type signal_handler: Any
        :rtype: None
        """

        self.builder.connect_signals(signal_handler)


@implementer(IWindow)
class _Window:
    """
    Base class for all windows.

    All sub-classes must define _builder attribute of type
    IWidgetBuilder.
    """

    _builder = None
    on_destroy = None
    name = None

    @property
    def w(self):
        if self._builder is None:
            raise AttributeError('_builder is not set')
        return self._builder

    def _get_name(self):
        """
        Return the name of the window widget.

        :rtype: str
        """

        return self.name or self.__class__.__name__

    def _get_window(self):
        """
        Return the window widget.

        :rtype: Gtk.Window
        """

        return self._builder.get_object(self._get_name())

    def show(self):
        assert self._builder is not None
        window = self._get_window()
        if self.on_destroy is not None:
            window.connect("destroy", lambda w: self.on_destroy())
        window.show()


@implementer(IDialog)
class _Dialog(_Window):

    def show(self, parent):
        """
        :type parent: Gtk.Window
        """

        assert self._builder is not None
        self._get_window().set_transient_for(parent)
        super().show()


class AboutDialog(_Dialog):

    def __init__(self):
        self._builder = BuilderHelper('about.ui')
        self._builder.connect_signals(self)
        self.w.AboutDialog.set_version(__version__)

    def on_AboutDialog_response(self, dialog, response):
        dialog.destroy()


class LoggingWindow(_Window):

    scroll_tolerance = 50

    def __init__(self, textbuffer):
        """
        :type textbuffer: Gtk.TextBuffer
        """

        self._textbuffer = textbuffer
        self._builder = BuilderHelper('logging.ui')
        self._builder.connect_signals(self)
        self._scroll_to_bottom = True
        self.w.textview.set_buffer(textbuffer)
        self._on_textbuffer_changed_handler = textbuffer.connect(
            'changed',
            self.on_textbuffer_changed,
            self.w.textview
        )
        self.scroll_to_end(self.w.textview, textbuffer)

    def scroll_to_end(self, textview, textbuffer):
        """
        Scroll the view to the bottom.

        :type textview: Gtk.TextView
        :type textbuffer: Gtk.TextBuffer
        """

        textview.scroll_to_mark(
            mark=textbuffer.get_mark('end'),
            within_margin=0.0,
            use_align=True,
            xalign=0,  # left
            yalign=1  # bottom
        )

    def on_scrolledwindow_scroll_event(self, window, event):
        """
        Check if the window should automatically scroll to the bottom when new
        messages arrives.

        :type window: Gtk.ScrolledWindow
        :type event: Gdk.EventScroll
        :rtype: bool
        """

        adjustment = window.get_vadjustment()
        self._scroll_to_bottom = (
            adjustment.get_value()  # current offset from top
            >=
            adjustment.get_upper() -  # The maximum value for the adjustment
            adjustment.get_page_size() -  # The visible size
            self.scroll_tolerance
        )
        return False

    def on_textbuffer_changed(self, textbuffer, textview):
        """
        Scroll the view to the bottom, following the messages as the arrive,
        but only if the user did not scroll up.

        :type textbuffer: Gtk.TextBuffer
        :type textview: Gtk.TextView
        """

        if self._scroll_to_bottom:
            self.scroll_to_end(textview, textbuffer)
        return True

    def on_LoggingWindow_destroy(self, window):
        """
        Remove the handled we connected when the logging window opened.

        :type adjustment: Gtk.Window
        """

        self._textbuffer.disconnect(self._on_textbuffer_changed_handler)
        return True

    def on_closeButton_clicked(self, button):
        """
        Close the window.

        :type adjustment: Gtk.Button
        """

        self.w.LoggingWindow.destroy()
        return True

    def on_clearButton_clicked(self, button):
        """
        Clean the logging window.

        :type adjustment: Gtk.Button
        """

        self._textbuffer.set_text('')
        return True

    def on_saveButton_clicked(self, button):
        """
        Save the message to a file.

        :type adjustment: Gtk.Button
        """

        chooser = Gtk.FileChooserDialog(
            title=_('Save as...'),
            parent=self.w.LoggingWindow,
            action=Gtk.FileChooserAction.SAVE,
            buttons=(
                'gtk-cancel', Gtk.ResponseType.CANCEL,
                'gtk-save', Gtk.ResponseType.OK
            )
        )
        chooser.set_do_overwrite_confirmation(True)
        chooser.connect('response', self.on_saveDialog_response)
        chooser.show()
        return True

    def on_saveDialog_response(self, dialog, response_id):
        try:
            if response_id == Gtk.ResponseType.OK:
                text = self._textbuffer.get_property('text')
                with open(dialog.get_filename(), 'w') as fp:
                    fp.write(text)
        finally:
            dialog.destroy()
        return True

    def on_reportBugLinkButton_activate_link(self, button):
        """
        Handle the click on report bug button

        :type button: Gtk.LinkButton
        """

        logger.info(bug_send)

        def xdg_email_exit_cb(codes):
            stdout, stderr, code = codes
            if code == 0:
                logger.info(bug_sent)
            elif code in BUG_REPORT_ERRORS:
                logger.error(bug_error, err=BUG_REPORT_ERRORS[code],
                             stderr=stderr, hide_to_user=True)
            else:
                logger.error(bug_report_fail, code=code, stderr=stderr,
                             hide_to_user=True)

        body = textwrap.dedent(
            f'''




            Please keep the following lines as they are.
            The attachment contains the logs of Virtualbricks.

            Virtualbricks version: {__version__}
            '''
        )
        messages = self._textbuffer.get_property('text')
        # Do not remove the file once xdg-email exits.
        fd, filename = tempfile.mkstemp(prefix='virtualbricks_log_', text=True)
        with os.fdopen(fd, mode='wt', encoding='utf8') as fp:
            fp.write(messages)
        params = [
            '--utf8', '--subject', '[Virtualbricks] ', '--body', body,
            '--attach', filename
        ]
        env = dict(os.environ, MM_NOTTTY='1')
        proc_d = utils.getProcessOutputAndValue('xdg-email', params, env)
        proc_d.addCallback(xdg_email_exit_cb)
        proc_d.addErrback(logger.failure_eb, bug_err_unknown)
        # Stop the propagation of activate-link signal
        return True


def iter_tree_model(tree_model):
    """
    :type disk_image: virtualbricks.virtualmachines.Image
    :rtype: Generator[Tuple[Any, Gtk.TreeIter]]
    """

    itr = tree_model.get_iter_first()
    while itr:
        value = tree_model.get_value(itr, 0)
        yield value, itr
        itr = tree_model.iter_next(itr)


class DisksLibraryWindow(_Window):

    @staticmethod
    def set_cell_name(tree_column, cell, tree_model, tree_itr, data):
        disk_image = tree_model.get_value(tree_itr, 0)
        cell.set_property('text', disk_image.get_name())
        return True

    @staticmethod
    def set_cell_path(tree_column, cell, tree_model, itr, data):
        disk_image = tree_model.get_value(itr, 0)
        cell.set_property('text', str(disk_image.path))
        return True

    @staticmethod
    def set_cell_used_by(tree_column, cell, tree_model, itr, brickfactory):
        disk_image = tree_model.get_value(itr, 0)
        count = 0
        for vm in filter(is_virtualmachine, brickfactory.bricks):
            for disk in vm.disks():
                if disk.image is disk_image and disk.is_cow():
                    count += 1
        cell.set_property("text", str(count))

    @staticmethod
    def set_cell_master_brick(tree_column, cell, tree_model, itr, data):
        disk_image = tree_model.get_value(itr, 0)
        text = '' if disk_image.master is None else repr(disk_image.master)
        cell.set_property('text', text)
        return True

    @staticmethod
    def set_cell_cows(tree_column, cell, tree_model, itr, brickfactory):
        disk_image = tree_model.get_value(itr, 0)
        num_cows = 0
        for vm in filter(is_virtualmachine, brickfactory.bricks):
            for disk in vm.disks():
                if disk.image is disk_image and disk.is_cow():
                    num_cows += 1
        cell.set_property("text", str(num_cows))
        return True

    @staticmethod
    def set_cell_size(tree_column, cell, tree_model, itr, data):
        disk_image = tree_model.get_value(itr, 0)
        cell.set_property('text', disk_image.get_size())
        return True

    def __init__(self, brickfactory):
        """
        :type brickfactory: virtualbricks.brickfactory.BrickFactory
        """

        self._brickfactory = brickfactory
        self._builder = BuilderHelper('disklibrary.ui')
        self._builder.connect_signals(self)
        self._disk_image = None
        tree_view = self.w.imagesTreeView
        tree_selection = tree_view.get_selection()
        tree_selection.set_mode(Gtk.SelectionMode.SINGLE)
        self._on_selection_changed_handler = tree_selection.connect(
            'changed', self.on_selection_changed)
        self._tree_model = tree_model = Gtk.ListStore(object)
        for disk_image in brickfactory.iter_disk_images():
            tree_model.append([disk_image])
        tree_view.set_model(tree_model)
        self.w.nameTreeViewColumn.set_cell_data_func(
            self.w.nameCellRendererText, self.set_cell_name)
        self.w.pathTreeViewColumn.set_cell_data_func(
            self.w.pathCellRendererText, self.set_cell_path)
        self.w.usedByTreeViewColumn.set_cell_data_func(
            self.w.usedByCellRendererText, self.set_cell_used_by, brickfactory)
        self.w.masterBrickTreeViewColumn.set_cell_data_func(
            self.w.masterBrickCellRendererText, self.set_cell_master_brick)
        self.w.cowsTreeViewColumn.set_cell_data_func(
            self.w.cowsCellRendererText, self.set_cell_cows, brickfactory)
        self.w.sizeTreeViewColumn.set_cell_data_func(
            self.w.sizeCellRendererText, self.set_cell_size)
        brickfactory.image_added.connect(self.on_disk_image_added, tree_model)
        brickfactory.image_changed.connect(
            self.on_disk_image_changed, tree_model)
        brickfactory.image_removed.connect(
            self.on_disk_image_removed, tree_model)

    def _show_edit_screen(self, disk_image):
        """
        :type disk_image: virtualbricks.virtualmachines.Image
        """

        self._disk_image = disk_image
        self.w.pathFileChooserButton.set_filename(disk_image.path)
        self.w.nameEntry.set_text(disk_image.get_name())
        self.w.descriptionTextBuffer.set_text(disk_image.get_description())
        self.w.stackWidget.set_visible_child(self.w.editImageBox)

    def _hide_edit_screen(self):
        self._disk_image = None
        self.w.stackWidget.set_visible_child(self.w.imageListBox)

    def on_selection_changed(self, tree_selection):
        """
        Show or hide the edit button if a disk image has been selected.

        :type tree_selection: Gtk.TreeSelection
        """

        tree_model, itr = tree_selection.get_selected()
        self.w.editButton.set_sensitive(itr is not None)
        return True

    def on_disk_image_added(self, disk_image, tree_model):
        """
        :type disk_image: virtualbricks.virtualmachines.Image
        :type tree_model: Gtk.TreeModel
        """

        tree_model.append([disk_image])

    def on_disk_image_changed(self, disk_image, tree_model):
        """
        :type disk_image: virtualbricks.virtualmachines.Image
        :type tree_model: Gtk.TreeModel
        """

        for obj, itr in iter_tree_model(tree_model):
            if obj == disk_image:
                tree_model.row_changed(tree_model.get_path(itr), itr)
                break

    def on_disk_image_removed(self, disk_image, tree_model):
        """
        :type disk_image: virtualbricks.virtualmachines.Image
        :type tree_model: Gtk.TreeModel
        """

        for obj, itr in iter_tree_model(tree_model):
            if obj == disk_image:
                tree_model.remove(itr)
                break

    def on_imagesTreeView_row_activated(self, tree_view, path, column):
        """
        :type tree_view: Gtk.TreeView
        :type path: Gtk.TreePath
        :type column: Gtk.TreeViewColumn
        """

        model = tree_view.get_model()
        disk_image = model.get_value(model.get_iter(path), 0)
        self._show_edit_screen(disk_image)
        return True

    def on_pathFileChooserButton_file_set(self, file_choser_button):
        filename = file_choser_button.get_filename()
        if filename is not None and self.w.nameEntry.get_text() == '':
            self.w.nameEntry.set_text(os.path.basename(filename))
        return True

    def on_cancelButton_clicked(self, button):
        self._hide_edit_screen()
        return True

    def on_removeButton_clicked(self, button):
        assert self._disk_image is not None
        # TODO: ask for confirmation
        self._brickfactory.remove_disk_image(self._disk_image)
        self._hide_edit_screen()
        return True

    def on_saveButton_clicked(self, button):
        assert self._disk_image is not None
        # self._disk_image.set_path(self.w.pathFileChooserButton.get_filename())
        self._disk_image.path = self.w.pathFileChooserButton.get_filename()
        self._disk_image.set_name(self.w.nameEntry.get_text())
        description = self.w.descriptionTextBuffer.get_property('text')
        self._disk_image.set_description(description)
        self._hide_edit_screen()
        return True

    def on_editButton_clicked(self, button):
        tree_selection = self.w.imagesTreeView.get_selection()
        tree_model, itr = tree_selection.get_selected()
        assert itr is not None
        disk_image = tree_model.get_value(itr, 0)
        self._show_edit_screen(disk_image)
        return True

    def on_closeButton_clicked(self, button):
        self.w.DisksLibraryWindow.destroy()
        return True

    def on_destroy(self, window=None):
        self._brickfactory.image_added.disconnect(
            self.on_disk_image_added, self._tree_model)
        self._brickfactory.image_changed.disconnect(
            self.on_disk_image_changed, self._tree_model)
        self._brickfactory.image_removed.disconnect(
            self.on_disk_image_removed, self._tree_model)
        return True


class UsbDevDialog(_Dialog):

    @staticmethod
    def set_cell_id(tree_column, cell, tree_model, tree_itr, data):
        usb_dev = tree_model.get_value(tree_itr, 1)
        cell.set_property('text', usb_dev.id)
        return True

    @staticmethod
    def set_cell_description(tree_column, cell, tree_model, tree_itr, data):
        usb_dev = tree_model.get_value(tree_itr, 1)
        cell.set_property('text', usb_dev.description)
        return True

    def __init__(self, usb_devices, selected_devices):
        """
        :type usb_devices: List[virtualbricks.virtualmachines.UsbDevice]
        :type selected_devices: List[virtualbricks.virtualmachines.UsbDevice]
        """

        self._usb_devices = usb_devices
        self._selected_devices = selected_devices
        self._builder = BuilderHelper('usbdev.ui')
        self._builder.connect_signals(self)
        self._tree_model = tree_model = Gtk.ListStore(bool, object)
        for device in usb_devices:
            selected = device in selected_devices
            tree_model.append((selected, device))
        self.w.devicesTreeView.set_model(tree_model)
        self.w.selectedCellRendererToggle.set_radio(False)
        self.w.idTreeViewColumn.set_cell_data_func(
            self.w.idCellRendererText, self.set_cell_id)
        self.w.descriptionTreeViewColumn.set_cell_data_func(
            self.w.descriptionCellRendererText, self.set_cell_description)

    def on_selectedCellRendererToggle_toggled(self, cell_renderer, path):
        """
        :type cell_renderer: Gtk.CellRendererToggle
        :type path: Gtk.TreePath
        """

        tree_iter = self._tree_model.get_iter(path)
        selected = self._tree_model.get_value(tree_iter, 0)
        self._tree_model.set_value(tree_iter, 0, not selected)
        return True

    @destroy_on_exit
    def on_UsbDevDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            new_selected_devices = [
                device for selected, device in self._tree_model if selected
            ]
            self._selected_devices[:] = new_selected_devices
        return True


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
        self.get_object("ok_button").set_property("label", "gtk-ok")
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


class _ConfirmDialog(_Dialog):

    name = 'ConfirmDialog'

    def set_primary_text(self, text, markup=False):
        """
        Set the text for the primary label.

        :type text: str
        :type markup: bool
        """

        if text is not None:
            self.w.primaryLabel.show()
            if markup:
                self.w.primaryLabel.set_markup(text)
            else:
                self.w.primaryLabel.set_text(text)
        else:
            self.w.primaryLabel.hide()

    def set_secondary_text(self, text, markup=False):
        """
        Set the text for the primary label.

        :type text: Optional[str]
        :type markup: bool
        """

        if text is not None:
            self.w.secondaryLabel.show()
            if markup:
                self.w.secondaryLabel.set_markup(text)
            else:
                self.w.secondaryLabel.set_text(text)
        else:
            self.w.secondaryLabel.hide()


class DeleteBrickConfirmDialog(_ConfirmDialog):

    def __init__(self, brickfactory, brick):
        self._brickfactory = brickfactory
        self._brick = brick
        self._builder = BuilderHelper('confirmdialog.ui')
        self._builder.connect_signals(self)
        qst_fmt = _('Do you really want to delete {brick} ({type})?')
        question = qst_fmt.format(brick=brick.name, type=brick.get_type())
        self.set_primary_text(question)

    def on_ConfirmDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            self._brickfactory.del_brick(self._brick)
        dialog.destroy()


class DeleteEventConfirmDialog(_ConfirmDialog):

    def __init__(self, brickfactory, event):
        self._brickfactory = brickfactory
        self._event = event
        self._builder = BuilderHelper('confirmdialog.ui')
        self._builder.connect_signals(self)
        qst_fmt = _('Do you really want to delete {event} ({type})?')
        question = qst_fmt.format(event=event.name, type=event.get_type())
        self.set_primary_text(question)
        if event.scheduled is not None:
            self.set_secondary_text(
                _('The event is in use, it will be stopped before.')
            )

    def on_ConfirmDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            self._brickfactory.del_event(self._event)
        dialog.destroy()


class DeleteLinkConfirmDialog(_ConfirmDialog):

    def __init__(self, qemu_config_controller, link):
        self._qemu_config_controller =  qemu_config_controller
        self._link = link
        self._builder = BuilderHelper('confirmdialog.ui')
        self._builder.connect_signals(self)
        question = _('Do you really want to delete the network interface?')
        self.set_primary_text(question)

    def on_ConfirmDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            self._qemu_config_controller._remove_link(self._link)
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
            self._event.set({
                'actions': [
                    console.VbShellCommand(f'{brick.name} {self._action}')
                    for brick in self._added
                ]
            })
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
    if is_virtualmachine(brick):
        for dev in 'hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb', 'mtdblock':
            yield brick.config[dev]


class CommitImageDialog(_Dialog):

    @staticmethod
    def set_cell_title(tree_column, cell, tree_model, tree_itr):
        disk = tree_model.get_value(tree_itr, 0)
        cell.set_property('text', f'{disk.device} on {disk.vm.get_name()}')
        return True

    def __init__(self, brickfactory):
        self._builder = BuilderHelper('commitimagedialog.ui')
        self._builder.connect_signals(self)
        self._tree_model = tree_model = Gtk.ListStore(object)
        for brick in filter(is_virtualmachine, brickfactory.iter_bricks()):
            for disk in (disk for disk in disks_of(brick) if disk.is_cow()):
                tree_model.append([disk])
        self.w.disksComboBox.set_model(tree_model)
        self.w.disksComboBox.set_cell_data_func(
            self.w.diskCellRendererText, self.set_cell_title)

    def do_commit_cow(self):
        filepath = self.w.cowFileChooserButton.get_filename()
        assert filepath is not None
        deferred = qemu_commit_image(filepath)
        ProgressBarDialog(deferred).show(self.w.CommitImageDialog)
        # return deferred

    def do_commit_vm(self):
        # TODO: logger.warning(commit_vm_not_implemented)
        logger.warn(not_implemented)

    def on_disksComboBox_changed(self, combobox):
        # itr = combobox.get_active_iter()
        # tree_model = combobox.get_model()
        # if itr is not None:
        #     selected_disk = tree_model.get_value(itr, 0)
        return True

    def on_CommitImageDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.APPLY:
            action_name = self.w.stack.get_visible_child_name()
            action = getattr(self, f'do_{action_name}')
            action()
        elif response_id == Gtk.ResponseType.CLOSE:
            dialog.destroy()
        return True


# class CommitImageDialog(Window):

#     resource = "commitdialog.ui"
#     parent = None
#     _set_label_d = None

#     def __init__(self, progessbar, factory):
#         Window.__init__(self)
#         self.progessbar = progessbar
#         model = self.get_object("model1")
#         for brick in factory.bricks:
#             for disk in (disk for disk in disks_of(brick) if disk.is_cow()):
#                 model.append((disk.device + " on " + brick.name, disk))

#     def show(self, parent=None):
#         self.parent = parent
#         Window.show(self, parent)

#     def do_image_commit(self, path):
#         self.window.destroy()
#         self.progessbar.wait_for(qemu_commit_image, path)

#     def commit_file(self, pathname):
#         question = ("Warning: the base image will be updated to the\n"
#                     "changes contained in the COW. This operation\n"
#                     "cannot be undone. Are you sure?")
#         ConfirmDialog(question, on_yes=self.do_image_commit,
#                       on_yes_arg=pathname).show(self.parent)

#     def _commit_vm(self, img):
#         logger.warning(not_implemented)
#         # img.VM.commit_disks()
#         self.window.destroy()

#     def commit_vm(self):
#         combobox = self.get_object("disk_combo")
#         model = combobox.get_model()
#         itr = combobox.get_active_iter()
#         if itr:
#             img = model[itr][1]
#             if not self.get_object("cow_checkbutton").get_active():
#                 question = ("Warning: the private COW image will be "
#                             "updated.\nThis operation cannot be undone.\n"
#                             "Are you sure?")
#                 ConfirmDialog(question, on_yes=self._commit_vm,
#                               on_yes_arg=img).show(self.parent)
#             else:
#                 self.commit_file(img.get_cow_path())
#         else:
#             logger.error(img_invalid)

#     def on_CommitImageDialog_response(self, dialog, response_id):
#         if response_id == Gtk.ResponseType.OK:
#             if self.get_object("file_radiobutton").get_active():
#                 pathname = self.get_object(
#                     "cowpath_filechooser").get_filename()
#                 self.commit_file(pathname)
#             else:
#                 self.commit_vm()
#         else:
#             dialog.destroy()

#     def on_file_radiobutton_toggled(self, button):
#         active = button.get_active()
#         filechooser = self.get_object("cowpath_filechooser")
#         filechooser.set_visible(active)
#         filechooser.unselect_all()
#         combo = self.get_object("disk_combo")
#         combo.set_visible(not active)
#         combo.set_active(-1)
#         self.get_object("cow_checkbutton").set_visible(not active)
#         self.get_object("msg_label").set_visible(False)

#     def _commit_image_show_result(self, img_info):
#         label = self.get_object("msg_label")
#         try:
#             label.set_text(img_info[0]['backing-filename'])
#         except KeyError:
#             label.set_text(_("Base not found (invalid cow?)"))
#         label.set_visible(True)

#     def on_cowpath_filechooser_file_set(self, filechooser):
#         if self._set_label_d is not None:
#             self._set_label_d.cancel()
#         filename = filechooser.get_filename()
#         if os.access(filename, os.R_OK):
#             deferred = qemu_img_info(filename)
#             deferred.addCallback(self._commit_image_show_result)
#             self._set_label_d = deferred
#             return deferred

#     def set_label(self, combobox=None, button=None):
#         if self._set_label_d is not None:
#             self._set_label_d.cancel()
#         if combobox is None:
#             combobox = self.get_object("disk_combo")
#         if button is None:
#             button = self.get_object("cow_checkbutton")
#         label = self.get_object("msg_label")
#         label.set_visible(False)
#         model = combobox.get_model()
#         itr = combobox.get_active_iter()
#         if itr is not None:
#             disk = model[itr][1]
#             base = disk.image and disk.image.path or None
#             if base and button.get_active():
#                 # XXX: make disk.get_real_disk_name's deferred cancellable
#                 deferred = disk.get_real_disk_name()
#                 deferred.addCallback(label.set_text)
#                 deferred.addCallback(lambda _: label.set_visible(True))
#                 deferred.addErrback(logger.failure_eb, img_combo)
#                 self._set_label_d = deferred
#             elif base:
#                 label.set_visible(True)
#                 label.set_text(base)
#             else:
#                 label.set_visible(True)
#                 label.set_text("base not found")
#         else:
#             label.set_visible(True)
#             label.set_text("base not found")

#     def on_disk_combo_changed(self, combobox):
#         self.set_label(combobox=combobox)

#     def on_cow_checkbutton_toggled(self, button):
#         self.set_label(button=button)


def block_signal_handler(g_object, handler_id):
    @contextmanager
    def inner():
        GObject.signal_handler_block(g_object, handler_id)
        try:
            yield
        finally:
            GObject.signal_handler_unblock(g_object, handler_id)
    return inner


class LoadImageDialog(_Dialog):

    def __init__(self, brickfactory):
        self._brickfactory = brickfactory
        self._name_set = False
        self._description_set = False
        self._builder = BuilderHelper('loadimagedialog.ui')
        self._builder.connect_signals(self)
        self._block_image_name_entry_changed = block_signal_handler(
            self.w.imageNameEntry,
            self.w.imageNameEntry.connect(
                'changed',
                self.on_imageNameEntry_changed
            )
        )
        self._block_description_textbuffer_changed = block_signal_handler(
            self.w.descriptionTextBuffer,
            self.w.descriptionTextBuffer.connect(
                'changed',
                self.on_descriptionTextBuffer_changed
            )
        )
        self._image_path_error = None
        self._name_error = None

    def _load_desc(self, pathname):
        try:
            with open(pathname + '.vbdescr') as fd:
                return fd.read()
        except FileNotFoundError:
            return ''

    def _set_error(self):
        """
        :rtype: None
        """

        file_chooser_button = self.w.imageFileChooserButton
        image_name_entry = self.w.imageNameEntry
        if self._image_path_error is not None:
            file_chooser_button.get_style_context().add_class('error')
            file_chooser_button.set_tooltip_markup(self._image_path_error)
        else:
            file_chooser_button.get_style_context().remove_class('error')
            file_chooser_button.set_tooltip_text(None)
        if self._name_error:
            image_name_entry.get_style_context().add_class('error')
            image_name_entry.set_tooltip_markup(self._name_error)
        else:
            image_name_entry.get_style_context().remove_class('error')
            image_name_entry.set_tooltip_markup(None)
        if self._image_path_error is not None or self._name_error is not None:
            self.w.okButton.set_sensitive(False)
        else:
            self.w.okButton.set_sensitive(
                file_chooser_button.get_filename() is not None
                and image_name_entry.get_text() != ''
            )

    def _check_name(self):
        image_name = self.w.imageNameEntry.get_text()
        if image_name == '':
            self._name_error = None
        else:
            try:
                self._brickfactory.normalize_name(image_name)
                self._name_error = None
            except NameAlreadyInUseError:
                self._name_error = (
                    f'Name <span weight="bold">{image_name}</span>'
                    ' is already in use'
                )
            except InvalidNameError as exc:
                self._name_error = str(exc)

    def on_imageFileChooserButton_file_set(self, filechooserbutton):
        """
        :type filechooserbutton: Gtk.FileChooserButton
        :rtype: bool
        """

        filepath = filechooserbutton.get_filename()
        if filepath is None:
            self._image_path_error = None
            return True
        if self._brickfactory.get_image_by_path(filepath) is not None:
            self._image_path_error = 'Image is already in use'
        else:
            self._image_path_error = None
        if not self._name_set:
            image_name, ext = splitext(basename(filepath))
            with self._block_image_name_entry_changed():
                self.w.imageNameEntry.set_text(image_name)
            self._check_name()
        if not self._description_set:
            with self._block_description_textbuffer_changed():
                self.w.descriptionTextBuffer.set_text(self._load_desc(filepath))
        self._set_error()
        return True

    def on_imageNameEntry_changed(self, entry):
        """
        :type entry: Gtk.Entry
        :rtype: bool
        """

        self._name_set = entry.get_text() != ''
        self._check_name()
        self._set_error()
        return True

    def on_descriptionTextBuffer_changed(self, textbuffer):
        """
        :type textbuffer: Gtk.TextBuffer
        :rtype: bool
        """

        self._description_set = textbuffer.get_property('text') != ''
        return True

    @destroy_on_exit
    def on_LoadImageDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            name = self.w.imageNameEntry.get_text()
            description = self.w.descriptionTextBuffer.get_property('text')
            filepath = self.w.imageFileChooserButton.get_filename()
            self._brickfactory.new_disk_image(name, filepath, description)
        return True


class QemuCreateArgs:

    def __init__(self, name, pathname, fileformat, size):
        self.name = name
        self.pathname = pathname
        self.fileformat = fileformat
        self.size = size


class CreateImageDialog(_Dialog):

    def __init__(self, gui, factory):
        self.gui = gui
        # self.factory = factory
        self._builder = BuilderHelper('createimagedialog.ui')
        self._builder.connect_signals(self)

    def _get_create_image_args(self):
        name = self.w.imageNameEntry.get_text()
        if not name:
            raise ValueError("empty name")
        folder = self.w.folderFileChooserButton.get_filename()
        if folder is None:
            raise ValueError("folder not chosen")
        fileformat = self._get_fileformat()
        pathname = f"{folder}/{name}.{fileformat}"
        size = self._get_size()
        return QemuCreateArgs(name, pathname, fileformat, size)

    def _get_fileformat(self):
        model = self.w.formatComboBox.get_model()
        itr = self.w.formatComboBox.get_active_iter()
        if itr is not None:
            fileformat = model[itr][0]
            if fileformat == "Auto":
                fileformat = "raw"
            return fileformat
        else:
            raise ValueError('invalid fileformat')

    def _get_size(self):
        size = self.w.sizeSpinButton.get_value_as_int()
        # Get size unit and remove the last character "B"
        # because qemu-img want k, M, G or T suffixes.
        model = self.w.unitComboBox.get_model()
        itr = self.w.unitComboBox.get_active_iter()
        if itr is not None:
            unit = model[itr][0][0]
        else:
            raise ValueError('invalid size')
        return f'{size}{unit}'

    def _toggle_dialog_response(self):
        enable = True
        try:
            self._get_create_image_args()
        except ValueError:
            enable = False
        self.w.createButton.set_sensitive(enable)

    def create_image(self, args):
        done_deferred = qemu_img([
            'create', '-f', args.fileformat, args.pathname, args.size
        ])
        done_deferred.addCallback((lambda stdout: args.name, args.pathname))
        logger.log_failure(done_deferred, img_create_err)
        return done_deferred

    # Events

    def on_imageNameEntry_changed(self, *args):
        self._toggle_dialog_response()
        return True

    def on_folderFileChooserButton_file_set(self, *args):
        self._toggle_dialog_response()
        return True

    def on_formatComboBox_changed(self, *args):
        self._toggle_dialog_response()
        return True

    def on_sizeSpinButton_value_changed(self, *args):
        self._toggle_dialog_response()
        return True

    def on_unitComboBox_changed(self, *args):
        self._toggle_dialog_response()
        return True

    def on_CreateImageDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            logger.info(img_create)
            args = self._get_create_image_args()
            self.gui.user_wait_action(self.create_image(args))
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


class _ProjectListDialog(_Dialog):

    name = 'ProjectListDialog'
    title = None

    def __init__(self, gui):
        self._gui = gui
        self._builder = BuilderHelper('projectlistdialog.ui')
        self._builder.connect_signals(self)
        tree_selection = self.w.projectsTreeView.get_selection()
        tree_model, tree_iter = tree_selection.get_selected()
        for project in project_manager:
            if project != project_manager.current:
                tree_model.append([project.name])
        if self.title is not None:
            self._get_window().set_title(self.title)
        tree_selection.unselect_all()

    def do_action(self, name):
        raise NotImplementedError('_ProjectListDialog.do_action')

    def _do_action_if_selected(self, tree_selection):
        model, tree_iter = tree_selection.get_selected()
        if tree_iter:
            name = model.get_value(tree_iter, 0)
            self.do_action(name)

    def on_projectsTreeSelection_changed(self, tree_selection):
        model, tree_iter = tree_selection.get_selected()
        button_is_sensitive = tree_iter is not None
        self.w.okButton.set_sensitive(button_is_sensitive)

    def on_projectsTreeView_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        tree_iter = model.get_iter(path)
        if tree_iter:
            name = model.get_value(tree_iter, 0)
            self.do_action(name)
        return True

    def on_ProjectListDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            tree_selection = self.w.projectsTreeView.get_selection()
            self._do_action_if_selected(tree_selection)
        dialog.destroy()
        return True


class OpenProjectDialog(_ProjectListDialog):

    @property
    def title(self):
        return _('Virtualbricks - Open project')

    def do_action(self, name):
        self._gui.on_open(name)
        self._gui.set_title()
        self._get_window().destroy()


class DeleteProjectConfirmDialog(_ConfirmDialog):

    def __init__(self, name, tree_model):
        self._name = name
        self._tree_model = tree_model
        self._builder = BuilderHelper('confirmdialog.ui')
        self._builder.connect_signals(self)
        question_fmt = _('Do you really want to delete the project {name}?')
        self.set_primary_text(question_fmt.format(name=name))

    def on_ConfirmDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            project_manager.get_project(self._name).delete()
            for project_name, tree_iter in iter_tree_model(self._tree_model):
                if project_name == self._name:
                    self._tree_model.remove(tree_iter)
                    break
        dialog.destroy()
        return True


class DeleteProjectDialog(_ProjectListDialog):

    @property
    def title(self):
        return _('Virtualbricks - Delete project')

    def do_action(self, name):
        tree_model = self.w.projectsListstore
        DeleteProjectConfirmDialog(name, tree_model).show(self._get_window())


class RenameProjectDialog(SimpleEntryDialog):

    @property
    def description(self):
        return _("New project name")

    def do_action(self, name):
        project_manager.current.rename(name)


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
    dialog = Gtk.MessageDialog(
        parent,
        Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        Gtk.MessageType.QUESTION,
        message_format=question
    )
    dialog.format_secondary_text(_("The file already exists in \"{0}\". "
                                   "Replacing it will overwrite its "
                                   "contents.").format(fp.dirname()))
    dialog.add_button("gtk-cancel", Gtk.ResponseType.CANCEL)
    button = Gtk.Button.new_with_mnemonic(_("_Replace"))
    button.set_can_default(True)
    button.set_image(
        Gtk.Image.new_from_icon_name(
            "gtk-save-as",
            Gtk.IconSize.BUTTON
        )
    )
    button.show()
    dialog.add_action_widget(button, Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.ACCEPT)
    return dialog


def normalize_project_filename(filename):
    """
    Assure that the project filename uses the "vbp" extension.

    :type filename: str
    :rtype: str
    """

    if filename[-4:] == '.vbp':
        return filename
    else:
        return f'{filename}.vbp'


class ExportProjectDialog(Window):

    resource = "exportproject.ui"
    include_images = False

    def __init__(self, progressbar, prjpath, iter_disk_images):
        super(Window, self).__init__()
        self.progressbar = progressbar
        if isinstance(prjpath, str):
            prjpath = filepath.FilePath(prjpath)
        self.prjpath = prjpath
        self.image_files = [
            (image.name, filepath.FilePath(image.path))
            for image in iter_disk_images
        ]
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
                row = (True, True, "gtk-directory", dirname, child)
                nodes[child.path] = model.append(parent, row)

    def append_files(self, dirpath, filenames, model, parent):
        for filename in sorted(filenames):
            child = dirpath.child(filename)
            if (child not in self.required_files | self.internal_files and
                    child.isfile() and not child.islink()):
                row = (True, True, "gtk-file", filename, child)
                model.append(parent, row)

    def build_path_tree(self, model, prjpath):
        row = (True, True, "gtk-directory", prjpath.basename(), prjpath)
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
        self.get_object("treeview1").expand_row(Gtk.TreePath(0), False)
        Window.show(self, parent_w)

    def _set_size(self, column, cellrenderer, model, itr, data=None):
        fp = model.get_value(itr, FILEPATH)
        if fp.isfile():
            cellrenderer.set_property("text", tools.fmtsize(fp.getsize()))
        else:
            size = self._calc_size(model, itr)
            if model.get_path(itr) == Gtk.TreePath((0,)):
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
                filename = normalize_project_filename(filename)
                self.get_object("filename_entry").set_text(filename)
                self.get_object("export_button").set_sensitive(True)

    def on_open_button_clicked(self, button):
        chooser = Gtk.FileChooserDialog(
            title=_("Export project"),
            action=Gtk.FileChooserAction.SAVE,
            buttons=(
                "gtk-cancel",
                Gtk.ResponseType.CANCEL,
                "gtk-save", Gtk.ResponseType.OK
            )
        )
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
        model.row_changed(
            Gtk.TreePath((0,)),
            model.get_iter(Gtk.TreePath((0,)))
        )

    def export(self, model, ancestor, filename, export=project_manager.export):
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
            filename = self.get_object('filename_entry').get_text()
            fp = filepath.FilePath(normalize_project_filename(filename))
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
    itr = model.get_iter_first()
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
        """
        :type freeze: Callable
        :type unfreeze: Callable
        :type parent: Optional[Gtk.Window]
        """

        self.freeze_parent_window = freeze
        self.unfreeze_parent_window = unfreeze
        builder = Gtk.Builder()
        resource = graphics.get_data_filename("userwait.ui")
        builder.add_from_file(resource)
        self.progressbar = builder.get_object("progressbar")
        self.wait_window = builder.get_object("UserWaitWindow")
        self.wait_window.set_transient_for(parent)
        self.wait_window.set_modal(True)

    def wait_for(self, deferred, *args):
        """
        :type deferred: Union[twisted.internet.defer.Deferred[Any], Callable]
        :type args: Tuple[Any]
        :rtype: twisted.internet.defer.Deferred[Any]
        """

        if not isinstance(deferred, defer.Deferred):
            if callable(deferred):
                deferred = defer.maybeDeferred(deferred, *args)
            else:
                raise RuntimeError('Invalid argument')
        pulse = self.start()
        deferred.addBoth(self.stop, pulse)
        return deferred

    def start(self):
        """
        :rtype: twisted.internet.task.LoopingCall
        """

        self.freeze_parent_window()
        self.wait_window.show_all()
        looping_call = task.LoopingCall(self.progressbar.pulse)
        looping_call.start(0.2, False)
        return looping_call

    def stop(self, passthru, looping_call):
        """
        :type passthru: Any
        :type looping_call: twisted.internet.task.LoopingCall
        :rtype: Any
        """

        looping_call.stop()
        self.wait_window.destroy()
        self.unfreeze_parent_window()
        return passthru


class ProgressBar:

    def __init__(self, dialog):
        self.freezer = Freezer(lambda: None, lambda: None, dialog)

    def wait_for(self, something, *args):
        return self.freezer.wait_for(something, *args)


class ProgressBarDialog(_Dialog):

    def __init__(self, deferred):
        """
        :type deferred: twisted.internet.defer.Deferred
        """

        self._deferred = deferred
        self._builder = BuilderHelper('progressbardialog.ui')
        self._builder.connect_signals(self)

    def show(self, parent):
        """
        :type parent: Gtk.Window
        :rtype: None
        """

        looping_call = task.LoopingCall(self.w.progressbar.pulse)
        looping_call.start(0.2, False)
        self._deferred.addBoth(self._stop, looping_call)
        super().show(parent)

    def _stop(self, passthru, looping_call):
        """
        :type passthru: Any
        :type looping_call: twisted.internet.task.LoopingCall
        :rtype: Any
        """

        looping_call.stop()
        self.w.ProgressBarDialog.destroy()
        return passthru


def all_paths_set(model):
    return all(path for (path,) in iter_model(model, 1))


class _HumbleImport:

    def step_1(self, dialog, model, path, extract=project_manager.import_prj):
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
        dialog.images = dict(
            (name, section["path"]) for (_, name), section
            in project.get_descriptor().get_images()
        )
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
            nlabel.props.halign = 0.0
            nlabel.props.valign = 0.5
            dlabel = Gtk.Label(dest.path)
            dlabel.set_tooltip_text(dest.path)
            dlabel.props.halign = 0.0
            dlabel.props.valign = 0.5
            dlabel.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
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
        for name, destination in saved.items():
            entry.remap_image(name, destination.path)
        for name, path in iter_model(store):
            entry.remap_image(name, path.path)
            saved[name] = path

    def rebase_all(self, project, images, entry):
        lst = []
        for name, path in images.items():
            for vmname, dev in entry.device_for_image(name):
                cow_name = "{0}_{1}.cow".format(vmname, dev)
                cow = filepath.FilePath(project.path).child(cow_name)
                if cow.exists():
                    logger.debug(log_rebase, cow=cow.path, basefile=path.path)
                    lst.append(self.rebase(path.path, cow.path))
        return defer.DeferredList(lst)

    def rebase(self, backing_file, cow, run=utils.getProcessOutputAndValue):
        args = ["rebase", "-u", "-b", backing_file, "-F", "qcow2", cow]
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
        chooser = Gtk.FileChooserDialog(
            title,
            self.window,
            action,
            (
                "gtk-cancel",
                Gtk.ResponseType.CANCEL,
                stock_id,
                Gtk.ResponseType.OK
            )
        )
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
        return self.get_filechooserdialog(
            model,
            path,
            _("Save image as..."),
            Gtk.FileChooserAction.SAVE,
            "gtk-save"
        )

    def get_map_filechooserdialog(self, model, path):
        return self.get_filechooserdialog(
            model,
            path,
            _("Map image as..."),
            Gtk.FileChooserAction.OPEN,
            "gtk-open"
        )

    # callbacks

    def on_liststore2_row_changed(self, model, path, iter):
        self.set_page_complete(complete=all_paths_set(model))

    def on_ImportDialog_prepare(self, assistant, page):
        page_num = assistant.get_current_page()
        if page_num == 0:
            pass
        elif page_num == 1:
            ws = settings.get("workspace")
            deferred = self.humble.step_1(
                self,
                self.get_object("liststore1"),
                filepath.FilePath(ws).child("vimages")
            )
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
        if name in list(prj.name for prj in project_manager):
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


class SaveProjectAsDialog(_Dialog):

    def __init__(self, brickfactory):
        self._brickfactory = brickfactory
        self._builder = BuilderHelper('saveprojectasdialog.ui')
        self._builder.connect_signals(self)
        model = self.w.projectsListstore
        for project in project_manager:
            model.append([project.name])

    def _set_error(self, tooltip):
        """
        :type tooltip: str
        :rtype: None
        """

        style_context = self.w.projectNameEntry.get_style_context()
        style_context.add_class('error')
        self.w.projectNameEntry.set_tooltip_markup(tooltip)
        self.w.okButton.set_sensitive(False)

    def _reset_error(self):
        """
        :rtype: None
        """

        style_context = self.w.projectNameEntry.get_style_context()
        style_context.remove_class('error')
        self.w.projectNameEntry.set_tooltip_text(None)
        self.w.okButton.set_sensitive(True)

    def on_projectNameEntry_changed(self, entry):
        new_project_name = entry.get_text()
        if not new_project_name:
            self._reset_error()
            self.w.okButton.set_sensitive(False)
            return
        elif new_project_name == project_manager.current.name:
            self._set_error(_('New project name is the same as previous name'))
            return
        try:
            Path(new_project_name).relative_to(settings.DEFAULT_HOME)
        except ValueError:
            # TODO: explain why name is invalid
            self._set_error(_('Invalid project name'))
        for project in project_manager:
            if new_project_name == project.name:
                tooltip = _('A project with the same name already exists')
                self._set_error(tooltip)
                break
        else:
            self._reset_error()

    def on_SaveProjectAsDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            # TODO: show progress bar
            project_manager.current.save_as(
                self.w.projectNameEntry.get_text(),
                self._brickfactory
            )
        dialog.destroy()


class RenameDialog(_Dialog):

    def __init__(self, brickfactory, brick):
        """
        :type brickfactory: virtualbricks.brickfactory.BrickFactory
        :type brick: Union[virtualbricks.bricks.Brick,
            virtualbricks.events.Event]
        :rtype: None
        """

        self._factory = brickfactory
        self._brick = brick
        self._prev_name = brick.name
        self._builder = BuilderHelper('renamedialog.ui')
        self._builder.connect_signals(self)
        self.w.brickNameEntry.set_text(brick.name)

    def _set_error(self, tooltip):
        """
        :type tooltip: str
        :rtype: None
        """

        style_context = self.w.brickNameEntry.get_style_context()
        style_context.add_class('error')
        self.w.brickNameEntry.set_tooltip_markup(tooltip)
        self.w.okButton.set_sensitive(False)

    def _reset_error(self):
        """
        :rtype: None
        """

        style_context = self.w.brickNameEntry.get_style_context()
        style_context.remove_class('error')
        self.w.brickNameEntry.set_tooltip_text(None)
        self.w.okButton.set_sensitive(True)

    def on_brickNameEntry_changed(self, entry):
        """
        Set the status of the entry based on brick name validity.

        :type entry: Gtk.Entry
        :rtype: bool
        """

        brick_name = entry.get_text()
        if not brick_name or brick_name == self._prev_name:
            self._reset_error()
            self.w.okButton.set_sensitive(False)
            return
        try:
            self._factory.normalize_name(brick_name)
            self._reset_error()
        except NameAlreadyInUseError:
            tooltip = (
                f'Name <span weight="bold">{brick_name}</span>'
                ' is already in use'
            )
            self._set_error(tooltip)
        except InvalidNameError as exc:
            self._set_error(str(exc))
        return True

    @destroy_on_exit
    def on_RenameDialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            name = self.w.brickNameEntry.get_text()
            try:
                self._brick.rename(name)
                # TODO: add debugging log
                # logger.debug(renamed)
            except errors.InvalidNameError:
                # TODO: check the difference between invalid_name and
                # brick_invalid_name
                logger.error(invalid_name, name=name)
        return True


class NewBrickDialog(_Dialog):

    def __init__(self, factory):
        """
        :type brickfactory: virtualbricks.brickfactory.BrickFactory
        :rtype: None
        """

        self._factory = factory
        self._builder = BuilderHelper('newbrick.ui')
        self._builder.connect_signals(self)
        self._type = 'switch'

    def _set_error(self, tooltip):
        """
        :type tooltip: str
        :rtype: None
        """

        style_context = self.w.brickNameEntry.get_style_context()
        style_context.add_class('error')
        self.w.brickNameEntry.set_tooltip_markup(tooltip)
        self.w.okButton.set_sensitive(False)

    def _reset_error(self):
        """
        :rtype: None
        """

        style_context = self.w.brickNameEntry.get_style_context()
        style_context.remove_class('error')
        self.w.brickNameEntry.set_tooltip_text(None)
        self.w.okButton.set_sensitive(True)

    def on_radiobutton_toggled(self, radiobutton):
        """
        :type radiobutton: Gtk.RadioButton
        :rtype: bool
        """

        if radiobutton.get_active():
            self._type = radiobutton.get_name()
        return True

    def on_brickNameEntry_changed(self, entry):
        """
        Set the status of the entry based on brick name validity.

        :type entry: Gtk.Entry
        :rtype: bool
        """

        brick_name = entry.get_text()
        if not brick_name:
            self._reset_error()
            self.w.okButton.set_sensitive(False)
            return
        try:
            self._factory.normalize_name(brick_name)
            self._reset_error()
        except NameAlreadyInUseError:
            tooltip = (
                f'Name <span weight="bold">{brick_name}</span>'
                ' is already in use'
            )
            self._set_error(tooltip)
        except InvalidNameError as exc:
            self._set_error(str(exc))
        return True

    @destroy_on_exit
    def on_NewBrickDialog_response(self, dialog, response_id):
        """
        :type dialog: Gtk.Dialog
        :type response_id: Gtk.ResponseType
        :rtype: bool
        """

        if response_id == Gtk.ResponseType.OK:
            name = self.w.brickNameEntry.get_text()
            try:
                self._factory.new_brick(self._type, name)
            except errors.InvalidNameError:
                # TODO: report the name
                logger.error(brick_invalid_name)
            else:
                logger.debug(created)
        return True


def settings_get_default(name, default=_MARKER):
    try:
        return settings.get(name)
    except NoOptionError as exc:
        if default is _MARKER:
            try:
                return DEFAULT_CONF[name]
            except KeyError:
                raise exc
        else:
            return default


def combobox_get_active_value(combobox, column, default=None):
    """
    Get current active value in combobox at the given column.

    :type combobox: Gtk.ComboBox
    :type column: int
    :type default: Any
    :rtype: Any
    """

    model = combobox.get_model()
    itr = combobox.get_active_iter()
    if itr:
        obj = model.get_value(itr, column)
        return obj
    else:
        return default


def combobox_set_active_value(combobox, value, column):
    """
    Set the current active value in the ComboBox to value if found.

    :type combobox: Gtk.ComboBox
    :type value: Any
    :type column: int
    :rtype: None
    """

    model = combobox.get_model()
    itr = model.get_iter_first()
    while itr:
        obj = model.get_value(itr, column)
        if obj == value:
            combobox.set_active_iter(itr)
            break
        itr = model.iter_next(itr)


class SettingsDialog(_Dialog):

    name = 'SettingsDialog'

    def __init__(self, virtualbricks_gui):
        """
        :type virtualbricks_gui: virtualbricks.gui.gui.VBGUI
        """

        self._setting_ksm_deferred = None
        self.virtualbricks_gui = virtualbricks_gui
        self._builder = BuilderHelper('settings.ui')
        self._builder.connect_signals(self)
        self.load_settings()

    @destroy_on_exit
    def on_SettingsDialog_response(self, dialog, response_id):
        """
        :type dialog: Gtk.Dialog
        :type response_id: Gtk.ResponseType
        """

        if response_id == Gtk.ResponseType.OK:
            self.store_settings()
        return True

    def on_SettingsDialog_delete_event(self, dialog, event):
        """
        :type dialog: Gtk.Dialog
        :type event: Gdk.Event
        """

        if self._setting_ksm_deferred is not None:
            # We are setting KSM, prevent the dialog to close.
            return True

    def on_enableKsmSwitch_active_notify(self, switch, param):
        """
        :type button: Gtk.Switch
        :type param: gobject.GParamSpec
        :rtype: bool
        """

        self.toggle_ksm()
        return False

    def toggle_ksm(self):

        def set_ksm_cb(ksm_enabled):
            """
            :type ksm_enabled: bool
            :rtype: None
            """

            self._setting_ksm_deferred = None
            self.w.enableKsmSwitch.set_sensitive(True)
            if self.w.enableKsmSwitch.get_active() != ksm_enabled:
                self.w.enableKsmSwitch.set_active(ksm_enabled)

        if self._setting_ksm_deferred is not None:
            # If we are already setting KSM, do nothing.
            return
        # disable the switch, try to change the value of KSM and reactivate
        # the switch
        self.w.enableKsmSwitch.set_sensitive(False)
        deferred = tools.set_ksm(enable=self.w.enableKsmSwitch.get_active())
        deferred.addBoth(set_ksm_cb)
        self._setting_ksm_deferred = deferred

    def load_settings(self):
        # General tab
        self.w.termEntry.set_text(settings_get_default('term'))
        self.w.sudoEntry.set_text(settings_get_default('sudo'))
        self.w.systraySwitch.set_active(settings_get_default('systray'))
        self.w.warnMissingSwitch.set_active(settings_get_default('show_missing'))
        # VDE tab
        self.w.vdePathFileChooserButton.set_current_folder(
            settings_get_default('vdepath'))
        self.w.usePythonSwitch.set_active(settings_get_default('python'))
        self.w.femalePlugsSwitch.set_active(settings_get_default('femaleplugs'))
        self.w.loopDetectionSwitch.set_active(
            settings_get_default('erroronloop'))
        # Qemu tab
        self.w.qemuPathFileChooserButton.set_current_folder(
            settings_get_default('qemupath'))
        combobox_set_active_value(self.w.cowFormatComboBox,
                                  settings_get_default('cowfmt'), 0)
        self.w.enableKsmSwitch.set_active(settings_get_default('ksm'))

    def store_settings(self):
        logger.debug(apply_settings)
        # General tab
        settings.set('term', self.w.termEntry.get_text())
        settings.set('sudo', self.w.sudoEntry.get_text())
        settings.set('systray', self.w.systraySwitch.get_active())
        settings.set('show_missing', self.w.warnMissingSwitch.get_active())
        # VDE tab
        vdepath = self.w.vdePathFileChooserButton.get_current_folder()
        if vdepath is not None:
            settings.set('vdepath', vdepath)
        settings.set('python', self.w.usePythonSwitch.get_active())
        settings.set('femaleplugs', self.w.femalePlugsSwitch.get_active())
        settings.set('erroronloop', self.w.loopDetectionSwitch.get_active())
        # Qemu tab
        qemupath = self.w.qemuPathFileChooserButton.get_current_folder()
        if qemupath is not None:
            settings.set('qemupath', qemupath)
        cowfmt = combobox_get_active_value(self.w.cowFormatComboBox, 0,
                                           DEFAULT_CONF['cowfmt'])
        settings.set('cowfmt', cowfmt)
        ksm_active = self.w.enableKsmSwitch.get_active()
        settings.set('ksm', ksm_active)
        tools.set_ksm(ksm_active)
        if self.w.systraySwitch.get_active():
            self.virtualbricks_gui.start_systray()
        else:
            self.virtualbricks_gui.stop_systray()


class AttachEventDialog(Window):

    resource = "attachevent.ui"

    def __init__(self, brick, factory):
        Window.__init__(self)
        self.brick = brick
        events = (e for e in factory.iter_events() if e.configured())
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
