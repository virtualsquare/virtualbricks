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
Dialog to commit the changes of a COW image to its base image.
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango

from virtualbricks import log
from virtualbricks.spawn import qemu_commit_image
from virtualbricks.virtualmachines import is_virtualmachine
from virtualbricks.gui.windows.base import _, _Dialog, pango_attr_list
from virtualbricks.gui.windows.progressbardialog import ProgressBarDialog


logger = log.Logger()

not_implemented = log.Event("Not implemented")


def disks_of(brick):
    if is_virtualmachine(brick):
        for dev in 'hda', 'hdb', 'hdc', 'hdd', 'fda', 'fdb', 'mtdblock':
            yield brick.config[dev]


class CommitImageDialog(_Dialog):
    """
    Commit the changes of a COW image to its base image. A stack switches
    between the choice of a COW file and the choice of a virtual machine disk.
    """

    @staticmethod
    def set_cell_title(tree_column, cell, tree_model, tree_itr):
        disk = tree_model.get_value(tree_itr, 0)
        cell.set_property('text', f'{disk.device} on {disk.vm.get_name()}')
        return True

    def __init__(self, brickfactory):
        self.build_ui()
        self._tree_model = tree_model = Gtk.ListStore(object)
        for brick in filter(is_virtualmachine, brickfactory.iter_bricks()):
            for disk in (disk for disk in disks_of(brick) if disk.is_cow()):
                tree_model.append([disk])
        self.disks_combo.set_model(tree_model)
        self.disks_combo.set_cell_data_func(
            self.disk_cell, self.set_cell_title)

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``commitimagedialog.ui``."""

        # image1 (Gtk.Image)
        image1 = Gtk.Image(
            visible=True,
            can_focus=False,
            icon_name="system-run",
        )

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            width_request=350,
            height_request=200,
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
        close_button = Gtk.Button(
            label=_("Close"),
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
            expand=True,
            fill=True,
        )
        commit_button = Gtk.Button(
            label=_("Commit"),
            visible=True,
            can_focus=True,
            can_default=True,
            receives_default=True,
            image=image1,
            always_show_image=True,
        )
        self.dialog.add_action_widget(
            commit_button,
            Gtk.ResponseType.APPLY,
        )
        commit_button.set_valign(Gtk.Align.FILL)
        action_area.child_set(
            commit_button,
            pack_type=Gtk.PackType.START,
            expand=True,
            fill=True,
        )
        content_area.child_set(action_area, expand=False, fill=False)
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            margin_top=5,
            margin_bottom=4,
            label=_("Commit COW changes"),
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
            ),
        )
        content_area.pack_start(label1, False, True, 0)
        content_area.reorder_child(label1, 0)
        stack_switcher1 = Gtk.StackSwitcher(
            can_focus=False,
            halign=Gtk.Align.CENTER,
        )
        content_area.pack_start(stack_switcher1, False, True, 0)
        content_area.reorder_child(stack_switcher1, 1)
        self.action_stack = Gtk.Stack(visible=True, can_focus=False)
        self.cow_chooser = Gtk.FileChooserButton(
            visible=True,
            can_focus=False,
            valign=Gtk.Align.START,
            title="",
        )
        self.action_stack.add_titled(
            self.cow_chooser,
            "commit_cow",
            _("Commit COW file changes"),
        )
        box1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        self.disks_combo = Gtk.ComboBox(visible=True, can_focus=False)
        self.disk_cell = Gtk.CellRendererText()
        self.disks_combo.pack_start(self.disk_cell, False)
        box1.pack_start(self.disks_combo, False, True, 0)
        check_button1 = Gtk.CheckButton(
            label=_("Commit changes on private COW"),
            visible=True,
            can_focus=True,
            receives_default=False,
            draw_indicator=True,
        )
        box1.pack_start(check_button1, False, True, 0)
        label2 = Gtk.Label(visible=True, can_focus=False, label=_("label"))
        box1.pack_start(label2, False, True, 0)
        self.action_stack.add_titled(
            box1,
            "commit_vm",
            _("Commit virtual machine changes"),
        )
        content_area.pack_start(self.action_stack, True, True, 0)
        content_area.reorder_child(self.action_stack, 2)

        # Need the complete widget tree:
        # references to objects created later, default and focus widgets.
        commit_button.grab_default()
        stack_switcher1.set_property("stack", self.action_stack)

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        self.disks_combo.connect("changed", self.on_disks_combo_changed)

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def do_commit_cow(self):
        filepath = self.cow_chooser.get_filename()
        assert filepath is not None
        deferred = qemu_commit_image(filepath)
        ProgressBarDialog(deferred).show(self.dialog)
        # return deferred

    def do_commit_vm(self):
        # TODO: logger.warning(commit_vm_not_implemented)
        logger.warn(not_implemented)

    def on_disks_combo_changed(self, combobox):
        # itr = combobox.get_active_iter()
        # tree_model = combobox.get_model()
        # if itr is not None:
        #     selected_disk = tree_model.get_value(itr, 0)
        return True

    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.APPLY:
            action_name = self.action_stack.get_visible_child_name()
            action = getattr(self, f'do_{action_name}')
            action()
        elif response_id == Gtk.ResponseType.CLOSE:
            dialog.destroy()
        return True
