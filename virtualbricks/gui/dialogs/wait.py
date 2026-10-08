# -*- test-case-name: virtualbricks.tests.gui.dialogs.test_wait -*-
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
The small window that says what the main window waits for, as Suspend and
Resume of a virtual machine: a line and a pulsing bar above the main
window, insensitive until it is done.
"""

from __future__ import annotations

from typing import TypeVar

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk
from twisted.internet import defer, task

from virtualbricks.gui.dialogs.base import GAP, MARGIN, Window, text_label
from virtualbricks.i18n import _

T = TypeVar("T")

# the seconds between two pulses of the bar
PULSE = 0.2


class WaitWindow(Window):
    """Say text above a window, insensitive until a Deferred fires."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.build_ui()
        self.pulsing = task.LoopingCall(self.bar.pulse)

    def build_ui(self) -> None:
        # no title bar, no close button: it goes when the wait is over
        self.window = Gtk.Window(
            title=_("Virtualbricks: action in progress"),
            modal=True,
            decorated=False,
            deletable=False,
            resizable=False,
            skip_taskbar_hint=True,
            skip_pager_hint=True,
            type_hint=Gdk.WindowTypeHint.DIALOG,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            destroy_with_parent=True,
        )
        box = Gtk.Box(
            visible=True,
            orientation=Gtk.Orientation.VERTICAL,
            spacing=GAP,
            margin=MARGIN,
        )
        self.label = text_label(self.text)
        box.pack_start(self.label, False, False, 0)
        self.bar = Gtk.ProgressBar(visible=True)
        box.pack_start(self.bar, False, False, 0)
        self.window.add(box)

    def get_root_widget(self) -> Gtk.Window:
        return self.window

    def wait_for(
        self, deferred: defer.Deferred[T], parent: Gtk.Window
    ) -> defer.Deferred[T]:
        """
        Show the window above parent, insensitive, until deferred fires;
        deferred, which fires with what it had.
        """

        parent.set_sensitive(False)
        self.show(parent)
        self.pulsing.start(PULSE, now=False)

        def done(result: T) -> T:
            self.pulsing.stop()
            self.window.destroy()
            parent.set_sensitive(True)
            return result

        return deferred.addBoth(done)
