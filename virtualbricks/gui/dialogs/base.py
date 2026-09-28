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
"""


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
