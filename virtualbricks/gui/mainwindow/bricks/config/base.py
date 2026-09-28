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
The panels that aren't on drafts yet, the event editor and the details of an
image: a ``ConfigController`` implements ``build_ui()``, that creates the
widgets, ``get_config_view()``, that returns the panel, and
``configure_brick()``, that OK calls.
"""


class ConfigController:
    """
    Base class of the panels without a draft.

    The panel returned by ``get_config_view()`` shows in a tab of the main
    window, with its OK and Cancel, which call the handlers below.
    """

    def __init__(self, original):
        self.original = original
        self.build_ui()

    def on_ok_button_clicked(self, button, gui):
        self.configure_brick(gui)
        gui.curtain_down()

    def on_cancel_button_clicked(self, button, gui):
        gui.curtain_down()
