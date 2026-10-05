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
Code shared by the windows and dialogs that build their UI in Python.

Every window subclasses ``Window`` and implements ``build_ui()``, that
creates the widgets, and ``get_root_widget()``, that returns the main
widget. Who wants to know when a window closes connects to the ``destroy``
signal of that widget. The settings of the bricks, of the events and of the
disk images are panels on drafts instead, of
:mod:`virtualbricks.gui.mainwindow.bricks.config.panel`.

The small dialogs that ask before an action, as Rename, Delete and Remove
Image, are an ``action_dialog()`` of ``text_label()`` lines.
"""

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from virtualbricks.gui.pango import pango_attr_list
from virtualbricks.i18n import _

# around the lines of a dialog, and between them
MARGIN = 18
GAP = 8


class Window:
    """
    A window or a dialog. The UI is built when the instance is made, unless
    a subclass makes it in its own ``__init__``; show() shows it, above
    parent if given.
    """

    def __init__(self):
        self.build_ui()

    def show(self, parent=None):
        window = self.get_root_widget()
        if parent is not None:
            window.set_transient_for(parent)
        window.show()


def text_label(
    text="", dim=False, bold=False, heading=False, visible=True, **props
):
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


def action_dialog(title, action, destructive=False):
    """
    A dialog with Cancel and the button of action in its header bar: the
    dialog, that button, and the box of its lines.
    """

    dialog = Gtk.Dialog(
        title=title,
        use_header_bar=True,
        modal=True,
        destroy_with_parent=True,
        default_width=440,
    )
    dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
    button = dialog.add_button(action, Gtk.ResponseType.OK)
    style = "destructive-action" if destructive else "suggested-action"
    button.get_style_context().add_class(style)
    box = dialog.get_content_area()
    box.set_properties(spacing=GAP, margin=MARGIN)
    return dialog, button, box
