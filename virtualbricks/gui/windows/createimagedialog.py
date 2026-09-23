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
Dialog to create a new empty disk image.
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango

from virtualbricks import log
from virtualbricks.spawn import qemu_img
from virtualbricks.gui.windows.base import _, _Dialog, pango_attr_list


logger = log.Logger()

img_create_err = log.Event("Error on creating image")
img_create = log.Event("Creating image...")


class QemuCreateArgs:

    def __init__(self, name, pathname, fileformat, size):
        self.name = name
        self.pathname = pathname
        self.fileformat = fileformat
        self.size = size


class CreateImageDialog(_Dialog):
    """
    Create a new empty disk image with ``qemu-img``: name, folder, format and
    size.
    """

    def __init__(self, gui, factory):
        self.gui = gui
        # self.factory = factory
        self.build_ui()

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``createimagedialog.ui``."""

        # adjustment1 (Gtk.Adjustment)
        adjustment1 = Gtk.Adjustment(
            lower=1,
            upper=1000000,
            value=1,
            step_increment=1,
            page_increment=100,
        )

        # imageTypeListStore (Gtk.ListStore)
        image_type_list_store = Gtk.ListStore(str)
        image_type_list_store.append([_("Auto")])
        image_type_list_store.append([_("raw")])
        image_type_list_store.append([_("qcow")])
        image_type_list_store.append([_("qcow2")])
        image_type_list_store.append([_("cow")])
        image_type_list_store.append([_("vmdk")])
        image_type_list_store.append([_("cloop")])

        # sizeSuffixListStore (Gtk.ListStore)
        size_suffix_list_store = Gtk.ListStore(str)
        size_suffix_list_store.append([_("Kb")])
        size_suffix_list_store.append([_("Mb")])
        size_suffix_list_store.append([_("Gb")])

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            width_request=300,
            can_focus=False,
            title=_("Create new Image"),
            modal=True,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
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
        close_button = Gtk.Button(
            label="Close",
            visible=True,
            can_focus=True,
            receives_default=True,
        )
        self.dialog.add_action_widget(
            close_button,
            Gtk.ResponseType.CLOSE,
        )
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        close_button.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            close_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        self.create_button = Gtk.Button(
            label="Create",
            visible=True,
            sensitive=False,
            can_focus=True,
            can_default=True,
            receives_default=True,
        )
        self.dialog.add_action_widget(
            self.create_button,
            Gtk.ResponseType.OK,
        )
        self.create_button.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            self.create_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        content_area.child_set(action_area, expand=False, fill=False)
        grid1 = Gtk.Grid(
            visible=True,
            can_focus=False,
            row_spacing=3,
            column_spacing=6,
        )
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Name"),
            xalign=0,
        )
        grid1.attach(label1, 0, 4, 1, 1)
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Format"),
            xalign=0,
        )
        grid1.attach(label2, 0, 5, 1, 1)
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Size"),
            xalign=0,
        )
        grid1.attach(label3, 0, 6, 1, 1)
        self.image_name_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            hexpand=True,
        )
        grid1.attach(self.image_name_entry, 1, 4, 2, 1)
        self.format_combo = Gtk.ComboBox(
            visible=True,
            can_focus=False,
            model=image_type_list_store,
            id_column=0,
        )
        cell_renderer_text1 = Gtk.CellRendererText()
        self.format_combo.pack_start(cell_renderer_text1, False)
        self.format_combo.add_attribute(cell_renderer_text1, "text", 0)
        grid1.attach(self.format_combo, 1, 5, 2, 1)
        self.size_spin = Gtk.SpinButton(
            visible=True,
            can_focus=True,
            hexpand=True,
            adjustment=adjustment1,
            numeric=True,
        )
        grid1.attach(self.size_spin, 1, 6, 1, 1)
        self.unit_combo = Gtk.ComboBox(
            visible=True,
            can_focus=False,
            model=size_suffix_list_store,
            active=2,
            id_column=0,
        )
        cell_renderer_text2 = Gtk.CellRendererText()
        self.unit_combo.pack_start(cell_renderer_text2, False)
        self.unit_combo.add_attribute(cell_renderer_text2, "text", 0)
        grid1.attach(self.unit_combo, 2, 6, 1, 1)
        separator1 = Gtk.Separator(
            visible=True,
            can_focus=False,
            margin_top=2,
            margin_bottom=2,
        )
        grid1.attach(separator1, 0, 3, 3, 1)
        label4 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Target folder for the new image"),
            xalign=0,
        )
        grid1.attach(label4, 0, 1, 3, 1)
        label5 = Gtk.Label(
            visible=True,
            can_focus=False,
            margin_top=6,
            margin_bottom=6,
            hexpand=True,
            label=_("Create new empty disk image"),
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
            ),
        )
        grid1.attach(label5, 0, 0, 3, 1)
        self.folder_chooser = Gtk.FileChooserButton(
            visible=True,
            can_focus=False,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            title=_("Select a directory"),
        )
        grid1.attach(self.folder_chooser, 0, 2, 3, 1)
        content_area.pack_start(grid1, True, True, 0)

        # Need the complete widget tree:
        # default and focus widgets.
        self.create_button.grab_default()

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        self.image_name_entry.connect("changed", self.on_image_name_entry_changed)
        self.format_combo.connect("changed", self.on_format_combo_changed)
        self.size_spin.connect(
            "value-changed",
            self.on_size_spin_value_changed,
        )
        self.unit_combo.connect("changed", self.on_unit_combo_changed)
        self.folder_chooser.connect(
            "file-set",
            self.on_folder_chooser_file_set,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def _get_create_image_args(self):
        name = self.image_name_entry.get_text()
        if not name:
            raise ValueError("empty name")
        folder = self.folder_chooser.get_filename()
        if folder is None:
            raise ValueError("folder not chosen")
        fileformat = self._get_fileformat()
        pathname = f"{folder}/{name}.{fileformat}"
        size = self._get_size()
        return QemuCreateArgs(name, pathname, fileformat, size)

    def _get_fileformat(self):
        model = self.format_combo.get_model()
        itr = self.format_combo.get_active_iter()
        if itr is not None:
            fileformat = model[itr][0]
            if fileformat == "Auto":
                fileformat = "raw"
            return fileformat
        else:
            raise ValueError('invalid fileformat')

    def _get_size(self):
        size = self.size_spin.get_value_as_int()
        # Get size unit and remove the last character "B"
        # because qemu-img want k, M, G or T suffixes.
        model = self.unit_combo.get_model()
        itr = self.unit_combo.get_active_iter()
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
        self.create_button.set_sensitive(enable)

    def create_image(self, args):
        done_deferred = qemu_img([
            'create', '-f', args.fileformat, args.pathname, args.size
        ])
        done_deferred.addCallback(lambda stdout: (args.name, args.pathname))
        logger.log_failure(done_deferred, img_create_err)
        return done_deferred

    # Events

    def on_image_name_entry_changed(self, *args):
        self._toggle_dialog_response()
        return True

    def on_folder_chooser_file_set(self, *args):
        self._toggle_dialog_response()
        return True

    def on_format_combo_changed(self, *args):
        self._toggle_dialog_response()
        return True

    def on_size_spin_value_changed(self, *args):
        self._toggle_dialog_response()
        return True

    def on_unit_combo_changed(self, *args):
        self._toggle_dialog_response()
        return True

    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            logger.info(img_create)
            args = self._get_create_image_args()
            self.gui.user_wait_action(self.create_image(args))
        dialog.destroy()
