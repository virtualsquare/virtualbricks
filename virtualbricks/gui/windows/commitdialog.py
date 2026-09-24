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
Old dialog to commit a COW image to its base image.

No class uses ``commitdialog.ui``: the class that loaded it,
``CommitImageDialog``, is commented out in ``virtualbricks/gui/dialogs.py``
and was replaced by ``commitimagedialog.ui``. Only the UI is converted.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk

from virtualbricks.gui.windows.base import _, _Dialog


class CommitDialog(_Dialog):
    """
    Commit the changes of a COW image to its base image, choosing the COW file
    or the disk of a virtual machine.

    The class that used this UI is commented out in
    ``virtualbricks/gui/dialogs.py``, the signal handlers are stubs.
    """

    def __init__(self):
        self.build_ui()

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``commitdialog.ui``."""

        # model1 (Gtk.ListStore)
        model1 = Gtk.ListStore(str, object)

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            can_focus=False,
            title=_("create new empty image"),
            type_hint=Gdk.WindowTypeHint.DIALOG,
        )
        dialog_vbox1 = self.dialog.get_content_area()
        dialog_vbox1.set_properties(visible=True, can_focus=False)
        dialog_action_area23 = self.dialog.get_action_area()
        dialog_action_area23.set_properties(
            visible=True,
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        commit_button = Gtk.Button(
            label=_("Commit"),
            visible=True,
            can_focus=True,
            can_default=True,
            receives_default=True,
        )
        self.dialog.add_action_widget(
            commit_button,
            Gtk.ResponseType.OK,
        )
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        commit_button.set_valign(Gtk.Align.FILL)
        dialog_action_area23.child_set(
            commit_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        close_button = Gtk.Button(
            label="gtk-close",
            visible=True,
            can_focus=True,
            can_default=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            close_button,
            Gtk.ResponseType.CLOSE,
        )
        close_button.set_valign(Gtk.Align.FILL)
        dialog_action_area23.child_set(
            close_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        dialog_vbox1.child_set(
            dialog_action_area23,
            expand=False,
            fill=True,
            pack_type=Gtk.PackType.END,
        )
        box1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
        )
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("<b>Commit COW changes to base image</b>"),
            use_markup=True,
        )
        box1.pack_start(label2, False, True, 0)
        hbox1 = Gtk.Box(visible=True, can_focus=False)
        file_radiobutton = Gtk.RadioButton(
            label=_("Commit _COW file changes"),
            visible=True,
            can_focus=True,
            receives_default=False,
            use_underline=True,
            xalign=0.5,
            active=True,
            draw_indicator=False,
        )
        hbox1.pack_start(file_radiobutton, False, True, 0)
        vm_radiobutton = Gtk.RadioButton(
            label=_("Commit _Virtual Machine changes"),
            visible=True,
            can_focus=True,
            receives_default=False,
            use_underline=True,
            xalign=0.5,
            image_position=Gtk.PositionType.RIGHT,
            draw_indicator=False,
            group=file_radiobutton,
        )
        hbox1.pack_start(vm_radiobutton, False, True, 0)
        box1.pack_start(hbox1, False, True, 0)
        hbox2 = Gtk.Box(visible=True, can_focus=False)
        cowpath_filechooser = Gtk.FileChooserButton(
            visible=True,
            can_focus=False,
            show_hidden=True,
            title=_("Select A Directory"),
        )
        hbox2.pack_start(cowpath_filechooser, True, True, 0)
        disk_combo = Gtk.ComboBox(can_focus=False, model=model1)
        renderer1 = Gtk.CellRendererText()
        disk_combo.pack_start(renderer1, False)
        disk_combo.add_attribute(renderer1, "text", 0)
        hbox2.pack_start(disk_combo, True, True, 0)
        box1.pack_start(hbox2, False, True, 0)
        cow_checkbutton = Gtk.CheckButton(
            label=_("Commit changes on private COW"),
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        box1.pack_start(cow_checkbutton, False, True, 0)
        msg_label = Gtk.Label(can_focus=False, label=_("label"))
        box1.pack_start(msg_label, False, True, 0)
        dialog_vbox1.pack_start(box1, False, True, 0)
        dialog_vbox1.reorder_child(box1, 0)
        hseparator1 = Gtk.Separator(visible=True, can_focus=False)
        dialog_vbox1.pack_start(hseparator1, False, True, 0)

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        file_radiobutton.connect(
            "toggled",
            self.on_file_radiobutton_toggled,
        )
        cowpath_filechooser.connect(
            "file-set",
            self.on_cowpath_filechooser_file_set,
        )
        disk_combo.connect("changed", self.on_disk_combo_changed)
        cow_checkbutton.connect(
            "toggled",
            self.on_cow_checkbutton_toggled,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def on_dialog_response(
        self,
        dialog: Gtk.Dialog,
        response_id: int,
        data=None,
    ) -> None:
        """
        Handler of the "response" signal of GtkDialog.

        TODO: no handler in the original class, Gtk.Builder left this signal
        unconnected.
        """

        pass

    def on_file_radiobutton_toggled(
        self,
        radio_button: Gtk.RadioButton,
        data=None,
    ) -> None:
        """
        Handler of the "toggled" signal of GtkRadioButton.

        TODO: no handler in the original class, Gtk.Builder left this signal
        unconnected.
        """

        pass

    def on_cowpath_filechooser_file_set(
        self,
        file_chooser_button: Gtk.FileChooserButton,
        data=None,
    ) -> None:
        """
        Handler of the "file-set" signal of GtkFileChooserButton.

        TODO: no handler in the original class, Gtk.Builder left this signal
        unconnected.
        """

        pass

    def on_disk_combo_changed(
        self,
        combo_box: Gtk.ComboBox,
        data=None,
    ) -> None:
        """
        Handler of the "changed" signal of GtkComboBox.

        TODO: no handler in the original class, Gtk.Builder left this signal
        unconnected.
        """

        pass

    def on_cow_checkbutton_toggled(
        self,
        check_button: Gtk.CheckButton,
        data=None,
    ) -> None:
        """
        Handler of the "toggled" signal of GtkCheckButton.

        TODO: no handler in the original class, Gtk.Builder left this signal
        unconnected.
        """

        pass
