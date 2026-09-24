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

"""
Dialog to add an existing disk image to the library.
"""

from contextlib import contextmanager
from os.path import basename, splitext

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import GObject, Gdk, Gtk, Pango

from virtualbricks.errors import InvalidNameError, NameAlreadyInUseError
from virtualbricks.gui.windows.base import (
    _,
    _Dialog,
    destroy_on_exit,
    pango_attr_list,
)


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
    """
    Add an existing disk image to the library: the image file, its name and an
    optional description.
    """

    def __init__(self, brickfactory):
        self._brickfactory = brickfactory
        self._name_set = False
        self._description_set = False
        self.build_ui()
        self._block_image_name_entry_changed = block_signal_handler(
            self.image_name_entry,
            self.image_name_entry.connect(
                "changed", self.on_image_name_entry_changed
            ),
        )
        self._block_description_textbuffer_changed = block_signal_handler(
            self.description_buffer,
            self.description_buffer.connect(
                "changed", self.on_description_buffer_changed
            ),
        )
        self._image_path_error = None
        self._name_error = None

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``loadimagedialog.ui``."""

        # description_buffer (Gtk.TextBuffer)
        self.description_buffer = Gtk.TextBuffer()

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            width_request=450,
            height_request=300,
            can_focus=False,
            modal=True,
            destroy_with_parent=True,
            type_hint=Gdk.WindowTypeHint.DIALOG,
        )
        # TODO: empty Glade placeholder, nothing to create.
        content_area = self.dialog.get_content_area()
        content_area.set_properties(
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
        )
        action_area = self.dialog.get_action_area()
        action_area.set_properties(
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        cancel_button = Gtk.Button(
            label=_("Cancel"),
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        self.dialog.add_action_widget(
            cancel_button,
            Gtk.ResponseType.CANCEL,
        )
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        cancel_button.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            cancel_button,
            pack_type=Gtk.PackType.START,
            expand=True,
            fill=True,
        )
        self.ok_button = Gtk.Button(
            label=_("OK"),
            name="okButton",
            visible=True,
            sensitive=False,
            can_focus=True,
            can_default=True,
            receives_default=True,
            always_show_image=True,
        )
        self.dialog.add_action_widget(
            self.ok_button,
            Gtk.ResponseType.OK,
        )
        self.ok_button.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            self.ok_button,
            pack_type=Gtk.PackType.START,
            expand=True,
            fill=True,
        )
        content_area.child_set(action_area, expand=False, fill=False)
        box1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=5,
        )
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Load disk image"),
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
            ),
        )
        box1.pack_start(label1, False, True, 0)
        self.image_chooser = Gtk.FileChooserButton(
            visible=True,
            can_focus=False,
            create_folders=False,
            title="",
        )
        box1.pack_start(self.image_chooser, False, True, 0)
        box2 = Gtk.Box(visible=True, can_focus=False)
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            margin_right=10,
            label=_("Name"),
        )
        box2.pack_start(label2, False, True, 0)
        self.image_name_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            placeholder_text=_("Image name"),
        )
        box2.pack_start(self.image_name_entry, True, True, 0)
        box1.pack_start(box2, False, True, 0)
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            margin_top=2,
            label=_("Description"),
        )
        box1.pack_start(label3, False, True, 0)
        scrolled_window1 = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            shadow_type=Gtk.ShadowType.IN,
        )
        text_view1 = Gtk.TextView(
            visible=True,
            can_focus=True,
            buffer=self.description_buffer,
        )
        scrolled_window1.add(text_view1)
        box1.pack_start(scrolled_window1, True, True, 0)
        content_area.pack_start(box1, True, True, 0)

        # Need the complete widget tree:
        # default and focus widgets.
        self.ok_button.grab_default()

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        self.image_chooser.connect(
            "file-set",
            self.on_image_chooser_file_set,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def _load_desc(self, pathname):
        try:
            with open(pathname + ".vbdescr") as fd:
                return fd.read()
        except FileNotFoundError:
            return ""

    def _set_error(self):
        """
        :rtype: None
        """

        file_chooser_button = self.image_chooser
        image_name_entry = self.image_name_entry
        if self._image_path_error is not None:
            file_chooser_button.get_style_context().add_class("error")
            file_chooser_button.set_tooltip_markup(self._image_path_error)
        else:
            file_chooser_button.get_style_context().remove_class("error")
            file_chooser_button.set_tooltip_text(None)
        if self._name_error:
            image_name_entry.get_style_context().add_class("error")
            image_name_entry.set_tooltip_markup(self._name_error)
        else:
            image_name_entry.get_style_context().remove_class("error")
            image_name_entry.set_tooltip_markup(None)
        if self._image_path_error is not None or self._name_error is not None:
            self.ok_button.set_sensitive(False)
        else:
            self.ok_button.set_sensitive(
                file_chooser_button.get_filename() is not None
                and image_name_entry.get_text() != ""
            )

    def _check_name(self):
        image_name = self.image_name_entry.get_text()
        if image_name == "":
            self._name_error = None
        else:
            try:
                self._brickfactory.normalize_name(image_name)
                self._name_error = None
            except NameAlreadyInUseError:
                self._name_error = (
                    f'Name <span weight="bold">{image_name}</span>'
                    " is already in use"
                )
            except InvalidNameError as exc:
                self._name_error = str(exc)

    def on_image_chooser_file_set(self, filechooserbutton):
        """
        :type filechooserbutton: Gtk.FileChooserButton
        :rtype: bool
        """

        filepath = filechooserbutton.get_filename()
        if filepath is None:
            self._image_path_error = None
            return True
        if self._brickfactory.get_image_by_path(filepath) is not None:
            self._image_path_error = "Image is already in use"
        else:
            self._image_path_error = None
        if not self._name_set:
            image_name, ext = splitext(basename(filepath))
            with self._block_image_name_entry_changed():
                self.image_name_entry.set_text(image_name)
            self._check_name()
        if not self._description_set:
            with self._block_description_textbuffer_changed():
                self.description_buffer.set_text(self._load_desc(filepath))
        self._set_error()
        return True

    def on_image_name_entry_changed(self, entry):
        """
        :type entry: Gtk.Entry
        :rtype: bool
        """

        self._name_set = entry.get_text() != ""
        self._check_name()
        self._set_error()
        return True

    def on_description_buffer_changed(self, textbuffer):
        """
        :type textbuffer: Gtk.TextBuffer
        :rtype: bool
        """

        self._description_set = textbuffer.get_property("text") != ""
        return True

    @destroy_on_exit
    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            name = self.image_name_entry.get_text()
            description = self.description_buffer.get_property("text")
            filepath = self.image_chooser.get_filename()
            self._brickfactory.new_disk_image(name, filepath, description)
        return True
