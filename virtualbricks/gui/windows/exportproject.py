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
Dialog to export a project to a file.
"""

import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk
from twisted.python import filepath

from virtualbricks import settings, tools
from virtualbricks.project import manager as project_manager
from virtualbricks.gui.windows.base import _, destroy_on_exit, Window


def gather_selected(model, parent, workspace, lst):
    itr = model.iter_children(parent)
    while itr:
        fp = model[itr][FILEPATH]
        if model[itr][SELECTED] and fp.isfile():
            lst.append(os.path.join(*fp.segmentsFrom(workspace)))
        else:
            gather_selected(model, itr, workspace, lst)
        itr = model.iter_next(itr)


SELECTED, ACTIVABLE, TYPE, NAME, FILEPATH = range(5)


def ConfirmOverwriteDialog(fp, parent):
    question = _(
        'A file named "{0}" already exists.  Do you want to ' "replace it?"
    ).format(fp.basename())
    dialog = Gtk.MessageDialog(
        parent,
        Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        Gtk.MessageType.QUESTION,
        message_format=question,
    )
    dialog.format_secondary_text(
        _(
            'The file already exists in "{0}". '
            "Replacing it will overwrite its "
            "contents."
        ).format(fp.dirname())
    )
    dialog.add_button("gtk-cancel", Gtk.ResponseType.CANCEL)
    button = Gtk.Button.new_with_mnemonic(_("_Replace"))
    button.set_can_default(True)
    button.set_image(
        Gtk.Image.new_from_icon_name("gtk-save-as", Gtk.IconSize.BUTTON)
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

    if filename[-4:] == ".vbp":
        return filename
    else:
        return f"{filename}.vbp"


class ExportProjectDialog(Window):
    """
    Export the current project to a ``.vbp`` file. The tree lists the files of
    the project to include; the disk images can be included too.
    """

    include_images = False

    def __init__(self, progressbar, prjpath, iter_disk_images):
        Window.__init__(self)
        self.progressbar = progressbar
        if isinstance(prjpath, str):
            prjpath = filepath.FilePath(prjpath)
        self.prjpath = prjpath
        self.image_files = [
            (image.name, filepath.FilePath(image.path))
            for image in iter_disk_images
        ]
        self.required_files = set(
            [prjpath.child(".project"), prjpath.child("README")]
        )
        self.internal_files = set(
            [
                prjpath.child("vde.dot"),
                prjpath.child("vde_topology.plain"),
                prjpath.child(".images"),
            ]
        )

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``exportproject.ui``."""

        # image1 (Gtk.Image)
        image1 = Gtk.Image(visible=True, can_focus=False, stock="gtk-ok")

        # files_store (Gtk.TreeStore)
        self.files_store = Gtk.TreeStore(bool, bool, str, str, object)

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            width_request=400,
            height_request=300,
            can_focus=False,
            border_width=2,
            title=_("Export project"),
            type_hint=Gdk.WindowTypeHint.DIALOG,
        )
        dialog_vbox1 = self.dialog.get_content_area()
        dialog_vbox1.set_properties(
            visible=True,
            can_focus=False,
            spacing=2,
        )
        dialog_action_area1 = self.dialog.get_action_area()
        dialog_action_area1.set_properties(
            visible=True,
            can_focus=False,
            layout_style=Gtk.ButtonBoxStyle.END,
        )
        cancel_button = Gtk.Button(
            label="gtk-cancel",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        self.dialog.add_action_widget(
            cancel_button,
            Gtk.ResponseType.CANCEL,
        )
        # add_action_widget() packs the button at the end and aligns it to
        # the baseline, restore the Glade packing and alignment.
        cancel_button.set_valign(Gtk.Align.FILL)
        dialog_action_area1.child_set(
            cancel_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        self.export_button = Gtk.Button(
            label=_("Export"),
            visible=True,
            sensitive=False,
            can_focus=True,
            receives_default=True,
            image=image1,
        )
        self.dialog.add_action_widget(
            self.export_button,
            Gtk.ResponseType.OK,
        )
        self.export_button.set_valign(Gtk.Align.FILL)
        dialog_action_area1.child_set(
            self.export_button,
            pack_type=Gtk.PackType.START,
            expand=False,
            fill=False,
        )
        dialog_vbox1.child_set(
            dialog_action_area1,
            expand=False,
            fill=True,
            pack_type=Gtk.PackType.END,
        )
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Choose the files to include in the project"),
        )
        dialog_vbox1.pack_start(label3, False, True, 3)
        dialog_vbox1.reorder_child(label3, 0)
        scrolledwindow1 = Gtk.ScrolledWindow(visible=True, can_focus=True)
        self.files_view = Gtk.TreeView(
            visible=True,
            can_focus=True,
            model=self.files_store,
            headers_visible=False,
        )
        treeviewcolumn1 = Gtk.TreeViewColumn.new()
        treeviewcolumn1.set_properties(title=_("Name"))
        self.selected_cell = Gtk.CellRendererToggle()
        treeviewcolumn1.pack_start(self.selected_cell, False)
        treeviewcolumn1.add_attribute(
            self.selected_cell,
            "activatable",
            1,
        )
        treeviewcolumn1.add_attribute(
            self.selected_cell,
            "active",
            0,
        )
        self.icon_cell = Gtk.CellRendererPixbuf()
        treeviewcolumn1.pack_start(self.icon_cell, False)
        treeviewcolumn1.add_attribute(
            self.icon_cell,
            "stock-id",
            2,
        )
        filename_cellrenderer = Gtk.CellRendererText()
        treeviewcolumn1.pack_start(filename_cellrenderer, False)
        treeviewcolumn1.add_attribute(
            filename_cellrenderer,
            "text",
            3,
        )
        self.files_view.append_column(treeviewcolumn1)
        self.size_column = Gtk.TreeViewColumn.new()
        self.size_column.set_properties(title=_("Size"))
        self.size_cell = Gtk.CellRendererText()
        self.size_column.pack_start(self.size_cell, False)
        self.files_view.append_column(self.size_column)
        scrolledwindow1.add(self.files_view)
        dialog_vbox1.pack_start(scrolledwindow1, True, True, 0)
        dialog_vbox1.reorder_child(scrolledwindow1, 1)
        hbox1 = Gtk.Box(visible=True, can_focus=False, spacing=6)
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("File:"),
        )
        hbox1.pack_start(label1, False, True, 0)
        self.filename_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            primary_icon_activatable=False,
            secondary_icon_activatable=False,
        )
        hbox1.pack_start(self.filename_entry, True, True, 0)
        open_button = Gtk.Button(
            label="gtk-open",
            visible=True,
            can_focus=True,
            receives_default=True,
            use_stock=True,
        )
        hbox1.pack_start(open_button, False, True, 0)
        dialog_vbox1.pack_start(hbox1, False, True, 0)
        include_images_check = Gtk.CheckButton(
            label=_("Include base disk images (slow)"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0.5,
            draw_indicator=True,
        )
        dialog_vbox1.pack_start(
            include_images_check,
            False,
            True,
            0,
        )

        # Signals
        self.dialog.connect(
            "response",
            self.on_dialog_response,
        )
        self.filename_entry.connect("changed", self.on_filename_entry_changed)
        open_button.connect("clicked", self.on_open_button_clicked)
        include_images_check.connect(
            "toggled",
            self.on_include_images_check_toggled,
        )

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

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
            if (
                child not in self.required_files | self.internal_files
                and child.isfile()
                and not child.islink()
            ):
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
        model = self.files_store
        self.build_path_tree(model, self.prjpath)
        pixbuf_cr = self.icon_cell
        pixbuf_cr.set_property("stock-size", Gtk.IconSize.MENU)
        size_c = self.size_column
        size_cr = self.size_cell
        size_c.set_cell_data_func(size_cr, self._set_size)
        self.selected_cell.connect(
            "toggled", self.on_selected_cell_toggled, model
        )
        self.files_view.expand_row(Gtk.TreePath(0), False)
        Window.show(self, parent_w)

    def _set_size(self, column, cellrenderer, model, itr, data=None):
        fp = model.get_value(itr, FILEPATH)
        if fp.isfile():
            cellrenderer.set_property("text", tools.fmtsize(fp.getsize()))
        else:
            size = self._calc_size(model, itr)
            if model.get_path(itr) == Gtk.TreePath((0,)):
                size += sum(
                    fp.getsize() for fp in self.required_files if fp.exists()
                )
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

    def on_selected_cell_toggled(self, cellrenderer, path, model):
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
                self.export_button.set_sensitive(False)
            elif os.path.exists(filename) and not os.path.isfile(filename):
                dialog.unselect_all()
                self.export_button.set_sensitive(False)
            else:
                filename = normalize_project_filename(filename)
                self.filename_entry.set_text(filename)
                self.export_button.set_sensitive(True)

    def on_open_button_clicked(self, button):
        chooser = Gtk.FileChooserDialog(
            title=_("Export project"),
            action=Gtk.FileChooserAction.SAVE,
            buttons=(
                "gtk-cancel",
                Gtk.ResponseType.CANCEL,
                "gtk-save",
                Gtk.ResponseType.OK,
            ),
        )
        vbp = Gtk.FileFilter()
        vbp.add_pattern("*.vbp")
        chooser.set_filter(vbp)
        chooser.connect("response", self.on_filechooser_response)
        chooser.set_transient_for(self.get_root_widget())
        chooser.set_current_name(self.filename_entry.get_text())
        chooser.show()

    def on_filename_entry_changed(self, entry):
        self.export_button.set_sensitive(bool(entry.get_text()))

    def on_include_images_check_toggled(self, checkbutton):
        self.include_images = checkbutton.get_active()
        model = self.files_store
        model.row_changed(
            Gtk.TreePath((0,)), model.get_iter(Gtk.TreePath((0,)))
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
        model = self.files_store
        ancestor = filepath.FilePath(settings.VIRTUALBRICKS_HOME)
        self.progressbar.wait_for(self.export(model, ancestor, filename))

    def on_dialog_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.OK:
            filename = self.filename_entry.get_text()
            fp = filepath.FilePath(normalize_project_filename(filename))
            if fp.exists():
                cdialog = ConfirmOverwriteDialog(fp, dialog)
                cdialog.connect(
                    "response", self.on_confirm_response, dialog, fp.path
                )
                cdialog.show()
            else:
                dialog.destroy()
                self.do_export(fp.path)
        else:
            dialog.destroy()
