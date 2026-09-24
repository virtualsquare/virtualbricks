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
Assistant to import a project from a file.
"""

import errno
import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango
import twisted
from twisted.internet import defer, error, utils
from twisted.python import filepath
from twisted.logger import Logger

from virtualbricks.config import projectfile, settings
from virtualbricks.project import manager as project_manager
from virtualbricks.gui.windows.base import _, pango_attr_list, Window
from virtualbricks.gui.windows.userwait import ProgressBar

if twisted.__version__ >= "15.0.2":
    # This is an ugly hack but virtualbricks is not really ready for
    # Python3
    def mktempfn():
        return filepath._secureEnoughString(project_manager.path)

else:

    def mktempfn():
        return filepath._secureEnoughString()


logger = Logger()

extract_err = "Error on import project"
log_rebase = "Rebasing {cow} to {basefile}"
rebase_error = "Error on rebase"
image_not_exists = (
    "Cannot save image to {destination}, file does " "not exists: {source}"
)
invalid_step_assitant = "Assistant cannot handle step {num}"
project_extracted = "Project has beed extracted in {path}"
removing_temporary_project = "Remove temporary files in {path}"
error_on_import_project = "An error occurred while import project"


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
    stderr = err.decode(errors="replace")
    if code != 0:
        logger.warn("{stderr}", stderr=stderr)
        raise error.ProcessTerminated(code)
    logger.info("{stderr}", stderr=stderr)
    return result


def _set_path(column, cell_renderer, model, iter, colid):
    path = model.get_value(iter, colid)
    cell_renderer.set_property("text", path.path if path else "")


def _set_path_remap(column, cell_renderer, model, iter, colid):
    path = model.get_value(iter, colid)
    if path:
        cell_renderer.set_properties(
            font_desc=None, foreground=None, text=path.path
        )
    else:
        font = Pango.FontDescription()
        font.set_style(Pango.Style.ITALIC)
        cell_renderer.set_properties(
            font_desc=font,
            foreground="gray",
            text="(Click here to select an image)",
        )


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
        dialog.images = projectfile.image_paths(project.read_document())
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

        imgs = dict(
            (name, path) for name, path, save in iter_model(store1) if save
        )
        store2.clear()
        for name in dialog.images:
            store2.append((name, imgs.get(name)))
        if len(store2) == 0 or all_paths_set(store2):
            dialog.set_page_complete()

    def step_3(self, dialog):
        dialog.project_name_label.set_text(dialog.get_project_name())
        path_label = dialog.project_path_label
        fp = filepath.FilePath(dialog.project.path)
        path = fp.sibling(dialog.get_project_name()).path
        path_label.set_text(path)
        path_label.set_tooltip_text(path)
        dialog.open_label.set_text(str(dialog.get_open()))
        dialog.overwrite_label.set_text(str(dialog.get_overwrite()))
        images = iter_model(dialog.save_images_store, 0, 2)
        iimgs = (name for name, s in images if s)
        dialog.imported_images_label.set_text("\n".join(iimgs))
        self.show_machine_paths(dialog)
        store = dialog.map_images_store
        vbox = dialog.mapped_images_box
        vbox.foreach(vbox.remove)
        for i, (name, dest) in enumerate(iter_model(store)):
            nlabel = Gtk.Label(name + ":")
            nlabel.props.halign = Gtk.Align.FILL
            nlabel.props.valign = Gtk.Align.CENTER
            dlabel = Gtk.Label(dest.path)
            dlabel.set_tooltip_text(dest.path)
            dlabel.props.halign = Gtk.Align.FILL
            dlabel.props.valign = Gtk.Align.CENTER
            dlabel.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            box.pack_start(nlabel, False, True, 0)
            box.pack_start(dlabel, True, True, 0)
            vbox.pack_start(box, False, True, 3)
            box.show_all()

    def show_machine_paths(self, dialog):
        """Offer to replace the paths of the machine the project comes from."""

        project_settings = dialog.project.read_document().get("settings", {})
        for key, check in dialog.machine_path_checks.items():
            theirs = project_settings.get(key)
            ours = settings.get_app(key)
            differs = isinstance(theirs, str) and theirs != ours
            check.set_visible(differs)
            if differs:
                check.set_label(
                    _("Use {0} of this machine, {1}, instead of {2}").format(
                        key, ours, theirs
                    )
                )
                check.set_active(not os.path.isdir(theirs))

    def use_machine_paths(self, entry, keys):
        table = entry.setdefault("settings", {})
        for key in keys:
            table[key] = settings.get_app(key)

    def apply(
        self,
        project,
        name,
        factory,
        overwrite,
        open,
        store1,
        store2,
        machine_paths=(),
    ):
        entry = project.read_document()
        self.use_machine_paths(entry, machine_paths)
        imgs = self.get_images(project, entry, store1, store2)
        deferred = self.rebase_all(project, imgs, entry)
        deferred.addCallback(self.check_rebase)
        deferred.addCallback(lambda a: project.rename(name, overwrite))
        if open:
            deferred.addCallback(pass_through(project.open, factory))
        deferred.addErrback(pass_through(project.delete))

        def log_import_error(failure):
            logger.failure(error_on_import_project, failure)
            return failure

        deferred.addErrback(log_import_error)
        return deferred

    def get_images(self, project, entry, store1, store2):
        imagesfp = filepath.FilePath(project.path).child(".images")
        imgs = self.save_images(store1, imagesfp)
        self.remap_images(entry, store2, imgs)
        project.write_document(entry)
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
                        logger.error(
                            image_not_exists,
                            source=fp.path,
                            destination=destination.path,
                        )
                        continue
                    else:
                        raise
                else:
                    saved[name] = destination
        return saved

    def remap_images(self, entry, store, saved):
        for name, destination in saved.items():
            projectfile.remap_image(entry, name, destination.path)
        for name, path in iter_model(store):
            projectfile.remap_image(entry, name, path.path)
            saved[name] = path

    def rebase_all(self, project, images, entry):
        lst = []
        for name, path in images.items():
            for vmname, dev in projectfile.devices_for_image(entry, name):
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
    """
    Assistant to import a project: choose the archive and the project name,
    save the images of the archive, map the images used by the project and
    confirm.
    """

    NAME, PATH, SELECTED = range(3)
    archive_path = None
    project = None
    images = None
    humble = _HumbleImport()

    def __init__(self, factory):
        Window.__init__(self)
        self.factory = factory

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``importdialog.ui``."""

        # TODO: the Glade file has an unused image1 (Gtk.Image, stock
        # "gtk-add"), nothing refers to it.

        # save_images_store (Gtk.ListStore)
        self.save_images_store = Gtk.ListStore(str, object, bool)

        # map_images_store (Gtk.ListStore)
        self.map_images_store = Gtk.ListStore(str, object)

        # assistant (Gtk.Assistant)
        self.assistant = Gtk.Assistant(
            width_request=450,
            height_request=400,
            can_focus=False,
            border_width=12,
            title=_("Virtualbricks - Import project"),
            resizable=False,
            modal=True,
            window_position=Gtk.WindowPosition.CENTER,
        )
        # TODO: empty Glade placeholder, nothing to create.
        self.intro_grid = Gtk.Grid(
            visible=True,
            can_focus=False,
            margin_left=5,
            resize_mode=Gtk.ResizeMode.IMMEDIATE,
            row_spacing=3,
            column_spacing=6,
        )
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Project name:"),
        )
        self.intro_grid.attach(label1, 0, 1, 1, 1)
        label3 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("File:"),
            justify=Gtk.Justification.RIGHT,
            xalign=0,
        )
        self.intro_grid.attach(label3, 0, 0, 1, 1)
        self.project_name_entry = Gtk.Entry(
            visible=True,
            can_focus=True,
            secondary_icon_activatable=False,
        )
        self.intro_grid.attach(self.project_name_entry, 1, 1, 1, 1)
        self.archive_chooser = Gtk.FileChooserButton(
            visible=True,
            can_focus=False,
        )
        self.intro_grid.attach(self.archive_chooser, 1, 0, 1, 1)
        self.open_check = Gtk.CheckButton(
            label=_("Open after import"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0,
            draw_indicator=True,
        )
        self.intro_grid.attach(self.open_check, 0, 2, 2, 1)
        self.overwrite_check = Gtk.CheckButton(
            label=_("Overwrite existing project"),
            visible=True,
            can_focus=True,
            receives_default=False,
            xalign=0,
            draw_indicator=True,
        )
        self.intro_grid.attach(self.overwrite_check, 0, 3, 2, 1)
        self.warn_label = Gtk.Label(
            can_focus=False,
            label=_("A project with such name already exists."),
            attributes=pango_attr_list(Pango.attr_foreground_new(65535, 0, 0)),
        )
        self.intro_grid.attach(self.warn_label, 0, 4, 2, 1)
        self.assistant.append_page(self.intro_grid)
        self.assistant.set_page_type(
            self.intro_grid,
            Gtk.AssistantPageType.INTRO,
        )
        self.assistant.set_page_title(self.intro_grid, _("Import project"))
        self.assistant.set_page_has_padding(self.intro_grid, False)
        save_images_page = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            margin_left=5,
        )
        self.save_images_view = Gtk.TreeView(
            visible=True,
            can_focus=True,
            model=self.save_images_store,
            headers_clickable=False,
            search_column=0,
            enable_grid_lines=Gtk.TreeViewGridLines.BOTH,
        )
        treeviewcolumn1 = Gtk.TreeViewColumn.new()
        treeviewcolumn1.set_properties(title=_("Save"))
        save_image_cell = Gtk.CellRendererToggle()
        treeviewcolumn1.pack_start(save_image_cell, False)
        treeviewcolumn1.add_attribute(
            save_image_cell,
            "active",
            2,
        )
        self.save_images_view.append_column(treeviewcolumn1)
        treeviewcolumn2 = Gtk.TreeViewColumn.new()
        treeviewcolumn2.set_properties(title=_("Image name"))
        cellrenderertext1 = Gtk.CellRendererText()
        treeviewcolumn2.pack_start(cellrenderertext1, False)
        treeviewcolumn2.add_attribute(cellrenderertext1, "text", 0)
        self.save_images_view.append_column(treeviewcolumn2)
        self.save_path_column = Gtk.TreeViewColumn.new()
        self.save_path_column.set_properties(title=_("Image path"))
        self.save_path_cell = Gtk.CellRendererText()
        self.save_path_column.pack_start(self.save_path_cell, False)
        self.save_images_view.append_column(self.save_path_column)
        save_images_page.add(self.save_images_view)
        self.assistant.append_page(save_images_page)
        self.assistant.set_page_title(
            save_images_page,
            _("Save images"),
        )
        self.assistant.set_page_complete(save_images_page, True)
        self.assistant.set_page_has_padding(save_images_page, False)
        # TODO: empty Glade placeholder, nothing to create.
        map_images_page = Gtk.ScrolledWindow(
            visible=True,
            can_focus=True,
            margin_left=5,
        )
        self.map_images_view = Gtk.TreeView(
            visible=True,
            can_focus=True,
            model=self.map_images_store,
            headers_clickable=False,
            search_column=0,
            enable_grid_lines=Gtk.TreeViewGridLines.BOTH,
        )
        treeviewcolumn4 = Gtk.TreeViewColumn.new()
        treeviewcolumn4.set_properties(title=_("Image name"))
        cellrenderertext3 = Gtk.CellRendererText()
        treeviewcolumn4.pack_start(cellrenderertext3, False)
        treeviewcolumn4.add_attribute(cellrenderertext3, "text", 0)
        self.map_images_view.append_column(treeviewcolumn4)
        self.map_path_column = Gtk.TreeViewColumn.new()
        self.map_path_column.set_properties(title=_("Image path"))
        self.map_path_cell = Gtk.CellRendererText()
        self.map_path_column.pack_start(self.map_path_cell, False)
        self.map_images_view.append_column(self.map_path_column)
        map_images_page.add(self.map_images_view)
        self.assistant.append_page(map_images_page)
        self.assistant.set_page_title(
            map_images_page,
            _("Remap images"),
        )
        self.assistant.set_page_has_padding(map_images_page, False)
        vbox2 = Gtk.Box(
            visible=True,
            can_focus=False,
            margin_left=5,
            orientation=Gtk.Orientation.VERTICAL,
        )
        hbox3 = Gtk.Box(visible=True, can_focus=False, spacing=5)
        label4 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Project name:"),
            xalign=0,
        )
        hbox3.pack_start(label4, False, True, 0)
        self.project_name_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("testproject"),
            xalign=0,
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
            ),
        )
        hbox3.pack_start(self.project_name_label, False, True, 0)
        vbox2.pack_start(hbox3, False, True, 0)
        hbox4 = Gtk.Box(visible=True, can_focus=False, spacing=5)
        label6 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Project path:"),
            xalign=0,
        )
        hbox4.pack_start(label6, False, True, 0)
        self.project_path_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("/home/bob/.virtualbricks/testproject"),
            wrap=True,
            wrap_mode=Pango.WrapMode.CHAR,
            ellipsize=Pango.EllipsizeMode.MIDDLE,
            xalign=0,
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
            ),
        )
        hbox4.pack_start(self.project_path_label, True, True, 0)
        vbox2.pack_start(hbox4, False, True, 0)
        hbox1 = Gtk.Box(visible=True, can_focus=False, spacing=5)
        label5 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Open:"),
            xalign=0,
        )
        hbox1.pack_start(label5, False, True, 0)
        self.open_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("False"),
            xalign=0,
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
            ),
        )
        hbox1.pack_start(self.open_label, True, True, 0)
        vbox2.pack_start(hbox1, False, True, 0)
        hbox2 = Gtk.Box(visible=True, can_focus=False)
        label14 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("existing project overwritten:"),
            xalign=0,
        )
        hbox2.pack_start(label14, False, True, 0)
        self.overwrite_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("False"),
            xalign=0,
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
            ),
        )
        hbox2.pack_start(self.overwrite_label, True, True, 0)
        vbox2.pack_start(hbox2, False, True, 0)
        label8 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Images imported:"),
            xalign=0,
            yalign=0,
        )
        vbox2.pack_start(label8, False, True, 3)
        self.imported_images_label = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("debian 7\nubuntu 12.04"),
            xalign=0,
            attributes=pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
            ),
        )
        vbox2.pack_start(self.imported_images_label, False, True, 3)
        label10 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Images mapped:"),
            xalign=0,
        )
        vbox2.pack_start(label10, False, True, 3)
        self.mapped_images_box = Gtk.Box(visible=True, can_focus=False)
        # TODO: empty Glade placeholder, nothing to create.
        # TODO: empty Glade placeholder, nothing to create.
        # TODO: empty Glade placeholder, nothing to create.
        vbox2.pack_start(self.mapped_images_box, True, True, 0)
        self.machine_path_checks = {}
        for key in ("qemupath", "vdepath"):
            check = Gtk.CheckButton(visible=False, can_focus=True)
            self.machine_path_checks[key] = check
            vbox2.pack_start(check, False, True, 3)
        self.assistant.append_page(vbox2)
        self.assistant.set_page_type(
            vbox2,
            Gtk.AssistantPageType.CONFIRM,
        )
        self.assistant.set_page_complete(vbox2, True)
        self.assistant.set_page_has_padding(vbox2, False)
        # TODO: the internal child 'action_area' of self.assistant has no
        # public accessor in GTK 3. Glade sets only default values:
        # can_focus=False.

        # Signals
        self.map_images_store.connect(
            "row-changed", self.on_map_images_store_row_changed
        )
        self.assistant.connect("apply", self.on_assistant_apply)
        self.assistant.connect("cancel", self.on_assistant_cancel)
        self.assistant.connect("close", self.on_assistant_close)
        self.assistant.connect("prepare", self.on_assistant_prepare)
        self.project_name_entry.connect(
            "changed", self.on_project_name_entry_changed
        )
        self.archive_chooser.connect(
            "file-set",
            self.on_archive_chooser_file_set,
        )
        self.overwrite_check.connect(
            "toggled",
            self.on_overwrite_check_toggled,
        )
        save_image_cell.connect(
            "toggled",
            self.on_save_image_cell_toggled,
        )

    def get_root_widget(self) -> Gtk.Assistant:
        return self.assistant

    def show(self, parent=None):
        col1 = self.save_path_column
        cell1 = self.save_path_cell
        col1.set_cell_data_func(cell1, _set_path, 1)
        col2 = self.map_path_column
        cell2 = self.map_path_cell
        col2.set_cell_data_func(cell2, _set_path_remap, 1)
        view1 = self.save_images_view
        view1.connect(
            "button_press_event",
            self.on_button_press_event,
            col1,
            self.get_save_filechooserdialog,
        )
        view2 = self.map_images_view
        view2.connect(
            "button_press_event",
            self.on_button_press_event,
            col2,
            self.get_map_filechooserdialog,
        )
        Window.show(self, parent)

    def destroy(self):
        self.assistant.destroy()

    # assistant method helpers

    def set_page_complete(self, page=None, complete=True):
        if page is None:
            page = self.assistant.get_nth_page(
                self.assistant.get_current_page()
            )
        self.assistant.set_page_complete(page, complete)

    ####

    def get_project_name(self):
        return self.project_name_entry.get_text()

    def set_project_name(self, name):
        self.project_name_entry.set_text(name)

    def get_archive_path(self):
        return self.archive_chooser.get_filename()

    def get_open(self):
        return self.open_check.get_active()

    def get_overwrite(self):
        return self.overwrite_check.get_active()

    def get_filechooserdialog(self, model, path, title, action, stock_id):
        chooser = Gtk.FileChooserDialog(
            title,
            self.get_root_widget(),
            action,
            (
                "gtk-cancel",
                Gtk.ResponseType.CANCEL,
                stock_id,
                Gtk.ResponseType.OK,
            ),
        )
        chooser.set_modal(True)
        chooser.set_select_multiple(False)
        chooser.set_transient_for(self.get_root_widget())
        chooser.set_destroy_with_parent(True)
        chooser.set_position(Gtk.WindowPosition.CENTER)
        chooser.set_do_overwrite_confirmation(True)
        chooser.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        chooser.connect(
            "response", self.on_filechooserdialog_response, model, path
        )
        return chooser

    def get_save_filechooserdialog(self, model, path):
        return self.get_filechooserdialog(
            model,
            path,
            _("Save image as..."),
            Gtk.FileChooserAction.SAVE,
            "gtk-save",
        )

    def get_map_filechooserdialog(self, model, path):
        return self.get_filechooserdialog(
            model,
            path,
            _("Map image as..."),
            Gtk.FileChooserAction.OPEN,
            "gtk-open",
        )

    # callbacks

    def on_map_images_store_row_changed(self, model, path, iter):
        self.set_page_complete(complete=all_paths_set(model))

    def on_assistant_prepare(self, assistant, page):
        page_num = assistant.get_current_page()
        if page_num == 0:
            pass
        elif page_num == 1:
            ws = settings.get("workspace")
            deferred = self.humble.step_1(
                self,
                self.save_images_store,
                filepath.FilePath(ws).child("vimages"),
            )
            if deferred:
                ProgressBar(self.assistant).wait_for(deferred)
        elif page_num == 2:
            self.humble.step_2(
                self, self.save_images_store, self.map_images_store
            )
        elif page_num == 3:
            self.humble.step_3(self)
        else:
            logger.error(invalid_step_assitant, num=page_num)
        return True

    def on_assistant_cancel(self, assistant):
        if self.project:
            logger.info(removing_temporary_project, path=self.project.path)
            self.project.delete()
        assistant.destroy()
        return True

    def on_assistant_apply(self, assistant):
        deferred = self.humble.apply(
            self.project,
            self.get_project_name(),
            self.factory,
            self.get_overwrite(),
            self.get_open(),
            self.save_images_store,
            self.map_images_store,
            [
                key
                for key, check in self.machine_path_checks.items()
                if check.get_visible() and check.get_active()
            ],
        )
        ProgressBar(assistant).wait_for(deferred)
        return True

    def on_assistant_close(self, assistant):
        assistant.destroy()
        return True

    def on_archive_chooser_file_set(self, filechooser):
        filename = filechooser.get_filename()
        name = os.path.splitext(os.path.basename(filename))[0]
        if not self.get_project_name():
            self.set_project_name(name)
        return True

    def on_project_name_entry_changed(self, entry):
        self.set_import_sensitive(
            self.get_archive_path(), entry.get_text(), self.overwrite_check
        )
        return True

    def on_overwrite_check_toggled(self, checkbutton):
        self.set_import_sensitive(
            self.get_archive_path(),
            self.project_name_entry.get_text(),
            checkbutton,
        )
        return True

    def set_import_sensitive(self, filename, name, overwrite_btn):
        page = self.intro_grid
        label = self.warn_label
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

    def on_save_image_cell_toggled(self, renderer, path):
        model = self.save_images_store
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
                model.set_value(
                    model.get_iter(path),
                    self.PATH,
                    filepath.FilePath(filename),
                )
        dialog.destroy()
        return True
