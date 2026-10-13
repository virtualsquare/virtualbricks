# Virtualbricks - a vde/qemu gui written in python and GTK/Glade.
# Copyright (C) 2026 Virtualbricks team

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
Code shared by the windows and dialogs that build their UI in Python.

Every window subclasses ``Window`` and implements ``build_ui()``, that
creates the widgets, and ``get_root_widget()``, that returns the main
widget. Who wants to know when a window closes connects to the ``destroy``
signal of that widget. F1 in a window opens the page of the user guide that
its ``help_page`` names, of :mod:`virtualbricks.gui.help`. The settings of
the bricks, of the events and of the disk images are panels on drafts
instead, of :mod:`virtualbricks.gui.mainwindow.bricks.config.panel`.

The small dialogs that ask before an action, as Rename, Delete and Remove
Image, are an ``action_dialog()`` of ``text_label()`` lines.
"""

from __future__ import annotations

from typing import Any

from gi.repository import Gdk, Gtk, Pango

from virtualbricks.gui.help import show_help
from virtualbricks.gui.pango import pango_attr_list
from virtualbricks.i18n import _

# the width of a dialog, around its lines, and between them
WIDTH = 440
MARGIN = 18
GAP = 8


class Window:
    """
    A window or a dialog. The UI is built when the instance is made: a
    subclass with an ``__init__`` of its own calls this one once what
    ``build_ui()`` reads is set. show() shows it, above parent if given.
    """

    def __init__(self) -> None:
        self.build_ui()
        self.get_root_widget().connect("key-press-event", self.on_help_key)

    @property
    def help_page(self) -> str | None:
        """The page of the guide about the window, None for its index."""

        return None

    def build_ui(self) -> None:
        """Make the widgets."""

        raise NotImplementedError

    def get_root_widget(self) -> Gtk.Window:
        """The window, or the dialog."""

        raise NotImplementedError

    def show(self, parent: Gtk.Window | None = None) -> None:
        window = self.get_root_widget()
        if parent is not None:
            window.set_transient_for(parent)
        window.show()

    def on_help_key(self, window: Gtk.Window, event: Gdk.EventKey) -> bool:
        """F1 opens the page of the guide about the window."""

        # not Ctrl+F1, which shows a tooltip, nor Shift+F1
        modifiers = event.state & Gtk.accelerator_get_default_mod_mask()
        if event.keyval != Gdk.KEY_F1 or modifiers:
            return False
        show_help(window, self.help_page)
        return True


def text_label(
    text: str = "",
    dim: bool = False,
    bold: bool = False,
    heading: bool = False,
    visible: bool = True,
    **props: Any,
) -> Gtk.Label:
    """A line of a dialog, wrapped: grey if dim, bold, or bold and larger."""

    label = Gtk.Label(
        visible=visible,
        label=text,
        xalign=0.0,
        wrap=True,
        max_width_chars=56,
        **props,
    )
    if dim:
        label.get_style_context().add_class("dim-label")
    if heading:
        label.set_attributes(
            pango_attr_list(
                Pango.attr_weight_new(Pango.Weight.BOLD),
                Pango.attr_scale_new(1.15),
            )
        )
    elif bold:
        label.set_attributes(
            pango_attr_list(Pango.attr_weight_new(Pango.Weight.BOLD))
        )
    return label


def action_dialog(
    title: str, action: str, destructive: bool = False
) -> tuple[Gtk.Dialog, Gtk.Widget, Gtk.Box]:
    """
    A dialog with Cancel and the button of action in its header bar: the
    dialog, that button, and the box of its lines.
    """

    dialog = Gtk.Dialog(
        title=title,
        use_header_bar=True,
        modal=True,
        destroy_with_parent=True,
        default_width=WIDTH,
    )
    dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
    button = dialog.add_button(action, Gtk.ResponseType.OK)
    style = "destructive-action" if destructive else "suggested-action"
    button.get_style_context().add_class(style)
    box = dialog.get_content_area()
    box.set_properties(spacing=GAP, margin=MARGIN)
    # else GTK makes it as tall as the lines are at their narrowest
    box.set_size_request(WIDTH - 2 * MARGIN, -1)
    return dialog, button, box
