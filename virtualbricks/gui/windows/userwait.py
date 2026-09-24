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
Window shown while the user waits for a long operation.
"""

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk
from twisted.internet import defer, task

from virtualbricks.gui.windows.base import _


class Freezer:
    """
    Show a window with a pulsing progress bar and make the parent window
    insensitive until an operation completes.
    """

    def __init__(self, freeze, unfreeze, parent):
        """
        :type freeze: Callable
        :type unfreeze: Callable
        :type parent: Optional[Gtk.Window]
        """

        self.freeze_parent_window = freeze
        self.unfreeze_parent_window = unfreeze
        self.build_ui()
        self.window.set_transient_for(parent)
        self.window.set_modal(True)

    def build_ui(self) -> None:
        """Create the widgets, formerly in ``userwait.ui``."""

        # window (Gtk.Window)
        self.window = Gtk.Window(
            width_request=200,
            height_request=50,
            can_focus=False,
            title=_("Virtualbricks: action in progress"),
            window_position=Gtk.WindowPosition.CENTER_ALWAYS,
            destroy_with_parent=True,
            type_hint=Gdk.WindowTypeHint.NOTIFICATION,
            skip_taskbar_hint=True,
            skip_pager_hint=True,
            urgency_hint=True,
            decorated=False,
            deletable=False,
        )
        vbox1 = Gtk.Box(
            visible=True,
            can_focus=False,
            orientation=Gtk.Orientation.VERTICAL,
        )
        Pleaselabel = Gtk.Label(
            visible=True,
            can_focus=False,
            label=_("Please wait"),
        )
        vbox1.pack_start(Pleaselabel, True, True, 0)
        self.progress = Gtk.ProgressBar(visible=True, can_focus=False)
        vbox1.pack_start(self.progress, False, False, 0)
        label2 = Gtk.Label(visible=True, can_focus=False)
        vbox1.pack_start(label2, True, True, 0)
        self.window.add(vbox1)

    def get_root_widget(self) -> Gtk.Window:
        return self.window

    def wait_for(self, deferred, *args):
        """
        :type deferred: Union[twisted.internet.defer.Deferred[Any], Callable]
        :type args: Tuple[Any]
        :rtype: twisted.internet.defer.Deferred[Any]
        """

        if not isinstance(deferred, defer.Deferred):
            if callable(deferred):
                deferred = defer.maybeDeferred(deferred, *args)
            else:
                raise RuntimeError("Invalid argument")
        pulse = self.start()
        deferred.addBoth(self.stop, pulse)
        return deferred

    def start(self):
        """
        :rtype: twisted.internet.task.LoopingCall
        """

        self.freeze_parent_window()
        self.window.show_all()
        looping_call = task.LoopingCall(self.progress.pulse)
        looping_call.start(0.2, False)
        return looping_call

    def stop(self, passthru, looping_call):
        """
        :type passthru: Any
        :type looping_call: twisted.internet.task.LoopingCall
        :rtype: Any
        """

        looping_call.stop()
        self.window.destroy()
        self.unfreeze_parent_window()
        return passthru


class ProgressBar:
    """
    Wait for an operation, freezing a dialog.
    """

    def __init__(self, dialog):
        self.freezer = Freezer(lambda: None, lambda: None, dialog)

    def wait_for(self, something, *args):
        return self.freezer.wait_for(something, *args)
