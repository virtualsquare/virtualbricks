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
Dialog with a progress bar shown during long operations.
"""

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk
from twisted.internet import task

from virtualbricks.gui.windows.base import _, _Dialog


class ProgressBarDialog(_Dialog):
    """
    A pulsing progress bar shown until the deferred fires.
    """

    def __init__(self, deferred):
        """
        :type deferred: twisted.internet.defer.Deferred
        """

        self._deferred = deferred
        self.build_ui()

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``progressbardialog.ui``."""

        # dialog (Gtk.Dialog)
        self.dialog = Gtk.Dialog(
            width_request=200,
            height_request=50,
            can_focus=False,
            margin_top=5,
            margin_bottom=5,
            title=_("Virtualbricks: action in progress"),
            modal=True,
            window_position=Gtk.WindowPosition.CENTER_ALWAYS,
            destroy_with_parent=True,
            type_hint=Gdk.WindowTypeHint.NOTIFICATION,
            skip_taskbar_hint=True,
            skip_pager_hint=True,
            urgency_hint=True,
            decorated=False,
            deletable=False,
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
        # TODO: empty Glade placeholder, nothing to create.
        # TODO: empty Glade placeholder, nothing to create.
        content_area.child_set(action_area, expand=False, fill=False)
        label1 = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Please wait..."),
        )
        content_area.pack_start(label1, False, True, 0)
        self.progress = Gtk.ProgressBar(visible=True, can_focus=False)
        content_area.pack_start(self.progress, False, True, 0)

    def get_root_widget(self) -> Gtk.Dialog:
        return self.dialog

    def show(self, parent):
        """
        :type parent: Gtk.Window
        :rtype: None
        """

        looping_call = task.LoopingCall(self.progress.pulse)
        looping_call.start(0.2, False)
        self._deferred.addBoth(self._stop, looping_call)
        super().show(parent)

    def _stop(self, passthru, looping_call):
        """
        :type passthru: Any
        :type looping_call: twisted.internet.task.LoopingCall
        :rtype: Any
        """

        looping_call.stop()
        self.dialog.destroy()
        return passthru
