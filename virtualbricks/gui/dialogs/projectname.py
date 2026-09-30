# -*- test-case-name: virtualbricks.tests.gui.dialogs.test_projectname -*-
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
One dialog for New Project, Rename Project and Duplicate Project.

The name is checked as you type, and the message appears under the field;
the main button waits until the name is valid. A failure keeps the dialog
open, with the reason.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango
from twisted.internet import defer
from twisted.logger import Logger

from virtualbricks import errors
from virtualbricks.config.workspace import projects
from virtualbricks.i18n import _
from virtualbricks.gui.pango import pango_attr_list

logger = Logger()
project_created = 'Project "{name}" created'
project_renamed = 'Project "{old}" renamed to "{name}"'
project_duplicated = 'Project "{old}" duplicated as "{name}"'

NEW = "new"
RENAME = "rename"
DUPLICATE = "duplicate"
MARGIN = 18


def _label(text="", dim=False, bold=False, wrap=False, **props):
    label = Gtk.Label(visible=True, label=text, xalign=0.0, wrap=wrap, **props)
    if dim:
        label.get_style_context().add_class("dim-label")
    if bold:
        label.set_attributes(pango_attr_list(Pango.attr_weight_new(700)))
    return label


class ProjectNameDialog:
    """
    Ask a name, and create, rename or duplicate a project with it.

    gui is the main window: the dialog saves, creates and opens projects
    through it, as its menus do, and renames and duplicates them through its
    engine. on_done, if set, is called after a change.
    """

    on_done = None

    def __init__(self, gui, kind, original=None, workspace=None):
        self.gui = gui
        self.kind = kind
        self.original = original
        self.workspace = projects if workspace is None else workspace
        self.build_ui()
        self.name_entry.set_text(self.suggested_name())
        self.check()

    # The widgets

    def build_ui(self):
        titles = {
            NEW: (_("New Project"), _("Create")),
            RENAME: (_("Rename Project"), _("Rename")),
            DUPLICATE: (_("Duplicate Project"), _("Duplicate")),
        }
        title, action = titles[self.kind]
        self.dialog = Gtk.Dialog(
            title=title,
            use_header_bar=True,
            modal=True,
            destroy_with_parent=True,
            default_width=420,
        )
        header = self.dialog.get_header_bar()
        if self.original is not None:
            header.set_subtitle(self.original)
        self.dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        self.ok_button = self.dialog.add_button(action, Gtk.ResponseType.OK)
        self.ok_button.get_style_context().add_class("suggested-action")
        self.dialog.set_default_response(Gtk.ResponseType.OK)

        box = self.dialog.get_content_area()
        box.set_properties(spacing=6, margin=MARGIN)
        labels = {
            NEW: _("Name"),
            RENAME: _("New name"),
            DUPLICATE: _("Name of the copy"),
        }
        box.pack_start(_label(labels[self.kind], bold=True), False, False, 0)
        self.name_entry = Gtk.Entry(visible=True, activates_default=True)
        box.pack_start(self.name_entry, False, False, 0)
        self.name_message = _label(dim=True, wrap=True)
        box.pack_start(self.name_message, False, False, 0)

        self.description_view = None
        if self.kind == NEW:
            box.pack_start(
                _label(_("Description"), bold=True, margin_top=6),
                False,
                False,
                0,
            )
            scrolled = Gtk.ScrolledWindow(
                visible=True,
                shadow_type=Gtk.ShadowType.IN,
                min_content_height=80,
            )
            self.description_view = Gtk.TextView(
                visible=True, wrap_mode=Gtk.WrapMode.WORD_CHAR
            )
            scrolled.add(self.description_view)
            box.pack_start(scrolled, True, True, 0)
            box.pack_start(
                _label(
                    _(
                        "Optional; it becomes the README of the project. The"
                        " project starts with a copy of the settings of the"
                        " open project."
                    ),
                    dim=True,
                    wrap=True,
                ),
                False,
                False,
                0,
            )

        self.open_check = None
        if self.kind == DUPLICATE:
            self.open_check = Gtk.CheckButton(
                visible=True,
                label=_("Open the copy"),
                active=True,
                margin_top=6,
            )
            box.pack_start(self.open_check, False, False, 0)

        self.error_label = _label(wrap=True, selectable=True)
        self.error_label.get_style_context().add_class("error")
        self.error_label.set_visible(False)
        box.pack_start(self.error_label, False, False, 0)

        self.name_entry.connect("changed", self.on_name_changed)
        self.dialog.connect("response", self.on_response)

    def get_root_widget(self):
        return self.dialog

    def show(self, parent=None):
        if parent is not None:
            self.dialog.set_transient_for(parent)
        self.dialog.show()

    # The name

    def suggested_name(self):
        if self.kind == RENAME:
            return self.original
        if self.kind == DUPLICATE:
            return self.workspace.free_name(f"{self.original}-copy")
        return self.workspace.free_name("new_project")

    def is_current(self):
        current = self.workspace.current
        return current is not None and current.name == self.original

    def bricks(self):
        """The bricks of the project renamed, if it's the open one."""

        if self.kind == RENAME and self.is_current():
            return [brick.name for brick in self.gui.brickfactory.bricks]
        return None

    def check(self):
        name = self.name_entry.get_text()
        if self.kind == RENAME:
            if name == self.original:
                self.ok_button.set_sensitive(False)
                self.show_message(None)
                return
            message = self.workspace.check_name(
                name, renaming=self.original, bricks=self.bricks()
            )
        elif self.kind == DUPLICATE:
            # the copy has the original's bricks
            message = self.workspace.check_name(name, renaming=None)
            if message is None:
                message = self.workspace.check_name(
                    name, renaming=self.original
                )
        else:
            message = self.workspace.check_name(name)
        self.show_message(message)
        self.ok_button.set_sensitive(message is None)

    def show_message(self, message):
        self.name_message.set_text(message or "")
        self.name_message.set_visible(bool(message))

    def on_name_changed(self, entry):
        self.error_label.set_visible(False)
        self.check()

    # The action

    def description(self):
        buffer = self.description_view.get_buffer()
        return buffer.get_text(
            buffer.get_start_iter(), buffer.get_end_iter(), False
        )

    def apply(self) -> defer.Deferred:
        """
        Do what the dialog is for, through the main window and its engine:
        a Deferred of the name, or of the failure of the engine.
        """

        name = self.name_entry.get_text()
        engine = self.gui.engine
        if self.kind == NEW:
            doing = defer.maybeDeferred(
                self.gui.on_new, name, self.description()
            )
            doing.addCallback(
                lambda _: logger.info(project_created, name=name)
            )
        elif self.kind == RENAME:
            doing = engine.rename_project(self.original, name)
            doing.addCallback(self._renamed, name)
        else:
            if self.is_current():
                doing = defer.maybeDeferred(self.gui.on_save)
            else:
                doing = defer.succeed(None)
            doing.addCallback(
                lambda _: engine.duplicate_project(self.original, name)
            )
            doing.addCallback(
                lambda _: logger.info(
                    project_duplicated, old=self.original, name=name
                )
            )
            if self.open_check.get_active():
                doing.addCallback(lambda _: self.gui.on_open(name))
        doing.addCallback(lambda _: name)
        return doing

    def _renamed(self, result, name):
        logger.info(project_renamed, old=self.original, name=name)
        self.gui.set_title()

    def on_response(self, dialog, response_id):
        if response_id != Gtk.ResponseType.OK:
            dialog.destroy()
            return
        if not self.ok_button.get_sensitive():
            return
        self.apply().addCallbacks(self._done, self._failed)

    def _done(self, name):
        self.dialog.destroy()
        if self.on_done is not None:
            self.on_done(name)

    def _failed(self, failure):
        failure.trap(OSError, errors.Error)
        self.error_label.set_text(str(failure.value))
        self.error_label.set_visible(True)
        self.check()
