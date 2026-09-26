# -*- test-case-name: virtualbricks.tests.gui.windows.test_projects -*-
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
The Projects window: find, open and look after the projects.

A searchable list of the projects, the most recently used first, and the
details of the selected one with every action: Open, Duplicate, Export,
Rename, Show in Files and Remove. New and Import are in the header bar.
The space a project takes is read in the background, for the selected
project only.
"""

import datetime

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, Gtk, Pango
from twisted.internet import threads
from twisted.logger import Logger

from virtualbricks import errors
from virtualbricks.config import projects
from virtualbricks.gui.markdownview import MarkdownView
from virtualbricks.gui.windows import projectname
from virtualbricks.gui.windows.base import _, pango_attr_list
from virtualbricks.i18n import ngettext
from virtualbricks.markdown import first_line

logger = Logger()
project_trashed = 'Project "{name}" moved to the trash'
project_deleted = 'Project "{name}" deleted'
cannot_remove = 'Cannot remove the project "{name}": {error}'
cannot_open = 'Cannot open the project "{name}": {error}'

MARGIN = 12
# The README in the details is drawn on the pane, as the labels around it.
README_CSS = b"textview, textview text { background-color: transparent; }"


def _label(text="", dim=False, bold=False, wrap=False, xalign=0.0, **props):
    label = Gtk.Label(
        visible=True, label=text, xalign=xalign, wrap=wrap, **props
    )
    if dim:
        label.get_style_context().add_class("dim-label")
    if bold:
        label.set_attributes(pango_attr_list(Pango.attr_weight_new(700)))
    return label


def human_size(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            if unit == "B":
                return f"{size:.0f} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1000
    return f"{size:.1f} TB"  # pragma: no cover


def when(timestamp, now=None):
    """Today at 14:03, Yesterday, 12 Sep, 3 Aug 2024."""

    now = datetime.datetime.now() if now is None else now
    moment = datetime.datetime.fromtimestamp(timestamp)
    days = (now.date() - moment.date()).days
    if days == 0:
        return _("Today at {time}").format(time=moment.strftime("%H:%M"))
    if days == 1:
        return _("Yesterday")
    if moment.year == now.year:
        return f"{moment.day} {moment.strftime('%b')}"
    return f"{moment.day} {moment.strftime('%b %Y')}"


def count_bricks(summary):
    total = sum(summary.bricks.values())
    return ngettext("{n} brick", "{n} bricks", total).format(n=total)


def facts(summary, now=None):
    """The line under a project's name in the list."""

    if summary.problem is not None:
        return _("Can't be read")
    parts = [count_bricks(summary), when(summary.modified, now)]
    missing = sum(1 for image in summary.images if not image.found)
    if missing:
        parts.append(
            ngettext(
                "{n} image missing", "{n} images missing", missing
            ).format(n=missing)
        )
    return " · ".join(parts)


class ProjectRow:
    def __init__(self, summary, is_open, now=None):
        self.summary = summary
        self.row = Gtk.ListBoxRow(visible=True)
        self.row.project = self
        box = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2,
            margin=8,
        )
        top = Gtk.Box(visible=True, spacing=6)
        self.name_label = _label(
            summary.name, bold=True, ellipsize=Pango.EllipsizeMode.END
        )
        top.pack_start(self.name_label, True, True, 0)
        self.open_badge = _label(_("Open"), dim=True)
        self.open_badge.set_visible(is_open)
        top.pack_end(self.open_badge, False, False, 0)
        box.pack_start(top, False, False, 0)
        line = first_line(summary.description)
        self.description_label = _label(
            line, dim=True, ellipsize=Pango.EllipsizeMode.END
        )
        self.description_label.set_visible(bool(line))
        box.pack_start(self.description_label, False, False, 0)
        self.facts_label = _label(facts(summary, now), dim=True)
        broken = summary.problem is not None or any(
            not image.found for image in summary.images
        )
        if broken:
            self.facts_label.get_style_context().add_class("warning")
        box.pack_start(self.facts_label, False, False, 0)
        self.row.add(box)

    def matches(self, text):
        text = text.casefold()
        return (
            text in self.summary.name.casefold()
            or text in self.summary.description.casefold()
        )


class ProjectsWindow:
    """
    The Projects window.

    gui is the main window: projects are opened, created and saved through
    it, as its menus do, and it runs the import and the export.
    """

    # Called when the window is closed.
    on_closed = None

    def __init__(self, gui, workspace=None, disk_usage=None):
        self.gui = gui
        self.workspace = projects if workspace is None else workspace
        if disk_usage is None:
            disk_usage = self._disk_usage_in_thread
        self._disk_usage = disk_usage
        self.rows = []
        self.selected = None
        self._usage_for = None
        self.destroyed = False
        self.build_ui()
        self.reload()

    def _disk_usage_in_thread(self, name):
        return threads.deferToThread(self.workspace.disk_usage, name)

    # The widgets

    def build_ui(self):
        self.window = Gtk.Window(
            title=_("Projects"),
            default_width=860,
            default_height=560,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            destroy_with_parent=True,
        )
        header = Gtk.HeaderBar(
            visible=True, show_close_button=True, title=_("Projects")
        )
        self.new_button = Gtk.Button(visible=True, label=_("New…"))
        header.pack_start(self.new_button)
        self.import_button = Gtk.Button(visible=True, label=_("Import…"))
        header.pack_start(self.import_button)
        self.window.set_titlebar(header)

        outer = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        self.info_bar = Gtk.InfoBar(
            visible=False,
            message_type=Gtk.MessageType.WARNING,
            show_close_button=True,
        )
        self.info_label = _label(wrap=True)
        self.info_bar.get_content_area().add(self.info_label)
        outer.pack_start(self.info_bar, False, False, 0)

        self.stack = Gtk.Stack(visible=True)
        self.stack.add_named(self._build_empty(), "empty")
        self.stack.add_named(self._build_projects(), "projects")
        outer.pack_start(self.stack, True, True, 0)
        self.window.add(outer)

        self.window.connect("destroy", self.on_destroy)
        self.window.connect("key-press-event", self.on_key_press)
        self.new_button.connect("clicked", self.on_new_clicked)
        self.import_button.connect("clicked", self.on_import_clicked)
        self.info_bar.connect("response", lambda bar, r: bar.hide())
        self.search_entry.connect("search-changed", self.on_search_changed)
        self.list.connect("row-selected", self.on_row_selected)
        self.list.connect("row-activated", self.on_row_activated)
        self.open_button.connect("clicked", self.on_open_clicked)
        self.duplicate_button.connect("clicked", self.on_duplicate_clicked)
        self.export_button.connect("clicked", self.on_export_clicked)

    def _build_empty(self):
        box = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
        )
        box.pack_start(
            _label(_("No projects yet"), bold=True, xalign=0.5),
            False,
            False,
            0,
        )
        box.pack_start(
            _label(
                _("A project is a lab: its bricks, events and images."),
                dim=True,
                xalign=0.5,
            ),
            False,
            False,
            0,
        )
        buttons = Gtk.Box(visible=True, spacing=6, halign=Gtk.Align.CENTER)
        self.empty_new_button = Gtk.Button(
            visible=True, label=_("New Project")
        )
        self.empty_new_button.get_style_context().add_class("suggested-action")
        self.empty_new_button.connect("clicked", self.on_new_clicked)
        buttons.pack_start(self.empty_new_button, False, False, 0)
        self.empty_import_button = Gtk.Button(
            visible=True, label=_("Import a Project…")
        )
        self.empty_import_button.connect("clicked", self.on_import_clicked)
        buttons.pack_start(self.empty_import_button, False, False, 0)
        box.pack_start(buttons, False, False, 0)
        return box

    def _build_projects(self):
        paned = Gtk.Paned(visible=True, position=320)
        left = Gtk.Box(visible=True, orientation=Gtk.Orientation.VERTICAL)
        self.search_entry = Gtk.SearchEntry(
            visible=True,
            placeholder_text=_("Find a project"),
            margin=6,
        )
        left.pack_start(self.search_entry, False, False, 0)
        scrolled = Gtk.ScrolledWindow(
            visible=True, hscrollbar_policy=Gtk.PolicyType.NEVER
        )
        # A click selects and shows the details; a double click or Enter
        # opens.
        self.list = Gtk.ListBox(visible=True, activate_on_single_click=False)
        self.list.set_filter_func(self._filter)
        scrolled.add(self.list)
        left.pack_start(scrolled, True, True, 0)
        paned.pack1(left, False, False)

        self.details_stack = Gtk.Stack(visible=True)
        self.details_stack.add_named(
            _label(_("Select a project"), dim=True, xalign=0.5), "none"
        )
        self.details_stack.add_named(self._build_details(), "details")
        paned.pack2(self.details_stack, True, False)
        return paned

    def _build_details(self):
        scrolled = Gtk.ScrolledWindow(
            visible=True, hscrollbar_policy=Gtk.PolicyType.NEVER
        )
        box = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin=18,
        )
        self.title_label = _label(
            bold=True, selectable=True, ellipsize=Pango.EllipsizeMode.END
        )
        box.pack_start(self.title_label, False, False, 0)
        self.path_label = _label(
            dim=True, selectable=True, ellipsize=Pango.EllipsizeMode.MIDDLE
        )
        box.pack_start(self.path_label, False, False, 0)
        self.problem_label = _label(wrap=True, selectable=True)
        self.problem_label.get_style_context().add_class("warning")
        box.pack_start(self.problem_label, False, False, 0)
        self.readme_view = MarkdownView(visible=True)
        style = Gtk.CssProvider()
        style.load_from_data(README_CSS)
        self.readme_view.get_style_context().add_provider(
            style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        box.pack_start(self.readme_view, False, False, 0)

        self.facts_grid = Gtk.Grid(
            visible=True, column_spacing=18, row_spacing=6, margin_top=6
        )
        self.fact_values = {}
        for i, (key, title) in enumerate(
            (
                ("bricks", _("Bricks")),
                ("events", _("Events")),
                ("images", _("Images")),
                ("disks", _("Private disks")),
                ("other", _("Other files")),
                ("used", _("Last used")),
            )
        ):
            self.facts_grid.attach(_label(title, dim=True), 0, i, 1, 1)
            value = _label(wrap=True, selectable=True, hexpand=True)
            self.facts_grid.attach(value, 1, i, 1, 1)
            self.fact_values[key] = value
        box.pack_start(self.facts_grid, False, False, 0)

        actions = Gtk.Box(visible=True, spacing=6, margin_top=12)
        self.open_button = Gtk.Button(visible=True, label=_("Open"))
        self.open_button.get_style_context().add_class("suggested-action")
        actions.pack_start(self.open_button, False, False, 0)
        self.duplicate_button = Gtk.Button(visible=True, label=_("Duplicate…"))
        actions.pack_start(self.duplicate_button, False, False, 0)
        self.export_button = Gtk.Button(visible=True, label=_("Export…"))
        actions.pack_start(self.export_button, False, False, 0)
        self.menu_button = Gtk.MenuButton(
            visible=True,
            tooltip_text=_("More"),
            image=Gtk.Image.new_from_icon_name(
                "view-more-symbolic", Gtk.IconSize.BUTTON
            ),
        )
        menu = Gio.Menu()
        menu.append(_("Rename…"), "project.rename")
        menu.append(_("Show in Files"), "project.show")
        menu.append(_("Remove…"), "project.remove")
        self.menu_button.set_menu_model(menu)
        actions.pack_start(self.menu_button, False, False, 0)
        box.pack_start(actions, False, False, 0)

        self.actions = Gio.SimpleActionGroup()
        for name, handler in (
            ("rename", self.on_rename),
            ("show", self.on_show),
            ("remove", self.on_remove),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.actions.add_action(action)
        self.window.insert_action_group("project", self.actions)
        scrolled.add(box)
        return scrolled

    def get_root_widget(self):
        return self.window

    def show(self, parent=None):
        if parent is not None:
            self.window.set_transient_for(parent)
        self.window.present()

    def show_problem(self, message):
        """Say why at the top, as at start-up when a project fails."""

        self.info_label.set_text(message)
        self.info_bar.show()

    # The list

    def reload(self):
        """Read the projects again, keeping the selection."""

        selected = self.selected.name if self.selected else None
        for child in self.list.get_children():
            self.list.remove(child)
        current = self.workspace.current
        open_name = current.name if current is not None else None
        self.rows = [
            ProjectRow(summary, summary.name == open_name)
            for summary in self.workspace.summaries()
        ]
        for row in self.rows:
            self.list.add(row.row)
        self.stack.set_visible_child_name("projects" if self.rows else "empty")
        self.select(selected or open_name)

    def select(self, name):
        for row in self.rows:
            if row.summary.name == name:
                self.list.select_row(row.row)
                return
        self.list.unselect_all()
        self.show_details(None)

    def _filter(self, row):
        return row.project.matches(self.search_entry.get_text())

    def on_search_changed(self, entry):
        self.list.invalidate_filter()

    def on_row_selected(self, listbox, row):
        self.show_details(row.project.summary if row is not None else None)

    def on_row_activated(self, listbox, row):
        self.open(row.project.summary.name)

    # The details

    def is_open(self, name):
        current = self.workspace.current
        return current is not None and current.name == name

    def show_details(self, summary):
        self.selected = summary
        if summary is None:
            self.details_stack.set_visible_child_name("none")
            return
        self.details_stack.set_visible_child_name("details")
        self.title_label.set_text(summary.name)
        self.path_label.set_text(summary.path)
        readable = summary.problem is None
        self.problem_label.set_text(
            _("The project file can't be read: {problem}").format(
                problem=summary.problem
            )
            if not readable
            else ""
        )
        self.problem_label.set_visible(not readable)
        readme = summary.description.strip()
        self.readme_view.set_markdown(readme)
        self.readme_view.set_visible(bool(readme))
        values = self.fact_values
        values["bricks"].set_text(
            ", ".join(
                f"{count} {kind}"
                for kind, count in sorted(summary.bricks.items())
            )
            or _("None")
        )
        values["events"].set_text(str(summary.events))
        values["images"].set_text(
            "\n".join(
                (
                    f"{image.name}: {image.path}"
                    if image.found
                    else _("{name}: {path}, not on this computer").format(
                        name=image.name, path=image.path or '""'
                    )
                )
                for image in summary.images
            )
            or _("None")
        )
        values["disks"].set_text("…")
        values["other"].set_text("…")
        values["used"].set_text(when(summary.modified))
        self.facts_grid.set_visible(readable)
        is_open = self.is_open(summary.name)
        self.open_button.set_sensitive(readable and not is_open)
        self.open_button.set_tooltip_text(
            _("This project is open") if is_open else None
        )
        self.duplicate_button.set_sensitive(readable)
        self.export_button.set_sensitive(readable)
        self.actions.lookup_action("rename").set_enabled(readable)
        self.read_usage(summary.name)

    def read_usage(self, name):
        self._usage_for = name
        deferred = self._disk_usage(name)
        deferred.addCallbacks(
            self.on_usage, self.on_usage_failed, (name,), None, (name,)
        )

    def on_usage(self, usage, name):
        if self.destroyed or name != self._usage_for:
            return
        self.fact_values["disks"].set_text(human_size(usage.private_disks))
        self.fact_values["other"].set_text(human_size(usage.other_files))

    def on_usage_failed(self, failure, name):
        if not self.destroyed and name == self._usage_for:
            self.fact_values["disks"].set_text(_("Unknown"))
            self.fact_values["other"].set_text(_("Unknown"))

    # The actions

    def open(self, name):
        if self.is_open(name) or not self._is_readable(name):
            return
        try:
            self.gui.on_open(name)
        except (OSError, errors.Error) as exc:
            logger.error(cannot_open, name=name, error=exc)
            self.show_problem(
                _("Cannot open {name}: {error}").format(name=name, error=exc)
            )
            return
        self.gui.set_title()
        self.window.destroy()

    def _is_readable(self, name):
        for row in self.rows:
            if row.summary.name == name:
                return row.summary.problem is None
        return False

    def name_dialog(self, kind, original=None):
        dialog = projectname.ProjectNameDialog(
            self.gui, kind, original, workspace=self.workspace
        )
        dialog.on_done = self.on_name_done
        dialog.show(self.window)
        return dialog

    def on_name_done(self, name):
        if self.destroyed:
            return
        if self.is_open(name):
            # New and an opened copy leave nothing to do here.
            self.window.destroy()
            return
        self.selected = None
        self.reload()
        self.select(name)

    def on_new_clicked(self, button):
        self.name_dialog(projectname.NEW)

    def on_import_clicked(self, button):
        self.gui.import_project(on_destroy=self.on_import_closed)

    def on_import_closed(self):
        if not self.destroyed:
            self.reload()

    def on_open_clicked(self, button):
        if self.selected is not None:
            self.open(self.selected.name)

    def on_duplicate_clicked(self, button):
        if self.selected is not None:
            self.name_dialog(projectname.DUPLICATE, self.selected.name)

    def on_export_clicked(self, button):
        if self.selected is not None:
            self.gui.export_project(self.selected, self.window)

    def on_rename(self, action=None, parameter=None):
        if self.selected is not None and self.selected.problem is None:
            self.name_dialog(projectname.RENAME, self.selected.name)

    def on_show(self, action=None, parameter=None):
        if self.selected is not None:
            uri = Gio.File.new_for_path(self.selected.path).get_uri()
            try:
                Gtk.show_uri_on_window(self.window, uri, Gdk.CURRENT_TIME)
            except Exception as exc:
                logger.error("{error}", error=exc)

    def on_remove(self, action=None, parameter=None):
        if self.selected is not None:
            dialog = RemoveDialog(self.workspace, self.selected)
            dialog.on_done = self.on_removed
            dialog.show(self.window)
            return dialog

    def on_removed(self, name):
        if not self.destroyed:
            self.selected = None
            self.reload()

    def on_key_press(self, window, event):
        if self.window.get_focus() is self.search_entry:
            return False
        if event.keyval == Gdk.KEY_F2:
            self.on_rename()
            return True
        if event.keyval == Gdk.KEY_Delete:
            self.on_remove()
            return True
        # typing searches
        return self.search_entry.handle_event(event)

    def on_destroy(self, window):
        self.destroyed = True
        if self.on_closed is not None:
            self.on_closed()


class RemoveDialog:
    """Ask whether to move a project to the trash or delete it for good."""

    TRASH = 1
    DELETE = 2
    on_done = None

    def __init__(self, workspace, summary, disk_usage=None):
        self.workspace = workspace
        self.summary = summary
        self.name = summary.name
        is_open = workspace.current is not None and (
            workspace.current.name == self.name
        )
        self.can_trash = not is_open and workspace.can_trash(self.name)
        if disk_usage is None:
            try:
                usage = workspace.disk_usage(self.name)
            except OSError:
                usage = None
        else:
            usage = disk_usage
        self.dialog = Gtk.MessageDialog(
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.QUESTION,
            text=_("Remove {name}?").format(name=self.name),
        )
        self.dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        if is_open:
            self.dialog.set_property("message-type", Gtk.MessageType.INFO)
            self.dialog.set_property(
                "text", _("{name} is open").format(name=self.name)
            )
            self.dialog.format_secondary_text(
                _("Open another project first, then remove {name}.").format(
                    name=self.name
                )
            )
            self.delete_button = self.trash_button = None
        else:
            self.delete_button = self.dialog.add_button(
                _("Delete Permanently"), self.DELETE
            )
            self.delete_button.get_style_context().add_class(
                "destructive-action"
            )
            self.trash_button = None
            if self.can_trash:
                self.trash_button = self.dialog.add_button(
                    _("Move to Trash"), self.TRASH
                )
                self.trash_button.get_style_context().add_class(
                    "suggested-action"
                )
                self.dialog.set_default_response(self.TRASH)
            self.dialog.format_secondary_text(self.explain(usage))
        self.dialog.connect("response", self.on_response)

    def explain(self, usage):
        if usage is not None and usage.private_disks:
            what = _("Its folder, with {size} of private disks, goes").format(
                size=human_size(usage.private_disks)
            )
        elif usage is not None:
            what = _("Its folder, {size}, goes").format(
                size=human_size(usage.total)
            )
        else:
            what = _("Its folder goes")
        if self.can_trash:
            where = _(" to the trash, where you can restore it.")
        else:
            where = _(" for good: the drive of the workspace has no trash.")
        return (
            what
            + where
            + " "
            + _("The images it uses stay in your image library.")
        )

    def show(self, parent=None):
        if parent is not None:
            self.dialog.set_transient_for(parent)
        self.dialog.show()

    def remove(self, how):
        if how == self.TRASH:
            self.workspace.trash(self.name)
            logger.info(project_trashed, name=self.name)
        else:
            self.workspace.delete(self.name)
            logger.info(project_deleted, name=self.name)

    def on_response(self, dialog, response_id):
        dialog.destroy()
        if response_id not in (self.TRASH, self.DELETE):
            return
        try:
            self.remove(response_id)
        except (OSError, errors.Error) as exc:
            logger.error(cannot_remove, name=self.name, error=exc)
            return
        if self.on_done is not None:
            self.on_done(self.name)
