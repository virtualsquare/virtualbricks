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
Window with the library of the disk images.
"""

import os

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from virtualbricks.virtualmachines import is_virtualmachine
from virtualbricks.gui.windows.base import (
    _,
    _Window,
    iter_tree_model,
    pango_attr_list,
)


class DisksLibraryWindow(_Window):
    """
    The library of the disk images. A stack switches between the list of the
    images and the form to edit the selected image.
    """

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
        self.build_ui()
        self._disk_image = None
        tree_view = self.images_view
        tree_selection = tree_view.get_selection()
        tree_selection.set_mode(Gtk.SelectionMode.SINGLE)
        self._on_selection_changed_handler = tree_selection.connect(
            'changed', self.on_selection_changed)
        self._tree_model = tree_model = Gtk.ListStore(object)
        for disk_image in brickfactory.iter_disk_images():
            tree_model.append([disk_image])
        tree_view.set_model(tree_model)
        self.name_column.set_cell_data_func(
            self.name_cell, self.set_cell_name)
        self.path_column.set_cell_data_func(
            self.path_cell, self.set_cell_path)
        self.used_by_column.set_cell_data_func(
            self.used_by_cell, self.set_cell_used_by, brickfactory)
        self.master_brick_column.set_cell_data_func(
            self.master_brick_cell, self.set_cell_master_brick)
        self.cows_column.set_cell_data_func(
            self.cows_cell, self.set_cell_cows, brickfactory)
        self.size_column.set_cell_data_func(
            self.size_cell, self.set_cell_size)
        brickfactory.image_added.connect(self.on_disk_image_added, tree_model)
        brickfactory.image_changed.connect(
            self.on_disk_image_changed, tree_model)
        brickfactory.image_removed.connect(
            self.on_disk_image_removed, tree_model)

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``disklibrary.ui``."""

        # description_buffer (Gtk.TextBuffer)
        self.description_buffer = Gtk.TextBuffer()

        # window (Gtk.Window)
        self.window = Gtk.Window(
            width_request=700,
            height_request=350,
            can_focus=False,
        )
        # TODO: empty Glade placeholder, nothing to create.
        self.library_stack = Gtk.Stack(visible=True, can_focus=False)
        self.image_list_box = Gtk.Box(
            visible=True,
            can_focus=False,
            border_width=2,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
        )
        scrolled_window1 = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            shadow_type=Gtk.ShadowType.IN,
        )
        self.images_view = Gtk.TreeView(visible=True, can_focus=True)
        self.name_column = Gtk.TreeViewColumn.new()
        self.name_column.set_properties(title=_("Name"))
        self.name_cell = Gtk.CellRendererText()
        self.name_column.pack_start(self.name_cell, False)
        self.images_view.append_column(self.name_column)
        self.path_column = Gtk.TreeViewColumn.new()
        self.path_column.set_properties(title=_("Path"))
        self.path_cell = Gtk.CellRendererText()
        self.path_column.pack_start(self.path_cell, False)
        self.images_view.append_column(self.path_column)
        self.used_by_column = Gtk.TreeViewColumn.new()
        self.used_by_column.set_properties(title=_("Used by"))
        self.used_by_cell = Gtk.CellRendererText()
        self.used_by_column.pack_start(
            self.used_by_cell,
            False,
        )
        self.images_view.append_column(self.used_by_column)
        self.master_brick_column = Gtk.TreeViewColumn.new()
        self.master_brick_column.set_properties(title=_("Master brick"))
        self.master_brick_cell = Gtk.CellRendererText()
        self.master_brick_column.pack_start(
            self.master_brick_cell,
            False,
        )
        self.images_view.append_column(self.master_brick_column)
        self.cows_column = Gtk.TreeViewColumn.new()
        self.cows_column.set_properties(title=_("COWs"))
        self.cows_cell = Gtk.CellRendererText()
        self.cows_column.pack_start(self.cows_cell, False)
        self.images_view.append_column(self.cows_column)
        self.size_column = Gtk.TreeViewColumn.new()
        self.size_column.set_properties(title=_("Size"))
        self.size_cell = Gtk.CellRendererText()
        self.size_column.pack_start(self.size_cell, False)
        self.images_view.append_column(self.size_column)
        scrolled_window1.add(self.images_view)
        self.image_list_box.pack_start(scrolled_window1, True, True, 0)
        button_box1 = Gtk.ButtonBox(
            visible=True,
            can_focus=False,
            spacing=4,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        self.edit_button = Gtk.Button(
            label="gtk-edit",
            visible=True,
            sensitive=False,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        button_box1.pack_start(self.edit_button, True, True, 0)
        close_button = Gtk.Button(
            label="gtk-close",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
            always_show_image=True,
        )
        button_box1.pack_start(close_button, True, True, 0)
        self.image_list_box.pack_start(button_box1, False, True, 0)
        self.library_stack.add_titled(self.image_list_box, "page0", _("page0"))
        self.edit_image_box = Gtk.Box(
            visible=True,
            can_focus=False,
            border_width=2,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
        )
        frame1 = Gtk.Frame(
            visible=True,
            can_focus=False,
            label_xalign=0.019999999552965164,
            shadow_type=Gtk.ShadowType.NONE,
        )
        box1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
        )
        grid1 = Gtk.Grid(
            visible=True,
            can_focus=False,
            row_spacing=2,
            column_spacing=5,
        )
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("File path"),
        )
        grid1.attach(label1, 0, 0, 1, 1)
        self.path_chooser = Gtk.FileChooserButton(
            visible=True,
            can_focus=False,
            hexpand=True,
            title="",
        )
        grid1.attach(self.path_chooser, 1, 0, 1, 1)
        label2 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Name"),
        )
        grid1.attach(label2, 0, 1, 1, 1)
        self.name_entry = Gtk.Entry(visible=True, can_focus=True)
        grid1.attach(self.name_entry, 1, 1, 1, 1)
        box1.pack_start(grid1, False, True, 0)
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            halign=Gtk.Align.START,
            label=_("Description"),
        )
        box1.pack_start(label3, False, True, 0)
        scrolled_window2 = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            shadow_type=Gtk.ShadowType.IN,
        )
        text_view1 = Gtk.TextView(
            visible=True,
            can_focus=True,
            buffer=self.description_buffer,
        )
        scrolled_window2.add(text_view1)
        box1.pack_start(scrolled_window2, True, True, 0)
        frame1.add(box1)
        label4 = Gtk.Label(
            visible=True,
            can_focus=False,
            margin_top=5,
            margin_bottom=5,
            label=_("Configure disk image"),
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
            ),
        )
        frame1.set_label_widget(label4)
        self.edit_image_box.pack_start(frame1, True, True, 0)
        button_box2 = Gtk.ButtonBox(
            visible=True,
            can_focus=False,
            spacing=4,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        cancel_button = Gtk.Button(
            label="gtk-cancel",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        button_box2.pack_start(cancel_button, True, True, 0)
        button_box2.set_child_secondary(cancel_button, True)
        remove_button = Gtk.Button(
            label="gtk-remove",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        button_box2.pack_start(remove_button, True, True, 0)
        save_button = Gtk.Button(
            label="gtk-save",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        button_box2.pack_start(save_button, True, True, 0)
        self.edit_image_box.pack_start(button_box2, False, True, 0)
        self.library_stack.add_titled(self.edit_image_box, "page1", _("page1"))
        self.window.add(self.library_stack)

        # Signals
        self.images_view.connect(
            "row-activated",
            self.on_images_view_row_activated,
        )
        self.edit_button.connect("clicked", self.on_edit_button_clicked)
        close_button.connect("clicked", self.on_close_button_clicked)
        self.path_chooser.connect(
            "file-set",
            self.on_path_chooser_file_set,
        )
        cancel_button.connect("clicked", self.on_cancel_button_clicked)
        remove_button.connect("clicked", self.on_remove_button_clicked)
        save_button.connect("clicked", self.on_save_button_clicked)

    def get_root_widget(self) -> Gtk.Window:
        return self.window

    def _show_edit_screen(self, disk_image):
        """
        :type disk_image: virtualbricks.virtualmachines.Image
        """

        self._disk_image = disk_image
        self.path_chooser.set_filename(disk_image.path)
        self.name_entry.set_text(disk_image.get_name())
        self.description_buffer.set_text(disk_image.get_description())
        self.library_stack.set_visible_child(self.edit_image_box)

    def _hide_edit_screen(self):
        self._disk_image = None
        self.library_stack.set_visible_child(self.image_list_box)

    def on_selection_changed(self, tree_selection):
        """
        Show or hide the edit button if a disk image has been selected.

        :type tree_selection: Gtk.TreeSelection
        """

        tree_model, itr = tree_selection.get_selected()
        self.edit_button.set_sensitive(itr is not None)
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

    def on_images_view_row_activated(self, tree_view, path, column):
        """
        :type tree_view: Gtk.TreeView
        :type path: Gtk.TreePath
        :type column: Gtk.TreeViewColumn
        """

        model = tree_view.get_model()
        disk_image = model.get_value(model.get_iter(path), 0)
        self._show_edit_screen(disk_image)
        return True

    def on_path_chooser_file_set(self, file_choser_button):
        filename = file_choser_button.get_filename()
        if filename is not None and self.name_entry.get_text() == '':
            self.name_entry.set_text(os.path.basename(filename))
        return True

    def on_cancel_button_clicked(self, button):
        self._hide_edit_screen()
        return True

    def on_remove_button_clicked(self, button):
        assert self._disk_image is not None
        # TODO: ask for confirmation
        self._brickfactory.remove_disk_image(self._disk_image)
        self._hide_edit_screen()
        return True

    def on_save_button_clicked(self, button):
        assert self._disk_image is not None
        # self._disk_image.set_path(self.path_chooser.get_filename())
        self._disk_image.path = self.path_chooser.get_filename()
        self._disk_image.set_name(self.name_entry.get_text())
        description = self.description_buffer.get_property('text')
        self._disk_image.set_description(description)
        self._hide_edit_screen()
        return True

    def on_edit_button_clicked(self, button):
        tree_selection = self.images_view.get_selection()
        tree_model, itr = tree_selection.get_selected()
        assert itr is not None
        disk_image = tree_model.get_value(itr, 0)
        self._show_edit_screen(disk_image)
        return True

    def on_close_button_clicked(self, button):
        self.window.destroy()
        return True

    def on_destroy(self, window=None):
        self._brickfactory.image_added.disconnect(
            self.on_disk_image_added, self._tree_model)
        self._brickfactory.image_changed.disconnect(
            self.on_disk_image_changed, self._tree_model)
        self._brickfactory.image_removed.disconnect(
            self.on_disk_image_removed, self._tree_model)
        return True
